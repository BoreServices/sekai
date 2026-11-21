import discord
from discord.ext import commands

from config import logs as cfg
from core import audit
from core.guild_logs import (
    disable_logging,
    is_log_channel,
    send_log,
    setup_logging)
from view import (
    audit_embed,
    automod_embed,
    ban_embed,
    bulk_delete_embed,
    channel_embed,
    command_embed,
    emoji_embed,
    error_embed,
    guild_update_embed,
    invite_embed,
    logging_disabled_embed,
    logging_setup_embed,
    member_join_embed,
    member_leave_embed,
    member_update_embed,
    message_delete_embed,
    message_edit_embed,
    pins_embed,
    presence_embed,
    role_embed,
    scheduled_event_embed,
    stage_embed,
    sticker_embed,
    thread_embed,
    user_update_embed,
    voice_embed,
    webhook_embed)

# Actions already posted by a richer raw-event listener; logging the audit
# entry too would double every ban, channel change, role edit and so on.
_SKIP_AUDIT = {
    "ban",
    "unban",
    "message_delete",
    "message_bulk_delete",
    "message_pin",
    "message_unpin",
    "channel_create",
    "channel_delete",
    "channel_update",
    "overwrite_create",
    "overwrite_update",
    "overwrite_delete",
    "role_create",
    "role_update",
    "role_delete",
    "emoji_create",
    "emoji_update",
    "emoji_delete",
    "sticker_create",
    "sticker_update",
    "sticker_delete",
    "guild_update",
    "webhook_update",
    "invite_create",
    "invite_delete",
    "thread_create",
    "thread_update",
    "thread_delete",
    "member_role_update",
    "member_update",
    "member_move",
    "member_disconnect",
    "automod_block_message",
    "automod_flag_message",
    "automod_timeout_member",
    "automod_quarantine_user",
    "scheduled_event_create",
    "scheduled_event_update",
    "scheduled_event_delete",
    "stage_instance_create",
    "stage_instance_update",
    "stage_instance_delete",
}

