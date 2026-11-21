"""Pinterest lookups through the public profile and board pages.

Each public page embeds its first batch of data in a <script> tag. Further
pages come from Pinterest's resource endpoints, which accept the cookies and
CSRF token picked up from that first page.
"""

import asyncio
import email.utils
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse

import aiohttp

BASE_URL = "https://www.pinterest.com"
TIMEOUT = 20
CACHE_TTL = 300
CACHE_LIMIT = 128
PAGE_SIZE = 50
MAX_PIN_PAGES = 12
MAX_BOARD_PAGES = 4

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

_PROPS = re.compile(
    r'<script id="__PWS_INITIAL_PROPS__" type="application/json">(.*?)</script>',
    re.DOTALL)
_USERNAME = re.compile(r"[A-Za-z0-9_]{1,64}")
_BOARD = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_NOT_BOARD = {"pins", "boards", "saved", "_saved", "followers", "following"}
_NOT_PROFILE = {"pin", "ideas", "search"}

_cache: dict[str, tuple[float, object]] = {}


class PinterestError(Exception):
    """Pinterest didn't return usable data."""


class PinterestNotFound(PinterestError):
    """The profile or board doesn't exist."""


@dataclass(frozen=True, slots=True)
class PinterestUser:
    username: str
    full_name: str
    about: str
    followers: int
    following: int
    pin_count: int
    board_count: int
    avatar_url: str | None
    website: str | None
    created_at: datetime | None
    verified: bool
    private: bool

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.username}/"


@dataclass(frozen=True, slots=True)
class PinterestBoard:
    id: str
    name: str
    url_path: str
    pin_count: int
    followers: int
    description: str
    cover_url: str | None
    privacy: str
    created_at: datetime | None

    @property
    def url(self) -> str:
        path = self.url_path if self.url_path.startswith("/") else f"/{self.url_path}"
        return f"{BASE_URL}{path}"


@dataclass(frozen=True, slots=True)
class PinterestPin:
    id: str
    image_url: str | None
    thumb_url: str | None
    title: str = ""
    link: str | None = None

    @property
    def url(self) -> str | None:
        if self.id.isdigit():
            return f"{BASE_URL}/pin/{self.id}/"
        return None


@dataclass(frozen=True, slots=True)
class ProfileResult:
    user: PinterestUser
    boards: list[PinterestBoard]
    pins: list[PinterestPin]


@dataclass(frozen=True, slots=True)
class BoardResult:
    board: PinterestBoard
    pins: list[PinterestPin]


def parse_target(text: str) -> tuple[str, str | None] | None:
    """Return (username, board) from a profile/board URL, @handle or name."""
    text = text.strip()
    if not text:
        return None
    lowered = text.lower()
    if "pinterest." in lowered or lowered.startswith("www."):
        if "://" not in text:
            text = f"https://{text}"
        parts = [unquote(part) for part in urlparse(text).path.split("/") if part]
    else:
        parts = [unquote(part) for part in text.strip("/").split("/") if part]
    if not parts or parts[0].lower() in _NOT_PROFILE:
        return None

    username = parts[0].lstrip("@")
    if not _USERNAME.fullmatch(username):
        return None

    board = None
    if len(parts) > 1 and parts[1].lower() not in _NOT_BOARD:
        board = parts[1]
        if not _BOARD.fullmatch(board):
            return None
    return username, board


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _image(images, key: str) -> str | None:
    item = images.get(key) if isinstance(images, dict) else None
    if isinstance(item, dict):
        url = item.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _user(raw: dict) -> PinterestUser:
    identity = raw.get("verified_identity")
    verified = isinstance(identity, dict) and bool(identity.get("verified"))
    return PinterestUser(
        username=str(raw.get("username") or ""),
        full_name=str(raw.get("full_name") or raw.get("first_name") or "").strip(),
        about=str(raw.get("about") or "").strip(),
        followers=_int(raw.get("follower_count")),
        following=_int(raw.get("following_count")),
        pin_count=_int(raw.get("pin_count")),
        board_count=_int(raw.get("board_count")),
        avatar_url=raw.get("image_xlarge_url") or raw.get("image_medium_url"),
        website=raw.get("website_url"),
        created_at=_time(raw.get("created_at")),
        verified=(
            verified
            or bool(raw.get("domain_verified"))
            or bool(raw.get("is_verified_merchant"))
        ),
        private=bool(raw.get("is_private_profile")))


