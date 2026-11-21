"""Owner-only page listing dashboard users, emails and login security data."""

from __future__ import annotations

from html import escape

from config.settings import settings
from web.design import document

OWNER_CSS = """
.owner-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 20px; flex-wrap: wrap; padding-bottom: 32px; margin-bottom: 32px;
  border-bottom: 1px solid var(--line);
}
.owner-head h1 { font: 600 26px/1.2 var(--font-display); letter-spacing: -0.02em; margin: 2px 0 4px; }
.owner-meta { color: var(--fg-3); font: 400 12px var(--font-mono); }
.owner-card {
  padding: 22px; border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--bg-2); margin-bottom: 14px;
}
.owner-card h2 { font: 500 18px var(--font-display); margin: 0 0 14px; }
.owner-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}
.owner-field .k { color: var(--fg-3); font: 400 11px var(--font-mono); margin-bottom: 4px; }
.owner-field .v { color: var(--fg); font: 400 14px var(--font-body); word-break: break-all; }
.owner-table { width: 100%; border-collapse: collapse; font: 400 13px var(--font-body); }
.owner-table th {
  text-align: left; padding: 8px 10px; color: var(--fg-3);
  font: 400 11px var(--font-mono); border-bottom: 1px solid var(--line);
}
.owner-table td { padding: 10px; border-bottom: 1px solid var(--line); color: var(--fg); }
.owner-table tr:last-child td { border-bottom: 0; }
.owner-table a { color: var(--fg); text-decoration: none; }
.owner-table a:hover { color: var(--signal); }
.owner-table .mono { font-family: var(--font-mono); font-size: 12px; color: var(--fg-2); }
.owner-agent {
  max-width: 360px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; color: var(--fg-2);
}
"""


def _user_rows(users: list[dict]) -> str:
    if not users:
        return ('<tr><td colspan="5" style="text-align:center;color:var(--fg-3);'
                'padding:18px">No dashboard logins yet.</td></tr>')
    parts = []
    for user in users:
        user_id = user["user_id"]
        email = user["email"] or "—"
        last_ip = user.get("last_ip") or "—"
        parts.append(
            "<tr>"
            f'<td><a href="/owner/{int(user_id)}">{escape(user["username"])}</a>'
            f'<div class="mono">{escape(str(user_id))}</div></td>'
            f"<td>{escape(email)}</td>"
            f'<td class="mono">{int(user["logins"])}</td>'
            f'<td class="mono">{escape(last_ip)}</td>'
            f'<td class="mono">{escape(user["last_login"])}</td>'
            "</tr>")
    return "".join(parts)


def _login_rows(logins: list[dict]) -> str:
    if not logins:
        return ('<tr><td colspan="4" style="text-align:center;color:var(--fg-3);'
                'padding:18px">No logins recorded.</td></tr>')
    parts = []
    for entry in logins:
        parts.append(
            "<tr>"
            f'<td><a href="/owner/{int(entry["user_id"])}">{escape(entry["username"])}</a></td>'
            f'<td class="mono">{escape(entry["ip"] or "—")}</td>'
            f'<td class="owner-agent">{escape(entry["user_agent"] or "—")}</td>'
            f'<td class="mono">{escape(entry["created_at"])}</td>'
            "</tr>")
    return "".join(parts)


def _target_card(target: dict) -> str:
    return f"""
<section class="owner-card" aria-labelledby="owner-target">
  <h2 id="owner-target">{escape(target["username"])}</h2>
  <div class="owner-grid">
    <div class="owner-field"><div class="k">Email</div><div class="v">{escape(target["email"] or "—")}</div></div>
    <div class="owner-field"><div class="k">User ID</div><div class="v mono">{escape(str(target["user_id"]))}</div></div>
    <div class="owner-field"><div class="k">Logins</div><div class="v mono">{int(target["logins"])}</div></div>
    <div class="owner-field"><div class="k">Last login (UTC)</div><div class="v mono">{escape(target["last_login"])}</div></div>
    <div class="owner-field"><div class="k">Last IP</div><div class="v mono">{escape(target.get("last_ip") or "—")}</div></div>
    <div class="owner-field"><div class="k">Last user agent</div><div class="v">{escape(target.get("last_user_agent") or "—")}</div></div>
  </div>
</section>
"""


def render_owner_page(
    *, users: list[dict], target: dict | None = None,
    logins: list[dict] | None = None,
) -> str:
    logins = logins or []
    title = f"{target['username']}'s logins" if target else "Recent logins"
    body = f"""
<div class="owner-head">
  <div>
    <p class="eyebrow">Owner · {escape(settings.bot_name)}</p>
    <h1>Dashboard users</h1>
    <div class="owner-meta">{len(users)} login{"s" if len(users) != 1 else ""} recorded</div>
  </div>
  <a class="btn" href="/">← Dashboard</a>
</div>
{_target_card(target) if target else ""}
<section class="owner-card">
  <h2>All users</h2>
  <table class="owner-table">
    <thead><tr><th>User</th><th>Email</th><th>Logins</th><th>Last IP</th><th>Last login (UTC)</th></tr></thead>
    <tbody>{_user_rows(users)}</tbody>
  </table>
</section>
<section class="owner-card">
  <h2>{escape(title)}</h2>
  <table class="owner-table">
    <thead><tr><th>User</th><th>IP</th><th>User agent</th><th>When (UTC)</th></tr></thead>
    <tbody>{_login_rows(logins)}</tbody>
  </table>
</section>
"""
    return document(
        f"Owner · {settings.bot_name}",
        body,
        active="dashboard",
        description="Owner-only dashboard user directory.",
        url=settings.dashboard_url,
        extra_css=OWNER_CSS)