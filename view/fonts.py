from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}

_BUNDLED_NAMES = {
    False: (
        "Outfit-Regular.ttf",
        "Inter-Regular.ttf",
        "Poppins-Regular.ttf",
        "Nunito-Regular.ttf"),
    True: (
        "Outfit-Bold.ttf",
        "Inter-Bold.ttf",
        "Poppins-Bold.ttf",
        "Nunito-Bold.ttf"),
}

_SYSTEM = {
    False: (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"),
    True: (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/verdanab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
}

_SYSTEM_CJK = (
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")

_EMOJI_SYSTEM = (
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf")

_EMOJI_BUNDLED = (
    "NotoEmoji.ttf",
    "NotoEmoji-VariableFont_wght.ttf")

# Fonts for fancy display names: mathematical script (𝓖), sub/superscripts
# (ₖᵢ), miscellaneous symbols (♡) and rare scripts like Warang Citi (𑣲).
_SYMBOL_SYSTEM = (
    "C:/Windows/Fonts/cambria.ttc",
    "C:/Windows/Fonts/SansSerifCollection.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansMath-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf")

_FONT_CACHE: dict[tuple[int, bool, bool], ImageFont.ImageFont] = {}
_SYMBOL_CACHE: dict[int, tuple[ImageFont.ImageFont, ...]] = {}


def _bundled(bold: bool) -> list[Path]:
    if not FONT_DIR.is_dir():
        return []
    named = [FONT_DIR / name for name in _BUNDLED_NAMES[bold]]
    found = [path for path in named if path.is_file()]
    if found:
        return found
    # Any font dropped in fonts/ works; filename decides regular vs bold.
    files = sorted(
        path
        for path in FONT_DIR.iterdir()
        if path.suffix.lower() in _FONT_SUFFIXES
        and "italic" not in path.stem.lower()
        and "emoji" not in path.stem.lower()
    )
    matching = [path for path in files if ("bold" in path.stem.lower()) == bold]
    return matching or files


def _bundled_cjk() -> list[Path]:
    if not FONT_DIR.is_dir():
        return []
    tags = ("cjk", "gothic", "meiryo", "wqy", "droid", "jp", "kr")
    return sorted(
        path
        for path in FONT_DIR.iterdir()
        if path.suffix.lower() in _FONT_SUFFIXES
        and "emoji" not in path.stem.lower()
        and any(tag in path.stem.lower() for tag in tags)
    )


def _bundled_emoji() -> list[Path]:
    if not FONT_DIR.is_dir():
        return []
    named = [FONT_DIR / name for name in _EMOJI_BUNDLED]
    found = [path for path in named if path.is_file()]
    if found:
        return found
    return sorted(
        path
        for path in FONT_DIR.iterdir()
        if path.suffix.lower() in _FONT_SUFFIXES
        and "emoji" in path.stem.lower()
    )


def _apply_weight(font: ImageFont.FreeTypeFont) -> None:
    # Variable fonts (Outfit/Inter) default to regular; push the weight axis up.
    try:
        axes = font.get_variation_axes()
    except (AttributeError, OSError):
        return
    values = []
    for axis in axes:
        name = axis.get("name") or ""
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if "weight" in str(name).lower():
            values.append(min(700, axis.get("max", 700)))
        else:
            values.append(axis.get("default", axis.get("min", 0)))
    if values:
        try:
            font.set_variation_by_axes(values)
        except (OSError, ValueError):
            pass


def _load(candidate: Path | str, size: int, *, bold: bool) -> ImageFont.ImageFont | None:
    try:
        loaded = ImageFont.truetype(str(candidate), size)
    except OSError:
        return None
    if bold and isinstance(loaded, ImageFont.FreeTypeFont):
        _apply_weight(loaded)
    return loaded


def font(size: int, *, bold: bool = False, cjk: bool = False) -> ImageFont.ImageFont:
    key = (size, bold, cjk)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached

    candidates: list[Path | str] = []
    if cjk:
        candidates.extend(_bundled_cjk())
        candidates.extend(_SYSTEM_CJK)
    candidates.extend(_bundled(bold))
    candidates.extend(_SYSTEM[bold])
    chosen: ImageFont.ImageFont | None = None
    for candidate in candidates:
        chosen = _load(candidate, size, bold=bold)
        if chosen is not None:
            break
    if chosen is None:
        chosen = ImageFont.load_default(size=size)
    _FONT_CACHE[key] = chosen
    return chosen


def symbol_fonts(size: int) -> tuple[ImageFont.ImageFont, ...]:
    """Fallback fonts that cover fancy Unicode used in display names."""
    cached = _SYMBOL_CACHE.get(size)
    if cached is not None:
        return cached
    loaded = [
        extra
        for extra in (_load(candidate, size, bold=False) for candidate in _SYMBOL_SYSTEM)
        if extra is not None
    ]
    _SYMBOL_CACHE[size] = tuple(loaded)
    return _SYMBOL_CACHE[size]


def emoji_font(size: int) -> ImageFont.ImageFont | None:
    """Font for emoji runs — system colour emoji first, bundled Noto Emoji last."""
    candidates: list[Path | str] = list(_EMOJI_SYSTEM)
    candidates.extend(_bundled_emoji())
    for candidate in candidates:
        loaded = _load(candidate, size, bold=False)
        if loaded is not None:
            return loaded
    return None
