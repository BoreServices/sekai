import discord

from view.base import SOURCE_COLORS, SOURCE_LABELS, base_embed, brand


def playlist_embed(
    name: str,
    *,
    count: int,
    description: str,
    source: str | None = None,
    url: str | None = None,
    artwork_url: str | None = None) -> discord.Embed:
    key = (source or "").lower()
    embed = base_embed(
        title=f"📜 {name}",
        description=description,
        color=SOURCE_COLORS.get(key))
    embed.add_field(name="🎵 Tracks", value=f"{count:,}", inline=True)
    if key:
        embed.add_field(
            name="📡 Source", value=SOURCE_LABELS.get(key, key.title()), inline=True
        )
    if url:
        embed.add_field(name="🔗 Playlist", value=f"[Open]({url})", inline=True)
    if artwork_url:
        embed.set_thumbnail(url=artwork_url)
    return brand(embed)
