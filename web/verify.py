import html
import logging
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web

from config.settings import settings
from config.token import DISCORD_CLIENT_SECRET
from src.verification import state
from pathlib import Path

from web import captcha
from web.https import enforce_https
from web.verify_page import render_verify_page

log = logging.getLogger("sekai.verify.web")

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
ME_URL = "https://discord.com/api/users/@me"
TIMEOUT = aiohttp.ClientTimeout(total=15)

HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
        "base-uri 'none'; form-action 'none'"
    ),
}

# The captcha page needs the vendored widget script, its blob: proof-of-work
# workers and a same-site challenge fetch. Nothing else is loosened.
CAPTCHA_CSP = (
    "default-src 'none'; script-src 'self'; worker-src blob:; connect-src 'self'; "
    "style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; "
    "form-action 'self' https://discord.com"
)
STATIC_DIR = Path(__file__).parent / "static"

def _page(
    *,
    title: str,
    heading: str,
    body: str,
    icon_url: str | None = None,
    status: int = 200,
    error: bool = False,
    success: bool = False,
    step: int = 1,
    csp: str | None = None) -> web.Response:
    headers = dict(HEADERS)
    if csp is not None:
        headers["Content-Security-Policy"] = csp
    return web.Response(
        text=render_verify_page(
            title=title,
            heading=heading,
            body=body,
            icon_url=icon_url,
            error=error,
            success=success,
            step=step),
        status=status,
        content_type="text/html",
        headers=headers)


def _expired_page() -> web.Response:
    return _page(
        title="Verification link expired",
        heading="That link expired",
        body=(
            '<p class="strong">Verification links work once and last a limited '
            "time.</p><p>Go back to Discord, click <strong>Verify</strong> "
            "again (or run <code>verify link</code>) and use the new link.</p>"
        ),
        status=404,
        error=True)


def _bot_icon(bot) -> str | None:
    user = getattr(bot, "user", None)
    return user.display_avatar.url if user is not None else None


