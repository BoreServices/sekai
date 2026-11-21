import asyncio
import base64
import logging
import re
import time
from contextlib import suppress
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import settings

log = logging.getLogger("sekai.emojis")

SUFFIXES = {".png", ".jpg", ".jpeg", ".gif"}
MAX_BYTES = 256 * 1024
WATCH_INTERVAL = 30.0
MAX_WATCH_INTERVAL = 300.0

# name -> id, filled by sync_application_emojis so embeds can reference the
# bot's own emojis without a Discord call at render time.
APPLICATION_EMOJIS: dict[str, str] = {}


def emoji_image(name: str) -> str | None:
    emoji_id = APPLICATION_EMOJIS.get(name.lower())
    if emoji_id is None:
        return None
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.png"


_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}
_DATA_URI_PATHS: dict[str, Path] = {}
_DATA_URI_REFRESHED = 0.0
_DATA_URI_CACHE: dict[str, tuple[tuple[int, int], str]] = {}


def emoji_data_uri(name: str) -> str | None:
    """Local emoji file as a data URI, so HTML transcripts are self-contained."""
    global _DATA_URI_REFRESHED
    now = time.monotonic()
    if now - _DATA_URI_REFRESHED >= 60:
        _DATA_URI_PATHS.clear()
        folder: Path = settings.emoji_dir
        if folder.is_dir():
            for path in folder.iterdir():
                if path.is_file() and path.suffix.lower() in SUFFIXES:
                    _DATA_URI_PATHS[emoji_name(path.stem)] = path
        _DATA_URI_REFRESHED = now

    key = name.lower()
    path = _DATA_URI_PATHS.get(key)
    if path is None:
        return None
    with suppress(OSError):
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = _DATA_URI_CACHE.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        mime = _MIME_TYPES[path.suffix.lower()]
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        uri = f"data:{mime};base64,{data}"
        _DATA_URI_CACHE[key] = (stamp, uri)
        return uri
    return None


def emoji_markdown(name: str) -> str | None:
    emoji_id = APPLICATION_EMOJIS.get(name.lower())
    if emoji_id is None:
        return None
    return f"<:{name.lower()}:{emoji_id}>"


def emoji_partial(name: str) -> discord.PartialEmoji | None:
    emoji_id = APPLICATION_EMOJIS.get(name.lower())
    if emoji_id is None:
        return None
    try:
        return discord.PartialEmoji(name=name.lower(), id=int(emoji_id))
    except ValueError:
        return None


def markup(name: str, fallback: str = "") -> str:
    """Custom application emoji for message/embed text, or a Unicode fallback."""
    return emoji_markdown(name) or fallback


