import html
import io
import logging
import sqlite3
from contextlib import suppress
from dataclasses import dataclass

import discord

from config.settings import settings
from core.emojis import emoji_data_uri, emoji_image
from src.tickets.formatting import (
    emoji_shortcodes,
    is_image,
    render_content,
    render_emoji,
    render_inline)
from view.tickets import ticket_closed_dm_embed, ticket_welcome_embed

log = logging.getLogger("sekai.tickets")

TRANSCRIPT_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  color-scheme: dark;
  --bg: #141415;
  --bg-deep: #0f0f10;
  --bg-2: #19191b;
  --bg-3: #232325;
  --line: rgba(237, 237, 237, 0.08);
  --line-2: rgba(237, 237, 237, 0.16);
  --fg: #ededed;
  --fg-2: #a1a1a6;
  --fg-3: #85858b;
  --signal: #4cc38a;
  --warning: #d4a72c;
  --danger: #e5484d;
  --font-display: 'Instrument Sans', 'Inter', system-ui, -apple-system, sans-serif;
  --font-body: 'Instrument Sans', 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, 'Cascadia Code', Consolas, monospace;
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 16px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
}

*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  padding: 48px clamp(16px, 4vw, 32px) 96px;
  background: var(--bg);
  color: var(--fg);
  font: 400 15px/1.65 var(--font-body);
  -webkit-font-smoothing: antialiased;
}
main {
  max-width: 860px;
  margin: 0 auto;
}
.eyebrow {
  margin: 0 0 12px;
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}
h1 {
  margin: 0 0 16px;
  font-family: var(--font-display);
  font-size: clamp(2rem, 3vw, 2.5rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--fg);
}
.topic {
  margin: 0 0 24px;
  color: var(--fg-2);
  font-size: 16px;
  max-width: 64ch;
}
.online {
  margin: -12px 0 24px;
  font: 400 13px var(--font-mono);
}
.online a {
  color: var(--fg);
  text-decoration-color: var(--line-2);
}
.online a:hover {
  text-decoration-color: var(--fg);
}

