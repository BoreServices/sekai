import logging
import time
from contextlib import suppress
from datetime import timedelta

import discord
from discord.ext import commands

from core.emojis import markup
from core.guild_logs import send_log
from src.honeypot import state
from view import (
    error_embed,
    honeypot_action_embed,
    honeypot_status_embed,
    success_embed)

log = logging.getLogger("sekai.honeypot")

TIMEOUT_SECONDS = 24 * 3600
# A timed-out member can keep typing from other channels' drafts, and a failed
# punishment should not fire once per message. Ignore repeats for this long.
PUNISH_COOLDOWN = 10.0
MAX_TRACKED = 5000
MESSAGE_TYPES = {discord.MessageType.default, discord.MessageType.reply}

# (guild, member) -> monotonic time until which they are considered handled.
_recent: dict[tuple[int, int], float] = {}


def _settings(guild_id: int) -> state.Settings:
    return state.get(guild_id) or state.Settings()


def _exempt(member: discord.Member) -> bool:
    """Staff who are allowed to post in a trap channel without being punished."""
    if member.id == member.guild.owner_id:
        return True
    permissions = member.guild_permissions
    return (
        permissions.administrator
        or permissions.manage_guild
        or permissions.manage_messages
    )


def _health(guild: discord.Guild) -> list[str]:
    """Reasons the honeypot would silently do nothing, shown in `honeypot`."""
    problems: list[str] = []
    channel_ids = state.channels(guild.id)
    if not channel_ids:
        problems.append(
            "No trap channel is set — add one with `honeypot set #channel`."
        )
    else:
        missing = [cid for cid in channel_ids if guild.get_channel(cid) is None]
        if missing:
            problems.append(
                f"{len(missing)} trap channel(s) no longer exist — remove them "
                "with `honeypot remove`."
            )
    me = guild.me
    if me is None:
        problems.append("I cannot see my own member object in this server.")
    elif not (
        me.guild_permissions.ban_members
        or me.guild_permissions.kick_members
        or me.guild_permissions.moderate_members
    ):
        problems.append(
            "I cannot punish anyone: I need **Ban Members**, **Kick Members** "
            "or **Moderate Members**."
        )
    return problems


def _status_embed(guild: discord.Guild) -> discord.Embed:
    settings = _settings(guild.id)
    return honeypot_status_embed(
        enabled=settings.enabled,
        punish=settings.punish,
        channel_ids=sorted(state.channels(guild.id)),
        problems=_health(guild))


async def _punish(bot, message: discord.Message, settings: state.Settings) -> None:
    guild = message.guild
    member = message.author
    channel = message.channel
    reason = f"Honeypot: posted in trap channel #{channel}"

    with suppress(discord.HTTPException):
        await message.delete()

    # Try the configured punishment, then fall back to anything that still
    # works (a too-low role or a missing permission should not let them off).
    order = {
        "ban": ("ban", "kick", "timeout"),
        "kick": ("kick", "ban", "timeout"),
        "timeout": ("timeout", "kick", "ban"),
    }.get(settings.punish, ("ban", "kick", "timeout"))

    outcome: str | None = None
    problem: str | None = None
    me = guild.me
    if me is None:
        problem = "I am no longer in the server."
    else:
        for kind in order:
            try:
                if kind == "ban":
                    await guild.ban(
                        member, reason=reason, delete_message_seconds=3600
                    )
                    outcome = "banned"
                elif kind == "kick":
                    await member.kick(reason=reason)
                    outcome = "kicked"
                else:
                    until = discord.utils.utcnow() + timedelta(
                        seconds=TIMEOUT_SECONDS
                    )
                    await member.timeout(until, reason=reason)
                    outcome = "timed out"
                problem = None
                break
            except discord.HTTPException as exc:
                problem = (
                    f"the {kind} failed ({getattr(exc, 'status', None) or exc})."
                )

    log.info(
        "Honeypot: %s (%s) posted in %s (%s); %s",
        member,
        member.id,
        channel.id,
        guild.id,
        outcome or problem or "no action")

    embed = honeypot_action_embed(
        member=member,
        channel=channel,
        punish=settings.punish,
        outcome=outcome,
        problem=problem,
        content=message.content[:400] or None)
    # Best effort: a banned member usually cannot be DMed any more.
    with suppress(discord.HTTPException):
        await member.send(embed=embed)
    await send_log(bot, guild, "moderation", embed)


