import logging
from html import escape
from typing import TYPE_CHECKING

from aiohttp import web

from config.settings import settings
from core import prefix as prefixes
from web.design import ICON_URL, document
from web.https import enforce_https
from web.legal_pages import render_privacy, render_terms
from web.status import collect_status

if TYPE_CHECKING:
    from core.bot import SekaiBot

log = logging.getLogger("sekai.web")

LANDING_CSS = """
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 216px;
  gap: 48px;
  align-items: center;
  padding-bottom: 40px;
  margin-bottom: 64px;
  border-bottom: 1px solid var(--line);
}
.hero-copy { max-width: var(--measure); }
.hero-status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.hero-title {
  font-size: clamp(2rem, 2.8vw, 2.75rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.06;
  margin: 0 0 20px;
  color: var(--fg);
}
.hero-lede {
  max-width: 48ch;
  font-size: 17px;
  line-height: 1.6;
  color: var(--fg-2);
  margin: 0 0 24px;
}
.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.hero-foot {
  color: var(--fg-3);
  font-size: 13px;
  margin: 0;
}
.hero-foot code {
  color: var(--fg);
}

/* Identity card for bot portrait */
.hero-portrait {
  width: 100%;
  max-width: 216px;
  padding: 16px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-lg);
  display: grid;
  gap: 12px;
  place-items: center;
}
.hero-portrait img {
  width: 176px;
  height: 176px;
  border-radius: 10px;
  object-fit: cover;
  filter: grayscale(1);
  border: 1px solid var(--line);
  background: var(--bg);
}
.hero-portrait-meta {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--fg-3);
  font: 400 11px var(--font-mono);
}

/* Feature list using hairline dividers */
.feature-list {
  border-top: 1px solid var(--line);
}
.feature {
  display: grid;
  grid-template-columns: 36px minmax(180px, 0.45fr) minmax(0, 1fr) auto;
  gap: 20px;
  align-items: start;
  padding: 20px 0;
  border-bottom: 1px solid var(--line);
}
.feature-mark {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  color: var(--fg-2);
}
.feature-index {
  color: var(--fg-3);
  font: 400 11px var(--font-mono);
  margin-bottom: 4px;
}
.feature h3 {
  font-size: 15px;
  font-weight: 500;
  color: var(--fg);
}
.feature p {
  color: var(--fg-2);
  font-size: 15px;
  line-height: 1.6;
}

/* Command list */
.cmd-search-wrap {
  width: 100%;
  max-width: 320px;
}
.cmd-list-wrap {
  border-top: 1px solid var(--line);
}
.cmd-list {
  display: grid;
  max-height: 440px;
  overflow-y: auto;
}
.cmd-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.3fr) minmax(0, 1fr);
  gap: 16px;
  align-items: baseline;
  padding: 14px 8px;
  border-bottom: 1px solid var(--line);
  transition: background-color 140ms var(--ease);
}
.cmd-row:hover {
  background: var(--bg-3);
}
.cmd-name {
  color: var(--fg);
  font: 500 13px var(--font-mono);
  overflow-wrap: anywhere;
}
.cmd-desc {
  color: var(--fg-2);
  font-size: 14px;
  line-height: 1.5;
}

/* Website link rows */
.site-list {
  border-top: 1px solid var(--line);
}
.site-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 8px;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  transition: background-color 140ms var(--ease);
}
.site-row:hover {
  background: var(--bg-3);
}
.site-name {
  font: 500 15px var(--font-display);
  color: var(--fg);
  margin-bottom: 4px;
}
.site-url {
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}
.site-arrow {
  color: var(--fg-3);
  font: 400 14px var(--font-mono);
  transition: transform 140ms var(--ease), color 140ms var(--ease);
}
.site-row:hover .site-arrow {
  color: var(--fg);
  transform: translateX(3px);
}

@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .hero-portrait {
    max-width: 100%;
    justify-items: center;
  }
  .feature {
    grid-template-columns: 28px 1fr;
    gap: 8px 16px;
  }
  .feature-index, .feature p, .feature .chip {
    grid-column: 2;
  }
  .feature .chip { justify-self: start; }
}

/* Command list header */
.cmd-list-wrap { border-top: 1px solid var(--line); }
.cmd-list-header {
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--line);
}
}

@media (max-width: 640px) {
  .cmd-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}
"""

