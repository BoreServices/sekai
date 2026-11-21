"""Pillow renders for Minecraft skins and capes.

The player model is drawn as an isometric projection of textured boxes, the
same way the game's own inventory preview looks. Everything is generated
locally so the bot doesn't depend on a third-party render service.
"""

import io
import math

from PIL import Image, ImageChops, ImageDraw

SCALE = 14
CHECKER_LIGHT = (241, 239, 246, 255)
CHECKER_DARK = (218, 214, 228, 255)
CAPE_REGION = (0, 0, 10, 16)
SKIN_PIXEL = 64
# The game inflates the hat/jacket layer by half a skin pixel, so the shell
# reads as a separate layer instead of lying flat on the base.
OVERLAY_DELTA = 0.5
COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))


class SkinError(ValueError):
    """The skin or cape file isn't a usable texture."""


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except (OSError, ValueError) as exc:
        raise SkinError("That skin file isn't a valid image.") from exc
    return image


def normalize_skin(data: bytes) -> Image.Image:
    """Return a 64x64 skin, expanding legacy 64x32 files."""
    image = _open(data)
    if image.size == (SKIN_PIXEL, SKIN_PIXEL):
        return image
    if image.size == (SKIN_PIXEL, SKIN_PIXEL // 2):
        return _expand_legacy(image)
    # HD skins are still 2:1 or 1:1; normalise them to the base resolution.
    width, height = image.size
    if width % SKIN_PIXEL == 0 and height in {width, width // 2}:
        scale = width // SKIN_PIXEL
        base = image.resize(
            (SKIN_PIXEL, height // scale), Image.Resampling.LANCZOS
        )
        if base.size == (SKIN_PIXEL, SKIN_PIXEL):
            return base
        return _expand_legacy(base)
    raise SkinError("That skin file has an unsupported size.")


def _expand_legacy(image: Image.Image) -> Image.Image:
    out = Image.new("RGBA", (SKIN_PIXEL, SKIN_PIXEL), (0, 0, 0, 0))
    out.paste(image, (0, 0))
    # The top-right quadrant is unused in legacy files and often holds opaque
    # leftovers, but in 64x64 files it is the head's overlay layer.
    out.paste((0, 0, 0, 0), (32, 0, SKIN_PIXEL, 16))
    # Legacy skins mirror the right limbs onto the empty left-limb slots.
    for source, target in (
        ((40, 16, 56, 32), (32, 48)),
        ((0, 16, 16, 32), (16, 48))):
        block = image.crop(source).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        out.paste(block, target)
    return out


def normalize_cape(data: bytes) -> Image.Image:
    image = _open(data)
    if image.size == CAPE_REGION[2:]:
        return image
    if image.width < CAPE_REGION[2] or image.height < CAPE_REGION[3]:
        raise SkinError("That cape file is too small.")
    return image.crop(CAPE_REGION)


def _checkerboard(size: tuple[int, int], cell: int) -> Image.Image:
    canvas = Image.new("RGBA", size, CHECKER_LIGHT)
    draw = ImageDraw.Draw(canvas)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle(
                    (x, y, x + cell - 1, y + cell - 1), fill=CHECKER_DARK
                )
    return canvas


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def skin_texture(data: bytes, *, pixel: int = 8) -> bytes:
    """The raw skin sheet, enlarged on a checkerboard."""
    skin = normalize_skin(data)
    size = SKIN_PIXEL * pixel
    canvas = _checkerboard((size, size), pixel * 4)
    canvas.alpha_composite(
        skin.resize((size, size), Image.Resampling.NEAREST)
    )
    return _png(canvas)


def cape_texture(data: bytes, *, pixel: int = 32) -> bytes:
    """The cape artwork on its own, enlarged on a checkerboard."""
    cape = normalize_cape(data)
    size = (cape.width * pixel, cape.height * pixel)
    canvas = _checkerboard(size, pixel * 2)
    canvas.alpha_composite(cape.resize(size, Image.Resampling.NEAREST))
    return _png(canvas)


def _box_uv(
    ox: int, oy: int, width: int, height: int, depth: int
) -> dict[str, tuple[int, int, int, int]]:
    return {
        "top": (ox + depth, oy, width, depth),
        "bottom": (ox + depth + width, oy, width, depth),
        "right": (ox, oy + depth, depth, height),
        "front": (ox + depth, oy + depth, width, height),
        "left": (ox + depth + width, oy + depth, depth, height),
        "back": (ox + depth + width + depth, oy + depth, width, height),
    }


Box = tuple[float, float, float, float, float, float]
Rect = tuple[int, int, int, int]
Faces = dict[str, Rect]


def _boxes(model: str) -> list[tuple[Box, Faces, Faces]]:
    arm = 3 if model.lower() == "slim" else 4
    return [
        ((-4, 0, 0, 8, 8, 8), _box_uv(0, 0, 8, 8, 8), _box_uv(32, 0, 8, 8, 8)),
        ((-4, 8, 0, 8, 12, 4), _box_uv(16, 16, 8, 12, 4), _box_uv(16, 32, 8, 12, 4)),
        # The character's right arm and leg are on the visible (+x) side.
        (
            (4, 8, 0, arm, 12, 4),
            _box_uv(40, 16, arm, 12, 4),
            _box_uv(40, 32, arm, 12, 4)),
        (
            (-4 - arm, 8, 0, arm, 12, 4),
            _box_uv(32, 48, arm, 12, 4),
            _box_uv(48, 48, arm, 12, 4)),
        ((0, 20, 0, 4, 12, 4), _box_uv(0, 16, 4, 12, 4), _box_uv(0, 32, 4, 12, 4)),
        ((-4, 20, 0, 4, 12, 4), _box_uv(16, 48, 4, 12, 4), _box_uv(0, 48, 4, 12, 4)),
    ]


def _inflate(box: Box, delta: float) -> Box:
    x, y, z, width, height, depth = box
    return (
        x - delta,
        y - delta,
        z - delta,
        width + 2 * delta,
        height + 2 * delta,
        depth + 2 * delta)


def _project(x: float, y: float, z: float, scale: int) -> tuple[float, float]:
    return (
        (x - z) * COS30 * scale,
        (x + z) * SIN30 * scale + y * scale)


def _face_points(
    box: Box,
    face: str) -> tuple[tuple[float, float, float], ...]:
    x, y, z, width, height, depth = box
    if face == "top":
        return (
            (x, y, z),
            (x + width, y, z),
            (x, y, z + depth))
    if face == "front":
        return (
            (x, y, z + depth),
            (x + width, y, z + depth),
            (x, y + height, z + depth))
    if face == "right":
        return (
            (x + width, y, z),
            (x + width, y, z + depth),
            (x + width, y + height, z))
    if face == "back":
        return (
            (x, y, z),
            (x + width, y, z),
            (x, y + height, z))
    if face == "left":
        return (
            (x, y, z + depth),
            (x, y, z),
            (x, y + height, z + depth))
    raise ValueError(face)


def _affine(
    pa: tuple[float, float],
    pb: tuple[float, float],
    pc: tuple[float, float],
    origin: tuple[float, float],
    rect: tuple[int, int, int, int]) -> tuple[float, ...] | None:
    ux, uy = pb[0] - pa[0], pb[1] - pa[1]
    vx, vy = pc[0] - pa[0], pc[1] - pa[1]
    det = ux * vy - uy * vx
    if abs(det) < 1e-9:
        return None
    inv00, inv01 = vy / det, -vx / det
    inv10, inv11 = -uy / det, ux / det
    ox, oy = pa[0] - origin[0], pa[1] - origin[1]
    width, height = rect[2], rect[3]
    a, b = inv00 * width, inv01 * width
    d, e = inv10 * height, inv11 * height
    return (a, b, -a * ox - b * oy, d, e, -d * ox - e * oy)


def _paste_face(
    canvas: Image.Image,
    texture: Image.Image,
    rect: Rect,
    points: tuple[tuple[float, float], ...],
    origin: tuple[float, float],
    scale: int) -> None:
    projected = [_project(*point, scale) for point in points]
    pa, pb, pc = projected
    pd = (pb[0] + pc[0] - pa[0], pb[1] + pc[1] - pa[1])
    xs = [point[0] for point in (pa, pb, pc, pd)]
    ys = [point[1] for point in (pa, pb, pc, pd)]
    left = math.floor(min(xs)) - 1
    top = math.floor(min(ys)) - 1
    right = math.ceil(max(xs)) + 1
    bottom = math.ceil(max(ys)) + 1
    size = (right - left, bottom - top)
    if size[0] <= 0 or size[1] <= 0:
        return

    coeffs = _affine(pa, pb, pc, (left, top), rect)
    if coeffs is None:
        return
    crop = texture.crop(
        (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])
    )
    warped = crop.transform(
        size, Image.Transform.AFFINE, coeffs, resample=Image.Resampling.NEAREST
    )

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(
        [
            (pa[0] - left, pa[1] - top),
            (pb[0] - left, pb[1] - top),
            (pd[0] - left, pd[1] - top),
            (pc[0] - left, pc[1] - top),
        ],
        fill=255)
    combined = ImageChops.multiply(warped.getchannel("A"), mask)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(
        warped, (left - round(origin[0]), top - round(origin[1])), combined
    )
    canvas.alpha_composite(layer)


def _rotate(
    point: tuple[float, float, float],
    *,
    back: bool,
    depth: float) -> tuple[float, float, float]:
    if not back:
        return point
    x, y, z = point
    return (-x, y, depth - z)


def _cape_face(*, back: bool) -> tuple[Rect, tuple[tuple[float, float, float], ...]]:
    rect = (CAPE_REGION[0], CAPE_REGION[1], CAPE_REGION[2], CAPE_REGION[3])
    z = -0.75
    if back:
        # Viewed from behind the cape's outside should read normally.
        points = (
            (5, 8, z),
            (-5, 8, z),
            (5, 24, z))
    else:
        points = (
            (-5, 8, z),
            (5, 8, z),
            (-5, 24, z))
    return rect, points


def _render(
    skin_data: bytes,
    cape_data: bytes | None,
    *,
    model: str,
    back: bool,
    scale: int = SCALE) -> bytes:
    if scale < 1:
        raise SkinError("Render scale must be positive.")
    skin = normalize_skin(skin_data)
    cape = normalize_cape(cape_data) if cape_data else None
    depth = 7.5

    layers: list[
        tuple[float, Image.Image, Rect, tuple[tuple[float, float, float], ...]]
    ] = []

    def add(
        center: tuple[float, float, float],
        texture: Image.Image,
        rect: Rect,
        points: tuple[tuple[float, float, float], ...]) -> None:
        points = tuple(_rotate(point, back=back, depth=depth) for point in points)
        x, y, z = _rotate(center, back=back, depth=depth)
        layers.append((x + z, texture, rect, points))

    for box, faces, overlay in _boxes(model):
        x, y, z, width, height, box_depth = box
        center = (x + width / 2, y + height / 2, z + box_depth / 2)
        outer = _inflate(box, OVERLAY_DELTA)
        visible = ("left", "back", "top") if back else ("right", "front", "top")
        for face in visible:
            points = _face_points(box, face)
            add(center, skin, faces[face], points)
            add(
                (center[0] + 0.001, *center[1:]),
                skin,
                overlay[face],
                _face_points(outer, face))

    if cape is not None:
        rect, points = _cape_face(back=back)
        add((0, 16, -0.75), cape, rect, points)

    layers.sort(key=lambda item: item[0])

    projected: list[tuple[float, float]] = []
    for _, _, _, points in layers:
        projected.extend(_project(*point, scale) for point in points)
    xs = [point[0] for point in projected]
    ys = [point[1] for point in projected]
    pad = 8
    origin = (math.floor(min(xs)) - pad, math.floor(min(ys)) - pad)
    width = math.ceil(max(xs)) + pad - origin[0]
    height = math.ceil(max(ys)) + pad - origin[1]

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for _, texture, rect, points in layers:
        _paste_face(canvas, texture, rect, points, origin, scale)
    return _png(canvas)


def render_skin(
    skin_data: bytes,
    cape_data: bytes | None = None,
    *,
    model: str = "classic",
    back: bool = False,
    scale: int = SCALE) -> bytes:
    return _render(
        skin_data, cape_data, model=model, back=back, scale=scale
    )


def render_pages(
    skin_data: bytes, cape_data: bytes | None, *, model: str = "classic"
) -> dict[str, bytes]:
    """Every image the profile menu can show: skin texture, skin 3D and cape."""
    pages = {
        "skin": skin_texture(skin_data),
        "skin_3d": render_skin(skin_data, model=model),
    }
    if cape_data:
        pages["cape"] = cape_texture(cape_data)
        pages["cape_3d"] = render_skin(
            skin_data, cape_data, model=model, back=True
        )
    return pages
