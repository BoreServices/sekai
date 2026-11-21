"""Guild shops: coins buy roles and timed XP boosts, tracked per member.

Shop items are per guild. Role items are handed out the moment they are
bought; boost items sit in the member's inventory until they activate them.
"""

import time

from core import economy

PAGE_SIZE = 10
MAX_NAME = 32
MAX_PRICE = 1_000_000_000
MAX_QUANTITY = 25
MAX_MULTIPLIER = 10.0

KIND_ROLE = "role"
KIND_BOOST = "xp_boost"
KINDS = (KIND_ROLE, KIND_BOOST)
KIND_LABELS = {KIND_ROLE: "Role", KIND_BOOST: "XP boost"}

BUY_OK = "ok"
BUY_POOR = "poor"
BUY_OWNED = "owned"
BUY_LIMIT = "limit"

USE_OK = "ok"
USE_NONE = "none"
USE_ROLE = "role"


def clean_name(raw: str) -> str | None:
    """Item names may contain spaces but must stay short and single-line."""
    name = " ".join(raw.split())
    if not name or len(name) > MAX_NAME:
        return None
    return name


async def items(db, guild_id: int) -> list:
    return await db.fetchall(
        """
        SELECT * FROM shop_items
        WHERE guild_id = ?
        ORDER BY price ASC, name COLLATE NOCASE ASC
        """,
        (guild_id,))


async def find_item(db, guild_id: int, name: str):
    return await db.fetchone(
        """
        SELECT * FROM shop_items
        WHERE guild_id = ? AND name = ? COLLATE NOCASE
        """,
        (guild_id, name))


async def create_item(
    db,
    guild_id: int,
    *,
    name: str,
    kind: str,
    price: int,
    role_id: int | None = None,
    multiplier: float | None = None,
    duration: int | None = None) -> int:
    return await db.insert(
        """
        INSERT INTO shop_items
            (guild_id, name, kind, price, role_id, multiplier, duration)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, name, kind, price, role_id, multiplier, duration))


async def delete_item(db, guild_id: int, name: str) -> bool:
    row = await db.fetchone(
        "SELECT id FROM shop_items WHERE guild_id = ? AND name = ? COLLATE NOCASE",
        (guild_id, name))
    if row is None:
        return False
    # Members lose what they bought from this item; nothing else references it.
    await db.execute(
        "DELETE FROM inventory WHERE guild_id = ? AND item_id = ?",
        (guild_id, row["id"]))
    await db.execute(
        "DELETE FROM shop_items WHERE guild_id = ? AND id = ?",
        (guild_id, row["id"]))
    return True


async def _held(db, guild_id: int, user_id: int, item_id: int):
    return await db.fetchone(
        "SELECT quantity, expires_at FROM inventory "
        "WHERE guild_id = ? AND user_id = ? AND item_id = ?",
        (guild_id, user_id, item_id))


async def owned_rows(db, guild_id: int, user_id: int) -> list:
    """Everything the member still holds — unopened stock or a live boost."""
    return await db.fetchall(
        """
        SELECT s.id, s.name, s.kind, s.role_id, s.multiplier, s.duration,
               i.quantity, i.expires_at
        FROM inventory i
        JOIN shop_items s ON s.id = i.item_id
        WHERE i.guild_id = ? AND i.user_id = ?
          AND (i.quantity > 0 OR i.expires_at > ?)
        ORDER BY s.kind ASC, s.name COLLATE NOCASE ASC
        """,
        (guild_id, user_id, int(time.time())))


async def buy(db, guild_id: int, user_id: int, item) -> str:
    """Charge the member and hand over one item. Returns a BUY_* status."""
    row = await _held(db, guild_id, user_id, item["id"])
    if item["kind"] == KIND_ROLE:
        # One role per member — buying it twice would just waste coins.
        if row is not None and row["quantity"] > 0:
            return BUY_OWNED
    elif row is not None and row["quantity"] >= MAX_QUANTITY:
        return BUY_LIMIT

    if await economy.get_balance(db, guild_id, user_id) < item["price"]:
        return BUY_POOR
    await economy.add_balance(db, guild_id, user_id, -item["price"])
    await db.execute(
        """
        INSERT INTO inventory (guild_id, user_id, item_id, quantity)
        VALUES (?, ?, ?, 1)
        ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET
            quantity = inventory.quantity + 1
        """,
        (guild_id, user_id, item["id"]))
    return BUY_OK


async def activate(db, guild_id: int, user_id: int, item) -> tuple[str, int | None]:
    """Open one unit of an item. Returns (status, new boost expiry)."""
    if item["kind"] != KIND_BOOST:
        return USE_ROLE, None
    row = await _held(db, guild_id, user_id, item["id"])
    if row is None or row["quantity"] < 1:
        return USE_NONE, None

    now = int(time.time())
    # Activating while one is running extends it instead of replacing it.
    expires_at = max(now, row["expires_at"] or 0) + int(item["duration"] or 0)
    await db.execute(
        "UPDATE inventory SET quantity = quantity - 1, expires_at = ? "
        "WHERE guild_id = ? AND user_id = ? AND item_id = ?",
        (expires_at, guild_id, user_id, item["id"]))
    return USE_OK, expires_at


async def active_multiplier(db, guild_id: int, user_id: int) -> float:
    """Best XP multiplier the member currently has running, 1.0 when none."""
    row = await db.fetchone(
        """
        SELECT MAX(s.multiplier) AS multiplier
        FROM inventory i
        JOIN shop_items s ON s.id = i.item_id
        WHERE i.guild_id = ? AND i.user_id = ?
          AND s.kind = ? AND i.expires_at IS NOT NULL AND i.expires_at > ?
        """,
        (guild_id, user_id, KIND_BOOST, int(time.time())))
    if row is None or row["multiplier"] is None:
        return 1.0
    return float(row["multiplier"])
