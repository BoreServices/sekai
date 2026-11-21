import logging
import random
import time
from contextlib import suppress
from dataclasses import dataclass, field

import discord

from view.giveaway import giveaway_embed

log = logging.getLogger("sekai.giveaways")

CHANNEL_TYPES = (discord.TextChannel, discord.Thread)


@dataclass
class Giveaway:
    id: str
    message_id: int
    channel_id: int
    guild_id: int
    prize: str
    winners: int
    host_id: int
    ends_at: int
    ended: bool = False
    winner_ids: list[int] = field(default_factory=list)


_giveaways: dict[str, Giveaway] = {}
_loaded = False


def _parse_ids(value: str | None) -> list[int]:
    return [int(part) for part in (value or "").split(",") if part]


async def load_state(bot) -> None:
    global _loaded
    _loaded = True
    _giveaways.clear()
    for row in await bot.db.fetchall(
        "SELECT id, message_id, channel_id, guild_id, prize, winners, host_id, "
        "ends_at, winner_ids FROM giveaways WHERE ended = 0"
    ):
        _giveaways[row["id"]] = Giveaway(
            id=row["id"],
            message_id=row["message_id"],
            channel_id=row["channel_id"],
            guild_id=row["guild_id"],
            prize=row["prize"],
            winners=row["winners"],
            host_id=row["host_id"],
            ends_at=row["ends_at"],
            winner_ids=_parse_ids(row["winner_ids"]))


def by_message(message_id: int) -> Giveaway | None:
    for giveaway in _giveaways.values():
        if giveaway.message_id == message_id:
            return giveaway
    return None


def active_for_guild(guild_id: int) -> list[Giveaway]:
    return [
        giveaway
        for giveaway in _giveaways.values()
        if giveaway.guild_id == guild_id
    ]


async def create(
    bot,
    *,
    giveaway_id: str,
    message_id: int,
    channel_id: int,
    guild_id: int,
    prize: str,
    winners: int,
    host_id: int,
    ends_at: int) -> Giveaway:
    giveaway = Giveaway(
        id=giveaway_id,
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild_id,
        prize=prize,
        winners=winners,
        host_id=host_id,
        ends_at=ends_at)
    _giveaways[giveaway_id] = giveaway
    await bot.db.execute(
        "INSERT INTO giveaways (id, message_id, channel_id, guild_id, prize, "
        "winners, host_id, ends_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            giveaway_id,
            message_id,
            channel_id,
            guild_id,
            prize,
            winners,
            host_id,
            ends_at))
    return giveaway


