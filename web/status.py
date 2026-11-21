import asyncio
import datetime
import hmac
import html
import json
import logging
import math
import os
import platform
import secrets
import sys
import time
from collections import deque
from typing import TYPE_CHECKING, Any

import discord
import psutil
from aiohttp import web

from config.nodelink import NODELINKS
from config.settings import BASE_DIR, settings
from config.web import OWNER_PAGE_PASSWORD
from core import music
from src.verification.state import website_configured
from web.design import document
from web.https import enforce_https
from web.status_page import render_status_page

if TYPE_CHECKING:
    from core.bot import SekaiBot

log = logging.getLogger("sekai.status")

# /owner is locked behind this password. Unset means the page always refuses.
OWNER_PASSWORD = OWNER_PAGE_PASSWORD
OWNER_COOKIE = "owner_session"
_OWNER_SESSIONS: dict[str, float] = {}   # token -> expiry (monotonic)
_OWNER_SESSION_TTL = 3600.0              # 1 hour
OWNER_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
}

_PROCESS = psutil.Process()
_START_TIME = _PROCESS.create_time()

# One sample a minute, capped at 6 hours (was 24h; halved for 1 GB VPS).
SAMPLE_INTERVAL = 60
HISTORY: deque[dict[str, Any]] = deque(maxlen=6 * 60)

# Prime the non-blocking CPU counters so the first reading is not 0.0.
psutil.cpu_percent(interval=None)
_PROCESS.cpu_percent(interval=None)


def _latency_ms(bot: "SekaiBot") -> float | None:
    latency = bot.latency
    if latency is None or math.isnan(latency):
        return None
    return round(latency * 1000, 1)


def _load_1m() -> float | None:
    try:
        return round(psutil.getloadavg()[0], 2)
    except (AttributeError, OSError):
        return None


def _serving(bot: "SekaiBot", runner_attr: str) -> bool:
    runner = getattr(bot, runner_attr, None)
    if runner is None:
        return False
    addresses = getattr(runner, "addresses", None)
    return bool(addresses) if addresses is not None else True


def collect_status(bot: "SekaiBot") -> dict[str, Any]:
    online = bot.user is not None
    now = time.time()

    memory = _PROCESS.memory_info()
    disk = psutil.disk_usage(str(BASE_DIR))
    virtual = psutil.virtual_memory()

    guilds = bot.guilds
    users = sum(guild.member_count or 0 for guild in guilds)
    channels = sum(len(guild.channels) for guild in guilds)
    commands = len(bot.commands)

    started_at = datetime.datetime.fromtimestamp(_START_TIME, datetime.timezone.utc)
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), datetime.timezone.utc)

    tunnel = getattr(bot, "tunnel", None)

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bot": {
            "name": settings.bot_name,
            "tag": str(bot.user) if bot.user else None,
            "id": bot.user.id if bot.user else None,
            "online": online,
            "dev_mode": bot.dev,
            "latency_ms": _latency_ms(bot),
            "uptime_seconds": round(now - _START_TIME),
            "started_at": started_at.isoformat(),
        },
        "counts": {
            "guilds": len(guilds),
            "users": users,
            "channels": channels,
            "commands": commands,
        },
        "process": {
            "pid": _PROCESS.pid,
            "memory_mb": round(memory.rss / 1024 / 1024, 1),
            "memory_percent": round(_PROCESS.memory_percent(), 2),
            "cpu_percent": round(_PROCESS.cpu_percent(interval=None), 1),
            "threads": _PROCESS.num_threads(),
            "started_at": started_at.isoformat(),
        },
        "system": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "discordpy": discord.__version__,
            "cpu_cores": psutil.cpu_count(logical=True),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "load_1m": _load_1m(),
            "memory_used_mb": round(virtual.used / 1024 / 1024, 1),
            "memory_total_mb": round(virtual.total / 1024 / 1024, 1),
            "memory_percent": virtual.percent,
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_percent": disk.percent,
            "boot_time": boot_time.isoformat(),
            "uptime_seconds": round(now - psutil.boot_time()),
        },
        "websites": {
            "main": {
                "url": settings.website_url,
                "running": _serving(bot, "_web_runner"),
            },
            "tickets": {
                "url": settings.transcript_url,
                "running": _serving(bot, "_transcript_runner"),
            },
            "verify": {
                "url": settings.verify_base_url,
                "running": _serving(bot, "_verify_runner"),
                "configured": website_configured(bot),
            },
        },
        "services": {
            "tunnel": {
                "enabled": not bot.dev,
                "running": bool(tunnel and tunnel.running),
            },
            "nodelink": {
                "online": len(music.connected_nodes()),
                "total": len(NODELINKS),
            },
        },
        "music": music.music_status(),
    }


