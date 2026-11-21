import atexit
import ctypes
import logging
import os
import re
import signal
import subprocess
import threading
import time
from contextlib import suppress

log = logging.getLogger("sekai.processes")

_pids: set[int] = set()
_job = None
_job_ready = False
_kernel32 = None
_installed = False
_previous_handlers: dict[int, object] = {}
_interrupted = False
_shutdown_hook = None
_console_handler_ref = None

# After the first Ctrl+C the bot still has this long to close cleanly before
# the process is forced down, so a wedged shutdown never keeps the ports.
SHUTDOWN_GRACE = 20.0

PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _build_job():
    """Create a Windows job that kills every assigned process when its last
    handle closes (i.e. when the bot dies, even on a force kill)."""
    global _kernel32, _job, _job_ready

    if os.name != "nt" or _job_ready:
        return _job
    _job_ready = True

    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD)

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        if not kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info)):
            raise OSError(
                ctypes.get_last_error(), "SetInformationJobObject failed"
            )
    except (OSError, AttributeError) as exc:
        log.warning("Could not set up child process job object: %s", exc)
        return None

    _kernel32 = kernel32
    _job = job
    return _job


def adopt(pid: int) -> None:
    """Track a child process so it is killed when the bot stops."""
    _pids.add(pid)
    if os.name != "nt":
        return
    job = _build_job()
    if job is None:
        return
    handle = _kernel32.OpenProcess(
        PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid
    )
    if not handle:
        log.debug("Could not open pid %s for job assignment", pid)
        return
    try:
        if not _kernel32.AssignProcessToJobObject(job, handle):
            log.debug(
                "Could not assign pid %s to the job (error %s)",
                pid,
                ctypes.get_last_error())
    finally:
        _kernel32.CloseHandle(handle)


def forget(pid: int) -> None:
    _pids.discard(pid)


def kill_tree(pid: int) -> None:
    """Force-kill a child and everything it spawned."""
    _pids.discard(pid)
    if os.name == "nt":
        with suppress(OSError):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
        return
    try:
        os.killpg(pid, signal.SIGKILL)
        return
    except OSError:
        pass
    with suppress(OSError):
        os.kill(pid, signal.SIGKILL)


def kill_all() -> None:
    for pid in list(_pids):
        log.warning("Killing leftover child process %s", pid)
        kill_tree(pid)


def force_exit(code: int) -> None:
    """Kill every child, then leave immediately.

    os._exit skips atexit, so children must go first or they outlive the bot.
    """
    with suppress(Exception):
        kill_all()
    os._exit(code)


def listener_pids(port: int) -> list[int]:
    """PIDs of the processes listening on a local TCP port."""
    if os.name == "nt":
        try:
            output = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW).stdout
        except OSError:
            return []
        suffix = f":{port}"
        pids: list[int] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            if parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
                continue
            if not parts[1].endswith(suffix):
                continue
            with suppress(ValueError):
                pid = int(parts[4])
                if pid > 0 and pid != os.getpid() and pid not in pids:
                    pids.append(pid)
        return pids

    # Linux: ss only reports listening sockets and includes PIDs.
    try:
        result = subprocess.run(
            ["ss", "-H", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True)
    except OSError:
        result = None
    if result is not None:
        pids = [
            pid
            for pid in {int(match) for match in re.findall(r"pid=(\d+)", result.stdout)}
            if pid != os.getpid()
        ]
        if pids:
            return pids

    for command in (
        ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
        ["fuser", "-n", "tcp", str(port)]):
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except OSError:
            continue
        pids = []
        for token in result.stdout.split():
            with suppress(ValueError):
                pid = int(token)
                if pid > 0 and pid != os.getpid() and pid not in pids:
                    pids.append(pid)
        return pids
    return []


def listener_pid(port: int) -> int | None:
    """PID of the process listening on a local TCP port."""
    pids = listener_pids(port)
    return pids[0] if pids else None


# Never touch these even if a listening socket somehow points at them.
_PROTECTED_IMAGES = {
    "system",
    "registry",
    "smss",
    "csrss",
    "wininit",
    "winlogon",
    "services",
    "lsass",
    "svchost",
    "explorer",
    "dwm",
}


def reclaim_ports(ports: set[int] | list[int]) -> dict[int, int]:
    """Kill whatever listens on these local ports so a restart can bind.

    A previous bot (or its managed NodeLink) that was force-closed can keep
    the sockets open. This runs before the web servers start and returns
    {port: killed_pid} for anything it cleared.
    """
    freed: dict[int, int] = {}
    for port in sorted(set(ports)):
        for pid in listener_pids(port):
            name = image_name(pid)
            if name in _PROTECTED_IMAGES:
                log.warning(
                    "Port %s is held by %s (pid %s); not killing it",
                    port,
                    name,
                    pid)
                continue
            log.warning(
                "Port %s is already in use by %s (pid %s); killing it",
                port,
                name or "an unknown process",
                pid)
            if os.name == "nt":
                # /T also takes down whatever the stale instance spawned.
                kill_tree(pid)
            else:
                with suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
            freed[port] = pid

    if not freed:
        return freed

    # Give the OS a moment to release the sockets before aiohttp binds.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if all(not listener_pids(port) for port in freed):
            break
        time.sleep(0.15)
    return freed


def image_name(pid: int) -> str | None:
    """Lower-case executable base name for a PID."""
    if os.name != "nt":
        # Linux/macOS: /proc/<pid>/comm gives the kernel process name
        # (truncated to 15 chars, but enough for "node"/"nodejs"/"python3").
        # Fall back to ps where /proc is unavailable.
        try:
            with open(f"/proc/{pid}/comm", "r", encoding="utf-8") as f:
                name = f.read().strip().lower()
            if name:
                return name
        except OSError:
            pass
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True)
        except OSError:
            return None
        name = result.stdout.strip().lower()
        return name or None

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return None
        return os.path.basename(buffer.value).lower().removesuffix(".exe")
    finally:
        kernel32.CloseHandle(handle)


