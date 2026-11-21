import logging
import time
from collections import deque
from dataclasses import dataclass

log = logging.getLogger("sekai.antinuke")

DEFAULT_THRESHOLD = 3
DEFAULT_WINDOW = 10
MIN_THRESHOLD = 2
MAX_THRESHOLD = 10
MIN_WINDOW = 5
MAX_WINDOW = 60
DEFAULT_PUNISH = "ban"
PUNISHMENTS = ("ban", "kick", "strip")

# A single mass ban writes one audit entry per victim, so only the first one
# should act. Everything from the same member is ignored for this long.
PUNISH_COOLDOWN = 60.0
# If the punishment could not be applied (role hierarchy, missing permission)
# retry sooner instead of leaving the account free for a whole minute.
RETRY_COOLDOWN = 10.0
MAX_TRACKED = 5000
# How many individual actions are remembered per account inside a window.
MAX_EVENTS = 256
# Bot-performed actions are credited to the member whose command caused them.
# Attribution is only valid for this long.
BOT_ATTRIBUTION_TTL = 20.0
# Antinuke history is kept in SQLite so it survives restarts. Older rows are
# trimmed per guild so the table cannot grow without bound.
MAX_LOG_ROWS = 1000

ACTION_TEXT = {
    "ban": "banned members",
    "kick": "kicked members",
    "member_prune": "pruned members",
    "channel_create": "created channels",
    "channel_delete": "deleted channels",
    "role_create": "created roles",
    "role_delete": "deleted roles",
    "webhook_create": "created webhooks",
    "bot_add": "added a bot",
    "emoji_delete": "deleted emojis",
    "sticker_delete": "deleted stickers",
    "guild_update": "changed server settings",
}


@dataclass
class Settings:
    enabled: bool = False
    threshold: int = DEFAULT_THRESHOLD
    window: int = DEFAULT_WINDOW
    punish: str = DEFAULT_PUNISH
    alert_channel: int | None = None
    log_channel: int | None = None


_settings: dict[int, Settings] = {}
_whitelist: dict[int, dict[int, str]] = {}
# (guild, actor) -> every watched action in the current window, in order. All
# action types share one counter: a nuke that deletes two channels then bans
# someone must still trip a threshold of three.
_events: dict[tuple[int, int], deque[tuple[float, str, int]]] = {}
# (guild, action) -> (timestamp, the member whose command made the bot do it)
_bot_actions: dict[tuple[int, str], tuple[float, int]] = {}
# (guild, actor) -> monotonic time until which they are considered handled.
_punished: dict[tuple[int, int], float] = {}
_loaded = False


async def load_state(bot) -> None:
    global _loaded
    settings: dict[int, Settings] = {}
    whitelist: dict[int, dict[int, str]] = {}
    for row in await bot.db.fetchall(
        "SELECT guild_id, enabled, threshold, window, punish, alert_channel, "
        "log_channel FROM antinuke_settings"
    ):
        settings[row["guild_id"]] = Settings(
            enabled=bool(row["enabled"]),
            threshold=row["threshold"],
            window=row["window"],
            punish=row["punish"],
            alert_channel=row["alert_channel"],
            log_channel=row["log_channel"])
    for row in await bot.db.fetchall(
        "SELECT guild_id, target_id, kind FROM antinuke_whitelist"
    ):
        whitelist.setdefault(row["guild_id"], {})[row["target_id"]] = row["kind"]

    # Only replace the cache once both queries succeeded, so a transient
    # database error cannot leave the guard looking disabled forever.
    _settings.clear()
    _settings.update(settings)
    _whitelist.clear()
    _whitelist.update(whitelist)
    _events.clear()
    _bot_actions.clear()
    _punished.clear()
    _loaded = True


def get(guild_id: int) -> Settings | None:
    return _settings.get(guild_id)


async def save(bot, guild_id: int, settings: Settings) -> None:
    _settings[guild_id] = settings
    await bot.db.execute(
        """
        INSERT INTO antinuke_settings (guild_id, enabled, threshold, window,
                                      punish, alert_channel, log_channel)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            enabled = excluded.enabled,
            threshold = excluded.threshold,
            window = excluded.window,
            punish = excluded.punish,
            alert_channel = excluded.alert_channel,
            log_channel = excluded.log_channel,
            updated_at = datetime('now')
        """,
        (
            guild_id,
            int(settings.enabled),
            settings.threshold,
            settings.window,
            settings.punish,
            settings.alert_channel,
            settings.log_channel))


