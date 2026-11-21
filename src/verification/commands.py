import logging
import time
from contextlib import suppress

import discord
from discord.ext import commands, tasks

from config.settings import settings
from core import guild_logs
from src.verification import state
from view import (
    VerifyLinkView,
    VerifyPanelView,
    error_embed,
    info_embed,
    raid_alert_embed,
    success_embed,
    verify_dm_embed,
    verify_kick_embed,
    verify_link_embed,
    verify_panel_embed,
    verify_settings_embed)

log = logging.getLogger("sekai.verification")

OFF_VALUES = {"off", "none", "clear", "disable", "0"}


def _role(guild: discord.Guild, role_id: int | None) -> str:
    if role_id is None:
        return "off"
    role = guild.get_role(role_id)
    return role.mention if role is not None else "*deleted role*"


def _website_status(bot) -> str:
    base = (settings.verify_base_url or settings.website_url).strip()
    if state.website_configured(bot):
        return f"[{base}]({base}) · ready"
    return (
        f"{base or 'not set'} · "
        "**client secret missing** (`config/token.py`)"
    )


def _panel_link(guild: discord.Guild, config: state.VerifyConfig) -> str:
    if not config.panel_channel_id or not config.panel_message_id:
        return "not posted"
    url = (
        f"https://discord.com/channels/{guild.id}/"
        f"{config.panel_channel_id}/{config.panel_message_id}"
    )
    return f"[Message]({url})"


async def _settings_embed(bot, guild: discord.Guild, config: state.VerifyConfig):
    raid = "off"
    if config.raid_mode:
        raid = (
            "on (manual)"
            if config.raid_until <= 0
            else f"auto-locked until <t:{config.raid_until}:R>"
        )
    embed = verify_settings_embed(
        label=guild.name,
        verified_role=_role(guild, config.verified_role_id),
        unverified_role=_role(guild, config.unverified_role_id),
        panel=_panel_link(guild, config),
        website=_website_status(bot),
        account_days=config.min_account_days,
        raid=raid,
        threshold=config.raid_threshold,
        window=config.raid_window,
        verified_members=await state.verified_count(bot, guild.id))
    if not state.website_configured(bot):
        embed.add_field(
            name="Website not ready",
            value=(
                "1. Developer Portal → OAuth2 → Client Secret → paste into "
                "`DISCORD_CLIENT_SECRET` in `config/token.py`.\n"
                "2. OAuth2 → Redirects → add "
                f"`{settings.verify_redirect_uri}`.\n"
                "3. Restart the bot."
            ),
            inline=False)
    return embed


def _kick_allowed(guild: discord.Guild) -> bool:
    me = guild.me
    return me is not None and me.guild_permissions.kick_members


async def _give_role(
    member: discord.Member, role: discord.Role | None, reason: str
) -> None:
    if role is None or role in member.roles:
        return
    with suppress(discord.HTTPException):
        await member.add_roles(role, reason=reason)


async def _remove_role(
    member: discord.Member, role: discord.Role | None, reason: str
) -> None:
    if role is None or role not in member.roles:
        return
    with suppress(discord.HTTPException):
        await member.remove_roles(role, reason=reason)


