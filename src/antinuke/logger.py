"""Dedicated antinuke logging.

Every guard event is written to SQLite (`antinuke_logs`) and posted to one
channel. The channel is resolved in this order:

1. `antinuke logs <#channel>` in the server,
2. the `#logs-antinuke` channel created by `p!logs`,
3. the `moderation` log channel.

`antinuke logs off` stores channel id `0`, which stops regular antinuke posts
while keeping the SQLite history. Critical alerts (`alert=True`) are mirrored
to the moderation log and the extra `antinuke alert` channel regardless, so a
misconfigured log channel cannot hide a nuke.
"""

import logging

import discord

from core.guild_logs import log_channel
from src.antinuke import state
from view import antinuke_log_embed

log = logging.getLogger("sekai.antinuke")

# `Settings.log_channel` uses 0 for "do not post antinuke events".
LOG_OFF = 0


def _text_channel(guild, channel_id) -> discord.TextChannel | None:
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def _destination(bot, guild, settings) -> discord.TextChannel | None:
    if settings.log_channel == LOG_OFF:
        return None
    channel = _text_channel(guild, settings.log_channel)
    if channel is not None:
        return channel
    channel = await log_channel(bot, guild, "antinuke")
    if channel is not None:
        return channel
    return await log_channel(bot, guild, "moderation")


async def _send(channel, embed: discord.Embed) -> None:
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        log.warning(
            "Cannot post an antinuke log in #%s (%s)",
            getattr(channel, "name", "?"),
            getattr(channel, "id", "?"))
    except discord.HTTPException:
        log.warning("Failed to post an antinuke log", exc_info=True)


async def emit(
    bot,
    guild: discord.Guild,
    settings: state.Settings,
    kind: str,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    detail: str | None = None,
    outcome: str | None = None,
    embed: discord.Embed | None = None,
    alert: bool = False) -> None:
    """Record an antinuke event and post it to the log channel."""
    await state.record_log(
        bot,
        guild.id,
        kind,
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
        outcome=outcome)

    if embed is None:
        embed = antinuke_log_embed(
            kind,
            guild=guild,
            actor_id=actor_id,
            actor_name=actor_name,
            detail=detail,
            outcome=outcome)

    try:
        channel = await _destination(bot, guild, settings)
    except Exception:
        log.exception("Could not resolve the antinuke log channel in %s", guild.id)
        channel = None

    await _send(channel, embed)

    if not alert:
        return

    seen = {getattr(channel, "id", None)}
    mirrored = await log_channel(bot, guild, "moderation")
    if mirrored is not None and mirrored.id not in seen:
        seen.add(mirrored.id)
        await _send(mirrored, embed)

    extra = _text_channel(guild, settings.alert_channel)
    if extra is not None and extra.id not in seen:
        await _send(extra, embed)
