import logging
import random
import time
from typing import Any

from config.owners import OWNER_IDS
from core import shop

log = logging.getLogger("sekai.levels")

MIN_XP = 15
MAX_XP = 25
COOLDOWN_SECONDS = 60
PAGE_SIZE = 10
OWNER_XP_MULTIPLIER = 3
_PRUNE_AT = 2000

# XP Boost system
DEFAULT_XP_BOOST = 1.0  # 1.0 = no boost, 1.5 = 50% more XP, etc.
MAX_XP_BOOST = 5.0  # Maximum boost multiplier

_cooldowns: dict[tuple[int, int], float] = {}
_xp_boost: dict[int, float] = {}  # guild_id -> boost multiplier


def xp_for_next_level(level: int) -> int:
    return 5 * level * level + 50 * level + 100


def xp_for_level(level: int) -> int:
    """Total XP needed to be at the start of a level."""
    level = max(level, 0)
    return level * (10 * level * level + 135 * level + 455) // 6


def level_progress(xp: int) -> tuple[int, int, int]:
    """Return (level, xp into the level, xp needed for the next one)."""
    xp = max(xp, 0)
    low, high = 0, 1
    while xp_for_level(high) <= xp:
        low, high = high, high * 2
    while low <= high:
        middle = (low + high) // 2
        if xp_for_level(middle) <= xp:
            low = middle + 1
        else:
            high = middle - 1
    level = high
    return level, xp - xp_for_level(level), xp_for_next_level(level)


def roll_xp() -> int:
    return random.randint(MIN_XP, MAX_XP)


def get_xp_boost(guild_id: int) -> float:
    """Current server-wide XP multiplier (1.0 means no boost)."""
    return _xp_boost.get(guild_id, DEFAULT_XP_BOOST)


def set_xp_boost(guild_id: int, multiplier: float) -> None:
    """Set the server-wide XP multiplier, clamped to the allowed range."""
    multiplier = max(DEFAULT_XP_BOOST, min(multiplier, MAX_XP_BOOST))
    if multiplier == DEFAULT_XP_BOOST:
        _xp_boost.pop(guild_id, None)
    else:
        _xp_boost[guild_id] = multiplier


def _prune(now: float) -> None:
    cutoff = now - COOLDOWN_SECONDS
    for key in [key for key, last in _cooldowns.items() if last < cutoff]:
        del _cooldowns[key]


