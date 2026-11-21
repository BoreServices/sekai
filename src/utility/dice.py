import random
import re

from discord.ext import commands

from view import info_embed

DICE_RE = re.compile(r"^(\d{0,2})d(\d{1,4})$", re.IGNORECASE)
MAX_DICE = 20
MAX_SIDES = 1000


def parse_dice(spec: str) -> tuple[int, int] | None:
    """Parse "2d6", "d20" or "6" into (count, sides), or None if invalid."""
    spec = spec.strip()
    if spec.isdigit():
        count, sides = 1, int(spec)
    else:
        match = DICE_RE.match(spec)
        if match is None:
            return None
        count = int(match.group(1) or 1)
        sides = int(match.group(2))
    if not (1 <= count <= MAX_DICE and 2 <= sides <= MAX_SIDES):
        return None
    return count, sides


def setup(bot) -> None:
    @bot.command(
        name="roll",
        help=f"Roll dice, e.g. d20, 2d6 or 6 ({MAX_DICE} dice max, up to {MAX_SIDES} sides).",
        usage="roll [NdM]")
    async def roll(ctx: commands.Context, spec: str = "1d6") -> None:
        parsed = parse_dice(spec)
        if parsed is None:
            await ctx.send(
                embed=info_embed(
                    title="Roll",
                    description=(
                        f"Use `NdM`, e.g. `d20` or `2d6`. Up to {MAX_DICE} dice "
                        f"with up to {MAX_SIDES} sides each."
                    ),
                    fields=[])
            )
            return
        count, sides = parsed
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        if count == 1:
            description = f"You rolled a **{total}** on a d{sides}."
        else:
            breakdown = " + ".join(str(value) for value in rolls)
            description = f"{breakdown} = **{total}** ({count}d{sides})"
        await ctx.send(
            embed=info_embed(title="🎲 Roll", description=description, fields=[])
        )

    @bot.command(
        name="coinflip",
        aliases=["flip"],
        help="Flip a coin.",
        usage="coinflip")
    async def coinflip(ctx: commands.Context) -> None:
        result = random.choice(["Heads", "Tails"])
        await ctx.send(
            embed=info_embed(
                title="🪙 Coin flip",
                description=f"It's **{result}**.",
                fields=[])
        )
