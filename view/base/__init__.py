import discord

from config.settings import settings

ACCENT = settings.embed_color
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
WARNING_COLOR = 0xFEE75C
INFO_COLOR = 0x5865F2
GOLD_COLOR = 0xF1C40F

SOURCE_LABELS = {
    "spotify": "Spotify",
    "ytmusic": "YouTube Music",
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "applemusic": "Apple Music",
    "deezer": "Deezer",
    "tidal": "Tidal",
    "bandcamp": "Bandcamp",
}
SOURCE_COLORS = {
    "spotify": 0x1DB954,
    "ytmusic": 0xFF0000,
    "youtube": 0xFF0000,
    "soundcloud": 0xFF5500,
}


def format_duration(milliseconds: int) -> str:
    seconds = int(milliseconds / 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class IconEmbed(discord.Embed):
    """Standard embed base for the bot."""


def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: discord.Color | int | None = None) -> discord.Embed:
    body = description or ""
    if title:
        body = f"**{title}**" if not body else f"**{title}**\n\n{body}"
    return IconEmbed(
        title=None,
        description=body or None,
        color=color if color is not None else settings.embed_color)


def source_label(source: str | None) -> str:
    if not source:
        return "Unknown"
    return SOURCE_LABELS.get(source.lower(), source.title())


def source_color(source: str | None, fallback: int | None = None) -> int:
    return SOURCE_COLORS.get(
        (source or "").lower(), fallback if fallback is not None else ACCENT
    )


def brand(
    embed: discord.Embed,
    *,
    footer: str | None = None,
    timestamp: bool = True,
    icon: str | None = None) -> discord.Embed:
    # No embed footer/title/author by design; formatting is used instead.
    return embed
