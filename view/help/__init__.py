import re

import discord
from discord.ext import commands

from config.settings import settings
from view.base import INFO_COLOR


def help_embed(
    *,
    title: str,
    description: str,
    fields: list[tuple[str, str]] | None = None,
    page: int,
    pages: int,
    prefix: str,
    icon_url: str | None = None,
) -> discord.Embed:
    parts = [f"**{title}**"]
    if description:
        parts.append(description)

    for field in fields or []:
        name, value = field[0], field[1]
        parts.append(f"**{name}**\n{value}")

    parts.append(f"-# Page {page}/{pages} • `{prefix}help <command>` for details")

    embed = discord.Embed(
        description="\n\n".join(parts),
        color=settings.embed_color,
    )
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    return embed


_PLACEHOLDER = re.compile(r"[<\[]([^<>\[\]]+)[>\]]")
_MAX_FIELDS = 24


def _example_value(inner: str) -> str:
    # Choice placeholders like <on|off> show their first option.
    if "|" in inner:
        inner = inner.split("|", 1)[0].strip()
    numeric_range = re.fullmatch(r"(\d+)\s*-\s*\d+", inner)
    if numeric_range:
        return numeric_range.group(1)
    key = inner.lower()
    if key == "ndm":
        return "2d6"
    if "hex" in key:
        return "#9B59B6"
    if "image url" in key:
        return "https://example.com/image.png"
    if "user id" in key or "message" in key:
        return "123456789012345678"
    if "member" in key:
        return "@Member"
    if "user" in key:
        return "@User"
    if "role" in key:
        return "@Role"
    if "channel" in key or key.startswith("#"):
        return "#channel"
    if "emoji" in key:
        return "⭐"
    if "duration" in key:
        return "10m"
    if "amount" in key:
        return "100"
    if "reason" in key:
        return "spamming"
    if "question" in key:
        return "will it rain today?"
    if "song" in key:
        return "never gonna give you up"
    if "text" in key:
        return "hello world"
    if "prize" in key:
        return "Nitro Classic"
    if "winners" in key or "uses" in key:
        return "1"
    if "page" in key:
        return "1"
    if "level" in key:
        return "5"
    if "xp" in key:
        return "100"
    if "multiplier" in key:
        return "2"
    if "price" in key:
        return "500"
    if "count" in key:
        return "10"
    if "limit" in key:
        return "5"
    if "days" in key or "age" in key:
        return "7"
    if "player" in key:
        return "Notch"
    if "address" in key:
        return "mc.hypixel.net"
    if "username" in key:
        return "example_user"
    if "invite" in key:
        return "https://discord.gg/example"
    if "topic" in key:
        return "I need help"
    if "id" in key:
        return "123456789012345678"
    if "name" in key:
        return "example"
    if "category" in key:
        return "general"
    if "board" in key:
        return "aesthetic"
    if "path" in key:
        return "hug"
    if "prefix" in key:
        return "!"
    return inner


def _example_usage(command: commands.Command) -> str:
    custom = command.extras.get("example")
    if custom:
        return custom
    if isinstance(command, commands.Group) and command.commands:
        first = sorted(command.commands, key=lambda c: c.name)[0]
        return _example_usage(first)
    usage = getattr(command, "usage", None) or command.qualified_name
    return _PLACEHOLDER.sub(lambda m: _example_value(m.group(1)), usage)


def command_usage_embed(
    command: commands.Command,
    *,
    prefix: str,
    problem: str | None = None,
) -> discord.Embed:
    """Detailed usage page for a command or command group."""
    name = command.qualified_name
    is_group = isinstance(command, commands.Group)
    usage = f"{name} <subcommand> [arguments]" if is_group else (
        getattr(command, "usage", None) or name
    )

    parts = [f"**Command: `{name}`{' (group)' if is_group else ''}**"]
    if problem:
        parts.append(f"**Issue**\n{problem}")
    if command.help:
        parts.append(command.help)
    parts.append(f"**Usage**\n```{prefix}{usage}```")
    parts.append(f"**Example**\n```{prefix}{_example_usage(command)}```")

    if command.aliases:
        parent = command.full_parent_name
        aliases = ", ".join(
            f"`{prefix}{parent + ' ' if parent else ''}{alias}`"
            for alias in command.aliases
        )
        parts.append(f"**Aliases**\n{aliases}")

    if is_group:
        subs = sorted(command.commands, key=lambda c: c.name)
        lines = []
        for sub in subs:
            sub_usage = getattr(sub, "usage", None) or sub.qualified_name
            sub_help = sub.help or "No description."
            lines.append(f"`{prefix}{sub_usage}` — {sub_help}")
        if lines:
            parts.append("**Subcommands**\n" + "\n".join(lines))

    parts.append(f"-# `{prefix}help` to browse categories")

    return discord.Embed(
        description="\n\n".join(parts),
        color=INFO_COLOR,
    )
