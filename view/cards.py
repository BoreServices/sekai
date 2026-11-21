import io
import asyncio

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from view.fonts import emoji_font, font, symbol_fonts

# At most 2 card renders run concurrently. Each render temporarily allocates
# several full-card RGBA buffers and a GaussianBlur copy (~20-50 MB peak per
# render on a 900px card), which stacks fast on a 1 GB VPS under load.
_RENDER_SEM = asyncio.Semaphore(2)


async def run_render(fn, *args, **kwargs) -> bytes:
    """Run a synchronous PIL render under the global concurrency limit."""
    async with _RENDER_SEM:
        return await asyncio.to_thread(fn, *args, **kwargs)

BACKGROUND_TOP = (38, 27, 56)
BACKGROUND_BOTTOM = (18, 13, 27)
ACCENT = (155, 89, 182)
ACCENT_LIGHT = (205, 150, 230)
TEXT = (243, 239, 248)
MUTED = (168, 158, 184)
TRACK = (255, 255, 255, 32)
GOLD = (212, 175, 55)
SILVER = (196, 199, 209)
BRONZE = (196, 120, 76)

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2300, 0x23FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF))
_EMOJI_EXTRA = {
    0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D,
    0x3297, 0x3299,
}
_EMOJI_JOINERS = {0x200D, 0xFE0E, 0xFE0F}
_KEYCAP_BASES = set("0123456789#*")
_KEYCAP_VS = {f"{base}\ufe0f\u20e3" for base in _KEYCAP_BASES}
_KEYCAP_PLAIN = {f"{base}\u20e3" for base in _KEYCAP_BASES}
_KEYCAP_INK = (28, 20, 40)
_EMOJI_FONTS: dict[int, ImageFont.ImageFont | None] = {}

# Fallback chain per main font, plus caches for glyph coverage and split runs.
_CHAINS: dict[int, tuple[ImageFont.ImageFont, ...]] = {}
_GLYPH_CACHE: dict[tuple[int, int], bool] = {}
_GLYPH_CACHE_LIMIT = 8192
_CHUNK_CACHE: dict[
    tuple[int, str], tuple[tuple[str, ImageFont.ImageFont], ...]
] = {}
_CHUNK_CACHE_LIMIT = 4096


def _chain(main: ImageFont.ImageFont) -> tuple[ImageFont.ImageFont, ...]:
    chain = _CHAINS.get(id(main))
    if chain is None:
        size = getattr(main, "size", 32)
        chain = (main, *symbol_fonts(size))
        _CHAINS[id(main)] = chain
    return chain


def _covers(fnt: ImageFont.ImageFont, char: str) -> bool:
    """True when the font has a real glyph, not the .notdef box."""
    if char.isspace():
        return True
    key = (id(fnt), ord(char))
    cached = _GLYPH_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        blank = bytes(fnt.getmask("\uffff"))
        covered = bytes(fnt.getmask(char)) != blank
    except Exception:
        covered = True
    if len(_GLYPH_CACHE) >= _GLYPH_CACHE_LIMIT:
        _GLYPH_CACHE.clear()
    _GLYPH_CACHE[key] = covered
    return covered


def _font_chunks(
    text: str, main: ImageFont.ImageFont
) -> tuple[tuple[str, ImageFont.ImageFont], ...]:
    """Split text into runs, each drawn with the first font that has the glyph."""
    key = (id(main), text)
    cached = _CHUNK_CACHE.get(key)
    if cached is not None:
        return cached
    chain = _chain(main)
    chunks: list[tuple[str, ImageFont.ImageFont]] = []
    for char in text:
        chosen = main
        if not _covers(main, char):
            for candidate in chain[1:]:
                if _covers(candidate, char):
                    chosen = candidate
                    break
        if chunks and chunks[-1][1] is chosen:
            chunks[-1] = (chunks[-1][0] + char, chosen)
        else:
            chunks.append((char, chosen))
    if len(_CHUNK_CACHE) >= _CHUNK_CACHE_LIMIT:
        _CHUNK_CACHE.clear()
    _CHUNK_CACHE[key] = tuple(chunks)
    return tuple(chunks)


def _is_emoji(char: str) -> bool:
    code = ord(char)
    if code in _EMOJI_EXTRA:
        return True
    return any(start <= code <= end for start, end in _EMOJI_RANGES)


def _runs(text: str) -> list[tuple[str, bool]]:
    """Split text into (chunk, is_emoji) runs, keeping sequences together."""
    runs: list[tuple[str, bool]] = []

    def add(chunk: str, is_emoji: bool) -> None:
        joinable = (
            runs
            and runs[-1][1] == is_emoji
            and "\u20e3" not in chunk
            and "\u20e3" not in runs[-1][0]
        )
        if joinable:
            runs[-1] = (runs[-1][0] + chunk, is_emoji)
        else:
            runs.append((chunk, is_emoji))

    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in _KEYCAP_BASES:
            if text[index : index + 3] in _KEYCAP_VS:
                add(text[index : index + 3], True)
                index += 3
                continue
            if text[index : index + 2] in _KEYCAP_PLAIN:
                add(text[index : index + 2], True)
                index += 2
                continue

        code = ord(char)
        if code in _EMOJI_JOINERS or 0x1F3FB <= code <= 0x1F3FF:
            add(char, runs[-1][1] if runs else False)
        else:
            add(char, _is_emoji(char))
        index += 1

    return runs


def _emoji_for(size: int) -> ImageFont.ImageFont | None:
    if size not in _EMOJI_FONTS:
        _EMOJI_FONTS[size] = emoji_font(size)
    return _EMOJI_FONTS[size]


def _keycap_side(size: int) -> int:
    return max(12, round(size * 0.98))