def _sample(bot: "SekaiBot") -> None:
    HISTORY.append(
        {
            "t": int(time.time()),
            "latency_ms": _latency_ms(bot),
            "online": bot.user is not None,
        }
    )


async def _sampler(bot: "SekaiBot") -> None:
    while True:
        try:
            _sample(bot)
        except Exception:
            log.exception("Status history sample failed")
        await asyncio.sleep(SAMPLE_INTERVAL)


def _owner_login_page(error: bool = False) -> str:
    note = '<p class="bad">Wrong password.</p>' if error else ""
    body = (
        '<h1>Owner</h1>' + note +
        '<form method="post" action="/owner/login" class="stack">'
        '<input type="password" name="password" required autofocus>'
        '<button class="btn primary" type="submit">Unlock</button></form>'
    )
    return document("Owner", body, brand_footer=False, fonts=False)


def _owner_page(bot: "SekaiBot") -> str:
    data = html.escape(json.dumps(collect_status(bot), indent=2))
    body = (
        '<h1>Owner dashboard</h1>'
        f'<pre class="card mono" style="overflow:auto">{data}</pre>'
    )
    return document("Owner", body, brand_footer=False, fonts=False)


def create_status_app(bot: "SekaiBot") -> web.Application:
    app = web.Application(middlewares=[enforce_https(settings.status_url)])

    async def api_history(_: web.Request) -> web.Response:
        return web.json_response({"interval_seconds": SAMPLE_INTERVAL, "points": list(HISTORY)})

    async def index(_: web.Request) -> web.Response:
        return web.Response(text=render_status_page(), content_type="text/html")

    async def api_status(_: web.Request) -> web.Response:
        return web.json_response(collect_status(bot))

    async def health(_: web.Request) -> web.Response:
        online = bot.user is not None
        return web.json_response(
            {
                "status": "online" if online else "starting",
                "uptime_seconds": round(time.time() - _START_TIME),
            }
        )

    def _signed_in(request: web.Request) -> bool:
        token = request.cookies.get(OWNER_COOKIE, "")
        if not OWNER_PASSWORD or not token:
            return False
        expiry = _OWNER_SESSIONS.get(token)
        if expiry is None or time.monotonic() > expiry:
            _OWNER_SESSIONS.pop(token, None)
            return False
        return True

    async def owner_get(request: web.Request) -> web.Response:
        if not _signed_in(request):
            return web.Response(text=_owner_login_page(), content_type="text/html", headers=OWNER_HEADERS)
        return web.Response(text=_owner_page(bot), content_type="text/html", headers=OWNER_HEADERS)

    async def owner_login(request: web.Request) -> web.Response:
        form = await request.post()
        given = str(form.get("password", ""))
        if not OWNER_PASSWORD or not hmac.compare_digest(given, OWNER_PASSWORD):
            return web.Response(text=_owner_login_page(error=True), content_type="text/html", status=401, headers=OWNER_HEADERS)
        token = secrets.token_urlsafe(32)
        _OWNER_SESSIONS[token] = time.monotonic() + _OWNER_SESSION_TTL
        response = web.HTTPSeeOther("/owner")
        response.set_cookie(OWNER_COOKIE, token, httponly=True, secure=True, samesite="Strict", path="/owner")
        raise response

    app.router.add_get("/owner", owner_get)
    app.router.add_post("/owner/login", owner_login)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/history", api_history)
    app.router.add_get("/health", health)
    return app


async def start_status_server(
    bot: "SekaiBot", host: str, port: int
) -> web.AppRunner:
    runner = web.AppRunner(create_status_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    asyncio.get_running_loop().create_task(_sampler(bot))
    log.info("Status page: http://%s:%s/  (dashboard + /api/status)", host, port)
    return runner
