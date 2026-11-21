import discord

from core.emojis import iconize
from view.base import (
    ERROR_COLOR,
    INFO_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)


def nodelink_checking_embed(target: str | None = None) -> discord.Embed:
    text = f"Checking **{target}**…" if target else "Checking NodeLink servers…"
    embed = base_embed(description=f"{iconize('🔍')} {text}", color=INFO_COLOR)
    return brand(embed)


def nodelink_servers_embed(
    nodes: list,
    statuses: dict[str, float | None],
    *,
    current,
    main,
    prefix: str = "p!") -> discord.Embed:
    online = sum(1 for latency in statuses.values() if latency is not None)
    color = (
        SUCCESS_COLOR
        if online == len(nodes)
        else WARNING_COLOR if online else ERROR_COLOR
    )
    embed = base_embed(
        title=f"🛰️ {online}/{len(nodes)} online",
        color=color)
    for node in nodes:
        latency = statuses.get(node.name)
        dot = iconize("🟢" if latency is not None else "🔴")
        marker = "➜ " if node is current else ""
        value = f"`{node.resolved_url}`\n"
        value += f"`{latency:.0f} ms`" if latency is not None else "*offline*"
        if node is main:
            value += "  ·  main"
        embed.add_field(
            name=f"{marker}{dot} {node.name}", value=value, inline=False
        )

    return brand(
        embed,
        footer=(
            f"Switch with {prefix}nodelinkswitch <name|auto>  ·  "
            "➜ marks the active node"
        ))
