import asyncio
import importlib
import logging
from contextlib import suppress

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands, tasks

from config.logs import LOG_PRESENCE, LOGGING_ENABLED
from config.owners import ERROR_REPORT_USER_ID
from config.settings import settings
from config.token import CLOUDFLARE_TUNNEL_TOKEN
from core import processes
from core.database import Database
from core.global_admin import install as install_global_admin
from core.music import close_music_nodes, start_music_node
from core.prefix import get_prefix
from core.presence import start_presence_loop
from src import COMMAND_MODULES
from view import ErrorReportView, bug_embed, command_usage_embed, error_embed
from web.dashboard import start_dashboard_server
from web.server import start_server
from web.status import start_status_server
from web.transcripts import start_transcript_server
from web.tunnel import CloudflareTunnel
from web.verify import start_verify_server

log = logging.getLogger("purpurite")


class SekaiBot(commands.Bot):
    def __init__(self, dev: bool = False) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        # Needed for join/leave logs, welcomes and autoroles. Also toggle it in
        # the Developer Portal (Bot -> Privileged Gateway Intents) or login fails.
        intents.members = True
        intents.presences = LOGGING_ENABLED and LOG_PRESENCE
        super().__init__(
            command_prefix=get_prefix, intents=intents, help_command=None
        )
        self.dev = dev
        self.start_time = discord.utils.utcnow()
        self.db = Database()
        self.prefix_cache: dict[int, str] = {}
        self._presence_task: tasks.Loop | None = None
        self._emoji_task: asyncio.Task | None = None
        self._web_runner: web.AppRunner | None = None
        self._status_runner: web.AppRunner | None = None
        self._transcript_runner: web.AppRunner | None = None
        self._verify_runner: web.AppRunner | None = None
        self._dashboard_runner: web.AppRunner | None = None
        self.tunnel: CloudflareTunnel | None = None

    async def setup_hook(self) -> None:
        loop = asyncio.get_running_loop()
        # Signal handlers run on the main thread, so hop back onto the loop
        # instead of letting KeyboardInterrupt cancel close() halfway through.
        processes.set_shutdown_hook(
            lambda _signum: loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.close())
            )
        )

        port = settings.dev_web_port if self.dev else settings.web_port
        status_port = (
            settings.dev_status_port if self.dev else settings.status_port
        )
        transcript_port = (
            settings.dev_transcript_port if self.dev else settings.transcript_port
        )
        verify_port = (
            settings.dev_verify_port if self.dev else settings.verify_port
        )
        dashboard_port = (
            settings.dev_dashboard_port if self.dev else settings.dashboard_port
        )
        # A previous instance that was force-closed can still hold these
        # ports; clear them before anything tries to bind.
        processes.reclaim_ports(
            {port, status_port, transcript_port, verify_port, dashboard_port})

        await self.db.connect()

        for module_path in COMMAND_MODULES:
            module = importlib.import_module(module_path)
            module.setup(self)
            log.info("Loaded commands from %s", module_path)

        # Let configured global admins pass every command's permission checks.
        install_global_admin(self)

        # Sync application emojis on startup, then watch the folder for new files.
        from core.emojis import start_emoji_watcher, sync_application_emojis
        try:
            synced = await sync_application_emojis(self)
        except Exception:
            log.exception("Initial emoji sync failed")
            synced = False
        self._emoji_task = start_emoji_watcher(self, synced=synced)
        self._presence_task = start_presence_loop(self)
        start_music_node(self)

        self._web_runner = await start_server(self, settings.web_host, port)

        self._status_runner = await start_status_server(
            self, settings.web_host, status_port
        )

        self._transcript_runner = await start_transcript_server(
            self, settings.web_host, transcript_port
        )

        self._verify_runner = await start_verify_server(
            self, settings.web_host, verify_port
        )

        self._dashboard_runner = await start_dashboard_server(
            self, settings.web_host, dashboard_port
        )

        if self.dev:
            log.info("Dev mode: using the dev token")
        self.tunnel = CloudflareTunnel(CLOUDFLARE_TUNNEL_TOKEN)
        await self.tunnel.start()
        log.info(
            "Tunnel targets: main page http://%s:%s · verification "
            "http://%s:%s · dashboard http://%s:%s",
            settings.web_host,
            port,
            settings.web_host,
            verify_port,
            settings.web_host,
            dashboard_port)

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandInvokeError) and isinstance(
            error.original, aiohttp.ClientConnectionError
        ):
            log.warning(
                "Network error while running %s: %s", ctx.command, error.original
            )
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("You don't have permission to use that command."))
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=error_embed("That command only works in a server."))
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                embed=error_embed(str(error) or "You can't use that command here.")
            )
            return
        if isinstance(error, commands.UserInputError):
            # Wrong arguments are user mistakes, not bugs — show the format
            # and an example instead of filing a report.
            problem = str(error) or None
            if ctx.command is not None:
                await ctx.send(
                    embed=command_usage_embed(
                        ctx.command, prefix=ctx.prefix, problem=problem
                    )
                )
            else:
                await ctx.send(
                    embed=error_embed(problem or "That isn't the right usage.")
                )
            return
        log.error("Command failed: %s", error, exc_info=error)
        await self._report_error(ctx, error)

    async def _report_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        original = (
            error.original
            if isinstance(error, commands.CommandInvokeError)
            else error
        )
        detail = f"{type(original).__name__}: {original}"[:1200]
        command = ctx.command.qualified_name if ctx.command else "unknown"

        where = (
            f"{ctx.guild.name} ({ctx.guild.id}) · {ctx.channel}"
            if ctx.guild is not None
            else "direct messages"
        )
        view = ErrorReportView(
            self,
            prefix=ctx.prefix,
            command=command,
            detail=detail,
            author=ctx.author,
            where=where)
        with suppress(discord.HTTPException):
            await ctx.send(
                embed=bug_embed(f"{ctx.prefix}{command}", detail), view=view
            )

    async def send_error_dm(
        self,
        *,
        reporter: discord.abc.User,
        author: discord.abc.User,
        prefix: str,
        command: str,
        detail: str,
        where: str) -> bool:
        user = self.get_user(ERROR_REPORT_USER_ID)
        if user is None:
            try:
                user = await self.fetch_user(ERROR_REPORT_USER_ID)
            except discord.HTTPException:
                return False

        try:
            await user.send(
                f"Hey, a bug was reported by {reporter} (`{reporter.id}`) "
                f"with the error:\n```\n{detail}\n```\n"
                f"Command: `{prefix}{command}` · {where}\n"
                f"Run by: {author} (`{author.id}`)"
            )
        except discord.HTTPException:
            return False
        return True

    async def close(self) -> None:
        log.info("Shutting down")
        # Free the listening ports first so a restart can bind even if a
        # later cleanup step is slow.
        if self._status_runner is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._status_runner.cleanup(), timeout=5)
            self._status_runner = None
        if self._transcript_runner is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._transcript_runner.cleanup(), timeout=5)
            self._transcript_runner = None
        if self._verify_runner is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._verify_runner.cleanup(), timeout=5)
            self._verify_runner = None
        if self._dashboard_runner is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._dashboard_runner.cleanup(), timeout=5)
            self._dashboard_runner = None
        if self._web_runner is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._web_runner.cleanup(), timeout=5)
            self._web_runner = None

        if self._emoji_task is not None:
            self._emoji_task.cancel()
            with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self._emoji_task, timeout=5)
            self._emoji_task = None
        if self._presence_task is not None:
            self._presence_task.stop()
            self._presence_task.cancel()
            self._presence_task = None
        with suppress(Exception):
            await asyncio.wait_for(close_music_nodes(), timeout=15)
        if self.tunnel is not None:
            with suppress(Exception):
                await asyncio.wait_for(self.tunnel.stop(), timeout=15)
        processes.kill_all()
        with suppress(Exception):
            await asyncio.wait_for(self.db.close(), timeout=5)
        await super().close()
        log.info("Shutdown complete")

