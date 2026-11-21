"""Global admin override for bot commands.

Users listed in ``config.owners.GLOBAL_ADMIN_IDS`` have control over every
server: they pass the permission checks on every prefix command, even without
the Discord permissions a command normally requires (for example
``manage_guild``). The override is installed once, after all cogs have loaded,
by wrapping each command's predicates, so individual commands keep their
``@commands.has_permissions`` decorators and behaviour for everyone else is
unchanged.

Only user-side failures are bypassed (``MissingPermissions``, ``MissingRole``,
``MissingAnyRole``). Bot-side failures such as ``BotMissingPermissions`` are
never bypassed: the bot itself still needs the permission to carry out the
action.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config.owners import GLOBAL_ADMIN_IDS

log = logging.getLogger("sekai.perms")

# User-side permission failures a global admin is allowed to bypass.
_BYPASS = (
    commands.MissingPermissions,
    commands.MissingRole,
    commands.MissingAnyRole,
)

_installed = False


def is_global_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in GLOBAL_ADMIN_IDS


def _wrap(check):
    async def wrapper(ctx: commands.Context) -> bool:
        author = getattr(ctx, "author", None)
        if is_global_admin(getattr(author, "id", None)):
            try:
                return await discord.utils.maybe_coroutine(check, ctx)
            except _BYPASS:
                return True
        return await discord.utils.maybe_coroutine(check, ctx)

    return wrapper


def install(bot: commands.Bot) -> None:
    """Wrap every command's checks so global admins pass permission predicates."""
    global _installed
    if _installed or not GLOBAL_ADMIN_IDS:
        return

    wrapped = 0
    for command in bot.walk_commands():
        if not command.checks:
            continue
        command.checks = [_wrap(check) for check in command.checks]
        wrapped += 1

    _installed = True
    log.info(
        "Global admin override enabled for %s across %d commands",
        ", ".join(str(uid) for uid in GLOBAL_ADMIN_IDS),
        wrapped,
    )