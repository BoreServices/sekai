def setup(bot) -> None:
    from src.giveaways.commands import setup as register

    register(bot)


__all__ = ["setup"]
