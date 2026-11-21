"""Embeds for the fun cog."""

import discord

from view.base import (
    ACCENT,
    ERROR_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand,
)

BAR_FULL = "▰"
BAR_EMPTY = "▱"
BAR_SLOTS = 10
DIH_SLOTS = 20


def meter_bar(percent: int, slots: int = BAR_SLOTS) -> str:
    filled = max(0, min(slots, round(percent / 100 * slots)))
    return BAR_FULL * filled + BAR_EMPTY * (slots - filled)


def _heat(percent: int) -> int:
    if percent < 25:
        return ERROR_COLOR
    if percent < 50:
        return WARNING_COLOR
    if percent < 75:
        return SUCCESS_COLOR
    return ACCENT


def _with_author(embed: discord.Embed, user: discord.abc.User) -> discord.Embed:
    return embed


def fun_meter_embed(
    *,
    user: discord.abc.User,
    label: str,
    icon: str,
    percent: int,
) -> discord.Embed:
    embed = base_embed(
        title=f"{icon} {label}",
        description=f"{user.mention} scored **{percent}%**\n`{meter_bar(percent)}`",
        color=_heat(percent),
    )
    return brand(_with_author(embed, user))


def dih_embed(
    *,
    user: discord.abc.User,
    size: int,
    maximum: int,
    verdict: str,
) -> discord.Embed:
    percent = round(size / maximum * 100)
    lines = [
        f"{user.mention} measures **{size} in**",
        f"`{meter_bar(percent, DIH_SLOTS)}`",
        verdict,
    ]
    embed = base_embed(
        title="📏 The dih meter",
        description="\n".join(lines),
        color=_heat(percent),
    )
    return brand(_with_author(embed, user))


__all__ = ["dih_embed", "fun_meter_embed", "meter_bar"]
