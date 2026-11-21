import discord

from config.settings import settings
from view.base import base_embed, brand


def level_rewards_embed(rows: list[tuple[int, str]]) -> discord.Embed:
    if rows:
        description = "\n".join(
            f"**Level {level}** · {role}" for level, role in rows
        )
    else:
        description = (
            "No rewards yet — add one with "
            f"`{settings.default_prefix}levelrewards add <level> <role>`."
        )

    embed = base_embed(title="Level Rewards", description=description)
    return brand(embed)