def _keycap_width(size: int) -> float:
    return _keycap_side(size) + size * 0.10


def _draw_keycap(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    anchor: str,
    ascent: int,
    size: int,
    base: str,
    fill) -> float:
    """Draw `1️⃣`-style keycaps as a badge; fonts can't shape U+20E3 in Pillow."""
    side = _keycap_side(size)
    center_y = y if anchor == "lm" else y + ascent - size * 0.36
    top = center_y - side / 2
    draw.rounded_rectangle(
        (x, top, x + side, top + side), radius=side * 0.18, fill=fill
    )
    digit = font(max(10, round(size * 0.62)), bold=True)
    draw.text(
        (x + side / 2, center_y + size * 0.02),
        base,
        font=digit,
        fill=_KEYCAP_INK,
        anchor="mm")
    return _keycap_width(size)


def measure_text(
    draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont
) -> float:
    """Width of text where emoji and fallback glyphs use their own fonts."""
    size = getattr(fnt, "size", 32)
    emoji = _emoji_for(size)
    total = 0.0
    for chunk, is_emoji in _runs(text):
        if is_emoji and emoji is not None:
            if "\u20e3" in chunk:
                total += _keycap_width(size)
            else:
                total += draw.textlength(chunk, font=emoji)
        else:
            for piece, piece_font in _font_chunks(chunk, fnt):
                total += draw.textlength(piece, font=piece_font)
    return total


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill,
    anchor: str = "la") -> None:
    """Draw text, switching fonts for emoji and fallback glyphs."""
    runs = _runs(text)
    size = getattr(font, "size", 32)
    emoji = _emoji_for(size)
    chain = _chain(font)
    no_emoji = emoji is None or not any(is_emoji for _, is_emoji in runs)
    if not anchor.startswith("l") or (no_emoji and len(chain) == 1):
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return

    x, y = xy
    y = int(y)
    ascent = 0
    emoji_y = y
    if emoji is not None:
        try:
            ascent, _ = font.getmetrics()
            emoji_ascent, _ = emoji.getmetrics()
        except (AttributeError, OSError):
            ascent = emoji_ascent = 0
        emoji_y = y + ascent - emoji_ascent if anchor == "la" else y

    for chunk, is_emoji in runs:
        if is_emoji and emoji is not None and "\u20e3" in chunk:
            x += _draw_keycap(draw, x, y, anchor, ascent, size, chunk[0], fill)
        elif is_emoji and emoji is not None:
            draw.text(
                (x, emoji_y),
                chunk,
                font=emoji,
                fill=fill,
                anchor=anchor,
                embedded_color=True)
            x += draw.textlength(chunk, font=emoji)
        elif is_emoji:
            draw.text((x, y), chunk, font=font, fill=fill, anchor=anchor)
            x += draw.textlength(chunk, font=font)
        else:
            for piece, piece_font in _font_chunks(chunk, font):
                draw.text((x, y), piece, font=piece_font, fill=fill, anchor=anchor)
                x += draw.textlength(piece, font=piece_font)


def needs_cjk(text: str) -> bool:
    return any(
        0x2E80 <= ord(char) <= 0x9FFF
        or 0xAC00 <= ord(char) <= 0xD7AF
        or 0xF900 <= ord(char) <= 0xFAFF
        for char in text
    )


def gradient(
    size: tuple[int, int],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    *,
    horizontal: bool = False) -> Image.Image:
    width, height = size
    if horizontal:
        strip = Image.new("RGB", (width, 1))
    else:
        strip = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(strip)
    length = width if horizontal else height
    for index in range(length):
        ratio = index / max(length - 1, 1)
        color = tuple(
            round(first + (second - first) * ratio)
            for first, second in zip(start, end)
        )
        draw.point((index, 0) if horizontal else (0, index), color)
    return strip.resize((width, height))


def background(
    size: tuple[int, int], accent: tuple[int, int, int] = ACCENT
) -> Image.Image:
    width, height = size
    card = gradient(size, BACKGROUND_TOP, BACKGROUND_BOTTOM).convert("RGBA")
    glow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (width - 380, -220, width + 120, 240), fill=(*accent, 95)
    )
    dim = tuple(round(channel * 0.7) for channel in accent)
    glow_draw.ellipse(
        (-180, height - 140, 300, height + 220), fill=(*dim, 70)
    )
    return Image.alpha_composite(card, glow.filter(ImageFilter.GaussianBlur(80)))


def fit_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> str:
    if measure_text(draw, text, font) <= max_width:
        return text
    while text and measure_text(draw, text + "…", font) > max_width:
        text = text[:-1]
    return f"{text}…" if text else "…"


def draw_right(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int]) -> None:
    draw_text(
        draw,
        (x - measure_text(draw, text, font), y),
        text,
        font=font,
        fill=fill)


def circle_mask(size: int) -> Image.Image:
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse(
        (0, 0, size * scale - 1, size * scale - 1), fill=255
    )
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def paste_avatar(
    card: Image.Image, avatar_bytes: bytes | None, x: int, y: int, size: int
) -> None:
    avatar = None
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        except (OSError, ValueError):
            avatar = None

    if avatar is None:
        avatar = Image.new("RGBA", (size, size), (64, 48, 92, 255))
        ImageDraw.Draw(avatar).text(
            (size / 2, size / 2),
            "?",
            font=font(int(size * 0.5), bold=True, cjk=True),
            fill=MUTED,
            anchor="mm")
    else:
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)

    card.paste(avatar, (x, y), circle_mask(size))


def rounded_card(card: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, card.size[0] - 1, card.size[1] - 1), radius=radius, fill=255
    )
    output = Image.new("RGBA", card.size, (0, 0, 0, 0))
    output.paste(card, (0, 0), mask)
    return output


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
