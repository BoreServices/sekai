def setup(bot) -> None:
    # Imported here so view.roblox can import src.roblox.client without a cycle.
    from src.roblox.commands import setup as register

    register(bot)