_SVG = (
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">{}</svg>'
)
ICON_SVG = {
    "shield": _SVG.format('<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>'),
    "ticket": _SVG.format('<path d="M3 8a2 2 0 0 0 0 4v4h18v-4a2 2 0 0 0 0-4V4H3z"/><path d="M14 4v16"/>'),
    "music": _SVG.format('<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'),
    "chart": _SVG.format('<path d="M3 20h18"/><path d="M6 16v-5M11 16V8M16 16v-9"/>'),
    "gift": _SVG.format('<rect x="3" y="8" width="18" height="4"/><path d="M5 12v8h14v-8M12 8v12M12 8c-2-4-6-4-6-1s6 1 6 1zM12 8c2-4 6-4 6-1s-6 1-6 1z"/>'),
    "check": _SVG.format('<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>'),
}

FEATURES = (
    (
        "shield",
        "Moderation & AutoMod",
        "Warnings, timeouts, and word filters with server audit logs.",
        "p!warn"),
    (
        "ticket",
        "Tickets with receipts",
        "Private support channels that generate permanent unlisted web transcripts.",
        "p!ticket"),
    (
        "music",
        "Music with failover",
        "NodeLink audio playback with automated cluster failover.",
        "p!play"),
    (
        "chart",
        "Levels & leaderboards",
        "XP progression, milestone role rewards, and tabular rank cards.",
        "p!rank"),
    (
        "gift",
        "Giveaways & reaction roles",
        "Automated timed prize draws and self-service button role panels.",
        "p!gstart"),
    (
        "check",
        "Website verification",
        "OAuth2 account ownership validation with automated member role assignment.",
        "p!verify"))

LANDING_JS = """
<script>
(() => {
  const PREFIX = "__PREFIX__";
  const $ = (id) => document.getElementById(id);
  const list = $("cmd-list");
  const input = $("cmd-search");
  let all = [];

  const empty = (text) => {
    const node = document.createElement("div");
    node.className = "empty";
    node.textContent = text;
    return node;
  };

  function render() {
    if (!list) return;
    const query = (input && input.value ? input.value : "").trim().toLowerCase();
    const matches = all.filter((cmd) =>
      !query || (PREFIX + cmd.name + " " + cmd.description).toLowerCase().includes(query)
    );
    list.textContent = "";
    if (!all.length) {
      list.append(empty("No commands are registered yet."));
    } else if (!matches.length) {
      list.append(empty('No commands match "' + query + '".'));
    } else {
      matches.slice(0, 100).forEach((cmd) => {
        const item = document.createElement("div");
        item.className = "cmd-row";
        const name = document.createElement("div");
        name.className = "cmd-name";
        name.textContent = PREFIX + cmd.name;
        const desc = document.createElement("div");
        desc.className = "cmd-desc";
        desc.textContent = cmd.description;
        item.append(name, desc);
        list.append(item);
      });
    }
    const count = $("cmd-count");
    if (count) {
      count.textContent = all.length
        ? matches.length + " of " + all.length + " commands"
        : "—";
    }
  }

  if (input) input.addEventListener("input", render);

  async function refresh() {
    try {
      const res = await fetch("/api/info", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      const dot = $("land-dot");
      if (dot) dot.className = "dot " + (d.bot.online ? "ok" : "warn");
      const statusText = $("land-status");
      if (statusText) statusText.textContent = d.bot.online ? "Online" : "Starting";
      const dev = $("land-dev");
      if (dev) dev.style.display = d.bot.dev_mode ? "inline-flex" : "none";
      const put = (id, value) => {
        const el = $(id);
        if (el) el.textContent = Number(value).toLocaleString();
      };
      put("land-guilds", d.counts.guilds);
      put("land-users", d.counts.users);
      put("land-channels", d.counts.channels);
      put("land-commands", d.counts.commands);
      all = Array.isArray(d.commands) ? d.commands : [];
      render();
    } catch (error) {
      const dot = $("land-dot");
      if (dot) dot.className = "dot bad";
      const statusText = $("land-status");
      if (statusText) statusText.textContent = "Unreachable";
    }
  }

  refresh();
  setInterval(refresh, 15000);
})();
</script>
"""


