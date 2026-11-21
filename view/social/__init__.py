import discord

from view.base import base_embed, brand

SOURCE = "purrbot.site"


def social_embed(
    *,
    title: str,
    description: str | None = None,
    fields: list[tuple[str, str, bool]] = (),
    image_url: str | None = None,
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(title=title, description=description)
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    if image_url:
        embed.set_image(url=image_url)

    return brand(embed, footer=footer or f"Powered by {SOURCE}")
