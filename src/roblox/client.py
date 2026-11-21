"""Roblox player lookups through Roblox's public web APIs.

A username resolves to an ID through the users API, then profile details,
social counts, groups, presence and the avatar renders come from their own
public endpoints.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime

import aiohttp

USERS_URL = "https://users.roblox.com/v1"
FRIENDS_URL = "https://friends.roblox.com/v1"
GROUPS_URL = "https://groups.roblox.com/v1"
PRESENCE_URL = "https://presence.roblox.com/v1"
THUMBNAILS_URL = "https://thumbnails.roblox.com/v1"

TIMEOUT = 15
CACHE_TTL = 300
CACHE_LIMIT = 256
USERNAME = re.compile(r"[A-Za-z0-9_]{3,20}")

HEADERS = {
    "accept": "application/json",
    "user-agent": "sekai-roblox/1.0",
}

PRESENCE_KINDS = {0: "offline", 1: "online", 2: "game", 3: "studio"}

_cache: dict[str, tuple[float, object]] = {}


class RobloxError(Exception):
    """Roblox data couldn't be loaded."""


class RobloxNotFound(RobloxError):
    """The player doesn't exist."""


@dataclass(frozen=True, slots=True)
class RobloxGroup:
    id: int
    name: str
    role: str
    rank: int
    members: int


@dataclass(frozen=True, slots=True)
class RobloxPresence:
    kind: str
    location: str | None
    place_id: int | None

    @property
    def game_url(self) -> str | None:
        if self.place_id is None:
            return None
        return f"https://www.roblox.com/games/{self.place_id}"


@dataclass(frozen=True, slots=True)
class RobloxUser:
    id: int
    username: str
    display_name: str
    description: str
    created: datetime | None
    verified: bool
    banned: bool
    followers: int
    following: int
    friends: int
    groups: list[RobloxGroup]
    presence: RobloxPresence | None
    avatar_url: str | None
    headshot_url: str | None

    @property
    def url(self) -> str:
        return f"https://www.roblox.com/users/{self.id}/profile"


def _cached(key: str):
    entry = _cache.get(key)
    if entry is None or time.monotonic() - entry[0] >= CACHE_TTL:
        return None
    return entry[1]


def _remember(key: str, value) -> None:
    if len(_cache) >= CACHE_LIMIT:
        oldest = min(_cache, key=lambda item: _cache[item][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.monotonic(), value)


def _time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    payload: dict | None = None):
    try:
        async with session.request(
            method, url, json=payload, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status in {204, 404}:
                return None
            if response.status == 429:
                raise RobloxError(
                    "Roblox is limiting lookups right now — try again in a minute."
                )
            if response.status != 200:
                raise RobloxError(
                    f"Roblox returned an error (`{response.status}`)."
                )
            return await response.json(content_type=None)
    except RobloxError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise RobloxError(
            "Couldn't reach Roblox — try again in a moment."
        ) from exc


async def _optional(
    session: aiohttp.ClientSession, method: str, url: str, payload=None
):
    try:
        return await _request(session, method, url, payload)
    except RobloxError:
        return None


async def _lookup(
    session: aiohttp.ClientSession, name: str
) -> tuple[int, str] | None:
    data = await _request(
        session,
        "POST",
        f"{USERS_URL}/usernames/users",
        {"usernames": [name], "excludeBannedUsers": False})
    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id"):
            username = str(entry.get("name") or "")
            if username.lower() == name.lower():
                return _int(entry["id"]), username
    entry = entries[0]
    if isinstance(entry, dict) and entry.get("id"):
        return _int(entry["id"]), str(entry.get("name") or name)
    return None


async def _count(session: aiohttp.ClientSession, user_id: int, kind: str) -> int:
    data = await _optional(
        session, "GET", f"{FRIENDS_URL}/users/{user_id}/{kind}/count"
    )
    return _int(data.get("count")) if isinstance(data, dict) else 0


async def _groups(
    session: aiohttp.ClientSession, user_id: int
) -> list[RobloxGroup]:
    data = await _optional(
        session, "GET", f"{GROUPS_URL}/users/{user_id}/groups/roles"
    )
    rows = data.get("data") if isinstance(data, dict) else None
    groups: list[RobloxGroup] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        group = row.get("group")
        role = row.get("role")
        if not isinstance(group, dict) or not group.get("id"):
            continue
        groups.append(
            RobloxGroup(
                id=_int(group["id"]),
                name=str(group.get("name") or "Unknown group"),
                role=str(role.get("name") or "Member")
                if isinstance(role, dict)
                else "Member",
                rank=_int(role.get("rank")) if isinstance(role, dict) else 0,
                members=_int(group.get("memberCount")))
        )
    groups.sort(key=lambda item: (item.rank, item.members), reverse=True)
    return groups


async def _presence(
    session: aiohttp.ClientSession, user_id: int
) -> RobloxPresence | None:
    data = await _optional(
        session,
        "POST",
        f"{PRESENCE_URL}/presence/users",
        {"userIds": [user_id]})
    rows = data.get("userPresences") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    place = row.get("placeId")
    return RobloxPresence(
        kind=PRESENCE_KINDS.get(_int(row.get("userPresenceType")), "offline"),
        location=str(row.get("lastLocation") or "") or None,
        place_id=_int(place) if place is not None else None)


async def _thumbnail(
    session: aiohttp.ClientSession, kind: str, user_id: int, size: str
) -> str | None:
    url = (
        f"{THUMBNAILS_URL}/users/{kind}?userIds={user_id}"
        f"&size={size}&format=Png&isCircular=false"
    )
    for attempt in range(2):
        data = await _optional(session, "GET", url)
        rows = data.get("data") if isinstance(data, dict) else None
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            row = rows[0]
            image = row.get("imageUrl")
            if row.get("state") == "Completed" and isinstance(image, str):
                return image
        if attempt == 0:
            await asyncio.sleep(1)
    return None


async def fetch_user(username: str) -> RobloxUser:
    name = username.strip().removeprefix("@")
    if not USERNAME.fullmatch(name):
        raise RobloxNotFound(f"`{name}` isn't a valid Roblox username.")

    key = f"user:{name.lower()}"
    cached = _cached(key)
    if cached is not None:
        return cached

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        identity = await _lookup(session, name)
        if identity is None:
            raise RobloxNotFound(f"No Roblox account named `{name}`.")
        user_id, real_name = identity

        details = await _request(
            session, "GET", f"{USERS_URL}/users/{user_id}"
        )
        if not isinstance(details, dict):
            raise RobloxError(
                "Roblox didn't return that profile — try again."
            )

        followers, following, friends, groups, presence, avatar, headshot = (
            await asyncio.gather(
                _count(session, user_id, "followers"),
                _count(session, user_id, "followings"),
                _count(session, user_id, "friends"),
                _groups(session, user_id),
                _presence(session, user_id),
                _thumbnail(session, "avatar", user_id, "720x720"),
                _thumbnail(session, "avatar-headshot", user_id, "420x420"))
        )

    result = RobloxUser(
        id=user_id,
        username=str(details.get("name") or real_name),
        display_name=str(details.get("displayName") or real_name),
        description=str(details.get("description") or "").strip(),
        created=_time(details.get("created")),
        verified=bool(details.get("hasVerifiedBadge")),
        banned=bool(details.get("isBanned")),
        followers=followers,
        following=following,
        friends=friends,
        groups=groups,
        presence=presence,
        avatar_url=avatar,
        headshot_url=headshot)
    _remember(key, result)
    return result