def set_shutdown_hook(hook) -> None:
    """Register a coroutine-friendly graceful shutdown, e.g. bot.close()."""
    global _shutdown_hook
    _shutdown_hook = hook


def _request_shutdown(signum: int) -> None:
    hook = _shutdown_hook
    if hook is None:
        raise KeyboardInterrupt
    try:
        hook(signum)
    except Exception:
        log.exception("Shutdown hook failed")
        force_exit(1)


def _start_watchdog() -> None:
    timer = threading.Timer(SHUTDOWN_GRACE, force_exit, args=(1))
    timer.daemon = True
    timer.start()


def _handle_signal(signum: int, frame) -> None:
    global _interrupted
    if _shutdown_hook is not None:
        if _interrupted:
            force_exit(1)
        _interrupted = True
        log.info("Received signal %s; shutting down", signum)
        _start_watchdog()
        _request_shutdown(signum)
        return

    log.info("Received signal %s; stopping child processes", signum)
    kill_all()
    previous = _previous_handlers.get(signum)
    if previous == signal.SIG_IGN:
        return
    if callable(previous):
        previous(signum, frame)
        return
    with suppress(OSError, ValueError):
        signal.signal(signum, signal.SIG_DFL)
    with suppress(OSError):
        os.kill(os.getpid(), signum)


def _handle_sigint(signum: int, frame) -> None:
    """Graceful on the first Ctrl+C, hard exit on the second or after a while."""
    global _interrupted
    if _interrupted:
        force_exit(1)
    _interrupted = True
    _start_watchdog()
    # Raising KeyboardInterrupt would cancel the loop mid-cleanup, so the
    # graceful hook (bot.close) runs as a normal task instead.
    _request_shutdown(signum)


def _console_ctrl(event: int) -> bool:
    # Closing the terminal window or logging off does not run atexit or any
    # asyncio cleanup, so the children have to go synchronously here.
    if event in (2, 5, 6):  # CLOSE, LOGOFF, SHUTDOWN
        log.info("Console closing; stopping child processes")
        kill_all()
    return False


def _install_console_handler() -> None:
    global _console_handler_ref
    if os.name != "nt" or _console_handler_ref is not None:
        return
    try:
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        _console_handler_ref = handler_type(_console_ctrl)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(
            _console_handler_ref, True
        )
    except (OSError, AttributeError):
        log.warning("Could not install the console close handler")


def install() -> None:
    """Hook interpreter exit and fatal signals so no orphan is left behind."""
    global _installed
    if _installed:
        return
    _installed = True
    atexit.register(kill_all)
    # SIGINT still raises KeyboardInterrupt like Python's default, so
    # discord.py can close cleanly; the watchdog guarantees the process dies.
    with suppress(OSError, ValueError):
        _previous_handlers[signal.SIGINT] = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _handle_sigint)
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        with suppress(OSError, ValueError):
            _previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, _handle_signal)
    _install_console_handler()
