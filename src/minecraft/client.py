"""Minecraft lookups through Mojang's public APIs and mcsrvstat.us.

Player profiles resolve a username to a UUID, then read the signed textures
property from the session server to find the skin and cape files. Server
status is read from mcsrvstat, which proxies the game's own ping.
"""

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass

import aiohttp

NAME_LOOKUP = (
    "https://api.minecraftservices.com/minecraft/profile/lookup/name/{name}"
)
NAME_LOOKUP_FALLBACK = "https://api.mojang.com/users/profiles/minecraft/{name}"
SESSION_PROFILE = (
    "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
)
JAVA_STATUS = "https://api.mcsrvstat.us/3/{address}"
BEDROCK_STATUS = "https://api.mcsrvstat.us/bedrock/3/{address}"

TIMEOUT = 15
PROFILE_TTL = 300
SERVER_TTL = 120
CACHE_LIMIT = 256
MAX_NAMES = 30

HEADERS = {
    "accept": "application/json",
    "user-agent": "sekai-minecraft/1.0",
}

_NAME = re.compile(r"[A-Za-z0-9_]{3,16}")
_ADDRESS = re.compile(r"[A-Za-z0-9._-]{1,253}(?::\d{1,5})?")

_cache: dict[str, tuple[float, object]] = {}


class MinecraftError(Exception):
    """Minecraft data couldn't be loaded."""


class MinecraftNotFound(MinecraftError):
    """The player or server doesn't exist."""


class InvalidAddress(MinecraftError):
    """The address doesn't look like a server hostname."""


@dataclass(frozen=True, slots=True)
class MinecraftProfile:
    username: str
    uuid: str
    model: str
    skin_url: str | None
    cape_url: str | None
    skin: bytes | None
    cape: bytes | None

    @property
    def namemc(self) -> str:
        return f"https://namemc.com/profile/{self.uuid}"


@dataclass(frozen=True, slots=True)
class MinecraftServer:
    address: str
    host: str
    port: int | None
    edition: str
    online: bool
    motd: list[str]
    players_online: int
    players_max: int
    players: list[str]
    version: str | None
    software: str | None
    plugins: list[str]
    mods: list[str]
    icon: bytes | None
    gamemode: str | None
    map_name: str | None
    hostname: str | None
    srv: bool


def parse_address(text: str) -> tuple[str, int | None]:
    value = text.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].strip()
    if not _ADDRESS.fullmatch(value):
        raise InvalidAddress(
            "That doesn't look like a server address — try `play.example.net`."
        )
    host, _, port = value.partition(":")
    if port and not 0 < int(port) < 65536:
        raise InvalidAddress("That port number isn't valid.")
    return host, int(port) if port else None


def _cached(key: str, ttl: int):
    entry = _cache.get(key)
    if entry is None or time.monotonic() - entry[0] >= ttl:
        return None
    return entry[1]


