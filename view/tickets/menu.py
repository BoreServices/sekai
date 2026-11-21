import asyncio
import io
import logging
from contextlib import suppress

import aiohttp
import discord

from core import emojis
from src.tickets import state
from view import (
    error_embed,
    info_embed,
    success_embed,
    ticket_claim_embed,
    ticket_close_confirm_embed,
    ticket_panel_embed)
from view.tickets.panel_image import render_ticket_panel
from view.cards import run_render

log = logging.getLogger("sekai.tickets")

ICONS = ("plus", "paper", "user", "settings", "crossmark")
PANEL_FILENAME = "ticket-panel.png"


async def _fetch_icons() -> dict[str, bytes]:
    icons: dict[str, bytes] = {}
    async with aiohttp.ClientSession() as session:
        for name in ICONS:
            url = emojis.emoji_image(name)
            if url is None:
                continue
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        icons[name] = await response.read()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue
    return icons


async def post_panel(
    bot,
    guild: discord.Guild,
    channel: discord.TextChannel,
    prefix: str,
    old_message_id: int | None = None) -> discord.Message:
    icons = await _fetch_icons()
    png = await run_render(
        render_ticket_panel,
        guild_name=guild.name,
        prefix=prefix,
        icons=icons)
    if old_message_id is not None:
        with suppress(discord.HTTPException):
            await channel.get_partial_message(old_message_id).delete()
    return await channel.send(
        embed=ticket_panel_embed(prefix=prefix),
        file=discord.File(io.BytesIO(png), filename=PANEL_FILENAME),
        view=TicketPanelView(bot))


class TicketPanelView(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        button = discord.ui.Button(
            label="Open a Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="ticket:open",
            emoji=emojis.emoji_partial("plus") or "🎫")
        button.callback = self.open_ticket
        self.add_item(button)

    async def open_ticket(self, interaction: discord.Interaction) -> None:
        if not state._loaded:
            await state.load_state(self.bot)
        if state._configs.get(interaction.guild_id) is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Tickets aren't set up in this server yet — ask an admin "
                    "to run `ticket setup`."
                ),
                ephemeral=True)
            return
        if state.find_open(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed(
                    "You already have an open ticket — close that one first."
                ),
                ephemeral=True)
            return
        await interaction.response.send_modal(OpenTicketModal(self.bot))


