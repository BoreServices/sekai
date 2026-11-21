"""Dashboard module registry.

Each module exposes a ``read`` coroutine (returns form/list sections for the
server page) and an ``apply`` coroutine (handles a form save, a list add, or a
list delete). The dashboard server page renders these generically, so adding a
module here is enough to surface it in the UI.

Field types: ``bool``, ``text``, ``textarea``, ``int``, ``select``,
``channel``, ``voice``, ``category``, ``role``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import discord

from core import economy, guild_logs, levels, prefix as prefixes, shop
from core import warnings as warnings_core
from src.antinuke import state as antinuke_state
from src.automod import commands as automod_commands
from src.giveaways import state as giveaway_state
from src.honeypot import state as honeypot_state
from src.reactionroles import state as reactionrole_state
from src.tempvoice import state as tempvoice_state
from src.tickets import state as tickets_state
from src.verification import state as verify_state
from src.welcome import state as welcome_state

if TYPE_CHECKING:
    from core.bot import SekaiBot

log = logging.getLogger("sekai.dashboard.modules")


# --------------------------------------------------------------------------- #
# Field helpers
# --------------------------------------------------------------------------- #

def _field(
    name: str, label: str, type: str, value: Any, **extra: Any
) -> dict[str, Any]:
    field: dict[str, Any] = {"name": name, "label": label, "type": type, "value": value}
    field.update({key: val for key, val in extra.items() if val is not None})
    return field


def _text(name: str, label: str, value: Any, *, kind: str = "text",
          placeholder: str | None = None, help: str | None = None) -> dict[str, Any]:
    return _field(name, label, kind, value, placeholder=placeholder, help=help)


def _int(name: str, label: str, value: Any, *, min: int | None = None,
         max: int | None = None, help: str | None = None) -> dict[str, Any]:
    return _field(name, label, "int", value, min=min, max=max, help=help)


def _bool(name: str, label: str, value: Any, *, help: str | None = None) -> dict[str, Any]:
    return _field(name, label, "bool", bool(value), help=help)


def _select(name: str, label: str, value: Any, options: list[dict[str, str]],
            *, help: str | None = None) -> dict[str, Any]:
    return _field(name, label, "select", value, options=options, help=help)


def _channel(guild: discord.Guild, name: str, label: str, value: Any, *,
             voice: bool = False, help: str | None = None) -> dict[str, Any]:
    channels = guild.voice_channels if voice else guild.text_channels
    prefix = "" if voice else "#"
    options = [{"value": str(c.id), "label": prefix + c.name} for c in channels]
    return _field(name, label, "channel", value, options=options, help=help)


def _category(guild: discord.Guild, name: str, label: str, value: Any, *,
              help: str | None = None) -> dict[str, Any]:
    options = [{"value": str(c.id), "label": c.name} for c in guild.categories]
    return _field(name, label, "category", value, options=options, help=help)


def _role(guild: discord.Guild, name: str, label: str, value: Any, *,
          help: str | None = None) -> dict[str, Any]:
    me = guild.me
    options = [
        {"value": str(role.id), "label": role.name}
        for role in reversed(guild.roles)
        if not role.is_default() and (me is None or role < me.top_role)
    ]
    return _field(name, label, "role", value, options=options, help=help)


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "none"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _require_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")


def _role_label(guild: discord.Guild, role_id: Any) -> str:
    if role_id is None:
        return "—"
    role = guild.get_role(int(role_id))
    return role.mention if role is not None else str(role_id)


def _channel_label(guild: discord.Guild, channel_id: Any) -> str:
    if channel_id is None:
        return "—"
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return str(channel_id)
    return getattr(channel, "mention", str(channel_id))


def _user_label(user_id: Any) -> str:
    return f"<@{user_id}>" if user_id is not None else "—"


# JavaScript's Number.MAX_SAFE_INTEGER: integers above it cannot be represented
# exactly in the browser.
_JS_SAFE_INTEGER = 2 ** 53 - 1


def _js_safe(value: Any) -> Any:
    """Serialise snowflakes as strings so the browser cannot round them.

    Discord IDs are 18-19 digits, past the range JavaScript represents exactly,
    so a JSON number arrives in the page with a different value — the saved
    channel/role no longer matches its ``<option>`` and a rounded ID is posted
    back. Converting them at the JSON boundary keeps every ID exact; the apply
    handlers read values with ``int()``, which accepts strings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > _JS_SAFE_INTEGER else value
    if isinstance(value, dict):
        return {key: _js_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_js_safe(item) for item in value]
    return value


# --------------------------------------------------------------------------- #
# Module: automod
# --------------------------------------------------------------------------- #

_AUTOMOD_FEATURES = (
    ("invites", "Block invite links"),
    ("links", "Block links"),
    ("spam", "Block spam"),
    ("mentionspam", "Block mention spam"),
    ("walloftext", "Block wall of text"),
    ("emojispam", "Block emoji spam"),
)


