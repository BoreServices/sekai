import discord

from core.emojis import iconize
from view.base import base_embed, brand, format_duration


def _line(index: int, track) -> str:
    title = discord.utils.escape_markdown(track.title)
    if track.uri:
        title = f"[{title}]({track.uri})"
    author = discord.utils.escape_markdown(track.author or "Unknown")
    duration = iconize("🔴 LIVE") if track.is_stream else format_duration(track.length)
    return f"**{index}.** {title}\n{author} · `{duration}`"


def search_embed(
    query: str,
    tracks: list,
    *,
    prefix: str = "p!",
    playlist_name: str | None = None,
    total: int | None = None) -> discord.Embed:
    description = "\n\n".join(
        _line(index, track) for index, track in enumerate(tracks, start=1)
    )
    if total is not None and total > len(tracks):
        description += (
            f"\n\n*Showing the first **{len(tracks)}** of **{total}** results.*"
        )
    embed = base_embed(
        title=f"🔎 Results for “{discord.utils.escape_markdown(query)}”",
        description=description)
    if playlist_name:
        embed.add_field(name="📜 Playlist", value=playlist_name, inline=False)
    artwork = next((track.artwork for track in tracks if track.artwork), None)
    if artwork:
        embed.set_thumbnail(url=artwork)
    return brand(
        embed,
        footer=(
            f"Pick one with {prefix}play <number> or {prefix}forceplay <number>"
            "  ·  numbers reset on your next search"
        ))
