import discord

from core.emojis import iconize
from view.base import (
    base_embed,
    brand,
    format_duration,
    source_color,
    source_label)


def track_added_embed(track, position: int) -> discord.Embed:
    title = discord.utils.escape_markdown(track.title)
    description = f"**[{title}]({track.uri})**" if track.uri else f"**{title}**"
    embed = base_embed(
        description=description,
        color=source_color(getattr(track, "source", None)))
    embed.add_field(
        name="👤 Author", value=track.author or "Unknown", inline=True
    )
    embed.add_field(
        name="⏱️ Duration",
        value=iconize("🔴 LIVE") if track.is_stream else format_duration(track.length),
        inline=True)
    embed.add_field(name="📍 Position", value=f"#{position}", inline=True)
    embed.add_field(
        name="📡 Source",
        value=source_label(getattr(track, "source", None)),
        inline=True)
    extras = getattr(track, "extras", None)
    requester = getattr(extras, "requester", None) if extras is not None else None
    if requester is not None:
        embed.add_field(name="🙋 Requested by", value=f"<@{requester}>", inline=True)
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)
    return brand(embed)
