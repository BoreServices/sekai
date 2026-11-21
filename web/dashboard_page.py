"""Dashboard markup: Discord login and the server list.

The per-server control panel lives at ``/server/<id>`` (see
``web.server_page``); this page only lists the servers a user can manage.
Styling comes from the shared PhaseWorld design system in ``web.design``.
"""

from __future__ import annotations

from html import escape

from config.settings import settings
from web.design import document

DASHBOARD_CSS = """
.dash-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  padding-bottom: 40px;
  margin-bottom: 48px;
  border-bottom: 1px solid var(--line);
}
.dash-top-copy { max-width: var(--measure); }
.dash-account {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg-2);
  font: 400 13px var(--font-mono);
}
.dash-account .dot { background: var(--signal); }

.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.server-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--bg-2);
  transition: background-color 140ms var(--ease), border-color 140ms var(--ease);
}
.server-card:hover { background: var(--bg-3); border-color: var(--line-2); }
.server-head { display: flex; align-items: center; gap: 12px; min-width: 0; }
.server-icon {
  width: 40px; height: 40px; flex: none;
  border-radius: 8px; object-fit: cover;
  background: var(--bg-3); border: 1px solid var(--line);
}
.server-icon--empty {
  display: grid; place-items: center;
  color: var(--fg-3); font: 500 15px var(--font-mono);
}
.server-name {
  display: block;
  font: 500 15px var(--font-display);
  color: var(--fg); text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.server-name:hover { color: var(--signal); }
.server-sub { color: var(--fg-3); font: 400 11px var(--font-mono); margin-top: 2px; }
.server-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
  background: var(--line); border: 1px solid var(--line);
  border-radius: var(--radius-sm); overflow: hidden;
}
.server-stat { background: var(--bg-2); padding: 8px 10px; }
.server-stat dt { color: var(--fg-3); font: 400 10px var(--font-mono); margin: 0; }
.server-stat dd {
  margin: 3px 0 0; color: var(--fg);
  font: 500 14px var(--font-mono); font-variant-numeric: tabular-nums;
}

.login-wrap { min-height: 52vh; display: grid; place-items: center; }
.login-card {
  width: 100%; max-width: 420px; padding: 32px;
  border: 1px solid var(--line-2); border-radius: var(--radius-lg);
  background: var(--bg-2); display: grid; gap: 20px;
}
.login-card .lede { color: var(--fg-2); font-size: 15px; }
.login-note { color: var(--fg-3); font: 400 12px var(--font-mono); }

@media (max-width: 560px) {
  .server-stats { grid-template-columns: repeat(3, 1fr); }
}
"""

_LOGIN_BODY = """
<div class="login-wrap">
  <section class="login-card" aria-labelledby="login-title">
    {notice}
    <div>
      <p class="eyebrow">Dashboard · Access</p>
      <h1 class="page-title" id="login-title" style="font-size:1.9rem">Sign in</h1>
      <p class="lede">Sign in with Discord to manage the servers you own or administer.</p>
    </div>
    {button}
    <p class="login-note">You will only see servers you own or can manage. Your session is stored in an HTTP-only cookie.</p>
  </section>
</div>
"""

_DASH_BODY = """
<div class="dash-top" id="overview">
  <div class="dash-top-copy">
    <p class="eyebrow">Dashboard · Server control</p>
    <h1 class="page-title">Servers</h1>
    <p class="page-lede">Servers you own or administer in {bot_name}. Open one to
    manage its modules — AutoMod, welcome, verification, tickets, levels, shop and more.</p>
  </div>
  <div class="dash-account">
    <span class="dot" aria-hidden="true"></span>
    <span id="account-name">{user_name}</span>
    <span class="muted" id="account-id">{user_id}</span>
    {owner_link}
    <button class="btn compact" type="button" id="logout">Sign out</button>
  </div>
</div>

<div class="banner" id="load-banner" role="status">
  <span class="dot warn" aria-hidden="true"></span>
  <span>Could not load servers — retrying.</span>
</div>

<section class="section" id="servers" aria-labelledby="servers-title" style="margin-top:0">
  <div class="section-head">
    <div>
      <p class="section-label">01 / Servers</p>
      <h2 class="section-title" id="servers-title">All servers</h2>
    </div>
    <p class="section-note" id="server-count">Loading…</p>
  </div>
  <div class="server-grid" id="server-grid">
    <div class="empty">Loading servers…</div>
  </div>
</section>
"""