def _feature_cards() -> str:
    cards = []
    for index, (mark, title, text, example) in enumerate(FEATURES, start=1):
        cards.append(
            '<article class="feature">'
            f'<span class="feature-mark" aria-hidden="true">{ICON_SVG.get(mark, "")}</span>'
            f'<div><p class="feature-index">{index:02d}</p><h3>{escape(title)}</h3></div>'
            f"<p>{escape(text)}</p>"
            f'<span class="chip">{escape(example)}</span>'
            "</article>"
        )
    return "".join(cards)


def _site_rows() -> str:
    verify_url = settings.verify_base_url or settings.website_url
    rows = (
        ("Landing page", "Bot information, numbers, and command index.", settings.website_url),
        ("Status dashboard", "Live telemetry, resource utilization, and dependency health.", settings.status_url),
        ("Ticket transcripts", "Closed support channels stored as private unlisted documents.", settings.transcript_url),
        ("Verification portal", "OAuth2 identity sign-in for automated member gating.", verify_url))
    return "".join(
        f'<a class="site-row" href="{escape(url, quote=True)}" target="_blank" rel="noopener">'
        "<div>"
        f'<div class="site-name">{escape(name)}</div>'
        f'<div class="site-url">{escape(description)}</div>'
        "</div>"
        '<span class="site-arrow" aria-hidden="true">→</span>'
        "</a>"
        for name, description, url in rows
    )


