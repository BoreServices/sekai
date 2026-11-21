import asyncio
import io
import logging
from contextlib import suppress

import aiohttp
import discord
from discord.ext import commands

from src.welcome import images, state
from view import (
    error_embed,
    info_embed,
    leave_embed,
    render_member_card,
    run_render,
    success_embed,
    welcome_embed)

log = logging.getLogger("sekai.welcome")

PLACEHOLDERS = "`{user}`, `{name}`, `{server}` and `{count}`"
OFF_VALUES = {"off", "none", "disable", "clear"}
COLOR_RESET = {"default", "reset", "off", "none"}
BACKGROUND_OFF = {"off", "none", "remove", "reset", "clear"}


def _config(guild_id: int) -> state.WelcomeConfig:
    return state.get(guild_id) or state.WelcomeConfig()


def _show_embed(ctx: commands.Context) -> discord.Embed:
    config = _config(ctx.guild.id)

    def channel(value: int | None) -> str:
        return f"<#{value}>" if value else "off"

    role = ctx.guild.get_role(config.autorole_id) if config.autorole_id else None
    return info_embed(
        title="Welcome, goodbye & autorole",
        description=f"Placeholders: {PLACEHOLDERS}.",
        fields=[
            ("👋 Welcome channel", channel(config.welcome_channel), True),
            ("🚪 Goodbye channel", channel(config.leave_channel), True),
            ("🎭 Autorole", role.mention if role else "off", True),
            (
                "🖼️ Card images",
                f"Welcome: {'on' if config.welcome_card_enabled else 'off'} · "
                f"Goodbye: {'on' if config.leave_card_enabled else 'off'}",
                True),
            (
                "Welcome message",
                f"`{config.welcome_message or state.DEFAULT_WELCOME}`",
                False),
            (
                "Goodbye message",
                f"`{config.leave_message or state.DEFAULT_LEAVE}`",
                False),
            (
                "Commands",
                "`welcome channel [#channel]` · `welcome message <text>` · "
                "`welcome off` · `welcome card` · `goodbye channel [#channel]` · "
                "`goodbye message <text>` · `goodbye off` · `goodbye card` · "
                "`autorole [role|off]`",
                False),
        ])


def _role_problem(guild: discord.Guild, role: discord.Role) -> str | None:
    me = guild.me
    if role.is_default():
        return "You can't assign @everyone."
    if role.managed:
        return "That role belongs to an integration and can't be assigned."
    if me is None or not me.guild_permissions.manage_roles:
        return "I need the Manage Roles permission to assign that role."
    if role >= me.top_role:
        return "Move my role above that one first."
    return None


async def _avatar(user: discord.abc.User) -> bytes | None:
    try:
        return await user.display_avatar.replace(size=256, format="png").read()
    except (discord.HTTPException, aiohttp.ClientError):
        return None


async def _render_card(
    guild: discord.Guild, member: discord.Member, *, leaving: bool
) -> bytes:
    config = _config(guild.id)
    avatar_bytes = await _avatar(member)
    return await run_render(
        render_member_card,
        display_name=member.display_name,
        guild_name=guild.name,
        member_count=guild.member_count,
        avatar_bytes=avatar_bytes,
        leaving=leaving,
        accent=state.accent_rgb(config, leaving=leaving),
        background_path=state.background_path(config, guild.id, leaving=leaving))


async def _card_file(
    guild: discord.Guild, member: discord.Member, *, leaving: bool
) -> discord.File | None:
    kind = "goodbye" if leaving else "welcome"
    try:
        png = await _render_card(guild, member, leaving=leaving)
    except Exception:
        log.exception("Could not render the %s card in %s", kind, guild.id)
        return None
    return discord.File(io.BytesIO(png), filename=f"{kind}-card.png")


