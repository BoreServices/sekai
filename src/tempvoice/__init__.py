def setup(bot) -> None:
    # Imported here so view.tempvoice.menu can import src.tempvoice.state without a cycle.
    from src.tempvoice.commands import setup as register

    register(bot)


__all__ = ["setup"]
