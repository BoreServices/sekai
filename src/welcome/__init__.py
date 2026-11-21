def setup(bot) -> None:
    # Imported here so the cog's modules can import view.welcome without a cycle.
    from src.welcome.commands import setup as register

    register(bot)


__all__ = ["setup"]