def _board(raw: dict, fallback_username: str = "") -> PinterestBoard:
    owner = raw.get("owner") if isinstance(raw.get("owner"), dict) else {}
    owner_name = str(owner.get("username") or fallback_username)
    name = str(raw.get("name") or "").strip() or "Untitled board"
    url_path = raw.get("url")
    if not isinstance(url_path, str) or not url_path.startswith("/"):
        url_path = f"/{owner_name}/{_slug(name)}/"
    return PinterestBoard(
        id=str(raw.get("id") or ""),
        name=name,
        url_path=url_path,
        pin_count=_int(raw.get("pin_count")),
        followers=_int(raw.get("follower_count")),
        description=str(raw.get("description") or "").strip(),
        cover_url=raw.get("image_cover_hd_url") or raw.get("image_cover_url"),
        privacy=str(raw.get("privacy") or "public"),
        created_at=_time(raw.get("created_at")))


def _pin(raw: dict) -> PinterestPin | None:
    images = raw.get("images") or {}
    image_url = (
        _image(images, "736x")
        or _image(images, "474x")
        or _image(images, "orig")
        or _image(images, "236x")
    )
    if image_url is None:
        return None
    link = raw.get("link")
    return PinterestPin(
        id=str(raw.get("id") or ""),
        image_url=image_url,
        thumb_url=_image(images, "236x") or image_url,
        title=str(raw.get("title") or raw.get("grid_title") or "").strip(),
        link=link if isinstance(link, str) and link else None)


def _pins_from(raw_pins) -> list[PinterestPin]:
    pins: list[PinterestPin] = []
    seen: set[str] = set()
    for raw in raw_pins:
        if not isinstance(raw, dict):
            continue
        pin = _pin(raw)
        if pin is None:
            continue
        key = pin.id or pin.image_url or ""
        if key in seen:
            continue
        seen.add(key)
        pins.append(pin)
    return pins


def _merge_pins(
    primary: list[PinterestPin], extra: list[PinterestPin]
) -> list[PinterestPin]:
    merged = list(primary)
    seen = {pin.id or pin.image_url or "" for pin in merged}
    for pin in extra:
        key = pin.id or pin.image_url or ""
        if key in seen:
            continue
        seen.add(key)
        merged.append(pin)
    return merged


def _merge_boards(
    primary: list[PinterestBoard], extra: list[PinterestBoard]
) -> list[PinterestBoard]:
    merged = list(primary)
    seen = {board.id or board.url_path for board in merged}
    for board in extra:
        key = board.id or board.url_path
        if key in seen:
            continue
        seen.add(key)
        merged.append(board)
    return merged


def _boards(state: dict, username: str) -> list[PinterestBoard]:
    wanted = username.lower()
    boards: list[PinterestBoard] = []
    for raw in (state.get("boards") or {}).values():
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("name"):
            continue
        owner = raw.get("owner")
        owner_name = (
            str(owner.get("username") or "").lower()
            if isinstance(owner, dict)
            else ""
        )
        if owner_name and owner_name != wanted:
            continue
        boards.append(_board(raw, fallback_username=username))
    return boards


def _pins(state: dict) -> list[PinterestPin]:
    return _pins_from((state.get("pins") or {}).values())


def _find_user(state: dict, username: str) -> PinterestUser:
    wanted = username.lower()
    for raw in (state.get("users") or {}).values():
        if not isinstance(raw, dict):
            continue
        if str(raw.get("username") or "").lower() == wanted:
            return _user(raw)
    raise PinterestNotFound(f"No Pinterest account named `{username}`.")


