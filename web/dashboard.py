"""Server control dashboard (port 8085 in production, 9085 with --dev).

A Discord-OAuth control panel. Anyone with a Discord account can sign in, but
each user only sees and manages the servers they own or administer
(Administrator / Manage Server). Users in
``config.owners.DASHBOARD_CONTROL_ALL_IDS`` manage every server.

Signed-in users can change the command prefix, toggle AutoMod filters, and
broadcast a message. Styling is the shared PhaseWorld system in ``web.design``
(the tokens described in ``theme.md``).
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

import aiohttp
import discord
from aiohttp import web

from config.owners import DASHBOARD_CONTROL_ALL_IDS, OWNER_IDS
from config.settings import settings
from config.token import DISCORD_CLIENT_SECRET
from core import prefix as prefixes
from src.automod import commands as automod_commands
from src.automod import state as automod_state
from web.dashboard_page import render_dashboard_page, render_login_page, render_notice_page
from web.https import enforce_https
from web.modules import apply_module, module_summaries, read_module
from web.owner_page import render_owner_page
from web.server_page import render_server_page

if TYPE_CHECKING:
    from core.bot import SekaiBot

log = logging.getLogger("sekai.dashboard")

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
ME_URL = "https://discord.com/api/users/@me"
OAUTH_TIMEOUT = aiohttp.ClientTimeout(total=15)

SESSION_COOKIE = "dashboard_session"
SESSION_TTL = 12 * 60 * 60.0   # 12 hours
STATE_TTL = 10 * 60.0          # 10 minutes
MAX_PREFIX_LENGTH = 5
MAX_BROADCAST = 2000

# token -> (user_id, expiry on the monotonic clock)
_SESSIONS: dict[str, tuple[int, float]] = {}
# state -> expiry on the monotonic clock
_STATES: dict[str, float] = {}
# guild_id -> guild, warmed from the bot and from API fallbacks
_GUILD_CACHE: dict[int, discord.Guild] = {}

HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

_oauth_configured = bool(DISCORD_CLIENT_SECRET)


def _prune() -> None:
    now = time.monotonic()
    for token, (_, expiry) in list(_SESSIONS.items()):
        if now > expiry:
            _SESSIONS.pop(token, None)
    for state, expiry in list(_STATES.items()):
        if now > expiry:
            _STATES.pop(state, None)


def _current_user(request: web.Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    entry = _SESSIONS.get(token)
    if entry is None:
        return None
    user_id, expiry = entry
    if time.monotonic() > expiry:
        _SESSIONS.pop(token, None)
        return None
    return user_id


def _same_origin(request: web.Request) -> bool:
    """Reject cross-site form posts. Same-site cookies already block most CSRF."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    host = request.host.split(":", 1)[0].lower()
    return (urlparse(origin).hostname or "").lower() == host


def _client_ip(request: web.Request) -> str:
    """Best-effort client IP. Cloudflare's tunnel sets CF-Connecting-IP."""
    ip = request.headers.get("CF-Connecting-IP", "").strip()
    if ip:
        return ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote or ""


def _user_agent(request: web.Request) -> str:
    return request.headers.get("User-Agent", "")[:300]


async def _remember_user(
    bot: "SekaiBot",
    user_id: int,
    identity: dict[str, Any],
    ip: str = "",
    user_agent: str = "",
) -> None:
    """Record (or refresh) a dashboard login so owners can review it later."""
    username = (
        identity.get("global_name")
        or identity.get("username")
        or str(user_id)
    )
    email = identity.get("email") or None
    await bot.db.execute(
        "INSERT INTO dashboard_users "
        "(user_id, username, email, logins, first_login, last_login, "
        "last_ip, last_user_agent) "
        "VALUES (?, ?, ?, 1, datetime('now'), datetime('now'), ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "username = excluded.username, "
        "email = COALESCE(excluded.email, dashboard_users.email), "
        "logins = dashboard_users.logins + 1, "
        "last_login = datetime('now'), "
        "last_ip = excluded.last_ip, "
        "last_user_agent = excluded.last_user_agent",
        (user_id, username, email, ip, user_agent))
    await bot.db.execute(
        "INSERT INTO dashboard_logins (user_id, ip, user_agent) "
        "VALUES (?, ?, ?)",
        (user_id, ip, user_agent))


