from contextlib import suppress

import discord

from core.emojis import emoji_partial
from src.roblox.client import RobloxUser
from view.error import error_embed
from view.roblox.embeds import (
    roblox_avatar_embed,
    roblox_headshot_embed,
    roblox_user_embed)

MENU_TIMEOUT = 240

BUILDERS = {
    "profile": roblox_user_embed,
    "avatar": roblox_avatar_embed,
    "headshot": roblox_headshot_embed,
}


class RobloxUserView(discord.ui.View):
    def __init__(
        self,
        *,
        invoker_id: int,
        user: RobloxUser,
        footer: str) -> None:
        super().__init__(timeout=MENU_TIMEOUT)
        self.invoker_id = invoker_id
        self.user = user
        self.footer = footer
        self.message: discord.Message | None = None

        self.profile_button.emoji = emoji_partial("user") or "👤"
        self.avatar_button.emoji = emoji_partial("user") or "👤"
        self.headshot_button.emoji = emoji_partial("user") or "👤"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"

        if not user.avatar_url:
            self.remove_item(self.avatar_button)
        if not user.headshot_url:
            self.remove_item(self.headshot_button)

    def adopt(self, interaction: discord.Interaction) -> None:
        self.message = interaction.message

    def render(self, key: str) -> discord.Embed:
        return BUILDERS[key](self.user, footer=self.footer)

    async def _show(self, interaction: discord.Interaction, key: str) -> None:
        self.adopt(interaction)
        await interaction.response.edit_message(
            embed=self.render(key),
            attachments=[],
            view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message(
            embed=error_embed(
                "This Roblox menu isn't yours — run the command yourself."
            ),
            ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.secondary, row=0)
    async def profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "profile")

    @discord.ui.button(label="Avatar", style=discord.ButtonStyle.primary, row=0)
    async def avatar_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "avatar")

    @discord.ui.button(label="Headshot", style=discord.ButtonStyle.primary, row=0)
    async def headshot_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "headshot")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=1)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