async def _announce(
    channel: discord.TextChannel,
    embed: discord.Embed,
    member: discord.Member,
    *,
    leaving: bool) -> None:
    file = None
    config = _config(member.guild.id)
    if state.card_enabled(config, leaving=leaving):
        file = await _card_file(member.guild, member, leaving=leaving)
    if file is not None:
        try:
            await channel.send(embed=embed, file=file)
            return
        except discord.HTTPException:
            log.warning(
                "Could not send the %s card to %s",
                "goodbye" if leaving else "welcome",
                channel.id)
        finally:
            file.close()
    with suppress(discord.HTTPException):
        await channel.send(embed=embed)


async def _send_preview(
    ctx: commands.Context, *, leaving: bool, note: str | None = None
) -> None:
    kind = "goodbye" if leaving else "welcome"
    file = await _card_file(ctx.guild, ctx.author, leaving=leaving)
    if file is None:
        await ctx.send(
            embed=error_embed("I couldn't render that card — try again.")
        )
        return
    if note:
        embed = success_embed(note, icon="🖼️")
    else:
        embed = info_embed(
            title=f"{kind.title()} card preview",
            description=(
                f"Change it with `{kind} card color <#hex>` or "
                f"`{kind} card background`."
            ),
            fields=[])
    embed.set_image(url=f"attachment://{kind}-card.png")
    try:
        await ctx.send(embed=embed, file=file)
    except discord.HTTPException:
        log.warning("Could not send a card preview in %s", ctx.guild.id)
    finally:
        file.close()


def _card_embed(ctx: commands.Context, *, leaving: bool) -> discord.Embed:
    config = _config(ctx.guild.id)
    kind = "goodbye" if leaving else "welcome"
    color = (
        config.leave_card_color if leaving else config.welcome_card_color
    )
    default = "#ED4245" if leaving else "#57F287"
    background = config.leave_card_bg if leaving else config.welcome_card_bg
    custom_background = bool(background) and (
        state.background_path(config, ctx.guild.id, leaving=leaving) is not None
    )
    return info_embed(
        title=f"{kind.title()} card image",
        description=(
            f"Attached to every {kind} message. Changes show a preview right "
            "away."
        ),
        fields=[
            (
                "🖼️ Image",
                "on" if state.card_enabled(config, leaving=leaving) else "off",
                True),
            ("🎨 Accent", color or f"{default} (default)", True),
            (
                "🌄 Background",
                "custom image" if custom_background else "default gradient",
                True),
            (
                "Commands",
                f"`{kind} card preview` · `{kind} card color <#hex|reset>` · "
                f"`{kind} card background [image url|off]` · "
                f"`{kind} card on` · `{kind} card off`",
                False),
        ])


async def _set_card_color(
    bot, ctx: commands.Context, *, leaving: bool, value: str
) -> None:
    kind = "goodbye" if leaving else "welcome"
    if value.strip().lower() in COLOR_RESET:
        color = None
    else:
        color = state.parse_color(value)
        if color is None:
            await ctx.send(
                embed=error_embed(
                    "Use a hex color like `#9B59B6`, or `reset` for the default."
                )
            )
            return
    config = _config(ctx.guild.id)
    if leaving:
        config.leave_card_color = color
    else:
        config.welcome_card_color = color
    await state.save(bot, ctx.guild.id, config)
    await _send_preview(
        ctx,
        leaving=leaving,
        note=f"{kind.title()} card accent set to {color or 'the default'}.")