def entries(guild_id: int) -> dict[int, str]:
    return dict(_whitelist.get(guild_id, {}))


def whitelisted(guild_id: int, user_id: int, role_ids: set[int]) -> bool:
    """True when the member itself, or one of their roles, is trusted."""
    trusted = _whitelist.get(guild_id)
    if not trusted:
        return False
    if user_id in trusted:
        return True
    return any(role_id in trusted for role_id in role_ids)


async def whitelist_add(
    bot, guild_id: int, target_id: int, kind: str, added_by: int
) -> None:
    _whitelist.setdefault(guild_id, {})[target_id] = kind
    await bot.db.execute(
        """
        INSERT INTO antinuke_whitelist (guild_id, target_id, kind, added_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (guild_id, target_id) DO UPDATE SET
            kind = excluded.kind,
            added_by = excluded.added_by,
            created_at = datetime('now')
        """,
        (guild_id, target_id, kind, added_by))


async def whitelist_remove(bot, guild_id: int, target_id: int) -> bool:
    removed = _whitelist.get(guild_id, {}).pop(target_id, None) is not None
    if removed:
        await bot.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND target_id = ?",
            (guild_id, target_id))
    return removed


def note(
    guild_id: int, actor_id: int, action: str, target_id: int, window: int
) -> list[tuple[str, int]]:
    """Record an action and return everything still inside the window."""
    if len(_events) > MAX_TRACKED:
        _events.clear()
    events = _events.setdefault((guild_id, actor_id), deque(maxlen=MAX_EVENTS))
    now = time.monotonic()
    while events and now - events[0][0] > window:
        events.popleft()
    events.append((now, action, target_id))
    return [(event_action, target) for _, event_action, target in events]


def record_bot_action(guild_id: int, action: str, user_id: int) -> None:
    """Remember that a member's command is making the bot do `action`.

    The audit log credits the bot, not the member, so the guard would otherwise
    let anyone with a moderation command wipe things without ever being caught.
    """
    if len(_bot_actions) > MAX_TRACKED:
        _bot_actions.clear()
    _bot_actions[(guild_id, action)] = (time.monotonic(), user_id)


def bot_actor(guild_id: int, action: str) -> int | None:
    """The member behind a recent bot action, if the attribution is still fresh."""
    record = _bot_actions.get((guild_id, action))
    if record is None:
        return None
    stamp, user_id = record
    if time.monotonic() - stamp > BOT_ATTRIBUTION_TTL:
        _bot_actions.pop((guild_id, action), None)
        return None
    return user_id


def forget(guild_id: int, actor_id: int) -> None:
    _events.pop((guild_id, actor_id), None)


def punished_recently(guild_id: int, actor_id: int) -> bool:
    return _punished.get((guild_id, actor_id), 0.0) > time.monotonic()


def mark_punished(
    guild_id: int, actor_id: int, seconds: float = PUNISH_COOLDOWN
) -> None:
    if len(_punished) > MAX_TRACKED:
        _punished.clear()
    _punished[(guild_id, actor_id)] = time.monotonic() + seconds


async def record_log(
    bot,
    guild_id: int,
    kind: str,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    detail: str | None = None,
    outcome: str | None = None) -> None:
    """Store one antinuke event so `antinuke history` works after a restart."""
    try:
        await bot.db.execute(
            """
            INSERT INTO antinuke_logs
                (guild_id, kind, actor_id, actor_name, detail, outcome)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, kind, actor_id, actor_name, detail, outcome))
        await bot.db.execute(
            """
            DELETE FROM antinuke_logs
            WHERE guild_id = ? AND id NOT IN (
                SELECT id FROM antinuke_logs
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (guild_id, guild_id, MAX_LOG_ROWS))
    except Exception:
        log.exception("Could not store an antinuke log for guild %s", guild_id)


async def recent_logs(bot, guild_id: int, limit: int = 10, offset: int = 0):
    try:
        return await bot.db.fetchall(
            """
            SELECT kind, actor_id, actor_name, detail, outcome, created_at
            FROM antinuke_logs
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, limit, offset))
    except Exception:
        log.exception("Could not read antinuke logs for guild %s", guild_id)
        return []


async def count_logs(bot, guild_id: int) -> int:
    try:
        row = await bot.db.fetchone(
            "SELECT COUNT(*) AS total FROM antinuke_logs WHERE guild_id = ?",
            (guild_id))
    except Exception:
        log.exception("Could not count antinuke logs for guild %s", guild_id)
        return 0
    return int(row["total"]) if row is not None else 0
