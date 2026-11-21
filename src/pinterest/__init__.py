def setup(bot) -> None:
    # Imported here so view.pinterest can import src.pinterest.client without a cycle.
    from src.pinterest.commands import setup as register

    register(bot)
