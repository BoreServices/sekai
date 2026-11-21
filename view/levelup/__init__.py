from PIL import ImageDraw

from view.cards import (
    ACCENT,
    ACCENT_LIGHT,
    MUTED,
    TEXT,
    background,
    draw_text,
    fit_text,
    font,
    needs_cjk,
    paste_avatar,
    rounded_card,
    to_png)

CARD_WIDTH = 900
CARD_HEIGHT = 300
PADDING = 40
AVATAR_SIZE = 160
CORNER_RADIUS = 32


def render_level_up_card(
    *,
    display_name: str,
    avatar_bytes: bytes | None,
    level: int,
    guild_name: str = "") -> bytes:
    card = background((CARD_WIDTH, CARD_HEIGHT))
    draw = ImageDraw.Draw(card)

    avatar_x = PADDING
    avatar_y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    paste_avatar(card, avatar_bytes, avatar_x, avatar_y, AVATAR_SIZE)
    ring = 5
    draw.ellipse(
        (
            avatar_x - ring,
            avatar_y - ring,
            avatar_x + AVATAR_SIZE + ring,
            avatar_y + AVATAR_SIZE + ring),
        outline=ACCENT,
        width=ring)

    left = avatar_x + AVATAR_SIZE + 36
    right = CARD_WIDTH - PADDING

    label_font = font(22, bold=True)
    level_font = font(64, bold=True)
    name_font = font(31, bold=True, cjk=needs_cjk(display_name))
    guild_font = font(20, cjk=needs_cjk(guild_name))

    draw.text((left, 58), "LEVEL UP", font=label_font, fill=ACCENT_LIGHT)
    draw.text((left, 84), f"Level {level}", font=level_font, fill=TEXT)

    name = fit_text(draw, display_name, name_font, right - left)
    draw_text(draw, (left, 180), name, font=name_font, fill=TEXT)

    if guild_name:
        guild = fit_text(draw, guild_name, guild_font, right - left)
        draw_text(draw, (left, 226), guild, font=guild_font, fill=MUTED)

    return to_png(rounded_card(card, CORNER_RADIUS))
