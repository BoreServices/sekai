import logging
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass

import discord

from config.settings import settings
from config.token import DISCORD_CLIENT_SECRET
from core.cache import SlidingWindowLimiter, TTLCache

log = logging.getLogger("sekai.verification")

CODE_TTL = 15 * 60
JOIN_CODE_TTL = 24 * 60 * 60
CONFIG_TTL = 60.0
VERIFIED_TTL = 300.0
EXPIRE_AFTER_DAYS = 30  # 0 = never expires, >0 = days until re-verification needed
RAID_DEFAULT_THRESHOLD = 10
RAID_DEFAULT_WINDOW = 60
RAID_LOCK_SECONDS = 10 * 60
MAX_ACCOUNT_DAYS = 365

_MISSING = object()

codes: TTLCache[str, "PendingVerification"] = TTLCache(
    maxsize=10_000, ttl=CODE_TTL
)
_configs: TTLCache[int, object] = TTLCache(maxsize=4_096, ttl=CONFIG_TTL)
_verified: TTLCache[tuple[int, int], bool] = TTLCache(
    maxsize=20_000, ttl=VERIFIED_TTL
)
_verified_expiry: TTLCache[tuple[int, int], float] = TTLCache(
    maxsize=20_000, ttl=86400
)
_join_times: TTLCache[int, deque[float]] = TTLCache(maxsize=4_096, ttl=300)
link_limiter = SlidingWindowLimiter(limit=3, window=30)
callback_limiter = SlidingWindowLimiter(limit=10, window=60)


@dataclass
class PendingVerification:
    guild_id: int
    user_id: int
    created_at: int
    source: str = "manual"


@dataclass
class VerifyConfig:
    guild_id: int
    verified_role_id: int | None = None
    unverified_role_id: int | None = None
    panel_channel_id: int | None = None
    panel_message_id: int | None = None
    verification_channel_id: int | None = None  # Channel for DM failures
    min_account_days: int = 0
    raid_mode: bool = False
    raid_until: int = 0
    raid_threshold: int = RAID_DEFAULT_THRESHOLD
    raid_window: int = RAID_DEFAULT_WINDOW
    url_path: str | None = None  # Custom path (e.g. "custom")
    custom_domain: str | None = None  # Custom domain (e.g. "verify.mydomain.com")
    expire_days: int = 0  # 0 = never expires, >0 = days until re-verification

    @property
    def enabled(self) -> bool:
        return self.verified_role_id is not None


def _verify_base() -> str:
    return (settings.verify_base_url or settings.website_url).strip().rstrip("/")


def website_configured(bot) -> bool:
    secret = (DISCORD_CLIENT_SECRET or "").strip()
    return (
        getattr(bot, "user", None) is not None
        and bool(_verify_base())
        and bool(secret)
        and not secret.startswith("YOUR_")
    )


URL_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
RESERVED_PATHS = {"verify", "auth", "static", "health", "captcha", "api"}


def clean_url_path(value: str) -> str | None:
    """Return a lowercase custom link path, or None if it's not allowed."""
    cleaned = value.strip().lower()
    if not URL_PATH_RE.match(cleaned) or cleaned in RESERVED_PATHS:
        return None
    return cleaned


def verify_url(code: str, url_path: str | None = None, custom_domain: str | None = None) -> str:
    base = _verify_base()
    if not base:
        return ""
    # Use custom domain if set, otherwise use base URL
    if custom_domain:
        return f"https://{custom_domain}/{code}"
    if url_path:
        return f"{base}/{url_path}/{code}"
    return f"{base}/verify/{code}"