async def _read_automod(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    rules = await automod_commands._fetch_sekai_rules(guild)

    def is_on(feature: str) -> bool:
        rule = rules.get(feature)
        return bool(rule is not None and getattr(rule, "enabled", True))

    mention: int | None = None
    rule = rules.get("mentionspam")
    if rule is not None:
        mention = getattr(getattr(rule, "trigger", None), "mention_limit", None)

    fields = [
        _bool(feature, label, is_on(feature))
        for feature, label in _AUTOMOD_FEATURES[:3]
    ]
    fields.append(_bool("mentionspam", "Block mention spam", is_on("mentionspam")))
    fields.append(_int("mention_limit", "Mention limit", mention or 5, min=1, max=50))
    fields.extend(
        _bool(feature, label, is_on(feature))
        for feature, label in _AUTOMOD_FEATURES[4:]
    )
    return {"sections": [{"type": "form", "fields": fields, "submit": "Save filters"}]}


async def _apply_automod(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    values = payload.get("values") or {}
    rules = await automod_commands._fetch_sekai_rules(guild)

    def is_on(feature: str) -> bool:
        rule = rules.get(feature)
        return bool(rule is not None and getattr(rule, "enabled", True))

    for feature, _ in _AUTOMOD_FEATURES:
        if feature not in values:
            continue
        want = bool(values[feature])
        if want and not is_on(feature):
            error = await automod_commands._enable_feature(guild, feature)
        elif not want and is_on(feature):
            error = await automod_commands._disable_feature(guild, feature)
        else:
            error = None
        if error:
            return error

    if values.get("mentionspam") and values.get("mention_limit") not in (None, ""):
        limit = _require_int(values.get("mention_limit"), "Mention limit")
        if not 1 <= limit <= 50:
            return "Mention limit must be between 1 and 50."
        error = await automod_commands._enable_feature(
            guild, "mentionspam", mention_limit=limit)
        if error:
            return error
    return None


# --------------------------------------------------------------------------- #
# Module: welcome
# --------------------------------------------------------------------------- #

async def _read_welcome(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not welcome_state._loaded:
        await welcome_state.load_state(bot)
    config = welcome_state.get(guild.id) or welcome_state.WelcomeConfig()
    fields = [
        _channel(guild, "welcome_channel", "Welcome channel", config.welcome_channel),
        _text("welcome_message", "Welcome message", config.welcome_message,
              kind="textarea", placeholder="Welcome {user} to {server}!"),
        _bool("welcome_card_enabled", "Generate a welcome card image",
              config.welcome_card_enabled),
        _channel(guild, "leave_channel", "Goodbye channel", config.leave_channel),
        _text("leave_message", "Goodbye message", config.leave_message,
              kind="textarea", placeholder="{name} left {server}."),
        _bool("leave_card_enabled", "Generate a goodbye card image",
              config.leave_card_enabled),
        _role(guild, "autorole_id", "Autorole", config.autorole_id,
              help="Role given to new members."),
    ]
    return {"sections": [{"type": "form", "fields": fields, "submit": "Save welcome settings"}]}


async def _apply_welcome(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    if not welcome_state._loaded:
        await welcome_state.load_state(bot)
    config = welcome_state.get(guild.id) or welcome_state.WelcomeConfig()
    values = payload.get("values") or {}

    config.welcome_channel = _int_or_none(values.get("welcome_channel"))
    config.leave_channel = _int_or_none(values.get("leave_channel"))
    config.autorole_id = _int_or_none(values.get("autorole_id"))
    config.welcome_card_enabled = bool(values.get("welcome_card_enabled"))
    config.leave_card_enabled = bool(values.get("leave_card_enabled"))
    if "welcome_message" in values:
        config.welcome_message = (values.get("welcome_message") or "").strip() or None
    if "leave_message" in values:
        config.leave_message = (values.get("leave_message") or "").strip() or None

    await welcome_state.save(bot, guild.id, config)
    return None


# --------------------------------------------------------------------------- #
# Module: verification
# --------------------------------------------------------------------------- #

async def _read_verify(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    config = await verify_state.get_config(bot, guild.id) or verify_state.VerifyConfig(guild.id)
    fields = [
        _role(guild, "verified_role_id", "Verified role", config.verified_role_id,
              help="Members get this role after verifying."),
        _role(guild, "unverified_role_id", "Unverified role", config.unverified_role_id),
        _channel(guild, "verification_channel_id", "Verification fallback channel",
                 config.verification_channel_id,
                 help="Where to send members if a DM fails."),
        _text("url_path", "Verification link path", config.url_path or "",
              placeholder="verify",
              help="New links look like /<path>/<code>. Leave empty for /verify."),
        _text("custom_domain", "Custom domain", config.custom_domain or "",
              placeholder="verify.example.com",
              help="When set, links use https://<domain>/<code> and the path is ignored."),
        _int("min_account_days", "Minimum account age (days)", config.min_account_days,
             min=0, max=365),
        _int("expire_days", "Re-verify after (days, 0 = never)", config.expire_days,
             min=0, max=365),
        _bool("raid_mode", "Raid mode", config.raid_mode,
              help="Gate every new join through verification until turned off."),
        _int("raid_threshold", "Raid joins threshold", config.raid_threshold,
             min=1, max=100),
        _int("raid_window", "Raid window (seconds)", config.raid_window,
             min=1, max=3600),
    ]
    sections: list[dict[str, Any]] = [
        {"type": "form", "fields": fields, "submit": "Save verification"}
    ]
    if config.panel_channel_id and config.panel_message_id:
        link = (
            f"https://discord.com/channels/{guild.id}/"
            f"{config.panel_channel_id}/{config.panel_message_id}"
        )
        sections.append({
            "type": "note",
            "text": (
                f"Panel posted in {_channel_label(guild, config.panel_channel_id)}: "
                f"{link}. Run `verify panel` in Discord to move or replace it."
            ),
        })
    else:
        sections.append({
            "type": "note",
            "text": (
                "No verification panel has been posted yet. Run `verify panel` "
                "in Discord to post the Verify button."
            ),
        })
    return {"sections": sections}


_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


async def _apply_verify(bot: "SekaiBot", guild: discord.Guild,
                        payload: dict[str, Any]) -> str | None:
    config = await verify_state.get_config(bot, guild.id) or verify_state.VerifyConfig(guild.id)
    values = payload.get("values") or {}

    verified_role_id = _int_or_none(values.get("verified_role_id"))
    unverified_role_id = _int_or_none(values.get("unverified_role_id"))

    # The website and the join gate both hand out these roles, so reject a role
    # the bot cannot actually assign instead of saving a setup that fails for
    # every member who tries to verify.
    if verified_role_id is not None:
        role = guild.get_role(verified_role_id)
        if role is None:
            return "That verified role no longer exists — pick another one."
        problem = verify_state.role_problem(guild, role)
        if problem:
            return problem
    if unverified_role_id is not None:
        if unverified_role_id == verified_role_id:
            return "The unverified role must be different from the verified role."
        role = guild.get_role(unverified_role_id)
        if role is None:
            return "That unverified role no longer exists — pick another one."
        problem = verify_state.role_problem(guild, role)
        if problem:
            return problem

    min_account_days = _require_int(
        values.get("min_account_days", 0), "Minimum account age")
    expire_days = _require_int(values.get("expire_days", 0), "Re-verify days")
    raid_threshold = _require_int(
        values.get("raid_threshold", 10), "Raid threshold")
    raid_window = _require_int(values.get("raid_window", 60), "Raid window")
    if not 0 <= min_account_days <= 365:
        return "Minimum account age must be between 0 and 365 days."
    if not 0 <= expire_days <= 365:
        return "Re-verify days must be between 0 and 365."
    if not 1 <= raid_threshold <= 100:
        return "Raid threshold must be between 1 and 100 joins."
    if not 1 <= raid_window <= 3600:
        return "Raid window must be between 1 and 3600 seconds."

    url_path: str | None = None
    raw_path = str(values.get("url_path") or "").strip()
    if "url_path" in values and raw_path:
        url_path = verify_state.clean_url_path(raw_path)
        if url_path is None:
            return (
                "Use 3-32 letters, numbers or hyphens (not starting with a "
                "hyphen) for the link path, and avoid reserved words like "
                "`verify` — or leave it empty for /verify."
            )

    custom_domain: str | None = None
    raw_domain = str(values.get("custom_domain") or "").strip().lower()
    if "custom_domain" in values and raw_domain:
        if not _HOSTNAME_RE.match(raw_domain):
            return (
                "Use a bare hostname like `verify.example.com` for the custom "
                "domain — no https:// and no path."
            )
        custom_domain = raw_domain

    raid_mode = bool(values.get("raid_mode"))
    if raid_mode != config.raid_mode:
        # Toggling by hand holds until it is toggled back, like `verify raid`.
        # Keeping a leftover auto-trigger expiry would leave raid mode on while
        # raid_locked() reports it expired, so joins would slip through.
        config.raid_until = 0

    config.verified_role_id = verified_role_id
    config.unverified_role_id = unverified_role_id
    config.verification_channel_id = _int_or_none(values.get("verification_channel_id"))
    if "url_path" in values:
        config.url_path = url_path
    if "custom_domain" in values:
        config.custom_domain = custom_domain
    config.min_account_days = min_account_days
    config.expire_days = expire_days
    config.raid_mode = raid_mode
    config.raid_threshold = raid_threshold
    config.raid_window = raid_window
    await verify_state.save_config(bot, config)
    return None


# --------------------------------------------------------------------------- #
# Module: tickets
# --------------------------------------------------------------------------- #

async def _read_tickets(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not tickets_state._loaded:
        await tickets_state.load_state(bot)
    config = tickets_state._configs.get(guild.id)
    category = config.category_id if config else None
    staff = config.staff_role_id if config else None
    logs = config.log_channel_id if config else None
    fields = [
        _category(guild, "category_id", "Ticket category", category,
                  help="Tickets are created inside this category."),
        _role(guild, "staff_role_id", "Staff role", staff),
        _channel(guild, "log_channel_id", "Ticket log channel", logs),
    ]
    sections: list[dict[str, Any]] = [
        {"type": "form", "fields": fields, "submit": "Save ticket settings"}
    ]
    if config and config.panel_channel_id:
        sections.append({
            "type": "note",
            "text": (
                f"Panel posted in {_channel_label(guild, config.panel_channel_id)}. "
                "Run `ticket setup` again to move it."
            ),
        })
    return {"sections": sections}


async def _apply_tickets(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    if not tickets_state._loaded:
        await tickets_state.load_state(bot)
    values = payload.get("values") or {}
    category_id = _int_or_none(values.get("category_id"))
    staff_id = _int_or_none(values.get("staff_role_id"))
    if category_id is None or staff_id is None:
        return "Pick both a category and a staff role."

    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        return "That category is not a category in this server."
    staff = guild.get_role(staff_id)
    if staff is None or staff.is_default():
        return "Pick a real staff role, not @everyone."

    old = tickets_state._configs.get(guild.id)
    try:
        await category.set_permissions(
            guild.default_role, view_channel=False,
            reason="Sekai dashboard: keep tickets private")
        await category.set_permissions(
            staff, view_channel=True, send_messages=True, read_message_history=True,
            reason="Sekai dashboard: ticket staff role")
        if guild.me is not None:
            await category.set_permissions(
                guild.me, view_channel=True, send_messages=True,
                read_message_history=True, manage_channels=True,
                reason="Sekai dashboard: ticket access")
        if old is not None and old.staff_role_id != staff.id:
            old_role = guild.get_role(old.staff_role_id)
            if old_role is not None and old_role != staff:
                await category.set_permissions(
                    old_role, overwrite=None, reason="Sekai dashboard: old staff role")
    except discord.Forbidden:
        return "I need Manage Channels and Manage Roles to update the ticket category."

    config = tickets_state.Config(
        category_id=category.id,
        staff_role_id=staff.id,
        panel_channel_id=old.panel_channel_id if old else None,
        panel_message_id=old.panel_message_id if old else None,
        log_channel_id=_int_or_none(values.get("log_channel_id")))
    tickets_state._configs[guild.id] = config
    await bot.db.execute(
        "INSERT INTO ticket_config (guild_id, category_id, staff_role_id, "
        "panel_channel_id, panel_message_id, log_channel_id) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "category_id = excluded.category_id, "
        "staff_role_id = excluded.staff_role_id, "
        "panel_channel_id = excluded.panel_channel_id, "
        "panel_message_id = excluded.panel_message_id, "
        "log_channel_id = excluded.log_channel_id, "
        "updated_at = datetime('now')",
        (guild.id, category.id, staff.id, config.panel_channel_id,
         config.panel_message_id, config.log_channel_id))
    return None


# --------------------------------------------------------------------------- #
# Module: VoiceMaster (tempvoice)
# --------------------------------------------------------------------------- #

async def _read_tempvoice(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not tempvoice_state._loaded:
        await tempvoice_state.load_state(bot)
    config = tempvoice_state._configs.get(guild.id)
    category = config[0] if config else None
    trigger = config[1] if config else None
    fields = [
        _category(guild, "category_id", "Temporary channel category", category),
        _channel(guild, "trigger_id", "Join-to-create channel", trigger, voice=True),
    ]
    return {"sections": [{"type": "form", "fields": fields, "submit": "Save VoiceMaster"}]}


async def _apply_tempvoice(bot: "SekaiBot", guild: discord.Guild,
                           payload: dict[str, Any]) -> str | None:
    if not tempvoice_state._loaded:
        await tempvoice_state.load_state(bot)
    values = payload.get("values") or {}
    category_id = _int_or_none(values.get("category_id"))
    trigger_id = _int_or_none(values.get("trigger_id"))
    if category_id is None or trigger_id is None:
        return "Pick both a category and a join-to-create voice channel."

    old = tempvoice_state._configs.get(guild.id)
    menu = old[2] if old else None
    tempvoice_state._configs[guild.id] = (category_id, trigger_id, menu)
    await bot.db.execute(
        "INSERT INTO tempvoice (guild_id, category_id, trigger_id, menu_channel_id) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "category_id = excluded.category_id, trigger_id = excluded.trigger_id, "
        "updated_at = datetime('now')",
        (guild.id, category_id, trigger_id, menu))
    return None


# --------------------------------------------------------------------------- #
# Module: starboard
# --------------------------------------------------------------------------- #

async def _read_starboard(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    row = await bot.db.fetchone(
        "SELECT channel_id, emoji, threshold, self_star FROM starboard_config "
        "WHERE guild_id = ?", (guild.id,))
    fields = [
        _channel(guild, "channel_id", "Starboard channel",
                 row["channel_id"] if row else None),
        _text("emoji", "Star emoji", (row["emoji"] if row else None) or "⭐"),
        _int("threshold", "Stars needed", row["threshold"] if row else 3, min=1),
        _bool("self_star", "Allow self-starring", bool(row["self_star"]) if row else False),
    ]
    return {"sections": [{"type": "form", "fields": fields, "submit": "Save starboard"}]}


async def _apply_starboard(bot: "SekaiBot", guild: discord.Guild,
                           payload: dict[str, Any]) -> str | None:
    values = payload.get("values") or {}
    channel_id = _int_or_none(values.get("channel_id"))
    if channel_id is None:
        await bot.db.execute("DELETE FROM starboard_config WHERE guild_id = ?", (guild.id,))
        return None
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return "Pick a text channel for the starboard."
    emoji = (values.get("emoji") or "⭐").strip() or "⭐"
    threshold = _require_int(values.get("threshold", 3), "Stars needed")
    if threshold < 1:
        return "Stars needed must be at least 1."
    await bot.db.execute(
        "INSERT INTO starboard_config (guild_id, channel_id, emoji, threshold, self_star) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "channel_id = excluded.channel_id, emoji = excluded.emoji, "
        "threshold = excluded.threshold, self_star = excluded.self_star, "
        "updated_at = datetime('now')",
        (guild.id, channel.id, emoji, threshold, int(bool(values.get("self_star")))))
    return None


# --------------------------------------------------------------------------- #
# Module: honeypot
# --------------------------------------------------------------------------- #

async def _read_honeypot(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not honeypot_state._loaded:
        await honeypot_state.load_state(bot)
    config = honeypot_state.get(guild.id) or honeypot_state.Settings()
    channels = honeypot_state.channels(guild.id)
    punish = config.punish if config.punish in honeypot_state.PUNISHMENTS else "ban"
    fields = [
        _bool("enabled", "Enable honeypot", config.enabled),
        _select("punish", "Punishment", punish, [
            {"value": "ban", "label": "Ban"},
            {"value": "kick", "label": "Kick"},
            {"value": "timeout", "label": "Timeout"},
        ]),
    ]
    rows = [
        {"channel_id": str(channel_id), "channel": _channel_label(guild, channel_id)}
        for channel_id in sorted(channels)
        if guild.get_channel(channel_id) is not None
    ]
    sections: list[dict[str, Any]] = [
        {"type": "form", "fields": fields, "submit": "Save honeypot"},
        {
            "type": "list",
            "title": "Trap channels",
            "columns": [
                {"key": "channel", "label": "Channel"},
                {"key": "channel_id", "label": "ID"},
            ],
            "rows": rows,
            "delete": {"keys": ["channel_id"], "label": "Remove"},
            "add": {
                "fields": [_channel(guild, "channel_id", "Add a trap channel", None)],
                "submit": "Add",
            },
        },
    ]
    return {"sections": sections}


async def _apply_honeypot(bot: "SekaiBot", guild: discord.Guild,
                          payload: dict[str, Any]) -> str | None:
    if not honeypot_state._loaded:
        await honeypot_state.load_state(bot)
    action = payload.get("action")
    if action == "add":
        channel_id = _int_or_none((payload.get("values") or {}).get("channel_id"))
        if channel_id is None:
            return "Pick a channel."
        await honeypot_state.add_channel(bot, guild.id, channel_id)
        return None
    if action == "delete":
        channel_id = _int_or_none((payload.get("row") or {}).get("channel_id"))
        if channel_id is None:
            return "Unknown channel."
        await honeypot_state.remove_channel(bot, guild.id, channel_id)
        return None

    values = payload.get("values") or {}
    config = honeypot_state.get(guild.id) or honeypot_state.Settings()
    config.enabled = bool(values.get("enabled"))
    config.punish = values.get("punish") if values.get("punish") in honeypot_state.PUNISHMENTS else "ban"
    await honeypot_state.save(bot, guild.id, config)
    return None


# --------------------------------------------------------------------------- #
# Module: antinuke
# --------------------------------------------------------------------------- #

async def _read_antinuke(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not antinuke_state._loaded:
        await antinuke_state.load_state(bot)
    config = antinuke_state.get(guild.id) or antinuke_state.Settings()
    whitelist = antinuke_state.entries(guild.id)
    fields = [
        _bool("enabled", "Enable antinuke", config.enabled),
        _int("threshold", "Actions before punishing", config.threshold, min=2, max=10),
        _int("window", "Window (seconds)", config.window, min=5, max=60),
        _select("punish", "Punishment", config.punish if config.punish in antinuke_state.PUNISHMENTS else "ban", [
            {"value": "ban", "label": "Ban"},
            {"value": "kick", "label": "Kick"},
            {"value": "strip", "label": "Strip roles"},
        ]),
        _channel(guild, "alert_channel", "Alert channel", config.alert_channel),
        _channel(guild, "log_channel", "Log channel", config.log_channel),
    ]
    rows = [
        {
            "target_id": str(target_id),
            "target": _role_label(guild, target_id) if kind == "role" else _user_label(target_id),
            "kind": kind,
        }
        for target_id, kind in sorted(whitelist.items())
    ]
    sections: list[dict[str, Any]] = [
        {"type": "form", "fields": fields, "submit": "Save antinuke"},
        {
            "type": "list",
            "title": "Whitelist",
            "columns": [
                {"key": "target", "label": "Target"},
                {"key": "kind", "label": "Type"},
                {"key": "target_id", "label": "ID"},
            ],
            "rows": rows,
            "delete": {"keys": ["target_id"], "label": "Remove"},
            "add": {
                "fields": [
                    _text("target_id", "User or role ID", None),
                    _select("kind", "Type", "user", [
                        {"value": "user", "label": "User"},
                        {"value": "role", "label": "Role"},
                    ]),
                ],
                "submit": "Add",
            },
        },
    ]
    return {"sections": sections}


async def _apply_antinuke(bot: "SekaiBot", guild: discord.Guild,
                          payload: dict[str, Any]) -> str | None:
    if not antinuke_state._loaded:
        await antinuke_state.load_state(bot)
    action = payload.get("action")
    if action == "add":
        values = payload.get("values") or {}
        target_id = _int_or_none(values.get("target_id"))
        kind = values.get("kind")
        if target_id is None:
            return "Enter a numeric user or role ID."
        if kind not in ("user", "role"):
            return "Pick user or role."
        await antinuke_state.whitelist_add(bot, guild.id, target_id, kind, guild.me.id if guild.me else 0)
        return None
    if action == "delete":
        target_id = _int_or_none((payload.get("row") or {}).get("target_id"))
        if target_id is None:
            return "Unknown target."
        await antinuke_state.whitelist_remove(bot, guild.id, target_id)
        return None

    values = payload.get("values") or {}
    config = antinuke_state.get(guild.id) or antinuke_state.Settings()
    config.enabled = bool(values.get("enabled"))
    config.threshold = _require_int(values.get("threshold", 3), "Threshold")
    config.window = _require_int(values.get("window", 10), "Window")
    config.punish = values.get("punish") if values.get("punish") in antinuke_state.PUNISHMENTS else "ban"
    config.alert_channel = _int_or_none(values.get("alert_channel"))
    config.log_channel = _int_or_none(values.get("log_channel"))
    if not antinuke_state.MIN_THRESHOLD <= config.threshold <= antinuke_state.MAX_THRESHOLD:
        return f"Threshold must be between {antinuke_state.MIN_THRESHOLD} and {antinuke_state.MAX_THRESHOLD}."
    if not antinuke_state.MIN_WINDOW <= config.window <= antinuke_state.MAX_WINDOW:
        return f"Window must be between {antinuke_state.MIN_WINDOW} and {antinuke_state.MAX_WINDOW} seconds."
    await antinuke_state.save(bot, guild.id, config)
    return None


# --------------------------------------------------------------------------- #
# Module: server logs
# --------------------------------------------------------------------------- #

async def _read_logging(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    row = await bot.db.fetchone(
        "SELECT category_id FROM log_guilds WHERE guild_id = ?", (guild.id,))
    channels = await bot.db.fetchall(
        "SELECT kind, channel_id FROM log_channels WHERE guild_id = ? ORDER BY kind",
        (guild.id,))
    fields = [_bool("enabled", "Enable server logging", row is not None)]
    sections: list[dict[str, Any]] = [
        {"type": "form", "fields": fields, "submit": "Save logging"}
    ]
    if row is not None:
        rows = [
            {"kind": item["kind"], "channel": _channel_label(guild, item["channel_id"])}
            for item in channels
        ]
        sections.append({
            "type": "list",
            "title": "Log channels",
            "columns": [
                {"key": "kind", "label": "Group"},
                {"key": "channel", "label": "Channel"},
            ],
            "rows": rows,
        })
    return {"sections": sections}


async def _apply_logging(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    enabled = bool((payload.get("values") or {}).get("enabled"))
    if enabled:
        result = await guild_logs.setup_logging(bot, guild)
        if result is None:
            return "Could not set up logging. Check the bot's Manage Channels permission."
    else:
        await guild_logs.disable_logging(bot, guild)
    return None


# --------------------------------------------------------------------------- #
# Module: level rewards
# --------------------------------------------------------------------------- #

async def _read_levels(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    rewards = await levels.list_rewards(bot.db, guild.id)
    rows = [
        {"level": reward["level"], "role": _role_label(guild, reward["role_id"])}
        for reward in rewards
    ]
    return {"sections": [{
        "type": "list",
        "title": "Level rewards",
        "columns": [
            {"key": "level", "label": "Level"},
            {"key": "role", "label": "Role"},
        ],
        "rows": rows,
        "delete": {"keys": ["level"], "label": "Remove"},
        "add": {
            "fields": [
                _int("level", "Level", 1, min=1, max=500),
                _role(guild, "role_id", "Role", None),
            ],
            "submit": "Add",
        },
    }]}


async def _apply_levels(bot: "SekaiBot", guild: discord.Guild,
                        payload: dict[str, Any]) -> str | None:
    action = payload.get("action")
    if action == "delete":
        level = _int_or_none((payload.get("row") or {}).get("level"))
        if level is None:
            return "Unknown level."
        await levels.remove_reward(bot.db, guild.id, level)
        return None
    values = payload.get("values") or {}
    level = _require_int(values.get("level"), "Level")
    role_id = _int_or_none(values.get("role_id"))
    if level < 1:
        return "Level must be at least 1."
    if role_id is None:
        return "Pick a role."
    if guild.get_role(role_id) is None:
        return "That role is not in this server."
    await levels.set_reward(bot.db, guild.id, level, role_id)
    return None


# --------------------------------------------------------------------------- #
# Module: shop
# --------------------------------------------------------------------------- #

async def _read_shop(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    items = await shop.items(bot.db, guild.id)
    rows = []
    for item in items:
        if item["kind"] == shop.KIND_ROLE:
            detail = _role_label(guild, item["role_id"])
        else:
            detail = f"x{item['multiplier']} for {item['duration']}s"
        rows.append({
            "name": item["name"],
            "kind": "Role" if item["kind"] == shop.KIND_ROLE else "XP boost",
            "price": item["price"],
            "detail": detail,
        })
    return {"sections": [{
        "type": "list",
        "title": "Shop items",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "kind", "label": "Type"},
            {"key": "price", "label": "Price"},
            {"key": "detail", "label": "Grants"},
        ],
        "rows": rows,
        "delete": {"keys": ["name"], "label": "Remove"},
        "add": {
            "fields": [
                _text("name", "Name", None, placeholder="vip"),
                _select("kind", "Type", "role", [
                    {"value": "role", "label": "Role"},
                    {"value": "xp_boost", "label": "XP boost"},
                ]),
                _int("price", "Price", 100, min=0),
                _role(guild, "role_id", "Role (role items)", None),
                _text("multiplier", "Multiplier (boost items)", None, placeholder="2"),
                _int("duration", "Duration seconds (boost items)", None, min=1),
            ],
            "submit": "Add",
        },
    }]}


async def _apply_shop(bot: "SekaiBot", guild: discord.Guild,
                      payload: dict[str, Any]) -> str | None:
    action = payload.get("action")
    if action == "delete":
        name = str((payload.get("row") or {}).get("name", "")).strip()
        if not name:
            return "Unknown item."
        await shop.delete_item(bot.db, guild.id, name)
        return None
    values = payload.get("values") or {}
    name = str(values.get("name", "")).strip()
    if not name:
        return "Enter an item name."
    price = _require_int(values.get("price", 0), "Price")
    if price < 0:
        return "Price cannot be negative."
    kind = values.get("kind")
    if kind == shop.KIND_ROLE:
        role_id = _int_or_none(values.get("role_id"))
        if role_id is None:
            return "Pick a role for this item."
        role = guild.get_role(role_id)
        if role is None or role.is_default():
            return "That role is not in this server."
        if guild.me is not None and role >= guild.me.top_role:
            return "That role is above the bot, so it cannot be granted."
        await shop.create_item(bot.db, guild.id, name=name, kind=shop.KIND_ROLE,
                               price=price, role_id=role.id)
        return None
    if kind != shop.KIND_BOOST:
        return "Pick a valid item type."
    multiplier = values.get("multiplier")
    try:
        multiplier_value = float(multiplier)
    except (TypeError, ValueError):
        return "Enter a numeric multiplier."
    duration = _require_int(values.get("duration"), "Duration")
    if duration < 1:
        return "Duration must be at least 1 second."
    await shop.create_item(bot.db, guild.id, name=name, kind=shop.KIND_XP_BOOST,
                           price=price, multiplier=multiplier_value, duration=duration)
    return None


# --------------------------------------------------------------------------- #
# Module: tags
# --------------------------------------------------------------------------- #

async def _read_tags(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    rows_db = await bot.db.fetchall(
        "SELECT name, content, uses FROM tags WHERE guild_id = ? ORDER BY name",
        (guild.id,))
    rows = [
        {
            "name": item["name"],
            "uses": item["uses"],
            "content": (item["content"][:60] + "…") if len(item["content"] or "") > 60 else item["content"],
        }
        for item in rows_db
    ]
    return {"sections": [{
        "type": "list",
        "title": "Tags",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "uses", "label": "Uses"},
            {"key": "content", "label": "Content"},
        ],
        "rows": rows,
        "delete": {"keys": ["name"], "label": "Delete"},
        "add": {
            "fields": [
                _text("name", "Name", None, placeholder="rules"),
                _text("content", "Content", None, kind="textarea"),
            ],
            "submit": "Add",
        },
    }]}


async def _apply_tags(bot: "SekaiBot", guild: discord.Guild,
                      payload: dict[str, Any]) -> str | None:
    action = payload.get("action")
    if action == "delete":
        name = str((payload.get("row") or {}).get("name", "")).strip()
        if not name:
            return "Unknown tag."
        await bot.db.execute(
            "DELETE FROM tags WHERE guild_id = ? AND name = ?", (guild.id, name))
        return None
    values = payload.get("values") or {}
    name = str(values.get("name", "")).strip()
    content = str(values.get("content", "")).strip()
    if not name or not content:
        return "Enter both a name and content."
    if len(name) > 32:
        return "Tag names can be at most 32 characters."
    if len(content) > 1500:
        return "Tag content can be at most 1500 characters."
    author_id = guild.me.id if guild.me else 0
    await bot.db.execute(
        "INSERT INTO tags (guild_id, name, content, author_id) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, name) DO UPDATE SET content = excluded.content",
        (guild.id, name, content, author_id))
    return None


# --------------------------------------------------------------------------- #
# Module: reaction roles
# --------------------------------------------------------------------------- #

async def _read_reactionroles(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not reactionrole_state._loaded:
        await reactionrole_state.load_state(bot)
    mappings = reactionrole_state.for_guild(guild.id)
    rows = [
        {
            "message_id": str(mapping.message_id),
            "emoji": mapping.emoji,
            "role": _role_label(guild, mapping.role_id),
            "channel": _channel_label(guild, mapping.channel_id),
        }
        for mapping in mappings
    ]
    return {"sections": [{
        "type": "list",
        "title": "Reaction roles",
        "columns": [
            {"key": "emoji", "label": "Emoji"},
            {"key": "role", "label": "Role"},
            {"key": "channel", "label": "Channel"},
            {"key": "message_id", "label": "Message ID"},
        ],
        "rows": rows,
        "delete": {"keys": ["message_id", "emoji"], "label": "Remove"},
        "add": {
            "fields": [
                _channel(guild, "channel_id", "Channel", None),
                _text("message_id", "Message ID", None),
                _text("emoji", "Emoji", None, placeholder="⭐"),
                _role(guild, "role_id", "Role", None),
            ],
            "submit": "Add",
        },
    }]}


async def _apply_reactionroles(bot: "SekaiBot", guild: discord.Guild,
                               payload: dict[str, Any]) -> str | None:
    action = payload.get("action")
    if action == "delete":
        row = payload.get("row") or {}
        message_id = _int_or_none(row.get("message_id"))
        emoji = row.get("emoji")
        if message_id is None or not emoji:
            return "Unknown mapping."
        await reactionrole_state.remove(bot, message_id, emoji)
        return None
    values = payload.get("values") or {}
    channel_id = _int_or_none(values.get("channel_id"))
    message_id = _int_or_none(values.get("message_id"))
    emoji = str(values.get("emoji", "")).strip()
    role_id = _int_or_none(values.get("role_id"))
    if channel_id is None or message_id is None:
        return "Pick a channel and enter a message ID."
    if not emoji:
        return "Enter an emoji."
    if role_id is None:
        return "Pick a role."
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return "Pick a text channel."
    try:
        message = await channel.fetch_message(message_id)
    except discord.HTTPException:
        return "Could not find that message in the channel."
    mapping = reactionrole_state.Mapping(
        guild_id=guild.id, channel_id=channel.id, message_id=message.id,
        emoji=emoji, role_id=role_id)
    await reactionrole_state.add(bot, mapping)
    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        pass
    return None


# --------------------------------------------------------------------------- #
# Module: giveaways
# --------------------------------------------------------------------------- #

async def _read_giveaways(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    if not giveaway_state._loaded:
        await giveaway_state.load_state(bot)
    active = giveaway_state.active_for_guild(guild.id)
    rows = []
    for giveaway in active:
        ends = datetime.fromtimestamp(giveaway.ends_at, tz=timezone.utc)
        rows.append({
            "message_id": str(giveaway.message_id),
            "prize": giveaway.prize,
            "winners": giveaway.winners,
            "ends": ends.strftime("%Y-%m-%d %H:%M UTC"),
        })
    return {"sections": [{
        "type": "list",
        "title": "Active giveaways",
        "columns": [
            {"key": "prize", "label": "Prize"},
            {"key": "winners", "label": "Winners"},
            {"key": "ends", "label": "Ends"},
            {"key": "message_id", "label": "Message ID"},
        ],
        "rows": rows,
        "delete": {"keys": ["message_id"], "label": "End now"},
    }]}


async def _apply_giveaways(bot: "SekaiBot", guild: discord.Guild,
                           payload: dict[str, Any]) -> str | None:
    message_id = _int_or_none((payload.get("row") or {}).get("message_id"))
    if message_id is None:
        return "Unknown giveaway."
    giveaway = giveaway_state.by_message(message_id)
    if giveaway is None:
        return "That giveaway is no longer active."
    await giveaway_state.finish(bot, giveaway)
    return None


# --------------------------------------------------------------------------- #
# Module: economy
# --------------------------------------------------------------------------- #

async def _read_economy(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    rows_db, total = await economy.leaderboard(bot.db, guild.id, 1)
    rows = [
        {"user": _user_label(row["user_id"]), "balance": row["balance"]}
        for row in rows_db
    ]
    sections: list[dict[str, Any]] = [
        {
            "type": "list",
            "title": f"Top balances ({total} members)",
            "columns": [
                {"key": "user", "label": "Member"},
                {"key": "balance", "label": "Coins"},
            ],
            "rows": rows,
        },
        {
            "type": "form",
            "title": "Adjust a balance",
            "fields": [
                _text("user_id", "User ID", None),
                _int("amount", "Amount (negative to remove)", 0),
            ],
            "submit": "Apply",
        },
    ]
    return {"sections": sections}


async def _apply_economy(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    values = payload.get("values") or {}
    user_id = _int_or_none(values.get("user_id"))
    amount = _require_int(values.get("amount", 0), "Amount")
    if user_id is None:
        return "Enter a numeric user ID."
    await economy.add_balance(bot.db, guild.id, user_id, amount)
    return None


# --------------------------------------------------------------------------- #
# Module: moderation (warnings)
# --------------------------------------------------------------------------- #

async def _read_moderation(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    rows_db = await bot.db.fetchall(
        "SELECT id, user_id, moderator_id, reason, created_at FROM warnings "
        "WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (guild.id,))
    rows = [
        {
            "id": item["id"],
            "user": _user_label(item["user_id"]),
            "moderator": _user_label(item["moderator_id"]),
            "reason": item["reason"],
            "created": item["created_at"],
        }
        for item in rows_db
    ]
    return {"sections": [
        {
            "type": "list",
            "title": "Recent warnings",
            "columns": [
                {"key": "id", "label": "ID"},
                {"key": "user", "label": "Member"},
                {"key": "moderator", "label": "By"},
                {"key": "reason", "label": "Reason"},
                {"key": "created", "label": "When"},
            ],
            "rows": rows,
            "delete": {"keys": ["id"], "label": "Delete"},
        },
        {
            "type": "form",
            "title": "Add a warning",
            "fields": [
                _text("user_id", "User ID", None),
                _text("reason", "Reason", None),
            ],
            "submit": "Warn",
        },
    ]}


async def _apply_moderation(bot: "SekaiBot", guild: discord.Guild,
                            payload: dict[str, Any]) -> str | None:
    action = payload.get("action")
    if action == "delete":
        warning_id = _int_or_none((payload.get("row") or {}).get("id"))
        if warning_id is None:
            return "Unknown warning."
        await warnings_core.delete_warning(bot.db, guild.id, warning_id)
        return None
    values = payload.get("values") or {}
    user_id = _int_or_none(values.get("user_id"))
    reason = str(values.get("reason", "")).strip() or "No reason provided"
    if user_id is None:
        return "Enter a numeric user ID."
    await warnings_core.add_warning(
        bot.db, guild.id, user_id, guild.me.id if guild.me else 0, reason)
    return None


# --------------------------------------------------------------------------- #
# Module: suggestions (storage not enabled yet)
# --------------------------------------------------------------------------- #

async def _read_suggestions(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    return {"sections": [{
        "type": "note",
        "text": (
            "The suggestion module does not store data yet — its commands are "
            "placeholders. Use `suggest` for now."
        ),
    }]}


async def _apply_suggestions(bot: "SekaiBot", guild: discord.Guild,
                             payload: dict[str, Any]) -> str | None:
    return None


# --------------------------------------------------------------------------- #
# Module: general (prefix + broadcast)
# --------------------------------------------------------------------------- #

MAX_PREFIX = 5
MAX_BROADCAST = 2000


async def _read_general(bot: "SekaiBot", guild: discord.Guild) -> dict[str, Any]:
    prefix = await prefixes.get_guild_prefix(bot, guild.id)
    return {"sections": [
        {
            "type": "form",
            "title": "Command prefix",
            "fields": [_text("prefix", "Prefix", prefix,
                             help="1-5 characters, no spaces.")],
            "submit": "Save prefix",
        },
        {
            "type": "form",
            "title": "Broadcast a message",
            "fields": [
                _channel(guild, "channel_id", "Channel", None),
                _text("message", "Message", None, kind="textarea"),
            ],
            "submit": "Send message",
        },
    ]}


async def _apply_general(bot: "SekaiBot", guild: discord.Guild,
                         payload: dict[str, Any]) -> str | None:
    values = payload.get("values") or {}
    if "prefix" in values:
        prefix = str(values.get("prefix", "")).strip()
        if not 1 <= len(prefix) <= MAX_PREFIX or any(
            char.isspace() for char in prefix
        ):
            return f"Prefix must be 1-{MAX_PREFIX} characters with no spaces."
        await prefixes.set_guild_prefix(bot, guild.id, prefix)
        return None
    if "channel_id" in values or "message" in values:
        channel_id = _int_or_none(values.get("channel_id"))
        content = str(values.get("message", "")).strip()
        if channel_id is None:
            return "Pick a channel."
        if not content:
            return "Message is empty."
        if len(content) > MAX_BROADCAST:
            return f"Message is too long (max {MAX_BROADCAST})."
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "Pick a text channel."
        me = guild.me
        if me is not None:
            permissions = channel.permissions_for(me)
            if not permissions.send_messages or not permissions.view_channel:
                return "The bot cannot send messages in that channel."
        try:
            await channel.send(content)
        except discord.Forbidden:
            return "The bot lacks permission to send messages there."
        except discord.HTTPException:
            return "Discord rejected the message."
        return None
    return None


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

@dataclass
class Module:
    key: str
    label: str
    description: str
    read: Callable[["SekaiBot", discord.Guild], Awaitable[dict[str, Any]]]
    apply: Callable[["SekaiBot", discord.Guild, dict[str, Any]], Awaitable[str | None]]


MODULES: list[Module] = [
    Module("general", "General", "Command prefix and one-off message broadcasts.",
           _read_general, _apply_general),
    Module("automod", "AutoMod", "Discord AutoMod filters: invites, links, spam, mentions, wall of text, emoji spam.",
           _read_automod, _apply_automod),
    Module("welcome", "Welcome & Goodbye", "Welcome/goodbye messages, autorole and join/leave card images.",
           _read_welcome, _apply_welcome),
    Module("verification", "Verification", "Website verification, account-age gate, raid mode and expiry.",
           _read_verify, _apply_verify),
    Module("tickets", "Tickets", "Private support channels, staff role and ticket log channel.",
           _read_tickets, _apply_tickets),
    Module("tempvoice", "VoiceMaster", "Join-to-create voice channels and their category.",
           _read_tempvoice, _apply_tempvoice),
    Module("starboard", "Starboard", "Repost popular reacted messages with a configurable threshold.",
           _read_starboard, _apply_starboard),
    Module("honeypot", "Honeypot", "Trap channels that auto-punish anyone who posts in them.",
           _read_honeypot, _apply_honeypot),
    Module("antinuke", "Antinuke", "Punish bursts of dangerous audit-log actions, with a whitelist.",
           _read_antinuke, _apply_antinuke),
    Module("logging", "Server Logs", "Structured audit/event logging into a Logs category.",
           _read_logging, _apply_logging),
    Module("levels", "Level Rewards", "Roles granted automatically when members reach a level.",
           _read_levels, _apply_levels),
    Module("shop", "Shop", "Roles and XP boosts members buy with server coins.",
           _read_shop, _apply_shop),
    Module("tags", "Tags", "Reusable text snippets members can recall.",
           _read_tags, _apply_tags),
    Module("reactionroles", "Reaction Roles", "Roles granted when members react to a message.",
           _read_reactionroles, _apply_reactionroles),
    Module("giveaways", "Giveaways", "Active button-based giveaways.",
           _read_giveaways, _apply_giveaways),
    Module("economy", "Economy", "Coin balances and admin balance adjustments.",
           _read_economy, _apply_economy),
    Module("moderation", "Moderation", "Recent warnings and manual warning removal.",
           _read_moderation, _apply_moderation),
    Module("suggestions", "Suggestions", "Member suggestion review (storage not enabled yet).",
           _read_suggestions, _apply_suggestions),
]

BY_KEY: dict[str, Module] = {module.key: module for module in MODULES}


def module_summaries() -> list[dict[str, str]]:
    return [
        {"key": module.key, "label": module.label, "description": module.description}
        for module in MODULES
    ]


async def read_module(bot: "SekaiBot", guild: discord.Guild, key: str) -> dict[str, Any] | None:
    module = BY_KEY.get(key)
    if module is None:
        return None
    data = await module.read(bot, guild)
    data["key"] = module.key
    data["label"] = module.label
    data["description"] = module.description
    return _js_safe(data)


async def apply_module(bot: "SekaiBot", guild: discord.Guild, key: str,
                       payload: dict[str, Any]) -> str | None:
    module = BY_KEY.get(key)
    if module is None:
        return "Unknown module."
    try:
        return await module.apply(bot, guild, payload)
    except ValueError as exc:
        return str(exc)
    except discord.Forbidden:
        return "The bot is missing a permission needed for that change."
    except discord.HTTPException as exc:
        return f"Discord rejected that change: {exc}"