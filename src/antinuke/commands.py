import logging
from contextlib import suppress

import discord
from discord.ext import commands

from src.antinuke import logger, state
from core.emojis import markup
from view import (
    antinuke_alert_embed,
    antinuke_dm_embed,
    antinuke_history_embed,
    antinuke_status_embed,
    error_embed,
    success_embed)

log = logging.getLogger("sekai.antinuke")

# Audit action -> the key the guard tracks. Anything not in here is ignored.
WATCHED = {
    discord.AuditLogAction.ban: "ban",
    discord.AuditLogAction.kick: "kick",
    discord.AuditLogAction.member_prune: "member_prune",
    discord.AuditLogAction.channel_create: "channel_create",
    discord.AuditLogAction.channel_delete: "channel_delete",
    discord.AuditLogAction.role_create: "role_create",
    discord.AuditLogAction.role_delete: "role_delete",
    discord.AuditLogAction.webhook_create: "webhook_create",
    discord.AuditLogAction.bot_add: "bot_add",
    discord.AuditLogAction.emoji_delete: "emoji_delete",
    discord.AuditLogAction.sticker_delete: "sticker_delete",
    discord.AuditLogAction.guild_update: "guild_update",
}

# Actions that are dangerous enough on their own. A single added bot can nuke a
# server faster than any threshold, so it does not wait for a burst.
INSTANT = {"bot_add"}

# Permissions that make a role worth ripping off a member during "strip".
DANGEROUS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members")

OFF_VALUES = {"off", "none", "disable", "disabled", "clear"}


def _settings(guild_id: int) -> state.Settings:
    return state.get(guild_id) or state.Settings()


def _trusted(guild_id: int) -> list[tuple[int, str]]:
    return sorted(state.entries(guild_id).items())


def _status(
    settings: state.Settings, guild: discord.Guild, bot=None
) -> discord.Embed:
    embed = antinuke_status_embed(
        enabled=settings.enabled,
        threshold=settings.threshold,
        window=settings.window,
        punish=settings.punish,
        alert_channel=settings.alert_channel,
        trusted=_trusted(guild.id),
        log_channel=settings.log_channel)
    problems = _health(guild, bot)
    if problems:
        embed.add_field(
            name=f"{markup('warning', '⚠️')} Guard is not fully armed",
            value="\n".join(f"• {problem}" for problem in problems),
            inline=False)
    else:
        embed.add_field(
            name="Testing",
            value=(
                "The server owner cannot be banned, kicked or stripped by a bot. "
                "Other bots are punished like members, so whitelist the bots you "
                "trust. Test with a second admin account, not your own."
            ),
            inline=False)
    return embed


def _health(guild: discord.Guild, bot=None) -> list[str]:
    """Reasons the guard would silently do nothing, shown in `antinuke`."""
    problems: list[str] = []
    if bot is not None and not bot.intents.moderation:
        problems.append(
            "The bot's **Moderation** intent is off, so Discord never sends the "
            "audit-log events the guard listens to."
        )

    me = guild.me
    if me is None:
        problems.append("I cannot see my own member object in this server.")
        return problems

    permissions = me.guild_permissions
    if not permissions.view_audit_log:
        problems.append(
            "I cannot read the audit log (**View Audit Log** is off), so I cannot "
            "see who deleted, banned or kicked anything."
        )
    if not (
        permissions.ban_members
        or permissions.kick_members
        or permissions.manage_roles
    ):
        problems.append(
            "I cannot punish anyone: I need **Ban Members**, **Kick Members** or "
            "**Manage Roles**."
        )
    # Name the people the guard would actually fail on, instead of a vague
    # warning. A bot at the bottom of an empty hierarchy is harmless; a bot
    # below a hijacked admin is the real problem.
    top = me.top_role.position
    blocked: list[discord.Member] = []
    for member in guild.members:
        if member.id == me.id or member.id == guild.owner_id:
            continue
        if member.top_role.position < top:
            continue
        roles = {role.id for role in member.roles}
        if state.whitelisted(guild.id, member.id, roles):
            continue
        blocked.append(member)
    if blocked:
        names = ", ".join(member.mention for member in blocked[:5])
        if len(blocked) > 5:
            names += f" and {len(blocked) - 5} more"
        problems.append(
            f"{len(blocked)} member(s) have a role at or above mine "
            f"({names}), so Discord will block my bans, kicks and role "
            "changes on them. Move my highest role above theirs."
        )
    return problems


