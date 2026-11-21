import discord

from core.emojis import iconize
from view.base import SUCCESS_COLOR, base_embed, brand


def success_embed(description: str, icon: str = "✅") -> discord.Embed:
    text = (
        description
        if icon in {"✅", "☑️", "✔️"}
        else f"{iconize(icon)} {description}"
    )
    embed = base_embed(description=text, color=SUCCESS_COLOR)
    return brand(embed)
