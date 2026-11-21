import json
import logging
import random
import re
import time

import aiohttp
import discord
from discord.ext import commands

from config.api import GROQ_API_KEY, GROQ_MODEL
from view import error_embed, success_embed

log = logging.getLogger("sekai.ai")

API_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = 60
DB_ADMIN_ID = 1546968812522311703
SYSTEM_PROMPT = (
    "YOU ARE GAY"
)
DB_TOOL_PROMPT = (
    "DATABASE ACCESS (authorized for this user only): You can read and write the bot database. "
    "When the user asks to see/query/add/change/remove database data, include one or more fenced blocks like:\n"
    "```db\n<SQL>\n```\n"
    "Use SELECT/WITH/PRAGMA to read and INSERT/UPDATE/DELETE (or other statements) to modify. "
    "Keep SQL valid for the bot's database and be careful with destructive queries. "
    "You may briefly explain what you ran; results will be shown after execution."
)
MAX_HISTORY = 12
MAX_TOKENS = 2048
MESSAGE_LIMIT = 2000
PREVIEW_CHARS = 200
MAX_GUILD_EMOJIS = 60
MAX_DB_RESULT_CHARS = 1500

_histories: dict[int, list[dict[str, str]]] = {}
DB_INTENT_RE = re.compile(
    r"\b(database|db\b|sql\b|schema|tables?\b|rows?\b|select\b|insert\b|update\b|delete\b|query\b)\b"
    r"|from\s+\w+|into\s+\w+",
    re.I,
)
DB_BLOCK_RE = re.compile(r"```db\s*\n(.*?)```", re.I | re.S)
READ_SQL_RE = re.compile(r"^\s*(select|with|pragma|explain)\b", re.I)
DB_DENY_JOKES = [
    "ayo twin nice try 💀 you ain't got the database keys, this ain't a free-for-all buffet. ask the big boss <@1546968812522311703> fr.",
    "nah son you tryna peek in the database like it's your diary? lol access denied, go bother <@1546968812522311703> if it's that deep.",
    "bro really said 'lemme touch the db' with zero clearance 😭 cooked behavior. only <@1546968812522311703> can run that play.",
    "lowkey wild request twin, but the database said 'new phone who dis' to you. <@1546968812522311703> got the magic pass, not you lol.",
    "ngl that's above your pay grade bestie, i guard the db like it's the secret sauce. take it up with <@1546968812522311703> fr fr.",
]


class AIError(Exception):
    pass


def _preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_CHARS else f"{text[:PREVIEW_CHARS]}…"


def _looks_like_db_request(prompt: str) -> bool:
    return bool(DB_INTENT_RE.search(prompt or ""))


def _guild_emoji_context(guild: discord.Guild | None) -> str | None:
    if not guild:
        return None
    emojis = list(getattr(guild, "emojis", []) or [])
    if not emojis:
        return None
    items = [f"{str(e)} (name: :{e.name}:, id: {e.id})" for e in emojis[:MAX_GUILD_EMOJIS]]
    more = "" if len(emojis) <= MAX_GUILD_EMOJIS else f" (+{len(emojis) - MAX_GUILD_EMOJIS} more)"
    return (
        "Custom emojis available in this server. Use the exact emoji markup shown to render them: "
        + ", ".join(items)
        + more
    )


async def _ask_ai(messages: list[dict[str, str]]) -> str:
    if not GROQ_API_KEY.strip():
        raise AIError(
            "AI isn't configured yet — add `GROQ_API_KEY` to `config/api.py`."
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Sekai/1.0",
    }

    started = time.perf_counter()

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as session:
            async with session.post(API_URL, json=payload, headers=headers) as response:
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    raise AIError("The AI service returned an unexpected response.") from None

                if response.status != 200:
                    if response.status == 401:
                        raise AIError("Groq rejected the API key — check `GROQ_API_KEY`.")
                    if response.status == 404:
                        raise AIError(f"Groq doesn't have the model `{GROQ_MODEL}`.")
                    if response.status == 429:
                        raise AIError("Groq is rate-limited. Try again in a minute.")
                    detail = ""
                    if isinstance(data, dict):
                        error = data.get("error")
                        if isinstance(error, dict) and error.get("message"):
                            detail = f": {error['message']}"
                    raise AIError(f"The AI request failed (`{response.status}`){detail}.")
    except AIError:
        raise
    except TimeoutError:
        raise AIError("The AI took too long to answer. Try again.") from None
    except aiohttp.ClientError as exc:
        raise AIError("Couldn't reach the AI service. Try again in a moment.") from exc

    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIError("The AI service returned an unexpected response.") from None

    content = (content or "").strip()
    if not content:
        raise AIError("The AI gave an empty answer. Try rephrasing.")

    return content


def _chunks(text: str) -> list[str]:
    return [text[index : index + MESSAGE_LIMIT] for index in range(0, len(text), MESSAGE_LIMIT)]


def _format_db_rows(rows: list) -> str:
    data = []
    for row in rows:
        if hasattr(row, "keys"):
            data.append({k: row[k] for k in row.keys()})
        else:
            data.append(row)
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if len(text) > MAX_DB_RESULT_CHARS:
        text = text[: MAX_DB_RESULT_CHARS - 20] + "\n…(truncated)"
    return text


