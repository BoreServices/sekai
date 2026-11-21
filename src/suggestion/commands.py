import logging

import discord
from discord.ext import commands

from view import error_embed, info_embed, success_embed

log = logging.getLogger("sekai.suggestion")


def setup(bot) -> None:
    @bot.command(
        name="suggest",
        help="Submit a suggestion for the server.",
        usage="suggest <text>")
    @commands.guild_only()
    async def suggest(ctx: commands.Context, *, text: str) -> None:
        snippet = text[:200] + ("..." if len(text) > 200 else "")
        await ctx.send(
            embed=success_embed(f"Your suggestion was recorded:\n> {snippet}")
        )

    @bot.command(
        name="suggestions",
        help="Show pending suggestions (staff only).",
        usage="suggestions")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggestions(ctx: commands.Context) -> None:
        await ctx.send(
            embed=info_embed(
                title="Suggestions",
                fields=[
                    (
                        "Nothing stored yet",
                        "Suggestions collected with `suggest` appear here "
                        "once storage is enabled.",
                        False)
                ])
        )

    @bot.command(
        name="approve",
        help="Approve a suggestion.",
        usage="approve <id>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def approve(ctx: commands.Context, suggestion_id: int) -> None:
        if suggestion_id <= 0:
            await ctx.send(embed=error_embed("Suggestion IDs start at 1."))
            return
        await ctx.send(
            embed=success_embed(f"Suggestion **#{suggestion_id}** approved.")
        )

    @bot.command(
        name="deny",
        help="Deny a suggestion.",
        usage="deny <id>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def deny(ctx: commands.Context, suggestion_id: int) -> None:
        if suggestion_id <= 0:
            await ctx.send(embed=error_embed("Suggestion IDs start at 1."))
            return
        await ctx.send(
            embed=success_embed(f"Suggestion **#{suggestion_id}** denied.")
        )
