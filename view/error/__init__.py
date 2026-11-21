from typing import TYPE_CHECKING

import discord

from core.emojis import emoji_partial, markup
from view.base import ERROR_COLOR, base_embed, brand

if TYPE_CHECKING:
    from core.bot import SekaiBot


def error_embed(description: str) -> discord.Embed:
    embed = base_embed(description=description, color=ERROR_COLOR)
    return brand(embed)


def bug_embed(command: str, detail: str) -> discord.Embed:
    embed = base_embed(
        title="Unexpected error",
        description=(
            f"Something went wrong while running `{command}`:\n\n"
            f"```\n{detail}\n```\n"
            "Please report this error to **PhaseWorld** so it can be fixed."
        ),
        color=ERROR_COLOR)
    embed.add_field(
        name="💡 What now?",
        value="Hit **Report bug** below to send the details — you might get "
        "credit for finding it.",
        inline=False)
    return brand(embed)


class ErrorReportView(discord.ui.View):
    def __init__(
        self,
        bot: "SekaiBot",
        *,
        prefix: str,
        command: str,
        detail: str,
        author: discord.abc.User,
        where: str) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.prefix = prefix
        self.command = command
        self.detail = detail
        self.author = author
        self.where = where
        self.reported = False
        self.report.emoji = emoji_partial("bug") or "🐛"

    @discord.ui.button(label="Report bug", style=discord.ButtonStyle.danger)
    async def report(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.reported:
            await interaction.response.send_message(
                f"{markup('facewithdiagonalmouth', '😐')} This bug was already reported.",
                ephemeral=True)
            return

        sent = await self.bot.send_error_dm(
            reporter=interaction.user,
            author=self.author,
            prefix=self.prefix,
            command=self.command,
            detail=self.detail,
            where=self.where)
        if not sent:
            await interaction.response.send_message(
                f"{markup('warning', '⚠️')} Couldn't DM PhaseWorld — their DMs may be closed.",
                ephemeral=True)
            return

        self.reported = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"{markup('slightlysmilingface', '🙂')} Thanks! Your report was sent to PhaseWorld.\n"
            "You might get credit for finding this bug.",
            ephemeral=True)
