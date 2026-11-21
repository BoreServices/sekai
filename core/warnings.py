import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("sekai.warnings")

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_created(value: str) -> datetime:
    """SQLite stores UTC text; turn it back into an aware datetime."""
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


async def add_warning(
    db, guild_id: int, user_id: int, moderator_id: int, reason: str
) -> int:
    warning_id = await db.insert(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) "
        "VALUES (?, ?, ?, ?)",
        (guild_id, user_id, moderator_id, reason))
    log.debug(
        "Warning #%s for %s/%s by %s: %s",
        warning_id, guild_id, user_id, moderator_id, reason)
    return warning_id


async def list_warnings(db, guild_id: int, user_id: int) -> list[Any]:
    return await db.fetchall(
        "SELECT id, moderator_id, reason, created_at FROM warnings "
        "WHERE guild_id = ? AND user_id = ? ORDER BY id ASC",
        (guild_id, user_id))


async def delete_warning(db, guild_id: int, warning_id: int) -> Any | None:
    """Delete one warning. Returns the deleted row so callers can name the user."""
    row = await db.fetchone(
        "SELECT id, user_id, reason FROM warnings "
        "WHERE guild_id = ? AND id = ?",
        (guild_id, warning_id))
    if row is None:
        return None
    await db.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND id = ?",
        (guild_id, warning_id))
    return row


async def clear_warnings(db, guild_id: int, user_id: int) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS total FROM warnings "
        "WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    total = row["total"] if row is not None else 0
    if total:
        await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))
    return total