def setup(bot) -> None:
    @bot.listen("on_member_join")
    async def member_joined(member: discord.Member) -> None:
        if not cfg.LOG_MEMBERS:
            return
        await send_log(
            bot,
            member.guild,
            "members",
            member_join_embed(member, member.guild.member_count))

    @bot.listen("on_member_remove")
    async def member_left(member: discord.Member) -> None:
        if not cfg.LOG_MEMBERS:
            return
        await send_log(
            bot,
            member.guild,
            "members",
            member_leave_embed(member, member.guild.member_count))

    @bot.listen("on_member_update")
    async def member_updated(
        before: discord.Member, after: discord.Member
    ) -> None:
        if not cfg.LOG_MEMBERS:
            return
        await send_log(
            bot, after.guild, "members", member_update_embed(before, after)
        )

    @bot.listen("on_user_update")
    async def user_updated(
        before: discord.User, after: discord.User
    ) -> None:
        if not (cfg.LOGGING_ENABLED and cfg.LOG_MEMBERS):
            return
        embed = user_update_embed(before, after)
        if embed is None:
            return
        for guild in bot.guilds:
            if guild.get_member(after.id) is None:
                continue
            await send_log(bot, guild, "members", embed)

    @bot.listen("on_message_edit")
    async def message_edited(
        before: discord.Message, after: discord.Message
    ) -> None:
        if not cfg.LOG_MESSAGES or after.guild is None:
            return
        if await is_log_channel(bot, after.channel):
            return
        await send_log(
            bot, after.guild, "messages", message_edit_embed(before, after)
        )

    @bot.listen("on_message_delete")
    async def message_deleted(message: discord.Message) -> None:
        if not cfg.LOG_MESSAGES or message.guild is None:
            return
        if await is_log_channel(bot, message.channel):
            return
        await send_log(
            bot, message.guild, "messages", message_delete_embed(message)
        )

    @bot.listen("on_bulk_message_delete")
    async def messages_deleted(messages: list[discord.Message]) -> None:
        if not cfg.LOG_MESSAGES or not messages:
            return
        channel = messages[0].channel
        if channel.guild is None or await is_log_channel(bot, channel):
            return
        await send_log(
            bot, channel.guild, "messages", bulk_delete_embed(channel, messages)
        )

    @bot.listen("on_guild_channel_create")
    async def channel_created(channel: discord.abc.GuildChannel) -> None:
        if not cfg.LOG_CHANNELS or await is_log_channel(bot, channel):
            return
        entry = await audit.wait_for_entry(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )
        await send_log(
            bot,
            channel.guild,
            "channels",
            channel_embed("create", channel, entry=entry))

    @bot.listen("on_guild_channel_delete")
    async def channel_deleted(channel: discord.abc.GuildChannel) -> None:
        if not cfg.LOG_CHANNELS or await is_log_channel(bot, channel):
            return
        entry = await audit.wait_for_entry(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )
        await send_log(
            bot,
            channel.guild,
            "channels",
            channel_embed("delete", channel, entry=entry))

    @bot.listen("on_guild_channel_update")
    async def channel_updated(
        before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        if not cfg.LOG_CHANNELS or await is_log_channel(bot, after):
            return
        if channel_embed("update", after, before, after) is None:
            return
        entry = await audit.wait_for_entry(
            after.guild, discord.AuditLogAction.channel_update, after.id
        )
        await send_log(
            bot,
            after.guild,
            "channels",
            channel_embed("update", after, before, after, entry=entry))

    @bot.listen("on_guild_role_create")
    async def role_created(role: discord.Role) -> None:
        if not cfg.LOG_ROLES:
            return
        entry = await audit.wait_for_entry(
            role.guild, discord.AuditLogAction.role_create, role.id
        )
        await send_log(bot, role.guild, "roles", role_embed("create", role, entry=entry))

    @bot.listen("on_guild_role_delete")
    async def role_deleted(role: discord.Role) -> None:
        if not cfg.LOG_ROLES:
            return
        entry = await audit.wait_for_entry(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )
        await send_log(bot, role.guild, "roles", role_embed("delete", role, entry=entry))

    @bot.listen("on_guild_role_update")
    async def role_updated(before: discord.Role, after: discord.Role) -> None:
        if not cfg.LOG_ROLES:
            return
        if role_embed("update", after, before, after) is None:
            return
        entry = await audit.wait_for_entry(
            after.guild, discord.AuditLogAction.role_update, after.id
        )
        await send_log(
            bot,
            after.guild,
            "roles",
            role_embed("update", after, before, after, entry=entry))

    @bot.listen("on_guild_update")
    async def guild_updated(
        before: discord.Guild, after: discord.Guild
    ) -> None:
        if not cfg.LOG_SERVER:
            return
        await send_log(
            bot, after, "server", guild_update_embed(before, after)
        )

    @bot.listen("on_member_ban")
    async def member_banned(guild: discord.Guild, user: discord.User) -> None:
        if not cfg.LOG_SERVER:
            return
        entry = await audit.wait_for_entry(
            guild, discord.AuditLogAction.ban, user.id
        )
        await send_log(
            bot, guild, "moderation", ban_embed("ban", user, entry=entry)
        )

    @bot.listen("on_member_unban")
    async def member_unbanned(guild: discord.Guild, user: discord.User) -> None:
        if not cfg.LOG_SERVER:
            return
        entry = await audit.wait_for_entry(
            guild, discord.AuditLogAction.unban, user.id
        )
        await send_log(
            bot, guild, "moderation", ban_embed("unban", user, entry=entry)
        )

    @bot.listen("on_webhooks_update")
    async def webhooks_updated(channel: discord.abc.GuildChannel) -> None:
        if not cfg.LOG_SERVER:
            return
        await send_log(bot, channel.guild, "server", webhook_embed(channel))

    @bot.listen("on_voice_state_update")
    async def voice_updated(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState) -> None:
        if not cfg.LOG_VOICE:
            return
        await send_log(
            bot, member.guild, "voice", voice_embed(before, after, member)
        )

    @bot.listen("on_invite_create")
    async def invite_created(invite: discord.Invite) -> None:
        if not cfg.LOG_INVITES or invite.guild is None:
            return
        await send_log(
            bot, invite.guild, "server", invite_embed("create", invite)
        )

    @bot.listen("on_invite_delete")
    async def invite_deleted(invite: discord.Invite) -> None:
        if not cfg.LOG_INVITES or invite.guild is None:
            return
        await send_log(
            bot, invite.guild, "server", invite_embed("delete", invite)
        )

    @bot.listen("on_thread_create")
    async def thread_created(thread: discord.Thread) -> None:
        if not cfg.LOG_THREADS:
            return
        entry = await audit.wait_for_entry(
            thread.guild, discord.AuditLogAction.thread_create, thread.id
        )
        await send_log(
            bot,
            thread.guild,
            "threads",
            thread_embed("create", thread, entry=entry))

    @bot.listen("on_thread_delete")
    async def thread_deleted(thread: discord.Thread) -> None:
        if not cfg.LOG_THREADS:
            return
        entry = await audit.wait_for_entry(
            thread.guild, discord.AuditLogAction.thread_delete, thread.id
        )
        await send_log(
            bot,
            thread.guild,
            "threads",
            thread_embed("delete", thread, entry=entry))

    @bot.listen("on_thread_update")
    async def thread_updated(
        before: discord.Thread, after: discord.Thread
    ) -> None:
        if not cfg.LOG_THREADS:
            return
        if thread_embed("update", after, before, after) is None:
            return
        entry = await audit.wait_for_entry(
            after.guild, discord.AuditLogAction.thread_update, after.id
        )
        await send_log(
            bot,
            after.guild,
            "threads",
            thread_embed("update", after, before, after, entry=entry))

    @bot.listen("on_guild_emojis_update")
    async def emojis_updated(
        guild: discord.Guild,
        before: list[discord.Emoji],
        after: list[discord.Emoji]) -> None:
        if not cfg.LOG_EMOJIS:
            return
        before_map = {emoji.id: emoji for emoji in before}
        after_map = {emoji.id: emoji for emoji in after}
        for emoji_id, emoji in after_map.items():
            old = before_map.get(emoji_id)
            if old is None:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.emoji_create, emoji_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    emoji_embed("create", emoji, entry=entry))
            elif old.name != emoji.name:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.emoji_update, emoji_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    emoji_embed("update", emoji, old, entry=entry))
        for emoji_id, emoji in before_map.items():
            if emoji_id not in after_map:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.emoji_delete, emoji_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    emoji_embed("delete", emoji, entry=entry))

    @bot.listen("on_guild_stickers_update")
    async def stickers_updated(
        guild: discord.Guild,
        before: list[discord.Sticker],
        after: list[discord.Sticker]) -> None:
        if not cfg.LOG_STICKERS:
            return
        before_map = {sticker.id: sticker for sticker in before}
        after_map = {sticker.id: sticker for sticker in after}
        for sticker_id, sticker in after_map.items():
            old = before_map.get(sticker_id)
            if old is None:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.sticker_create, sticker_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    sticker_embed("create", sticker, entry=entry))
            elif old.name != sticker.name or old.description != sticker.description:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.sticker_update, sticker_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    sticker_embed("update", sticker, old, entry=entry))
        for sticker_id, sticker in before_map.items():
            if sticker_id not in after_map:
                entry = await audit.wait_for_entry(
                    guild, discord.AuditLogAction.sticker_delete, sticker_id
                )
                await send_log(
                    bot,
                    guild,
                    "server",
                    sticker_embed("delete", sticker, entry=entry))

    @bot.listen("on_guild_channel_pins_update")
    async def pins_updated(
        channel: discord.abc.GuildChannel, last_pin
    ) -> None:
        if not cfg.LOG_PINS:
            return
        await send_log(
            bot, channel.guild, "messages", pins_embed(channel, last_pin)
        )

    @bot.listen("on_stage_instance_create")
    async def stage_created(stage: discord.StageInstance) -> None:
        if not cfg.LOG_STAGES:
            return
        entry = await audit.wait_for_entry(
            stage.guild, discord.AuditLogAction.stage_instance_create, stage.id
        )
        await send_log(
            bot,
            stage.guild,
            "server",
            stage_embed("create", stage, entry=entry))

    @bot.listen("on_stage_instance_update")
    async def stage_updated(
        before: discord.StageInstance, after: discord.StageInstance
    ) -> None:
        if not cfg.LOG_STAGES:
            return
        if stage_embed("update", after, before) is None:
            return
        entry = await audit.wait_for_entry(
            after.guild, discord.AuditLogAction.stage_instance_update, after.id
        )
        await send_log(
            bot,
            after.guild,
            "server",
            stage_embed("update", after, before, entry=entry))

    @bot.listen("on_stage_instance_delete")
    async def stage_deleted(stage: discord.StageInstance) -> None:
        if not cfg.LOG_STAGES:
            return
        entry = await audit.wait_for_entry(
            stage.guild, discord.AuditLogAction.stage_instance_delete, stage.id
        )
        await send_log(
            bot,
            stage.guild,
            "server",
            stage_embed("delete", stage, entry=entry))

    @bot.listen("on_scheduled_event_create")
    async def event_created(event: discord.ScheduledEvent) -> None:
        if not cfg.LOG_EVENTS:
            return
        entry = await audit.wait_for_entry(
            event.guild, discord.AuditLogAction.scheduled_event_create, event.id
        )
        await send_log(
            bot,
            event.guild,
            "server",
            scheduled_event_embed("create", event, entry=entry))

    @bot.listen("on_scheduled_event_update")
    async def event_updated(
        before: discord.ScheduledEvent, after: discord.ScheduledEvent
    ) -> None:
        if not cfg.LOG_EVENTS:
            return
        if scheduled_event_embed("update", after, before) is None:
            return
        entry = await audit.wait_for_entry(
            after.guild, discord.AuditLogAction.scheduled_event_update, after.id
        )
        await send_log(
            bot,
            after.guild,
            "server",
            scheduled_event_embed("update", after, before, entry=entry))

    @bot.listen("on_scheduled_event_delete")
    async def event_deleted(event: discord.ScheduledEvent) -> None:
        if not cfg.LOG_EVENTS:
            return
        entry = await audit.wait_for_entry(
            event.guild, discord.AuditLogAction.scheduled_event_delete, event.id
        )
        await send_log(
            bot,
            event.guild,
            "server",
            scheduled_event_embed("delete", event, entry=entry))

    @bot.listen("on_automod_action")
    async def automod_triggered(execution) -> None:
        if not cfg.LOG_AUTOMOD:
            return
        await send_log(
            bot, execution.guild, "moderation", automod_embed(execution)
        )

    @bot.listen("on_audit_log_entry_create")
    async def audit_entry(entry: discord.AuditLogEntry) -> None:
        audit.deliver(entry)
        if not cfg.LOG_AUDIT:
            return
        name = getattr(entry.action, "name", str(entry.action))
        if name in _SKIP_AUDIT:
            return
        await send_log(bot, entry.guild, "moderation", audit_embed(entry))

    @bot.listen("on_command")
    async def command_used(ctx: commands.Context) -> None:
        if not cfg.LOG_COMMANDS or ctx.guild is None or ctx.command is None:
            return
        await send_log(bot, ctx.guild, "commands", command_embed(ctx))

    @bot.listen("on_presence_update")
    async def presence_updated(
        before: discord.Member, after: discord.Member
    ) -> None:
        if not cfg.LOG_PRESENCE:
            return
        await send_log(
            bot, after.guild, "members", presence_embed(before, after)
        )

    @bot.command(
        name="logs",
        aliases=["logging", "logsetup"],
        help=(
            "Turn on server logging: create the Logs category and one "
            "channel per log type. `logs off` turns it off again."
        ))
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(ctx: commands.Context, action: str = "") -> None:
        if not cfg.LOGGING_ENABLED:
            await ctx.send(
                embed=error_embed("Logging is disabled in `config/logs.py`.")
            )
            return
        if action.lower() in {"off", "disable", "stop"}:
            await disable_logging(bot, ctx.guild)
            await ctx.send(embed=logging_disabled_embed())
            return
        if action:
            await ctx.send(
                embed=error_embed(
                    "Use `logs` to set logging up in this server, or "
                    "`logs off` to stop it."
                )
            )
            return
        channels = await setup_logging(bot, ctx.guild)
        if not channels:
            await ctx.send(
                embed=error_embed(
                    "I couldn't create the logging channels. Give me "
                    "**Manage Channels** and try again."
                )
            )
            return
        await ctx.send(embed=logging_setup_embed(channels))