# Unicode stand-ins mapped to the bot's own emoji. Embed builders run text
# through iconize(), so no embed shows a plain system emoji when the matching
# application emoji exists.
UNICODE_NAMES: dict[str, str] = {
    "✅": "checkmark",
    "✔️": "checkmark",
    "✔": "checkmark",
    "☑️": "checkmark",
    "☑": "checkmark",
    "🟢": "checkmark",
    "🔓": "checkmark",
    "❌": "crossmark",
    "❎": "crossmark",
    "✖️": "crossmark",
    "✖": "crossmark",
    "🚫": "crossmark",
    "⛔": "crossmark",
    "👢": "crossmark",
    "🔨": "crossmark",
    "⏹️": "crossmark",
    "⏹": "crossmark",
    "🛑": "crossmark",
    "🔴": "crossmark",
    "⚠️": "warning",
    "⚠": "warning",
    "🟡": "warning",
    "⚫": "warning",
    "❗": "warning",
    "❕": "warning",
    "💡": "warning",
    "❓": "warning",
    "❔": "warning",
    "🔞": "warning",
    "🚨": "textwarning",
    "➕": "plus",
    "➖": "minus",
    "🗑️": "trash",
    "🗑": "trash",
    "🧹": "trash",
    "👑": "crown",
    "🏆": "crown",
    "🥇": "crown",
    "🛡️": "shield",
    "🛡": "shield",
    "🔒": "shield",
    "🔐": "shield",
    "🔑": "shield",
    "⚙️": "settings",
    "⚙": "settings",
    "🎚️": "settings",
    "🎚": "settings",
    "🎛️": "settings",
    "🎨": "settings",
    "🔧": "wrench",
    "🔩": "wrench",
    "🧰": "wrench",
    "📊": "settings",
    "🎵": "music",
    "🎶": "music",
    "🎧": "music",
    "🔊": "music",
    "🔈": "music",
    "🔉": "music",
    "🎙️": "music",
    "🎙": "music",
    "▶️": "music",
    "▶": "music",
    "⏭️": "music",
    "⏭": "music",
    "📝": "paper",
    "📄": "paper",
    "📜": "paper",
    "📋": "paper",
    "📁": "paper",
    "📚": "paper",
    "🖼️": "paper",
    "🖼": "paper",
    "📎": "paper",
    "📖": "paper",
    "🔗": "paper",
    "🔖": "paper",
    "🆔": "paper",
    "🏷️": "paper",
    "🏷": "paper",
    "🗄️": "paper",
    "🗄": "paper",
    "💬": "paper",
    "🧵": "paper",
    "📰": "paper",
    "🎫": "ticket",
    "📌": "pin",
    "📍": "pin",
    "📮": "pin",
    "🔔": "pin",
    "🔄": "refresh",
    "🔁": "refresh",
    "🔀": "refresh",
    "🔍": "refresh",
    "🔎": "refresh",
    "🌐": "server",
    "🏠": "server",
    "🖥️": "server",
    "🖥": "server",
    "📡": "server",
    "🛰️": "server",
    "🛰": "server",
    "🌍": "server",
    "👤": "user",
    "👥": "user",
    "🙋": "user",
    "🎭": "user",
    "🎯": "user",
    "🎮": "gamecontroller",
    "🕹️": "gamecontroller",
    "🕹": "gamecontroller",
    "👋": "slightlysmilingface",
    "🙂": "slightlysmilingface",
    "😐": "facewithdiagonalmouth",
    "😑": "facewithdiagonalmouth",
    "🎉": "confetti",
    "🥳": "confetti",
    "🎁": "gift",
    "⭐": "star",
    "🌟": "star",
    "🔥": "fire",
    "💣": "fire",
    "💥": "fire",
    "🚀": "fire",
    "⏸️": "timer",
    "⏸": "timer",
    "⏱️": "timer",
    "⏱": "timer",
    "⏲️": "timer",
    "⏲": "timer",
    "⏳": "timer",
    "⌛": "timer",
    "🏓": "timer",
    "📶": "timer",
    "📅": "timer",
    "📆": "timer",
    "📥": "timer",
    "🐌": "timer",
    "🔇": "timer",
    "✏️": "paper",
    "✏": "paper",
    "🤖": "robot",
    "🧠": "robot",
    "🐛": "bug",
    # --- additional mappings ---
    # lock / unlock  →  shield
    "🔒": "shield",
    "🔓": "shield",
    # door / goodbye  →  slightlysmilingface (wave goodbye)
    "🚪": "slightlysmilingface",
    # roles / theatre  →  user
    "🎭": "user",
    # shopping cart  →  gift
    "🛒": "gift",
    # sparkle  →  star
    "✨": "star",
    # eye  →  settings (visibility control)
    "👁️": "settings",
    "👁": "settings",
    # hide / see-no-evil  →  crossmark
    "🙈": "crossmark",
    # bell / notification  →  pin
    "🔔": "pin",
    "🔕": "pin",
    # alarm clock  →  timer
    "⏰": "timer",
    # up/down arrows  →  plus / minus
    "⬆️": "plus",
    "⬆": "plus",
    "⬇️": "minus",
    "⬇": "minus",
    # games / billiards  →  gamecontroller
    "🎱": "gamecontroller",
    # keycap / 1234  →  paper
    "🔢": "paper",
    # rock-paper-scissors
    "🪨": "gamecontroller",
    "✂️": "crossmark",
    "✂": "crossmark",
    "✊": "gamecontroller",
    "⭕": "checkmark",
    # age-restricted  →  warning
    "🔞": "warning",
    # frame / picture  →  paper
    "🖼️": "paper",
    "🖼": "paper",
    # speech bubble / chat  →  paper
    "💬": "paper",
    # paw print  →  slightlysmilingface
    "🐾": "slightlysmilingface",
    # smiley  →  slightlysmilingface
    "🙂": "slightlysmilingface",
    # bitrate / slider  →  settings
    "🎚️": "settings",
    "🎚": "settings",
}