def render_index(prefix: str) -> str:
    name = escape(settings.bot_name)
    owner = escape(settings.owner_name)
    invite = escape(settings.invite_url, quote=True)
    status_url = escape(settings.status_url, quote=True)
    verify_url = escape(settings.verify_base_url or settings.website_url, quote=True)

    toc = [
        ("overview", "00 / Overview"),
        ("numbers", "01 / Numbers"),
        ("commands", "02 / Commands"),
        ("features", "03 / Features"),
        ("sites", "04 / Endpoints"),
    ]

    body = f"""
<section class="hero" id="overview" aria-labelledby="overview-title">
  <div class="hero-copy">
    <div class="hero-status-row">
      <span class="pill" role="status" aria-live="polite">
        <span class="dot" id="land-dot" aria-hidden="true"></span>
        <span id="land-status">Connecting…</span>
      </span>
      <span class="dev-tag" id="land-dev" style="display:none">dev</span>
    </div>
    <p class="eyebrow">00 / Overview · Discord prefix bot</p>
    <h1 class="hero-title" id="overview-title">{name}</h1>
    <p class="hero-lede">Moderation, tickets, music, levels, giveaways, and
    website verification in one restrained Discord prefix bot — with unlisted
    web transcripts and live telemetry.</p>
    <div class="hero-actions">
      <a class="button button--primary" href="{invite}">Add to Discord</a>
      <a class="button" href="{status_url}">Live telemetry</a>
      <a class="button" href="{verify_url}">Verification</a>
    </div>
    <p class="hero-foot">Default prefix <code>{escape(prefix)}</code> · run
    <code>{escape(prefix)}help</code> for full documentation or configure with
    <code>{escape(prefix)}prefix</code>.</p>
  </div>
  <aside class="hero-portrait" aria-label="Bot identity">
    <img src="{ICON_URL}" alt="{name} portrait" width="176" height="176" loading="lazy">
    <div class="hero-portrait-meta">
      <span>{name}</span>
      <span>by {owner}</span>
    </div>
  </aside>
</section>

<section class="section" id="numbers" aria-labelledby="numbers-title">
  <div class="section-head">
    <div>
      <p class="section-label">01 / Telemetry</p>
      <h2 class="section-title" id="numbers-title">Bot numbers</h2>
    </div>
    <p class="section-note">Live counts across Discord gateway connections.</p>
  </div>
  <div class="stat-grid">
    <div class="stat">
      <p class="stat-label">Servers</p>
      <p class="stat-value" id="land-guilds">—</p>
      <p class="stat-sub">connected guilds</p>
    </div>
    <div class="stat">
      <p class="stat-label">Members</p>
      <p class="stat-value" id="land-users">—</p>
      <p class="stat-sub">reached users</p>
    </div>
    <div class="stat">
      <p class="stat-label">Channels</p>
      <p class="stat-value" id="land-channels">—</p>
      <p class="stat-sub">visible text channels</p>
    </div>
    <div class="stat">
      <p class="stat-label">Commands</p>
      <p class="stat-value" id="land-commands">—</p>
      <p class="stat-sub">prefix commands</p>
    </div>
  </div>
</section>

<section class="section" id="commands" aria-labelledby="commands-title">
  <div class="section-head">
    <div>
      <p class="section-label">02 / Reference</p>
      <h2 class="section-title" id="commands-title">Command index</h2>
      <p class="section-note">All capabilities are invoked via prefix. Filter by keyword or name.</p>
    </div>
    <div class="cmd-search-wrap">
      <label class="sr-only" for="cmd-search">Filter commands</label>
      <input class="field block" id="cmd-search" type="search" placeholder="Filter commands…"
             autocomplete="off" spellcheck="false">
    </div>
  </div>
  <div class="card">
    <div class="cmd-list-header">
      <span style="font:500 14px var(--font-display);color:var(--fg)">Registered commands</span>
      <span class="mono" id="cmd-count" style="font-size:12px;color:var(--fg-3)">—</span>
    </div>
    <div class="cmd-list" id="cmd-list">
      <div class="empty">Loading commands…</div>
    </div>
  </div>
</section>

<section class="section" id="features" aria-labelledby="features-title">
  <div class="section-head">
    <div>
      <p class="section-label">03 / Architecture</p>
      <h2 class="section-title" id="features-title">Built-in systems</h2>
    </div>
    <p class="section-note">A single unified codebase with zero third-party bot dependencies.</p>
  </div>
  <div class="feature-list">{_feature_cards()}</div>
</section>

<section class="section" id="sites" aria-labelledby="sites-title">
  <div class="section-head">
    <div>
      <p class="section-label">04 / Endpoints</p>
      <h2 class="section-title" id="sites-title">Web services</h2>
    </div>
    <p class="section-note">Dedicated lightweight services running alongside the Discord gateway.</p>
  </div>
  <div class="site-list">{_site_rows()}</div>
</section>
"""
    return document(
        f"{name} · Discord bot",
        body + LANDING_JS.replace("__PREFIX__", escape(prefix)),
        active="bot",
        description=(
            f"{settings.bot_name} is a Discord prefix bot for moderation, "
            "tickets with web transcripts, music, levels, giveaways, and "
            "website verification."
        ),
        extra_css=LANDING_CSS,
        toc=toc)


def create_app(bot: "SekaiBot") -> web.Application:
    app = web.Application(middlewares=[enforce_https(settings.website_url)])

    async def index(_: web.Request) -> web.Response:
        return web.Response(
            text=render_index(prefixes.default_prefix(bot)),
            content_type="text/html")

    async def info(_: web.Request) -> web.Response:
        data = collect_status(bot)
        data["commands"] = [
            {
                "name": command.name,
                "description": getattr(command, "help", None) or "No description.",
            }
            for command in sorted(bot.commands, key=lambda item: item.name)
        ]
        return web.json_response(data)

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "online" if bot.user else "starting",
                "bot": str(bot.user) if bot.user else None,
                "latency_ms": round(bot.latency * 1000) if bot.latency else None,
            }
        )

    async def terms(_: web.Request) -> web.Response:
        return web.Response(text=render_terms(), content_type="text/html")

    async def privacy(_: web.Request) -> web.Response:
        return web.Response(text=render_privacy(), content_type="text/html")

    app.router.add_get("/", index)
    app.router.add_get("/terms", terms)
    app.router.add_get("/privacy", privacy)
    app.router.add_get("/api/info", info)
    app.router.add_get("/health", health)
    return app


async def start_server(bot: "SekaiBot", host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Main page:   http://%s:%s/", host, port)
    return runner