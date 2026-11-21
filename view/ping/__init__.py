import math

import discord
from discord.ext import commands

from core.emojis import iconize
from view.base import (
    ACCENT,
    ERROR_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)


def _uptime(bot: commands.Bot) -> str:
    start = getattr(bot, "start_time", None)
    if start is None:
        return "Unknown"
    total = int((discord.utils.utcnow() - start).total_seconds())
    days, rest = divmod(total, 86400)
    hours, minutes = divmod(rest // 60, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def ping_embed(bot: commands.Bot) -> discord.Embed:
    latency = round(bot.latency * 1000) if math.isfinite(bot.latency) else None

    if latency is None:
        quality, color = f"{iconize('⚫')} Unknown", ACCENT
    elif latency < 100:
        quality, color = f"{iconize('🟢')} Excellent", SUCCESS_COLOR
    elif latency < 200:
        quality, color = f"{iconize('🟡')} Good", WARNING_COLOR
    else:
        quality, color = f"{iconize('🔴')} Poor", ERROR_COLOR

    embed = base_embed(
        title="🏓 Pong!",
        description=f"### {latency if latency is not None else '—'} ms",
        color=color)
    embed.add_field(
        name="📶 Quality", value=quality, inline=True
    )
    embed.add_field(
        name="⏳ Uptime", value=_uptime(bot), inline=True
    )
    return brand(embed)
