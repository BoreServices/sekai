import logging
from contextlib import suppress

import discord
from discord.ext import commands

from core import prefix as prefixes
from src.tempvoice import state
from view.tempvoice.menu import (
    ClaimPromptView,
    TempVoiceMenuView,
    TempVoicePanelView,
    post_menu,
    update_panel)
from view import (
    error_embed,
    success_embed,
    voicemaster_claim_prompt_embed,
    voicemaster_setup_embed)

log = logging.getLogger("sekai.voicemaster")

CATEGORY_NAME = "VoiceMaster"
TRIGGER_NAME = "Join to Create"
MENU_NAME = "voicemaster-menu"


async def _restore_menus(bot) -> None:
    """Recreate the menu channel/message if they vanished while the bot was down."""
    for guild_id, (category_id, trigger_id, _) in list(state._configs.items()):
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue
        trigger = guild.get_channel(trigger_id)
        if not isinstance(trigger, discord.VoiceChannel):
            log.warning(
                "VoiceMaster: trigger %s missing in guild %s", trigger_id, guild_id
            )
            continue

        row = await bot.db.fetchone(
            "SELECT menu_channel_id, menu_message_id FROM tempvoice WHERE guild_id = ?",
            (guild_id))
        if row is None:
            continue

        menu_id = row["menu_channel_id"]
        menu = guild.get_channel(menu_id) if menu_id else None
        if not isinstance(menu, discord.TextChannel):
            category = guild.get_channel(category_id)
            if not isinstance(category, discord.CategoryChannel):
                category = trigger.category
            try:
                menu = await guild.create_text_channel(
                    MENU_NAME,
                    category=category,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            add_reactions=False)
                    },
                    reason="Restoring the VoiceMaster menu")
            except discord.HTTPException as exc:
                log.warning(
                    "VoiceMaster: could not restore menu channel in guild %s: %s",
                    guild_id,
                    exc)
                continue
            state._configs[guild_id] = (category_id, trigger_id, menu.id)
            await bot.db.execute(
                "UPDATE tempvoice SET menu_channel_id = ? WHERE guild_id = ?",
                (menu.id, guild_id))

        message_id = row["menu_message_id"]
        if message_id:
            try:
                await menu.get_partial_message(message_id).fetch()
                continue
            except discord.NotFound:
                pass
            except discord.HTTPException:
                continue

        prefix = await prefixes.get_guild_prefix(bot, guild_id)
        try:
            message = await post_menu(bot, guild, menu, trigger, prefix)
        except discord.HTTPException as exc:
            log.warning(
                "VoiceMaster: could not restore menu in guild %s: %s", guild_id, exc
            )
            continue
        await bot.db.execute(
            "UPDATE tempvoice SET menu_message_id = ? WHERE guild_id = ?",
            (message.id, guild_id))
        log.info("VoiceMaster: restored menu message in guild %s", guild_id)


async def _post_claim_prompt(bot, channel: discord.VoiceChannel) -> None:
    """Tell the members left behind they can take the channel over."""
    previous = state._claim_prompts.get(channel.id)
    if previous is not None:
        with suppress(discord.HTTPException):
            await channel.get_partial_message(previous).delete()
    try:
        message = await channel.send(
            embed=voicemaster_claim_prompt_embed(channel=channel),
            view=ClaimPromptView(bot))
    except discord.HTTPException as exc:
        log.warning(
            "VoiceMaster: could not post claim prompt in %s: %s", channel.id, exc
        )
        return
    state._claim_prompts[channel.id] = message.id