async def handle_join(bot, member: discord.Member) -> None:
    """Apply the verification gate to a new member."""
    if member.bot:
        return
    guild = member.guild
    config = await state.get_config(bot, guild.id)
    if config is None or not config.enabled:
        return

    verified_role = (
        guild.get_role(config.verified_role_id)
        if config.verified_role_id
        else None
    )
    unverified_role = (
        guild.get_role(config.unverified_role_id)
        if config.unverified_role_id
        else None
    )

    if await state.is_verified(bot, guild.id, member.id):
        await _give_role(member, verified_role, "Returning verified member")
        await _remove_role(member, unverified_role, "Verified")
        return

    if config.min_account_days > 0:
        age = state.account_age_days(member)
        if age < config.min_account_days:
            if not _kick_allowed(guild):
                log.warning(
                    "Cannot enforce the account-age gate in %s: missing "
                    "Kick Members",
                    guild.id)
            else:
                try:
                    await member.kick(
                        reason=(
                            f"Account younger than "
                            f"{config.min_account_days} days "
                            "(verification gate)"
                        )
                    )
                except discord.HTTPException as exc:
                    log.warning(
                        "Could not kick young account %s in %s: %s",
                        member.id,
                        guild.id,
                        exc)
                else:
                    await guild_logs.send_log(
                        bot,
                        guild,
                        "moderation",
                        verify_kick_embed(
                            member, required_days=config.min_account_days
                        ))
                    return

    joins = state.record_join(guild.id, window=config.raid_window)
    if joins >= config.raid_threshold and not config.raid_mode:
        until = int(time.time()) + state.RAID_LOCK_SECONDS
        await state.set_raid(bot, guild.id, True, until=until)
        config.raid_mode = True
        config.raid_until = until
        await guild_logs.send_log(
            bot,
            guild,
            "moderation",
            raid_alert_embed(
                guild,
                joins=joins,
                window=config.raid_window,
                minutes=state.RAID_LOCK_SECONDS // 60,
                automatic=True))
        log.warning(
            "Raid mode enabled in %s after %s joins in %ss",
            guild.id,
            joins,
            config.raid_window)
    elif config.raid_mode:
        await state.extend_raid(bot, config)

    await _give_role(member, unverified_role, "Verification required")

    if not state.website_configured(bot):
        log.warning(
            "Verification is enabled in %s but the OAuth2 client secret "
            "is missing",
            guild.id)
        return

    code = state.new_code(
        guild.id,
        member.id,
        ttl=state.JOIN_CODE_TTL,
        source="join")
    url = state.verify_url(
        code,
        config.url_path if config else None,
        config.custom_domain if config else None)
    try:
        await member.send(
            embed=verify_dm_embed(
                guild, url, hours=state.JOIN_CODE_TTL // 3600
            ),
            view=VerifyLinkView(url))
    except discord.HTTPException:
        # DMs are closed: post the link in the verification channel instead.
        fallback_id = config.verification_channel_id if config else None
        fallback = guild.get_channel(fallback_id) if fallback_id else None
        if isinstance(fallback, discord.TextChannel):
            with suppress(discord.HTTPException):
                await fallback.send(
                    embed=verify_dm_embed(
                        guild, url, hours=state.JOIN_CODE_TTL // 3600
                    ),
                    view=VerifyLinkView(url))
        log.info("Could not DM a verification link to %s", member.id)


