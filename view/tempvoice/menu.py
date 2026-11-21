import asyncio
import io
import logging
from contextlib import suppress

import aiohttp
import discord

from core import emojis, prefix as prefixes
from src.tempvoice import state
from view import (
    error_embed,
    info_embed,
    success_embed,
    voicemaster_menu_embed,
    voicemaster_panel_embed)
from view.tempvoice.menu_image import render_voicemaster_menu
from view.cards import run_render

log = logging.getLogger("sekai.voicemaster")

ICONS = (
    "plus", "crossmark", "checkmark", "paper", "settings",
    "crown", "refresh", "user", "minus", "music", "fire")
MENU_FILENAME = "voicemaster-menu.png"


def current_channel(user) -> discord.VoiceChannel | None:
    voice = getattr(user, "voice", None)
    channel = voice.channel if voice is not None else None
    if channel is None or state._owners.get(channel.id) != user.id:
        return None
    return channel


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


async def post_menu(
    bot,
    guild: discord.Guild,
    channel: discord.TextChannel,
    trigger: discord.VoiceChannel,
    prefix: str,
    old_message_id: int | None = None) -> discord.Message:
    icons = await _fetch_icons()
    png = await run_render(
        render_voicemaster_menu,
        guild_name=guild.name,
        trigger_name=trigger.name,
        icons=icons)
    if old_message_id is not None:
        with suppress(discord.HTTPException):
            await channel.get_partial_message(old_message_id).delete()
    return await channel.send(
        embed=voicemaster_menu_embed(trigger=trigger, prefix=prefix),
        file=discord.File(io.BytesIO(png), filename=MENU_FILENAME),
        view=TempVoiceMenuView(bot))


async def update_panel(bot, channel: discord.VoiceChannel) -> None:
    """Post the control panel in a temp channel's chat, or refresh it in place."""
    owner_id = state._owners.get(channel.id)
    if owner_id is None:
        return
    prefix = await prefixes.get_guild_prefix(bot, channel.guild.id)
    embed = voicemaster_panel_embed(channel=channel, owner_id=owner_id, prefix=prefix)

    message_id = state._panels.get(channel.id)
    if message_id is not None:
        try:
            await channel.get_partial_message(message_id).edit(embed=embed)
            return
        except discord.NotFound:
            state._panels.pop(channel.id, None)
            await bot.db.execute(
                "UPDATE tempvoice_channels SET panel_message_id = NULL "
                "WHERE channel_id = ?",
                (channel.id))
        except discord.HTTPException as exc:
            log.warning(
                "VoiceMaster: panel update failed in %s: %s", channel.id, exc
            )
            return

    try:
        message = await channel.send(embed=embed, view=TempVoicePanelView(bot))
    except discord.HTTPException as exc:
        log.warning(
            "VoiceMaster: could not post the control panel in %s: %s",
            channel.id,
            exc)
        return
    state._panels[channel.id] = message.id
    await bot.db.execute(
        "UPDATE tempvoice_channels SET panel_message_id = ? WHERE channel_id = ?",
        (message.id, channel.id))


def _button(
    custom_id: str,
    label: str,
    emoji_name: str,
    fallback: str,
    style: discord.ButtonStyle,
    row: int = 0) -> discord.ui.Button:
    return discord.ui.Button(
        label=label,
        style=style,
        custom_id=custom_id,
        row=row,
        emoji=emojis.emoji_partial(emoji_name) or fallback)


async def claim_channel(bot, interaction: discord.Interaction) -> None:
    """Give the temporary channel the user is sitting in to them, if the owner left."""
    member = interaction.user
    voice = getattr(member, "voice", None)
    channel = voice.channel if voice is not None else None
    owner_id = state._owners.get(channel.id) if channel is not None else None
    if channel is None or owner_id is None:
        await interaction.response.send_message(
            embed=error_embed("Join a temporary channel first, then claim it."),
            ephemeral=True)
        return
    if owner_id == member.id:
        await interaction.response.send_message(
            embed=error_embed("You already own this channel."), ephemeral=True
        )
        return
    if any(occupant.id == owner_id for occupant in channel.members):
        await interaction.response.send_message(
            embed=error_embed(
                "The owner is still in the channel — you can claim it after they leave."
            ),
            ephemeral=True)
        return
    await state.transfer_owner(bot, channel, member, reason=f"Claimed by {member}")
    await interaction.response.send_message(
        embed=success_embed(f"You now own {channel.mention}.", icon="👑"),
        ephemeral=True)
    prompt_id = state._claim_prompts.pop(channel.id, None)
    if prompt_id is not None:
        with suppress(discord.HTTPException):
            await channel.get_partial_message(prompt_id).delete()