async def get_config(bot, guild_id: int) -> VerifyConfig | None:
    cached = _configs.get(guild_id, _MISSING)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]
    row = await bot.db.fetchone(
        "SELECT guild_id, verified_role_id, unverified_role_id, "
        "panel_channel_id, panel_message_id, min_account_days, raid_mode, "
        "raid_until, raid_threshold, raid_window, url_path, expire_days, "
        "custom_domain, verification_channel_id "
        "FROM verify_config WHERE guild_id = ?",
        (guild_id,))
    config = None
    if row is not None:
        config = VerifyConfig(
            guild_id=row["guild_id"],
            verified_role_id=row["verified_role_id"],
            unverified_role_id=row["unverified_role_id"],
            panel_channel_id=row["panel_channel_id"],
            panel_message_id=row["panel_message_id"],
            min_account_days=row["min_account_days"],
            raid_mode=bool(row["raid_mode"]),
            raid_until=row["raid_until"],
            raid_threshold=row["raid_threshold"],
            raid_window=row["raid_window"],
            url_path=row["url_path"],
            expire_days=row["expire_days"] or 0,
            custom_domain=row["custom_domain"],
            verification_channel_id=row["verification_channel_id"])
    _configs.set(guild_id, config)
    return config


async def save_config(bot, config: VerifyConfig) -> None:
    await bot.db.execute(
        """
        INSERT INTO verify_config (
            guild_id, verified_role_id, unverified_role_id, panel_channel_id,
            panel_message_id, min_account_days, raid_mode, raid_until,
            raid_threshold, raid_window, url_path, expire_days, custom_domain,
            verification_channel_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            url_path = excluded.url_path,
            verified_role_id = excluded.verified_role_id,
            unverified_role_id = excluded.unverified_role_id,
            panel_channel_id = excluded.panel_channel_id,
            panel_message_id = excluded.panel_message_id,
            min_account_days = excluded.min_account_days,
            raid_mode = excluded.raid_mode,
            raid_until = excluded.raid_until,
            raid_threshold = excluded.raid_threshold,
            raid_window = excluded.raid_window,
            expire_days = excluded.expire_days,
            custom_domain = excluded.custom_domain,
            verification_channel_id = excluded.verification_channel_id,
            updated_at = datetime('now')
        """,
        (
            config.guild_id,
            config.verified_role_id,
            config.unverified_role_id,
            config.panel_channel_id,
            config.panel_message_id,
            config.min_account_days,
            int(config.raid_mode),
            config.raid_until,
            config.raid_threshold,
            config.raid_window,
            config.url_path,
            config.expire_days,
            config.custom_domain,
            config.verification_channel_id))
    _configs.set(config.guild_id, config)


async def delete_config(bot, guild_id: int) -> None:
    await bot.db.execute("DELETE FROM verify_config WHERE guild_id = ?", (guild_id,))
    _configs.delete(guild_id)


async def all_configs(bot) -> list[VerifyConfig]:
    rows = await bot.db.fetchall("SELECT guild_id FROM verify_config")
    configs = []
    for row in rows:
        config = await get_config(bot, row["guild_id"])
        if config is not None:
            configs.append(config)
    return configs


async def set_raid(
    bot, guild_id: int, enabled: bool, *, until: int = 0
) -> None:
    await bot.db.execute(
        "UPDATE verify_config SET raid_mode = ?, raid_until = ?, "
        "updated_at = datetime('now') WHERE guild_id = ?",
        (int(enabled), until if enabled else 0, guild_id))
    _configs.delete(guild_id)


def raid_locked(config: VerifyConfig, *, now: int | None = None) -> bool:
    if not config.raid_mode:
        return False
    if config.raid_until <= 0:
        return True
    return config.raid_until > (now if now is not None else int(time.time()))


async def extend_raid(bot, config: VerifyConfig) -> None:
    if not config.raid_mode or config.raid_until <= 0:
        return
    config.raid_until = int(time.time()) + RAID_LOCK_SECONDS
    await bot.db.execute(
        "UPDATE verify_config SET raid_until = ? WHERE guild_id = ?",
        (config.raid_until, config.guild_id))


def new_code(
    guild_id: int,
    user_id: int,
    *,
    ttl: int = CODE_TTL,
    source: str = "manual") -> str:
    code = secrets.token_urlsafe(24)
    while code in codes:
        code = secrets.token_urlsafe(24)
    codes.set(
        code,
        PendingVerification(
            guild_id=guild_id,
            user_id=user_id,
            created_at=int(time.time()),
            source=source),
        ttl=ttl)
    return code


