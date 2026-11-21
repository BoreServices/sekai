from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime

import discord

from core.emojis import emoji_markdown, emoji_partial
from view.base import SUCCESS_COLOR, WARNING_COLOR, base_embed, brand

# Moderation badges: semantic key -> (application emoji name, Unicode fallback).
# Application emojis only exist after the startup sync, so every badge keeps a
# Unicode fallback for the first moments of a run and if an upload is missing.
ICONS = {
    "target": ("user", "🎯"),
    "moderator": ("shield", "🛡️"),
    "reason": ("paper", "📝"),
    "success": ("checkmark", "✅"),
    "cancel": ("crossmark", "❌"),
    "kick": ("crossmark", "👢"),
    "ban": ("crossmark", "🔨"),
    "unban": ("checkmark", "🔓"),
    "softban": ("crossmark", "🧹"),
    "banlist": ("crossmark", "📋"),
    "mute": ("timer", "🔇"),
    "unmute": ("checkmark", "🔊"),
    "warn": ("warning", "⚠️"),
    "warnings": ("warning", "⚠️"),
    "delwarn": ("minus", "🗑️"),
    "clearwarns": ("minus", "🗑️"),
    "role": ("user", "🎭"),
    "purge": ("minus", "🧹"),
    "slowmode": ("timer", "⏳"),
    "nuke": ("fire", "💣"),
    "lock": ("shield", "🔒"),
    "unlock": ("shield", "🔓"),
    "nick": ("user", "✏️"),
    "move": ("user", "🔀"),
    "vmute": ("music", "🔇"),
    "vunmute": ("checkmark", "🔊"),
    "vdeafen": ("music", "🔈"),
    "vundeafen": ("checkmark", "🔊"),
    "pin": ("pin", "📌"),
    "unpin": ("minus", "📌"),
}


def badge(icon: str) -> str:
    name, fallback = ICONS.get(icon, ("shield", "🛡️"))
    return emoji_markdown(name) or fallback


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def moderation_embed(
    action: str,
    *,
    target: str,
    moderator: discord.abc.User,
    reason: str | None = None,
    details: str | None = None,
    icon: str = "shield",
    color: discord.Color | int | None = None) -> discord.Embed:
    embed = base_embed(
        title=f"{badge(icon)} {action}", description=details, color=color
    )
    embed.add_field(name=f"{badge('target')} Target", value=target, inline=True)
    embed.add_field(
        name=f"{badge('moderator')} Moderator",
        value=moderator.mention,
        inline=True)
    if reason:
        embed.add_field(
            name=f"{badge('reason')} Reason", value=reason, inline=False
        )
    return brand(embed)


def warnings_embed(
    member: discord.abc.User,
    *,
    entries: list[tuple[int, str, str, datetime]],
    total: int) -> discord.Embed:
    description = f"**{total}** warning{'s' if total != 1 else ''} on record"
    if len(entries) < total:
        description += f" — showing the latest **{len(entries)}**"
    embed = base_embed(
        title=f"{badge('warnings')} Warnings for {member.display_name}",
        description=description + ".",
        color=WARNING_COLOR)
    for warning_id, moderator, reason, created in entries:
        embed.add_field(
            name=f"#{warning_id} · {discord.utils.format_dt(created, 'R')}",
            value=f"by {moderator}\n{_clip(reason, 400)}",
            inline=False)
    return brand(embed)


def warning_dm_embed(
    guild_name: str, reason: str, warning_id: int
) -> discord.Embed:
    embed = base_embed(
        title=f"{badge('warn')} You received a warning",
        description=f"You were warned in **{guild_name}**.",
        color=WARNING_COLOR)
    embed.add_field(
        name=f"{badge('reason')} Reason",
        value=_clip(reason, 1000),
        inline=False)
    embed.add_field(name="Warning", value=f"#{warning_id}", inline=True)
    return brand(embed, footer=f"Warning #{warning_id}")


def ban_list_embed(
    entries: list[tuple[int, str, int, str | None]],
    *,
    page: int,
    pages: int,
    total: int) -> discord.Embed:
    lines = []
    for position, name, user_id, reason in entries:
        text = _clip(reason, 120) if reason else "No reason given."
        lines.append(f"**{position}.** {name} (`{user_id}`) — {text}")
    embed = base_embed(
        title=f"{badge('banlist')} Ban list",
        description="\n".join(lines) or "No one is banned.")
    return brand(embed, footer=f"Page {page}/{pages} · {total:,} banned")


def nuke_confirm_embed(channel: discord.abc.GuildChannel) -> discord.Embed:
    embed = base_embed(
        title=f"{badge('nuke')} Nuke this channel?",
        description=(
            f"{channel.mention} will be deleted and recreated in the same spot. "
            "**Every message** goes with it — pins, threads and history included."
        ),
        color=discord.Color.red())
    embed.add_field(
        name=f"{badge('reason')} Channel", value=channel.mention, inline=True
    )
    embed.add_field(
        name=f"{badge('purge')} Messages", value="All of them", inline=True
    )
    return brand(embed, footer="This can't be undone  ·  confirming in 30s")


class NukeConfirmView(discord.ui.View):
    def __init__(
        self,
        author: discord.abc.User,
        confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=30)
        self.author = author
        self.confirm_action = confirm
        self.done = False
        self.message: discord.Message | None = None
        # Resolved here, not in the decorator: app emojis only exist after the
        # startup upload, and decorator emojis are evaluated once at import.
        self.confirm.emoji = emoji_partial("fire") or "💣"
        self.cancel.emoji = emoji_partial("crossmark") or "❌"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author.id:
            return True
        await interaction.response.send_message(
            "Only the moderator who ran this can confirm.", ephemeral=True
        )
        return False

    def _disable(self) -> None:
        for child in self.children:
            child.disabled = True

    @discord.ui.button(
        label="Nuke channel",
        style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.done:
            return
        self.done = True
        self._disable()
        await interaction.response.defer()
        with suppress(discord.HTTPException):
            await interaction.message.edit(view=self)
        await self.confirm_action(interaction)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.done:
            return
        self.done = True
        self._disable()
        embed = base_embed(
            description=f"{badge('success')} Nuke cancelled. Nothing was deleted.",
            color=SUCCESS_COLOR)
        await interaction.response.edit_message(
            embed=brand(embed),
            view=self)

    async def on_timeout(self) -> None:
        self._disable()
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)