class OpenTicketModal(discord.ui.Modal, title="Open a ticket"):
    subject = discord.ui.TextInput(
        label="What can we help with?",
        placeholder="Short summary — e.g. I can't verify my account",
        max_length=state.MAX_TOPIC,
        required=True)

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Tickets only work in a server."),
                ephemeral=True)
            return
        if state._configs.get(interaction.guild.id) is None:
            await interaction.response.send_message(
                embed=error_embed("Tickets aren't set up in this server anymore."),
                ephemeral=True)
            return
        if state.find_open(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed(
                    "You already have an open ticket — close that one first."
                ),
                ephemeral=True)
            return

        topic = self.subject.value.replace("\n", " ").strip()
        topic = topic[: state.MAX_TOPIC] or "General support"
        await interaction.response.defer(ephemeral=True)
        channel, error = await state.create_ticket(
            self.bot, interaction.guild, interaction.user, topic
        )
        if channel is None:
            await interaction.followup.send(
                embed=error_embed(error or "I couldn't open the ticket."),
                ephemeral=True)
            return
        await interaction.followup.send(
            embed=success_embed(
                f"Your ticket is ready: {channel.mention}", icon="🎫"
            ),
            ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        entries = (
            ("ticket:claim", "Claim", "crown", "🙋", discord.ButtonStyle.secondary, self.claim),
            ("ticket:add", "Add Member", "user", "➕", discord.ButtonStyle.secondary, self.add),
            ("ticket:rename", "Rename", "paper", "✏️", discord.ButtonStyle.secondary, self.rename),
            ("ticket:close", "Close", "crossmark", "🔒", discord.ButtonStyle.danger, self.close))
        for custom_id, label, emoji_name, fallback, style, callback in entries:
            button = discord.ui.Button(
                label=label,
                style=style,
                custom_id=custom_id,
                emoji=emojis.emoji_partial(emoji_name) or fallback)
            button.callback = callback
            self.add_item(button)

    def _ticket(self, interaction: discord.Interaction) -> state.Ticket | None:
        return state._tickets.get(interaction.channel_id or 0)

    async def _manageable(self, interaction: discord.Interaction):
        ticket = self._ticket(interaction)
        if ticket is None:
            await interaction.response.send_message(
                embed=error_embed("This channel isn't an open ticket."),
                ephemeral=True)
            return None, None
        config = state._configs.get(ticket.guild_id)
        if not state.can_manage(interaction.user, ticket, config):
            await interaction.response.send_message(
                embed=error_embed("Only the opener or ticket staff can do that."),
                ephemeral=True)
            return None, None
        return ticket, config

    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = self._ticket(interaction)
        if ticket is None:
            await interaction.response.send_message(
                embed=error_embed("This channel isn't an open ticket."),
                ephemeral=True)
            return
        config = state._configs.get(ticket.guild_id)
        if config is None or not state.is_staff(interaction.user, config):
            await interaction.response.send_message(
                embed=error_embed("Only ticket staff can claim tickets."),
                ephemeral=True)
            return
        if ticket.claimed_id is not None:
            if ticket.claimed_id == interaction.user.id:
                text = "You already claimed this ticket."
            else:
                text = f"This ticket is already claimed by <@{ticket.claimed_id}>."
            await interaction.response.send_message(
                embed=error_embed(text), ephemeral=True
            )
            return
        await state.claim_ticket(
            self.bot, interaction.channel, ticket, interaction.user
        )
        await interaction.response.send_message(
            embed=ticket_claim_embed(
                number=ticket.number, member=interaction.user
            )
        )

    async def add(self, interaction: discord.Interaction) -> None:
        ticket, _ = await self._manageable(interaction)
        if ticket is None:
            return
        await interaction.response.send_message(
            embed=info_embed(
                title="Add someone",
                description="Pick a member who should also see this ticket.",
                fields=[]),
            view=TicketMemberPickerView(self.bot, "add"),
            ephemeral=True)

    async def rename(self, interaction: discord.Interaction) -> None:
        ticket, _ = await self._manageable(interaction)
        if ticket is None:
            return
        await interaction.response.send_modal(TicketRenameModal(interaction.channel))

    async def close(self, interaction: discord.Interaction) -> None:
        ticket, _ = await self._manageable(interaction)
        if ticket is None:
            return
        await interaction.response.send_message(
            embed=ticket_close_confirm_embed(number=ticket.number),
            view=TicketCloseView(self.bot, ticket),
            ephemeral=True)


class TicketCloseView(discord.ui.View):
    def __init__(
        self, bot, ticket: state.Ticket, reason: str | None = None
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.ticket = ticket
        self.reason = reason

        confirm = discord.ui.Button(
            label="Close with transcript",
            style=discord.ButtonStyle.danger,
            emoji=emojis.emoji_partial("crossmark") or "🗑️")
        confirm.callback = self.confirm
        self.add_item(confirm)

        cancel = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.secondary
        )
        cancel.callback = self.cancel
        self.add_item(cancel)

    async def _validate(self, interaction: discord.Interaction) -> bool:
        ticket = state._tickets.get(interaction.channel_id or 0)
        if ticket is None or ticket.number != self.ticket.number:
            await interaction.response.send_message(
                embed=error_embed("This ticket is already closed."),
                ephemeral=True)
            return False
        config = state._configs.get(ticket.guild_id)
        if not state.can_manage(interaction.user, ticket, config):
            await interaction.response.send_message(
                embed=error_embed("Only the opener or ticket staff can close it."),
                ephemeral=True)
            return False
        return True

    async def confirm(self, interaction: discord.Interaction) -> None:
        if not await self._validate(interaction):
            return
        await interaction.response.defer()
        closed = await state.close_ticket(
            self.bot,
            interaction.channel,
            self.ticket,
            closed_by=interaction.user,
            reason=self.reason,
            transcript=True)
        if not closed:
            await interaction.followup.send(
                embed=error_embed(
                    "I couldn't delete this channel — check my permissions."
                ),
                ephemeral=True)

    async def cancel(self, interaction: discord.Interaction) -> None:
        if not await self._validate(interaction):
            return
        await interaction.response.edit_message(
            embed=success_embed("Closing cancelled.", icon="✅"), view=None
        )


class TicketMemberPickerView(discord.ui.View):
    PLACEHOLDERS = {
        "add": "Choose a member to add…",
        "remove": "Choose a member to remove…",
    }

    def __init__(self, bot, action: str) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.action = action
        self.select = discord.ui.UserSelect(
            placeholder=self.PLACEHOLDERS[action], min_values=1, max_values=1
        )
        self.select.callback = self.pick
        self.add_item(self.select)

    async def pick(self, interaction: discord.Interaction) -> None:
        ticket = state._tickets.get(interaction.channel_id or 0)
        config = (
            state._configs.get(ticket.guild_id) if ticket is not None else None
        )
        if ticket is None or not state.can_manage(
            interaction.user, ticket, config
        ):
            await interaction.response.edit_message(
                embed=error_embed("You can't change this ticket."), view=None
            )
            return
        user = self.select.values[0]
        member = interaction.guild.get_member(user.id) if interaction.guild else None
        if member is None:
            await interaction.response.edit_message(
                embed=error_embed("Pick a member of this server."), view=None
            )
            return

        if self.action == "add":
            if member.bot:
                await interaction.response.edit_message(
                    embed=error_embed("Pick a human member."), view=None
                )
                return
            if member.id in (ticket.opener_id, interaction.user.id):
                await interaction.response.edit_message(
                    embed=error_embed("They already have access."), view=None
                )
                return
            await state.add_member(
                interaction.channel,
                member,
                reason=f"Added to ticket #{ticket.number:04d} by {interaction.user}")
            text = f"{member.mention} can now see this ticket."
        else:
            if member.id == ticket.opener_id:
                await interaction.response.edit_message(
                    embed=error_embed(
                        "The opener always keeps access — close the ticket instead."
                    ),
                    view=None)
                return
            if member.id == interaction.user.id:
                await interaction.response.edit_message(
                    embed=error_embed("You can't remove yourself."), view=None
                )
                return
            await state.remove_member(
                interaction.channel,
                member,
                reason=f"Removed from ticket #{ticket.number:04d} by {interaction.user}")
            text = f"{member.mention} no longer has access to this ticket."

        await interaction.response.edit_message(
            embed=success_embed(text), view=None
        )


class TicketRenameModal(discord.ui.Modal, title="Rename ticket"):
    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__()
        self.channel = channel
        self.name = discord.ui.TextInput(
            label="Channel name",
            max_length=100,
            default=channel.name,
            placeholder="e.g. verify-account")
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ticket = state._tickets.get(interaction.channel_id or 0)
        config = (
            state._configs.get(ticket.guild_id) if ticket is not None else None
        )
        if ticket is None or not state.can_manage(
            interaction.user, ticket, config
        ):
            await interaction.response.send_message(
                embed=error_embed("You can't rename this ticket."), ephemeral=True
            )
            return
        name = "-".join(self.name.value.lower().split())[:100]
        if not name:
            await interaction.response.send_message(
                embed=error_embed("Give the ticket a name."), ephemeral=True
            )
            return
        try:
            await state.rename_ticket(
                interaction.channel,
                name,
                reason=f"Renamed by {interaction.user}")
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("I couldn't rename this channel."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=success_embed(
                f"Renamed to **{discord.utils.escape_markdown(name)}**.", icon="✏️"
            ),
            ephemeral=True)
