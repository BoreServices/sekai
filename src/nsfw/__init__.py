def setup(bot) -> None:
    from src.nsfw.commands import setup as register

    register(bot)
