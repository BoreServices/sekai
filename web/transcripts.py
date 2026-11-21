import logging
from html import escape
from typing import TYPE_CHECKING

from aiohttp import web

from config.settings import settings
from web.design import document
from web.https import enforce_https

if TYPE_CHECKING:
    from core.bot import SekaiBot

log = logging.getLogger("sekai.transcripts")

TRANSCRIPT_CSS = """
.transcripts-wrap {
  max-width: 640px;
  margin: min(4vh, 40px) auto 0;
}
.transcripts-card {
  padding: 32px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-lg);
}
.transcripts-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
}
.transcripts-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-3);
  color: var(--fg);
  font: 500 16px var(--font-mono);
  flex: none;
}
.transcripts-title {
  font-size: clamp(1.8rem, 3.2vw, 2.25rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--fg);
  margin-bottom: 12px;
}
.transcripts-lede {
  color: var(--fg-2);
  font-size: 16px;
  line-height: 1.6;
  margin-bottom: 24px;
}
.steps-list {
  display: grid;
  gap: 14px;
  padding: 0;
  margin: 24px 0 0;
  list-style: none;
  counter-reset: step;
}
.steps-list li {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 12px;
  align-items: start;
  color: var(--fg-2);
  font-size: 14px;
  line-height: 1.6;
  counter-increment: step;
}
.steps-list li::before {
  content: counter(step);
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  border-radius: 4px;
  background: var(--bg-2);
  color: var(--fg);
  font: 400 12px var(--font-mono);
  margin-top: 1px;
}
.steps-list strong { color: var(--fg); font-weight: 500; }
.transcripts-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 28px;
}
.privacy-note {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--fg-3);
  font: 400 13px/1.6 var(--font-body);
}

@media (max-width: 560px) {
  .transcripts-card { padding: 22px; }
}
"""


def _page(title: str, body: str, description: str) -> str:
    return document(
        title,
        f'<div class="transcripts-wrap">{body}</div>',
        active="tickets",
        description=description,
        extra_css=TRANSCRIPT_CSS)


def render_index() -> str:
    name = escape(settings.bot_name)
    invite = escape(settings.invite_url, quote=True)
    web_url = escape(settings.website_url, quote=True)
    body = (
        '<div class="transcripts-card">'
        '<div class="transcripts-head">'
        '<span class="transcripts-mark" aria-hidden="true">T</span>'
        '<p class="eyebrow" style="margin:0">Support archives</p>'
        "</div>"
        f'<h1 class="transcripts-title">Ticket transcripts</h1>'
        '<p class="transcripts-lede">Every closed support channel is preserved as a '
        "permanent, unlisted technical document with exact timestamps and message receipts.</p>"
        '<ol class="steps-list">'
        "<li><span>Open a ticket in the server and speak with support staff.</span></li>"
        "<li><span>When the channel is <strong>closed</strong>, the bot compiles the "
        "conversation and delivers a private link via DM.</span></li>"
        "<li><span>Open that link anytime. Only people with the direct URL can view "
        "it — it is not indexed by search engines.</span></li>"
        "</ol>"
        '<div class="transcripts-actions">'
        f'<a class="button button--primary" href="{invite}">Join the server</a>'
        f'<a class="button" href="{web_url}">{name} overview</a>'
        "</div>"
        '<p class="privacy-note">Transcript URLs contain unguessable channel identifiers, '
        "ensuring they stay unlisted unless explicitly shared. Search engine indexing is "
        "disallowed by robots policy.</p>"
        "</div>"
    )
    return _page(
        f"{settings.bot_name} · Ticket transcripts",
        body,
        f"Private, unlisted web transcripts of closed support tickets for {settings.bot_name}.")


def render_not_found() -> str:
    name = escape(settings.bot_name)
    invite = escape(settings.invite_url, quote=True)
    body = (
        '<div class="transcripts-card">'
        '<div class="transcripts-head">'
        '<span class="transcripts-mark" aria-hidden="true">?</span>'
        '<p class="eyebrow" style="margin:0">Support archives</p>'
        "</div>"
        '<h1 class="transcripts-title">Transcript not found</h1>'
        '<p class="transcripts-lede">The requested transcript URL is missing, was mistyped, '
        "or the ticket has not yet been closed.</p>"
        '<ol class="steps-list">'
        "<li><span>Verify the exact URL received from the bot DM.</span></li>"
        "<li><span>If the channel is currently open, request staff to close it first; "
        "transcripts are generated upon ticket closure.</span></li>"
        "</ol>"
        '<div class="transcripts-actions">'
        f'<a class="button button--primary" href="{invite}">Ask in Discord</a>'
        '<a class="button" href="/">Transcripts home</a>'
        "</div>"
        '<p class="privacy-note">Need assistance? Server staff can locate tickets by '
        "channel snowflake ID in the bot database.</p>"
        "</div>"
    )
    return _page(
        f"{settings.bot_name} · Transcript not found",
        body,
        "That ticket transcript is missing or was removed.")


TRANSCRIPT_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:"
    ),
}


def create_app(bot: "SekaiBot") -> web.Application:
    app = web.Application(
        middlewares=[enforce_https(settings.transcript_url)]
    )

    async def index(_: web.Request) -> web.Response:
        return web.Response(
            text=render_index(),
            content_type="text/html",
            headers={"X-Robots-Tag": "noindex, nofollow"})

    async def transcript(request: web.Request) -> web.Response:
        guild_id = int(request.match_info["guild_id"])
        ticket_id = int(request.match_info["ticket_id"])
        row = await bot.db.fetchone(
            "SELECT html FROM ticket_transcripts "
            "WHERE guild_id = ? AND channel_id = ?",
            (guild_id, ticket_id))
        if row is None:
            return web.Response(
                status=404,
                text=render_not_found(),
                content_type="text/html",
                headers={"X-Robots-Tag": "noindex, nofollow"})
        return web.Response(
            text=row["html"],
            content_type="text/html",
            headers=TRANSCRIPT_HEADERS)

    app.router.add_get("/", index)
    app.router.add_get(r"/{guild_id:\d+}/{ticket_id:\d+}", transcript)
    return app


async def start_transcript_server(
    bot: "SekaiBot", host: str, port: int
) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Transcripts: http://%s:%s/", host, port)
    return runner