class ClaimPromptView(discord.ui.View):
    """Posted in a temp channel when its owner leaves; anyone there can claim it."""

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        button = _button(
            "voicemaster:claim_prompt",
            "Claim ownership",
            "crown",
            "👑",
            discord.ButtonStyle.primary)
        button.callback = self.claim
        self.add_item(button)

    async def claim(self, interaction: discord.Interaction) -> None:
        await claim_channel(self.bot, interaction)


class _VoiceControlsView(discord.ui.View):
    """Shared buttons for the public menu and each channel's control panel."""

    ENTRIES: tuple[
        tuple[str, str, str, str, discord.ButtonStyle, int, str], ...
    ] = ()

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        for custom_id, label, emoji_name, fallback, style, row, action in self.ENTRIES:
            button = _button(custom_id, label, emoji_name, fallback, style, row)
            button.callback = getattr(self, action)
            self.add_item(button)

    async def _owned(self, interaction: discord.Interaction):
        channel = current_channel(interaction.user)
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "You need to be inside your own temporary channel for that."
                ),
                ephemeral=True)
        return channel

    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await state.set_locked(channel, True, reason=f"Locked by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed(f"{channel.mention} is now locked."), ephemeral=True
        )

    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await state.set_locked(channel, False, reason=f"Unlocked by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed(f"{channel.mention} is now unlocked."), ephemeral=True
        )

    async def hide(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        if state.is_hidden(channel):
            await interaction.response.send_message(
                embed=error_embed(f"{channel.mention} is already hidden."),
                ephemeral=True)
            return
        await state.set_hidden(channel, True, reason=f"Hidden by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed(
                f"{channel.mention} is now hidden from the server. Only you and "
                "permitted members can see it."
            ),
            ephemeral=True)

    async def unhide(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        if not state.is_hidden(channel):
            await interaction.response.send_message(
                embed=error_embed(f"{channel.mention} is already visible."),
                ephemeral=True)
            return
        await state.set_hidden(channel, False, reason=f"Unhidden by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed(f"{channel.mention} is visible to everyone again."),
            ephemeral=True)

    async def rename(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(RenameModal())

    async def limit(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(LimitModal())

    async def claim(self, interaction: discord.Interaction) -> None:
        await claim_channel(self.bot, interaction)

    async def transfer(self, interaction: discord.Interaction) -> None:
        await self._pick(
            interaction,
            "transfer",
            "Transfer channel",
            "Choose the member who should own this channel.")

    async def permit(self, interaction: discord.Interaction) -> None:
        await self._pick(
            interaction,
            "permit",
            "Permit a member",
            "Choose a member who may join even while the channel is locked.")

    async def reject(self, interaction: discord.Interaction) -> None:
        await self._pick(
            interaction,
            "reject",
            "Reject a member",
            "Choose a member to disconnect and keep out of this channel.")

    async def _pick(
        self,
        interaction: discord.Interaction,
        action: str,
        title: str,
        description: str) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await interaction.response.send_message(
            embed=info_embed(
                title=title,
                description=f"{description}\n\nChannel: {channel.mention}",
                fields=[]),
            view=MemberPickerView(self.bot, channel, action),
            ephemeral=True)

    async def bitrate(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(BitrateModal(channel))

    async def delete(self, interaction: discord.Interaction) -> None:
        channel = await self._owned(interaction)
        if channel is None:
            return
        await state.delete_temp(self.bot, channel)
        await interaction.response.send_message(
            embed=success_embed("Your temporary channel was deleted.", icon="🗑️"),
            ephemeral=True)


class TempVoiceMenuView(_VoiceControlsView):
    ENTRIES = (
        ("voicemaster:join", "Join to Create", "plus", "➕", discord.ButtonStyle.primary, 0, "join"),
        ("voicemaster:lock", "Lock", "crossmark", "🔒", discord.ButtonStyle.secondary, 1, "lock"),
        ("voicemaster:unlock", "Unlock", "checkmark", "🔓", discord.ButtonStyle.secondary, 1, "unlock"),
        ("voicemaster:rename", "Rename", "paper", "✏️", discord.ButtonStyle.secondary, 1, "rename"),
        ("voicemaster:limit", "Limit", "settings", "👥", discord.ButtonStyle.secondary, 1, "limit"),
        ("voicemaster:bitrate", "Bitrate", "music", "🎚️", discord.ButtonStyle.secondary, 1, "bitrate"),
        ("voicemaster:claim", "Claim", "crown", "🙋", discord.ButtonStyle.secondary, 2, "claim"),
        ("voicemaster:transfer", "Transfer", "refresh", "🔄", discord.ButtonStyle.secondary, 2, "transfer"),
        ("voicemaster:permit", "Permit", "user", "✅", discord.ButtonStyle.secondary, 2, "permit"),
        ("voicemaster:reject", "Reject", "minus", "🚫", discord.ButtonStyle.secondary, 2, "reject"),
        ("voicemaster:hide", "Hide", "crossmark", "🙈", discord.ButtonStyle.secondary, 2, "hide"),
        ("voicemaster:unhide", "Unhide", "checkmark", "👁️", discord.ButtonStyle.secondary, 3, "unhide"),
        ("voicemaster:delete", "Delete", "fire", "🗑️", discord.ButtonStyle.danger, 3, "delete"))

    async def join(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        voice = getattr(member, "voice", None)
        channel = voice.channel if voice is not None else None
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Join a voice channel first, then press **Join to Create**."
                ),
                ephemeral=True)
            return
        if state._owners.get(channel.id) == member.id:
            await interaction.response.send_message(
                embed=error_embed("You're already in your own temporary channel."),
                ephemeral=True)
            return
        config = state._configs.get(member.guild.id)
        trigger = member.guild.get_channel(config[1]) if config is not None else None
        if not isinstance(trigger, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "This server isn't set up — run the `voicemaster setup` command."
                ),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        created = await state.create_temp(self.bot, member, trigger)
        if created is None:
            await interaction.followup.send(
                embed=error_embed("I couldn't create the channel — check my permissions."),
                ephemeral=True)
            return
        await interaction.followup.send(
            embed=success_embed(f"{created.mention} is ready."), ephemeral=True
        )


class TempVoicePanelView(_VoiceControlsView):
    ENTRIES = (
        ("voicemasterpanel:lock", "Lock", "crossmark", "🔒", discord.ButtonStyle.secondary, 0, "lock"),
        ("voicemasterpanel:unlock", "Unlock", "checkmark", "🔓", discord.ButtonStyle.secondary, 0, "unlock"),
        ("voicemasterpanel:rename", "Rename", "paper", "✏️", discord.ButtonStyle.secondary, 0, "rename"),
        ("voicemasterpanel:limit", "Limit", "settings", "👥", discord.ButtonStyle.secondary, 0, "limit"),
        ("voicemasterpanel:bitrate", "Bitrate", "music", "🎚️", discord.ButtonStyle.secondary, 0, "bitrate"),
        ("voicemasterpanel:claim", "Claim", "crown", "🙋", discord.ButtonStyle.secondary, 1, "claim"),
        ("voicemasterpanel:transfer", "Transfer", "refresh", "🔄", discord.ButtonStyle.secondary, 1, "transfer"),
        ("voicemasterpanel:permit", "Permit", "user", "✅", discord.ButtonStyle.secondary, 1, "permit"),
        ("voicemasterpanel:reject", "Reject", "minus", "🚫", discord.ButtonStyle.secondary, 1, "reject"),
        ("voicemasterpanel:hide", "Hide", "crossmark", "🙈", discord.ButtonStyle.secondary, 1, "hide"),
        ("voicemasterpanel:unhide", "Unhide", "checkmark", "👁️", discord.ButtonStyle.secondary, 2, "unhide"),
        ("voicemasterpanel:delete", "Delete", "fire", "🗑️", discord.ButtonStyle.danger, 2, "delete"))


class RenameModal(discord.ui.Modal, title="Rename your channel"):
    name = discord.ui.TextInput(
        label="New channel name", max_length=100, placeholder="chill zone"
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        channel = current_channel(interaction.user)
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed("You need to be inside your own temporary channel."),
                ephemeral=True)
            return
        name = self.name.value.replace("\n", " ").strip()[:100]
        if not name:
            await interaction.response.send_message(
                embed=error_embed("Give the channel a name."), ephemeral=True
            )
            return
        try:
            await channel.edit(name=name, reason=f"Renamed by {interaction.user}")
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("I couldn't rename that channel."), ephemeral=True
            )
            return
        await state.refresh_panel(channel)
        await interaction.response.send_message(
            embed=success_embed(
                f"Renamed to **{discord.utils.escape_markdown(name)}**."
            ),
            ephemeral=True)


class LimitModal(discord.ui.Modal, title="Set member limit"):
    limit = discord.ui.TextInput(
        label="Limit (0 = unlimited)", max_length=2, placeholder="0-99"
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        channel = current_channel(interaction.user)
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed("You need to be inside your own temporary channel."),
                ephemeral=True)
            return
        raw = self.limit.value.strip()
        if not raw.isdigit() or not 0 <= int(raw) <= state.MAX_USER_LIMIT:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Limit must be between 0 and {state.MAX_USER_LIMIT} (0 = unlimited)."
                ),
                ephemeral=True)
            return
        value = int(raw)
        try:
            await channel.edit(
                user_limit=value, reason=f"Limit set by {interaction.user}"
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("I couldn't change that channel's limit."),
                ephemeral=True)
            return
        await state.refresh_panel(channel)
        text = "unlimited" if value == 0 else str(value)
        await interaction.response.send_message(
            embed=success_embed(f"User limit set to **{text}**."), ephemeral=True
        )