def _authorize_url(bot, code: str) -> str:
    params = {
        "client_id": str(bot.user.id),
        "response_type": "code",
        "redirect_uri": settings.verify_redirect_uri,
        "scope": "identify",
        "state": code,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class OAuthError(Exception):
    pass


async def _oauth_identity(client_id: str, code: str) -> dict:
    payload = {
        "client_id": client_id,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.verify_redirect_uri,
    }
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            TOKEN_URL, data=payload, headers={"Accept": "application/json"}
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200 or not isinstance(data, dict):
                raise OAuthError(f"token exchange returned {response.status}")
            token = data.get("access_token")
            if not token:
                raise OAuthError("token exchange returned no access token")
        async with session.get(
            ME_URL, headers={"Authorization": f"Bearer {token}"}
        ) as response:
            user = await response.json(content_type=None)
            if response.status != 200 or not isinstance(user, dict):
                raise OAuthError(f"identity request returned {response.status}")
            return user


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded.strip()
    header = request.headers.get("X-Forwarded-For", "")
    if header:
        return header.split(",")[0].strip()
    return request.remote or "unknown"


def register_verify_routes(app: web.Application, bot) -> None:
    async def info(_: web.Request) -> web.Response:
        if not state.website_configured(bot):
            return _page(
                title="Verification unavailable",
                heading="Verification isn't set up yet",
                body=(
                    "<p>This server hasn't finished configuring the "
                    "verification website. Ask a staff member to run "
                    "<code>verify settings</code> in Discord.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=503,
                error=True)
        return _page(
            title="Verification",
            heading="Open your personal link",
            body=(
                '<div class="verify-hero"><span class="hero-mark" aria-hidden="true">🛡️</span>'
                '<p class="eyebrow" style="margin:0">Member verification</p></div>'
                '<p class="lede">Verification links are personal and single-use, '
                "so this page only works when you open one from the bot.</p>"
                '<ol class="steps-list">'
                "<li><span>Go to the server and find the verification panel.</span></li>"
                "<li><span>Click <strong>Verify</strong> (or run <code>verify link</code>).</span></li>"
                "<li><span>Open the page the bot sends you and finish the check.</span></li>"
                "</ol>"
                '<p class="fine">Your link is unlisted and expires shortly after it is '
                "created.</p>"
            ),
            icon_url=_bot_icon(bot),
            step=0)

    async def altcha_script(_: web.Request) -> web.Response:
        return web.FileResponse(
            STATIC_DIR / "altcha.min.js",
            headers={
                "Content-Type": "text/javascript; charset=utf-8",
                "Cache-Control": "public, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            })

    async def pending_for(prefix: str, code: str):
        """Return the pending code only if its server uses this URL prefix."""
        pending = state.peek_code(code)
        if pending is None:
            return None
        config = await state.get_config(bot, pending.guild_id)
        expected = config.url_path if config and config.url_path else "verify"
        return pending if prefix == expected else None

    async def code_page(request: web.Request) -> web.Response:
        if not state.website_configured(bot):
            return _page(
                title="Verification unavailable",
                heading="Verification isn't set up yet",
                body=(
                    "<p>Ask a staff member to run <code>verify settings</code> "
                    "in Discord.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=503,
                error=True)
        code = request.match_info["code"]
        prefix = request.match_info["prefix"]
        pending = await pending_for(prefix, code)
        if pending is None:
            return _expired_page()
        guild = bot.get_guild(pending.guild_id)
        if guild is None:
            return _page(
                title="Server unavailable",
                heading="That server isn't available",
                body=(
                    "<p>The bot is no longer in that server, so verification "
                    "can't finish. Ask staff for a new link.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=404,
                error=True)
        icon = guild.icon.url if guild.icon is not None else _bot_icon(bot)
        return _page(
            title=f"Verify for {guild.name}",
            heading=f"Verify for {guild.name}",
            body=(
                '<p class="strong">Confirm you are a person first.</p>'
                f"<p>Complete the check below, then continue to Discord to prove "
                f"you are a real member of <strong>{html.escape(guild.name)}</strong>.</p>"
                f'<form method="post" action="/{html.escape(prefix, quote=True)}/{html.escape(code, quote=True)}/start">'
                '<altcha-widget challenge="/verify/captcha/challenge" hidefooter></altcha-widget>'
                '<button class="btn primary block" type="submit">Continue with Discord</button>'
                "</form>"
                '<p class="fine">This link is personal, works once and expires soon. '
                "Only continue if you started it from the server.</p>"
                '<script src="/static/altcha.min.js" type="module"></script>'
            ),
            icon_url=icon,
            step=2,
            csp=CAPTCHA_CSP)

    async def captcha_challenge(_: web.Request) -> web.Response:
        return web.json_response(
            captcha.create_challenge(),
            headers={"Cache-Control": "no-store"})

    async def captcha_start(request: web.Request) -> web.Response:
        """Send the user to Discord only after a server-verified captcha solution."""
        code = request.match_info["code"]
        prefix = request.match_info["prefix"]
        if await pending_for(prefix, code) is None:
            return _expired_page()
        form = await request.post()
        if not captcha.verify_solution(str(form.get("altcha", ""))):
            return _page(
                title="Captcha failed",
                heading="Let's try that again",
                body=(
                    '<p class="strong">The check didn\'t pass.</p>'
                    "<p>Complete the check once more.</p>"
                    f'<p><a class="btn primary block" href="/{html.escape(prefix, quote=True)}/{html.escape(code, quote=True)}">'
                    "Try again</a></p>"
                ),
                icon_url=_bot_icon(bot),
                status=403,
                error=True,
                step=2,
                csp=CAPTCHA_CSP)
        raise web.HTTPFound(_authorize_url(bot, code))

    async def callback(request: web.Request) -> web.Response:
        if not state.website_configured(bot):
            return _page(
                title="Verification unavailable",
                heading="Verification isn't set up yet",
                body=(
                    "<p>Ask a staff member to run <code>verify settings</code> "
                    "in Discord.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=503,
                error=True)

        raw_state = request.query.get("state", "")
        pending = state.consume_code(raw_state) if raw_state else None
        if pending is None:
            return _expired_page()

        if request.query.get("error"):
            return _page(
                title="Sign-in cancelled",
                heading="Sign-in cancelled",
                body=(
                    '<p class="strong">You cancelled the Discord sign-in.</p>'
                    "<p>Go back to Discord and click <strong>Verify</strong> "
                    "again to get a fresh link.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=403,
                error=True)

        oauth_code = request.query.get("code")
        if not oauth_code:
            return _page(
                title="Sign-in failed",
                heading="Discord sent no code",
                body=(
                    "<p>Something interrupted the sign-in. Click "
                    "<strong>Verify</strong> in Discord and try again.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=400,
                error=True)

        if not state.callback_limiter.allow(_client_ip(request)):
            return _page(
                title="Slow down",
                heading="Too many attempts",
                body=(
                    "<p>Wait a minute, then click <strong>Verify</strong> in "
                    "Discord to get a fresh link.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=429,
                error=True)

        try:
            identity = await _oauth_identity(str(bot.user.id), oauth_code)
        except (OAuthError, aiohttp.ClientError, TimeoutError) as exc:
            log.warning("Discord OAuth2 exchange failed: %s", exc)
            return _page(
                title="Sign-in failed",
                heading="Discord didn't answer",
                body=(
                    "<p>Try again in a moment. If it keeps failing, ask staff "
                    "to check the OAuth2 redirect URL and client secret.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=502,
                error=True)

        try:
            user_id = int(identity.get("id", "0"))
        except (TypeError, ValueError):
            user_id = 0

        guild = bot.get_guild(pending.guild_id)
        if guild is None:
            return _page(
                title="Server unavailable",
                heading="That server isn't available",
                body=(
                    "<p>The bot is no longer in that server. Ask staff for "
                    "help.</p>"
                ),
                icon_url=_bot_icon(bot),
                status=404,
                error=True)

        if user_id != pending.user_id:
            log.info(
                "Verification rejected: link for %s used by %s",
                pending.user_id,
                user_id)
            return _page(
                title="Wrong account",
                heading="Wrong Discord account",
                body=(
                    '<p class="strong">This link belongs to a different '
                    "account.</p><p>Go back to Discord, click "
                    "<strong>Verify</strong> again and sign in with the "
                    "account that requested the link.</p>"
                ),
                icon_url=guild.icon.url if guild.icon else _bot_icon(bot),
                status=403,
                error=True)

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                return _page(
                    title="Not in the server",
                    heading="Join the server first",
                    body=(
                        f"<p>You're not in <strong>{html.escape(guild.name)}"
                        "</strong> right now. Rejoin, then click "
                        "<strong>Verify</strong> again.</p>"
                    ),
                    icon_url=guild.icon.url if guild.icon else _bot_icon(bot),
                    status=404,
                    error=True)
            except discord.HTTPException as exc:
                log.warning("Could not fetch verified member %s: %s", user_id, exc)
                return _page(
                    title="Verification failed",
                    heading="I couldn't check your membership",
                    body=(
                        "<p>Discord didn't answer. Try again in a moment.</p>"
                    ),
                    icon_url=_bot_icon(bot),
                    status=502,
                    error=True)

        ok, reason = await state.mark_verified(
            bot, guild, member, method="website"
        )
        if not ok:
            return _page(
                title="Verification failed",
                heading="I couldn't give you the role",
                body=(
                    f"<p>{html.escape(reason)}</p>"
                    "<p>Ask a staff member to fix the role setup, then click "
                    "<strong>Verify</strong> again.</p>"
                ),
                icon_url=guild.icon.url if guild.icon else _bot_icon(bot),
                status=409,
                error=True)

        log.info("Website verified %s in guild %s", user_id, guild.id)
        return _page(
            title="Verified",
            heading="You're verified!",
            body=(
                f"<p class=\"strong\">Welcome to <strong>{html.escape(guild.name)}</strong>. "
                "Your role was added automatically.</p>"
                f'<a class="btn primary" href="https://discord.com/channels/{guild.id}">'
                "Back to Discord</a>"
                '<p class="fine">You can close this tab any time.</p>'
            ),
            icon_url=guild.icon.url if guild.icon else _bot_icon(bot),
            success=True,
            step=3)

    # The OAuth2 redirect target. Registered before the code route so it is
    # never captured as a verification code.
    app.router.add_get("/auth/callback", callback)
    app.router.add_get("/", info)
    app.router.add_get("/verify", info)
    app.router.add_get("/verify/captcha/challenge", captcha_challenge)
    app.router.add_get("/static/altcha.min.js", altcha_script)
    app.router.add_post("/{prefix}/{code}/start", captcha_start)
    app.router.add_get("/{prefix}/{code}", code_page)


def create_verify_app(bot) -> web.Application:
    app = web.Application(
        middlewares=[
            enforce_https(settings.verify_base_url or settings.website_url)
        ]
    )

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "online" if bot.user else "starting",
                "website": state.website_configured(bot),
            }
        )

    register_verify_routes(app, bot)
    app.router.add_get("/health", health)
    return app


async def start_verify_server(bot, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(create_verify_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Verify site: http://%s:%s/", host, port)
    return runner
