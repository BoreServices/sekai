from discord.ext import commands

from config.settings import settings
from src.pinterest import client
from view import PinterestBoardView, PinterestProfileView, error_embed


def _footer(ctx: commands.Context) -> str:
    return (
        f"Requested by {ctx.author}  ·  {settings.bot_name}  ·  "
        f"Owned by {settings.owner_name}"
    )


def setup(bot) -> None:
    @bot.command(
        name="pinterest",
        aliases=["pins", "pint"],
        help="Look up a Pinterest account, its boards and pins.",
        usage="pinterest <username or profile link> [board]")
    async def pinterest_lookup(
        ctx: commands.Context,
        target: str | None = None,
        *,
        board: str | None = None) -> None:
        usage = f"`{ctx.prefix}pinterest <username or profile link> [board]`"
        if target is None:
            await ctx.send(embed=error_embed(f"Usage: {usage}"))
            return

        parsed = client.parse_target(target)
        if parsed is None:
            await ctx.send(
                embed=error_embed(
                    "That doesn't look like a Pinterest username or profile "
                    f"link.\nUsage: {usage}"
                )
            )
            return

        username, target_board = parsed
        board = board or target_board

        async with ctx.typing():
            try:
                profile = await client.fetch_profile(username)
                result = (
                    await client.fetch_board(username, board) if board else None
                )
            except client.PinterestError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

        if result is not None:
            view = PinterestBoardView(
                invoker_id=ctx.author.id,
                profile=profile,
                result=result,
                footer=_footer(ctx))
            message = await ctx.send(embed=view.render(), view=view)
        else:
            view = PinterestProfileView(
                invoker_id=ctx.author.id, profile=profile, footer=_footer(ctx)
            )
            message = await ctx.send(embed=view.embed(), view=view)
        view.message = message
