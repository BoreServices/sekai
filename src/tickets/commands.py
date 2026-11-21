import logging
from contextlib import suppress

import discord
from discord.ext import commands

from core import prefix as prefixes
from src.tickets import state
from view.tickets.menu import (
    TicketCloseView,
    TicketControlView,
    TicketPanelView,
    post_panel)
from view import (
    command_usage_embed,
    error_embed,
    success_embed,
    ticket_claim_embed,
    ticket_close_confirm_embed,
    ticket_list_embed,
    ticket_setup_embed)

log = logging.getLogger("sekai.tickets")


def _staff_only(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return False
    config = state._configs.get(ctx.guild.id)
    if config is None:
        permissions = ctx.author.guild_permissions
        if permissions.administrator or permissions.manage_guild:
            return True
        raise commands.CheckFailure(
            "Tickets aren't set up in this server — run `ticket setup`."
        )
    if not state.is_staff(ctx.author, config):
        raise commands.CheckFailure("Only ticket staff can use that.")
    return True


async def _manageable(ctx: commands.Context) -> state.Ticket | None:
    ticket = state._tickets.get(ctx.channel.id)
    if ticket is None:
        await ctx.send(
            embed=error_embed("Run that inside an open ticket channel.")
        )
        return None
    config = state._configs.get(ticket.guild_id)
    if not state.can_manage(ctx.author, ticket, config):
        await ctx.send(
            embed=error_embed("Only the opener or ticket staff can do that.")
        )
        return None
    return ticket


async def _restore_panels(bot) -> None:
    """Repost the panel if it vanished while the bot was down."""
    for guild_id, config in list(state._configs.items()):
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue
        channel = (
            guild.get_channel(config.panel_channel_id)
            if config.panel_channel_id
            else None
        )
        if not isinstance(channel, discord.TextChannel):
            log.warning(
                "Tickets: panel channel missing in guild %s", guild_id
            )
            continue

        if config.panel_message_id:
            try:
                await channel.get_partial_message(config.panel_message_id).fetch()
                continue
            except discord.NotFound:
                pass
            except discord.HTTPException:
                continue

        prefix = await prefixes.get_guild_prefix(bot, guild_id)
        try:
            message = await post_panel(bot, guild, channel, prefix)
        except discord.HTTPException as exc:
            log.warning(
                "Tickets: could not restore panel in guild %s: %s", guild_id, exc
            )
            continue
        config.panel_message_id = message.id
        await bot.db.execute(
            "UPDATE ticket_config SET panel_message_id = ? WHERE guild_id = ?",
            (message.id, guild_id))
        log.info("Tickets: restored panel message in guild %s", guild_id)


def setup(bot) -> None:
    if not getattr(bot, "_tickets_views_registered", False):
        bot._tickets_views_registered = True
        bot.add_view(TicketPanelView(bot))
        bot.add_view(TicketControlView(bot))

    @bot.listen("on_ready")
    async def load_tickets() -> None:
        if not state._loaded:
            await state.load_state(bot)
        if not getattr(bot, "_tickets_panels_restored", False):
            bot._tickets_panels_restored = True
            await _restore_panels(bot)

    @bot.listen("on_guild_channel_delete")
    async def ticket_channel_deleted(channel: discord.abc.GuildChannel) -> None:
        if channel.id in state._tickets:
            state._tickets.pop(channel.id, None)
            await bot.db.execute(
                "DELETE FROM tickets WHERE channel_id = ?", (channel.id)
            )

    @bot.group(
        name="ticket",
        help="Support tickets — private channels for members and staff.",
        usage="ticket",
        invoke_without_command=True,
        extras={"example": "ticket open My game keeps crashing"})
    @commands.guild_only()
    async def ticket(ctx: commands.Context) -> None:
        # Unknown subcommands ("ticket panel") fall through to here too.
        problem = (
            f"`{discord.utils.escape_markdown(ctx.subcommand_passed)}` "
            "isn't a ticket subcommand."
            if ctx.subcommand_passed
            else None
        )
        await ctx.send(
            embed=command_usage_embed(ticket, prefix=ctx.prefix, problem=problem)
        )

    @ticket.command(
        name="setup",
        help="Create the ticket category and post the panel.",
        usage="ticket setup <staff role> [#panel] [#logs]")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def setup_command(
        ctx: commands.Context,
        staff: discord.Role,
        panel: discord.TextChannel | None = None,
        logs: discord.TextChannel | None = None) -> None:
        guild = ctx.guild
        if staff.is_default():
            await ctx.send(
                embed=error_embed(
                    "Pick a staff role, not @everyone — otherwise everyone "
                    "can read every ticket."
                )
            )
            return

        panel = panel or ctx.channel
        if not isinstance(panel, discord.TextChannel):
            await ctx.send(
                embed=error_embed(
                    "Mention the text channel where the panel should live."
                )
            )
            return
        permissions = panel.permissions_for(guild.me)
        if not (
            permissions.send_messages
            and permissions.embed_links
            and permissions.attach_files
        ):
            await ctx.send(
                embed=error_embed(
                    f"I need **Send Messages**, **Embed Links** and "
                    f"**Attach Files** in {panel.mention}."
                )
            )
            return

        old = state._configs.get(guild.id)
        category = guild.get_channel(old.category_id) if old else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        try:
            if category is None:
                category = await guild.create_category(
                    state.CATEGORY_NAME,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(
                            view_channel=False
                        ),
                        staff: discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True),
                        guild.me: discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                            manage_channels=True),
                    },
                    reason=f"Ticket setup by {ctx.author}")
            else:
                await category.set_permissions(
                    guild.default_role,
                    view_channel=False,
                    reason="Tickets stay private")
                await category.set_permissions(
                    staff,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    reason=f"Ticket staff role set by {ctx.author}")
                await category.set_permissions(
                    guild.me,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    reason="Ticket setup")
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    "I need **Manage Channels** and **Manage Roles** to set "
                    "up the ticket category."
                )
            )
            return

        old_message_id = None
        if old is not None:
            if old.panel_channel_id == panel.id:
                old_message_id = old.panel_message_id
            elif old.panel_channel_id and old.panel_message_id:
                old_panel = guild.get_channel(old.panel_channel_id)
                if isinstance(old_panel, discord.TextChannel):
                    with suppress(discord.HTTPException):
                        await old_panel.get_partial_message(
                            old.panel_message_id
                        ).delete()

        message = None
        try:
            message = await post_panel(
                bot, guild, panel, ctx.prefix, old_message_id
            )
        except discord.HTTPException as exc:
            log.warning("Tickets: panel failed in guild %s: %s", guild.id, exc)

        config = state.Config(
            category_id=category.id,
            staff_role_id=staff.id,
            panel_channel_id=panel.id,
            panel_message_id=message.id if message is not None else None,
            log_channel_id=logs.id if logs is not None else None)
        state._configs[guild.id] = config
        await bot.db.execute(
            "INSERT INTO ticket_config "
            "(guild_id, category_id, staff_role_id, panel_channel_id, "
            "panel_message_id, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "category_id = excluded.category_id, "
            "staff_role_id = excluded.staff_role_id, "
            "panel_channel_id = excluded.panel_channel_id, "
            "panel_message_id = excluded.panel_message_id, "
            "log_channel_id = excluded.log_channel_id, "
            "updated_at = datetime('now')",
            (
                guild.id,
                category.id,
                staff.id,
                panel.id,
                config.panel_message_id,
                config.log_channel_id))
        log.info(
            "Tickets set up in guild %s (category %s, staff role %s, panel %s)",
            guild.id,
            category.id,
            staff.id,
            panel.id)
        if message is None:
            await ctx.send(
                embed=error_embed(
                    "The settings were saved, but I couldn't post the panel. "
                    "Check my permissions and run `ticket setup` again."
                )
            )
            return
        await ctx.send(
            embed=ticket_setup_embed(
                category=category,
                staff_role=staff,
                panel=panel,
                logs=logs,
                prefix=ctx.prefix,
                already=old is not None)
        )

    @ticket.command(
        name="reset",
        help="Remove the panel and ticket configuration.",
        usage="ticket reset")
    @commands.has_permissions(manage_guild=True)
    async def reset(ctx: commands.Context) -> None:
        old = state._configs.get(ctx.guild.id)
        if old is None:
            await ctx.send(
                embed=error_embed("Tickets aren't set up in this server.")
            )
            return
        if old.panel_channel_id and old.panel_message_id:
            panel = ctx.guild.get_channel(old.panel_channel_id)
            if isinstance(panel, discord.TextChannel):
                with suppress(discord.HTTPException):
                    await panel.get_partial_message(old.panel_message_id).delete()
        state._configs.pop(ctx.guild.id, None)
        await bot.db.execute(
            "DELETE FROM ticket_config WHERE guild_id = ?", (ctx.guild.id)
        )
        await ctx.send(
            embed=success_embed(
                "Ticket configuration removed. The category and any open "
                "ticket channels were left alone.",
                icon="🗑️")
        )

    @ticket.command(
        name="open",
        help="Open a ticket without pressing the panel button.",
        usage="ticket open [topic]")
    @commands.guild_only()
    async def open_command(
        ctx: commands.Context, *, topic: str = "General support"
    ) -> None:
        topic = topic.replace("\n", " ").strip()[: state.MAX_TOPIC]
        channel, error = await state.create_ticket(
            bot, ctx.guild, ctx.author, topic or "General support"
        )
        if channel is None:
            await ctx.send(embed=error_embed(error or "I couldn't open it."))
            return
        await ctx.send(
            embed=success_embed(
                f"Your ticket is ready: {channel.mention}", icon="🎫"
            )
        )

    @ticket.command(
        name="list",
        aliases=["open-tickets"],
        help="List every open ticket in the server.",
        usage="ticket list")
    @commands.guild_only()
    @commands.check(_staff_only)
    async def list_tickets(ctx: commands.Context) -> None:
        open_tickets = sorted(
            (
                (channel_id, ticket)
                for channel_id, ticket in state._tickets.items()
                if ticket.guild_id == ctx.guild.id
            ),
            key=lambda item: item[1].number)
        entries = []
        for channel_id, ticket in open_tickets[:25]:
            channel = ctx.guild.get_channel(channel_id)
            location = channel.mention if channel is not None else "`channel gone`"
            claimed = (
                f"claimed by <@{ticket.claimed_id}>"
                if ticket.claimed_id is not None
                else "unclaimed"
            )
            entries.append(
                (
                    ticket.number,
                    f"{location} · opened by <@{ticket.opener_id}> · {claimed}\n"
                    f"Topic: {discord.utils.escape_markdown(ticket.topic[:80])}")
            )
        await ctx.send(
            embed=ticket_list_embed(
                entries=entries, total=len(open_tickets)
            )
        )

    @ticket.command(
        name="add",
        help="Let a member see and write in this ticket.",
        usage="ticket add <member>")
    @commands.guild_only()
    async def add_command(
        ctx: commands.Context, member: discord.Member
    ) -> None:
        ticket = await _manageable(ctx)
        if ticket is None:
            return
        if member.bot:
            await ctx.send(embed=error_embed("Pick a human member."))
            return
        if member.id in (ticket.opener_id, ctx.author.id):
            await ctx.send(
                embed=error_embed("They already have access to this ticket.")
            )
            return
        await state.add_member(
            ctx.channel,
            member,
            reason=f"Added to ticket #{ticket.number:04d} by {ctx.author}")
        await ctx.send(
            embed=success_embed(
                f"{member.mention} can now see this ticket.", icon="➕"
            )
        )

    @ticket.command(
        name="remove",
        help="Remove a member's access to this ticket.",
        usage="ticket remove <member>")
    @commands.guild_only()
    async def remove_command(
        ctx: commands.Context, member: discord.Member
    ) -> None:
        ticket = await _manageable(ctx)
        if ticket is None:
            return
        if member.id == ticket.opener_id:
            await ctx.send(
                embed=error_embed(
                    "The opener always keeps access — close the ticket instead."
                )
            )
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You can't remove yourself."))
            return
        await state.remove_member(
            ctx.channel,
            member,
            reason=f"Removed from ticket #{ticket.number:04d} by {ctx.author}")
        await ctx.send(
            embed=success_embed(
                f"{member.mention} no longer has access to this ticket.",
                icon="🚫")
        )

    @ticket.command(
        name="claim",
        help="Claim this ticket as the staff member handling it.",
        usage="ticket claim")
    @commands.guild_only()
    async def claim_command(ctx: commands.Context) -> None:
        ticket = state._tickets.get(ctx.channel.id)
        if ticket is None:
            await ctx.send(
                embed=error_embed("Run that inside an open ticket channel.")
            )
            return
        config = state._configs.get(ticket.guild_id)
        if config is None or not state.is_staff(ctx.author, config):
            await ctx.send(
                embed=error_embed("Only ticket staff can claim tickets.")
            )
            return
        if ticket.claimed_id == ctx.author.id:
            await ctx.send(
                embed=error_embed("You already claimed this ticket.")
            )
            return
        if ticket.claimed_id is not None:
            await ctx.send(
                embed=error_embed(
                    f"This ticket is already claimed by <@{ticket.claimed_id}>."
                )
            )
            return
        await state.claim_ticket(bot, ctx.channel, ticket, ctx.author)
        await ctx.send(
            embed=ticket_claim_embed(number=ticket.number, member=ctx.author)
        )

    @ticket.command(
        name="rename",
        help="Rename this ticket channel.",
        usage="ticket rename <name>")
    @commands.guild_only()
    async def rename_command(ctx: commands.Context, *, name: str) -> None:
        ticket = await _manageable(ctx)
        if ticket is None:
            return
        name = "-".join(name.lower().split())[:100]
        if not name:
            await ctx.send(embed=error_embed("Give the ticket a name."))
            return
        await state.rename_ticket(
            ctx.channel, name, reason=f"Renamed by {ctx.author}"
        )
        await ctx.send(
            embed=success_embed(
                f"Renamed to **{discord.utils.escape_markdown(name)}**.", icon="✏️"
            )
        )

    @ticket.command(
        name="close",
        help="Close this ticket and DM the opener a transcript.",
        usage="ticket close [reason]")
    @commands.guild_only()
    async def close_command(
        ctx: commands.Context, *, reason: str | None = None
    ) -> None:
        ticket = await _manageable(ctx)
        if ticket is None:
            return
        if reason is not None:
            reason = reason.replace("\n", " ").strip()[:200] or None
        await ctx.send(
            embed=ticket_close_confirm_embed(
                number=ticket.number, reason=reason
            ),
            view=TicketCloseView(bot, ticket, reason))
