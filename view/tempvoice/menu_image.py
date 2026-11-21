import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config.settings import settings
from view.cards import draw_text as _draw_text
from view.fonts import font as _font

WIDTH = 1080
HEIGHT = 970
PADDING = 52
ROW_HEIGHT = 88
COLUMN_GAP = 36
ICON_SIZE = 54
ICON_ART = 36
HEADER_Y = 158
ROWS_Y = 208

_BACKGROUND_TOP = (38, 27, 56)
_BACKGROUND_BOTTOM = (18, 13, 27)
_ACCENT = (155, 89, 182)
_ACCENT_LIGHT = (205, 150, 230)
_TEXT = (243, 239, 248)
_MUTED = (168, 158, 184)
_TILE_FILL = (255, 255, 255, 20)
_TILE_FILL_ACCENT = (155, 89, 182, 110)
_TILE_LINE = (205, 150, 230, 80)
_TILE_LINE_ACCENT = (205, 150, 230, 190)


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
            tuple(round(first + (second - first) * ratio) for first, second in zip(start, end)))
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


def _columns(
    trigger_name: str) -> tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]:
    name = trigger_name or "Join to Create"
    return (
        (
            "Channel controls",
            (
                ("plus", "Join to Create", f"Get your own channel — or join “{name}”."),
                ("crossmark", "Lock", "Block new members from joining."),
                ("checkmark", "Unlock", "Let everyone connect again."),
                ("paper", "Rename", "Change the channel name."),
                ("settings", "Limit", "Cap members (0 = unlimited)."),
                ("music", "Bitrate", "Set the audio quality."),
                ("crossmark", "Hide", "Remove it from the server's channel list."),
                ("checkmark", "Unhide", "Show the channel to everyone again."))),
        (
            "Members & ownership",
            (
                ("crown", "Claim", "Take over if the owner left."),
                ("refresh", "Transfer", "Hand the channel to someone."),
                ("user", "Permit", "Let one member in while locked."),
                ("minus", "Reject", "Remove a member from the channel."),
                ("fire", "Delete", "Delete the channel right now."))))


def render_voicemaster_menu(
    *,
    guild_name: str,
    trigger_name: str,
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
    draw.text((PADDING, 42), "VoiceMaster Menu", font=_font(46, bold=True), fill=_TEXT)
    draw.text(
        (PADDING, 104),
        "Create a channel, then control it from its own live panel or the buttons below.",
        font=_font(22),
        fill=_MUTED)

    columns = _columns(trigger_name)
    column_width = (WIDTH - 2 * PADDING - COLUMN_GAP) // 2
    header_font = _font(22, bold=True)
    title_font = _font(25, bold=True)
    desc_font = _font(17)

    for column, (header, rows) in enumerate(columns):
        x = PADDING + column * (column_width + COLUMN_GAP)
        draw.text((x, HEADER_Y), header, font=header_font, fill=_ACCENT_LIGHT)
        draw.line(
            (x, HEADER_Y + 34, x + column_width, HEADER_Y + 34),
            fill=_TILE_LINE,
            width=2)

        for row, (emoji_name, title, description) in enumerate(rows):
            y = ROWS_Y + row * ROW_HEIGHT
            highlight = column == 0 and row == 0

            tile = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
            ImageDraw.Draw(tile).rounded_rectangle(
                (0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
                radius=17,
                fill=_TILE_FILL_ACCENT if highlight else _TILE_FILL,
                outline=_TILE_LINE_ACCENT if highlight else _TILE_LINE,
                width=1)
            art = _icon(icons.get(emoji_name), ICON_ART)
            if art is not None:
                tile.alpha_composite(
                    art, ((ICON_SIZE - ICON_ART) // 2, (ICON_SIZE - ICON_ART) // 2)
                )
            image.alpha_composite(tile, (x, y))

            text_x = x + ICON_SIZE + 18
            draw.text(
                (text_x, y - 2),
                _fit_text(draw, title, title_font, x + column_width - text_x),
                font=title_font,
                fill=_TEXT)
            draw.text(
                (text_x, y + 31),
                _fit_text(draw, description, desc_font, x + column_width - text_x),
                font=desc_font,
                fill=_MUTED)

    draw.text(
        (PADDING, 896),
        "A live control panel is posted inside every channel you create.",
        font=_font(20),
        fill=_ACCENT_LIGHT)
    _draw_text(
        draw,
        (PADDING, HEIGHT - 42),
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

