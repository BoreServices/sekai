import io
from contextlib import suppress

import discord

from core.emojis import emoji_partial
from src.minecraft.client import MinecraftProfile
from view.error import error_embed
from view.minecraft.embeds import (
    mc_cape_3d_embed,
    mc_cape_embed,
    mc_profile_embed,
    mc_skin_3d_embed,
    mc_skin_embed)

MENU_TIMEOUT = 240

FILES = {
    "skin": "skin.png",
    "skin_3d": "skin_3d.png",
    "cape": "cape.png",
    "cape_3d": "cape_3d.png",
}

BUILDERS = {
    "skin": mc_skin_embed,
    "skin_3d": mc_skin_3d_embed,
    "cape": mc_cape_embed,
    "cape_3d": mc_cape_3d_embed,
}


class MinecraftProfileView(discord.ui.View):
    def __init__(
        self,
        *,
        invoker_id: int,
        profile: MinecraftProfile,
        images: dict[str, bytes],
        footer: str) -> None:
        super().__init__(timeout=MENU_TIMEOUT)
        self.invoker_id = invoker_id
        self.profile = profile
        self.images = images
        self.footer = footer
        self.message: discord.Message | None = None

        self.info_button.emoji = emoji_partial("user") or "👤"
        self.skin_button.emoji = emoji_partial("settings") or "🎨"
        self.skin_3d_button.emoji = emoji_partial("user") or "👤"
        self.cape_button.emoji = emoji_partial("paper") or "🧵"
        self.cape_3d_button.emoji = emoji_partial("paper") or "🧵"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"

        if "skin" not in images:
            self.remove_item(self.skin_button)
            self.remove_item(self.skin_3d_button)
        if "cape" not in images:
            self.remove_item(self.cape_button)
            self.remove_item(self.cape_3d_button)

    def adopt(self, interaction: discord.Interaction) -> None:
        self.message = interaction.message

    def render(self, key: str) -> tuple[discord.Embed, discord.File | None]:
        if key == "info":
            embed = mc_profile_embed(self.profile, footer=self.footer)
            data = self.images.get("skin")
            name = FILES["skin"]
        else:
            embed = BUILDERS[key](self.profile, footer=self.footer)
            data = self.images.get(key)
            name = FILES[key]
        file = (
            discord.File(io.BytesIO(data), filename=name)
            if data is not None
            else None
        )
        return embed, file

    async def _show(self, interaction: discord.Interaction, key: str) -> None:
        embed, file = self.render(key)
        self.adopt(interaction)
        await interaction.response.edit_message(
            embed=embed,
            attachments=[] if file is None else [file],
            view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message(
            embed=error_embed(
                "This Minecraft menu isn't yours — run the command yourself."
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
    async def info_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "info")

    @discord.ui.button(label="Skin", style=discord.ButtonStyle.primary, row=0)
    async def skin_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "skin")

    @discord.ui.button(label="Skin 3D", style=discord.ButtonStyle.primary, row=0)
    async def skin_3d_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "skin_3d")

    @discord.ui.button(label="Cape", style=discord.ButtonStyle.secondary, row=0)
    async def cape_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "cape")

    @discord.ui.button(label="Cape 3D", style=discord.ButtonStyle.secondary, row=0)
    async def cape_3d_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, "cape_3d")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=1)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
