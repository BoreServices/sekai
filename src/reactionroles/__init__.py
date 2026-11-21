def setup(bot) -> None:
    from src.reactionroles.commands import setup as register

    register(bot)


__all__ = ["setup"]
