import discord

from config.settings import settings
from view.base import base_embed, brand


def info_embed(
    *,
    title: str,
    fields: list[tuple[str, str, bool]],
    description: str | None = None,
    icon_url: str | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
    footer: str | None = None,
) -> discord.Embed:
    embed = base_embed(title=title, description=description)
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    elif icon_url:
        embed.set_thumbnail(url=icon_url)

    if image_url:
        embed.set_image(url=image_url)

    return brand(embed, footer=footer)


def avatar_decoration_embed(
    *, name: str, url: str, footer: str | None = None
) -> discord.Embed:
    embed = base_embed(title=f"✨ {name[:220]}'s decoration")
    embed.set_image(url=url)
    return brand(embed, footer=footer)
