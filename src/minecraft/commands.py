import asyncio
import io

import discord
from discord.ext import commands

from config.settings import settings
from src.minecraft import client
from view import error_embed
from view.cards import run_render
from view.minecraft import MinecraftProfileView, mc_server_embed, render_pages
from view.minecraft.skin import SkinError


def _footer(ctx: commands.Context) -> str:
    return (
        f"Requested by {ctx.author}  ·  {settings.bot_name}  ·  "
        f"Owned by {settings.owner_name}"
    )


def setup(bot) -> None:
    @bot.command(
        name="mcuser",
        aliases=["mcplayer", "mcu"],
        help="Look up a Minecraft player, their skin and their cape.",
        usage="mcuser <player>")
    async def mc_user(
        ctx: commands.Context, *, player: str | None = None
    ) -> None:
        usage = f"`{ctx.prefix}mcuser <player>`"
        if player is None:
            await ctx.send(embed=error_embed(f"Usage: {usage}"))
            return

        async with ctx.typing():
            try:
                profile = await client.fetch_profile(player)
            except client.MinecraftError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

            images: dict[str, bytes] = {}
            if profile.skin is not None:
                try:
                    images = await run_render(
                        render_pages,
                        profile.skin,
                        profile.cape,
                        model=profile.model)
                except SkinError:
                    images = {}

        view = MinecraftProfileView(
            invoker_id=ctx.author.id,
            profile=profile,
            images=images,
            footer=_footer(ctx))
        embed, file = view.render("info")
        message = await ctx.send(embed=embed, file=file, view=view)
        view.message = message

    @bot.command(
        name="mcserver",
        aliases=["mcs", "mcsrv"],
        help="Show a Minecraft server's status, version and players.",
        usage="mcserver <address>")
    async def mc_server(
        ctx: commands.Context, *, address: str | None = None
    ) -> None:
        usage = f"`{ctx.prefix}mcserver <address>`"
        if address is None:
            await ctx.send(embed=error_embed(f"Usage: {usage}"))
            return

        async with ctx.typing():
            try:
                server = await client.fetch_server(address)
            except client.MinecraftError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

        embed = mc_server_embed(server, footer=_footer(ctx))
        file = (
            discord.File(io.BytesIO(server.icon), filename="icon.png")
            if server.icon
            else None
        )
        await ctx.send(embed=embed, file=file)
