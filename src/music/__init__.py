from src.music.commands import setup as setup_commands
from src.music.nodelink import setup as setup_status


def setup(bot) -> None:
    setup_commands(bot)
    setup_status(bot)


__all__ = ["setup"]
