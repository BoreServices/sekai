def setup(bot) -> None:
    from src.automod.commands import setup as register

    register(bot)


__all__ = ["setup"]