def setup(bot) -> None:
    if not getattr(bot, "_verify_view_registered", False):
        bot._verify_view_registered = True
        bot.add_view(VerifyPanelView(bot))

    @bot.listen("on_member_join")
    async def gate_member(member: discord.Member) -> None:
        await handle_join(bot, member)

    @tasks.loop(seconds=30)
    async def raid_expiry() -> None:
        await bot.wait_until_ready()
        now = int(time.time())
        rows = await bot.db.fetchall(
            "SELECT guild_id FROM verify_config "
            "WHERE raid_mode = 1 AND raid_until > 0 AND raid_until <= ?",
            (now,))
        for row in rows:
            await state.set_raid(bot, row["guild_id"], False)
            log.info("Raid mode expired in guild %s", row["guild_id"])

    if not raid_expiry.is_running():
        raid_expiry.start()

    @bot.group(
        name="verify",
        aliases=["verification"],
        help="Website verification, join gating and raid alerts.",
        usage="verify",
        invoke_without_command=True)
    @commands.guild_only()
    async def verify(ctx: commands.Context) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=info_embed(
                    title="Verification",
                    description=(
                        "Require new members to verify through a website before "
                        "they get access. Set the role members receive after "
                        "verifying with `verify setup <role> [unverified role]`, "
                        "then post the button with `verify panel #channel`."
                    ),
                    fields=[
                        (
                            "Commands",
                            "`verify setup <role> [unverified role]`\n"
                            "`verify panel [#channel]` · `verify settings`\n"
                            "`verify accountage <days|off>` · "
                            "`verify raid <on|off>`\n"
                            "`verify unverified <role|off>` · `verify off`\n"
                            "Everyone: `verify link`",
                            False)
                    ])
            )
            return

        await ctx.send(
            embed=info_embed(
                title="Verification",
                description=(
                    "Click **Verify** on the panel, or run `verify link`, to "
                    "get a personal verification page."
                ),
                fields=[
                    (
                        "Status",
                        f"On · verified role {_role(ctx.guild, config.verified_role_id)}",
                        True),
                    ("Website", _website_status(bot), True),
                    (
                        "Staff",
                        "`verify settings` shows the full setup · "
                        "`verify panel` posts the button",
                        False),
                ])
        )

    @verify.command(
        name="setup",
        help="Enable verification and choose the verified role.",
        usage="verify setup <verified role> [unverified role]")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def setup_verify(
        ctx: commands.Context,
        verified: discord.Role,
        unverified: discord.Role | None = None) -> None:
        problem = state.role_problem(ctx.guild, verified)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        if unverified is not None:
            if unverified.id == verified.id:
                await ctx.send(
                    embed=error_embed(
                        "The verified and unverified roles must be different."
                    )
                )
                return
            problem = state.role_problem(ctx.guild, unverified)
            if problem:
                await ctx.send(embed=error_embed(problem))
                return

        config = await state.get_config(bot, ctx.guild.id) or state.VerifyConfig(
            guild_id=ctx.guild.id
        )
        config.verified_role_id = verified.id
        if unverified is not None:
            config.unverified_role_id = unverified.id
        await state.save_config(bot, config)

        fields = [
            ("Verified role", verified.mention, True),
            (
                "Unverified role",
                _role(ctx.guild, config.unverified_role_id),
                True),
            ("Website", _website_status(bot), True),
            (
                "Next steps",
                "1. Post the button panel: `verify panel #channel`\n"
                "2. New members get the unverified role and a DM with the "
                "verification page.\n"
                "3. After verifying they receive the verified role "
                "automatically.",
                False),
        ]
        if not state.website_configured(bot):
            fields.append(
                (
                    "Website setup",
                    "Add the OAuth2 client secret in `config/token.py`, then "
                    f"add `{settings.verify_redirect_uri}` under OAuth2 → "
                    "Redirects in the Developer Portal and restart me.",
                    False)
            )
        await ctx.send(
            embed=info_embed(
                title="Verification enabled",
                description=(
                    "Verification is on. Existing members are left alone; "
                    "remove their access by hand if you want them to verify "
                    "too."
                ),
                fields=fields)
        )

    @verify.command(
        name="panel",
        help="Post the Verify button panel in a channel.",
        usage="verify panel [#channel]")
    @commands.has_permissions(manage_guild=True)
    async def panel(
        ctx: commands.Context, channel: discord.TextChannel | None = None
    ) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        target = channel or ctx.channel
        if config.panel_channel_id and config.panel_message_id:
            old = ctx.guild.get_channel(config.panel_channel_id)
            if isinstance(old, discord.TextChannel):
                with suppress(discord.HTTPException):
                    await old.get_partial_message(
                        config.panel_message_id
                    ).delete()
        try:
            message = await target.send(
                embed=verify_panel_embed(), view=VerifyPanelView(bot)
            )
        except discord.HTTPException as exc:
            log.warning("Could not post verify panel in %s: %s", target.id, exc)
            await ctx.send(
                embed=error_embed(
                    "I couldn't post the panel there — check Send Messages "
                    "and Embed Links."
                )
            )
            return
        config.panel_channel_id = target.id
        config.panel_message_id = message.id
        await state.save_config(bot, config)
        await ctx.send(
            embed=success_embed(f"Verification panel posted in {target.mention}.")
        )

    @verify.command(
        name="link",
        help="Get a personal verification link.",
        usage="verify link")
    @commands.guild_only()
    async def link(ctx: commands.Context) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Verification isn't enabled in this server.")
            )
            return
        if await state.is_verified(bot, ctx.guild.id, ctx.author.id):
            await ctx.send(embed=success_embed("You're already verified."))
            return
        if not state.website_configured(bot):
            await ctx.send(
                embed=error_embed(
                    "The verification website isn't configured yet — ask "
                    "staff to set the OAuth2 client secret and redirect URL."
                )
            )
            return
        if not state.link_limiter.allow(ctx.author.id):
            await ctx.send(
                embed=error_embed(
                    "Give the last link a minute before asking for another."
                )
            )
            return

        code = state.new_code(ctx.guild.id, ctx.author.id)
        url = state.verify_url(
            code,
            config.url_path if config else None,
            config.custom_domain if config else None)
        embed = verify_link_embed(
            url,
            minutes=state.CODE_TTL // 60,
            guild_name=ctx.guild.name)
        try:
            await ctx.author.send(embed=embed, view=VerifyLinkView(url))
        except discord.HTTPException:
            await ctx.send(embed=embed, view=VerifyLinkView(url))
        else:
            await ctx.send(
                embed=success_embed("I sent your verification link in a DM.")
            )

    @verify.command(
        name="settings",
        help="Show verification roles, website and raid status.",
        usage="verify settings")
    @commands.has_permissions(manage_guild=True)
    async def settings_cmd(ctx: commands.Context) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Verification isn't set up in this server.")
            )
            return
        await ctx.send(embed=await _settings_embed(bot, ctx.guild, config))

    @verify.command(
        name="accountage",
        help="Kick accounts younger than N days when they join.",
        usage="verify accountage <days|off>")
    @commands.has_permissions(manage_guild=True)
    async def accountage(ctx: commands.Context, value: str) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        if value.strip().lower() in OFF_VALUES:
            days = 0
        else:
            try:
                days = int(value)
            except ValueError:
                await ctx.send(
                    embed=error_embed(
                        f"Use a whole number of days (1–{state.MAX_ACCOUNT_DAYS}) "
                        "or `off`."
                    )
                )
                return
            if not 1 <= days <= state.MAX_ACCOUNT_DAYS:
                await ctx.send(
                    embed=error_embed(
                        f"Days must be between 1 and {state.MAX_ACCOUNT_DAYS}, "
                        "or `off`."
                    )
                )
                return
        config.min_account_days = days
        await state.save_config(bot, config)
        if days:
            await ctx.send(
                embed=success_embed(
                    f"Accounts younger than **{days} days** will be kicked on "
                    "join. I need **Kick Members** for that."
                )
            )
        else:
            await ctx.send(
                embed=success_embed("The account-age gate is off.")
            )

    @verify.command(
        name="url",
        help="Set a custom verification link path, or `off` for /verify.",
        usage="verify url <path|off>")
    @commands.has_permissions(manage_guild=True)
    async def url_cmd(ctx: commands.Context, value: str) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        if value.strip().lower() in OFF_VALUES:
            config.url_path = None
        else:
            cleaned = state.clean_url_path(value)
            if cleaned is None:
                await ctx.send(
                    embed=error_embed(
                        "Use 3–32 letters, numbers or hyphens (not starting "
                        "with a hyphen), and avoid reserved words like `verify`."
                    )
                )
                return
            config.url_path = cleaned
        await state.save_config(bot, config)
        base = state._verify_base()
        shown = config.url_path or "verify"
        await ctx.send(
            embed=success_embed(
                f"New verification links will use `{base}/{shown}/…`. "
                "Links already sent keep working until they expire."
            )
        )

    @verify.command(
        name="raid",
        help="Force raid mode on or off.",
        usage="verify raid <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def raid(ctx: commands.Context, value: str) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        lowered = value.strip().lower()
        if lowered not in {"on", "off"}:
            await ctx.send(embed=error_embed("Use `verify raid on` or `verify raid off`."))
            return
        enabled = lowered == "on"
        await state.set_raid(bot, ctx.guild.id, enabled)
        config.raid_mode = enabled
        config.raid_until = 0
        if enabled:
            await ctx.send(
                embed=success_embed(
                    "Raid mode is on until you turn it off. New joins are "
                    "gated through verification."
                )
            )
        else:
            await ctx.send(embed=success_embed("Raid mode is off."))

    @verify.command(
        name="unverified",
        help="Set the role new members get before they verify.",
        usage="verify unverified <role|off>")
    @commands.has_permissions(manage_guild=True)
    async def unverified(ctx: commands.Context, *, value: str) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        if value.strip().lower() in OFF_VALUES:
            config.unverified_role_id = None
            await state.save_config(bot, config)
            await ctx.send(embed=success_embed("The unverified role is off."))
            return

        try:
            role = await commands.RoleConverter().convert(ctx, value)
        except commands.BadArgument:
            await ctx.send(
                embed=error_embed("I couldn't find that role — mention it or use its ID.")
            )
            return
        if role.id == config.verified_role_id:
            await ctx.send(
                embed=error_embed(
                    "That's the verified role — pick a different one."
                )
            )
            return
        problem = state.role_problem(ctx.guild, role)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        config.unverified_role_id = role.id
        await state.save_config(bot, config)
        await ctx.send(
            embed=success_embed(
                f"New members now get {role.mention} until they verify."
            )
        )

    @verify.command(
        name="off",
        aliases=["disable"],
        help="Turn verification off in this server.",
        usage="verify off")
    @commands.has_permissions(manage_guild=True)
    async def off(ctx: commands.Context) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Verification is already off in this server.")
            )
            return
        await state.delete_config(bot, ctx.guild.id)
        await ctx.send(
            embed=success_embed(
                "Verification is off. Roles already handed out were left in "
                "place, and the old panel button now says it isn't set up."
            )
        )

    @verify.command(
        name="expire",
        help="Set how long verification lasts before re-verification is needed.",
        usage="verify expire <days|off>")
    @commands.has_permissions(manage_guild=True)
    async def expire(ctx: commands.Context, value: str) -> None:
        config = await state.get_config(bot, ctx.guild.id)
        if config is None or not config.enabled:
            await ctx.send(
                embed=error_embed("Run `verify setup <role>` first.")
            )
            return
        OFF_VALUES = {"off", "none", "clear", "disable", "0"}
        if value.strip().lower() in OFF_VALUES:
            config.expire_days = 0
            await state.save_config(bot, config)
            await ctx.send(
                embed=success_embed("Verification never expires.")
            )
            return
        try:
            days = int(value)
        except ValueError:
            await ctx.send(
                embed=error_embed(
                    f"Use a whole number of days (1–{state.MAX_ACCOUNT_DAYS}) "
                    "or `off`."
                )
            )
            return
        if not 1 <= days <= state.MAX_ACCOUNT_DAYS:
            await ctx.send(
                embed=error_embed(
                    f"Days must be between 1 and {state.MAX_ACCOUNT_DAYS}, "
                    "or `off`."
                )
            )
            return
        config.expire_days = days
        await state.save_config(bot, config)
        await ctx.send(
            embed=success_embed(
                f"Verification will expire after **{days} days**. "
                f"Members will need to re-verify after that."
            )
        )
