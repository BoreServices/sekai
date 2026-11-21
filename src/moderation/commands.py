import logging
import math
import re
from contextlib import suppress
from datetime import timedelta

import discord
from discord.ext import commands

from core import warnings
from src.antinuke import state as antinuke_state
from view import (
    NukeConfirmView,
    SUCCESS_COLOR,
    ban_list_embed,
    error_embed,
    moderation_embed,
    nuke_confirm_embed,
    warning_dm_embed,
    warnings_embed)

log = logging.getLogger("sekai.moderation")

DURATION = re.compile(r"(\d+)([smhdw])")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
DEFAULT_MUTE = 600
MAX_TIMEOUT = 28 * 86400
MAX_SLOWMODE = 6 * 3600
PURGE_LIMIT = 100
BAN_PAGE_SIZE = 15
WARN_PAGE_SIZE = 15
NICK_MAX = 32
SOFTBAN_SECONDS = 86400


async def _nuke_blocked(ctx: commands.Context) -> bool:
    """Antinuke is on and this member has not been trusted with destructive tools."""
    if not antinuke_state._loaded:
        await antinuke_state.load_state(ctx.bot)
    guard = antinuke_state.get(ctx.guild.id)
    if guard is None or not guard.enabled:
        return False
    trusted = antinuke_state.whitelisted(
        ctx.guild.id, ctx.author.id, {role.id for role in ctx.author.roles}
    )
    return not trusted


def _parse_duration(token: str) -> int | None:
    match = DURATION.fullmatch(token.lower())
    if match is None:
        return None
    return int(match.group(1)) * UNITS[match.group(2)]


def _split_duration(args: str | None, default: int) -> tuple[int, str | None]:
    tokens = (args or "").split()
    if tokens:
        seconds = _parse_duration(tokens[0])
        if seconds is not None:
            return seconds, " ".join(tokens[1:]) or None
    return default, " ".join(tokens) or None


def _duration_text(seconds: int) -> str:
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _target(member: discord.abc.User) -> str:
    return f"{member.mention} (`{member.id}`)"


def _hierarchy(ctx: commands.Context, member: discord.Member) -> str | None:
    if member.id == ctx.author.id:
        return "You can't use that on yourself."
    if ctx.bot.user is not None and member.id == ctx.bot.user.id:
        return "I can't use that on myself."
    if member.id == ctx.guild.owner_id:
        return "The server owner can't be moderated."
    if ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
        return f"{member.mention} has a role equal to or higher than yours."
    me = ctx.guild.me
    if me is None or member.top_role >= me.top_role:
        return f"I can't act on {member.mention} — move my role above theirs."
    return None


def _ban_blocker(ctx: commands.Context, user: discord.abc.User) -> str | None:
    if user.id == ctx.author.id:
        return "You can't ban yourself."
    if ctx.bot.user is not None and user.id == ctx.bot.user.id:
        return "I can't ban myself."
    if user.id == ctx.guild.owner_id:
        return "The server owner can't be banned."
    member = ctx.guild.get_member(user.id)
    if member is not None:
        return _hierarchy(ctx, member)
    return None


def _voice_problem(ctx: commands.Context, member: discord.Member) -> str | None:
    problem = _hierarchy(ctx, member)
    if problem:
        return problem
    if member.voice is None or member.voice.channel is None:
        return f"{member.mention} isn't in a voice channel."
    return None


