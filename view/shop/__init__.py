import discord

from core.shop import KIND_BOOST, KIND_LABELS, PAGE_SIZE
from view.base import GOLD_COLOR, base_embed, brand

UNITS = (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1))


def describe_duration(seconds: int) -> str:
    """'2h 30m', '45s' — the longest two units are enough detail here."""
    seconds = max(int(seconds), 0)
    parts = []
    for unit, size in UNITS:
        if seconds >= size and len(parts) < 2:
            count, seconds = divmod(seconds, size)
            parts.append(f"{count}{unit}")
    return " ".join(parts) or "0s"


def item_detail(row) -> str:
    """The one-line summary shown under an item's name."""
    if row["kind"] == KIND_BOOST:
        return (
            f"**{row['multiplier']:g}x XP** for {describe_duration(row['duration'])}"
        )
    return "A role added to your profile"


def _item_value(row, currency: str) -> str:
    return f"{item_detail(row)}\n`{row['price']:,} {currency}`"


def shop_embed(
    *,
    guild_name: str,
    entries: list,
    page: int,
    pages: int,
    total: int,
    currency: str = "coins",
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(
        title=f"🛒 {guild_name} shop",
        description=(
            f"**{total}** item{'s' if total != 1 else ''} for sale. "
            "Buy one with `buy <name>` and check `inventory` afterwards."
        ),
        color=GOLD_COLOR)
    if not entries:
        embed.add_field(
            name="Nothing for sale yet",
            value="Server managers can add items with `shop role` or `shop boost`.",
            inline=False)
    else:
        start = (page - 1) * PAGE_SIZE
        for offset, row in enumerate(entries):
            name = discord.utils.escape_markdown(row["name"])
            embed.add_field(
                name=f"{start + offset + 1}. {name}",
                value=_item_value(row, currency),
                inline=False)
    if pages > 1:
        footer = f"Page {page}/{pages}"
    return brand(embed, footer=footer)


def inventory_embed(
    *,
    display_name: str,
    entries: list,
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(title=f"🎒 {display_name}'s inventory", color=GOLD_COLOR)
    if not entries:
        embed.description = "Nothing here yet — head to `shop` and spend some coins."
        return brand(embed, footer=footer)

    now = int(discord.utils.utcnow().timestamp())
    for row in entries:
        lines = []
        if row["quantity"] > 0:
            lines.append(f"**{row['quantity']}** ready to use")
        if row["expires_at"] and row["expires_at"] > now:
            if row["kind"] == KIND_BOOST:
                lines.append(
                    f"Active — **{row['multiplier']:g}x XP** until "
                    f"<t:{row['expires_at']}:R>"
                )
            else:
                lines.append(f"Active until <t:{row['expires_at']}:R>")
        elif row["kind"] == KIND_BOOST:
            lines.append("Use it with `use <name>` to start the boost")

        embed.add_field(
            name=(
                f"{KIND_LABELS.get(row['kind'], row['kind'])} · "
                f"{discord.utils.escape_markdown(row['name'])}"
            ),
            value="\n".join(lines) or "Owned",
            inline=False)
    return brand(embed, footer=footer)


__all__ = ["describe_duration", "inventory_embed", "item_detail", "shop_embed"]