DASHBOARD_JS = """
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const grid = $("server-grid");
  const banner = $("load-banner");
  if (!grid) return;

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((key) => {
        const value = attrs[key];
        if (value == null) return;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value);
      });
    }
    children.flat().forEach((child) => {
      if (child == null) return;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    });
    return node;
  }

  async function api(path) {
    const res = await fetch(path, { cache: "no-store" });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      const message = data && data.error ? data.error : ("HTTP " + res.status);
      throw new Error(message);
    }
    return data;
  }

  function num(value) {
    return value == null ? "—" : Number(value).toLocaleString();
  }

  function guildIcon(guild) {
    if (guild.icon) {
      return h("img", { class: "server-icon", src: guild.icon, alt: "", loading: "lazy" });
    }
    const initial = (guild.name || "?").slice(0, 1).toUpperCase();
    return h("div", { class: "server-icon server-icon--empty", "aria-hidden": "true", text: initial });
  }

  function serverCard(guild) {
    const href = "/server/" + guild.id;
    const stats = h("dl", { class: "server-stats" },
      h("div", { class: "server-stat" }, h("dt", { text: "Members" }), h("dd", { text: num(guild.members) })),
      h("div", { class: "server-stat" }, h("dt", { text: "Channels" }), h("dd", { text: num(guild.channels) })),
      h("div", { class: "server-stat" }, h("dt", { text: "Prefix" }), h("dd", { text: guild.prefix || "—" }))
    );
    return h("article", { class: "server-card" },
      h("div", { class: "server-head" },
        guildIcon(guild),
        h("div", { style: "min-width:0" },
          h("a", { class: "server-name", href: href, text: guild.name }),
          h("div", { class: "server-sub mono", text: guild.id })
        )
      ),
      stats,
      h("a", { class: "btn block", href: href }, "Manage")
    );
  }

  async function loadServers() {
    try {
      const data = await api("/api/servers");
      const servers = data.servers || [];
      grid.textContent = "";
      if (!servers.length) {
        const message = data.control_all
          ? "The bot is not in any servers yet."
          : "You don't manage any servers yet. Ask a server owner to make you an admin.";
        grid.append(h("div", { class: "empty", text: message }));
      } else {
        servers.forEach((guild) => grid.append(serverCard(guild)));
      }
      const count = $("server-count");
      if (count) count.textContent = servers.length + (servers.length === 1 ? " server" : " servers");
      if (banner) banner.classList.remove("show");
    } catch (error) {
      if (banner) banner.classList.add("show");
    }
  }

  const logout = $("logout");
  if (logout) {
    logout.addEventListener("click", async () => {
      try { await fetch("/auth/logout", { method: "POST" }); } catch (_) {}
      window.location.href = "/";
    });
  }

  loadServers();
  setInterval(loadServers, 30000);
})();
</script>
"""


def render_login_page(*, configured: bool, error: str = "") -> str:
    notice = f'<div class="banner show" style="margin:0"><span class="dot bad" aria-hidden="true"></span><span>{escape(error)}</span></div>' if error else ""
    if configured:
        button = '<a class="button button--primary block" href="/auth/login">Login with Discord</a>'
    else:
        button = (
            '<button class="button block" type="button" disabled>'
            "Login unavailable"
            "</button>"
        )
    body = _LOGIN_BODY.format(notice=notice, button=button)
    return document(
        f"{settings.bot_name} · Dashboard",
        body,
        active="dashboard",
        description=f"Sign in to manage {settings.bot_name} servers.",
        url=settings.dashboard_url,
        extra_css=DASHBOARD_CSS,
        brand_footer=True)


def render_dashboard_page(
    *, user_name: str, user_id: int, is_owner: bool = False
) -> str:
    owner_link = '<a class="btn compact" href="/owner">Users</a>' if is_owner else ""
    body = _DASH_BODY.format(
        bot_name=escape(settings.bot_name),
        user_name=escape(user_name),
        user_id=user_id,
        owner_link=owner_link,
    )
    return document(
        f"{settings.bot_name} · Dashboard",
        body + DASHBOARD_JS,
        active="dashboard",
        description=f"Manage every server {settings.bot_name} is in.",
        url=settings.dashboard_url,
        extra_css=DASHBOARD_CSS)


_NOTICE_BODY = """
<div class="login-wrap">
  <section class="login-card" aria-labelledby="notice-title">
    <div>
      <p class="eyebrow">Dashboard</p>
      <h1 class="page-title" id="notice-title" style="font-size:1.6rem">{title}</h1>
      <p class="lede">{message}</p>
    </div>
    <a class="button button--primary block" href="/">Back to servers</a>
  </section>
</div>
"""


def render_notice_page(*, title: str, message: str) -> str:
    body = _NOTICE_BODY.format(title=escape(title), message=escape(message))
    return document(
        f"{settings.bot_name} · Dashboard",
        body,
        active="dashboard",
        description=message,
        url=settings.dashboard_url,
        extra_css=DASHBOARD_CSS)