_UNICODE_PATTERN: re.Pattern[str] | None = None


def _unicode_pattern() -> re.Pattern[str]:
    global _UNICODE_PATTERN
    if _UNICODE_PATTERN is None:
        keys = sorted(UNICODE_NAMES, key=len, reverse=True)
        _UNICODE_PATTERN = re.compile("|".join(re.escape(key) for key in keys))
    return _UNICODE_PATTERN


def iconize(text: str) -> str:
    """Return text unchanged so emoji in embeds stay fully manual."""
    return text


def emoji_name(stem: str) -> str:
    name = re.sub(r"[^a-z0-9_]", "_", stem.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    if len(name) < 2:
        name = f"emoji_{name}" if name else "emoji"
    return name[:32]


async def sync_application_emojis(bot: commands.Bot) -> bool:
    """Upload new files from the emoji folder. Returns False if a retry is useful."""
    folder: Path = settings.emoji_dir
    if not folder.is_dir():
        log.info("No emoji folder at %s, skipping emoji sync", folder)
        return True

    try:
        emojis = await bot.fetch_application_emojis()
    except discord.HTTPException as exc:
        log.warning("Could not list application emojis: %s", exc)
        return False
    existing = {emoji.name.lower(): str(emoji.id) for emoji in emojis}
    APPLICATION_EMOJIS.update(existing)

    failed = False
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        name = emoji_name(path.stem)
        if name in existing:
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            log.warning("Skipping %s: %d bytes exceeds 256 KiB", path.name, size)
            continue
        try:
            emoji = await bot.create_application_emoji(
                name=name, image=path.read_bytes()
            )
        except discord.HTTPException as exc:
            log.warning("Could not upload %s: %s", path.name, exc)
            failed = True
            continue
        existing[name] = str(emoji.id)
        APPLICATION_EMOJIS[name] = str(emoji.id)
        log.info("Uploaded application emoji :%s: (id %s)", emoji.name, emoji.id)
    return not failed


def _snapshot(folder: Path) -> tuple[tuple[str, int, int], ...]:
    entries = []
    try:
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                continue
            stat = path.stat()
            entries.append((path.name, stat.st_size, stat.st_mtime_ns))
    except OSError:
        return ()
    return tuple(entries)


async def _watch_emojis(
    bot: commands.Bot,
    interval: float,
    last: tuple[tuple[str, int, int], ...] | None) -> None:
    folder: Path = settings.emoji_dir
    delay = interval
    while True:
        await asyncio.sleep(delay)
        current = _snapshot(folder)
        if current == last:
            delay = interval
            continue
        try:
            synced = await sync_application_emojis(bot)
        except Exception:
            log.exception("Emoji sync crashed")
            synced = False
        if synced:
            last = current
            delay = interval
        else:
            delay = min(delay * 2, MAX_WATCH_INTERVAL)


def start_emoji_watcher(
    bot: commands.Bot,
    interval: float = WATCH_INTERVAL,
    *,
    synced: bool = True) -> asyncio.Task:
    last = _snapshot(settings.emoji_dir) if synced else None
    return asyncio.create_task(
        _watch_emojis(bot, interval, last), name="emoji-watcher"
    )
