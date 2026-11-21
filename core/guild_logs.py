import logging

import discord

from config import logs as cfg

log = logging.getLogger("sekai.logs")

# Log group -> config toggles that keep it enabled. Each group gets its own
# channel inside the Logs category.
GROUPS: dict[str, tuple[str, ...]] = {
    "members": ("LOG_MEMBERS", "LOG_PRESENCE"),
    "messages": ("LOG_MESSAGES", "LOG_PINS"),
    "channels": ("LOG_CHANNELS"),
    "roles": ("LOG_ROLES"),
    "server": (
        "LOG_SERVER",
        "LOG_INVITES",
        "LOG_EMOJIS",
        "LOG_STICKERS",
        "LOG_EVENTS",
        "LOG_STAGES"),
    "voice": ("LOG_VOICE"),
    "threads": ("LOG_THREADS"),
    "moderation": ("LOG_AUDIT", "LOG_SERVER", "LOG_AUTOMOD"),
    "antinuke": ("LOG_ANTINUKE"),
    "commands": ("LOG_COMMANDS"),
}

_channels: dict[tuple[int, str], int] = {}
_guilds: dict[int, int] = {}
_configured: set[int] = set()
_unconfigured: set[int] = set()
_warned: set[int] = set()
_audit_warned: set[int] = set()
_setting_up: set[int] = set()


def channel_name(kind: str) -> str:
    return f"{cfg.LOG_CHANNEL_PREFIX}-{kind}"


def _is_category(channel) -> bool:
    return isinstance(channel, discord.CategoryChannel) or (
        getattr(channel, "type", None) is discord.ChannelType.category
    )


def _is_text(channel) -> bool:
    return isinstance(channel, discord.TextChannel) or (
        getattr(channel, "type", None) is discord.ChannelType.text
    )


def enabled_kinds() -> list[str]:
    return [
        kind
        for kind, toggles in GROUPS.items()
        if any(getattr(cfg, toggle, False) for toggle in toggles)
    ]


def _find_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    target = cfg.LOG_CATEGORY_NAME.lower()
    return discord.utils.find(
        lambda category: category.name.lower() == target, guild.categories
    )


def _find_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel | None,
    name: str) -> discord.TextChannel | None:
    target = name.lower()
    fallback = None
    for channel in guild.text_channels:
        if channel.name.lower() != target:
            continue
        if category is not None and channel.category_id == category.id:
            return channel
        fallback = fallback or channel
    return fallback


def _overwrites(guild: discord.Guild) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    me = guild.me
    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True)
    return overwrites


async def _create_category(
    guild: discord.Guild) -> discord.CategoryChannel | None:
    try:
        return await guild.create_category(
            cfg.LOG_CATEGORY_NAME,
            overwrites=_overwrites(guild),
            reason="Sekai logging setup")
    except discord.Forbidden:
        # Without Manage Roles the category cannot be made private.
        try:
            return await guild.create_category(
                cfg.LOG_CATEGORY_NAME, reason="Sekai logging setup"
            )
        except discord.HTTPException:
            return None
    except discord.HTTPException:
        return None


async def _create_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel | None,
    name: str) -> discord.TextChannel:
    kwargs = {"category": category, "reason": "Sekai logging setup"}
    try:
        return await guild.create_text_channel(
            name, overwrites=_overwrites(guild), **kwargs
        )
    except discord.Forbidden:
        log.warning(
            "Missing Manage Roles in %s; #%s will not be private",
            guild.name,
            name)
        return await guild.create_text_channel(name, **kwargs)


async def _remember_category(
    bot, guild: discord.Guild, category: discord.CategoryChannel
) -> None:
    _guilds[guild.id] = category.id
    _configured.add(guild.id)
    _unconfigured.discard(guild.id)
    await bot.db.execute(
        """
        INSERT INTO log_guilds (guild_id, category_id) VALUES (?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            category_id = excluded.category_id,
            updated_at = datetime('now')
        """,
        (guild.id, category.id))


async def _remember_channel(
    bot, guild: discord.Guild, kind: str, channel: discord.TextChannel
) -> None:
    _channels[(guild.id, kind)] = channel.id
    _configured.add(guild.id)
    _unconfigured.discard(guild.id)
    _warned.discard(guild.id)
    await bot.db.execute(
        """
        INSERT INTO log_channels (guild_id, kind, channel_id) VALUES (?, ?, ?)
        ON CONFLICT (guild_id, kind) DO UPDATE SET
            channel_id = excluded.channel_id,
            updated_at = datetime('now')
        """,
        (guild.id, kind, channel.id))


async def _load(bot, guild: discord.Guild) -> None:
    if guild.id in _configured or guild.id in _unconfigured:
        return
    row = await bot.db.fetchone(
        "SELECT category_id FROM log_guilds WHERE guild_id = ?", (guild.id,)
    )
    rows = await bot.db.fetchall(
        "SELECT kind, channel_id FROM log_channels WHERE guild_id = ?",
        (guild.id,))
    # The category row can be missing even when logging is on (older setups
    # reused an existing Logs category). Channel rows alone are enough.
    if row is None and not rows:
        _unconfigured.add(guild.id)
        return
    if row is not None:
        _guilds[guild.id] = row["category_id"]
    for kind_row in rows:
        _channels[(guild.id, kind_row["kind"])] = kind_row["channel_id"]
    _configured.add(guild.id)