def _guild_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info["guild_id"])
    except (KeyError, ValueError):
        return None


async def _guild_for(bot: "SekaiBot", guild_id: int | None) -> discord.Guild | None:
    """Guild lookup that falls back to the API if the cache is cold.

    The server cards are built from ``bot.guilds``, so resolve against that
    list first — this guarantees the id in the URL matches the card that was
    clicked even if ``Client.get_guild`` is momentarily stale.
    """
    if guild_id is None:
        return None
    guild = _GUILD_CACHE.get(guild_id)
    if guild is None:
        guild = discord.utils.get(bot.guilds, id=guild_id)
    if guild is None:
        guild = bot.get_guild(guild_id)
    if guild is not None:
        _GUILD_CACHE[guild_id] = guild
        return guild
    try:
        guild = await bot.fetch_guild(guild_id)
    except discord.HTTPException:
        return None
    if guild is not None:
        _GUILD_CACHE[guild_id] = guild
    return guild


def _authorize_url(bot: "SekaiBot", state: str) -> str:
    params = {
        "client_id": str(bot.user.id) if bot.user else "",
        "response_type": "code",
        "redirect_uri": settings.dashboard_redirect_uri,
        "scope": "identify email",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class OAuthError(Exception):
    """A Discord OAuth2 failure, carrying Discord's machine-readable reason."""

    def __init__(self, message: str, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


_OAUTH_HINTS = {
    "invalid_client": (
        "Discord rejected the app credentials. Check the OAuth2 client secret "
        "in config/token.py."
    ),
    "invalid_redirect_uri": (
        "Discord rejected the redirect URI. Add {uri} under OAuth2 → Redirects "
        "in the Discord Developer Portal."
    ),
    "invalid_grant": "The sign-in code was invalid or expired. Start again.",
    "invalid_request": "Discord rejected the sign-in request.",
}


def _oauth_hint(reason: str | None) -> str:
    if reason and reason in _OAUTH_HINTS:
        return _OAUTH_HINTS[reason].format(uri=settings.dashboard_redirect_uri)
    return "Discord did not complete the sign-in. Check the server log for details."


async def _exchange_identity(client_id: str, code: str) -> dict[str, Any]:
    payload = {
        "client_id": client_id,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.dashboard_redirect_uri,
    }
    async with aiohttp.ClientSession(timeout=OAUTH_TIMEOUT) as session:
        async with session.post(
            TOKEN_URL, data=payload, headers={"Accept": "application/json"}
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200 or not isinstance(data, dict):
                reason = data.get("error") if isinstance(data, dict) else None
                raise OAuthError(
                    f"token exchange returned {response.status}: {data}",
                    reason=reason)
            access_token = data.get("access_token")
            if not access_token:
                raise OAuthError("token exchange returned no access token")
        async with session.get(
            ME_URL, headers={"Authorization": f"Bearer {access_token}"}
        ) as response:
            user = await response.json(content_type=None)
            if response.status != 200 or not isinstance(user, dict):
                raise OAuthError(f"identity request returned {response.status}")
            return user


def _is_control_all(user_id: int | None) -> bool:
    return user_id is not None and user_id in DASHBOARD_CONTROL_ALL_IDS


async def _can_manage(bot: "SekaiBot", guild: discord.Guild, user_id: int | None) -> bool:
    """True when the user may control this server.

    Config owners control every server. Everyone else must own the server or
    hold Administrator / Manage Server in it.
    """
    if _is_control_all(user_id):
        return True
    if user_id is None:
        return False
    if guild.owner_id == user_id:
        return True
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.HTTPException:
            return False
    permissions = getattr(member, "guild_permissions", None)
    if permissions is None:
        return False
    return bool(permissions.administrator or permissions.manage_guild)


def _guild_icon(guild: discord.Guild) -> str | None:
    return guild.icon.url if guild.icon is not None else None


def _guild_owner(guild: discord.Guild) -> str | None:
    owner = guild.owner
    if owner is not None:
        return f"{owner} ({owner.id})"
    return str(guild.owner_id) if guild.owner_id else None


async def _guild_automod(guild: discord.Guild) -> dict[str, bool]:
    rules = await automod_commands._fetch_sekai_rules(guild)
    status: dict[str, bool] = {}
    for feature in automod_state.FEATURES:
        rule = rules.get(feature)
        status[feature] = bool(rule is not None and getattr(rule, "enabled", True))
    return status


def _text_channels(guild: discord.Guild) -> list[dict[str, Any]]:
    me = guild.me
    channels = []
    for channel in guild.text_channels:
        if me is not None:
            try:
                if not channel.permissions_for(me).send_messages:
                    continue
            except discord.HTTPException:
                continue
        channels.append({"id": str(channel.id), "name": channel.name})
    return channels


def _login_page(error: str = "") -> web.Response:
    return web.Response(
        text=render_login_page(configured=_oauth_configured, error=error),
        content_type="text/html",
        headers=HEADERS)


def create_dashboard_app(bot: "SekaiBot") -> web.Application:
    app = web.Application(middlewares=[enforce_https(settings.dashboard_url)])

    async def login(request: web.Request) -> web.Response:
        if not _oauth_configured:
            return _login_page("Login is not configured on this deployment.")
        if bot.user is None:
            return _login_page("The bot is still starting. Try again shortly.")
        _prune()
        state = secrets.token_urlsafe(24)
        _STATES[state] = time.monotonic() + STATE_TTL
        raise web.HTTPFound(_authorize_url(bot, state))

    async def callback(request: web.Request) -> web.Response:
        if not _oauth_configured:
            return _login_page("Login is not configured on this deployment.")
        if bot.user is None:
            return _login_page("The bot is still starting. Try again shortly.")

        _prune()
        state = request.query.get("state", "")
        if not state or state not in _STATES:
            return _login_page("That sign-in link expired. Start again.")
        _STATES.pop(state, None)

        if request.query.get("error"):
            return _login_page("Sign-in was cancelled.")

        code = request.query.get("code")
        if not code:
            return _login_page("Discord did not return a code.")

        try:
            identity = await _exchange_identity(str(bot.user.id), code)
        except OAuthError as exc:
            log.warning("Dashboard OAuth2 exchange failed: %s", exc)
            return _login_page(_oauth_hint(exc.reason))
        except (ValueError, aiohttp.ClientError, TimeoutError) as exc:
            log.warning("Dashboard OAuth2 exchange failed: %s", exc)
            return _login_page("Discord did not answer. Try again in a moment.")

        try:
            user_id = int(identity.get("id", "0"))
        except (TypeError, ValueError):
            user_id = 0

        if user_id == 0:
            return _login_page("Discord did not return a user ID.")

        try:
            await _remember_user(
                bot, user_id, identity,
                _client_ip(request), _user_agent(request))
        except Exception:
            log.exception("Could not record dashboard login for %s", user_id)

        token = secrets.token_urlsafe(32)
        _SESSIONS[token] = (user_id, time.monotonic() + SESSION_TTL)
        # Secure cookies only make sense over HTTPS. Behind the Cloudflare
        # tunnel TLS is terminated upstream, so trust X-Forwarded-Proto; a
        # local http://127.0.0.1 dev request gets a non-Secure cookie so the
        # session actually persists while testing.
        forwarded = request.headers.get("X-Forwarded-Proto", "").lower()
        secure = forwarded == "https" or request.url.scheme == "https"
        response = web.HTTPFound("/")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=int(SESSION_TTL),
            httponly=True,
            secure=secure,
            samesite="Lax",
            path="/",
        )
        raise response

    async def logout(request: web.Request) -> web.Response:
        token = request.cookies.get(SESSION_COOKIE, "")
        if token:
            _SESSIONS.pop(token, None)
        response = web.HTTPFound("/")
        response.del_cookie(SESSION_COOKIE, path="/")
        raise response

    async def index(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return _login_page()
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            name = str(user)
        except discord.HTTPException:
            name = str(user_id)
        return web.Response(
            text=render_dashboard_page(
                user_name=name,
                user_id=user_id,
                is_owner=user_id in OWNER_IDS),
            content_type="text/html",
            headers=HEADERS)

    async def api_servers(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        servers = []
        for guild in bot.guilds:
            # Warm the dashboard's guild cache from the exact list the cards
            # are built from, so /server/<id> resolves even if the Client
            # cache is momentarily cold.
            _GUILD_CACHE[guild.id] = guild
            if not await _can_manage(bot, guild, user_id):
                continue
            prefix = await prefixes.get_guild_prefix(bot, guild.id)
            servers.append(
                {
                    "id": str(guild.id),
                    "name": guild.name,
                    "icon": _guild_icon(guild),
                    "members": guild.member_count,
                    "channels": len(guild.channels),
                    "roles": len(guild.roles),
                    "owner": _guild_owner(guild),
                    "created_at": guild.created_at.isoformat(),
                    "prefix": prefix,
                }
            )
        servers.sort(key=lambda item: item["name"].lower())
        return web.json_response(
            {"servers": servers, "control_all": _is_control_all(user_id)},
            headers=HEADERS)

    async def server_page(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return _login_page()
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            requested = request.match_info.get("guild_id")
            log.warning(
                "Dashboard: no guild %s for /server page (bot is in %d guilds: %s)",
                requested, len(bot.guilds),
                ", ".join(str(g.id) for g in bot.guilds[:12]) or "none")
            known = ", ".join(str(g.id) for g in bot.guilds[:12]) or "none"
            return web.Response(
                text=render_notice_page(
                    title="Server not found",
                    message=(
                        f"Requested `{requested}`. The dashboard bot is in "
                        f"{len(bot.guilds)} server(s): {known}. If your server "
                        "is not in that list, the dashboard is connected to a "
                        "different bot instance than the one in your server.")),
                content_type="text/html",
                status=404,
                headers=HEADERS)
        if not await _can_manage(bot, guild, user_id):
            return web.Response(
                text=render_notice_page(
                    title="No access",
                    message="You do not own or administer this server."),
                content_type="text/html",
                status=403,
                headers=HEADERS)
        return web.Response(
            text=render_server_page(
                guild_name=guild.name,
                guild_id=guild.id,
                guild_icon=guild.icon.url if guild.icon is not None else None,
                member_count=guild.member_count),
            content_type="text/html",
            headers=HEADERS)

    async def api_modules(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        return web.json_response({"modules": module_summaries()}, headers=HEADERS)

    async def api_module(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        key = request.match_info.get("key", "")
        try:
            data = await read_module(bot, guild, key)
        except Exception:
            log.exception("Dashboard module %s failed to load in %s", key, guild.id)
            return web.json_response(
                {"error": "Could not load this module."}, status=500)
        if data is None:
            return web.json_response({"error": "unknown module"}, status=404)
        return web.json_response(data, headers=HEADERS)

    async def api_module_apply(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        if not _same_origin(request):
            return web.json_response({"error": "bad origin"}, status=403)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        key = request.match_info.get("key", "")
        try:
            payload = await request.json()
        except (aiohttp.ContentTypeError, ValueError):
            return web.json_response({"error": "invalid JSON body"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "invalid JSON body"}, status=400)
        try:
            error = await apply_module(bot, guild, key, payload)
        except Exception:
            log.exception("Dashboard module %s failed to apply in %s", key, guild.id)
            return web.json_response(
                {"error": "Could not apply that change."}, status=500)
        if error:
            return web.json_response({"error": error}, status=400)
        return web.json_response({"ok": True}, headers=HEADERS)

    async def api_server_detail(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        prefix = await prefixes.get_guild_prefix(bot, guild.id)
        return web.json_response(
            {
                "id": str(guild.id),
                "name": guild.name,
                "prefix": prefix,
                "automod": await _guild_automod(guild),
                "text_channels": _text_channels(guild),
            },
            headers=HEADERS)

    async def api_prefix(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        if not _same_origin(request):
            return web.json_response({"error": "bad origin"}, status=403)
        if bot.dev:
            return web.json_response(
                {"error": "prefix changes are disabled in dev mode"}, status=409)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            payload = await request.json()
        except (aiohttp.ContentTypeError, ValueError):
            return web.json_response({"error": "invalid JSON body"}, status=400)
        prefix = str(payload.get("prefix", "")).strip()
        if not 1 <= len(prefix) <= MAX_PREFIX_LENGTH or any(
            char.isspace() for char in prefix
        ):
            return web.json_response(
                {"error": f"prefix must be 1-{MAX_PREFIX_LENGTH} characters with no spaces"},
                status=400)
        await prefixes.set_guild_prefix(bot, guild.id, prefix)
        return web.json_response({"prefix": prefix}, headers=HEADERS)

    async def api_automod(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        if not _same_origin(request):
            return web.json_response({"error": "bad origin"}, status=403)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            payload = await request.json()
        except (aiohttp.ContentTypeError, ValueError):
            return web.json_response({"error": "invalid JSON body"}, status=400)

        feature = str(payload.get("feature", ""))
        if feature not in automod_state.FEATURE_RULE_NAMES:
            return web.json_response({"error": "unknown automod feature"}, status=400)
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            return web.json_response({"error": "enabled must be a boolean"}, status=400)

        error = (
            await automod_commands._enable_feature(guild, feature)
            if enabled
            else await automod_commands._disable_feature(guild, feature)
        )
        if error:
            return web.json_response({"error": error}, status=400)
        return web.json_response({"feature": feature, "enabled": enabled}, headers=HEADERS)

    async def api_broadcast(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        if not _same_origin(request):
            return web.json_response({"error": "bad origin"}, status=403)
        guild = await _guild_for(bot, _guild_id(request))
        if guild is None:
            return web.json_response({"error": "server not found"}, status=404)
        if not await _can_manage(bot, guild, user_id):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            payload = await request.json()
        except (aiohttp.ContentTypeError, ValueError):
            return web.json_response({"error": "invalid JSON body"}, status=400)

        try:
            channel_id = int(payload.get("channel_id", 0))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid channel"}, status=400)
        content = str(payload.get("message", "")).strip()
        if not content:
            return web.json_response({"error": "message is empty"}, status=400)
        if len(content) > MAX_BROADCAST:
            return web.json_response(
                {"error": f"message is too long (max {MAX_BROADCAST})"}, status=400)

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return web.json_response(
                {"error": "channel is not a text channel in this server"}, status=400)
        me = guild.me
        if me is not None:
            permissions = channel.permissions_for(me)
            if not permissions.send_messages or not permissions.view_channel:
                return web.json_response(
                    {"error": "the bot cannot send messages in that channel"}, status=400)
        try:
            await channel.send(content)
        except discord.Forbidden:
            return web.json_response(
                {"error": "the bot lacks permission to send messages there"}, status=400)
        except discord.HTTPException as exc:
            log.warning("Dashboard broadcast failed in %s: %s", guild.id, exc)
            return web.json_response(
                {"error": "Discord rejected the message"}, status=502)
        return web.json_response({"ok": True}, headers=HEADERS)

    async def owner_page(request: web.Request) -> web.Response:
        user_id = _current_user(request)
        if user_id is None:
            return _login_page()
        if user_id not in OWNER_IDS:
            return web.Response(
                text=render_notice_page(
                    title="Owner only",
                    message="Only the bot owners can view dashboard users."),
                content_type="text/html",
                status=403,
                headers=HEADERS)

        rows = await bot.db.fetchall(
            "SELECT user_id, username, email, logins, last_login, last_ip, "
            "last_user_agent FROM dashboard_users ORDER BY last_login DESC")
        users = [
            {
                "user_id": row["user_id"],
                "username": row["username"] or str(row["user_id"]),
                "email": row["email"],
                "logins": row["logins"],
                "last_login": row["last_login"],
                "last_ip": row["last_ip"],
                "last_user_agent": row["last_user_agent"],
            }
            for row in rows
        ]

        login_rows = await bot.db.fetchall(
            "SELECT l.user_id, l.ip, l.user_agent, l.created_at, u.username "
            "FROM dashboard_logins l "
            "LEFT JOIN dashboard_users u ON u.user_id = l.user_id "
            "ORDER BY l.id DESC LIMIT 50")
        logins = [
            {
                "user_id": row["user_id"],
                "username": row["username"] or str(row["user_id"]),
                "ip": row["ip"],
                "user_agent": row["user_agent"],
                "created_at": row["created_at"],
            }
            for row in login_rows
        ]

        target = None
        raw = request.match_info.get("user_id")
        if raw:
            try:
                target_id = int(raw)
            except ValueError:
                target_id = None
            if target_id is not None:
                target = next(
                    (user for user in users if user["user_id"] == target_id), None)
                if target is None:
                    return web.Response(
                        text=render_notice_page(
                            title="User not found",
                            message="That user has never signed in to the dashboard."),
                        content_type="text/html",
                        status=404,
                        headers=HEADERS)

        if target is not None:
            logins = [
                entry for entry in logins
                if entry["user_id"] == target["user_id"]
            ]

        return web.Response(
            text=render_owner_page(users=users, target=target, logins=logins),
            content_type="text/html",
            headers=HEADERS)

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "online" if bot.user else "starting",
                "oauth": _oauth_configured,
                "control_all": len(DASHBOARD_CONTROL_ALL_IDS),
                "bot_id": bot.user.id if bot.user else None,
                "guilds": len(bot.guilds),
                "guild_ids": [guild.id for guild in bot.guilds],
            },
            headers=HEADERS)

    app.router.add_get("/auth/login", login)
    app.router.add_get("/auth/callback", callback)
    app.router.add_post("/auth/logout", logout)
    app.router.add_get("/api/servers", api_servers)
    app.router.add_get("/api/servers/{guild_id}", api_server_detail)
    app.router.add_get("/server/{guild_id}", server_page)
    app.router.add_get("/api/servers/{guild_id}/modules", api_modules)
    app.router.add_get("/api/servers/{guild_id}/modules/{key}", api_module)
    app.router.add_post("/api/servers/{guild_id}/modules/{key}", api_module_apply)
    app.router.add_post("/api/servers/{guild_id}/prefix", api_prefix)
    app.router.add_post("/api/servers/{guild_id}/automod", api_automod)
    app.router.add_post("/api/servers/{guild_id}/broadcast", api_broadcast)
    app.router.add_get("/owner", owner_page)
    app.router.add_get("/owner/{user_id}", owner_page)
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    return app


async def start_dashboard_server(
    bot: "SekaiBot", host: str, port: int
) -> web.AppRunner:
    runner = web.AppRunner(create_dashboard_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info(
        "Dashboard:   http://%s:%s/  (Discord login, %d control-all owners)",
        host,
        port,
        len(DASHBOARD_CONTROL_ALL_IDS),
    )
    if _oauth_configured:
        log.info(
            "Dashboard OAuth2 redirect URI (register in the Discord Developer "
            "Portal): %s",
            settings.dashboard_redirect_uri,
        )
    else:
        log.warning(
            "Dashboard OAuth2 is not configured: set DISCORD_CLIENT_SECRET in "
            "config/token.py to enable Discord login.")
    return runner