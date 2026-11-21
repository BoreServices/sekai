import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config.settings import settings
from view.fonts import font as _font

WIDTH = 1080
HEIGHT = 700
PADDING = 52
ROW_HEIGHT = 92
ICON_SIZE = 58
ICON_ART = 38

_BACKGROUND_TOP = (38, 27, 56)
_BACKGROUND_BOTTOM = (18, 13, 27)
_ACCENT = (155, 89, 182)
_ACCENT_LIGHT = (205, 150, 230)
_TEXT = (243, 239, 248)
_MUTED = (168, 158, 184)
_TILE_FILL = (255, 255, 255, 20)
_TILE_LINE = (205, 150, 230, 80)


def _gradient(
    size: tuple[int, int],
    start: tuple[int, int, int],
    end: tuple[int, int, int]) -> Image.Image:
    width, height = size
    strip = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(strip)
    for index in range(height):
        ratio = index / max(height - 1, 1)
        draw.point(
            (0, index),
            tuple(
                round(first + (second - first) * ratio)
                for first, second in zip(start, end)
            ))
    return strip.resize((width, height))


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return f"{text}…" if text else "…"


def _icon(data: bytes | None, size: int) -> Image.Image | None:
    if not data:
        return None
    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except (OSError, ValueError):
        return None
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _rows() -> list[tuple[str, str, str]]:
    return [
        (
            "plus",
            "Press Open a Ticket",
            "The button under this image starts a private channel for you."),
        (
            "paper",
            "Tell us what you need",
            "Write a short summary so staff know what to look into."),
        (
            "user",
            "Staff joins you",
            "Only you, the bot and the staff team can see the channel."),
        (
            "settings",
            "Claimed and handled",
            "A staff member claims the ticket and works through it with you."),
        (
            "crossmark",
            "Close when done",
            "Press Close and the transcript lands in your DMs."),
    ]


def render_ticket_panel(
    *,
    guild_name: str,
    prefix: str,
    icons: dict[str, bytes]) -> bytes:
    image = _gradient((WIDTH, HEIGHT), _BACKGROUND_TOP, _BACKGROUND_BOTTOM).convert(
        "RGBA"
    )

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((WIDTH - 420, -260, WIDTH + 140, 260), fill=(*_ACCENT, 90))
    glow_draw.ellipse(
        (-200, HEIGHT - 180, 340, HEIGHT + 240), fill=(110, 70, 160, 70)
    )
    image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(90)))

    draw = ImageDraw.Draw(image)
    draw.text((PADDING, 42), "Support Tickets", font=_font(46, bold=True), fill=_TEXT)
    draw.text(
        (PADDING, 104),
        "Private help from the staff team — one open ticket per member.",
        font=_font(22),
        fill=_MUTED)

    rows = _rows()
    column_width = WIDTH - 2 * PADDING
    title_font = _font(26, bold=True)
    desc_font = _font(18)

    for index, (emoji_name, title, description) in enumerate(rows):
        y = 158 + index * ROW_HEIGHT

        tile = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile)
        tile_draw.rounded_rectangle(
            (0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
            radius=18,
            fill=_TILE_FILL,
            outline=_TILE_LINE,
            width=1)
        art = _icon(icons.get(emoji_name), ICON_ART)
        if art is not None:
            tile.alpha_composite(
                art, ((ICON_SIZE - ICON_ART) // 2, (ICON_SIZE - ICON_ART) // 2)
            )
        else:
            # Fallback when the app emoji is missing: a font-safe step number.
            tile_draw.text(
                (ICON_SIZE / 2, ICON_SIZE / 2 - 2),
                str(index + 1),
                font=_font(30, bold=True),
                fill=_ACCENT_LIGHT,
                anchor="mm")
        image.alpha_composite(tile, (PADDING, y))

        text_x = PADDING + ICON_SIZE + 20
        draw.text((text_x, y - 2), title, font=title_font, fill=_TEXT)
        draw.text(
            (text_x, y + 34),
            _fit_text(draw, description, desc_font, column_width - ICON_SIZE - 20),
            font=desc_font,
            fill=_MUTED)

    footer_y = 158 + len(rows) * ROW_HEIGHT + 4
    draw.text(
        (PADDING, footer_y),
        f"Prefix commands: {prefix}ticket add, remove, claim, rename, close, list",
        font=_font(20),
        fill=_ACCENT_LIGHT)
    draw.text(
        (PADDING, HEIGHT - 40),
        f"{guild_name}  ·  {settings.bot_name}  ·  Owned by {settings.owner_name}",
        font=_font(18),
        fill=_MUTED)

    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, WIDTH - 1, HEIGHT - 1), radius=36, fill=255
    )
    output = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)

    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    return buffer.getvalue()
