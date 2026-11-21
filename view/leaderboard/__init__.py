import io
import logging
from contextlib import suppress
from typing import Awaitable, Callable

import discord
from PIL import Image, ImageDraw

from config.settings import settings
from view.cards import (
    ACCENT,
    ACCENT_LIGHT,
    BRONZE,
    GOLD,
    MUTED,
    SILVER,
    TEXT,
    background,
    draw_right,
    draw_text,
    fit_text,
    font,
    needs_cjk,
    paste_avatar,
    rounded_card,
    to_png)

WIDTH = 1080
PADDING = 40
HEADER_HEIGHT = 152
ROW_HEIGHT = 100
FOOTER_HEIGHT = 76
CORNER_RADIUS = 36
AVATAR_SIZE = 60

log = logging.getLogger("sekai.leaderboard")

MEDAL_COLORS = {1: GOLD, 2: SILVER, 3: BRONZE}

RenderPage = Callable[[int], Awaitable[tuple[bytes, int]]]


def render_leaderboard(
    *,
    guild_name: str,
    entries: list[tuple[int, str, int, int, int, bytes | None]],
    page: int,
    pages: int,
    total: int) -> bytes:
    rows = max(len(entries), 1)
    height = HEADER_HEIGHT + rows * ROW_HEIGHT + FOOTER_HEIGHT
    card = background((WIDTH, height))

    label_font = font(20, bold=True)
    title_font = font(42, bold=True, cjk=needs_cjk(guild_name))
    page_font = font(22, bold=True)
    rank_font = font(23, bold=True)
    cjk_names = needs_cjk(guild_name) or any(
        needs_cjk(entry[1]) for entry in entries
    )
    name_font = font(27, bold=True, cjk=cjk_names)
    level_font = font(24, bold=True)
    stat_font = font(22)
    footer_font = font(19, cjk=needs_cjk(guild_name))

    # Row backgrounds go on an overlay so the translucent tiles keep the
    # gradient behind them instead of punching holes in the alpha channel.
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for index in range(len(entries)):
        top = HEADER_HEIGHT + index * ROW_HEIGHT
        tint = MEDAL_COLORS.get(entries[index][0])
        fill = (*tint, 30) if tint else (255, 255, 255, 10)
        overlay_draw.rounded_rectangle(
            (PADDING, top + 4, WIDTH - PADDING, top + ROW_HEIGHT - 12),
            radius=20,
            fill=fill)
    card = Image.alpha_composite(card, overlay)
    draw = ImageDraw.Draw(card)

    draw.text((PADDING, 38), "LEADERBOARD", font=label_font, fill=ACCENT_LIGHT)
    title = fit_text(draw, guild_name, title_font, WIDTH - PADDING * 2 - 220)
    draw_text(draw, (PADDING, 64), title, font=title_font, fill=TEXT)
    draw_right(
        draw, WIDTH - PADDING, 48, f"PAGE {page}/{pages}", page_font, ACCENT_LIGHT
    )

    if not entries:
        empty_font = font(26)
        draw.text(
            (WIDTH / 2, HEADER_HEIGHT + ROW_HEIGHT / 2 - 4),
            "No one has earned XP here yet — start chatting!",
            font=empty_font,
            fill=MUTED,
            anchor="mm")
    else:
        right = WIDTH - PADDING
        level_x = right - 300
        xp_x = right - 140
        name_x = PADDING + 168
        name_width = level_x - name_x - 64

        for index, entry in enumerate(entries):
            position, name, level, xp, messages, avatar_bytes = entry
            top = HEADER_HEIGHT + index * ROW_HEIGHT
            center_y = top + ROW_HEIGHT / 2 - 4
            medal = MEDAL_COLORS.get(position)

            badge_x = PADDING + 36
            badge_radius = 25
            draw.ellipse(
                (
                    badge_x - badge_radius,
                    center_y - badge_radius,
                    badge_x + badge_radius,
                    center_y + badge_radius),
                fill=medal or (52, 40, 70))
            draw.text(
                (badge_x, center_y),
                str(position),
                font=rank_font,
                fill=(28, 20, 40) if medal else MUTED,
                anchor="mm")

            avatar_x = PADDING + 86
            avatar_y = int(center_y - AVATAR_SIZE / 2)
            paste_avatar(card, avatar_bytes, avatar_x, avatar_y, AVATAR_SIZE)
            draw.ellipse(
                (
                    avatar_x - 3,
                    avatar_y - 3,
                    avatar_x + AVATAR_SIZE + 3,
                    avatar_y + AVATAR_SIZE + 3),
                outline=medal or (90, 76, 112),
                width=3)

            shown = fit_text(draw, name, name_font, name_width)
            draw_text(
                draw,
                (name_x, center_y),
                shown,
                font=name_font,
                fill=TEXT,
                anchor="lm")
            draw_right(draw, level_x, center_y - 14, f"Lv {level}", level_font, ACCENT_LIGHT)
            draw_right(draw, xp_x, center_y - 12, f"{xp:,} XP", stat_font, MUTED)
            draw_right(
                draw,
                right,
                center_y - 12,
                f"{messages:,} msgs",
                stat_font,
                MUTED)

    footer_y = height - 48
    draw.text(
        (PADDING, footer_y),
        f"{settings.bot_name}  ·  Owned by {settings.owner_name}",
        font=footer_font,
        fill=MUTED)
    members = f"{total:,} ranked member{'s' if total != 1 else ''}"
    draw_right(
        draw, WIDTH - PADDING, footer_y, members, footer_font, MUTED
    )

    return to_png(rounded_card(card, CORNER_RADIUS))


class LeaderboardView(discord.ui.View):
    """Prev/next buttons around render_leaderboard, locked to one member."""

    def __init__(
        self,
        *,
        author_id: int,
        page: int,
        pages: int,
        render: RenderPage) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.page = page
        self.pages = pages
        self._render = render
        self._sync()

    def _sync(self) -> None:
        self.previous.disabled = self.page <= 1
        self.next.disabled = self.page >= self.pages

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Run the leaderboard command yourself to flip through its pages.",
            ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction, step: int) -> None:
        await interaction.response.defer()
        target = max(1, min(self.page + step, self.pages))
        try:
            png, pages = await self._render(target)
            if target > pages:
                target = pages
                png, pages = await self._render(target)
        except Exception:
            log.exception("Could not render leaderboard page %s", target)
            await interaction.followup.send(
                "I couldn't render that page — try the command again.",
                ephemeral=True)
            return
        self.page = target
        self.pages = pages
        self._sync()
        await interaction.edit_original_response(
            attachments=[
                discord.File(
                    io.BytesIO(png), filename=f"leaderboard-{self.page}.png"
                )
            ],
            view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, -1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, 1)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        message = getattr(self, "message", None)
        if message is not None:
            with suppress(discord.HTTPException):
                await message.edit(view=self)
