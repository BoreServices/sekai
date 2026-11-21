import discord

from view.base import INFO_COLOR, base_embed, brand

PER_FIELD = 20


def _uses(count: int) -> str:
    return f"{count} use{'s' if count != 1 else ''}"


def tag_show_embed(
    *,
    name: str,
    content: str,
    author: str,
    uses: int,
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(
        title=f"🏷️ {discord.utils.escape_markdown(name)}",
        description=content,
        color=INFO_COLOR)
    return brand(embed, footer=footer or f"Added by {author}  ·  {_uses(uses)}")


def tag_list_embed(
    *,
    title: str,
    entries: list,
    total: int,
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(title=title, color=INFO_COLOR)
    if not entries:
        embed.description = (
            "No tags yet. Create one with `tag add <name> <text>`."
        )
        return brand(embed, footer=footer)

    embed.description = (
        f"**{total}** tag{'s' if total != 1 else ''} — "
        "open one with `tag <name>`."
    )
    for start in range(0, len(entries), PER_FIELD):
        chunk = entries[start : start + PER_FIELD]
        lines = [
            f"`{discord.utils.escape_markdown(row['name'])}` · {_uses(row['uses'])}"
            for row in chunk
        ]
        embed.add_field(
            name=f"Tags {start + 1}–{start + len(chunk)}",
            value="\n".join(lines),
            inline=False)
    return brand(embed, footer=footer)


__all__ = ["tag_list_embed", "tag_show_embed"]
