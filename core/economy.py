import random
import time

DAILY_AMOUNT = 250
DAILY_COOLDOWN = 86400
WORK_MIN = 40
WORK_MAX = 120
WORK_COOLDOWN = 3600
PAGE_SIZE = 10
CURRENCY = "coins"


async def _row(db, guild_id: int, user_id: int):
    return await db.fetchone(
        "SELECT balance, last_daily, last_work FROM economy "
        "WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))


async def get_balance(db, guild_id: int, user_id: int) -> int:
    row = await _row(db, guild_id, user_id)
    return row["balance"] if row is not None else 0


async def add_balance(db, guild_id: int, user_id: int, amount: int) -> int:
    """Add coins (may be negative, never below zero). Returns the new balance."""
    current = await get_balance(db, guild_id, user_id)
    new_balance = max(current + amount, 0)
    await db.execute(
        """
        INSERT INTO economy (guild_id, user_id, balance)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            balance = excluded.balance,
            updated_at = datetime('now')
        """,
        (guild_id, user_id, new_balance))
    return new_balance


def _remaining(last: int, cooldown: int, now: int) -> int:
    return max(last + cooldown - now, 0)


async def claim_daily(db, guild_id: int, user_id: int) -> tuple[int, int]:
    """Returns (coins gained, seconds left on cooldown). Gains are 0 on cooldown."""
    now = int(time.time())
    row = await _row(db, guild_id, user_id)
    last = row["last_daily"] if row is not None else 0
    wait = _remaining(last, DAILY_COOLDOWN, now)
    if wait > 0:
        return 0, wait
    await add_balance(db, guild_id, user_id, DAILY_AMOUNT)
    await db.execute(
        "UPDATE economy SET last_daily = ? WHERE guild_id = ? AND user_id = ?",
        (now, guild_id, user_id))
    return DAILY_AMOUNT, 0


async def work(db, guild_id: int, user_id: int) -> tuple[int, int]:
    """Returns (coins earned, seconds left on cooldown). Earnings are 0 on cooldown."""
    now = int(time.time())
    row = await _row(db, guild_id, user_id)
    last = row["last_work"] if row is not None else 0
    wait = _remaining(last, WORK_COOLDOWN, now)
    if wait > 0:
        return 0, wait
    earned = random.randint(WORK_MIN, WORK_MAX)
    await add_balance(db, guild_id, user_id, earned)
    await db.execute(
        "UPDATE economy SET last_work = ? WHERE guild_id = ? AND user_id = ?",
        (now, guild_id, user_id))
    return earned, 0


async def pay(db, guild_id: int, sender_id: int, receiver_id: int, amount: int) -> bool:
    """Move coins between members. False when the sender can't afford it."""
    if amount <= 0 or sender_id == receiver_id:
        return False
    if await get_balance(db, guild_id, sender_id) < amount:
        return False
    await add_balance(db, guild_id, sender_id, -amount)
    await add_balance(db, guild_id, receiver_id, amount)
    return True


async def gamble(db, guild_id: int, user_id: int, bet: int) -> tuple[bool | None, int]:
    """Bet coins on a coin flip. Returns (won, new balance); won is None if the bet isn't affordable."""
    current = await get_balance(db, guild_id, user_id)
    if bet <= 0 or current < bet:
        return None, current
    won = random.random() < 0.5
    new_balance = await add_balance(db, guild_id, user_id, bet if won else -bet)
    return won, new_balance


SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
SLOT_WEIGHTS = [30, 25, 20, 15, 10]


async def slots(db, guild_id: int, user_id: int, bet: int) -> tuple[list[str], int | None, int]:
    """Spin three reels. Returns (symbols, net change, new balance); net is None if unaffordable."""
    current = await get_balance(db, guild_id, user_id)
    if bet <= 0 or current < bet:
        return [], None, current
    reels = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    if reels[0] == reels[1] == reels[2]:
        net = bet * 5
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        net = bet
    else:
        net = -bet
    new_balance = await add_balance(db, guild_id, user_id, net)
    return reels, net, new_balance


async def leaderboard(db, guild_id: int, page: int = 1) -> tuple[list, int]:
    total_row = await db.fetchone(
        "SELECT COUNT(*) AS total FROM economy WHERE guild_id = ? AND balance > 0",
        (guild_id,))
    total = total_row["total"] if total_row is not None else 0
    rows = await db.fetchall(
        """
        SELECT user_id, balance FROM economy
        WHERE guild_id = ? AND balance > 0
        ORDER BY balance DESC, user_id ASC
        LIMIT ? OFFSET ?
        """,
        (guild_id, PAGE_SIZE, (max(page, 1) - 1) * PAGE_SIZE))
    return rows, total