def setup(bot) -> None:
    state.set_panel_hook(lambda channel: update_panel(bot, channel))
    if not getattr(bot, "_tempvoice_view_registered", False):
        bot._tempvoice_view_registered = True
        bot.add_view(TempVoiceMenuView(bot))
        bot.add_view(TempVoicePanelView(bot))
        bot.add_view(ClaimPromptView(bot))

    @bot.listen("on_ready")
    async def load_tempvoice() -> None:
        if not state._loaded:
            await state.load_state(bot)
        if not getattr(bot, "_tempvoice_menus_restored", False):
            bot._tempvoice_menus_restored = True
            await _restore_menus(bot)

    @bot.listen("on_voice_state_update")
    async def tempvoice_voice_state(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState) -> None:
        if member.bot:
            return
        if not state._loaded:
            await state.load_state(bot)
        config = state._configs.get(member.guild.id)
        if (
            config is not None
            and after.channel is not None
            and after.channel.id == config[1]
        ):
            await state.create_temp(bot, member, after.channel)
            return
        if after.channel is not None and after.channel.id in state._owners:
            if state._owners[after.channel.id] == member.id:
                prompt_id = state._claim_prompts.pop(after.channel.id, None)
                if prompt_id is not None:
                    with suppress(discord.HTTPException):
                        await after.channel.get_partial_message(prompt_id).delete()
        if before.channel is not None and before.channel.id in state._owners:
            humans = [occupant for occupant in before.channel.members if not occupant.bot]
            if not humans:
                await state.delete_temp(bot, before.channel)
            elif state._owners[before.channel.id] == member.id:
                await _post_claim_prompt(bot, before.channel)

        if before.channel != after.channel:
            for channel in {before.channel, after.channel}:
                if channel is not None and channel.id in state._owners:
                    state.schedule_refresh(channel)

    @bot.listen("on_guild_channel_delete")
    async def tempvoice_channel_deleted(channel: discord.abc.GuildChannel) -> None:
        if channel.id in state._owners:
            state._owners.pop(channel.id, None)
            await bot.db.execute(
                "DELETE FROM tempvoice_channels WHERE channel_id = ?", (channel.id)
            )

    def owned(ctx: commands.Context) -> discord.VoiceChannel | None:
        voice = getattr(ctx.author, "voice", None)
        channel = voice.channel if voice is not None else None
        if channel is None or state._owners.get(channel.id) != ctx.author.id:
            return None
        return channel

    @bot.group(
        name="voicemaster",
        help="VoiceMaster — join the trigger to get your own voice channel.",
        usage=(
            "voicemaster setup|lock|unlock|hide|unhide|rename <name>|limit <0-99>|claim|"
            "transfer <member>|permit <member>|reject <member>|"
            "bitrate <kbps>|delete"
        ),
        invoke_without_command=True)
    @commands.guild_only()
    async def voicemaster(ctx: commands.Context) -> None:
        await ctx.send(
            embed=error_embed(
                f"Use `{ctx.prefix}voicemaster setup` first, then in your "
                f"channel: `lock`, `unlock`, `hide`, `unhide`, `rename <name>`, "
                f"`limit <0-99>`, `claim`, `transfer <member>`, `permit <member>`, "
                f"`reject <member>`, `bitrate <kbps>` or `delete`."
            )
        )

    @voicemaster.command(
        name="setup",
        help="Create the category, trigger channel and the button menu.",
        usage="voicemaster setup")
    @commands.has_permissions(manage_guild=True)
    async def setup_command(ctx: commands.Context) -> None:
        guild = ctx.guild
        row = await bot.db.fetchone(
            "SELECT category_id, trigger_id, menu_channel_id, menu_message_id "
            "FROM tempvoice WHERE guild_id = ?",
            (guild.id))

        category = None
        trigger = None
        menu = None
        if row is not None:
            candidate = guild.get_channel(row["category_id"])
            if isinstance(candidate, discord.CategoryChannel):
                category = candidate
            candidate = guild.get_channel(row["trigger_id"])
            if isinstance(candidate, discord.VoiceChannel):
                trigger = candidate
            if row["menu_channel_id"]:
                candidate = guild.get_channel(row["menu_channel_id"])
                if isinstance(candidate, discord.TextChannel):
                    menu = candidate

        already = category is not None and trigger is not None
        try:
            if category is None:
                category = await guild.create_category(
                    CATEGORY_NAME, reason=f"VoiceMaster setup by {ctx.author}"
                )
            if trigger is None:
                trigger = await guild.create_voice_channel(
                    TRIGGER_NAME,
                    category=category,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(
                            view_channel=True, connect=True
                        )
                    },
                    reason=f"VoiceMaster setup by {ctx.author}")
            elif trigger.category != category:
                await trigger.edit(
                    category=category,
                    reason="Aligning VoiceMaster trigger with its category")
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    "I need the **Manage Channels** permission to set up "
                    "VoiceMaster channels."
                )
            )
            return

        try:
            if menu is None:
                menu = await guild.create_text_channel(
                    MENU_NAME,
                    category=category,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            add_reactions=False)
                    },
                    reason=f"VoiceMaster menu by {ctx.author}")
        except discord.Forbidden:
            log.warning("VoiceMaster: cannot create menu channel in guild %s", guild.id)
            menu = None

        message = None
        if menu is not None:
            old_message_id = row["menu_message_id"] if row is not None else None
            try:
                message = await post_menu(
                    bot, guild, menu, trigger, ctx.prefix, old_message_id
                )
            except discord.HTTPException as exc:
                log.warning(
                    "VoiceMaster: menu message failed in guild %s: %s", guild.id, exc
                )

        state._configs[guild.id] = (
            category.id,
            trigger.id,
            menu.id if menu is not None else None)
        await bot.db.execute(
            "INSERT INTO tempvoice "
            "(guild_id, category_id, trigger_id, menu_channel_id, menu_message_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "category_id = excluded.category_id, "
            "trigger_id = excluded.trigger_id, "
            "menu_channel_id = excluded.menu_channel_id, "
            "menu_message_id = excluded.menu_message_id, "
            "updated_at = datetime('now')",
            (
                guild.id,
                category.id,
                trigger.id,
                menu.id if menu is not None else None,
                message.id if message is not None else None))
        for channel_id in list(state._owners):
            existing = guild.get_channel(channel_id)
            if isinstance(existing, discord.VoiceChannel):
                state.schedule_refresh(existing)
        log.info(
            "VoiceMaster set up in guild %s (category %s, trigger %s, menu %s)",
            guild.id,
            category.id,
            trigger.id,
            menu.id if menu is not None else "none")
        await ctx.send(
            embed=voicemaster_setup_embed(
                category=category,
                trigger=trigger,
                prefix=ctx.prefix,
                already=already,
                menu=menu)
        )

    @voicemaster.command(
        name="lock",
        help="Stop other members from joining your temporary channel.",
        usage="voicemaster lock")
    async def lock(ctx: commands.Context) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to lock it."
                )
            )
            return
        await state.set_locked(channel, True, reason=f"Locked by {ctx.author}")
        await ctx.send(
            embed=success_embed(f"{channel.mention} is now locked.", icon="🔒")
        )

    @voicemaster.command(
        name="unlock",
        help="Let other members join your temporary channel again.",
        usage="voicemaster unlock")
    async def unlock(ctx: commands.Context) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to unlock it."
                )
            )
            return
        await state.set_locked(channel, False, reason=f"Unlocked by {ctx.author}")
        await ctx.send(
            embed=success_embed(f"{channel.mention} is now unlocked.", icon="🔓")
        )

    @voicemaster.command(
        name="hide",
        help="Hide your temporary channel from the server's channel list.",
        usage="voicemaster hide")
    async def hide(ctx: commands.Context) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to hide it."
                )
            )
            return
        if state.is_hidden(channel):
            await ctx.send(embed=error_embed(f"{channel.mention} is already hidden."))
            return
        await state.set_hidden(channel, True, reason=f"Hidden by {ctx.author}")
        await ctx.send(
            embed=success_embed(
                f"{channel.mention} is now hidden from the server. Only you and "
                "permitted members can see it.",
                icon="🙈")
        )

    @voicemaster.command(
        name="unhide",
        help="Show your hidden temporary channel to the server again.",
        usage="voicemaster unhide")
    async def unhide(ctx: commands.Context) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to unhide it."
                )
            )
            return
        if not state.is_hidden(channel):
            await ctx.send(
                embed=error_embed(f"{channel.mention} is already visible.")
            )
            return
        await state.set_hidden(channel, False, reason=f"Unhidden by {ctx.author}")
        await ctx.send(
            embed=success_embed(
                f"{channel.mention} is visible to everyone again.", icon="👁️"
            )
        )

    @voicemaster.command(
        name="rename",
        help="Rename your temporary channel.",
        usage="voicemaster rename <name>")
    async def rename(ctx: commands.Context, *, name: str) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to rename it."
                )
            )
            return
        name = name.replace("\n", " ").strip()[:100]
        if not name:
            await ctx.send(embed=error_embed("Give the channel a name."))
            return
        await channel.edit(name=name, reason=f"Renamed by {ctx.author}")
        await state.refresh_panel(channel)
        await ctx.send(
            embed=success_embed(
                f"Renamed to **{discord.utils.escape_markdown(name)}**.", icon="✏️"
            )
        )

    @voicemaster.command(
        name="limit",
        help="Cap how many members can join your temporary channel.",
        usage="voicemaster limit <0-99>")
    async def set_limit(ctx: commands.Context, value: int) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to change its limit."
                )
            )
            return
        if not 0 <= value <= state.MAX_USER_LIMIT:
            await ctx.send(
                embed=error_embed(
                    f"Limit must be between 0 and {state.MAX_USER_LIMIT} (0 = unlimited)."
                )
            )
            return
        await channel.edit(user_limit=value, reason=f"Limit set by {ctx.author}")
        await state.refresh_panel(channel)
        text = "unlimited" if value == 0 else f"{value}"
        await ctx.send(
            embed=success_embed(f"User limit set to **{text}**.", icon="👥")
        )

    @voicemaster.command(
        name="claim",
        help="Take over your temporary channel if its owner left.",
        usage="voicemaster claim")
    async def claim(ctx: commands.Context) -> None:
        voice = getattr(ctx.author, "voice", None)
        channel = voice.channel if voice is not None else None
        owner_id = state._owners.get(channel.id) if channel is not None else None
        if channel is None or owner_id is None:
            await ctx.send(
                embed=error_embed("Join a VoiceMaster channel first, then claim it.")
            )
            return
        if owner_id == ctx.author.id:
            await ctx.send(embed=error_embed("You already own this channel."))
            return
        if any(member.id == owner_id for member in channel.members):
            await ctx.send(
                embed=error_embed(
                    "The owner is still in the channel — you can claim it after they leave."
                )
            )
            return
        await state.transfer_owner(
            bot, channel, ctx.author, reason=f"Claimed by {ctx.author}"
        )
        await ctx.send(
            embed=success_embed(f"You now own {channel.mention}.", icon="👑")
        )

    @voicemaster.command(
        name="transfer",
        help="Give your temporary channel to another member.",
        usage="voicemaster transfer <member>")
    async def transfer(ctx: commands.Context, member: discord.Member) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to transfer it."
                )
            )
            return
        if member.bot:
            await ctx.send(
                embed=error_embed("Bots can't own a VoiceMaster channel.")
            )
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You already own this channel."))
            return
        if member not in channel.members:
            await ctx.send(
                embed=error_embed(
                    "They need to be in your channel before you transfer it."
                )
            )
            return
        await state.transfer_owner(
            bot, channel, member, reason=f"Transferred by {ctx.author}"
        )
        await ctx.send(
            embed=success_embed(
                f"{member.mention} now owns {channel.mention}.", icon="🔄"
            )
        )

    @voicemaster.command(
        name="permit",
        help="Let one member join even while your channel is locked.",
        usage="voicemaster permit <member>")
    async def permit(ctx: commands.Context, member: discord.Member) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to permit someone."
                )
            )
            return
        if member.bot:
            await ctx.send(embed=error_embed("Pick a human member."))
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You already own this channel."))
            return
        await state.set_permitted(
            channel, member, True, reason=f"Permitted by {ctx.author}"
        )
        await ctx.send(
            embed=success_embed(
                f"{member.mention} can join {channel.mention}, even while locked.",
                icon="✅")
        )

    @voicemaster.command(
        name="reject",
        help="Disconnect a member and keep them out of your channel.",
        usage="voicemaster reject <member>")
    async def reject(ctx: commands.Context, member: discord.Member) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to reject someone."
                )
            )
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You can't reject yourself."))
            return
        if member not in channel.members:
            await ctx.send(embed=error_embed("They aren't in your channel."))
            return
        await state.set_permitted(
            channel,
            member,
            False,
            reason=f"Rejected by {ctx.author}",
            disconnect=True)
        await ctx.send(
            embed=success_embed(
                f"{member.mention} was removed and can't rejoin.", icon="🚫"
            )
        )

    @voicemaster.command(
        name="bitrate",
        help="Set the audio bitrate of your temporary channel (kbps).",
        usage="voicemaster bitrate <kbps>")
    async def bitrate(ctx: commands.Context, value: int) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to change its bitrate."
                )
            )
            return
        limit = int(channel.guild.bitrate_limit // 1000)
        if not 8 <= value <= limit:
            await ctx.send(
                embed=error_embed(f"Bitrate must be between 8 and {limit} kbps.")
            )
            return
        await channel.edit(
            bitrate=value * 1000, reason=f"Bitrate set by {ctx.author}"
        )
        await state.refresh_panel(channel)
        await ctx.send(
            embed=success_embed(f"Bitrate set to **{value} kbps**.", icon="🎚️")
        )

    @voicemaster.command(
        name="delete",
        aliases=["close"],
        help="Delete your temporary channel now.",
        usage="voicemaster delete")
    async def delete(ctx: commands.Context) -> None:
        channel = owned(ctx)
        if channel is None:
            await ctx.send(
                embed=error_embed(
                    "You need to be in your own VoiceMaster channel to delete it."
                )
            )
            return
        await state.delete_temp(bot, channel)
        await ctx.send(
            embed=success_embed("Your VoiceMaster channel was deleted.", icon="🗑️")
        )