def _describe(events: list[tuple[str, int]]) -> str:
    """Summarise a mixed burst, e.g. `2 × deleted channels · 1 × banned members`."""
    counts: dict[str, int] = {}
    for action, _ in events:
        counts[action] = counts.get(action, 0) + 1
    return " · ".join(
        f"{count} × {state.ACTION_TEXT.get(action, action)}"
        for action, count in counts.items()
    )


def _manage_only():
    """Only the owner or someone already trusted may reconfigure the guard.

    Administrator alone is not enough: a hijacked admin account could otherwise
    run `antinuke disable` and then wipe the server unopposed.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        roles = {role.id for role in getattr(ctx.author, "roles", [])}
        if state.whitelisted(ctx.guild.id, ctx.author.id, roles):
            return True
        raise commands.CheckFailure(
            "Only the server owner or an antinuke-whitelisted member can change "
            "antinuke. Ask the owner to run `antinuke whitelist add` for you."
        )

    return commands.check(predicate)


def _dangerous(role: discord.Role) -> bool:
    permissions = role.permissions
    return permissions.administrator or any(
        getattr(permissions, name) for name in DANGEROUS
    )


async def _strip(actor: discord.Member, reason: str) -> str | None:
    """Take away every role that carries a dangerous permission."""
    me = actor.guild.me
    if me is None:
        return None
    doomed = [
        role
        for role in actor.roles
        if not role.is_default()
        and not role.managed
        and role < me.top_role
        and _dangerous(role)
    ]
    if not doomed:
        return None
    await actor.remove_roles(*doomed, reason=reason)
    names = ", ".join(role.name for role in doomed[:5])
    if len(doomed) > 5:
        names += f" +{len(doomed) - 5} more"
    return f"removed {len(doomed)} dangerous role(s): {names}"


async def _remove_added_bot(
    bot, guild: discord.Guild, target_id: int | None, actor_id: int
) -> tuple[str, bool]:
    """Ban a bot the moment a non-whitelisted account adds it.

    Punishing the inviter alone is not enough: the newly added bot keeps its
    token and can start deleting channels while the inviter is gone. Trusted
    bots must be whitelisted by id *before* they are added.
    """
    if target_id is None or (bot.user is not None and target_id == bot.user.id):
        return ("", True)
    if state.whitelisted(guild.id, target_id, set()):
        return (f"The newly added bot <@{target_id}> is whitelisted, so I left it.", True)

    reason = f"Antinuke: bot added by {actor_id} (not whitelisted)"
    try:
        await guild.ban(discord.Object(id=target_id), reason=reason)
    except discord.HTTPException as exc:
        log.warning(
            "Antinuke: could not ban newly added bot %s in %s: %s",
            target_id,
            guild.id,
            exc)
        return (
            f"I could not ban the newly added bot <@{target_id}> "
            f"({getattr(exc, 'status', None) or exc}). Remove it yourself.",
            False)
    log.info("Antinuke: banned newly added bot %s in %s", target_id, guild.id)
    return (f"The newly added bot <@{target_id}> was **banned**.", True)


async def _punish(
    bot,
    guild: discord.Guild,
    member: discord.Member | None,
    actor_id: int,
    settings: state.Settings,
    events: list[tuple[str, int]],
    extra: tuple[str, bool] | None = None) -> bool:
    """Try the configured punishment, then fall back to anything that still works."""
    summary = _describe(events)
    reason = f"Antinuke: {len(events)} watched actions in {settings.window}s ({summary})"
    me = guild.me
    problem: str | None = None
    undone: str | None = None
    outcome: str | None = None

    order = {
        "ban": ("ban", "kick", "strip"),
        "kick": ("kick", "ban", "strip"),
        "strip": ("strip", "kick", "ban"),
    }.get(settings.punish, ("ban", "kick", "strip"))

    if me is None:
        problem = "I am no longer in the server."
    elif member is None:
        # They already left; a ban by ID still works and stops them rejoining.
        try:
            await guild.ban(discord.Object(id=actor_id), reason=reason)
            outcome = "They were **banned** after leaving the server."
            problem = None
        except discord.HTTPException as exc:
            problem = f"they had already left and the ban failed ({exc.status})."
    elif member.id == guild.owner_id:
        problem = "Discord does not let a bot punish the server owner."
    else:
        # Do not pre-judge the role hierarchy. Discord sometimes allows a ban
        # even when positions look equal (for example managed integration
        # roles), so attempt the punishment and report the real API error.
        for kind in order:
            try:
                if kind == "ban":
                    await guild.ban(member, reason=reason)
                    outcome = "They were **banned**."
                elif kind == "kick":
                    await member.kick(reason=reason)
                    outcome = "They were **kicked**."
                else:
                    undone = await _strip(member, reason)
                    if undone is None:
                        problem = "they had no dangerous roles left to remove."
                        continue
                    outcome = "They were **stripped of their dangerous roles**."
                problem = None
                break
            except discord.HTTPException as exc:
                problem = f"the {kind} failed ({getattr(exc, 'status', None) or exc})."

    if extra is not None:
        text, extra_ok = extra
        if text:
            if extra_ok:
                outcome = f"{outcome}\n{text}" if outcome else text
            else:
                problem = f"{problem}\n{text}" if problem else text

    log.info(
        "Antinuke: %s (%s) %s in %s as %s/%s, %s",
        member or actor_id,
        actor_id,
        summary,
        guild.id,
        settings.punish,
        len(events),
        problem or outcome or "punished")

    alert = antinuke_alert_embed(
        member,
        actor_id=actor_id,
        count=len(events),
        window=settings.window,
        breakdown=summary,
        outcome=outcome,
        problem=problem,
        undone=undone)
    await _post_alert(
        bot,
        guild,
        settings,
        alert,
        actor_id=actor_id,
        actor_name=str(member) if member is not None else None,
        detail=summary,
        outcome=outcome or problem)

    # Best effort: a banned member usually can't be DMed any more.
    if isinstance(member, discord.abc.User):
        with suppress(discord.HTTPException):
            await member.send(
                embed=antinuke_dm_embed(
                    label=summary,
                    punish=settings.punish,
                    reason=reason,
                    problem=problem)
            )
    return problem is None


async def _post_alert(
    bot,
    guild: discord.Guild,
    settings: state.Settings,
    alert: discord.Embed,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    detail: str | None = None,
    outcome: str | None = None) -> None:
    await logger.emit(
        bot,
        guild,
        settings,
        "trigger",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
        outcome=outcome,
        embed=alert,
        alert=True)


async def _guard(bot, entry: discord.AuditLogEntry) -> None:
    guild = entry.guild
    if guild is None:
        return
    if not state._loaded:
        await state.load_state(bot)

    settings = state.get(guild.id)
    if settings is None or not settings.enabled:
        return

    action = WATCHED.get(entry.action)
    if action is None:
        return

    actor_id = entry.user_id or getattr(getattr(entry, "user", None), "id", None)
    if actor_id is None:
        return

    # Actions the *bot* took are credited to whoever ran the command that made
    # the bot do it (p!nuke, p!ban, p!massban, ...). Without this, anyone with a
    # moderation command could wipe the server and the audit log would blame the
    # bot, which is exempt.
    if bot.user is not None and actor_id == bot.user.id:
        invoker = state.bot_actor(guild.id, action)
        if invoker is None:
            return
        actor_id = invoker

    member = guild.get_member(actor_id)
    if member is None:
        with suppress(discord.HTTPException):
            member = await guild.fetch_member(actor_id)

    # Other bots are NOT exempt. A compromised or malicious bot can delete the
    # server just as fast as a member, and this is how most nukes happen. Trusted
    # bots have to be whitelisted (`antinuke whitelist add`) like anyone else;
    # only this bot's own actions are attributed above instead of punished.

    me = guild.me
    if me is None or not me.guild_permissions.view_audit_log:
        log.warning(
            "Antinuke: cannot read the audit log in %s (%s)", guild, guild.id
        )
        return

    # A mass ban writes one entry per victim; the cooldown keeps the guard
    # from punishing the same nuker once per entry.
    if state.punished_recently(guild.id, actor_id):
        return

    role_ids = {role.id for role in member.roles} if member is not None else set()
    if state.whitelisted(guild.id, actor_id, role_ids):
        return

    # `entry.target` can raise for entries whose target id is null, and the id
    # is all we need to remember the burst.
    target_id = getattr(entry, "_target_id", 0) or 0
    recent = state.note(guild.id, actor_id, action, target_id, settings.window)
    needed = 1 if action in INSTANT else settings.threshold
    if len(recent) < needed:
        return

    state.forget(guild.id, actor_id)
    state.mark_punished(guild.id, actor_id)

    # A newly added bot is removed even when the inviter is the owner or cannot
    # be punished: otherwise the malicious bot keeps its token and carries on
    # nuking after the inviter is gone.
    added = None
    if action == "bot_add":
        added = await _remove_added_bot(bot, guild, target_id, actor_id)

    if actor_id == guild.owner_id:
        # Discord lets nobody ban, kick or strip the owner. Still report it so
        # an owner whose account was hijacked finds out immediately.
        log.warning(
            "Antinuke: owner %s (%s) tripped the guard in %s (%s); "
            "Discord does not let a bot punish the owner",
            member or actor_id,
            actor_id,
            guild,
            guild.id)
        problem = (
            "the server owner cannot be banned, kicked or stripped by a bot. "
            "If this was not you, secure the account now."
        )
        outcome = (
            "Not punished: the server owner cannot be banned, kicked or "
            "stripped by a bot."
        )
        if added is not None:
            text, ok = added
            if text:
                if ok:
                    outcome = f"{outcome}\n{text}"
                else:
                    problem = f"{problem}\n{text}"
        alert = antinuke_alert_embed(
            member,
            actor_id=actor_id,
            count=len(recent),
            window=settings.window,
            breakdown=_describe(recent),
            problem=problem)
        await _post_alert(
            bot,
            guild,
            settings,
            alert,
            actor_id=actor_id,
            actor_name=str(member) if member is not None else None,
            detail=_describe(recent),
            outcome=outcome)
        return

    punished = await _punish(
        bot, guild, member, actor_id, settings, recent, extra=added
    )
    if not punished:
        # Do not leave the server unprotected for the full cooldown when the
        # first attempt failed (for example because the bot's role is too low).
        state.mark_punished(guild.id, actor_id, state.RETRY_COOLDOWN)


def setup(bot) -> None:
    health_reported: set[int] = set()

    @bot.listen("on_ready")
    async def load_antinuke() -> None:
        if not state._loaded:
            await state.load_state(bot)
        for guild in bot.guilds:
            settings = state.get(guild.id)
            if settings is None or not settings.enabled:
                continue
            problems = _health(guild, bot)
            if not problems:
                continue
            for problem in problems:
                log.warning(
                    "Antinuke is enabled but not armed in %s (%s): %s",
                    guild,
                    guild.id,
                    problem)
            if guild.id not in health_reported:
                health_reported.add(guild.id)
                await logger.emit(
                    bot,
                    guild,
                    settings,
                    "health",
                    detail="The guard is enabled but cannot act:\n"
                    + "\n".join(f"• {problem}" for problem in problems),
                    outcome="Fix the items above before relying on antinuke.")

    @bot.listen("on_audit_log_entry_create")
    async def antinuke_listener(entry: discord.AuditLogEntry) -> None:
        await _guard(bot, entry)

    @bot.group(
        name="antinuke",
        help="Stop hijacked accounts from wiping the server.",
        usage="antinuke",
        invoke_without_command=True)
    @commands.guild_only()
    async def antinuke(ctx: commands.Context) -> None:
        await ctx.send(embed=_status(_settings(ctx.guild.id), ctx.guild, bot))

    @antinuke.command(
        name="enable",
        help="Turn the antinuke guard on.",
        usage="antinuke enable")
    @_manage_only()
    async def enable(ctx: commands.Context) -> None:
        settings = _settings(ctx.guild.id)
        settings.enabled = True
        await state.save(bot, ctx.guild.id, settings)
        problems = _health(ctx.guild, bot)
        text = (
            f"Antinuke is **on**. Anyone crossing **{settings.threshold}** "
            f"watched actions in **{settings.window}s** gets `{settings.punish}`."
            "\nAdd your staff with `antinuke whitelist add` so they are never "
            "caught by it."
        )
        if problems:
            text += f"\n\n{markup('warning', '⚠️')} **It will not work yet:** " + " ".join(problems)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "enabled",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=(
                f"Enabled at **{settings.threshold}** actions in "
                f"**{settings.window}s**, punishment `{settings.punish}`."
            ),
            outcome=("It will not work yet: " + " ".join(problems)) if problems else None)
        await ctx.send(embed=success_embed(text, icon="🛡️"))

    @antinuke.command(
        name="disable",
        help="Turn the antinuke guard off.",
        usage="antinuke disable")
    @_manage_only()
    async def disable(ctx: commands.Context) -> None:
        settings = _settings(ctx.guild.id)
        settings.enabled = False
        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "disabled",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail="The guard was turned **off**. Watched actions are no longer punished.")
        await ctx.send(embed=success_embed("Antinuke is **off**.", icon="🛡️"))

    @antinuke.command(
        name="threshold",
        help="How many watched actions in the window trigger a punishment.",
        usage="antinuke threshold <2-10>")
    @_manage_only()
    async def threshold(ctx: commands.Context, value: int) -> None:
        if not state.MIN_THRESHOLD <= value <= state.MAX_THRESHOLD:
            await ctx.send(
                embed=error_embed(
                    f"Pick a threshold between {state.MIN_THRESHOLD} and "
                    f"{state.MAX_THRESHOLD}."
                )
            )
            return
        settings = _settings(ctx.guild.id)
        previous = settings.threshold
        settings.threshold = value
        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "threshold",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=f"Trigger threshold: **{previous}** → **{value}** actions.")
        await ctx.send(
            embed=success_embed(
                f"Antinuke now triggers at **{value}** actions in "
                f"{settings.window}s.",
                icon="🛡️")
        )

    @antinuke.command(
        name="window",
        help="How long a burst of actions keeps counting, in seconds.",
        usage="antinuke window <5-60>")
    @_manage_only()
    async def window(ctx: commands.Context, seconds: int) -> None:
        if not state.MIN_WINDOW <= seconds <= state.MAX_WINDOW:
            await ctx.send(
                embed=error_embed(
                    f"Pick a window between {state.MIN_WINDOW} and "
                    f"{state.MAX_WINDOW} seconds."
                )
            )
            return
        settings = _settings(ctx.guild.id)
        previous = settings.window
        settings.window = seconds
        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "window",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=f"Window: **{previous}s** → **{seconds}s**.")
        await ctx.send(
            embed=success_embed(
                f"Antinuke now counts actions over **{seconds}s** "
                f"({settings.threshold} of them is a trigger).",
                icon="🛡️")
        )

    @antinuke.command(
        name="punish",
        help="What happens to whoever trips the guard.",
        usage="antinuke punish <ban|kick|strip>")
    @_manage_only()
    async def punish(ctx: commands.Context, mode: str) -> None:
        lowered = mode.strip().lower()
        if lowered not in state.PUNISHMENTS:
            await ctx.send(
                embed=error_embed("Pick `ban`, `kick` or `strip`.")
            )
            return
        settings = _settings(ctx.guild.id)
        previous = settings.punish
        settings.punish = lowered
        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "punish",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=f"Punishment: **{previous}** → **{lowered}**.")
        await ctx.send(
            embed=success_embed(
                f"Antinuke will now **{lowered}** whoever trips it.",
                icon="🛡️")
        )

    @antinuke.command(
        name="check",
        help="See whether the guard could actually stop a member.",
        usage="antinuke check <member>")
    @_manage_only()
    async def check(ctx: commands.Context, member: discord.Member) -> None:
        me = ctx.guild.me
        role_ids = {role.id for role in member.roles}
        above = me is not None and member.top_role >= me.top_role
        if member.id == ctx.guild.owner_id:
            verdict = (
                "the **server owner**: Discord never lets a bot ban, kick or "
                "strip the owner, so the guard can only send an alert."
            )
            ok = False
        elif state.whitelisted(ctx.guild.id, member.id, role_ids):
            verdict = "**trusted**, so the guard will never punish them."
            ok = True
        elif above:
            verdict = (
                f"**above me**: their top role ({member.top_role.mention}) is at "
                f"or above mine ({me.top_role.mention}), so Discord blocks every "
                "ban, kick and role change I try. "
                + ("Bots are **not** exempt, so moving my role up will let the "
                   "guard stop it." if member.bot else "")
            )
            ok = False
        elif member.bot:
            verdict = (
                "a **bot account**: bots are not exempt, so the guard punishes "
                "it like a member unless it is whitelisted."
            )
            ok = True
        else:
            verdict = "**stoppable**: the guard can ban, kick or strip them."
            ok = True

        text = f"{member.mention} is {verdict}"
        if not _settings(ctx.guild.id).enabled:
            text += f"\n\n{markup('warning', '⚠️')} Antinuke is **disabled** right now."
        problems = _health(ctx.guild, bot)
        if problems:
            text += f"\n\n{markup('warning', '⚠️')} " + " ".join(problems)
        embed = success_embed(text, icon="🛡️") if ok else error_embed(text)
        await ctx.send(embed=embed)

    @antinuke.command(
        name="alert",
        help="Extra channel for antinuke alerts, on top of the log channel.",
        usage="antinuke alert <#channel|off>")
    @_manage_only()
    async def alert(ctx: commands.Context, target: discord.TextChannel | str) -> None:
        settings = _settings(ctx.guild.id)
        if isinstance(target, str):
            if target.strip().lower() not in OFF_VALUES:
                await ctx.send(
                    embed=error_embed(
                        "Mention a channel, or use `off` to fall back to the "
                        "server's log channel."
                    )
                )
                return
            settings.alert_channel = None
            note = "Antinuke alerts go to the server's log channel again."
        else:
            settings.alert_channel = target.id
            note = f"Antinuke alerts also go to {target.mention}."
        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "alert_channel",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=note)
        await ctx.send(embed=success_embed(note, icon="🛡️"))

    @antinuke.command(
        name="logs",
        help="Where antinuke events are posted (history is always stored).",
        usage="antinuke logs <#channel|auto|off>")
    @_manage_only()
    async def logs(ctx: commands.Context, target: str = "") -> None:
        settings = _settings(ctx.guild.id)
        if not target:
            if settings.log_channel == logger.LOG_OFF:
                current = (
                    "**off**. Alerts still go to the moderation log and the "
                    "alert channel; `antinuke history` still works."
                )
            elif settings.log_channel:
                current = f"<#{settings.log_channel}>"
            else:
                current = (
                    "**auto**: `#logs-antinuke` (created by `logs`) if it "
                    "exists, then the moderation log."
                )
            await ctx.send(
                embed=success_embed(
                    f"Antinuke log: {current}", icon="🛡️"
                )
            )
            return

        lowered = target.strip().lower()
        if lowered in {"auto", "default"}:
            settings.log_channel = None
            note = "Antinuke logs will use `#logs-antinuke`, then the moderation log."
        elif lowered in OFF_VALUES:
            settings.log_channel = logger.LOG_OFF
            note = (
                "Antinuke log posts are **off** here. Alerts still go to the "
                "moderation log and alert channel, and `antinuke history` "
                "keeps recording."
            )
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, target)
            except commands.BadArgument:
                await ctx.send(
                    embed=error_embed(
                        "Mention a text channel, or use `auto` / `off`."
                    )
                )
                return
            if channel.guild.id != ctx.guild.id:
                await ctx.send(
                    embed=error_embed("Pick a channel from this server.")
                )
                return
            settings.log_channel = channel.id
            note = f"Antinuke logs go to {channel.mention}."

        await state.save(bot, ctx.guild.id, settings)
        await logger.emit(
            bot,
            ctx.guild,
            settings,
            "log_channel",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=note)
        await ctx.send(embed=success_embed(note, icon="🛡️"))

    @antinuke.command(
        name="history",
        help="Show recent antinuke events (triggers, punishments and changes).",
        usage="antinuke history [page]")
    @_manage_only()
    async def history(ctx: commands.Context, page: int = 1) -> None:
        size = 10
        page = max(1, page)
        total = await state.count_logs(bot, ctx.guild.id)
        rows = await state.recent_logs(
            bot, ctx.guild.id, size, (page - 1) * size
        )
        if not rows and page > 1:
            await ctx.send(
                embed=error_embed(
                    f"There are only {max(1, (total + size - 1) // size)} "
                    "page(s) of history."
                )
            )
            return
        await ctx.send(
            embed=antinuke_history_embed(
                rows, total=total, page=page, page_size=size
            )
        )

    @antinuke.group(
        name="whitelist",
        help="Members and roles the guard never punishes.",
        usage="antinuke whitelist",
        invoke_without_command=True)
    @_manage_only()
    async def whitelist(ctx: commands.Context) -> None:
        await ctx.send(embed=_status(_settings(ctx.guild.id), ctx.guild, bot))

    @whitelist.command(
        name="add",
        help="Trust a member or a role.",
        usage="antinuke whitelist add <member|role>")
    @_manage_only()
    async def whitelist_add(
        ctx: commands.Context, target: discord.Member | discord.Role
    ) -> None:
        kind = "role" if isinstance(target, discord.Role) else "user"
        await state.whitelist_add(
            bot, ctx.guild.id, target.id, kind, ctx.author.id
        )
        await logger.emit(
            bot,
            ctx.guild,
            _settings(ctx.guild.id),
            "whitelist_add",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=(
                f"Trusted {kind} {target.mention} (`{target.id}`). The guard "
                "will not punish them."
            ))
        await ctx.send(
            embed=success_embed(
                f"{target.mention} is now trusted — the guard will never "
                "punish them.",
                icon="🛡️")
        )

    @whitelist.command(
        name="remove",
        help="Stop trusting a member or a role.",
        usage="antinuke whitelist remove <member|role>")
    @_manage_only()
    async def whitelist_remove(
        ctx: commands.Context, target: discord.Member | discord.Role
    ) -> None:
        removed = await state.whitelist_remove(bot, ctx.guild.id, target.id)
        if not removed:
            await ctx.send(
                embed=error_embed(f"{target.mention} is not on the whitelist.")
            )
            return
        await logger.emit(
            bot,
            ctx.guild,
            _settings(ctx.guild.id),
            "whitelist_remove",
            actor_id=ctx.author.id,
            actor_name=str(ctx.author),
            detail=(
                f"Stopped trusting {target.mention} (`{target.id}`). The guard "
                "can punish them again."
            ))
        await ctx.send(
            embed=success_embed(
                f"{target.mention} is no longer trusted.", icon="🛡️"
            )
        )

    @whitelist.command(
        name="list",
        help="Show who the guard leaves alone.",
        usage="antinuke whitelist list")
    @_manage_only()
    async def whitelist_list(ctx: commands.Context) -> None:
        await ctx.send(embed=_status(_settings(ctx.guild.id), ctx.guild, bot))