def peek_code(code: str) -> PendingVerification | None:
    return codes.get(code)


def consume_code(code: str) -> PendingVerification | None:
    return codes.pop(code)


def record_join(guild_id: int, *, window: int) -> int:
    now = time.monotonic()
    times = _join_times.get(guild_id)
    if times is None:
        times = deque()
    cutoff = now - window
    while times and times[0] < cutoff:
        times.popleft()
    times.append(now)
    _join_times.set(guild_id, times, ttl=max(window * 2, 60))
    return len(times)


def role_problem(guild: discord.Guild, role: discord.Role) -> str | None:
    me = guild.me
    if role.is_default():
        return "You can't use @everyone for verification."
    if role.managed:
        return "That role belongs to an integration and can't be assigned."
    if me is None or not me.guild_permissions.manage_roles:
        return "I need the Manage Roles permission to assign that role."
    if role >= me.top_role:
        return "Move my role above that one first."
    return None


def account_age_days(user: discord.abc.User) -> float:
    return (discord.utils.utcnow() - user.created_at).total_seconds() / 86400


async def is_verified(bot, guild_id: int, user_id: int) -> bool:
    key = (guild_id, user_id)
    cached = _verified.get(key)
    if cached is not None:
        # Check if verification has expired
        expire_cache = _verified_expiry.get(key)
        if expire_cache is not None:
            now = int(time.time())
            if now - expire_cache > EXPIRE_AFTER_DAYS * 86400:
                # Expired, clear the cache and re-fetch from DB
                _verified.delete(key)
                _verified_expiry.delete(key)
                row = await bot.db.fetchone(
                    "SELECT 1 FROM verified_members WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id))
                result = row is not None
                if result:
                    _verified.set(key, True)
                    _verified_expiry.set(key, now)
                return result
        return cached
    row = await bot.db.fetchone(
        "SELECT 1 FROM verified_members WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    result = row is not None
    if result:
        _verified.set(key, True)
        _verified_expiry.set(key, int(time.time()))
    return result


async def verified_count(bot, guild_id: int) -> int:
    row = await bot.db.fetchone(
        "SELECT COUNT(*) AS total FROM verified_members WHERE guild_id = ?",
        (guild_id,))
    return int(row["total"]) if row is not None else 0


async def mark_verified(
    bot,
    guild: discord.Guild,
    member: discord.Member,
    *,
    method: str = "website") -> tuple[bool, str]:
    config = await get_config(bot, guild.id)
    if config is None or config.verified_role_id is None:
        return False, "Verification isn't configured in this server."
    role = guild.get_role(config.verified_role_id)
    if role is None:
        return False, (
            "The verified role no longer exists — ask staff to run "
            "`verify setup` again."
        )
    problem = role_problem(guild, role)
    if problem:
        return False, problem

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Verification")
    except discord.HTTPException as exc:
        log.warning("Could not verify %s in %s: %s", member.id, guild.id, exc)
        return False, "I couldn't update your roles — ask staff to check my role position."

    # Always strip the unverified role: member.roles can be stale (the web flow
    # reuses guild.get_member), so guarding on `unverified in member.roles`
    # silently skips the removal. remove_roles is a no-op if they lack the role.
    if config.unverified_role_id is not None:
        unverified = guild.get_role(config.unverified_role_id)
        if unverified is not None:
            try:
                await member.remove_roles(unverified, reason="Verified")
            except discord.HTTPException as exc:
                log.warning(
                    "Verified %s in %s but could not remove unverified role %s: %s",
                    member.id,
                    guild.id,
                    unverified.id,
                    exc)

    await bot.db.execute(
        """
        INSERT INTO verified_members (guild_id, user_id, method)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            method = excluded.method,
            verified_at = datetime('now')
        """,
        (guild.id, member.id, method))
    _verified.set((guild.id, member.id), True)
    _verified_expiry.set((guild.id, member.id), int(time.time()))
    log.info("Verified %s in %s via %s", member.id, guild.id, method)
    return True, "verified"