async def _set_card_background(
    bot, ctx: commands.Context, *, leaving: bool, value: str | None
) -> None:
    kind = "goodbye" if leaving else "welcome"
    config = _config(ctx.guild.id)
    attachments = ctx.message.attachments
    attachment = next(
        (
            item
            for item in attachments
            if (item.content_type or "").startswith("image/")
        ),
        None)
    if attachment is None and attachments:
        attachment = attachments[0]

    if attachment is None and value and value.strip().lower() in BACKGROUND_OFF:
        await images.delete(ctx.guild.id, leaving=leaving)
        if leaving:
            config.leave_card_bg = None
        else:
            config.welcome_card_bg = None
        await state.save(bot, ctx.guild.id, config)
        await _send_preview(
            ctx,
            leaving=leaving,
            note="Background removed — back to the default gradient.")
        return

    if attachment is None and not value:
        await ctx.send(
            embed=info_embed(
                title=f"{kind.title()} card background",
                description=(
                    "Attach a PNG, JPG, WebP or GIF to this command, paste a "
                    "direct image link, or use `off` to go back to the default "
                    "gradient."
                ),
                fields=[])
        )
        return

    try:
        if attachment is not None:
            data = await images.from_attachment(attachment)
        else:
            data = await images.from_url(value.strip())
        filename = await images.save(ctx.guild.id, leaving=leaving, data=data)
    except images.BackgroundError as exc:
        await ctx.send(embed=error_embed(str(exc)))
        return
    except (aiohttp.ClientError, asyncio.TimeoutError):
        await ctx.send(embed=error_embed("I couldn't download that image."))
        return

    if leaving:
        config.leave_card_bg = filename
    else:
        config.welcome_card_bg = filename
    await state.save(bot, ctx.guild.id, config)
    await _send_preview(
        ctx, leaving=leaving, note="Background saved — preview below."
    )


async def _toggle_card(
    bot, ctx: commands.Context, *, leaving: bool, enabled: bool
) -> None:
    kind = "goodbye" if leaving else "welcome"
    config = _config(ctx.guild.id)
    if leaving:
        config.leave_card_enabled = enabled
    else:
        config.welcome_card_enabled = enabled
    await state.save(bot, ctx.guild.id, config)
    if enabled:
        await _send_preview(
            ctx, leaving=leaving, note=f"{kind.title()} card images are on."
        )
    else:
        await ctx.send(
            embed=success_embed(
                f"{kind.title()} card images are off — messages will be "
                "text only.",
                icon="🖼️")
        )


