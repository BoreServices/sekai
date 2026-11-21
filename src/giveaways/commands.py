import logging
import secrets
import time

import discord
from discord.ext import commands, tasks

from core.duration import parse_duration
from src.giveaways import state
from view import error_embed, info_embed, success_embed
from view.giveaway import GiveawayView, giveaway_embed

log = logging.getLogger("sekai.giveaways")

MAX_WINNERS = 20
MAX_PRIZE = 200
LOOP_SECONDS = 15


def _mentions(winner_ids: list[int]) -> str:
    return ", ".join(f"<@{user_id}>" for user_id in winner_ids)


def _register_view(bot, giveaway_id: str, view=None) -> None:
    registered = getattr(bot, "_giveaway_views", None)
    if registered is None:
        registered = set()
        bot._giveaway_views = registered
    if giveaway_id in registered:
        return
    registered.add(giveaway_id)
    bot.add_view(view or GiveawayView(bot, giveaway_id))


def setup(bot) -> None:
    @bot.listen("on_ready")
    async def load_giveaways() -> None:
        if not state._loaded:
            await state.load_state(bot)
        for giveaway in state._giveaways.values():
            _register_view(bot, giveaway.id)

    @tasks.loop(seconds=LOOP_SECONDS)
    async def giveaway_loop() -> None:
        await bot.wait_until_ready()
        if not state._loaded:
            await state.load_state(bot)
        now = int(time.time())
        for giveaway in list(state._giveaways.values()):
            if giveaway.ends_at <= now:
                await state.finish(bot, giveaway)

    if not giveaway_loop.is_running():
        giveaway_loop.start()

    @bot.group(
        name="giveaway",
        aliases=["gw"],
        help="Button-based giveaways with automatic winners.",
        usage="giveaway",
        invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(ctx: commands.Context) -> None:
        await ctx.send(
            embed=info_embed(
                title="Giveaways",
                description=(
                    "Members click **Enter** to join (and again to leave). "
                    "Winners are picked when the timer runs out."
                ),
                fields=[
                    (
                        "Commands",
                        "`giveaway start <duration> <winners> <prize>`\n"
                        "`giveaway end <message id>`\n"
                        "`giveaway extend <message id> <duration>`\n"
                        "`giveaway reroll <message id> [winners]`\n"
                        "`giveaway entries <message id>` · `giveaway list`",
                        False)
                ])
        )

    @giveaway.command(
        name="start",
        help="Start a giveaway in this channel.",
        usage="giveaway start <duration> <winners> <prize>")
    @commands.has_permissions(manage_guild=True)
    async def start(
        ctx: commands.Context, duration: str, winners: int, *, prize: str
    ) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=error_embed(
                    "Duration must look like `30s`, `10m`, `2h` or `1d30m`."
                )
            )
            return
        if not 1 <= winners <= MAX_WINNERS:
            await ctx.send(
                embed=error_embed(f"Winners must be between 1 and {MAX_WINNERS}.")
            )
            return
        prize = prize.strip()
        if not prize or len(prize) > MAX_PRIZE:
            await ctx.send(
                embed=error_embed(
                    f"Give the prize a name under {MAX_PRIZE} characters."
                )
            )
            return

        giveaway_id = secrets.token_hex(4)
        ends_at = int(time.time()) + seconds
        view = GiveawayView(bot, giveaway_id)
        try:
            message = await ctx.send(
                embed=giveaway_embed(
                    prize=prize,
                    host=ctx.author,
                    winners=winners,
                    ends_at=ends_at),
                view=view)
        except discord.HTTPException as exc:
            log.warning("Could not post giveaway in %s: %s", ctx.channel.id, exc)
            await ctx.send(
                embed=error_embed("I couldn't post the giveaway here.")
            )
            return

        await state.create(
            bot,
            giveaway_id=giveaway_id,
            message_id=message.id,
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            prize=prize,
            winners=winners,
            host_id=ctx.author.id,
            ends_at=ends_at)
        _register_view(bot, giveaway_id, view)
        log.info(
            "Giveaway %s started in %s by %s",
            message.id,
            ctx.guild.id,
            ctx.author.id)

    @giveaway.command(
        name="end",
        help="End a giveaway early.",
        usage="giveaway end <message id>")
    @commands.has_permissions(manage_guild=True)
    async def end(ctx: commands.Context, message_id: int) -> None:
        giveaway = state.by_message(message_id)
        if giveaway is None or giveaway.guild_id != ctx.guild.id:
            await ctx.send(
                embed=error_embed("No active giveaway has that message ID.")
            )
            return
        winner_ids = await state.finish(bot, giveaway)
        if winner_ids is None:
            await ctx.send(
                embed=error_embed("That giveaway has already ended.")
            )
            return
        if winner_ids:
            await ctx.send(
                embed=success_embed(
                    f"Giveaway ended — winners: {_mentions(winner_ids)}.",
                    icon="🎉")
            )
        else:
            await ctx.send(
                embed=success_embed(
                    "Giveaway ended — nobody entered.", icon="🎉"
                )
            )

    @giveaway.command(
        name="reroll",
        help="Pick new winners for an ended giveaway.",
        usage="giveaway reroll <message id> [winners]")
    @commands.has_permissions(manage_guild=True)
    async def reroll(
        ctx: commands.Context, message_id: int, winners: int | None = None
    ) -> None:
        count = winners or 1
        if not 1 <= count <= MAX_WINNERS:
            await ctx.send(
                embed=error_embed(f"Winners must be between 1 and {MAX_WINNERS}.")
            )
            return
        result = await state.reroll(
            bot, message_id, count, guild_id=ctx.guild.id
        )
        if result is None:
            await ctx.send(
                embed=error_embed("I don't know a giveaway with that message ID.")
            )
            return
        winner_ids, _ = result
        if not winner_ids:
            await ctx.send(
                embed=error_embed("Nobody entered that giveaway — nothing to reroll.")
            )
            return
        await ctx.send(
            embed=success_embed(
                f"New winner(s): {_mentions(winner_ids)}.", icon="🎉"
            )
        )

    @giveaway.command(
        name="entries",
        help="See how many members entered a giveaway.",
        usage="giveaway entries <message id>")
    async def entries(ctx: commands.Context, message_id: int) -> None:
        row = await state.lookup(bot, message_id)
        if row is None or row["guild_id"] != ctx.guild.id:
            await ctx.send(
                embed=error_embed("I don't know a giveaway with that message ID.")
            )
            return
        joined = await state.entrants(bot, row["id"])
        url = (
            f"https://discord.com/channels/{row['guild_id']}/"
            f"{row['channel_id']}/{message_id}"
        )
        status = "ended" if row["ended"] else f"ends <t:{row['ends_at']}:R>"
        fields = [
            (
                "🎁 Prize",
                discord.utils.escape_markdown(row["prize"])[:256],
                True),
            ("👥 Entrants", f"{len(joined):,}", True),
            ("⏰ Status", status, True),
        ]
        if joined:
            shown = ", ".join(f"<@{user_id}>" for user_id in joined[:20])
            if len(joined) > 20:
                shown += f" and {len(joined) - 20:,} more"
            fields.append(("Joined", shown[:1024], False))
        await ctx.send(
            embed=info_embed(
                title="Giveaway entries",
                description=f"[Jump to the giveaway]({url})",
                fields=fields)
        )

    @giveaway.command(
        name="extend",
        help="Add more time to a running giveaway.",
        usage="giveaway extend <message id> <duration>")
    @commands.has_permissions(manage_guild=True)
    async def extend(
        ctx: commands.Context, message_id: int, duration: str
    ) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=error_embed(
                    "Duration must look like `30s`, `10m`, `2h` or `1d30m`."
                )
            )
            return
        giveaway = state.by_message(message_id)
        if giveaway is None or giveaway.guild_id != ctx.guild.id:
            await ctx.send(
                embed=error_embed("No active giveaway has that message ID.")
            )
            return
        ends_at = await state.extend(bot, giveaway, seconds)
        await ctx.send(
            embed=success_embed(
                f"Giveaway extended — it now ends <t:{ends_at}:R>.",
                icon="🎉")
        )

    @giveaway.command(
        name="list",
        help="List the active giveaways in this server.",
        usage="giveaway list")
    async def list_giveaways(ctx: commands.Context) -> None:
        active = state.active_for_guild(ctx.guild.id)
        if not active:
            await ctx.send(
                embed=error_embed("No active giveaways in this server.")
            )
            return
        fields = []
        for giveaway in active[:15]:
            url = (
                f"https://discord.com/channels/{giveaway.guild_id}/"
                f"{giveaway.channel_id}/{giveaway.message_id}"
            )
            fields.append(
                (
                    f"🎉 {discord.utils.escape_markdown(giveaway.prize)}"[:256],
                    f"[Message]({url}) · ends <t:{giveaway.ends_at}:R> · "
                    f"{giveaway.winners} winner(s)",
                    False)
            )
        await ctx.send(
            embed=info_embed(
                title="Active giveaways",
                description=f"{len(active)} giveaway(s) running.",
                fields=fields)
        )