def _resource_board(state: dict, fallback: str) -> PinterestBoard | None:
    resources = state.get("resources")
    if not isinstance(resources, dict):
        return None
    for payload in resources.values():
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and data.get("id") and data.get("name"):
            return _board(data, fallback_username=fallback)
    return None


def _resource_pins(state: dict) -> list[PinterestPin]:
    resources = state.get("resources")
    feed = resources.get("BoardFeedResource") if isinstance(resources, dict) else None
    if not isinstance(feed, dict):
        return []
    for payload in feed.values():
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            continue
        pins = _pins_from(data)
        if pins:
            return pins
    return []


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


def _session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers=HEADERS, cookie_jar=aiohttp.CookieJar(unsafe=True)
    )


def _csrf(session: aiohttp.ClientSession) -> str:
    for cookie in session.cookie_jar:
        if cookie.key == "csrftoken":
            return cookie.value
    return ""


async def _load(session: aiohttp.ClientSession, path: str) -> dict:
    try:
        async with session.get(
            f"{BASE_URL}{path}", timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status in {403, 429}:
                raise PinterestError(
                    "Pinterest is limiting lookups right now — try again "
                    "in a minute."
                )
            if response.status == 404:
                raise PinterestNotFound("That Pinterest page doesn't exist.")
            if response.status != 200:
                raise PinterestError(
                    f"Pinterest returned an error (`{response.status}`)."
                )
            html = await response.text()
    except PinterestError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise PinterestError(
            "Couldn't reach Pinterest — try again in a moment."
        ) from exc

    match = _PROPS.search(html)
    if match is None:
        raise PinterestError("Pinterest returned an unexpected page — try again.")
    try:
        props = json.loads(match.group(1))
    except ValueError as exc:
        raise PinterestError(
            "Pinterest returned an unexpected page — try again."
        ) from exc
    state = props.get("initialReduxState")
    if not isinstance(state, dict):
        raise PinterestError("Pinterest returned an unexpected page — try again.")
    return state


async def _resource(
    session: aiohttp.ClientSession,
    name: str,
    source: str,
    options: dict,
    handler: str) -> dict | None:
    payload = json.dumps({"options": options, "context": {}})
    url = (
        f"{BASE_URL}/resource/{name}/get/?source_url={quote(source, safe='')}"
        f"&data={quote(payload, safe='')}"
    )
    headers = {
        "x-csrftoken": _csrf(session),
        "x-requested-with": "XMLHttpRequest",
        "x-pinterest-pws-handler": handler,
        "x-pinterest-appstate": "active",
        "referer": f"{BASE_URL}{source}",
    }
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            if response.status != 200:
                return None
            body = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    result = body.get("resource_response")
    return result if isinstance(result, dict) else None


async def _paged_pins(
    session: aiohttp.ClientSession,
    name: str,
    source: str,
    options: dict,
    handler: str,
    max_pages: int) -> list[PinterestPin]:
    pins: list[PinterestPin] = []
    seen: set[str] = set()
    bookmark = None
    for _ in range(max_pages):
        page_options = dict(options)
        if bookmark:
            page_options["bookmarks"] = [bookmark]
        result = await _resource(session, name, source, page_options, handler)
        if result is None:
            break
        data = result.get("data")
        if not isinstance(data, list) or not data:
            break
        for pin in _pins_from(data):
            key = pin.id or pin.image_url or ""
            if key in seen:
                continue
            seen.add(key)
            pins.append(pin)
        bookmark = result.get("bookmark")
        if not bookmark:
            break
    return pins


async def _paged_boards(
    session: aiohttp.ClientSession, username: str, max_pages: int
) -> list[PinterestBoard]:
    boards: list[PinterestBoard] = []
    seen: set[str] = set()
    bookmark = None
    source = f"/{username}/boards/"
    for _ in range(max_pages):
        options = {
            "username": username,
            "page_size": PAGE_SIZE,
            "bookmarks": [bookmark] if bookmark else [],
            "field_set_key": "profile_grid_item",
        }
        result = await _resource(
            session, "BoardsResource", source, options, "www/[username]/boards.js"
        )
        if result is None:
            break
        data = result.get("data")
        if not isinstance(data, list) or not data:
            break
        for raw in data:
            if not isinstance(raw, dict) or not raw.get("id") or not raw.get("name"):
                continue
            board = _board(raw, fallback_username=username)
            key = board.id or board.url_path
            if key in seen:
                continue
            seen.add(key)
            boards.append(board)
        bookmark = result.get("bookmark")
        if not bookmark:
            break
    return boards


async def fetch_profile(username: str) -> ProfileResult:
    key = f"profile:{username.lower()}"
    cached = _cached(key)
    if cached is not None:
        return cached

    async with _session() as session:
        state = await _load(session, f"/{username}/")
        user = _find_user(state, username)
        boards = _boards(state, username)
        pins = _pins(state)

        more_boards = await _paged_boards(session, username, MAX_BOARD_PAGES)
        if more_boards:
            boards = _merge_boards(more_boards, boards)

        more_pins = await _paged_pins(
            session,
            "UserPinsResource",
            f"/{username}/pins/",
            {"username": username, "page_size": PAGE_SIZE, "bookmarks": []},
            "www/[username]/pins.js",
            MAX_PIN_PAGES)
        if more_pins:
            pins = _merge_pins(more_pins, pins)

    result = ProfileResult(user=user, boards=boards, pins=pins)
    _remember(key, result)
    return result


async def _board_page(session: aiohttp.ClientSession, path: str) -> BoardResult:
    key = f"board:{path.rstrip('/').lower()}"
    cached = _cached(key)
    if cached is not None:
        return cached

    state = await _load(session, path)
    parts = [part for part in path.strip("/").split("/") if part]
    fallback = parts[0] if parts else ""
    boards = []
    for raw in (state.get("boards") or {}).values():
        if isinstance(raw, dict) and raw.get("id") and raw.get("name"):
            boards.append(_board(raw, fallback_username=fallback))

    if not boards:
        board = _resource_board(state, fallback)
        if board is None:
            raise PinterestNotFound("That board doesn't exist or is private.")
        pins = _pins(state) or _resource_pins(state)
    else:
        target = path.rstrip("/").lower()
        board = next(
            (item for item in boards if item.url_path.rstrip("/").lower() == target),
            boards[0])
        pins = _pins(state) or _resource_pins(state)

    if board.id:
        more = await _paged_pins(
            session,
            "BoardFeedResource",
            path,
            {
                "board_id": board.id,
                "page_size": PAGE_SIZE,
                "bookmarks": [],
                "field_set_key": "react_grid_pin",
            },
            "www/[username]/[slug].js",
            MAX_PIN_PAGES)
        if more:
            pins = _merge_pins(more, pins)

    result = BoardResult(board=board, pins=pins)
    _remember(key, result)
    return result


async def fetch_board(username: str, board: str) -> BoardResult:
    value = board.strip().strip("/")
    if not value:
        raise PinterestNotFound("Tell me which board to open.")
    parts = [unquote(part) for part in value.split("/") if part]
    path = (
        f"/{parts[0]}/{parts[1]}/"
        if len(parts) >= 2
        else f"/{username}/{parts[0]}/"
    )

    try:
        async with _session() as session:
            return await _board_page(session, path)
    except PinterestNotFound:
        pass

    profile = await fetch_profile(username)
    wanted = _slug(parts[-1])
    for candidate in profile.boards:
        slug = candidate.url_path.rstrip("/").rsplit("/", 1)[-1]
        if wanted in {_slug(candidate.name), _slug(slug)}:
            async with _session() as session:
                return await _board_page(session, candidate.url_path)
    raise PinterestNotFound(f"@{username} has no board called `{parts[-1]}`.")