async def toggle_entry(bot, giveaway_id: str, user_id: int) -> bool | None:
    """True when entered, False when left, None when the giveaway is over."""
    giveaway = _giveaways.get(giveaway_id)
    if giveaway is None or giveaway.ended:
        return None
    row = await bot.db.fetchone(
        "SELECT 1 FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
        (giveaway_id, user_id))
    if row is not None:
        await bot.db.execute(
            "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id))
        return False
    await bot.db.execute(
        "INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id) "
        "VALUES (?, ?)",
        (giveaway_id, user_id))
    return True


async def _channel(bot, channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is not None:
        return channel
    with suppress(discord.HTTPException):
        return await bot.fetch_channel(channel_id)
    return None


async def _edit_message(
    bot, giveaway: Giveaway, *, ended: bool = True
) -> None:
    channel = await _channel(bot, giveaway.channel_id)
    if not isinstance(channel, CHANNEL_TYPES):
        return
    host = bot.get_user(giveaway.host_id)
    kwargs = {
        "embed": giveaway_embed(
            prize=giveaway.prize,
            host=host,
            winners=giveaway.winners,
            ends_at=giveaway.ends_at,
            ended=ended,
            winner_ids=giveaway.winner_ids if ended else None)
    }
    if ended:
        kwargs["view"] = None
    with suppress(discord.HTTPException):
        await channel.get_partial_message(giveaway.message_id).edit(**kwargs)


async def lookup(bot, message_id: int):
    return await bot.db.fetchone(
        "SELECT id, guild_id, channel_id, prize, winners, ends_at, ended, "
        "winner_ids FROM giveaways WHERE message_id = ?",
        (message_id))


async def entrants(bot, giveaway_id: str) -> list[int]:
    rows = await bot.db.fetchall(
        "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ? "
        "ORDER BY entered_at",
        (giveaway_id))
    return [row["user_id"] for row in rows]


async def extend(bot, giveaway: Giveaway, seconds: int) -> int:
    giveaway.ends_at = max(giveaway.ends_at, int(time.time())) + seconds
    await bot.db.execute(
        "UPDATE giveaways SET ends_at = ? WHERE id = ?",
        (giveaway.ends_at, giveaway.id))
    await _edit_message(bot, giveaway, ended=False)
    return giveaway.ends_at


def _pick(entrants: list[int], count: int) -> list[int]:
    if not entrants:
        return []
    return random.sample(entrants, min(count, len(entrants)))


async def finish(bot, giveaway: Giveaway) -> list[int] | None:
    if giveaway.ended:
        return None
    giveaway.ended = True
    _giveaways.pop(giveaway.id, None)

    rows = await bot.db.fetchall(
        "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
        (giveaway.id,))
    entrants = [row["user_id"] for row in rows]
    winner_ids = _pick(entrants, giveaway.winners)
    giveaway.winner_ids = winner_ids
    await bot.db.execute(
        "UPDATE giveaways SET ended = 1, winner_ids = ? WHERE id = ?",
        (",".join(map(str, winner_ids)) or None, giveaway.id))
    await _edit_message(bot, giveaway)

    channel = await _channel(bot, giveaway.channel_id)
    if isinstance(channel, CHANNEL_TYPES):
        prize = discord.utils.escape_markdown(giveaway.prize)
        if winner_ids:
            mentions = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
            text = (
                f"🎉 Congratulations {mentions}! You won **{prize}** "
                f"in {channel.mention}."
            )
        else:
            text = f"No one entered **{prize}** — no winner this time."
        with suppress(discord.HTTPException):
            await channel.send(text)
    log.info("Giveaway %s ended with winners %s", giveaway.message_id, winner_ids)
    return winner_ids


async def reroll(
    bot, message_id: int, count: int, *, guild_id: int | None = None
) -> tuple[list[int], str] | None:
    row = await bot.db.fetchone(
        "SELECT id, channel_id, guild_id, prize, winners, host_id, ends_at, "
        "winner_ids FROM giveaways WHERE message_id = ?",
        (message_id))
    if row is None or (guild_id is not None and row["guild_id"] != guild_id):
        return None

    previous = _parse_ids(row["winner_ids"])
    rows = await bot.db.fetchall(
        "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
        (row["id"]))
    entrants = [entry["user_id"] for entry in rows]
    pool = [user_id for user_id in entrants if user_id not in previous]
    if len(pool) < count:
        pool = entrants
    winner_ids = _pick(pool, count)
    if not winner_ids:
        return [], row["prize"]

    combined = previous + winner_ids
    await bot.db.execute(
        "UPDATE giveaways SET winner_ids = ? WHERE id = ?",
        (",".join(map(str, combined)), row["id"]))

    giveaway = Giveaway(
        id=row["id"],
        message_id=message_id,
        channel_id=row["channel_id"],
        guild_id=row["guild_id"],
        prize=row["prize"],
        winners=row["winners"],
        host_id=row["host_id"],
        ends_at=row["ends_at"],
        ended=True,
        winner_ids=combined)
    await _edit_message(bot, giveaway)

    channel = await _channel(bot, row["channel_id"])
    if isinstance(channel, CHANNEL_TYPES):
        mentions = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
        prize = discord.utils.escape_markdown(row["prize"])
        with suppress(discord.HTTPException):
            await channel.send(
                f"🎉 Reroll: {mentions} won **{prize}** in {channel.mention}."
            )
    log.info("Giveaway %s rerolled winners %s", message_id, winner_ids)
    return winner_ids, row["prize"]
