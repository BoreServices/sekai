"""Per-guild, per-game win/loss tracking for the games cog.

Every game reports into the `game_stats` table so `gamestats` and `gamelb`
can show records. Winning a solo game also pays coins through the economy.
"""

from core import economy

PAGE_SIZE = 10

TRIVIA_REWARD = 40
HANGMAN_REWARD = 60
NUMGUESS_REWARD = 30
RPS_REWARD = 15
TICTACTOE_REWARD = 25
CONNECT4_REWARD = 50


async def _ensure(db, guild_id: int, user_id: int, game: str) -> None:
    await db.execute(
        """
        INSERT INTO game_stats (guild_id, user_id, game)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, user_id, game) DO NOTHING
        """,
        (guild_id, user_id, game))


async def record(db, guild_id: int, user_id: int, game: str, *, won: bool) -> None:
    """Bump the win or loss counters (and the streak) for one game."""
    await _ensure(db, guild_id, user_id, game)
    if won:
        await db.execute(
            """
            UPDATE game_stats
            SET wins   = wins + 1,
                played = played + 1,
                streak = CASE WHEN streak > 0 THEN streak + 1 ELSE 1 END,
                best   = MAX(
                    best, CASE WHEN streak > 0 THEN streak + 1 ELSE 1 END
                ),
                updated_at = datetime('now')
            WHERE guild_id = ? AND user_id = ? AND game = ?
            """,
            (guild_id, user_id, game))
    else:
        await db.execute(
            """
            UPDATE game_stats
            SET losses = losses + 1,
                played = played + 1,
                streak = CASE WHEN streak < 0 THEN streak - 1 ELSE -1 END,
                updated_at = datetime('now')
            WHERE guild_id = ? AND user_id = ? AND game = ?
            """,
            (guild_id, user_id, game))


async def award(
    db,
    guild_id: int,
    user_id: int,
    game: str,
    amount: int,
    *,
    won: bool) -> int:
    """Record the result and pay the winner. Returns the coins paid."""
    await record(db, guild_id, user_id, game, won=won)
    if won and amount:
        await economy.add_balance(db, guild_id, user_id, amount)
        return amount
    return 0


async def get(db, guild_id: int, user_id: int, game: str):
    return await db.fetchone(
        "SELECT wins, losses, played, streak, best FROM game_stats "
        "WHERE guild_id = ? AND user_id = ? AND game = ?",
        (guild_id, user_id, game))


async def all_for(db, guild_id: int, user_id: int) -> list:
    return await db.fetchall(
        """
        SELECT game, wins, losses, played, streak, best
        FROM game_stats
        WHERE guild_id = ? AND user_id = ?
        ORDER BY played DESC, game ASC
        """,
        (guild_id, user_id))


async def leaderboard(db, guild_id: int, page: int = 1, page_size: int = PAGE_SIZE):
    total_row = await db.fetchone(
        "SELECT COUNT(*) AS total FROM ("
        "  SELECT user_id FROM game_stats WHERE guild_id = ? GROUP BY user_id"
        ")",
        (guild_id,))
    total = total_row["total"] if total_row is not None else 0
    rows = await db.fetchall(
        """
        SELECT user_id,
               SUM(wins)   AS wins,
               SUM(losses) AS losses,
               SUM(played) AS played
        FROM game_stats
        WHERE guild_id = ?
        GROUP BY user_id
        ORDER BY wins DESC, played ASC, user_id ASC
        LIMIT ? OFFSET ?
        """,
        (guild_id, page_size, (max(page, 1) - 1) * page_size))
    return rows, total