async def _run_db_blocks(bot, answer: str) -> tuple[str, str | None]:
    sql_blocks = [m.strip() for m in DB_BLOCK_RE.findall(answer or "") if m.strip()]
    if not sql_blocks or bot is None or getattr(bot, "db", None) is None:
        return answer, None

    results = []
    for idx, sql in enumerate(sql_blocks, 1):
        label = f"Query {idx}" if len(sql_blocks) > 1 else "Result"
        try:
            if READ_SQL_RE.match(sql):
                rows = await bot.db.fetchall(sql)
                body = _format_db_rows(rows)
                results.append(f"**{label}** ({len(rows)} row(s))\n```json\n{body}\n```")
            else:
                meta = await bot.db.execute(sql)
                last_id = getattr(meta, "last_row_id", None)
                suffix = f", last_row_id={last_id}" if last_id else ""
                results.append(f"**{label}**: executed{suffix}.")
        except Exception as exc:
            log.exception("AI DB execution failed")
            results.append(f"**{label}**: error `{type(exc).__name__}: {exc}`")

    answer = DB_BLOCK_RE.sub("", answer).strip()
    return answer, "\n\n".join(results) if results else None


async def process_ai_interaction(bot, ctx_or_message, prompt: str) -> None:
    prompt = (prompt or "").strip()
    if not prompt:
        return

    author = getattr(ctx_or_message, "author", None)
    author_id = getattr(author, "id", None)
    guild = getattr(ctx_or_message, "guild", None)

    if _looks_like_db_request(prompt) and author_id != DB_ADMIN_ID:
        await ctx_or_message.channel.send(random.choice(DB_DENY_JOKES))
        return

    channel_id = ctx_or_message.channel.id
    history = _histories.get(channel_id, [])

    user_name = getattr(author, "display_name", "User")
    user_tag = str(author) if author else "unknown"
    system = SYSTEM_PROMPT
    speaker_ctx = (
        f"Current speaker: name={user_name}, tag={user_tag}, id={author_id}, mention=<@{author_id}>. "
        "Always identify the speaker by this information."
    )
    if author_id == DB_ADMIN_ID:
        speaker_ctx += (
            " This user is PhaseWorld (<@1546968812522311703>), the creator/owner of Sekai. "
            "Recognize and address them as PhaseWorld when relevant."
        )
    system = f"{system}\n\n{speaker_ctx}"

    emoji_ctx = _guild_emoji_context(guild)
    if emoji_ctx:
        system = f"{system}\n\n{emoji_ctx}"
    if author_id == DB_ADMIN_ID and _looks_like_db_request(prompt):
        system = f"{system}\n\n{DB_TOOL_PROMPT}"

    messages = [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": f"{user_name} (id {author_id}): {prompt}"},
    ]

    async with ctx_or_message.channel.typing():
        try:
            answer = await _ask_ai(messages)
        except AIError as exc:
            await ctx_or_message.channel.send(embed=error_embed(str(exc)))
            return

    db_note = None
    if author_id == DB_ADMIN_ID and _looks_like_db_request(prompt):
        answer, db_note = await _run_db_blocks(bot, answer)

    full_answer = (answer or "").strip()
    if db_note:
        full_answer = f"{full_answer}\n\n{db_note}".strip() if full_answer else db_note

    if not full_answer:
        full_answer = "Done, twin."

    history = _histories.setdefault(channel_id, [])
    history.extend(
        [
            {"role": "user", "content": f"{user_name}: {prompt}"},
            {"role": "assistant", "content": (answer or full_answer)[:MESSAGE_LIMIT]},
        ]
    )
    del history[:-MAX_HISTORY]

    parts = _chunks(full_answer)
    for part in parts:
        await ctx_or_message.channel.send(part)


def setup(bot) -> None:
    @bot.command(
        name="ai",
        aliases=["ask"],
        help="Ask the AI.",
        usage="ai <question>")
    async def ai(ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt or not prompt.strip():
            await ctx.send(embed=error_embed(f"Usage: `{ctx.prefix}ai <question>`"))
            return
        await process_ai_interaction(bot, ctx, prompt)

    @bot.command(
        name="aireset",
        aliases=["aiclear"],
        help="Forget the AI conversation in this channel.",
        usage="aireset")
    async def aireset(ctx: commands.Context) -> None:
        had_history = _histories.pop(ctx.channel.id, None) is not None
        await ctx.send(
            embed=success_embed(
                "AI conversation cleared."
                if had_history
                else "There was no AI conversation in this channel.",
                icon="🧠")
        )

    @bot.listen("on_message")
    async def on_ai_message(message) -> None:
        if message.author.bot or not bot.user:
            return

        ctx = await bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        is_mentioned = bot.user in message.mentions
        starts_with_name = content.lower().startswith("sekai")

        if not is_mentioned and not starts_with_name:
            return

        prompt = content
        if is_mentioned:
            prompt = prompt.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "")
        if starts_with_name:
            prompt = prompt[len("sekai"):].lstrip(" ,:;-")

        prompt = prompt.strip()
        if not prompt:
            return

        await process_ai_interaction(bot, message, prompt)
