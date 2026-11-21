def setup(bot) -> None:
    from src.antinuke.commands import setup as register

    register(bot)


__all__ = ["setup"]