/* Meta grid */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--line);
}
.meta {
  padding: 14px 16px;
  background: var(--bg-2);
}
.meta span {
  display: block;
  font: 400 11px var(--font-mono);
  color: var(--fg-3);
  margin-bottom: 4px;
}
.meta strong {
  font-weight: 500;
  color: var(--fg);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

/* Message feed */
.messages {
  margin-top: 36px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message {
  display: flex;
  gap: 14px;
  padding: 16px 18px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  flex: none;
  background: var(--bg-3);
  border: 1px solid var(--line);
  object-fit: cover;
}
.body { min-width: 0; flex: 1; }
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 6px;
}
.name {
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 14px;
  color: var(--fg);
}
.handle {
  font: 400 12px var(--font-mono);
  color: var(--fg-3);
}
time {
  margin-left: auto;
  font: 400 11px var(--font-mono);
  color: var(--fg-3);
  white-space: nowrap;
}
.text {
  margin: 0;
  color: var(--fg-2);
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.text a, blockquote a, .field a {
  color: var(--fg);
  text-decoration-color: var(--line-2);
}
.text a:hover, blockquote a:hover, .field a:hover {
  text-decoration-color: var(--fg);
}
.inline-code {
  background: var(--bg-3);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.88em;
  font-family: var(--font-mono);
  color: var(--fg);
}
.code {
  margin: 10px 0 0;
  padding: 14px 16px;
  background: var(--bg-deep);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.7;
  font-family: var(--font-mono);
  color: var(--fg);
}
.code-lang {
  display: block;
  font: 400 11px var(--font-mono);
  color: var(--fg-3);
  margin-bottom: 6px;
}
.heading { margin: 12px 0 4px; font-weight: 500; color: var(--fg); font-family: var(--font-display); }
.heading-1 { font-size: 18px; }
.heading-2 { font-size: 16px; }
.heading-3 { font-size: 14px; }
blockquote {
  margin: 8px 0 0;
  padding: 2px 0 2px 14px;
  color: var(--fg-2);
  border-left: 1px solid var(--line-2);
}
ul, ol { margin: 6px 0 0 22px; padding: 0; }
.mention {
  background: var(--bg-3);
  border: 1px solid var(--line-2);
  color: var(--fg);
  border-radius: 4px;
  padding: 1px 5px;
  font: 400 12px var(--font-mono);
}
.spoiler {
  background: var(--bg-3);
  color: transparent;
  border-radius: 4px;
  padding: 1px 4px;
  transition: background-color 140ms var(--ease), color 140ms var(--ease);
}
.spoiler:hover { background: var(--bg-3); color: var(--fg); }
.image {
  display: block;
  max-width: 100%;
  margin-top: 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}
.thumb { float: right; max-width: 80px; margin: 0 0 8px 10px; border-radius: 6px; border: 1px solid var(--line); }
.muted { color: var(--fg-3); }
.reply {
  display: block;
  font: 400 12px var(--font-mono);
  color: var(--fg-3);
  text-decoration: none;
  margin-bottom: 4px;
}
.quote {
  display: block;
  margin-top: 2px;
  padding-left: 10px;
  border-left: 1px solid var(--line-2);
  font-size: 13px;
  color: var(--fg-3);
  white-space: pre-wrap;
}
.embed {
  margin-top: 10px;
  padding: 14px 16px;
  background: var(--bg-deep);
  border: 1px solid var(--line);
  border-left-width: 2px;
  border-radius: var(--radius-sm);
}
.embed-title {
  display: block;
  margin-bottom: 6px;
  font: 500 14px var(--font-display);
  color: var(--fg);
  text-decoration: none;
}
.field { margin-top: 6px; font-size: 13px; color: var(--fg-2); }
.field strong { color: var(--fg); font-weight: 500; }
.attachment {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  margin-right: 8px;
  padding: 4px 10px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  font: 400 12px var(--font-mono);
  background: var(--bg-deep);
  color: var(--fg);
  text-decoration: none;
}
.attachment:hover { background: var(--bg-3); }
.emoji { width: 16px; height: 16px; vertical-align: -2px; }
footer {
  margin-top: 48px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
  text-align: center;
}
.jump { display: inline-block; margin-top: 8px; font-size: 11px; color: var(--fg-3); font-family: var(--font-mono); }
"""

CATEGORY_NAME = "Tickets"
TRANSCRIPT_LIMIT = 2000
MAX_TOPIC = 100


@dataclass
class Config:
    category_id: int
    staff_role_id: int
    panel_channel_id: int | None = None
    panel_message_id: int | None = None
    log_channel_id: int | None = None


@dataclass
class Ticket:
    number: int
    guild_id: int
    opener_id: int
    claimed_id: int | None
    topic: str


# guild_id -> config
_configs: dict[int, Config] = {}
# channel_id -> ticket
_tickets: dict[int, Ticket] = {}
_loaded = False


def find_open(guild_id: int, user_id: int) -> Ticket | None:
    for ticket in _tickets.values():
        if ticket.guild_id == guild_id and ticket.opener_id == user_id:
            return ticket
    return None


def is_staff(member: discord.Member, config: Config) -> bool:
    permissions = member.guild_permissions
    if permissions.administrator or permissions.manage_guild:
        return True
    return any(role.id == config.staff_role_id for role in member.roles)


def can_manage(
    member: discord.Member, ticket: Ticket, config: Config | None
) -> bool:
    if member.id == ticket.opener_id:
        return True
    if config is None:
        permissions = member.guild_permissions
        return permissions.administrator or permissions.manage_guild
    return is_staff(member, config)


def _open_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        attach_files=True,
        embed_links=True)


async def _next_number(bot, guild_id: int) -> int:
    row = await bot.db.fetchone(
        "SELECT counter FROM ticket_config WHERE guild_id = ?", (guild_id,)
    )
    number = (row["counter"] if row is not None else 0) + 1
    await bot.db.execute(
        "UPDATE ticket_config SET counter = ? WHERE guild_id = ?",
        (number, guild_id))
    return number


async def create_ticket(
    bot, guild: discord.Guild, member: discord.Member, topic: str
) -> tuple[discord.TextChannel | None, str | None]:
    config = _configs.get(guild.id)
    if config is None:
        return None, "Tickets aren't set up in this server yet."

    category = guild.get_channel(config.category_id)
    if not isinstance(category, discord.CategoryChannel):
        return None, "The ticket category is missing — run `ticket setup` again."

    staff = guild.get_role(config.staff_role_id)
    if staff is None:
        return None, "The staff role is missing — run `ticket setup` again."

    existing = find_open(guild.id, member.id)
    if existing is not None:
        return None, "You already have an open ticket — close that one first."

    number = await _next_number(bot, guild.id)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: _open_overwrite(),
        staff: _open_overwrite(),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            manage_channels=True),
    }
    try:
        channel = await guild.create_text_channel(
            f"ticket-{number:04d}",
            category=category,
            overwrites=overwrites,
            topic=f"{topic} · opened by {member} ({member.id})",
            reason=f"Ticket #{number:04d} opened by {member} ({member.id})")
    except discord.HTTPException as exc:
        log.warning("Could not create ticket for %s: %s", member, exc)
        return None, "I couldn't create the channel — check my permissions."

    ticket = Ticket(
        number=number,
        guild_id=guild.id,
        opener_id=member.id,
        claimed_id=None,
        topic=topic)
    _tickets[channel.id] = ticket
    await bot.db.execute(
        "INSERT INTO tickets (channel_id, guild_id, number, opener_id, topic) "
        "VALUES (?, ?, ?, ?, ?)",
        (channel.id, guild.id, number, member.id, topic))

    # Imported lazily: the views import this module.
    from view.tickets.menu import TicketControlView

    with suppress(discord.HTTPException):
        await channel.send(
            embed=ticket_welcome_embed(
                number=number, member=member, staff_role=staff, topic=topic
            ),
            view=TicketControlView(bot))
    return channel, None


async def claim_ticket(
    bot, channel: discord.TextChannel, ticket: Ticket, member
) -> None:
    ticket.claimed_id = member.id
    await bot.db.execute(
        "UPDATE tickets SET claimed_id = ? WHERE channel_id = ?",
        (member.id, channel.id))


async def add_member(
    channel: discord.TextChannel, member: discord.Member, *, reason: str
) -> None:
    overwrite = channel.overwrites_for(member)
    overwrite.view_channel = True
    overwrite.send_messages = True
    overwrite.read_message_history = True
    overwrite.attach_files = True
    overwrite.embed_links = True
    await channel.set_permissions(member, overwrite=overwrite, reason=reason)


async def remove_member(
    channel: discord.TextChannel, member: discord.Member, *, reason: str
) -> None:
    overwrite = channel.overwrites_for(member)
    overwrite.view_channel = False
    overwrite.send_messages = False
    overwrite.read_message_history = False
    await channel.set_permissions(member, overwrite=overwrite, reason=reason)


async def rename_ticket(
    channel: discord.TextChannel, name: str, *, reason: str
) -> None:
    await channel.edit(name=name, reason=reason)


def _display_name(user) -> str:
    for attribute in ("display_name", "global_name", "name"):
        value = getattr(user, attribute, None)
        if value:
            return str(value)
    return str(user)


def _avatar_url(user) -> str | None:
    return getattr(getattr(user, "display_avatar", None), "url", None)


def _message_html(
    message: discord.Message, *, guild, guild_id: int, channel_id: int
) -> str:
    author = message.author
    avatar = _avatar_url(author)
    avatar_html = (
        f'<img class="avatar" src="{html.escape(avatar)}" alt="">'
        if avatar
        else '<div class="avatar"></div>'
    )
    body = [
        '<div class="head">'
        f'<span class="name">{html.escape(_display_name(author))}</span>'
        f'<span class="handle">{html.escape(str(author))}</span>'
        f'<time>{message.created_at.strftime("%Y-%m-%d %H:%M UTC")}</time>'
        "</div>"
    ]

    reference = message.reference
    if reference is not None:
        resolved = getattr(reference, "resolved", None)
        label = "Replying to a message"
        quote = ""
        if isinstance(resolved, discord.Message):
            label = f"Replying to {_display_name(resolved.author)}"
            if resolved.content:
                quote = (
                    f'<span class="quote">'
                    f"{render_inline(resolved.content[:120], guild)}</span>"
                )
        url = getattr(reference, "jump_url", None)
        if url:
            body.append(
                f'<a class="reply" href="{html.escape(url)}">↪ '
                f"{html.escape(label)}</a>{quote}"
            )
        else:
            body.append(f'<div class="reply">↪ {html.escape(label)}</div>{quote}')

    if message.content:
        body.append(render_content(message.content, guild))

    for embed in message.embeds[:5]:
        accent = f"#{embed.color.value:06x}" if embed.color else "#85858b"
        parts = [f'<div class="embed" style="border-left-color: {accent}">']
        title = render_emoji(embed.title) if embed.title else "Embed"
        if embed.url:
            parts.append(
                f'<a class="embed-title" href="{html.escape(embed.url)}" '
                f'rel="noreferrer noopener">{title}</a>'
            )
        else:
            parts.append(f'<span class="embed-title">{title}</span>')
        if embed.author and embed.author.name:
            parts.append(
                f'<div class="field muted">{render_emoji(embed.author.name[:120])}'
                "</div>"
            )
        if embed.description:
            parts.append(render_content(embed.description[:600], guild))
        if embed.image and embed.image.url:
            parts.append(
                f'<a href="{html.escape(embed.image.url)}" target="_blank" '
                f'rel="noreferrer noopener"><img class="image" '
                f'src="{html.escape(embed.image.url)}" alt="" loading="lazy"></a>'
            )
        if embed.thumbnail and embed.thumbnail.url:
            parts.append(
                f'<img class="thumb" src="{html.escape(embed.thumbnail.url)}" '
                'alt="" loading="lazy">'
            )
        for field in embed.fields[:6]:
            parts.append(
                f'<div class="field"><strong>{render_emoji(field.name[:120])}'
                f"</strong>{render_content(field.value[:300], guild)}</div>"
            )
        if embed.footer and embed.footer.text:
            parts.append(
                f'<div class="field muted">{render_emoji(embed.footer.text[:120])}'
                "</div>"
            )
        parts.append("</div>")
        body.append("".join(parts))

    clip_url = emoji_data_uri("paper") or emoji_image("paper")
    clip = (
        f'<img class="emoji" src="{html.escape(clip_url)}" alt="attachment"> '
        if clip_url
        else ""
    )
    for attachment in message.attachments:
        if is_image(
            attachment.filename,
            getattr(attachment, "content_type", None)):
            body.append(
                f'<a href="{html.escape(attachment.url)}" target="_blank" '
                f'rel="noreferrer noopener">'
                f'<img class="image" src="{html.escape(attachment.url)}" '
                f'alt="{html.escape(attachment.filename)}" loading="lazy"></a>'
            )
            continue
        body.append(
            f'<a class="attachment" href="{html.escape(attachment.url)}">'
            f"{clip}{html.escape(attachment.filename)}</a>"
        )

    body.append(
        f'<a class="jump" href="https://discord.com/channels/{guild_id}/'
        f'{channel_id}/{message.id}">open in Discord</a>'
    )
    return (
        f'<article class="message">{avatar_html}'
        f'<div class="body">{"".join(body)}</div></article>'
    )


def transcript_url(guild_id: int, channel_id: int) -> str:
    return f"{settings.transcript_url.rstrip('/')}/{guild_id}/{channel_id}"


async def _recent_messages(
    channel: discord.TextChannel) -> list[discord.Message]:
    # Newest-first keeps the most recent messages when a ticket is huge;
    # transcripts are written back in chronological order.
    messages = [
        message
        async for message in channel.history(
            limit=TRANSCRIPT_LIMIT, oldest_first=False
        )
    ]
    messages.reverse()
    return messages


async def build_transcript(
    channel: discord.TextChannel,
    ticket: Ticket,
    *,
    closed_by,
    reason: str | None = None,
    url: str | None = None,
    messages: list[discord.Message] | None = None) -> bytes:
    guild = channel.guild
    if messages is None:
        messages = await _recent_messages(channel)

    def who(user_id: int | None) -> str:
        if user_id is None:
            return "—"
        member = guild.get_member(user_id) if guild is not None else None
        if member is not None:
            return f"{_display_name(member)} ({user_id})"
        return f"<@{user_id}>"

    period = "—"
    if messages:
        period = (
            f"{messages[0].created_at.strftime('%Y-%m-%d %H:%M')} – "
            f"{messages[-1].created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    meta = [
        ("Opened by", who(ticket.opener_id)),
        ("Claimed by", who(ticket.claimed_id)),
        ("Closed by", _display_name(closed_by) if closed_by is not None else "—"),
        ("Messages", str(len(messages))),
        ("Period", period),
        ("Channel", f"#{channel.name}"),
    ]
    if reason:
        meta.append(("Closed because", reason))
    meta_html = "".join(
        f'<div class="meta"><span>{html.escape(label)}</span>'
        f"<strong>{html.escape(value)}</strong></div>"
        for label, value in meta
    )

    if messages:
        body_html = "".join(
            _message_html(
                message, guild=guild, guild_id=guild.id, channel_id=channel.id
            )
            for message in messages
        )
    else:
        body_html = '<p class="muted">No messages were sent in this ticket.</p>'

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ticket #{ticket.number:04d} · {html.escape(guild.name)}</title>
<style>{TRANSCRIPT_STYLE}</style>
</head>
<body>
<main>
<p class="eyebrow">Support transcript</p>
<h1>Ticket #{ticket.number:04d}</h1>
<p class="topic">{html.escape(ticket.topic)}</p>
{f'<p class="online"><a href="{html.escape(url)}">View this transcript online</a></p>' if url else ''}
<div class="meta-grid">{meta_html}</div>
<section class="messages">{body_html}</section>
<footer>{html.escape(guild.name)} · ticket #{ticket.number:04d} · {len(messages)} messages</footer>
</main>
</body>
</html>"""
    return document.encode("utf-8")


def build_text_transcript(
    channel: discord.TextChannel,
    ticket: Ticket,
    *,
    closed_by,
    reason: str | None = None,
    url: str | None = None,
    messages: list[discord.Message]) -> str:
    """Plain-text copy of the transcript for the opener and the log channel."""
    guild = channel.guild

    def who(user_id: int | None) -> str:
        if user_id is None:
            return "—"
        member = guild.get_member(user_id) if guild is not None else None
        if member is not None:
            return f"{_display_name(member)} ({user_id})"
        return f"<@{user_id}>"

    lines = [
        f"Ticket #{ticket.number:04d} — {guild.name}",
        "Support transcript",
        "",
        f"Topic: {ticket.topic}",
        f"Opened by: {who(ticket.opener_id)}",
        f"Claimed by: {who(ticket.claimed_id)}",
        f"Closed by: {_display_name(closed_by) if closed_by is not None else '—'}",
    ]
    if reason:
        lines.append(f"Closed because: {reason}")
    lines.append(f"Messages: {len(messages)}")
    if messages:
        lines.append(
            f"Period: {messages[0].created_at.strftime('%Y-%m-%d %H:%M')} – "
            f"{messages[-1].created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    lines.append(f"Channel: #{channel.name}")
    if url:
        lines.append(f"Online (HTML): {url}")
    lines.append("")

    for message in messages:
        author = message.author
        lines.append(
            f"[{message.created_at.strftime('%Y-%m-%d %H:%M UTC')}] "
            f"{_display_name(author)} ({author}):"
        )
        reference = message.reference
        if reference is not None:
            resolved = getattr(reference, "resolved", None)
            if isinstance(resolved, discord.Message):
                lines.append(f"  ↪ replying to {_display_name(resolved.author)}")
        if message.content:
            lines.extend(
                f"  {line}"
                for line in emoji_shortcodes(message.content).splitlines()
            )
        for embed in message.embeds[:5]:
            if embed.title:
                lines.append(f"  [embed] {emoji_shortcodes(embed.title)}")
            if embed.description:
                lines.append(f"  {emoji_shortcodes(embed.description[:600])}")
            for field in embed.fields[:6]:
                lines.append(
                    f"  {emoji_shortcodes(field.name[:120])}: "
                    f"{emoji_shortcodes(field.value[:300])}"
                )
        for attachment in message.attachments:
            lines.append(f"  [attachment] {attachment.filename} — {attachment.url}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


async def close_ticket(
    bot,
    channel: discord.TextChannel,
    ticket: Ticket,
    *,
    closed_by,
    reason: str | None = None,
    transcript: bool = True) -> bool:
    guild = channel.guild
    config = _configs.get(guild.id)
    online = transcript_url(guild.id, channel.id)
    data = None
    text_data = None
    if transcript:
        try:
            messages = await _recent_messages(channel)
            data = await build_transcript(
                channel,
                ticket,
                closed_by=closed_by,
                reason=reason,
                url=online,
                messages=messages)
            text_data = build_text_transcript(
                channel,
                ticket,
                closed_by=closed_by,
                reason=reason,
                url=online,
                messages=messages)
        except discord.HTTPException as exc:
            log.warning(
                "Could not build transcript for ticket %s: %s", ticket.number, exc
            )

    if data is not None:
        try:
            await bot.db.execute(
                "INSERT OR REPLACE INTO ticket_transcripts "
                "(channel_id, guild_id, number, topic, html) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    channel.id,
                    guild.id,
                    ticket.number,
                    ticket.topic,
                    data.decode("utf-8")))
        except sqlite3.Error:
            log.exception(
                "Could not store transcript for ticket %s", ticket.number
            )

    has_transcript = data is not None and text_data is not None
    embed = ticket_closed_dm_embed(
        guild_name=guild.name,
        number=ticket.number,
        closed_by=str(closed_by),
        reason=reason,
        transcript=has_transcript,
        url=online if has_transcript else None)
    opener = guild.get_member(ticket.opener_id)
    if opener is None:
        opener = bot.get_user(ticket.opener_id)
    if opener is None:
        with suppress(discord.HTTPException):
            opener = await bot.fetch_user(ticket.opener_id)
    if opener is not None:
        payload = {"embed": embed}
        if text_data is not None:
            payload["file"] = discord.File(
                io.BytesIO(text_data.encode("utf-8")),
                filename=f"ticket-{ticket.number:04d}.txt")
        with suppress(discord.HTTPException):
            await opener.send(**payload)

    if has_transcript and config is not None and config.log_channel_id is not None:
        log_channel = guild.get_channel(config.log_channel_id)
        if isinstance(log_channel, discord.TextChannel):
            with suppress(discord.HTTPException):
                await log_channel.send(
                    embed=embed,
                    file=discord.File(
                        io.BytesIO(text_data.encode("utf-8")),
                        filename=f"ticket-{ticket.number:04d}.txt"))

    try:
        await channel.delete(reason=f"Ticket closed by {closed_by}")
    except discord.HTTPException as exc:
        log.warning("Could not delete ticket channel %s: %s", channel.id, exc)
        return False

    _tickets.pop(channel.id, None)
    await bot.db.execute(
        "DELETE FROM tickets WHERE channel_id = ?", (channel.id)
    )
    return True


async def load_state(bot) -> None:
    global _loaded
    _loaded = True

    for row in await bot.db.fetchall(
        "SELECT guild_id, category_id, staff_role_id, panel_channel_id, "
        "panel_message_id, log_channel_id FROM ticket_config"
    ):
        _configs[row["guild_id"]] = Config(
            category_id=row["category_id"],
            staff_role_id=row["staff_role_id"],
            panel_channel_id=row["panel_channel_id"],
            panel_message_id=row["panel_message_id"],
            log_channel_id=row["log_channel_id"])

    for row in await bot.db.fetchall(
        "SELECT channel_id, guild_id, number, opener_id, claimed_id, topic "
        "FROM tickets"
    ):
        channel = bot.get_channel(row["channel_id"])
        if channel is None:
            with suppress(discord.HTTPException):
                channel = await bot.fetch_channel(row["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            await bot.db.execute(
                "DELETE FROM tickets WHERE channel_id = ?", (row["channel_id"])
            )
            continue
        _tickets[channel.id] = Ticket(
            number=row["number"],
            guild_id=row["guild_id"],
            opener_id=row["opener_id"],
            claimed_id=row["claimed_id"],
            topic=row["topic"])
