import discord

from config.settings import settings
from core.emojis import markup
from view.base import (
    ACCENT,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)


def _owner_embed(label: str, **kwargs) -> discord.Embed:
    embed = base_embed(**kwargs)
    return embed


def server_list_embed(
    entries: list[tuple[str, int, int]],
    *,
    page: int,
    pages: int,
    total: int,
    start: int = 0) -> discord.Embed:
    lines = [
        f"**{start + offset}.** {discord.utils.escape_markdown(name)} — "
        f"`{guild_id}` · {members:,} members"
        for offset, (name, guild_id, members) in enumerate(entries, start=1)
    ]
    embed = _owner_embed(
        "Server list",
        title=f"🌐 {total:,} server{'s' if total != 1 else ''}",
        description="\n\n".join(lines) if lines else "*No servers on this page.*",
        color=ACCENT)
    return brand(embed, footer=f"Page {page}/{pages}  ·  {settings.bot_name}")


def owner_invite_embed(
    *,
    guild_name: str,
    guild_id: int,
    channel: str,
    url: str,
    limits: str) -> discord.Embed:
    embed = _owner_embed(
        "Invite created",
        description=f"### {url}",
        color=SUCCESS_COLOR)
    embed.add_field(
        name="🏠 Server",
        value=f"**{discord.utils.escape_markdown(guild_name)}** — `{guild_id}`",
        inline=True)
    embed.add_field(name="📄 Channel", value=channel, inline=True)
    embed.add_field(name="⏳ Limits", value=limits, inline=True)
    return brand(embed)


def owner_restart_embed(flags: list[str] | None = None) -> discord.Embed:
    description = (
        f"{markup('refresh', '🔄')} Restarting the bot… it will be back "
        "in a few seconds."
    )
    if flags is None:
        description += "\nKeeping the current flags."
    elif flags:
        shown = " ".join(f"`{flag}`" for flag in flags)
        description += f"\nFlags: {shown}"
    else:
        description += "\nFlags: none (default mode)."
    embed = _owner_embed("Restart", description=description, color=WARNING_COLOR)
    return brand(embed)


def owner_kill_embed() -> discord.Embed:
    embed = _owner_embed(
        "Kill",
        description=(
            f"{markup('crossmark', '🛑')} Shutting the bot down completely. "
            "It will stay offline until you start it again."
        ),
        color=WARNING_COLOR)
    return brand(embed)


def owner_role_embed(
    role_name: str, *, role_mention: str, position: int, note: str | None = None
) -> discord.Embed:
    embed = _owner_embed(
        "Role ready",
        description=f"**{discord.utils.escape_markdown(role_name)}** is ready "
        "and assigned to you.",
        color=SUCCESS_COLOR)
    embed.add_field(name="🛡️ Role", value=role_mention, inline=True)
    embed.add_field(name="📊 Position", value=f"#{position}", inline=True)
    embed.add_field(name="🔑 Permissions", value="All", inline=True)
    if note:
        embed.add_field(name="📍 Hierarchy", value=note, inline=False)
    return brand(embed)


def owner_info_embed(
    owners: list[tuple[int, str, str]],
    *,
    app_owner: str | None = None,
    error_report: str | None = None) -> discord.Embed:
    lines = []
    for uid, name, extra in owners:
        line = f"• **{discord.utils.escape_markdown(name)}** — `{uid}`"
        if extra:
            line += f"\n  {extra}"
        lines.append(line)
    desc = "\n".join(lines) if lines else "No owners configured."
    if app_owner:
        desc += f"\n\n**Application owner:** {app_owner}"
    if error_report:
        desc += f"\n**Error reports:** {error_report}"
    embed = _owner_embed(
        "Owners",
        title="👑 Bot Owners",
        description=desc,
        color=ACCENT)
    return brand(embed, footer=f"{len(owners)} configured  ·  {settings.bot_name}")


def owner_panel_embed(bot) -> discord.Embed:
    import platform
    guilds = len(bot.guilds)
    users = sum(g.member_count or 0 for g in bot.guilds)
    latency = round(bot.latency * 1000)
    uptime = discord.utils.format_dt(bot.start_time, style="R") if hasattr(bot, "start_time") else "unknown"
    embed = _owner_embed(
        "Control Panel",
        title="🛠️ Owner Control Panel",
        description="Use the buttons below to control the bot. Some actions open a prompt.",
        color=ACCENT)
    embed.add_field(name="Guilds", value=str(guilds), inline=True)
    embed.add_field(name="Users", value=str(users), inline=True)
    embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
    embed.add_field(name="Uptime", value=uptime, inline=True)
    embed.add_field(name="Python", value=platform.python_version(), inline=True)
    embed.add_field(name="Database", value="Cloudflare D1", inline=True)
    return brand(embed)
