import asyncio
import io
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import aiohttp
import discord
from PIL import Image, ImageOps

from src.welcome import state

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2560
MAX_REDIRECTS = 3
TIMEOUT = aiohttp.ClientTimeout(total=15)

_WEB_PAGE_MESSAGE = (
    "That link opens a web page, not the image itself. Open the image, "
    "copy its direct address (it usually ends in .png or .jpg), or upload "
    "the file here."
)


def _format_problem(data: bytes) -> str:
    head = data[:2048]
    lowered = head.lstrip().lower()
    if b"<svg" in lowered:
        return "SVG files aren't supported — export it as a PNG or JPEG first."
    if (
        lowered.startswith((b"<!doctype", b"<html", b"<head", b"<?xml"))
        or b"<html" in lowered
    ):
        return _WEB_PAGE_MESSAGE
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in {b"avif", b"avis"}:
            return (
                "That file is AVIF, not PNG — save it as PNG or JPEG and "
                "upload that instead."
            )
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return (
                "That file is HEIC/HEIF, not PNG — export it as PNG or JPEG "
                "and upload that instead."
            )
    return (
        "I couldn't read that file as an image. PNG, JPG, WebP and GIF are "
        "supported — try re-uploading it."
    )


class BackgroundError(Exception):
    pass


async def from_attachment(attachment: discord.Attachment) -> bytes:
    if attachment.size > MAX_BYTES:
        raise BackgroundError("That image is too large (8 MB max).")
    data = await attachment.read()
    if len(data) > MAX_BYTES:
        raise BackgroundError("That image is too large (8 MB max).")
    return data


async def from_url(url: str) -> bytes:
    current = url
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for _ in range(MAX_REDIRECTS + 1):
            await _ensure_public(current)
            async with session.get(current, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise BackgroundError("That link redirected nowhere.")
                    current = urljoin(current, location)
                    continue
                if response.status != 200:
                    raise BackgroundError(
                        f"That link returned HTTP {response.status}."
                    )
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "html" in content_type or content_type.startswith("text/"):
                    raise BackgroundError(_WEB_PAGE_MESSAGE)
                if response.content_length and response.content_length > MAX_BYTES:
                    raise BackgroundError("That image is too large (8 MB max).")
                # aiohttp's read(n) returns whatever arrived first, not n bytes.
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise BackgroundError("That image is too large (8 MB max).")
                return bytes(data)
    raise BackgroundError("That link redirected too many times.")


async def _ensure_public(url: str) -> None:
    """Reject private targets so a Manage Server user can't probe the host."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise BackgroundError("Use a direct http(s) image link.")
    host = parsed.hostname
    if not host:
        raise BackgroundError("That link has no host.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise BackgroundError("I couldn't resolve that link.") from exc
    if not infos:
        raise BackgroundError("I couldn't resolve that link.")
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError as exc:
            raise BackgroundError("That link points to an invalid address.") from exc
        if not address.is_global:
            raise BackgroundError("That link points to a private address.")


def normalize(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Image.DecompressionBombError as exc:
        raise BackgroundError(
            "That image is too large in pixel dimensions — resize it and "
            "try again."
        ) from exc
    except (OSError, ValueError) as exc:
        raise BackgroundError(_format_problem(data)) from exc
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    return buffer.getvalue()


async def save(guild_id: int, *, leaving: bool, data: bytes) -> str:
    jpeg = await asyncio.to_thread(normalize, data)
    path = state.path_for(guild_id, leaving=leaving)
    await asyncio.to_thread(_write, path, jpeg)
    return path.name


async def delete(guild_id: int, *, leaving: bool) -> None:
    path = state.path_for(guild_id, leaving=leaving)
    await asyncio.to_thread(lambda: path.unlink(missing_ok=True))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