def setup(bot) -> None:
    @bot.listen("on_ready")
    async def load_honeypot() -> None:
        if not state._loaded:
            await state.load_state(bot)

    @bot.listen("on_message")
    async def honeypot_listener(message: discord.Message) -> None:
        if message.guild is None or message.webhook_id is not None:
            return
        if message.type not in MESSAGE_TYPES:
            return
        if bot.user is not None and message.author.id == bot.user.id:
            return
        if not state._loaded:
            await state.load_state(bot)
        settings = state.get(message.guild.id)
        if settings is None or not settings.enabled:
            return
        if not state.is_honeypot(message.guild.id, message.channel.id):
            return
        member = message.author
        if not isinstance(member, discord.Member) or _exempt(member):
            return
        me = message.guild.me
        if me is None or not (
            me.guild_permissions.ban_members
            or me.guild_permissions.kick_members
            or me.guild_permissions.moderate_members
        ):
            return

        key = (message.guild.id, member.id)
        if _recent.get(key, 0.0) > time.monotonic():
            with suppress(discord.HTTPException):
                await message.delete()
            return
        if len(_recent) > MAX_TRACKED:
            _recent.clear()
        _recent[key] = time.monotonic() + PUNISH_COOLDOWN
        await _punish(bot, message, settings)

    @bot.group(
        name="honeypot",
        help="Trap channels that auto-punish raid bots and self-bots.",
        usage="honeypot",
        invoke_without_command=True)
    @commands.guild_only()
    async def honeypot(ctx: commands.Context) -> None:
        if not state._loaded:
            await state.load_state(bot)
        await ctx.send(embed=_status_embed(ctx.guild))

    @honeypot.command(
        name="set",
        aliases=["add"],
        help="Mark a channel as a honeypot trap.",
        usage="honeypot set <#channel>")
    @commands.has_permissions(manage_guild=True)
    async def set_channel(ctx: commands.Context, channel: discord.TextChannel) -> None:
        if not state._loaded:
            await state.load_state(bot)
        if channel.guild.id != ctx.guild.id:
            await ctx.send(embed=error_embed("Pick a channel from this server."))
            return
        await state.add_channel(bot, ctx.guild.id, channel.id)
        settings = _settings(ctx.guild.id)
        text = (
            f"{channel.mention} is now a honeypot. Anyone who posts there "
            f"(except staff) is **{settings.punish}**."
        )
        if not settings.enabled:
            text += "\n\nIt is not active yet — run `honeypot enable`."
        problems = _health(ctx.guild)
        if problems:
            text += f"\n\n{markup('warning', '⚠️')} " + " ".join(problems)
        await ctx.send(embed=success_embed(text, icon="🍯"))

    @honeypot.command(
        name="remove",
        aliases=["del", "unset"],
        help="Stop treating a channel as a honeypot.",
        usage="honeypot remove <#channel>")
    @commands.has_permissions(manage_guild=True)
    async def remove_channel(ctx: commands.Context, channel: discord.TextChannel) -> None:
        if not state._loaded:
            await state.load_state(bot)
        removed = await state.remove_channel(bot, ctx.guild.id, channel.id)
        if not removed:
            await ctx.send(
                embed=error_embed(f"{channel.mention} is not a honeypot.")
            )
            return
        await ctx.send(
            embed=success_embed(
                f"{channel.mention} is no longer a honeypot.", icon="🍯"
            )
        )

    @honeypot.command(
        name="list",
        help="Show every honeypot channel in this server.",
        usage="honeypot list")
    @commands.has_permissions(manage_guild=True)
    async def list_channels(ctx: commands.Context) -> None:
        if not state._loaded:
            await state.load_state(bot)
        await ctx.send(embed=_status_embed(ctx.guild))

    @honeypot.command(
        name="punish",
        help="What happens to whoever posts in a trap channel.",
        usage="honeypot punish <ban|kick|timeout>")
    @commands.has_permissions(manage_guild=True)
    async def punish(ctx: commands.Context, mode: str) -> None:
        lowered = mode.strip().lower()
        if lowered not in state.PUNISHMENTS:
            await ctx.send(embed=error_embed("Pick `ban`, `kick` or `timeout`."))
            return
        settings = _settings(ctx.guild.id)
        settings.punish = lowered
        await state.save(bot, ctx.guild.id, settings)
        await ctx.send(
            embed=success_embed(
                f"The honeypot will now **{lowered}** whoever posts in it.",
                icon="🍯")
        )

    @honeypot.command(
        name="enable",
        help="Turn the honeypot on.",
        usage="honeypot enable")
    @commands.has_permissions(manage_guild=True)
    async def enable(ctx: commands.Context) -> None:
        if not state._loaded:
            await state.load_state(bot)
        settings = _settings(ctx.guild.id)
        settings.enabled = True
        await state.save(bot, ctx.guild.id, settings)
        text = (
            f"The honeypot is **on**. Posting in a trap channel gets you "
            f"**{settings.punish}**."
        )
        problems = _health(ctx.guild)
        if problems:
            text += f"\n\n{markup('warning', '⚠️')} **It will not work yet:** " + " ".join(problems)
        await ctx.send(embed=success_embed(text, icon="🍯"))

    @honeypot.command(
        name="disable",
        help="Turn the honeypot off.",
        usage="honeypot disable")
    @commands.has_permissions(manage_guild=True)
    async def disable(ctx: commands.Context) -> None:
        settings = _settings(ctx.guild.id)
        settings.enabled = False
        await state.save(bot, ctx.guild.id, settings)
        await ctx.send(embed=success_embed("The honeypot is **off**.", icon="🍯"))