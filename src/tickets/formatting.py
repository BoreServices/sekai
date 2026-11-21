import html
import re

from core.emojis import emoji_data_uri

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*```(.*)$")
_FENCE_END = re.compile(r"^\s*```\s*$")

_MASKED_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)\"']+)\)")
_URL = re.compile(r"https?://[^\s<>\"']+")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_UNDERLINE = re.compile(r"__(?=\S)(.+?)(?<=\S)__")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_SPOILER = re.compile(r"\|\|(?=\S)(.+?)(?<=\S)\|\|")
_ITALIC_STAR = re.compile(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)")
_ITALIC_UNDER = re.compile(r"(?<!_)_(?=\S)(.+?)(?<=\S)_(?!_)")

_USER = re.compile(r"&lt;@!?(\d+)&gt;")
_CHANNEL = re.compile(r"&lt;#(\d+)&gt;")
_ROLE = re.compile(r"&lt;@&amp;(\d+)&gt;")
_CUSTOM_EMOJI = re.compile(r"&lt;(a?):([\w~]+):(\d+)&gt;")
_CUSTOM_EMOJI_RAW = re.compile(r"<a?:([\w~]+):\d+>")

_TOKEN = re.compile("\ue000(\\d+)\ue001")
_TRAILING = ".,!?;:)]}…*~|"


def _stash(store: list[str], value: str) -> str:
    store.append(value)
    return f"\ue000{len(store) - 1}\ue001"


def _member_label(guild, raw_id: str) -> str:
    member = guild.get_member(int(raw_id)) if guild is not None else None
    name = member.display_name if member is not None else raw_id
    return f'<span class="mention">@{html.escape(str(name))}</span>'


def _channel_label(guild, raw_id: str) -> str:
    channel = guild.get_channel(int(raw_id)) if guild is not None else None
    name = channel.name if channel is not None else raw_id
    return f'<span class="mention">#{html.escape(str(name))}</span>'


def _role_label(guild, raw_id: str) -> str:
    role = guild.get_role(int(raw_id)) if guild is not None else None
    name = role.name if role is not None else raw_id
    return f'<span class="mention">@{html.escape(str(name))}</span>'


def _emoji_tag(match: re.Match[str], store: list[str]) -> str:
    animated, name, emoji_id = match.groups()
    # The bot's own emojis are inlined from the emoji folder so transcripts
    # keep working offline and after an emoji is deleted; foreign emojis
    # fall back to the Discord CDN.
    url = emoji_data_uri(name)
    if url is None:
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
    return _stash(
        store,
        f'<img class="emoji" src="{html.escape(url)}" '
        f'alt=":{html.escape(name)}:" title=":{html.escape(name)}:">')


def render_emoji(text: str) -> str:
    """Escape plain text and render custom emoji (embed titles, authors, footers)."""
    escaped = html.escape(text, quote=False)
    store: list[str] = []
    escaped = _CUSTOM_EMOJI.sub(lambda m: _emoji_tag(m, store), escaped)
    return _TOKEN.sub(lambda m: store[int(m.group(1))], escaped)


def emoji_shortcodes(text: str) -> str:
    """Replace custom emoji markup with :name: for plain-text transcripts."""
    return _CUSTOM_EMOJI_RAW.sub(r":\1:", text)


def render_inline(text: str, guild=None) -> str:
    """Escape text and apply Discord inline markdown (links, mentions, emphasis)."""
    escaped = html.escape(text, quote=False)
    store: list[str] = []

    def code(match: re.Match[str]) -> str:
        return _stash(store, f'<code class="inline-code">{match.group(1)}</code>')

    def masked(match: re.Match[str]) -> str:
        label, url = match.groups()
        return _stash(
            store,
            f'<a href="{url}" rel="noreferrer noopener">{label}</a>')

    def url(match: re.Match[str]) -> str:
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in _TRAILING:
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        if not raw:
            return trailing
        link = _stash(
            store, f'<a href="{raw}" rel="noreferrer noopener">{raw}</a>'
        )
        return link + trailing

    escaped = _INLINE_CODE.sub(code, escaped)
    escaped = _MASKED_LINK.sub(masked, escaped)
    escaped = _CUSTOM_EMOJI.sub(lambda m: _emoji_tag(m, store), escaped)
    escaped = _USER.sub(lambda m: _member_label(guild, m.group(1)), escaped)
    escaped = _CHANNEL.sub(lambda m: _channel_label(guild, m.group(1)), escaped)
    escaped = _ROLE.sub(lambda m: _role_label(guild, m.group(1)), escaped)
    escaped = _URL.sub(url, escaped)

    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _UNDERLINE.sub(r"<u>\1</u>", escaped)
    escaped = _STRIKE.sub(r"<s>\1</s>", escaped)
    escaped = _SPOILER.sub(r'<span class="spoiler">\1</span>', escaped)
    escaped = _ITALIC_STAR.sub(r"<em>\1</em>", escaped)
    escaped = _ITALIC_UNDER.sub(r"<em>\1</em>", escaped)

    return _TOKEN.sub(lambda m: store[int(m.group(1))], escaped)


def render_content(text: str, guild=None) -> str:
    """Render a Discord message body to HTML blocks (code fences, quotes, lists)."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    kind: str | None = None
    quote: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append('<div class="text">' + "<br>".join(paragraph) + "</div>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal kind
        if items:
            tag = kind or "ul"
            out.append(
                f"<{tag}>"
                + "".join(f"<li>{item}</li>" for item in items)
                + f"</{tag}>"
            )
            items.clear()
        kind = None

    def flush_quote() -> None:
        if quote:
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            quote.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            flush_list()
            flush_quote()
            language = fence.group(1).strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not _FENCE_END.match(lines[index]):
                code_lines.append(lines[index])
                index += 1
            code = html.escape("\n".join(code_lines), quote=False)
            label = (
                f'<span class="code-lang">{html.escape(language)}</span>'
                if language
                else ""
            )
            out.append(f'<pre class="code">{label}<code>{code}</code></pre>')
            index += 1
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(heading.group(1))
            out.append(
                f'<div class="heading heading-{level}">'
                f"{render_inline(heading.group(2), guild)}</div>"
            )
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            quote.append(render_inline(stripped[1:].lstrip(" "), guild))
            index += 1
            continue

        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        if bullet or numbered:
            flush_paragraph()
            flush_quote()
            wanted = "ul" if bullet else "ol"
            if kind is not None and kind != wanted:
                flush_list()
            kind = wanted
            items.append(render_inline((bullet or numbered).group(1), guild))
            index += 1
            continue

        flush_list()
        flush_quote()
        paragraph.append(render_inline(line, guild))
        index += 1

    flush_paragraph()
    flush_list()
    flush_quote()
    return "".join(out)


def is_image(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("image/"):
        return True
    lowered = filename.lower()
    return any(lowered.endswith(suffix) for suffix in IMAGE_SUFFIXES)
