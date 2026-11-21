def setup(bot) -> None:
    from src.honeypot.commands import setup as register

    register(bot)


__all__ = ["setup"]