def _remember(key: str, value) -> None:
    if len(_cache) >= CACHE_LIMIT:
        oldest = min(_cache, key=lambda item: _cache[item][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.monotonic(), value)


def _dashed(uuid: str) -> str:
    plain = uuid.replace("-", "")
    return (
        f"{plain[0:8]}-{plain[8:12]}-{plain[12:16]}-"
        f"{plain[16:20]}-{plain[20:32]}"
    )


def _textures(profile: dict) -> dict:
    for prop in profile.get("properties") or []:
        if not isinstance(prop, dict) or prop.get("name") != "textures":
            continue
        value = prop.get("value")
        if not isinstance(value, str):
            continue
        try:
            decoded = json.loads(base64.b64decode(value))
        except (ValueError, TypeError):
            continue
        textures = decoded.get("textures")
        return textures if isinstance(textures, dict) else {}
    return {}


def _url(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    url = entry.get("url")
    if not isinstance(url, str) or not url:
        return None
    return url.replace("http://", "https://", 1)


async def _json(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status in {204, 404}:
                return None
            if response.status == 429:
                raise MinecraftError(
                    "Mojang is limiting lookups right now — try again in a minute."
                )
            if response.status != 200:
                raise MinecraftError(
                    f"The lookup service returned an error (`{response.status}`)."
                )
            return await response.json(content_type=None)
    except MinecraftError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise MinecraftError(
            "Couldn't reach the lookup service — try again in a moment."
        ) from exc


async def _download(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status != 200:
                return None
            return await response.read()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def _identity(
    session: aiohttp.ClientSession, name: str
) -> tuple[str, str] | None:
    try:
        data = await _json(session, NAME_LOOKUP.format(name=name))
    except MinecraftError:
        data = None
    if not isinstance(data, dict) or not data.get("id"):
        data = await _json(session, NAME_LOOKUP_FALLBACK.format(name=name))
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return str(data["id"]), str(data.get("name") or name)


async def fetch_profile(username: str) -> MinecraftProfile:
    name = username.strip()
    if not _NAME.fullmatch(name):
        raise MinecraftNotFound(
            f"`{username.strip()}` isn't a valid Minecraft username."
        )

    key = f"profile:{name.lower()}"
    cached = _cached(key, PROFILE_TTL)
    if cached is not None:
        return cached

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        identity = await _identity(session, name)
        if identity is None:
            raise MinecraftNotFound(f"No Minecraft account named `{name}`.")
        uuid, real_name = identity

        profile = await _json(session, SESSION_PROFILE.format(uuid=uuid))
        if not isinstance(profile, dict):
            raise MinecraftError(
                "Mojang didn't return that player's profile — try again."
            )
        textures = _textures(profile)
        skin_entry = textures.get("SKIN")
        skin_url = _url(skin_entry)
        cape_url = _url(textures.get("CAPE"))
        metadata = skin_entry.get("metadata") if isinstance(skin_entry, dict) else None
        model = (
            "slim"
            if isinstance(metadata, dict) and metadata.get("model") == "slim"
            else "classic"
        )

        skin = await _download(session, skin_url) if skin_url else None
        cape = await _download(session, cape_url) if cape_url else None
        if skin_url and skin is None:
            raise MinecraftError(
                "Couldn't download that player's skin — try again."
            )

    result = MinecraftProfile(
        username=real_name,
        uuid=_dashed(uuid),
        model=model,
        skin_url=skin_url,
        cape_url=cape_url,
        skin=skin,
        cape=cape)
    _remember(key, result)
    return result


def _names(raw) -> list[str]:
    names = []
    for entry in raw or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _versions(raw) -> list[str]:
    names = []
    for entry in raw or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            version = entry.get("version")
            if isinstance(name, str) and name:
                names.append(f"{name} {version}" if version else name)
        elif isinstance(entry, str) and entry:
            names.append(entry)
    return names


def _icon(raw) -> bytes | None:
    if not isinstance(raw, str) or "," not in raw:
        return None
    try:
        return base64.b64decode(raw.split(",", 1)[1])
    except (ValueError, TypeError):
        return None


def _count(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _server(
    address: str,
    host: str,
    port: int | None,
    edition: str,
    data: dict) -> MinecraftServer:
    motd = data.get("motd") or {}
    lines = motd.get("clean") if isinstance(motd, dict) else None
    players = data.get("players") or {}
    version = data.get("version")
    protocol = data.get("protocol") or {}
    debug = data.get("debug") or {}
    bed = edition == "Bedrock"
    return MinecraftServer(
        address=address,
        host=host,
        port=port,
        edition=edition,
        online=bool(data.get("online")),
        motd=[str(line) for line in lines or [] if str(line).strip()],
        players_online=_count(players.get("online")),
        players_max=_count(players.get("max")),
        players=_names(players.get("list"))[:MAX_NAMES],
        version=(
            str(protocol.get("name") or version)
            if (protocol.get("name") or version)
            else None
        ),
        software=str(data.get("software") or "") or None,
        plugins=[] if bed else _versions(data.get("plugins")),
        mods=[] if bed else _versions(data.get("mods")),
        icon=_icon(data.get("icon")),
        gamemode=(str(data.get("gamemode") or "") or None) if bed else None,
        map_name=(str(data.get("map") or "") or None) if bed else None,
        hostname=str(data.get("hostname") or "") or None,
        srv=bool(debug.get("srv")))


async def _status(
    session: aiohttp.ClientSession, url: str
) -> dict | None:
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise MinecraftError(
                    f"The status service returned an error (`{response.status}`)."
                )
            data = await response.json(content_type=None)
    except MinecraftError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise MinecraftError(
            "Couldn't reach the status service — try again in a moment."
        ) from exc
    return data if isinstance(data, dict) else None


async def fetch_server(address: str) -> MinecraftServer:
    host, port = parse_address(address)
    target = f"{host}:{port}" if port else host
    key = f"server:{target.lower()}"
    cached = _cached(key, SERVER_TTL)
    if cached is not None:
        return cached

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        data = await _status(session, JAVA_STATUS.format(address=target))
        result = None
        if data is not None:
            result = _server(target, host, port, "Java", data)

        if result is None or not result.online:
            bedrock = await _status(
                session, BEDROCK_STATUS.format(address=target)
            )
            if bedrock is not None and bedrock.get("online"):
                result = _server(target, host, port, "Bedrock", bedrock)

    if result is None:
        raise MinecraftNotFound(
            f"No Minecraft server found at `{target}`. Check the address."
        )

    _remember(key, result)
    return result
