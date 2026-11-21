"""Random images and text from the PurrBot API (https://purrbot.site/).

Covers the whole v2 API: `img/sfw|nsfw/<path>/<kind>` (one random link per
call, so results are deliberately never cached), `list/sfw|nsfw/<path>/<kind>`
and the API info document. The documented `/v2/info` endpoint answers 404, so
info comes from the API root, which serves the same document.
"""

import asyncio

import aiohttp

SOURCE = "purrbot.site"
BASE_URL = "https://api.purrbot.site/v2"
INFO_URL = "https://api.purrbot.site"
TIMEOUT = 10
MAX_TEXT = 500

HEADERS = {
    "accept": "application/json",
    "user-agent": "sekai-social/1.0",
}


class PurrbotError(Exception):
    """The PurrBot API couldn't be reached or returned an error."""


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _section(nsfw: bool) -> str:
    return "nsfw" if nsfw else "sfw"


async def _request(
    session: aiohttp.ClientSession,
    url: str,
    params: dict | None = None) -> dict:
    status = 0
    data = None
    try:
        async with session.get(
            url, params=params, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as response:
            status = response.status
            data = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise PurrbotError(
            "Couldn't reach purrbot.site — try again in a moment."
        ) from exc

    if not isinstance(data, dict):
        raise PurrbotError(
            f"purrbot.site returned an unexpected response (`{status}`)."
        )
    if data.get("error"):
        message = data.get("message")
        raise PurrbotError(
            str(message) if message else f"purrbot.site returned an error (`{status}`)."
        )
    return data


async def fetch_image(path: str, kind: str = "gif", *, nsfw: bool = False) -> str:
    """One random image link for a PurrBot path, e.g. `hug`, `neko` or `anal`."""

    url = f"{BASE_URL}/img/{_section(nsfw)}/{path}/{kind}"
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        data = await _request(session, url)

    link = data.get("link")
    if not isinstance(link, str) or not link:
        raise PurrbotError("purrbot.site didn't return an image — try again.")
    return link


async def fetch_list(
    path: str, kind: str = "gif", *, nsfw: bool = False
) -> list[str]:
    """Every image link PurrBot has for a path."""

    url = f"{BASE_URL}/list/{_section(nsfw)}/{path}/{kind}"
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        data = await _request(session, url)

    links = data.get("links")
    if not isinstance(links, list) or not links:
        raise PurrbotError("purrbot.site didn't return any images — try again.")
    return [link for link in links if isinstance(link, str)]


async def fetch_info() -> dict:
    """Name, version, licence and links of the API itself."""

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        return await _request(session, INFO_URL)


async def owoify(
    text: str,
    *,
    replace_words: bool = True,
    stutter: bool = True,
    emoticons: bool = True) -> str:
    """Rewrite text with PurrBot's OwOify filter."""

    params = {
        "text": text,
        "replace-words": _flag(replace_words),
        "stutter": _flag(stutter),
        "emoticons": _flag(emoticons),
    }
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        data = await _request(session, f"{BASE_URL}/owoify", params)

    result = data.get("text")
    if not isinstance(result, str):
        raise PurrbotError("purrbot.site didn't return any text — try again.")
    return result