class MemberPickerView(discord.ui.View):
    PLACEHOLDERS = {
        "transfer": "Choose the new owner…",
        "permit": "Choose a member to permit…",
        "reject": "Choose a member to reject…",
    }

    def __init__(
        self, bot, channel: discord.VoiceChannel, action: str
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.channel = channel
        self.action = action
        self.select = discord.ui.UserSelect(
            placeholder=self.PLACEHOLDERS[action],
            min_values=1,
            max_values=1)
        self.select.callback = self.pick
        self.add_item(self.select)

    async def pick(self, interaction: discord.Interaction) -> None:
        channel = current_channel(interaction.user)
        if channel is None or channel.id != self.channel.id:
            await interaction.response.edit_message(
                embed=error_embed("You no longer own this channel."), view=None
            )
            return

        user = self.select.values[0]
        member = interaction.guild.get_member(user.id) if interaction.guild else None
        if member is None:
            await interaction.response.edit_message(
                embed=error_embed("Pick a member of this server."), view=None
            )
            return

        owner_id = state._owners.get(channel.id)
        if member.id == owner_id:
            await interaction.response.edit_message(
                embed=error_embed("They already own this channel."), view=None
            )
            return

        if self.action == "transfer":
            if member.bot:
                await interaction.response.edit_message(
                    embed=error_embed("Bots can't own a temporary channel."),
                    view=None)
                return
            if member not in channel.members:
                await interaction.response.edit_message(
                    embed=error_embed(
                        "They need to be in the channel before you transfer it."
                    ),
                    view=None)
                return
            await state.transfer_owner(
                self.bot,
                channel,
                member,
                reason=f"Transferred by {interaction.user}")
            text = f"{member.mention} now owns {channel.mention}."
            icon = "🔄"
        elif self.action == "permit":
            if member.bot:
                await interaction.response.edit_message(
                    embed=error_embed("Pick a human member."), view=None
                )
                return
            await state.set_permitted(
                channel,
                member,
                True,
                reason=f"Permitted by {interaction.user}")
            text = f"{member.mention} can join {channel.mention}, even while locked."
            icon = "✅"
        else:
            if member not in channel.members:
                await interaction.response.edit_message(
                    embed=error_embed("They aren't in your channel."), view=None
                )
                return
            await state.set_permitted(
                channel,
                member,
                False,
                reason=f"Rejected by {interaction.user}",
                disconnect=True)
            text = f"{member.mention} was removed and can't rejoin."
            icon = "🚫"

        await interaction.response.edit_message(
            embed=success_embed(text, icon=icon), view=None
        )


class BitrateModal(discord.ui.Modal, title="Set audio bitrate"):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel
        limit = int(channel.guild.bitrate_limit // 1000)
        self.bitrate = discord.ui.TextInput(
            label=f"Bitrate in kbps (8-{limit})",
            max_length=3,
            placeholder=f"8-{limit}",
            default=str(channel.bitrate // 1000))
        self.add_item(self.bitrate)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        channel = current_channel(interaction.user)
        if channel is None or channel.id != self.channel.id:
            await interaction.response.send_message(
                embed=error_embed("You no longer own this channel."),
                ephemeral=True)
            return

        raw = self.bitrate.value.strip()
        if not raw.isdigit():
            await interaction.response.send_message(
                embed=error_embed("Bitrate must be a number in kbps."),
                ephemeral=True)
            return

        value = int(raw)
        limit = int(channel.guild.bitrate_limit // 1000)
        if not 8 <= value <= limit:
            await interaction.response.send_message(
                embed=error_embed(f"Bitrate must be between 8 and {limit} kbps."),
                ephemeral=True)
            return

        try:
            await channel.edit(
                bitrate=value * 1000,
                reason=f"Bitrate set by {interaction.user}")
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("I couldn't change the channel's bitrate."),
                ephemeral=True)
            return

        await state.refresh_panel(channel)
        await interaction.response.send_message(
            embed=success_embed(f"Bitrate set to **{value} kbps**.", icon="🎚️"),
            ephemeral=True)
