import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

RESET = "\x1b[0m"
DIM = "\x1b[2m"
LEVEL_COLORS = {
    logging.DEBUG: "\x1b[36m",
    logging.INFO: "\x1b[32m",
    logging.WARNING: "\x1b[33m",
    logging.ERROR: "\x1b[31m",
    logging.CRITICAL: "\x1b[1;31m",
}
NAME_COLOR = "\x1b[35m"
TIME_COLOR = "\x1b[90m"


def _enable_windows_vt() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


class ColorFormatter(logging.Formatter):
    def __init__(self, *, use_color: bool) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        time = self.formatTime(record, self.datefmt)
        level = record.levelname.ljust(7)
        name = record.name
        msg = record.message
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        if self.use_color:
            lc = LEVEL_COLORS.get(record.levelno, "")
            return (
                f"{TIME_COLOR}{time}{RESET} "
                f"{lc}{level}{RESET} "
                f"{NAME_COLOR}{name}{RESET} "
                f"{msg}"
            )
        return f"{time} {level} {name}: {msg}"


def setup_logging(debug: bool = False) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    _enable_windows_vt()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(ColorFormatter(use_color=getattr(console.stream, "isatty", lambda: False)()))

    file_handler = RotatingFileHandler(
        LOG_DIR / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.addHandler(console)
    root.addHandler(file_handler)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.INFO)
    logging.getLogger("aiohttp.access").setLevel(
        logging.DEBUG if debug else logging.WARNING
    )
    logging.getLogger("sekai.nodelink").setLevel(
        logging.DEBUG if debug else logging.INFO
    )
