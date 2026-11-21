from PIL import Image, ImageDraw

from config.settings import settings
from view.cards import (
    ACCENT_LIGHT,
    BRONZE,
    GOLD,
    MUTED,
    SILVER,
    TEXT,
    background,
    draw_right as _right,
    draw_text as _draw_text,
    fit_text as _fit_text,
    font as _font,
    needs_cjk as _needs_cjk,
    paste_avatar as _paste_avatar,
    rounded_card,
    to_png)

CARD_WIDTH = 900
CARD_HEIGHT = 280
PADDING = 40
AVATAR_SIZE = 176
CORNER_RADIUS = 32

BALTOP_WIDTH = 1080
BALTOP_HEADER = 152
BALTOP_ROW = 100
BALTOP_FOOTER = 76
BALTOP_AVATAR = 60
BALTOP_CORNER = 36
MEDAL_COLORS = {1: GOLD, 2: SILVER, 3: BRONZE}


def render_balance_card(
    *,
    display_name: str,
    avatar_bytes: bytes | None,
    balance: int,
    rank: int,
    daily_ready: bool,
    work_ready: bool,
    guild_name: str = "",
    currency: str = "coins") -> bytes:
    card = background((CARD_WIDTH, CARD_HEIGHT), accent=GOLD)
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
        outline=GOLD,
        width=ring)

    left = avatar_x + AVATAR_SIZE + 36
    right = CARD_WIDTH - PADDING

    rank_font = _font(40, bold=True)
    rank_label_font = _font(18)
    name_font = _font(46, bold=True, cjk=_needs_cjk(display_name))
    balance_font = _font(56, bold=True)
    detail_font = _font(24)
    footer_font = _font(19, cjk=_needs_cjk(guild_name))

    name = _fit_text(draw, display_name, name_font, right - left - 150)
    _draw_text(draw, (left, 34), name, font=name_font, fill=TEXT)

    _right(draw, right, 50, "RANK", rank_label_font, MUTED)
    _right(draw, right, 68, f"#{rank}", rank_font, ACCENT_LIGHT)

    _draw_text(draw, (left, 110), f"{balance:,} {currency}", font=balance_font, fill=GOLD)

    daily_text = "Daily ready" if daily_ready else "Daily on cooldown"
    work_text = "Work ready" if work_ready else "Work on cooldown"
    draw.text((left, 190), daily_text, font=detail_font, fill=TEXT if daily_ready else MUTED)
    _right(draw, right, 190, work_text, detail_font, TEXT if work_ready else MUTED)

    _draw_text(draw, (left, 242), guild_name, font=footer_font, fill=MUTED)

    return to_png(rounded_card(card, CORNER_RADIUS))


def render_baltop_card(
    *,
    guild_name: str,
    entries: list[tuple[int, str, int, bytes | None]],
    page: int,
    pages: int,
    total: int = 0,
    currency: str = "coins") -> bytes:
    """entries are (position, display name, balance, avatar bytes)."""
    rows = max(len(entries), 1)
    height = BALTOP_HEADER + rows * BALTOP_ROW + BALTOP_FOOTER
    card = background((BALTOP_WIDTH, height), accent=GOLD)

    # Translucent row tiles go on an overlay so they blend with the gradient.
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for index, entry in enumerate(entries):
        top = BALTOP_HEADER + index * BALTOP_ROW
        tint = MEDAL_COLORS.get(entry[0])
        fill = (*tint, 30) if tint else (255, 255, 255, 10)
        overlay_draw.rounded_rectangle(
            (BALTOP_ROW // 2 - 60, top + 4, BALTOP_WIDTH - 40, top + BALTOP_ROW - 12),
            radius=20,
            fill=fill)
    card = Image.alpha_composite(card, overlay)
    draw = ImageDraw.Draw(card)

    names = [entry[1] for entry in entries]
    cjk = _needs_cjk(guild_name) or any(_needs_cjk(name) for name in names)
    label_font = _font(20, bold=True)
    title_font = _font(42, bold=True, cjk=_needs_cjk(guild_name))
    page_font = _font(22, bold=True)
    rank_font = _font(23, bold=True)
    name_font = _font(27, bold=True, cjk=cjk)
    balance_font = _font(26, bold=True)
    footer_font = _font(19, cjk=_needs_cjk(guild_name))

    draw.text((40, 38), "RICHEST", font=label_font, fill=ACCENT_LIGHT)
    title = _fit_text(draw, guild_name, title_font, BALTOP_WIDTH - 80 - 220)
    _draw_text(draw, (40, 64), title, font=title_font, fill=TEXT)
    _right(draw, BALTOP_WIDTH - 40, 48, f"PAGE {page}/{pages}", page_font, ACCENT_LIGHT)

    if not entries:
        draw.text(
            (BALTOP_WIDTH / 2, BALTOP_HEADER + BALTOP_ROW / 2),
            "Nobody has any coins yet.",
            font=_font(26),
            fill=MUTED,
            anchor="mm")
    else:
        right = BALTOP_WIDTH - 40
        for index, (position, name, balance, avatar_bytes) in enumerate(entries):
            top = BALTOP_HEADER + index * BALTOP_ROW
            center_y = top + BALTOP_ROW / 2 - 4
            medal = MEDAL_COLORS.get(position)

            badge_x = 40 + 36
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

            avatar_x = 40 + 72
            avatar_y = int(center_y - BALTOP_AVATAR / 2)
            _paste_avatar(card, avatar_bytes, avatar_x, avatar_y, BALTOP_AVATAR)

            name_x = avatar_x + BALTOP_AVATAR + 20
            name_width = right - 260 - name_x
            _draw_text(
                draw,
                (name_x, center_y - 18),
                _fit_text(draw, name, name_font, name_width),
                font=name_font,
                fill=TEXT)
            _right(
                draw,
                right,
                int(center_y - 16),
                f"{balance:,} {currency}",
                balance_font,
                GOLD)

    footer_y = height - 48
    _draw_text(
        draw,
        (40, footer_y),
        f"{settings.bot_name}  ·  Owned by {settings.owner_name}",
        font=footer_font,
        fill=MUTED)
    members = f"{total:,} ranked member{'s' if total != 1 else ''}"
    _right(draw, BALTOP_WIDTH - 40, footer_y, members, footer_font, MUTED)
    return to_png(rounded_card(card, BALTOP_CORNER))
