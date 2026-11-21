import discord

from datetime import datetime, timezone

from view.base import (
    ERROR_COLOR,
    INFO_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)

# "punish" setting -> how the alert phrases what happened.
PUNISHMENTS = {
    "ban": "banned",
    "kick": "kicked",
    "strip": "stripped of their roles",
}

# A stored antinuke event -> title and colour for its log embed.
LOG_KINDS = {
    "enabled": ("🛡️ Guard enabled", SUCCESS_COLOR),
    "disabled": ("🛡️ Guard disabled", WARNING_COLOR),
    "threshold": ("⚙️ Threshold changed", INFO_COLOR),
    "window": ("⚙️ Window changed", INFO_COLOR),
    "punish": ("⚙️ Punishment changed", INFO_COLOR),
    "alert_channel": ("🔔 Alert channel changed", INFO_COLOR),
    "log_channel": ("📝 Log channel changed", INFO_COLOR),
    "whitelist_add": ("✅ Trusted", SUCCESS_COLOR),
    "whitelist_remove": ("➖ No longer trusted", WARNING_COLOR),
    "trigger": ("🚨 Guard triggered", ERROR_COLOR),
    "health": ("⚠️ Guard not armed", WARNING_COLOR),
}


def antinuke_status_embed(
    *,
    enabled: bool,
    threshold: int,
    window: int,
    punish: str,
    alert_channel: int | None,
    trusted: list[tuple[int, str]],
    log_channel: int | None = None) -> discord.Embed:
    state = "enabled" if enabled else "disabled"
    embed = base_embed(
        title="🛡️ Antinuke",
        description=(
            f"The guard is **{state}**. It watches bans, kicks, prunes, channel "
            "and role creates/deletes, emoji and sticker deletions, webhook "
            "creations, bot additions and server-setting changes, then punishes "
            f"whoever crosses **{threshold}** of them in **{window}s**. Adding a "
            "bot triggers instantly and the added bot is banned if untrusted."
        ),
        color=SUCCESS_COLOR if enabled else WARNING_COLOR)
    if trusted:
        lines = [
            f"<@{target_id}>" if kind == "user" else f"<@&{target_id}>"
            for target_id, kind in trusted[:20]
        ]
        if len(trusted) > 20:
            lines.append(f"…and {len(trusted) - 20} more")
        trusted_text = "\n".join(lines)
    else:
        trusted_text = "Nobody is exempt — add your staff with `antinuke whitelist add`."

    alert_text = f"<#{alert_channel}>" if alert_channel else "the server's log channel"
    if log_channel == 0:
        log_text = "off (alerts still go to moderation)"
    elif log_channel:
        log_text = f"<#{log_channel}>"
    else:
        log_text = "auto (`#logs-antinuke` → moderation log)"

    embed.add_field(
        name="Threshold",
        value=f"`{threshold}` actions in `{window}s`",
        inline=True)
    embed.add_field(name="Punishment", value=f"`{punish}`", inline=True)
    embed.add_field(name="Alerts", value=alert_text, inline=True)
    embed.add_field(name="Antinuke log", value=log_text, inline=True)
    embed.add_field(name="Trusted", value=trusted_text, inline=False)
    embed.add_field(
        name="Commands",
        value=(
            "`antinuke enable` · `antinuke disable` · `antinuke threshold <2-10>` · "
            "`antinuke window <5-60>` · `antinuke punish <ban|kick|strip>` · "
            "`antinuke alert <#channel|off>` · `antinuke logs <#channel|auto|off>` · "
            "`antinuke history [page]` · `antinuke check <member>` · "
            "`antinuke whitelist add <member|role>` · "
            "`antinuke whitelist remove <member|role>` · `antinuke whitelist list`"
        ),
        inline=False)
    return brand(embed)


