import asyncio
import io
import logging
import math

import aiohttp
import discord
from discord.ext import commands

from core import economy
from view import LeaderboardView, error_embed, success_embed
from view.economy import render_balance_card, render_baltop_card
from view.cards import run_render

log = logging.getLogger("sekai.economy")

MAX_PAY = 1_000_000_000
MAX_ADJUST = 1_000_000


def _duration_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


async def _avatar(user: discord.abc.User | None) -> bytes | None:
    if user is None:
        return None
    try:
        return await user.display_avatar.replace(size=256, format="png").read()
    except (discord.HTTPException, aiohttp.ClientError):
        return None


async def _resolve_user(
    bot, guild: discord.Guild, user_id: int
) -> discord.abc.User | None:
    """Member cache first, then the API, so names show without the members intent."""
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound:
        pass
    except discord.HTTPException:
        pass
    try:
        return await bot.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def _baltop_page(bot, guild: discord.Guild, page: int) -> tuple[bytes, int]:
    rows, total = await economy.leaderboard(bot.db, guild.id, page)
    pages = max(1, math.ceil(total / economy.PAGE_SIZE))

    offset = (page - 1) * economy.PAGE_SIZE
    users = await asyncio.gather(
        *(_resolve_user(bot, guild, row["user_id"]) for row in rows)
    )
    avatars = await asyncio.gather(*(_avatar(user) for user in users))

    entries = []
    for position, row, user, avatar in zip(
        range(offset + 1, offset + 1 + len(rows)), rows, users, avatars
    ):
        name = (
            getattr(user, "display_name", None) or f"User {row['user_id']}"
        )
        entries.append((position, name, row["balance"], avatar))

    png = await run_render(
        render_baltop_card,
        guild_name=guild.name,
        entries=entries,
        page=page,
        pages=pages,
        total=total,
        currency=economy.CURRENCY)
    return png, pages