def setup(bot) -> None:
    @bot.command(
        name="kick",
        help="Kick a member from the server.",
        usage="kick <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _hierarchy(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return

        reason = reason or f"Kicked by {ctx.author}"
        antinuke_state.record_bot_action(ctx.guild.id, "kick", ctx.author.id)
        try:
            await member.kick(reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the kick: {exc}"))
            return

        log.info(
            "Kicked %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member kicked",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} was removed from the server.",
                icon="kick",
                color=discord.Color.orange())
        )

    @bot.command(
        name="ban",
        help="Ban a user by mention or ID.",
        usage="ban <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(
        ctx: commands.Context, user: discord.User, *, reason: str | None = None
    ) -> None:
        blocker = _ban_blocker(ctx, user)
        if blocker:
            await ctx.send(embed=error_embed(blocker))
            return

        reason = reason or f"Banned by {ctx.author}"
        antinuke_state.record_bot_action(ctx.guild.id, "ban", ctx.author.id)
        try:
            await ctx.guild.ban(user, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the ban: {exc}"))
            return

        log.info(
            "Banned %s (%s) in %s by %s: %s",
            user, user.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "User banned",
                target=_target(user),
                moderator=ctx.author,
                reason=reason,
                details=f"{user.mention} can no longer join the server.",
                icon="ban",
                color=discord.Color.red())
        )

    @bot.command(
        name="softban",
        help="Ban, wipe the last day of their messages and unban right away.",
        usage="softban <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def softban(
        ctx: commands.Context, user: discord.User, *, reason: str | None = None
    ) -> None:
        blocker = _ban_blocker(ctx, user)
        if blocker:
            await ctx.send(embed=error_embed(blocker))
            return

        reason = reason or f"Softbanned by {ctx.author}"
        antinuke_state.record_bot_action(ctx.guild.id, "ban", ctx.author.id)
        try:
            await ctx.guild.ban(
                user,
                reason=f"{reason} — {ctx.author}",
                delete_message_seconds=SOFTBAN_SECONDS)
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the ban: {exc}"))
            return

        try:
            await ctx.guild.unban(user, reason=f"Softban lift — {ctx.author}")
        except discord.HTTPException as exc:
            log.warning(
                "Softban of %s (%s) in %s failed to unban: %s",
                user, user.id, ctx.guild.id, exc)
            await ctx.send(
                embed=error_embed(
                    f"Banned {user.mention} but couldn't lift the ban: {exc}\n"
                    f"Run `{ctx.prefix}unban {user.id}` to finish."
                )
            )
            return

        log.info(
            "Softbanned %s (%s) in %s by %s: %s",
            user, user.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "User softbanned",
                target=_target(user),
                moderator=ctx.author,
                reason=reason,
                details=(
                    f"{user.mention}'s last 24h of messages were removed and "
                    "they can rejoin immediately."
                ),
                icon="softban",
                color=discord.Color.orange())
        )

    @bot.command(
        name="banlist",
        help="List every banned user, 15 per page.",
        usage="banlist [page]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def banlist(ctx: commands.Context, page: int = 1) -> None:
        entries = [
            (entry.user.display_name, entry.user.id, entry.reason)
            async for entry in ctx.guild.bans(limit=None)
        ]
        total = len(entries)
        pages = max(1, math.ceil(total / BAN_PAGE_SIZE))
        page = min(max(page, 1), pages)
        start = (page - 1) * BAN_PAGE_SIZE
        chunk = entries[start : start + BAN_PAGE_SIZE]

        await ctx.send(
            embed=ban_list_embed(
                [
                    (start + offset + 1, name, user_id, reason)
                    for offset, (name, user_id, reason) in enumerate(chunk)
                ],
                page=page,
                pages=pages,
                total=total)
        )

    @bot.command(
        name="unban",
        help="Lift a ban using the user ID.",
        usage="unban <user id> [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(
        ctx: commands.Context, user: discord.User, *, reason: str | None = None
    ) -> None:
        reason = reason or f"Unbanned by {ctx.author}"
        try:
            await ctx.guild.unban(user, reason=f"{reason} — {ctx.author}")
        except discord.NotFound:
            await ctx.send(embed=error_embed(f"{user.mention} isn't banned."))
            return
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the unban: {exc}"))
            return

        log.info(
            "Unbanned %s (%s) in %s by %s: %s",
            user, user.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "User unbanned",
                target=_target(user),
                moderator=ctx.author,
                reason=reason,
                details=f"{user.mention} can join the server again.",
                icon="unban",
                color=discord.Color.green())
        )

    @bot.command(
        name="mute",
        aliases=["timeout"],
        help="Time out a member (default 10m, max 28d).",
        usage="mute <member> [duration] [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def mute(
        ctx: commands.Context, member: discord.Member, *, args: str | None = None
    ) -> None:
        problem = _hierarchy(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return

        seconds, reason = _split_duration(args, DEFAULT_MUTE)
        if seconds <= 0:
            await ctx.send(embed=error_embed("The timeout must be at least 1 second."))
            return
        if seconds > MAX_TIMEOUT:
            await ctx.send(
                embed=error_embed("Discord allows timeouts of at most **28d**.")
            )
            return

        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        reason = reason or f"Muted by {ctx.author}"
        try:
            await member.timeout(until, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the timeout: {exc}"))
            return

        log.info(
            "Muted %s (%s) in %s for %ss by %s: %s",
            member, member.id, ctx.guild.id, seconds, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member muted",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=(
                    f"{member.mention} is timed out for **{_duration_text(seconds)}** "
                    f"until {discord.utils.format_dt(until, 'f')}."
                ),
                icon="mute",
                color=discord.Color.red())
        )

    @bot.command(
        name="unmute",
        aliases=["untimeout"],
        help="Remove a member's timeout.",
        usage="unmute <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def unmute(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _hierarchy(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if member.timed_out_until is None:
            await ctx.send(embed=error_embed(f"{member.mention} isn't muted."))
            return

        reason = reason or f"Unmuted by {ctx.author}"
        try:
            await member.timeout(None, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the unmute: {exc}"))
            return

        log.info(
            "Unmuted %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member unmuted",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} can talk again.",
                icon="unmute",
                color=discord.Color.green())
        )

    @bot.command(
        name="warn",
        help="Warn a member and keep the warning on record.",
        usage="warn <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _hierarchy(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return

        reason = reason or "No reason given."
        warning_id = await warnings.add_warning(
            ctx.bot.db, ctx.guild.id, member.id, ctx.author.id, reason
        )

        with suppress(discord.HTTPException):
            await member.send(
                embed=warning_dm_embed(ctx.guild.name, reason, warning_id)
            )

        log.info(
            "Warned %s (%s) in %s by %s (#%s): %s",
            member, member.id, ctx.guild.id, ctx.author, warning_id, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member warned",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=(
                    f"Warning **#{warning_id}** saved. Check their record with "
                    f"`{ctx.prefix}warnings {member.id}`."
                ),
                icon="warn",
                color=discord.Color.yellow())
        )

    @bot.command(
        name="warnings",
        aliases=["warns"],
        help="Show a member's latest warnings.",
        usage="warnings <user>")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warnings_cmd(ctx: commands.Context, user: discord.User) -> None:
        rows = await warnings.list_warnings(ctx.bot.db, ctx.guild.id, user.id)
        total = len(rows)
        if not total:
            await ctx.send(
                embed=moderation_embed(
                    "No warnings",
                    target=_target(user),
                    moderator=ctx.author,
                    details=f"{user.mention} has a clean record.",
                    icon="warnings",
                    color=discord.Color.green())
            )
            return

        entries = []
        for row in reversed(rows[-WARN_PAGE_SIZE:]):
            moderator = ctx.guild.get_member(row["moderator_id"])
            entries.append(
                (
                    row["id"],
                    moderator.mention if moderator else f"`{row['moderator_id']}`",
                    row["reason"],
                    warnings.parse_created(row["created_at"]))
            )
        await ctx.send(embed=warnings_embed(user, entries=entries, total=total))

    @bot.command(
        name="delwarn",
        aliases=["removewarn"],
        help="Delete one warning by its number.",
        usage="delwarn <warning id>")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def delwarn(ctx: commands.Context, warning_id: int) -> None:
        row = await warnings.delete_warning(ctx.bot.db, ctx.guild.id, warning_id)
        if row is None:
            await ctx.send(
                embed=error_embed(f"Warning **#{warning_id}** doesn't exist.")
            )
            return

        target = f"<@{row['user_id']}> (`{row['user_id']}`)"
        log.info(
            "Deleted warning #%s in %s by %s", warning_id, ctx.guild.id, ctx.author
        )
        await ctx.send(
            embed=moderation_embed(
                "Warning deleted",
                target=target,
                moderator=ctx.author,
                reason=row["reason"],
                details=f"Warning **#{warning_id}** was removed from the record.",
                icon="delwarn",
                color=discord.Color.green())
        )

    @bot.command(
        name="clearwarns",
        help="Delete every warning for a member.",
        usage="clearwarns <user>")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def clearwarns(ctx: commands.Context, user: discord.User) -> None:
        cleared = await warnings.clear_warnings(ctx.bot.db, ctx.guild.id, user.id)
        if not cleared:
            await ctx.send(
                embed=error_embed(f"{user.mention} has no warnings to clear.")
            )
            return

        log.info(
            "Cleared %s warnings for %s (%s) in %s by %s",
            cleared, user, user.id, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Warnings cleared",
                target=_target(user),
                moderator=ctx.author,
                details=(
                    f"Removed **{cleared}** warning"
                    f"{'s' if cleared != 1 else ''} from {user.mention}'s record."
                ),
                icon="clearwarns",
                color=discord.Color.green())
        )

    @bot.command(
        name="role",
        help="Add or remove a role from a member.",
        usage="role <member> <role>")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def role(
        ctx: commands.Context, member: discord.Member, *, role: discord.Role
    ) -> None:
        if role.is_default():
            await ctx.send(embed=error_embed("The @everyone role can't be assigned."))
            return
        if role.managed:
            await ctx.send(
                embed=error_embed(
                    f"{role.mention} is managed by an integration, so I can't assign it."
                )
            )
            return

        me = ctx.guild.me
        if me is None or role >= me.top_role:
            await ctx.send(
                embed=error_embed(
                    f"I can't assign {role.mention} — move my role above it."
                )
            )
            return
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            await ctx.send(
                embed=error_embed(
                    f"{role.mention} is equal to or higher than your highest role."
                )
            )
            return

        reason = f"Requested by {ctx.author}"
        try:
            # The cached member can be stale (roles changed outside the bot or
            # no member events), which used to flip the toggle the wrong way.
            member = await ctx.guild.fetch_member(member.id)
        except discord.HTTPException:
            await ctx.send(
                embed=error_embed(
                    f"I couldn't load {member.mention}'s current roles — try again."
                )
            )
            return
        adding = member.get_role(role.id) is None
        try:
            if adding:
                await member.add_roles(role, reason=reason)
            else:
                await member.remove_roles(role, reason=reason)
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the change: {exc}"))
            return

        log.info(
            "%s role %s (%s) %s in %s by %s",
            "Added" if adding else "Removed",
            role.name, role.id,
            "to" if adding else "from",
            member, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Role added" if adding else "Role removed",
                target=_target(member),
                moderator=ctx.author,
                details=(
                    f"{member.mention} now has {role.mention}."
                    if adding
                    else f"{member.mention} no longer has {role.mention}."
                ),
                icon="role")
        )

    @bot.command(
        name="nick",
        aliases=["setnick"],
        help="Change a member's nickname, or reset it with no name.",
        usage="nick <member> [name]")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nick(
        ctx: commands.Context, member: discord.Member, *, name: str | None = None
    ) -> None:
        if ctx.bot.user is not None and member.id == ctx.bot.user.id:
            await ctx.send(embed=error_embed("I can't change my own nickname."))
            return
        if member.id == ctx.guild.owner_id:
            await ctx.send(
                embed=error_embed("The server owner's nickname can't be changed.")
            )
            return
        me = ctx.guild.me
        if me is None or member.top_role >= me.top_role:
            await ctx.send(
                embed=error_embed(
                    f"I can't rename {member.mention} — move my role above theirs."
                )
            )
            return

        nickname = discord.utils.escape_markdown(name.strip()) if name else None
        if nickname is not None and len(nickname) > NICK_MAX:
            nickname = nickname[: NICK_MAX - 1] + "…"
        if nickname == member.nick:
            await ctx.send(embed=error_embed("That's already their nickname."))
            return

        try:
            await member.edit(nick=nickname, reason=f"Renamed by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the rename: {exc}"))
            return

        log.info(
            "Renamed %s (%s) to %r in %s by %s",
            member, member.id, nickname, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Nickname reset" if nickname is None else "Nickname changed",
                target=_target(member),
                moderator=ctx.author,
                details=(
                    f"{member.mention}'s nickname was reset."
                    if nickname is None
                    else f"{member.mention} is now **{nickname}**."
                ),
                icon="nick",
                color=discord.Color.green() if nickname is None else None)
        )

    @bot.command(
        name="move",
        help="Move a member to another voice channel.",
        usage="move <member> <voice channel>")
    @commands.guild_only()
    @commands.has_permissions(move_members=True)
    async def move(
        ctx: commands.Context, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        problem = _voice_problem(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        current = member.voice.channel
        if current.id == channel.id:
            await ctx.send(
                embed=error_embed(f"{member.mention} is already in {channel.mention}.")
            )
            return

        try:
            await member.move_to(channel, reason=f"Moved by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the move: {exc}"))
            return

        log.info(
            "Moved %s (%s) from #%s to #%s in %s by %s",
            member, member.id, current.name, channel.name, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Member moved",
                target=_target(member),
                moderator=ctx.author,
                details=(
                    f"{member.mention} was moved from {current.mention} "
                    f"to {channel.mention}."
                ),
                icon="move")
        )

    @bot.command(
        name="vmute",
        help="Server-mute a member in voice channels.",
        usage="vmute <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(mute_members=True)
    async def vmute(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _voice_problem(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if member.voice.mute:
            await ctx.send(
                embed=error_embed(f"{member.mention} is already server-muted.")
            )
            return

        reason = reason or f"Voice muted by {ctx.author}"
        try:
            await member.edit(mute=True, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the mute: {exc}"))
            return

        log.info(
            "Voice-muted %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member voice-muted",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} can't speak in voice channels.",
                icon="vmute",
                color=discord.Color.red())
        )

    @bot.command(
        name="vunmute",
        help="Remove a voice server-mute.",
        usage="vunmute <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(mute_members=True)
    async def vunmute(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _voice_problem(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if not member.voice.mute:
            await ctx.send(embed=error_embed(f"{member.mention} isn't voice-muted."))
            return

        reason = reason or f"Voice unmuted by {ctx.author}"
        try:
            await member.edit(mute=False, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the unmute: {exc}"))
            return

        log.info(
            "Voice-unmuted %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member voice-unmuted",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} can speak in voice again.",
                icon="vunmute",
                color=discord.Color.green())
        )

    @bot.command(
        name="vdeafen",
        help="Server-deafen a member in voice channels.",
        usage="vdeafen <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(deafen_members=True)
    async def vdeafen(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _voice_problem(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if member.voice.deaf:
            await ctx.send(
                embed=error_embed(f"{member.mention} is already server-deafened.")
            )
            return

        reason = reason or f"Voice deafened by {ctx.author}"
        try:
            await member.edit(deafen=True, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the deafen: {exc}"))
            return

        log.info(
            "Voice-deafened %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member voice-deafened",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} can't hear voice channels.",
                icon="vdeafen",
                color=discord.Color.red())
        )

    @bot.command(
        name="vundeafen",
        help="Remove a voice server-deafen.",
        usage="vundeafen <member> [reason]")
    @commands.guild_only()
    @commands.has_permissions(deafen_members=True)
    async def vundeafen(
        ctx: commands.Context, member: discord.Member, *, reason: str | None = None
    ) -> None:
        problem = _voice_problem(ctx, member)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if not member.voice.deaf:
            await ctx.send(
                embed=error_embed(f"{member.mention} isn't server-deafened.")
            )
            return

        reason = reason or f"Voice undeafened by {ctx.author}"
        try:
            await member.edit(deafen=False, reason=f"{reason} — {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the undeafen: {exc}"))
            return

        log.info(
            "Voice-undeafened %s (%s) in %s by %s: %s",
            member, member.id, ctx.guild.id, ctx.author, reason)
        await ctx.send(
            embed=moderation_embed(
                "Member voice-undeafened",
                target=_target(member),
                moderator=ctx.author,
                reason=reason,
                details=f"{member.mention} can hear voice channels again.",
                icon="vundeafen",
                color=discord.Color.green())
        )

    @bot.command(
        name="lock",
        help="Stop @everyone from sending messages in this channel.",
        usage="lock")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lock(ctx: commands.Context) -> None:
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("This channel can't be locked."))
            return

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is False:
            await ctx.send(embed=error_embed("This channel is already locked."))
            return

        overwrite.send_messages = False
        overwrite.send_messages_in_threads = False
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Locked by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the lock: {exc}"))
            return

        log.info(
            "Locked #%s (%s) in %s by %s",
            channel.name, channel.id, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Channel locked",
                target=channel.mention,
                moderator=ctx.author,
                details=(
                    f"**@everyone** can no longer send messages in "
                    f"{channel.mention}."
                ),
                icon="lock",
                color=discord.Color.orange())
        )

    @bot.command(
        name="unlock",
        help="Let @everyone send messages in this channel again.",
        usage="unlock")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlock(ctx: commands.Context) -> None:
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("This channel can't be unlocked."))
            return

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is not False:
            await ctx.send(embed=error_embed("This channel isn't locked."))
            return

        overwrite.send_messages = None
        overwrite.send_messages_in_threads = None
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Unlocked by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the unlock: {exc}"))
            return

        log.info(
            "Unlocked #%s (%s) in %s by %s",
            channel.name, channel.id, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Channel unlocked",
                target=channel.mention,
                moderator=ctx.author,
                details=(
                    f"**@everyone** can send messages in {channel.mention} again."
                ),
                icon="unlock",
                color=discord.Color.green())
        )

    @bot.command(
        name="lockdown",
        help="Lock every text channel so @everyone can't send messages.",
        usage="lockdown [reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def lockdown(ctx: commands.Context, *, reason: str | None = None) -> None:
        reason = reason or f"Server lockdown by {ctx.author}"
        locked = 0
        failed = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is False:
                continue
            overwrite.send_messages = False
            overwrite.send_messages_in_threads = False
            try:
                await channel.set_permissions(
                    ctx.guild.default_role, overwrite=overwrite, reason=reason
                )
                locked += 1
            except discord.HTTPException:
                failed += 1

        log.info("Lockdown in %s by %s: %s locked, %s failed", ctx.guild.id, ctx.author, locked, failed)
        await ctx.send(
            embed=moderation_embed(
                "Server locked down",
                target=ctx.guild.name,
                moderator=ctx.author,
                reason=reason,
                details=(
                    f"Locked **{locked}** channel{'s' if locked != 1 else ''}."
                    + (f" **{failed}** couldn't be changed." if failed else "")
                ),
                icon="lock",
                color=discord.Color.red())
        )

    @bot.command(
        name="unlockdown",
        help="Let @everyone send messages in every text channel again.",
        usage="unlockdown [reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def unlockdown(ctx: commands.Context, *, reason: str | None = None) -> None:
        reason = reason or f"Server unlocked by {ctx.author}"
        unlocked = 0
        failed = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is not False:
                continue
            overwrite.send_messages = None
            overwrite.send_messages_in_threads = None
            try:
                await channel.set_permissions(
                    ctx.guild.default_role, overwrite=overwrite, reason=reason
                )
                unlocked += 1
            except discord.HTTPException:
                failed += 1

        log.info("Unlockdown in %s by %s: %s unlocked, %s failed", ctx.guild.id, ctx.author, unlocked, failed)
        await ctx.send(
            embed=moderation_embed(
                "Server unlocked",
                target=ctx.guild.name,
                moderator=ctx.author,
                reason=reason,
                details=(
                    f"Unlocked **{unlocked}** channel{'s' if unlocked != 1 else ''}."
                    + (f" **{failed}** couldn't be changed." if failed else "")
                ),
                icon="unlock",
                color=discord.Color.green())
        )

    @bot.command(
        name="massban",
        help="Ban up to 20 users by ID in one go.",
        usage="massban <user id> [user id ...]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massban(ctx: commands.Context, *user_ids: int) -> None:
        if not user_ids:
            await ctx.send(embed=error_embed("Give at least one user ID."))
            return
        if len(user_ids) > 20:
            await ctx.send(embed=error_embed("You can ban at most **20** users at once."))
            return

        banned: list[int] = []
        skipped: list[str] = []
        for user_id in dict.fromkeys(user_ids):
            user = discord.Object(id=user_id)
            member = ctx.guild.get_member(user_id)
            blocker = _ban_blocker(ctx, member or user)
            if blocker:
                skipped.append(f"`{user_id}`: {blocker}")
                continue
            try:
                antinuke_state.record_bot_action(ctx.guild.id, "ban", ctx.author.id)
                await ctx.guild.ban(
                    user, reason=f"Mass ban — {ctx.author}"
                )
                banned.append(user_id)
            except discord.HTTPException as exc:
                skipped.append(f"`{user_id}`: {exc}")

        log.info("Massban in %s by %s: %s banned", ctx.guild.id, ctx.author, len(banned))
        details = f"Banned **{len(banned)}** user{'s' if len(banned) != 1 else ''}."
        if skipped:
            details += "\n\nSkipped:\n" + "\n".join(skipped[:10])
        await ctx.send(
            embed=moderation_embed(
                "Mass ban",
                target=ctx.guild.name,
                moderator=ctx.author,
                details=details,
                icon="ban",
                color=discord.Color.red())
        )

    @bot.command(
        name="massrole",
        help="Give or remove a role for every member who has another role (or everyone).",
        usage="massrole <add|remove> <role> [has role]")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def massrole(
        ctx: commands.Context,
        action: str,
        role: discord.Role,
        has_role: discord.Role | None = None) -> None:
        action = action.lower()
        if action not in {"add", "remove"}:
            await ctx.send(embed=error_embed("Action must be `add` or `remove`."))
            return
        if role.is_default() or role.managed:
            await ctx.send(embed=error_embed(f"I can't assign {role.mention}."))
            return
        me = ctx.guild.me
        if me is None or role >= me.top_role:
            await ctx.send(
                embed=error_embed(f"I can't assign {role.mention} — move my role above it.")
            )
            return
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            await ctx.send(
                embed=error_embed(f"{role.mention} is equal to or higher than your highest role.")
            )
            return

        reason = f"Mass role {action} by {ctx.author}"
        changed = 0
        failed = 0
        async for member in ctx.guild.fetch_members(limit=None):
            if member.bot:
                continue
            if has_role is not None and member.get_role(has_role.id) is None:
                continue
            if (action == "add") == (member.get_role(role.id) is not None):
                continue
            try:
                if action == "add":
                    await member.add_roles(role, reason=reason)
                else:
                    await member.remove_roles(role, reason=reason)
                changed += 1
            except discord.HTTPException:
                failed += 1

        log.info("Massrole %s %s in %s by %s: %s changed", action, role.id, ctx.guild.id, ctx.author, changed)
        await ctx.send(
            embed=moderation_embed(
                "Mass role update",
                target=role.mention,
                moderator=ctx.author,
                details=(
                    f"{'Added' if action == 'add' else 'Removed'} {role.mention} for "
                    f"**{changed}** member{'s' if changed != 1 else ''}."
                    + (f" **{failed}** failed." if failed else "")
                ),
                icon="role")
        )

    @bot.command(
        name="hide",
        help="Hide this channel from @everyone.",
        usage="hide")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def hide(ctx: commands.Context) -> None:
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("This channel can't be hidden."))
            return

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.view_channel is False:
            await ctx.send(embed=error_embed("This channel is already hidden."))
            return

        overwrite.view_channel = False
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Hidden by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the change: {exc}"))
            return

        log.info("Hid #%s (%s) in %s by %s", channel.name, channel.id, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Channel hidden",
                target=channel.mention,
                moderator=ctx.author,
                details=f"{channel.mention} is hidden from **@everyone**.",
                icon="lock",
                color=discord.Color.orange())
        )

    @bot.command(
        name="unhide",
        help="Make this channel visible to @everyone again.",
        usage="unhide")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unhide(ctx: commands.Context) -> None:
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("This channel can't be unhidden."))
            return

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.view_channel is not False:
            await ctx.send(embed=error_embed("This channel isn't hidden."))
            return

        overwrite.view_channel = None
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Unhidden by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the change: {exc}"))
            return

        log.info("Unhid #%s (%s) in %s by %s", channel.name, channel.id, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Channel visible",
                target=channel.mention,
                moderator=ctx.author,
                details=f"{channel.mention} is visible to **@everyone** again.",
                icon="unlock",
                color=discord.Color.green())
        )

    @bot.command(
        name="masskick",
        help="Kick up to 20 members by mention or ID in one go.",
        usage="masskick <member> [member ...]")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def masskick(ctx: commands.Context, *members: discord.Member) -> None:
        if not members:
            await ctx.send(embed=error_embed("Give at least one member."))
            return
        if len(members) > 20:
            await ctx.send(embed=error_embed("You can kick at most **20** members at once."))
            return

        kicked = 0
        skipped: list[str] = []
        for member in dict.fromkeys(members):
            problem = _hierarchy(ctx, member)
            if problem:
                skipped.append(f"{member.mention}: {problem}")
                continue
            try:
                antinuke_state.record_bot_action(ctx.guild.id, "kick", ctx.author.id)
                await member.kick(reason=f"Mass kick — {ctx.author}")
                kicked += 1
            except discord.HTTPException as exc:
                skipped.append(f"{member.mention}: {exc}")

        log.info("Masskick in %s by %s: %s kicked", ctx.guild.id, ctx.author, kicked)
        details = f"Kicked **{kicked}** member{'s' if kicked != 1 else ''}."
        if skipped:
            details += "\n\nSkipped:\n" + "\n".join(skipped[:10])
        await ctx.send(
            embed=moderation_embed(
                "Mass kick",
                target=ctx.guild.name,
                moderator=ctx.author,
                details=details,
                icon="ban",
                color=discord.Color.red())
        )

    @bot.command(
        name="massunban",
        help="Lift bans for up to 20 users by ID in one go.",
        usage="massunban <user id> [user id ...]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massunban(ctx: commands.Context, *user_ids: int) -> None:
        if not user_ids:
            await ctx.send(embed=error_embed("Give at least one user ID."))
            return
        if len(user_ids) > 20:
            await ctx.send(embed=error_embed("You can unban at most **20** users at once."))
            return

        unbanned = 0
        skipped: list[str] = []
        for user_id in dict.fromkeys(user_ids):
            try:
                await ctx.guild.unban(
                    discord.Object(id=user_id), reason=f"Mass unban — {ctx.author}"
                )
                unbanned += 1
            except discord.NotFound:
                skipped.append(f"`{user_id}`: isn't banned")
            except discord.HTTPException as exc:
                skipped.append(f"`{user_id}`: {exc}")

        log.info("Massunban in %s by %s: %s unbanned", ctx.guild.id, ctx.author, unbanned)
        details = f"Unbanned **{unbanned}** user{'s' if unbanned != 1 else ''}."
        if skipped:
            details += "\n\nSkipped:\n" + "\n".join(skipped[:10])
        await ctx.send(
            embed=moderation_embed(
                "Mass unban",
                target=ctx.guild.name,
                moderator=ctx.author,
                details=details,
                icon="unban",
                color=discord.Color.green())
        )

    @bot.command(
        name="purge",
        aliases=["clear"],
        help="Bulk-delete up to 100 recent messages, optionally from one member.",
        usage="purge <count> [member]")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(
        ctx: commands.Context, count: int, member: discord.Member | None = None
    ) -> None:
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(embed=error_embed("This channel doesn't hold messages."))
            return
        if not 1 <= count <= PURGE_LIMIT:
            await ctx.send(
                embed=error_embed(f"Count must be between 1 and {PURGE_LIMIT}.")
            )
            return

        purge_kwargs = {"reason": f"Purge by {ctx.author}"}
        if member is not None:
            purge_kwargs["check"] = lambda message: message.author.id == member.id
        try:
            deleted = await ctx.channel.purge(limit=count, **purge_kwargs)
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the purge: {exc}"))
            return

        detail = f"Deleted **{len(deleted)}** message{'s' if len(deleted) != 1 else ''}"
        if member is not None:
            detail += f" from {member.mention}"
        await ctx.send(
            embed=moderation_embed(
                "Messages purged",
                target=ctx.channel.mention,
                moderator=ctx.author,
                details=detail + ".",
                icon="purge",
                color=SUCCESS_COLOR),
            delete_after=6)

    @bot.command(
        name="slowmode",
        help="Set slowmode: 10s, 1m, 1h or off.",
        usage="slowmode <duration|off>")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(ctx: commands.Context, duration: str) -> None:
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(embed=error_embed("This channel doesn't support slowmode."))
            return
        lowered = duration.lower()
        seconds = 0 if lowered in {"off", "none", "clear", "0"} else _parse_duration(lowered)
        if seconds is None:
            await ctx.send(
                embed=error_embed("Use a duration like `10s`, `1m`, `1h` or `off`.")
            )
            return
        if seconds > MAX_SLOWMODE:
            await ctx.send(embed=error_embed("Slowmode can be at most `6h`."))
            return

        try:
            await ctx.channel.edit(
                slowmode_delay=seconds, reason=f"Requested by {ctx.author}"
            )
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the change: {exc}"))
            return

        text = (
            f"Slowmode is off in {ctx.channel.mention}."
            if seconds == 0
            else f"Slowmode set to **{_duration_text(seconds)}** in {ctx.channel.mention}."
        )
        await ctx.send(
            embed=moderation_embed(
                "Slowmode updated",
                target=ctx.channel.mention,
                moderator=ctx.author,
                details=text,
                icon="slowmode",
                color=SUCCESS_COLOR)
        )

    @bot.command(
        name="pin",
        help="Pin a message in this channel by its ID.",
        usage="pin <message id>")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def pin(ctx: commands.Context, message_id: int) -> None:
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(embed=error_embed("This channel doesn't hold messages."))
            return
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(
                embed=error_embed(f"No message with ID `{message_id}` in this channel.")
            )
            return
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the lookup: {exc}"))
            return
        if message.pinned:
            await ctx.send(embed=error_embed("That message is already pinned."))
            return

        try:
            await message.pin(reason=f"Pinned by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the pin: {exc}"))
            return

        log.info(
            "Pinned message %s in #%s (%s) by %s",
            message.id, ctx.channel.name, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Message pinned",
                target=f"[Jump]({message.jump_url})",
                moderator=ctx.author,
                details=(
                    f"{message.author.mention}'s message was pinned "
                    f"in {ctx.channel.mention}."
                ),
                icon="pin",
                color=discord.Color.green())
        )

    @bot.command(
        name="unpin",
        help="Unpin a message in this channel by its ID.",
        usage="unpin <message id>")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def unpin(ctx: commands.Context, message_id: int) -> None:
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(embed=error_embed("This channel doesn't hold messages."))
            return
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(
                embed=error_embed(f"No message with ID `{message_id}` in this channel.")
            )
            return
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the lookup: {exc}"))
            return
        if not message.pinned:
            await ctx.send(embed=error_embed("That message isn't pinned."))
            return

        try:
            await message.unpin(reason=f"Unpinned by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the unpin: {exc}"))
            return

        log.info(
            "Unpinned message %s in #%s (%s) by %s",
            message.id, ctx.channel.name, ctx.guild.id, ctx.author)
        await ctx.send(
            embed=moderation_embed(
                "Message unpinned",
                target=f"[Jump]({message.jump_url})",
                moderator=ctx.author,
                details=(
                    f"{message.author.mention}'s message was unpinned "
                    f"in {ctx.channel.mention}."
                ),
                icon="unpin")
        )

    @bot.command(
        name="nuke",
        help="Delete this channel and recreate it in place, wiping every message.",
        usage="nuke")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(ctx: commands.Context) -> None:
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
            await ctx.send(
                embed=error_embed("Only text and voice channels can be nuked.")
            )
            return
        if await _nuke_blocked(ctx):
            await ctx.send(
                embed=error_embed(
                    "Antinuke is on and you are not on its whitelist, so I will "
                    "not wipe this channel. Ask an admin to run "
                    f"`{ctx.prefix}antinuke whitelist add @you` first."
                )
            )
            return

        async def confirm(interaction: discord.Interaction) -> None:
            try:
                clone = await channel.clone(reason=f"Nuked by {ctx.author}")
            except discord.HTTPException as exc:
                await interaction.followup.send(
                    embed=error_embed(
                        f"Discord refused to recreate the channel: {exc}"
                    )
                )
                return

            # clone() copies settings but not position, so put it back in place.
            with suppress(discord.HTTPException):
                await clone.edit(
                    position=channel.position, reason=f"Nuked by {ctx.author}"
                )

            try:
                antinuke_state.record_bot_action(
                    ctx.guild.id, "channel_delete", ctx.author.id
                )
                await channel.delete(reason=f"Nuked by {ctx.author}")
            except discord.HTTPException as exc:
                with suppress(discord.HTTPException):
                    await clone.delete(
                        reason="Rollback: original channel could not be deleted"
                    )
                await interaction.followup.send(
                    embed=error_embed(
                        f"Discord refused to delete the old channel: {exc}"
                    )
                )
                return

            log.info(
                "Nuked #%s (%s) in %s by %s",
                channel.name, channel.id, ctx.guild.id, ctx.author)
            with suppress(discord.HTTPException):
                await clone.send(
                    embed=moderation_embed(
                        "Channel nuked",
                        target=f"#{clone.name}",
                        moderator=ctx.author,
                        details=(
                            "The channel was recreated in place and all messages "
                            "were removed."
                        ),
                        icon="nuke",
                        color=discord.Color.red())
                )

        view = NukeConfirmView(ctx.author, confirm)
        view.message = await ctx.send(embed=nuke_confirm_embed(channel), view=view)