async def add_message_xp(db, guild_id: int, user_id: int) -> int | None:
    """Award XP for a message, respecting the per-member cooldown.

    Returns the new level when the member just levelled up.
    """
    now = time.monotonic()
    key = (guild_id, user_id)
    last = _cooldowns.get(key)
    if last is not None and now - last < COOLDOWN_SECONDS:
        return None
    if len(_cooldowns) >= _PRUNE_AT:
        _prune(now)
    _cooldowns[key] = now

    row = await db.fetchone(
        "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    previous = row["xp"] if row is not None else 0
    gain = roll_xp() * (OWNER_XP_MULTIPLIER if user_id in OWNER_IDS else 1)
    boost = await shop.active_multiplier(db, guild_id, user_id)
    if boost > 1:
        gain = int(gain * boost)
    server_boost = get_xp_boost(guild_id)
    if server_boost != DEFAULT_XP_BOOST:
        gain = int(gain * server_boost)

    await db.execute(
        """
        INSERT INTO levels (guild_id, user_id, xp, messages)
        VALUES (?, ?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            xp = levels.xp + excluded.xp,
            messages = levels.messages + 1,
            updated_at = datetime('now')
        """,
        (guild_id, user_id, gain))

    before, _, _ = level_progress(previous)
    after, _, _ = level_progress(previous + gain)
    log.debug(
        "XP %s/%s %+d: level %d -> %d", guild_id, user_id, gain, before, after
    )
    return after if after > before else None


async def get_stats(db, guild_id: int, user_id: int) -> tuple[int, int]:
    row = await db.fetchone(
        "SELECT xp, messages FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    if row is None:
        return 0, 0
    return row["xp"], row["messages"]


async def add_xp(
    db, guild_id: int, user_id: int, amount: int
) -> tuple[int, int]:
    """Add XP directly. Returns the level before and after the change."""
    row = await db.fetchone(
        "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    previous = row["xp"] if row is not None else 0
    await db.execute(
        """
        INSERT INTO levels (guild_id, user_id, xp, messages)
        VALUES (?, ?, ?, 0)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            xp = levels.xp + excluded.xp,
            updated_at = datetime('now')
        """,
        (guild_id, user_id, amount))
    return level_progress(previous)[0], level_progress(previous + amount)[0]


async def set_xp(db, guild_id: int, user_id: int, xp: int) -> None:
    await db.execute(
        """
        INSERT INTO levels (guild_id, user_id, xp, messages)
        VALUES (?, ?, ?, 0)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            xp = excluded.xp,
            updated_at = datetime('now')
        """,
        (guild_id, user_id, max(xp, 0)))


async def remove_xp(
    db, guild_id: int, user_id: int, amount: int
) -> int | None:
    """Remove XP, never dropping below zero. None means the member had none."""
    row = await db.fetchone(
        "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    if row is None:
        return None
    new_xp = max(row["xp"] - amount, 0)
    await db.execute(
        "UPDATE levels SET xp = ?, updated_at = datetime('now') "
        "WHERE guild_id = ? AND user_id = ?",
        (new_xp, guild_id, user_id))
    return new_xp


async def reset_xp(db, guild_id: int, user_id: int) -> None:
    await db.execute(
        "DELETE FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))


async def set_level(db, guild_id: int, user_id: int, level: int) -> int:
    """Put a member at the start of a level. Returns the XP that implies."""
    xp = xp_for_level(level)
    await set_xp(db, guild_id, user_id, xp)
    return xp


async def add_levels(
    db, guild_id: int, user_id: int, count: int
) -> tuple[int, int]:
    """Add whole levels to a member. Returns the level before and after."""
    row = await db.fetchone(
        "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    current = row["xp"] if row is not None else 0
    before, _, _ = level_progress(current)
    after = before + count
    await set_xp(db, guild_id, user_id, xp_for_level(after))
    return before, after


async def list_rewards(db, guild_id: int) -> list[Any]:
    return await db.fetchall(
        "SELECT level, role_id FROM level_rewards "
        "WHERE guild_id = ? ORDER BY level ASC",
        (guild_id,))


async def rewards_up_to(db, guild_id: int, level: int) -> list[int]:
    """Role IDs that a member at this level should already have."""
    rows = await db.fetchall(
        "SELECT role_id FROM level_rewards "
        "WHERE guild_id = ? AND level <= ? ORDER BY level ASC",
        (guild_id, level))
    return [row["role_id"] for row in rows]


async def set_reward(db, guild_id: int, level: int, role_id: int) -> None:
    await db.execute(
        """
        INSERT INTO level_rewards (guild_id, level, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, level) DO UPDATE SET
            role_id = excluded.role_id
        """,
        (guild_id, level, role_id))


async def remove_reward(db, guild_id: int, level: int) -> bool:
    row = await db.fetchone(
        "SELECT role_id FROM level_rewards WHERE guild_id = ? AND level = ?",
        (guild_id, level))
    if row is None:
        return False
    await db.execute(
        "DELETE FROM level_rewards WHERE guild_id = ? AND level = ?",
        (guild_id, level))
    return True


async def get_rank(db, guild_id: int, xp: int) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS higher FROM levels WHERE guild_id = ? AND xp > ?",
        (guild_id, xp))
    return (row["higher"] if row is not None else 0) + 1


async def leaderboard(
    db, guild_id: int, page: int = 1
) -> tuple[list[Any], int]:
    total_row = await db.fetchone(
        "SELECT COUNT(*) AS total FROM levels WHERE guild_id = ?", (guild_id,)
    )
    total = total_row["total"] if total_row is not None else 0
    rows = await db.fetchall(
        """
        SELECT user_id, xp, messages FROM levels
        WHERE guild_id = ?
        ORDER BY xp DESC, updated_at ASC, user_id ASC
        LIMIT ? OFFSET ?
        """,
        (guild_id, PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE))
    return rows, total
