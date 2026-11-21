"""
src/music/nodelink.py — p!musicstatus: NodeLink server + player status.
"""

from __future__ import annotations

import asyncio
import time

import discord
import wavelink
from discord.ext import commands

from config.nodelink import NODELINKS
from core import music as engine
from core.emojis import iconize
from view.base import (
    ERROR_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)


async def _node_latency(node: wavelink.Node) -> float | None:
    start = time.monotonic()
    try:
        await asyncio.wait_for(node.fetch_info(), timeout=5)
    except Exception:
        return None
    return (time.monotonic() - start) * 1000


async def _status_embed(bot) -> discord.Embed:
    pool = wavelink.Pool.nodes
    servers = list(NODELINKS)
    latencies: dict[str, float | None] = {}
    connected: set[str] = set()

    async def probe(server) -> None:
        node = pool.get(server.name)
        if node is None or node.status is not wavelink.NodeStatus.CONNECTED:
            latencies[server.name] = None
            return
        connected.add(server.name)
        latencies[server.name] = await _node_latency(node)

    await asyncio.gather(*(probe(server) for server in servers))

    online = len(connected)
    color = (
        SUCCESS_COLOR
        if online == len(servers)
        else WARNING_COLOR if online else ERROR_COLOR
    )
    embed = base_embed(
        title=f"🛰️ {online}/{len(servers)} NodeLink servers online",
        color=color)
    for server in servers:
        latency = latencies[server.name]
        node = pool.get(server.name)
        is_online = server.name in connected
        dot = iconize("🟢" if is_online else "🔴")
        value = f"`{server.resolved_url}`\n"
        if is_online:
            players = len(node.players) if node else 0
            if latency is not None:
                value += f"`{latency:.0f} ms` · {players} player(s)"
            else:
                value += f"{players} player(s)"
        elif node is not None and node.status is wavelink.NodeStatus.CONNECTING:
            value += "*connecting…*"
        else:
            value += "*offline*"
        embed.add_field(name=f"{dot} {server.name}", value=value, inline=False)

    players = engine.all_players()
    lines = []
    for gid, player in players.items():
        guild = bot.get_guild(gid)
        name = guild.name if guild else f"Guild {gid}"
        current = player.current.title if player.current else "idle"
        lines.append(
            f"**{discord.utils.escape_markdown(name)}** — "
            f"{discord.utils.escape_markdown(current)} "
            f"({len(player.queue)} queued · `{player.node.identifier}`)"
        )
    embed.add_field(
        name="🎵 Active players",
        value="\n".join(lines) if lines else "*No active players.*",
        inline=False)
    return brand(embed, footer="Wavelink · public NodeLink servers · auto failover")


def setup(bot) -> None:
    @bot.command(
        name="musicstatus",
        aliases=["mstatus"],
        help="Show NodeLink server status and active music players.",
        usage="musicstatus")
    @commands.guild_only()
    async def musicstatus(ctx: commands.Context) -> None:
        async with ctx.typing():
            embed = await _status_embed(bot)
        await ctx.send(embed=embed)