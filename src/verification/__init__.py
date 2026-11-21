def setup(bot) -> None:
    # Imported here so view.verify can import state without a cycle.
    from src.verification.commands import setup as register

    register(bot)


__all__ = ["setup"]
