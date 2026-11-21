"""Games you can play against the bot or with each other.

Every game is a standalone command; the interactive ones open a button or
select view from `src/games/views.py`. Results are recorded per guild in the
`game_stats` table (see `src/games/stats.py`) so `gamestats` and `gamelb` can
show records, and solo wins pay coins.
"""

import asyncio
import math
import random

import discord
from discord.ext import commands

from src.games import data, stats
from src.games.views import (
    ConnectFourView,
    HangmanView,
    RPSView,
    TicTacToeView,
    TriviaView,
    WouldYouRatherView)
from view import error_embed, games_embed, success_embed


def setup(bot) -> None:
    @bot.command(
        name="8ball",
        aliases=["eightball"],
        help="Ask the magic 8-ball a yes/no question.",
        usage="8ball <question>")
    async def eightball(
        ctx: commands.Context, *, question: str | None = None
    ) -> None:
        if question is None or not question.strip():
            await ctx.send(
                embed=error_embed(f"Usage: `{ctx.prefix}8ball <question>`")
            )
            return
        await ctx.send(
            embed=games_embed(
                title="🎱 The 8-ball says…",
                description=(
                    f"**{question.strip()}**\n\n"
                    f"{random.choice(data.EIGHTBALL)}"
                ))
        )

    @bot.command(
        name="trivia",
        help="Answer a multiple-choice trivia question for coins.",
        usage="trivia [category]")
    @commands.guild_only()
    async def trivia(
        ctx: commands.Context, category: str | None = None
    ) -> None:
        name = (category or "").lower()
        if name and name not in data.TRIVIA:
            options = ", ".join(f"`{key}`" for key in data.TRIVIA)
            await ctx.send(
                embed=error_embed(f"Unknown category — try one of: {options}.")
            )
            return
        name = name or random.choice(list(data.TRIVIA))
        question, choices, answer = random.choice(data.TRIVIA[name])
        view = TriviaView(
            bot=bot,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            category=name,
            question=question,
            options=choices,
            answer=answer)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="hangman",
        help="Guess the hidden word before you run out of lives.",
        usage="hangman")
    @commands.guild_only()
    async def hangman(ctx: commands.Context) -> None:
        word, hint = random.choice(data.HANGMAN)
        view = HangmanView(
            bot=bot,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            word=word,
            hint=hint)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="tictactoe",
        aliases=["ttt"],
        help="Play tic-tac-toe against the bot or another member.",
        usage="tictactoe [member]")
    @commands.guild_only()
    async def tictactoe(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        opponent = _opponent(ctx, member)
        if opponent is None:
            o_id, o_name, vs_bot = bot.user.id, bot.user.display_name, True
        else:
            o_id, o_name, vs_bot = opponent.id, opponent.display_name, False
        view = TicTacToeView(
            bot=bot,
            guild_id=ctx.guild.id,
            x_id=ctx.author.id,
            x_name=ctx.author.display_name,
            o_id=o_id,
            o_name=o_name,
            vs_bot=vs_bot)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="connectfour",
        aliases=["c4"],
        help="Play Connect Four against the bot or another member.",
        usage="connectfour [member]")
    @commands.guild_only()
    async def connectfour(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        opponent = _opponent(ctx, member)
        if opponent is None:
            yellow_id, yellow_name, vs_bot = (
                bot.user.id,
                bot.user.display_name,
                True)
        else:
            yellow_id, yellow_name, vs_bot = (
                opponent.id,
                opponent.display_name,
                False)
        view = ConnectFourView(
            bot=bot,
            guild_id=ctx.guild.id,
            red_id=ctx.author.id,
            red_name=ctx.author.display_name,
            yellow_id=yellow_id,
            yellow_name=yellow_name,
            vs_bot=vs_bot)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="rps",
        aliases=["rockpaperscissors"],
        help="Play rock-paper-scissors against the bot or another member.",
        usage="rps [member]")
    @commands.guild_only()
    async def rps(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        opponent = _opponent(ctx, member)
        view = RPSView(
            bot=bot,
            guild_id=ctx.guild.id,
            author_id=ctx.author.id,
            author_name=ctx.author.display_name,
            opponent_id=opponent.id if opponent is not None else None,
            opponent_name=(
                opponent.display_name
                if opponent is not None
                else bot.user.display_name
            ))
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="numguess",
        aliases=["guessnumber"],
        help="Guess the number I'm thinking of between 1 and 100.",
        usage="numguess")
    @commands.guild_only()
    async def numguess(ctx: commands.Context) -> None:
        secret = random.randint(1, 100)
        tries = 7

        def check(message: discord.Message) -> bool:
            content = message.content.strip()
            return (
                message.author.id == ctx.author.id
                and message.channel.id == ctx.channel.id
                and content.lstrip("-").isdigit()
            )

        await ctx.send(
            embed=games_embed(
                title="🔢 Guess the number",
                description=(
                    "I picked a number between **1** and **100**. "
                    f"You have **{tries}** tries — just type your guess here."
                ))
        )

        for attempt in range(1, tries + 1):
            try:
                message = await bot.wait_for(
                    "message", timeout=45.0, check=check
                )
            except asyncio.TimeoutError:
                await stats.record(
                    bot.db, ctx.guild.id, ctx.author.id, "numguess", won=False
                )
                await ctx.send(
                    embed=error_embed(f"Time's up! The number was **{secret}**.")
                )
                return

            guess = int(message.content.strip())
            if guess == secret:
                paid = await stats.award(
                    bot.db,
                    ctx.guild.id,
                    ctx.author.id,
                    "numguess",
                    stats.NUMGUESS_REWARD,
                    won=True)
                await ctx.send(
                    embed=success_embed(
                        f"You got it in **{attempt}** "
                        f"{'try' if attempt == 1 else 'tries'}! **+{paid} coins**."
                    )
                )
                return

            remaining = tries - attempt
            if remaining == 0:
                break
            direction = "low" if guess < secret else "high"
            await ctx.send(
                embed=games_embed(
                    title="🔢 Guess the number",
                    description=(
                        f"**{guess}** is too {direction} — go "
                        f"{'higher ⬆️' if guess < secret else 'lower ⬇️'}. "
                        f"**{remaining}** "
                        f"{'try' if remaining == 1 else 'tries'} left."
                    ))
            )

        await stats.record(
            bot.db, ctx.guild.id, ctx.author.id, "numguess", won=False
        )
        await ctx.send(
            embed=error_embed(f"Out of tries! The number was **{secret}**.")
        )

    @bot.command(
        name="wyr",
        aliases=["wouldyourather"],
        help="Vote on a would-you-rather question.",
        usage="wyr")
    async def wyr(ctx: commands.Context) -> None:
        option_a, option_b = random.choice(data.WYR)
        view = WouldYouRatherView(option_a=option_a, option_b=option_b)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @bot.command(
        name="gamestats",
        aliases=["gstats"],
        help="Show a member's game win/loss record.",
        usage="gamestats [member]")
    @commands.guild_only()
    async def gamestats(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        name = getattr(target, "display_name", target.name)
        rows = await stats.all_for(bot.db, ctx.guild.id, target.id)
        if not rows:
            await ctx.send(
                embed=games_embed(
                    title=f"🎮 {name}'s game stats",
                    description=(
                        f"{target.mention} hasn't played a game yet. Try "
                        "`trivia`, `hangman`, `tictactoe` or `numguess`!"
                    ))
            )
            return

        fields = []
        for row in rows:
            streak = row["streak"]
            if streak > 0:
                current = f"W{streak}"
            elif streak < 0:
                current = f"L{abs(streak)}"
            else:
                current = "—"
            fields.append(
                (
                    row["game"].title(),
                    (
                        f"Wins **{row['wins']}** · Losses **{row['losses']}**\n"
                        f"Played **{row['played']}** · Best streak "
                        f"**{row['best']}**\n"
                        f"Current streak **{current}**"
                    ),
                    True)
            )
        await ctx.send(
            embed=games_embed(title=f"🎮 {name}'s game stats", fields=fields)
        )

    @bot.command(
        name="gamelb",
        aliases=["gametop"],
        help="Show the server's games leaderboard by wins.",
        usage="gamelb [page]")
    @commands.guild_only()
    async def gamelb(ctx: commands.Context, page: int = 1) -> None:
        page = max(page, 1)
        rows, total = await stats.leaderboard(bot.db, ctx.guild.id, page)
        if not total:
            await ctx.send(
                embed=games_embed(
                    title="🎮 Games leaderboard",
                    description="Nobody has played a game yet — be the first!")
            )
            return

        pages = max(1, math.ceil(total / stats.PAGE_SIZE))
        if page > pages:
            await ctx.send(
                embed=error_embed(
                    f"Only **{pages}** page{'s' if pages != 1 else ''} so far."
                )
            )
            return

        offset = (page - 1) * stats.PAGE_SIZE
        lines = [
            f"**{offset + position}.** <@{row['user_id']}> — "
            f"**{row['wins']}** wins · {row['played']} played"
            for position, row in enumerate(rows, start=1)
        ]
        await ctx.send(
            embed=games_embed(
                title="🎮 Games leaderboard",
                description="\n".join(lines),
                footer=(
                    f"Page {page}/{pages} · {total} "
                    f"player{'s' if total != 1 else ''}"
                ))
        )


def _opponent(ctx: commands.Context, member: discord.Member | None):
    """Treat bots and the invoker as "no opponent" so the game runs vs the bot."""
    if member is None or member.bot or member.id == ctx.author.id:
        return None
    return member
