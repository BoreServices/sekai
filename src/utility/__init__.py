def setup(bot) -> None:
    from src.utility import afk, dice, reminders

    afk.setup(bot)
    reminders.setup(bot)
    dice.setup(bot)


__all__ = ["setup"]