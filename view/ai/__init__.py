import discord

from view.base import INFO_COLOR, base_embed, brand


def ai_embed(
    text: str, *, model: str, author: str, first: bool = True
) -> discord.Embed:
    embed = base_embed(
        description=text,
        color=INFO_COLOR)
    return brand(embed, footer=f"asked by {author}")
