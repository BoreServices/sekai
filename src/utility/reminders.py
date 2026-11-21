import logging
import time
from contextlib import suppress

import discord
from discord.ext import commands, tasks

from core.duration import parse_duration
from view import error_embed, info_embed, success_embed

log = logging.getLogger("sekai.reminders")

LOOP_SECONDS = 20
MAX_PENDING = 15
MAX_TEXT = 1900


async def _deliver_due(bot) -> None:
    rows = await bot.db.fetchall(
        "SELECT id, user_id, guild_id, channel_id, message FROM reminders "
        "WHERE due_at <= ? ORDER BY due_at",
        (int(time.time()),))
    for row in rows:
        embed = info_embed(
            title="⏳ Reminder",
            description=row["message"][:MAX_TEXT] or "(no text)",
            fields=[])
        user = bot.get_user(row["user_id"])
        if user is None:
            with suppress(discord.HTTPException):
                user = await bot.fetch_user(row["user_id"])

        sent = False
        channel = bot.get_channel(row["channel_id"])
        if isinstance(channel, discord.abc.Messageable):
            content = (
                user.mention
                if user is not None and row["guild_id"] is not None
                else None
            )
            try:
                await channel.send(content=content, embed=embed)
                sent = True
            except discord.HTTPException:
                sent = False
        if not sent and user is not None:
            with suppress(discord.HTTPException):
                await user.send(embed=embed)
                sent = True

        await bot.db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))
        log.info(
            "Reminder %s for %s delivered=%s", row["id"], row["user_id"], sent
        )


def setup(bot) -> None:
    @tasks.loop(seconds=LOOP_SECONDS)
    async def reminder_loop() -> None:
        await bot.wait_until_ready()
        await _deliver_due(bot)

    if not reminder_loop.is_running():
        reminder_loop.start()

    @bot.command(
        name="remind",
        help="Set a reminder in this channel.",
        usage="remind <duration> <text>")
    async def remind(ctx: commands.Context, duration: str, *, text: str) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=error_embed(
                    "Duration must look like `30s`, `10m`, `2h` or `1d30m`."
                )
            )
            return
        text = text.strip()
        if not text:
            await ctx.send(embed=error_embed("Tell me what to remind you about."))
            return

        due_at = int(time.time()) + seconds
        reminder_id = await bot.db.insert(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, "
            "due_at) VALUES (?, ?, ?, ?, ?)",
            (
                ctx.author.id,
                ctx.guild.id if ctx.guild is not None else None,
                ctx.channel.id,
                text[:MAX_TEXT],
                due_at))
        await ctx.send(
            embed=success_embed(
                f"Reminder **#{reminder_id}** set for <t:{due_at}:R>.\n"
                f"> {discord.utils.escape_markdown(text)}",
                icon="⏳")
        )

    @bot.command(
        name="reminders",
        aliases=["remindlist"],
        help="List your pending reminders.",
        usage="reminders")
    async def reminders(ctx: commands.Context) -> None:
        rows = await bot.db.fetchall(
            "SELECT id, message, due_at FROM reminders WHERE user_id = ? "
            "ORDER BY due_at LIMIT ?",
            (ctx.author.id, MAX_PENDING))
        if not rows:
            await ctx.send(
                embed=info_embed(
                    title="Your reminders",
                    description="You have no pending reminders.",
                    fields=[])
            )
            return
        fields = [
            (
                f"#{row['id']} · <t:{row['due_at']}:R>",
                row["message"][:200],
                False)
            for row in rows
        ]
        await ctx.send(
            embed=info_embed(
                title="Your reminders",
                description=(
                    f"You have {len(rows)} pending reminder(s). "
                    "Cancel one with `forget <id>`."
                ),
                fields=fields)
        )

    @bot.command(
        name="forget",
        aliases=["remindcancel"],
        help="Cancel one of your reminders.",
        usage="forget <id>")
    async def forget(ctx: commands.Context, reminder_id: int) -> None:
        row = await bot.db.fetchone(
            "SELECT user_id FROM reminders WHERE id = ?", (reminder_id)
        )
        if row is None or row["user_id"] != ctx.author.id:
            await ctx.send(
                embed=error_embed("You don't have a reminder with that ID.")
            )
            return
        await bot.db.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id)
        )
        await ctx.send(
            embed=success_embed(f"Reminder **#{reminder_id}** cancelled.")
        )