def antinuke_alert_embed(
    actor: discord.abc.User | None,
    *,
    actor_id: int | None = None,
    count: int,
    window: int,
    breakdown: str | None = None,
    outcome: str | None = None,
    problem: str | None = None,
    undone: str | None = None) -> discord.Embed:
    mention = getattr(actor, "mention", None) or f"<@{actor_id}>"
    description = (
        f"{mention} tripped the guard with **{count}** watched action"
        f"{'s' if count != 1 else ''} in {window} seconds."
    )
    if breakdown:
        description += f"\n{breakdown}"
    if problem:
        description += f"\n\n⚠️ I could not stop them: {problem}"
    elif outcome:
        description += f"\n\n{outcome}"

    embed = base_embed(
        title="🚨 Antinuke triggered",
        description=description,
        color=ERROR_COLOR if problem is None else WARNING_COLOR)
    embed.add_field(name="Account", value=f"`{actor_id}`", inline=True)
    embed.add_field(name="Actions", value=f"`{count}`", inline=True)
    if breakdown:
        embed.add_field(name="Trigger", value=breakdown, inline=False)
    if undone:
        embed.add_field(name="Cleanup", value=undone, inline=False)
    return brand(embed)


def antinuke_dm_embed(
    *,
    label: str,
    punish: str,
    reason: str,
    problem: str | None = None) -> discord.Embed:
    """DM sent to whoever got caught, so they know what happened."""
    if problem:
        embed = base_embed(
            title="🛡️ Antinuke caught you",
            description=(
                f"You triggered the antinuke guard by {label}, but I could not "
                f"punish you: {problem}"
            ),
            color=WARNING_COLOR)
    else:
        embed = base_embed(
            title="🛡️ Antinuke caught you",
            description=(
                f"You were {PUNISHMENTS.get(punish, punish)} for {label} too "
                f"quickly. Staff can restore whatever they need to."
            ),
            color=ERROR_COLOR)
    embed.add_field(name="Reason", value=reason, inline=False)
    return brand(embed)


def _when(value) -> int | None:
    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return int(parsed.timestamp())


def _short(text, limit: int = 90) -> str:
    text = str(text).replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def antinuke_log_embed(
    kind: str,
    *,
    guild: discord.Guild | None = None,
    actor_id: int | None = None,
    actor_name: str | None = None,
    detail: str | None = None,
    outcome: str | None = None) -> discord.Embed:
    """One entry in the antinuke log channel (config changes, triggers, ...)."""
    title, color = LOG_KINDS.get(kind, ("🛡️ Antinuke event", INFO_COLOR))
    embed = base_embed(title=title, description=detail or None, color=color)
    if guild is not None:
        embed.add_field(
            name="Server", value=f"{guild.name} (`{guild.id}`)", inline=True
        )
    if actor_id is not None:
        who = f"{actor_name} (`{actor_id}`)" if actor_name else f"<@{actor_id}>"
        embed.add_field(name="By", value=who, inline=True)
    if outcome:
        embed.add_field(name="Outcome", value=outcome, inline=False)
    return brand(embed)


def antinuke_history_embed(
    rows,
    *,
    total: int,
    page: int = 1,
    page_size: int = 10) -> discord.Embed:
    """The `antinuke history` view, newest first."""
    pages = max(1, (total + page_size - 1) // page_size)
    if not rows:
        embed = base_embed(
            title="📜 Antinuke history",
            description="No antinuke events have been recorded yet.",
            color=INFO_COLOR)
    else:
        lines: list[str] = []
        for row in rows:
            title, _ = LOG_KINDS.get(row["kind"], ("Antinuke event", INFO_COLOR))
            bits = [f"**{title}**"]
            stamp = _when(row["created_at"])
            if stamp is not None:
                bits.insert(0, f"<t:{stamp}:R>")
            if row["actor_id"]:
                bits.append(row["actor_name"] or f"<@{row['actor_id']}>")
            if row["detail"]:
                bits.append(_short(row["detail"]))
            line = "• " + " · ".join(bits)
            if row["outcome"]:
                line += f"\n> {_short(row['outcome'])}"
            lines.append(line)
        embed = base_embed(
            title="📜 Antinuke history",
            description="\n".join(lines),
            color=INFO_COLOR)
    embed.add_field(name="Page", value=f"{page}/{pages}", inline=True)
    embed.add_field(name="Stored", value=f"{total} event(s)", inline=True)
    return brand(embed)

