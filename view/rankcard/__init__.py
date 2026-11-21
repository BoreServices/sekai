from PIL import Image, ImageDraw

from view.cards import (
    ACCENT,
    ACCENT_LIGHT,
    MUTED,
    TEXT,
    TRACK,
    background,
    draw_right as _right,
    draw_text as _draw_text,
    fit_text as _fit_text,
    font as _font,
    gradient as _gradient,
    needs_cjk as _needs_cjk,
    paste_avatar as _paste_avatar,
    rounded_card,
    to_png)

CARD_WIDTH = 900
CARD_HEIGHT = 280
PADDING = 40
AVATAR_SIZE = 176
CORNER_RADIUS = 32


def render_rank_card(
    *,
    display_name: str,
    avatar_bytes: bytes | None,
    level: int,
    rank: int,
    xp: int,
    xp_into_level: int,
    xp_needed: int,
    messages: int,
    guild_name: str = "") -> bytes:
    card = background((CARD_WIDTH, CARD_HEIGHT))
    draw = ImageDraw.Draw(card)

    avatar_x = PADDING
    avatar_y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    _paste_avatar(card, avatar_bytes, avatar_x, avatar_y, AVATAR_SIZE)
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

    rank_font = _font(40, bold=True)
    rank_label_font = _font(18)
    name_font = _font(46, bold=True, cjk=_needs_cjk(display_name))
    detail_font = _font(24)
    level_font = _font(27, bold=True)
    xp_font = _font(21)
    footer_font = _font(19, cjk=_needs_cjk(guild_name))

    name = _fit_text(draw, display_name, name_font, right - left - 150)
    _draw_text(draw, (left, 34), name, font=name_font, fill=TEXT)

    _right(draw, right, 50, "RANK", rank_label_font, MUTED)
    _right(draw, right, 68, f"#{rank}", rank_font, ACCENT_LIGHT)

    count_text = f"{messages:,} message{'s' if messages != 1 else ''}"
    draw.text((left, 110), count_text, font=detail_font, fill=MUTED)

    draw.text((left, 160), f"Level {level}", font=level_font, fill=TEXT)
    _right(
        draw,
        right,
        166,
        f"{xp_into_level:,} / {xp_needed:,} XP",
        xp_font,
        MUTED)

    bar_width = right - left
    bar_height = 22
    bar_y = 204
    ratio = min(max(xp_into_level / xp_needed, 0.0), 1.0) if xp_needed else 0.0

    track = Image.new("RGBA", (bar_width, bar_height), TRACK)
    if ratio > 0:
        fill_width = max(bar_height, int(bar_width * ratio))
        fill = _gradient(
            (fill_width, bar_height), ACCENT, ACCENT_LIGHT, horizontal=True
        ).convert("RGBA")
        fill_mask = Image.new("L", (fill_width, bar_height), 0)
        ImageDraw.Draw(fill_mask).rounded_rectangle(
            (0, 0, fill_width - 1, bar_height - 1),
            radius=bar_height // 2,
            fill=255)
        track.paste(fill, (0, 0), fill_mask)

    bar_mask = Image.new("L", (bar_width, bar_height), 0)
    ImageDraw.Draw(bar_mask).rounded_rectangle(
        (0, 0, bar_width - 1, bar_height - 1),
        radius=bar_height // 2,
        fill=255)
    card.paste(track, (left, bar_y), bar_mask)

    _draw_text(draw, (left, 242), guild_name, font=footer_font, fill=MUTED)
    xp_total = f"{xp:,} XP total"
    _right(draw, right, 242, xp_total, footer_font, MUTED)

    return to_png(rounded_card(card, CORNER_RADIUS))
