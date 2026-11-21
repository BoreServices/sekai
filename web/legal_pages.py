"""Terms of Service and Privacy Policy pages for the website."""

from __future__ import annotations

from html import escape

from config.settings import settings
from web.design import document

LEGAL_CSS = """
.legal { max-width: var(--measure); }
.legal h2 {
  font-size: 1.1rem;
  font-weight: 500;
  margin: 32px 0 10px;
  color: var(--fg);
}
.legal p, .legal li {
  color: var(--fg-2);
  font-size: 15px;
  line-height: 1.7;
}
.legal ul { margin: 8px 0 0 20px; padding: 0; display: grid; gap: 6px; }
.legal-meta {
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
  margin-top: 8px;
}
"""


def render_terms() -> str:
    name = escape(settings.bot_name)
    body = f"""
<p class="eyebrow">Legal · Terms of Service</p>
<h1 class="page-title">Terms of Service</h1>
<p class="page-lede">Rules for using {name} and its related web services.</p>
<p class="legal-meta">Last updated: 2026-11-15</p>

<section class="section legal" id="terms" style="margin-top:40px">
  <h2>1. Acceptance</h2>
  <p>By inviting or using {name} in a Discord server, or by accessing its websites
  (including status, verification, and transcript pages), you agree to these terms and to
  Discord's Terms of Service and Community Guidelines.</p>

  <h2>2. Use of the service</h2>
  <ul>
    <li>Use the bot and websites only for lawful purposes and in compliance with Discord rules.</li>
    <li>Do not attempt to abuse, disrupt, exploit, or reverse-engineer the bot or its services.</li>
    <li>Server administrators are responsible for configuring and using moderation, logging,
    verification, and other features in their servers.</li>
  </ul>

  <h2>3. Availability and changes</h2>
  <p>{name} is provided on an "as is" and "as available" basis. Features, commands, and web
  pages may change, be limited, or be discontinued at any time without notice.</p>

  <h2>4. Enforcement</h2>
  <p>Access to the bot or its websites may be restricted or removed for abuse, security risks,
  or violations of these terms.</p>

  <h2>5. Contact</h2>
  <p>For questions or concerns, contact the bot operators through the official community server
  or the owner listed on the website.</p>
</section>
"""
    return document(
        f"{settings.bot_name} · Terms of Service",
        body,
        active="",
        description=f"Terms of Service for {settings.bot_name}.",
        extra_css=LEGAL_CSS,
    )


def render_privacy() -> str:
    name = escape(settings.bot_name)
    body = f"""
<p class="eyebrow">Legal · Privacy Policy</p>
<h1 class="page-title">Privacy Policy</h1>
<p class="page-lede">How {name} handles data when you use the bot and its web services.</p>
<p class="legal-meta">Last updated: 2026-11-15</p>

<section class="section legal" id="privacy" style="margin-top:40px">
  <h2>1. Data we may process</h2>
  <ul>
    <li>Discord identifiers and profile data needed for features (user, server, channel, role,
    and message IDs/names/content where a feature requires it).</li>
    <li>Configuration and feature data you or server staff set (prefixes, settings, logs,
    tickets, tags, levels, verification state, and similar records).</li>
    <li>Operational and security data such as command usage, errors, and service status.</li>
    <li>Dashboard sign-in records: when you log in to the web dashboard with Discord, the bot
    stores your user ID, display name, email address (with the OAuth2 <code>email</code> scope),
    and login timestamps so the bot owners can review who has accessed the dashboard.</li>
  </ul>

  <h2>2. How data is used</h2>
  <p>Data is used to provide, maintain, secure, and improve bot features (moderation, tickets
  and transcripts, verification, music, levels, giveaways, and related services) and to operate
  the associated websites.</p>

  <h2>3. Sharing and storage</h2>
  <p>Data is not sold. It may be stored in the bot's databases/logs and, where applicable,
  exposed through configured web pages (for example unlisted ticket transcripts or status
  information) only as needed for the requested functionality. Third-party services used by
  features (such as Discord or external APIs) process data under their own policies.</p>

  <h2>4. Retention and removal</h2>
  <p>Data is retained as long as reasonably necessary for the features in use. Server staff can
  remove certain configuration data via bot commands; for other removal requests, contact the
  bot operators.</p>

  <h2>5. Contact</h2>
  <p>For privacy questions or requests, contact the bot operators through the official community
  server or the owner listed on the website.</p>
</section>
"""
    return document(
        f"{settings.bot_name} · Privacy Policy",
        body,
        active="",
        description=f"Privacy Policy for {settings.bot_name}.",
        extra_css=LEGAL_CSS,
    )
