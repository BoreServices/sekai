import logging
import time
from contextlib import suppress
from dataclasses import dataclass

import discord
from discord.ext import commands

from core import prefix as prefixes
from view import info_embed, success_embed

log = logging.getLogger("sekai.afk")

OFF_VALUES = {"off", "stop", "clear"}
MAX_REASON = 200


@dataclass
class AfkEntry:
    reason: str
    since: int


_entries: dict[tuple[int, int], AfkEntry] = {}
_loaded = False


async def load_state(bot) -> None:
    global _loaded
    _loaded = True
    _entries.clear()
    for row in await bot.db.fetchall(
        "SELECT guild_id, user_id, reason, since FROM afk"
    ):
        _entries[(row["guild_id"], row["user_id"])] = AfkEntry(
            reason=row["reason"], since=row["since"]
        )


async def clear(bot, guild_id: int, user_id: int) -> None:
    if _entries.pop((guild_id, user_id), None) is not None:
        await bot.db.execute(
            "DELETE FROM afk WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id))


async def set_afk(bot, guild_id: int, user_id: int, reason: str) -> AfkEntry:
    entry = AfkEntry(reason=reason, since=int(time.time()))
    _entries[(guild_id, user_id)] = entry
    await bot.db.execute(
        """
        INSERT INTO afk (guild_id, user_id, reason, since) VALUES (?, ?, ?, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            reason = excluded.reason,
            since = excluded.since
        """,
        (guild_id, user_id, reason, entry.since))
    return entry


def setup(bot) -> None:
    @bot.listen("on_ready")
    async def load_afk() -> None:
        if not _loaded:
            await load_state(bot)

    @bot.command(
        name="afk",
        help="Tell everyone you're away. Mentions will say why.",
        usage="afk [reason|off]")
    @commands.guild_only()
    async def afk(ctx: commands.Context, *, reason: str | None = None) -> None:
        if reason is not None and reason.strip().lower() in OFF_VALUES:
            if (ctx.guild.id, ctx.author.id) in _entries:
                await clear(bot, ctx.guild.id, ctx.author.id)
                await ctx.send(
                    embed=success_embed("Your AFK status is cleared.", icon="👋")
                )
            else:
                await ctx.send(
                    embed=info_embed(
                        title="AFK",
                        description="You weren't AFK.",
                        fields=[])
                )
            return

        reason = (reason or "").strip() or "AFK"
        if len(reason) > MAX_REASON:
            reason = reason[:MAX_REASON]
        await set_afk(bot, ctx.guild.id, ctx.author.id, reason)
        await ctx.send(
            embed=success_embed(
                f"You're AFK: **{discord.utils.escape_markdown(reason)}**. "
                "I'll mention it when someone pings you.",
                icon="👋")
        )

    @bot.listen("on_message")
    async def afk_notices(message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not _entries:
            return
        if not _loaded:
            await load_state(bot)

        guild_id = message.guild.id
        author_afk = (guild_id, message.author.id) in _entries
        mentioned = [
            member
            for member in message.mentions
            if not member.bot
            and member.id != message.author.id
            and (guild_id, member.id) in _entries
        ]
        if not author_afk and not mentioned:
            return

        prefix = await prefixes.get_guild_prefix(bot, guild_id)
        if message.content.startswith(prefix):
            return

        if author_afk:
            await clear(bot, guild_id, message.author.id)
            with suppress(discord.HTTPException):
                await message.channel.send(
                    embed=success_embed(
                        f"Welcome back {message.author.mention} — your AFK "
                        "status was cleared.",
                        icon="👋")
                )

        if not mentioned:
            return
        lines = []
        for member in mentioned[:3]:
            entry = _entries.get((guild_id, member.id))
            if entry is None:
                continue
            lines.append(
                f"{member.mention} is AFK — "
                f"{discord.utils.escape_markdown(entry.reason)} "
                f"(since <t:{entry.since}:R>)"
            )
        if lines:
            with suppress(discord.HTTPException):
                await message.channel.send(
                    embed=info_embed(
                        title="AFK", description="\n".join(lines), fields=[]
                    )
                )

    @bot.listen("on_member_remove")
    async def forget_afk(member: discord.Member) -> None:
        if not member.bot:
            await clear(bot, member.guild.id, member.id)
