import asyncio
import logging
import os
import shutil

from core import processes

log = logging.getLogger("sekai.tunnel")


class CloudflareTunnel:
    def __init__(self, token: str) -> None:
        self.token = token
        self.process: asyncio.subprocess.Process | None = None
        self._drain_task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> bool:
        if not self.token or self.token.startswith("YOUR_"):
            log.warning("CLOUDFLARE_TUNNEL_TOKEN is not set, tunnel disabled")
            return False

        cloudflared = shutil.which("cloudflared")
        if cloudflared is None:
            log.warning("cloudflared not found on PATH, tunnel disabled")
            return False

        self.process = await asyncio.create_subprocess_exec(
            cloudflared,
            "tunnel",
            "--no-autoupdate",
            "run",
            "--token",
            self.token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=os.name == "posix")
        processes.adopt(self.process.pid)
        self._drain_task = asyncio.create_task(self._drain())
        log.info("Cloudflare named tunnel started")
        return True

    async def _drain(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    return
                text = line.decode(errors="replace").strip()
                if text:
                    log.debug("cloudflared: %s", text)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._drain_task is not None:
            self._drain_task.cancel()
            await asyncio.gather(self._drain_task, return_exceptions=True)
            self._drain_task = None

        if self.process is not None and self.process.returncode is None:
            pid = self.process.pid
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                processes.kill_tree(pid)
                await self.process.wait()
        if self.process is not None:
            processes.forget(self.process.pid)
        self.process = None
