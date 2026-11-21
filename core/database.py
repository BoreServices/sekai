import logging
from dataclasses import dataclass
from typing import Any, Iterable

import aiohttp

from config.d1 import d1_config

log = logging.getLogger("sekai.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id   INTEGER PRIMARY KEY,
    prefix     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS levels (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    xp         INTEGER NOT NULL DEFAULT 0,
    messages   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_levels_xp ON levels (guild_id, xp DESC);
CREATE TABLE IF NOT EXISTS level_rewards (
    guild_id INTEGER NOT NULL,
    level    INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);
CREATE TABLE IF NOT EXISTS economy (
    guild_id       INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    balance        INTEGER NOT NULL DEFAULT 0,
    last_daily     INTEGER NOT NULL DEFAULT 0,
    last_work      INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_economy_balance ON economy (guild_id, balance DESC);
CREATE TABLE IF NOT EXISTS warnings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings (guild_id, user_id);
CREATE TABLE IF NOT EXISTS tempvoice (
    guild_id        INTEGER PRIMARY KEY,
    category_id     INTEGER NOT NULL,
    trigger_id      INTEGER NOT NULL,
    menu_channel_id INTEGER,
    menu_message_id INTEGER,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tempvoice_channels (
    channel_id       INTEGER PRIMARY KEY,
    guild_id         INTEGER NOT NULL,
    owner_id         INTEGER NOT NULL,
    panel_message_id INTEGER,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tempvoice_channels_guild ON tempvoice_channels (guild_id);
CREATE TABLE IF NOT EXISTS ticket_config (
    guild_id         INTEGER PRIMARY KEY,
    category_id      INTEGER NOT NULL,
    staff_role_id    INTEGER NOT NULL,
    panel_channel_id INTEGER,
    panel_message_id INTEGER,
    log_channel_id   INTEGER,
    counter          INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id   INTEGER NOT NULL,
    number     INTEGER NOT NULL,
    opener_id  INTEGER NOT NULL,
    claimed_id INTEGER,
    topic      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets (guild_id, number);
CREATE TABLE IF NOT EXISTS ticket_transcripts (
    channel_id INTEGER PRIMARY KEY,
    guild_id   INTEGER NOT NULL,
    number     INTEGER NOT NULL,
    topic      TEXT NOT NULL,
    html       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ticket_transcripts_guild ON ticket_transcripts (guild_id, number);
CREATE TABLE IF NOT EXISTS log_guilds (
    guild_id    INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS log_channels (
    guild_id   INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, kind)
);
CREATE TABLE IF NOT EXISTS welcome_config (
    guild_id             INTEGER PRIMARY KEY,
    welcome_channel      INTEGER,
    welcome_message      TEXT,
    leave_channel        INTEGER,
    leave_message        TEXT,
    autorole_id          INTEGER,
    welcome_card_enabled INTEGER NOT NULL DEFAULT 1,
    leave_card_enabled   INTEGER NOT NULL DEFAULT 1,
    welcome_card_bg      TEXT,
    leave_card_bg        TEXT,
    welcome_card_color   TEXT,
    leave_card_color     TEXT,
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji      TEXT NOT NULL,
    role_id    INTEGER NOT NULL,
    PRIMARY KEY (message_id, emoji)
);
CREATE INDEX IF NOT EXISTS idx_reaction_roles_guild ON reaction_roles (guild_id);
CREATE TABLE IF NOT EXISTS giveaways (
    id         TEXT PRIMARY KEY,
    message_id INTEGER NOT NULL UNIQUE,
    channel_id INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL,
    prize      TEXT NOT NULL,
    winners    INTEGER NOT NULL DEFAULT 1,
    host_id    INTEGER NOT NULL,
    ends_at    INTEGER NOT NULL,
    ended      INTEGER NOT NULL DEFAULT 0,
    winner_ids TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_giveaways_active ON giveaways (ended, ends_at);
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    entered_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (giveaway_id, user_id)
);
CREATE TABLE IF NOT EXISTS afk (
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    reason   TEXT NOT NULL,
    since    INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    guild_id   INTEGER,
    channel_id INTEGER NOT NULL,
    message    TEXT NOT NULL,
    due_at     INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (due_at);
CREATE TABLE IF NOT EXISTS automod_settings (
    guild_id      INTEGER PRIMARY KEY,
    invites       INTEGER NOT NULL DEFAULT 0,
    links         INTEGER NOT NULL DEFAULT 0,
    mentions      INTEGER NOT NULL DEFAULT 0,
    mention_limit INTEGER NOT NULL DEFAULT 5,
    spam          INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS honeypot_settings (
    guild_id   INTEGER PRIMARY KEY,
    enabled    INTEGER NOT NULL DEFAULT 0,
    punish     TEXT NOT NULL DEFAULT 'ban',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS honeypot_channels (
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_honeypot_channels_guild ON honeypot_channels (guild_id);
CREATE TABLE IF NOT EXISTS verify_config (
    guild_id           INTEGER PRIMARY KEY,
    verified_role_id   INTEGER,
    unverified_role_id INTEGER,
    panel_channel_id   INTEGER,
    panel_message_id   INTEGER,
    min_account_days   INTEGER NOT NULL DEFAULT 0,
    raid_mode          INTEGER NOT NULL DEFAULT 0,
    raid_until         INTEGER NOT NULL DEFAULT 0,
    raid_threshold     INTEGER NOT NULL DEFAULT 10,
    raid_window        INTEGER NOT NULL DEFAULT 60,
    url_path           TEXT,
    expire_days        INTEGER NOT NULL DEFAULT 0,
    custom_domain      TEXT,
    verification_channel_id INTEGER,
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS verified_members (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    method      TEXT NOT NULL DEFAULT 'website',
    verified_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_verified_members_guild ON verified_members (guild_id);
CREATE TABLE IF NOT EXISTS game_stats (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    game       TEXT NOT NULL,
    wins       INTEGER NOT NULL DEFAULT 0,
    losses     INTEGER NOT NULL DEFAULT 0,
    played     INTEGER NOT NULL DEFAULT 0,
    streak     INTEGER NOT NULL DEFAULT 0,
    best       INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id, game)
);
CREATE INDEX IF NOT EXISTS idx_game_stats_guild ON game_stats (guild_id, wins DESC);
CREATE TABLE IF NOT EXISTS starboard_config (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    emoji      TEXT NOT NULL DEFAULT '⭐',
    threshold  INTEGER NOT NULL DEFAULT 3,
    self_star  INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS starboard_ignored (
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS starboard_messages (
    message_id   INTEGER PRIMARY KEY,
    guild_id     INTEGER NOT NULL,
    channel_id   INTEGER NOT NULL,
    starboard_id INTEGER NOT NULL,
    author_id    INTEGER NOT NULL,
    stars        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_starboard_messages_guild ON starboard_messages (guild_id);
CREATE TABLE IF NOT EXISTS tags (
    guild_id   INTEGER NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    author_id  INTEGER NOT NULL,
    uses       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, name)
);
CREATE TABLE IF NOT EXISTS shop_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    price       INTEGER NOT NULL,
    role_id     INTEGER,
    multiplier  REAL,
    duration    INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_shop_items_name ON shop_items (guild_id, name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS inventory (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 0,
    expires_at  INTEGER,
    acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory (guild_id, user_id);
CREATE TABLE IF NOT EXISTS antinuke_settings (
    guild_id      INTEGER PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 0,
    threshold     INTEGER NOT NULL DEFAULT 3,
    window        INTEGER NOT NULL DEFAULT 10,
    punish        TEXT NOT NULL DEFAULT 'ban',
    alert_channel INTEGER,
    log_channel   INTEGER,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS antinuke_whitelist (
    guild_id   INTEGER NOT NULL,
    target_id  INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    added_by   INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, target_id)
);
CREATE TABLE IF NOT EXISTS antinuke_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    actor_id   INTEGER,
    actor_name TEXT,
    detail     TEXT,
    outcome    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_antinuke_logs_guild ON antinuke_logs (guild_id, id);
CREATE TABLE IF NOT EXISTS user_consent (
    user_id    INTEGER PRIMARY KEY,
    agreed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    version    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dashboard_users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    email           TEXT,
    logins          INTEGER NOT NULL DEFAULT 1,
    first_login     TEXT NOT NULL DEFAULT (datetime('now')),
    last_login      TEXT NOT NULL DEFAULT (datetime('now')),
    last_ip         TEXT,
    last_user_agent TEXT
);
CREATE TABLE IF NOT EXISTS dashboard_logins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dashboard_logins_user
    ON dashboard_logins (user_id, id);
"""

# Columns added after the first dashboard release. D1 has no "IF NOT EXISTS"
# for ALTER TABLE, so each statement is attempted and duplicate-column errors
# are ignored in connect().
MIGRATIONS = [
    "ALTER TABLE dashboard_users ADD COLUMN last_ip TEXT",
    "ALTER TABLE dashboard_users ADD COLUMN last_user_agent TEXT",
]


@dataclass
class _ResultMeta:
    last_row_id: int | None = None


class D1Row(dict):
    __getattr__ = dict.get


class Database:
    def __init__(self, path: Any = None) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._last_meta = _ResultMeta()

    @property
    def conn(self) -> "Database":
        return self

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {d1_config.api_token}",
                "Content-Type": "application/json",
            }
        )
        # Create schema (split into statements for D1)
        for stmt in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
            await self._query(stmt + ";")
        for stmt in MIGRATIONS:
            try:
                await self._query(stmt + ";")
            except RuntimeError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
        log.info("Cloudflare D1 ready (db=%s)", d1_config.database_id)

    async def _query(self, sql: str, params: Iterable[Any] = ()) -> dict:
        if self._session is None:
            raise RuntimeError("Database.connect() must be awaited first.")
        payload = {"sql": sql, "params": list(params)}
        async with self._session.post(d1_config.query_url, json=payload) as resp:
            data = await resp.json(content_type=None)
        if not data.get("success", False):
            errors = data.get("errors") or data
            raise RuntimeError(f"D1 query failed: {errors}")
        result = (data.get("result") or [{}])[0]
        meta = result.get("meta") or {}
        self._last_meta = _ResultMeta(last_row_id=meta.get("last_row_id"))
        return result

    async def execute(self, sql: str, parameters: Iterable[Any] = ()) -> None:
        await self._query(sql, parameters)

    async def insert(self, sql: str, parameters: Iterable[Any] = ()) -> int:
        await self._query(sql, parameters)
        return self._last_meta.last_row_id or 0

    async def fetchone(
        self, sql: str, parameters: Iterable[Any] = ()
    ) -> D1Row | None:
        result = await self._query(sql, parameters)
        results = result.get("results") or []
        return D1Row(results[0]) if results else None

    async def fetchall(
        self, sql: str, parameters: Iterable[Any] = ()
    ) -> list[D1Row]:
        result = await self._query(sql, parameters)
        return [D1Row(r) for r in (result.get("results") or [])]

    async def executescript(self, sql: str) -> None:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            await self._query(stmt + ";")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
