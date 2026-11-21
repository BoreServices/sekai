from discord.ext import commands

from core import prefix as prefixes
from view import error_embed, success_embed

MAX_PREFIX_LENGTH = 5


def setup(bot) -> None:
    @bot.command(
        name="prefix",
        help="Show or change this server's command prefix.",
        usage="prefix [new prefix|reset]")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def prefix(ctx: commands.Context, value: str | None = None) -> None:
        current = await prefixes.get_guild_prefix(bot, ctx.guild.id)
        default = prefixes.default_prefix(bot)

        if value is None:
            if bot.dev:
                text = f"Current prefix: `{current}` — fixed while running with `--dev`."
            else:
                text = (
                    f"Current prefix: `{current}`\n"
                    f"Use `{current}prefix <new>` to change it, "
                    f"or `{current}prefix reset` to go back to `{default}`."
                )
            await ctx.send(embed=success_embed(text, icon="🔧"))
            return

        if bot.dev:
            await ctx.send(
                embed=error_embed(
                    f"The dev bot always uses `{default}` — prefix changes are "
                    "disabled with `--dev`."
                )
            )
            return

        if value.lower() == "reset":
            await prefixes.reset_guild_prefix(bot, ctx.guild.id)
            await ctx.send(
                embed=success_embed(
                    f"Custom prefix removed. Using `{default}`.", icon="🔧"
                )
            )
            return

        if len(value) > MAX_PREFIX_LENGTH or any(char.isspace() for char in value):
            await ctx.send(
                embed=error_embed(
                    f"Prefix must be 1-{MAX_PREFIX_LENGTH} characters with no spaces."
                )
            )
            return

        await prefixes.set_guild_prefix(bot, ctx.guild.id, value)
        await ctx.send(
            embed=success_embed(f"Prefix set to `{value}`.", icon="🔧")
        )