def setup(bot) -> None:
    @bot.listen("on_ready")
    async def load_welcome() -> None:
        if not state._loaded:
            await state.load_state(bot)

    @bot.listen("on_member_join")
    async def greet_member(member: discord.Member) -> None:
        if member.bot:
            return
        if not state._loaded:
            await state.load_state(bot)
        config = state.get(member.guild.id)
        if config is None:
            return

        if config.autorole_id is not None:
            role = member.guild.get_role(config.autorole_id)
            if role is not None and _role_problem(member.guild, role) is None:
                try:
                    await member.add_roles(role, reason="Autorole")
                except discord.HTTPException as exc:
                    log.warning(
                        "Could not give autorole %s to %s: %s", role.id, member, exc
                    )

        if config.welcome_channel is None:
            return
        channel = member.guild.get_channel(config.welcome_channel)
        if not isinstance(channel, discord.TextChannel):
            return
        text = state.render(
            config.welcome_message or state.DEFAULT_WELCOME,
            member,
            member.guild.member_count)
        await _announce(
            channel, welcome_embed(member, text), member, leaving=False
        )

    @bot.listen("on_member_remove")
    async def say_goodbye(member: discord.Member) -> None:
        if member.bot:
            return
        if not state._loaded:
            await state.load_state(bot)
        config = state.get(member.guild.id)
        if config is None or config.leave_channel is None:
            return
        channel = member.guild.get_channel(config.leave_channel)
        if not isinstance(channel, discord.TextChannel):
            return
        text = state.render(
            config.leave_message or state.DEFAULT_LEAVE,
            member,
            member.guild.member_count)
        await _announce(
            channel, leave_embed(member, text), member, leaving=True
        )

    @bot.group(
        name="welcome",
        help="Welcome messages and the role new members receive.",
        usage="welcome",
        invoke_without_command=True)
    @commands.guild_only()
    async def welcome(ctx: commands.Context) -> None:
        await ctx.send(embed=_show_embed(ctx))

    @welcome.command(
        name="channel",
        help="Set the welcome channel (defaults to this one).",
        usage="welcome channel [#channel]")
    @commands.has_permissions(manage_guild=True)
    async def welcome_channel(
        ctx: commands.Context, channel: discord.TextChannel | None = None
    ) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("Pick a text channel."))
            return
        config = _config(ctx.guild.id)
        config.welcome_channel = channel.id
        if config.welcome_message is None:
            config.welcome_message = state.DEFAULT_WELCOME
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(
            embed=success_embed(
                f"Welcome messages will be posted in {channel.mention}.",
                icon="👋")
        )

    @welcome.command(
        name="message",
        help="Set the welcome message template.",
        usage="welcome message <text>")
    @commands.has_permissions(manage_guild=True)
    async def welcome_message(ctx: commands.Context, *, text: str) -> None:
        if len(text) > state.MAX_MESSAGE:
            await ctx.send(
                embed=error_embed(
                    f"Keep the message under {state.MAX_MESSAGE} characters."
                )
            )
            return
        config = _config(ctx.guild.id)
        config.welcome_message = text.strip()
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(
            embed=success_embed(f"Welcome message saved. Placeholders: {PLACEHOLDERS}.")
        )

    @welcome.command(
        name="off",
        help="Stop posting welcome messages.",
        usage="welcome off")
    @commands.has_permissions(manage_guild=True)
    async def welcome_off(ctx: commands.Context) -> None:
        config = _config(ctx.guild.id)
        config.welcome_channel = None
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(embed=success_embed("Welcome messages are off.", icon="👋"))

    @welcome.group(
        name="card",
        help="Custom image attached to welcome messages.",
        usage="welcome card",
        invoke_without_command=True)
    @commands.guild_only()
    async def welcome_card(ctx: commands.Context) -> None:
        await ctx.send(embed=_card_embed(ctx, leaving=False))

    @welcome_card.command(
        name="preview",
        help="Preview the welcome card image.",
        usage="welcome card preview")
    @commands.guild_only()
    async def welcome_card_preview(ctx: commands.Context) -> None:
        await _send_preview(ctx, leaving=False)

    @welcome_card.command(
        name="color",
        help="Set the welcome card accent colour (hex, or reset).",
        usage="welcome card color <#hex|reset>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_card_color(ctx: commands.Context, *, value: str) -> None:
        await _set_card_color(bot, ctx, leaving=False, value=value)

    @welcome_card.command(
        name="background",
        help="Upload or link a PNG/JPG/WebP background for the welcome card.",
        usage="welcome card background [image url|off]")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_card_background(
        ctx: commands.Context, url: str | None = None
    ) -> None:
        await _set_card_background(bot, ctx, leaving=False, value=url)

    @welcome_card.command(
        name="on",
        help="Attach the welcome card image again.",
        usage="welcome card on")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_card_on(ctx: commands.Context) -> None:
        await _toggle_card(bot, ctx, leaving=False, enabled=True)

    @welcome_card.command(
        name="off",
        help="Stop attaching the welcome card image.",
        usage="welcome card off")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_card_off(ctx: commands.Context) -> None:
        await _toggle_card(bot, ctx, leaving=False, enabled=False)

    @bot.group(
        name="goodbye",
        help="Messages posted when a member leaves.",
        usage="goodbye",
        invoke_without_command=True)
    @commands.guild_only()
    async def goodbye(ctx: commands.Context) -> None:
        await ctx.send(embed=_show_embed(ctx))

    @goodbye.command(
        name="channel",
        help="Set the goodbye channel (defaults to this one).",
        usage="goodbye channel [#channel]")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_channel(
        ctx: commands.Context, channel: discord.TextChannel | None = None
    ) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=error_embed("Pick a text channel."))
            return
        config = _config(ctx.guild.id)
        config.leave_channel = channel.id
        if config.leave_message is None:
            config.leave_message = state.DEFAULT_LEAVE
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(
            embed=success_embed(
                f"Goodbye messages will be posted in {channel.mention}.", icon="🚪"
            )
        )

    @goodbye.command(
        name="message",
        help="Set the goodbye message template.",
        usage="goodbye message <text>")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_message(ctx: commands.Context, *, text: str) -> None:
        if len(text) > state.MAX_MESSAGE:
            await ctx.send(
                embed=error_embed(
                    f"Keep the message under {state.MAX_MESSAGE} characters."
                )
            )
            return
        config = _config(ctx.guild.id)
        config.leave_message = text.strip()
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(
            embed=success_embed(f"Goodbye message saved. Placeholders: {PLACEHOLDERS}.")
        )

    @goodbye.command(
        name="off",
        help="Stop posting goodbye messages.",
        usage="goodbye off")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_off(ctx: commands.Context) -> None:
        config = _config(ctx.guild.id)
        config.leave_channel = None
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(embed=success_embed("Goodbye messages are off.", icon="🚪"))

    @goodbye.group(
        name="card",
        help="Custom image attached to goodbye messages.",
        usage="goodbye card",
        invoke_without_command=True)
    @commands.guild_only()
    async def goodbye_card(ctx: commands.Context) -> None:
        await ctx.send(embed=_card_embed(ctx, leaving=True))

    @goodbye_card.command(
        name="preview",
        help="Preview the goodbye card image.",
        usage="goodbye card preview")
    @commands.guild_only()
    async def goodbye_card_preview(ctx: commands.Context) -> None:
        await _send_preview(ctx, leaving=True)

    @goodbye_card.command(
        name="color",
        help="Set the goodbye card accent colour (hex, or reset).",
        usage="goodbye card color <#hex|reset>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def goodbye_card_color(ctx: commands.Context, *, value: str) -> None:
        await _set_card_color(bot, ctx, leaving=True, value=value)

    @goodbye_card.command(
        name="background",
        help="Upload or link a PNG/JPG/WebP background for the goodbye card.",
        usage="goodbye card background [image url|off]")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def goodbye_card_background(
        ctx: commands.Context, url: str | None = None
    ) -> None:
        await _set_card_background(bot, ctx, leaving=True, value=url)

    @goodbye_card.command(
        name="on",
        help="Attach the goodbye card image again.",
        usage="goodbye card on")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def goodbye_card_on(ctx: commands.Context) -> None:
        await _toggle_card(bot, ctx, leaving=True, enabled=True)

    @goodbye_card.command(
        name="off",
        help="Stop attaching the goodbye card image.",
        usage="goodbye card off")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def goodbye_card_off(ctx: commands.Context) -> None:
        await _toggle_card(bot, ctx, leaving=True, enabled=False)

    @bot.command(
        name="autorole",
        help="Role given to new members automatically.",
        usage="autorole [role|off]")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def autorole(ctx: commands.Context, *, value: str | None = None) -> None:
        config = _config(ctx.guild.id)
        if value is None:
            role = (
                ctx.guild.get_role(config.autorole_id)
                if config.autorole_id
                else None
            )
            description = (
                f"New members receive {role.mention}."
                if role is not None
                else "Autorole is off."
            )
            await ctx.send(
                embed=info_embed(title="Autorole", description=description, fields=[])
            )
            return

        if value.strip().lower() in OFF_VALUES:
            config.autorole_id = None
            await state.save(bot, ctx.guild.id, config)
            await ctx.send(embed=success_embed("Autorole is off.", icon="👋"))
            return

        role = state.resolve_role(ctx.guild, value)
        if role is None:
            await ctx.send(
                embed=error_embed(
                    "I couldn't find that role — mention it, use its ID or type "
                    "the exact name."
                )
            )
            return
        problem = _role_problem(ctx.guild, role)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return

        config.autorole_id = role.id
        await state.save(bot, ctx.guild.id, config)
        await ctx.send(
            embed=success_embed(f"New members will receive {role.mention}.", icon="👋")
        )
