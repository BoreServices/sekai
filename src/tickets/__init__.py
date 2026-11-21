def setup(bot) -> None:
    # Imported here so view.tickets.menu can import src.tickets.state without a cycle.
    from src.tickets.commands import setup as register

    register(bot)


__all__ = ["setup"]
