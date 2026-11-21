import discord

from config.settings import settings
from core.emojis import iconize
from view.base import base_embed, brand, format_duration

QUEUE_PAGE = 10


def _track_line(track) -> str:
    title = discord.utils.escape_markdown(track.title)
    link = f"[{title}]({track.uri})" if track.uri else title
    duration = iconize("🔴 LIVE") if track.is_stream else format_duration(track.length)
    return f"{link}\n{track.author or 'Unknown'} · `{duration}`"


def _total_duration(tracks: list) -> str | None:
    total = sum(track.length for track in tracks if not track.is_stream)
    if total <= 0:
        return None
    return format_duration(total)


def queue_embed(player) -> discord.Embed:
    upcoming = list(player.queue)
    total = len(upcoming)
    shown = [
        f"**{index}.** {_track_line(track)}"
        for index, track in enumerate(upcoming[:QUEUE_PAGE], start=1)
    ]
    if total > QUEUE_PAGE:
        shown.append(f"*…and {total - QUEUE_PAGE} more*")

    embed = base_embed(
        title=f"Up next — {total} track{'s' if total != 1 else ''}",
        description="\n\n".join(shown) if shown else "*Nothing queued yet.*")
    current = player.current
    if current is not None:
        embed.add_field(
            name="▶️ Now playing",
            value=_track_line(current),
            inline=False)

    if current is not None and current.artwork:
        embed.set_thumbnail(url=current.artwork)
    elif upcoming and upcoming[0].artwork:
        embed.set_thumbnail(url=upcoming[0].artwork)

    duration = _total_duration(upcoming)
    footer = f"{total} queued"
    if duration:
        footer += f"  ·  {duration} total"
    footer += f"  ·  {settings.bot_name}"
    return brand(embed, footer=footer)