def setup(bot) -> None:
    @bot.command(
        name="balance",
        aliases=["bal", "wallet"],
        help="Show your coin balance, or someone else's.",
        usage="balance [member]")
    @commands.guild_only()
    async def balance(ctx: commands.Context, user: discord.User | None = None) -> None:
        target = user or ctx.author
        display_name = getattr(target, "display_name", target.name)
        coins = await economy.get_balance(bot.db, ctx.guild.id, target.id)
        higher = await bot.db.fetchone(
            "SELECT COUNT(*) AS higher FROM economy "
            "WHERE guild_id = ? AND balance > ?",
            (ctx.guild.id, coins))
        position = (higher["higher"] if higher is not None else 0) + 1

        now_row = await bot.db.fetchone(
            "SELECT last_daily, last_work FROM economy "
            "WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, target.id))
        now = int(discord.utils.utcnow().timestamp())
        last_daily = now_row["last_daily"] if now_row is not None else 0
        last_work = now_row["last_work"] if now_row is not None else 0

        avatar_bytes = await _avatar(target)
        png = await run_render(
            render_balance_card,
            display_name=display_name,
            avatar_bytes=avatar_bytes,
            balance=coins,
            rank=position,
            daily_ready=now - last_daily >= economy.DAILY_COOLDOWN,
            work_ready=now - last_work >= economy.WORK_COOLDOWN,
            guild_name=ctx.guild.name,
            currency=economy.CURRENCY)
        await ctx.send(
            file=discord.File(io.BytesIO(png), filename=f"balance-{target.id}.png")
        )

    @bot.command(
        name="daily",
        help=f"Claim {economy.DAILY_AMOUNT} coins once every 24 hours.",
        usage="daily")
    @commands.guild_only()
    async def daily(ctx: commands.Context) -> None:
        gained, wait = await economy.claim_daily(bot.db, ctx.guild.id, ctx.author.id)
        if wait:
            await ctx.send(
                embed=error_embed(
                    f"Your daily reward is ready in **{_duration_text(wait)}**."
                )
            )
            return
        balance_now = await economy.get_balance(bot.db, ctx.guild.id, ctx.author.id)
        await ctx.send(
            embed=success_embed(
                f"You claimed **{gained} {economy.CURRENCY}**. "
                f"Balance: **{balance_now:,}**."
            )
        )

    @bot.command(
        name="work",
        help="Work for coins, once an hour.",
        usage="work")
    @commands.guild_only()
    async def work(ctx: commands.Context) -> None:
        earned, wait = await economy.work(bot.db, ctx.guild.id, ctx.author.id)
        if wait:
            await ctx.send(
                embed=error_embed(
                    f"You can work again in **{_duration_text(wait)}**."
                )
            )
            return
        balance_now = await economy.get_balance(bot.db, ctx.guild.id, ctx.author.id)
        await ctx.send(
            embed=success_embed(
                f"You earned **{earned} {economy.CURRENCY}**. "
                f"Balance: **{balance_now:,}**."
            )
        )

    @bot.command(
        name="pay",
        aliases=["give", "transfer"],
        help="Send coins to another member.",
        usage="pay <member> <amount>")
    @commands.guild_only()
    async def pay(
        ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if member.bot:
            await ctx.send(embed=error_embed("Bots don't need coins."))
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You can't pay yourself."))
            return
        if not 1 <= amount <= MAX_PAY:
            await ctx.send(
                embed=error_embed(f"Amount must be between 1 and {MAX_PAY:,}.")
            )
            return

        moved = await economy.pay(
            bot.db, ctx.guild.id, ctx.author.id, member.id, amount
        )
        if not moved:
            await ctx.send(embed=error_embed("You don't have enough coins."))
            return
        await ctx.send(
            embed=success_embed(
                f"You sent **{amount:,} {economy.CURRENCY}** to {member.mention}."
            )
        )

    @bot.command(
        name="gamble",
        aliases=["bet"],
        help="Bet coins on a coin flip: win to double your bet, lose it all otherwise.",
        usage="gamble <amount>")
    @commands.guild_only()
    async def gamble(ctx: commands.Context, amount: int) -> None:
        if not 1 <= amount <= MAX_PAY:
            await ctx.send(
                embed=error_embed(f"Bet must be between 1 and {MAX_PAY:,}.")
            )
            return
        won, new_balance = await economy.gamble(
            bot.db, ctx.guild.id, ctx.author.id, amount
        )
        if won is None:
            await ctx.send(embed=error_embed("You don't have enough coins for that bet."))
            return
        if won:
            await ctx.send(
                embed=success_embed(
                    f"You won **{amount:,} {economy.CURRENCY}**! "
                    f"Balance: **{new_balance:,}**."
                )
            )
        else:
            await ctx.send(
                embed=error_embed(
                    f"You lost **{amount:,} {economy.CURRENCY}**. "
                    f"Balance: **{new_balance:,}**."
                )
            )

    @bot.command(
        name="baltop",
        aliases=["richest", "economylb"],
        help="Show this server's richest members as a card.",
        usage="baltop [page]")
    @commands.guild_only()
    async def baltop(ctx: commands.Context, page: int = 1) -> None:
        page = max(page, 1)
        rows, total = await economy.leaderboard(bot.db, ctx.guild.id, page)
        pages = max(1, math.ceil(total / economy.PAGE_SIZE))
        if total and page > pages:
            await ctx.send(
                embed=error_embed(
                    f"Only **{pages}** page{'s' if pages != 1 else ''} so far."
                )
            )
            return

        async def render(target: int) -> tuple[bytes, int]:
            return await _baltop_page(ctx.bot, ctx.guild, target)

        png, pages = await _baltop_page(ctx.bot, ctx.guild, page)
        view = LeaderboardView(
            author_id=ctx.author.id,
            page=page,
            pages=pages,
            render=render)
        await ctx.send(
            file=discord.File(io.BytesIO(png), filename=f"baltop-{page}.png"),
            view=view)

    @bot.command(
        name="slots",
        help="Spin three reels. Three matches pays 5x, a pair pays 1x, otherwise you lose the bet.",
        usage="slots <amount>")
    @commands.guild_only()
    async def slots(ctx: commands.Context, amount: int) -> None:
        if not 1 <= amount <= MAX_PAY:
            await ctx.send(
                embed=error_embed(f"Bet must be between 1 and {MAX_PAY:,}.")
            )
            return
        reels, net, new_balance = await economy.slots(
            bot.db, ctx.guild.id, ctx.author.id, amount
        )
        if net is None:
            await ctx.send(embed=error_embed("You don't have enough coins for that bet."))
            return
        spin = " ".join(reels)
        if net > 0:
            text = f"{spin}\n\nYou won **{net:,} {economy.CURRENCY}**! Balance: **{new_balance:,}**."
            await ctx.send(embed=success_embed(text))
        else:
            text = f"{spin}\n\nYou lost **{amount:,} {economy.CURRENCY}**. Balance: **{new_balance:,}**."
            await ctx.send(embed=error_embed(text))

    @bot.command(
        name="addcoins",
        aliases=["givecoins"],
        help="Add or remove coins from a member (manage server).",
        usage="addcoins <member> <amount>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addcoins(
        ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if not -MAX_ADJUST <= amount <= MAX_ADJUST or amount == 0:
            await ctx.send(
                embed=error_embed(
                    f"Amount must be between -{MAX_ADJUST:,} and {MAX_ADJUST:,}, "
                    "and not 0."
                )
            )
            return
        new_balance = await economy.add_balance(
            bot.db, ctx.guild.id, member.id, amount
        )
        log.info(
            "Adjusted coins for %s in %s by %s: %+d",
            member.id, ctx.guild.id, ctx.author.id, amount)
        await ctx.send(
            embed=success_embed(
                f"{member.mention} now has **{new_balance:,} {economy.CURRENCY}**."
            )
        )
