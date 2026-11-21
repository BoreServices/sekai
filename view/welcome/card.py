from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from view.cards import (
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


def _custom_background(
    path: Path, size: tuple[int, int], accent: tuple[int, int, int]
) -> Image.Image | None:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None

    image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    card = Image.alpha_composite(
        image.convert("RGBA"), Image.new("RGBA", size, (12, 9, 18, 128))
    )
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (size[0] - 360, -240, size[0] + 80, 180), fill=(*accent, 70)
    )
    return Image.alpha_composite(card, glow.filter(ImageFilter.GaussianBlur(80)))


def render_member_card(
    *,
    display_name: str,
    guild_name: str,
    member_count: int | None,
    avatar_bytes: bytes | None,
    leaving: bool,
    accent: tuple[int, int, int],
    background_path: Path | None = None) -> bytes:
    size = (CARD_WIDTH, CARD_HEIGHT)
    card = (
        _custom_background(background_path, size, accent)
        if background_path is not None
        else None
    )
    if card is None:
        card = background(size, accent)
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
        outline=(*accent, 255),
        width=ring)

    left = avatar_x + AVATAR_SIZE + 40
    right = CARD_WIDTH - PADDING
    text_width = right - left - 24
    label_font = font(21, bold=True)
    name_font = font(40, bold=True, cjk=needs_cjk(display_name))
    server_font = font(21, cjk=needs_cjk(guild_name))
    count_font = font(19, bold=True)
    accent_light = tuple(
        round(channel + (255 - channel) * 0.45) for channel in accent
    )

    draw.rounded_rectangle((left - 18, 76, left - 12, 216), radius=3, fill=accent)
    draw.text(
        (left, 74),
        "GOODBYE" if leaving else "WELCOME",
        font=label_font,
        fill=accent_light)
    name = fit_text(draw, display_name, name_font, text_width)
    draw_text(draw, (left, 104), name, font=name_font, fill=TEXT)
    if guild_name:
        server = fit_text(draw, guild_name, server_font, text_width)
        draw_text(draw, (left, 164), server, font=server_font, fill=MUTED)
    if member_count is not None:
        draw.text(
            (left, 204),
            f"MEMBER #{member_count:,}",
            font=count_font,
            fill=accent_light)

    return to_png(rounded_card(card, CORNER_RADIUS))
