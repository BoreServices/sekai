import discord
from discord.ext import commands

from config.settings import settings
from src.roblox import client
from view import error_embed
from view.roblox import RobloxUserView


def _footer(ctx: commands.Context) -> str:
    return (
        f"Requested by {ctx.author}  ·  {settings.bot_name}  ·  "
        f"Owned by {settings.owner_name}"
    )


def setup(bot) -> None:
    @bot.command(
        name="roblox",
        aliases=["rbx", "rblx"],
        help="Look up a Roblox player, their avatar and profile stats.",
        usage="roblox <username>")
    async def roblox_user(
        ctx: commands.Context, *, username: str | None = None
    ) -> None:
        usage = f"`{ctx.prefix}roblox <username>`"
        if username is None:
            await ctx.send(embed=error_embed(f"Usage: {usage}"))
            return

        async with ctx.typing():
            try:
                user = await client.fetch_user(username)
            except client.RobloxError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

        view = RobloxUserView(
            invoker_id=ctx.author.id,
            user=user,
            footer=_footer(ctx))
        message = await ctx.send(embed=view.render("profile"), view=view)
        view.message = message