async def setup_logging(
    bot, guild: discord.Guild, kinds: list[str] | None = None
) -> dict[str, discord.TextChannel] | None:
    """Create/reuse the Logs category and one channel per enabled log group."""
    if not cfg.LOGGING_ENABLED:
        return None
    await _load(bot, guild)

    wanted = list(kinds) if kinds is not None else enabled_kinds()
    if not wanted:
        return None

    category = None
    stored = _guilds.get(guild.id)
    if stored is not None:
        found = guild.get_channel(stored)
        if _is_category(found):
            category = found
        else:
            _guilds.pop(guild.id, None)
    if category is None:
        category = _find_category(guild)
    if category is not None and _guilds.get(guild.id) != category.id:
        # Reusing an existing Logs category still has to be stored, or the
        # guild looks unconfigured after the next restart.
        await _remember_category(bot, guild, category)

    channels: dict[str, discord.TextChannel] = {}
    missing: list[str] = []
    for kind in wanted:
        existing = _find_channel(guild, category, channel_name(kind))
        if existing is not None:
            channels[kind] = existing
        else:
            missing.append(kind)

    me = guild.me
    if missing and (me is None or not me.guild_permissions.manage_channels):
        if guild.id not in _warned:
            _warned.add(guild.id)
            log.warning(
                "Cannot set up logging in %s: missing Manage Channels",
                guild.name)
        return channels or None

    _setting_up.add(guild.id)
    try:
        if category is None:
            category = await _create_category(guild)
            if category is not None:
                await _remember_category(bot, guild, category)
        for kind in missing:
            name = channel_name(kind)
            try:
                channel = await _create_channel(guild, category, name)
            except discord.HTTPException:
                log.warning(
                    "Could not create #%s in %s", name, guild.name, exc_info=True
                )
                continue
            channels[kind] = channel
            log.info("Created #%s in %s", name, guild.name)

        for kind, channel in channels.items():
            await _remember_channel(bot, guild, kind, channel)
    finally:
        _setting_up.discard(guild.id)

    if (
        cfg.LOG_AUDIT
        and me is not None
        and guild.id not in _audit_warned
        and not me.guild_permissions.view_audit_log
    ):
        _audit_warned.add(guild.id)
        log.warning(
            "Audit log entries will not arrive in %s: missing "
            "View Audit Log permission",
            guild.name)

    return channels or None


async def log_channel(
    bot, guild: discord.Guild, kind: str
) -> discord.TextChannel | None:
    """Return the channel for a log group, or None if it is not set up.

    A deleted channel is forgotten here but not recreated: only running
    `logs` builds missing channels, so an event never silently re-setups
    logging in a server.
    """
    if not cfg.LOGGING_ENABLED:
        return None
    await _load(bot, guild)
    if guild.id not in _configured:
        return None

    cached = _channels.get((guild.id, kind))
    if cached is None:
        return None
    channel = guild.get_channel(cached)
    if _is_text(channel):
        return channel
    _channels.pop((guild.id, kind), None)
    return None


async def is_log_channel(bot, channel) -> bool:
    guild = getattr(channel, "guild", None)
    if guild is None:
        return False
    if guild.id in _setting_up:
        return True
    await _load(bot, guild)
    if guild.id not in _configured:
        return False
    category_id = _guilds.get(guild.id)
    if category_id is not None and (
        getattr(channel, "id", None) == category_id
        or getattr(channel, "category_id", None) == category_id
    ):
        return True
    channel_id = getattr(channel, "id", None)
    return any(
        guild_id == guild.id and cached == channel_id
        for (guild_id, _), cached in _channels.items()
    )


async def send_log(
    bot, guild: discord.Guild, kind: str, embed: discord.Embed | None
) -> None:
    if embed is None or not cfg.LOGGING_ENABLED:
        return
    channel = await log_channel(bot, guild, kind)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        if guild.id not in _warned:
            _warned.add(guild.id)
            log.warning(
                "Missing permissions to post in #%s in %s",
                channel.name,
                guild.name)
    except discord.HTTPException:
        log.warning("Failed to post a log in %s", guild.name, exc_info=True)


async def disable_logging(bot, guild: discord.Guild) -> None:
    """Stop logging in a server. Existing channels are left in place."""
    await bot.db.execute(
        "DELETE FROM log_channels WHERE guild_id = ?", (guild.id,)
    )
    await bot.db.execute("DELETE FROM log_guilds WHERE guild_id = ?", (guild.id,))
    for key in [key for key in _channels if key[0] == guild.id]:
        _channels.pop(key, None)
    _guilds.pop(guild.id, None)
    _configured.discard(guild.id)
    _unconfigured.add(guild.id)

