def setup(bot) -> None:
    # Imported here so view.minecraft can import src.minecraft.client without a cycle.
    from src.minecraft.commands import setup as register

    register(bot)
