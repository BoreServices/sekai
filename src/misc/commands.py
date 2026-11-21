from src.misc import ai, logs, prefix, consent
from src.misc import help as help_menu


def setup(bot) -> None:
    prefix.setup(bot)
    logs.setup(bot)
    ai.setup(bot)
    help_menu.setup(bot)
    consent.setup(bot)
