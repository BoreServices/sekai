def setup(bot) -> None:
    from src.social.commands import setup as register

    register(bot)
