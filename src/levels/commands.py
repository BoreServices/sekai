import asyncio
import io
import logging
import math
from contextlib import suppress

import aiohttp
import discord
from discord.ext import commands

from core import levels
from view import (
    LeaderboardView,
    error_embed,
    info_embed,
    level_rewards_embed,
    success_embed)
from view.leaderboard import render_leaderboard
from view.levelup import render_level_up_card
from view.rankcard import render_rank_card
from view.cards import run_render

log = logging.getLogger("sekai.levels")

MAX_ADJUST = 1_000_000
MAX_SET_XP = 100_000_000
MAX_LEVEL = 1000
MAX_ADD_LEVELS = 100


async def _avatar(user: discord.abc.User | None) -> bytes | None:
    if user is None:
        return None
    try:
        return await user.display_avatar.replace(size=256, format="png").read()
    except (discord.HTTPException, aiohttp.ClientError):
        return None


async def _resolve_user(
    bot, guild: discord.Guild, user_id: int
) -> discord.abc.User | None:
    """Member cache first, then the API, so names show without the members intent."""
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound:
        pass
    except discord.HTTPException:
        pass
    try:
        return await bot.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def _grant_rewards(bot, member: discord.Member, level: int) -> None:
    """Hand out every reward role the member is owed but doesn't hold yet."""
    role_ids = await levels.rewards_up_to(bot.db, member.guild.id, level)
    if not role_ids:
        return
    me = member.guild.me
    if me is None:
        return

    roles = [
        role
        for role_id in role_ids
        if (role := member.guild.get_role(role_id)) is not None
        and not role.managed
        and role < me.top_role
        and role not in member.roles
    ]
    if not roles:
        return

    try:
        await member.add_roles(*roles, reason=f"Level {level} reward")
    except discord.HTTPException:
        log.exception(
            "Could not grant level rewards in guild %s", member.guild.id
        )


async def _leaderboard_page(
    bot, guild: discord.Guild, page: int
) -> tuple[bytes, int]:
    rows, total = await levels.leaderboard(bot.db, guild.id, page)
    pages = max(1, math.ceil(total / levels.PAGE_SIZE))

    offset = (page - 1) * levels.PAGE_SIZE
    users = await asyncio.gather(
        *(_resolve_user(bot, guild, row["user_id"]) for row in rows)
    )
    avatars = await asyncio.gather(*(_avatar(user) for user in users))

    entries = []
    for position, row, user, avatar in zip(
        range(offset + 1, offset + 1 + len(rows)), rows, users, avatars
    ):
        name = (
            user.display_name if user is not None else f"User {row['user_id']}"
        )
        level, _, _ = levels.level_progress(row["xp"])
        entries.append(
            (position, name, level, row["xp"], row["messages"], avatar)
        )

    png = await run_render(
        render_leaderboard,
        guild_name=guild.name,
        entries=entries,
        page=page,
        pages=pages,
        total=total)
    return png, pages


def setup(bot) -> None:
    @bot.listen("on_message")
    async def award_message_xp(message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        prefixes = await bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if any(message.content.startswith(prefix) for prefix in prefixes):
            return

        new_level = await levels.add_message_xp(
            bot.db, message.guild.id, message.author.id
        )
        if new_level is None:
            return

        await _grant_rewards(bot, message.author, new_level)

        avatar_bytes = await _avatar(message.author)
        png = await run_render(
            render_level_up_card,
            display_name=message.author.display_name,
            avatar_bytes=avatar_bytes,
            level=new_level,
            guild_name=message.guild.name)
        with suppress(discord.HTTPException):
            await message.channel.send(
                file=discord.File(
                    io.BytesIO(png), filename=f"levelup-{message.author.id}.png"
                )
            )

    @bot.command(
        name="rank",
        aliases=["level", "lvl"],
        help="Show a member's level card.",
        usage="rank [member]")
    @commands.guild_only()
    async def rank(
        ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        target = user or ctx.author
        display_name = getattr(target, "display_name", target.name)
        xp, messages = await levels.get_stats(bot.db, ctx.guild.id, target.id)
        level, into, needed = levels.level_progress(xp)
        position = await levels.get_rank(bot.db, ctx.guild.id, xp)

        avatar_bytes = await _avatar(target)
        png = await run_render(
            render_rank_card,
            display_name=display_name,
            avatar_bytes=avatar_bytes,
            level=level,
            rank=position,
            xp=xp,
            xp_into_level=into,
            xp_needed=needed,
            messages=messages,
            guild_name=ctx.guild.name)
        await ctx.send(
            file=discord.File(io.BytesIO(png), filename=f"rank-{target.id}.png")
        )

    @bot.command(
        name="leaderboard",
        aliases=["lb", "top"],
        help="Show this server's XP leaderboard.",
        usage="leaderboard [page]")
    @commands.guild_only()
    async def leaderboard(ctx: commands.Context, page: int = 1) -> None:
        page = max(page, 1)
        rows, total = await levels.leaderboard(bot.db, ctx.guild.id, page)
        pages = max(1, math.ceil(total / levels.PAGE_SIZE))

        if total and page > pages:
            await ctx.send(
                embed=error_embed(
                    f"Only **{pages}** page{'s' if pages != 1 else ''} so far."
                )
            )
            return

        async def render(target: int) -> tuple[bytes, int]:
            return await _leaderboard_page(ctx.bot, ctx.guild, target)

        png, pages = await _leaderboard_page(ctx.bot, ctx.guild, page)
        view = LeaderboardView(
            author_id=ctx.author.id,
            page=page,
            pages=pages,
            render=render)
        await ctx.send(
            file=discord.File(io.BytesIO(png), filename=f"leaderboard-{page}.png"),
            view=view)

    @bot.command(
        name="addxp",
        help="Give a member bonus XP.",
        usage="addxp <member> <amount>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addxp(
        ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if not 1 <= amount <= MAX_ADJUST:
            await ctx.send(
                embed=error_embed(f"Amount must be between 1 and {MAX_ADJUST:,}.")
            )
            return
        before, after = await levels.add_xp(
            bot.db, ctx.guild.id, member.id, amount
        )
        total, _ = await levels.get_stats(bot.db, ctx.guild.id, member.id)
        if after > before:
            await _grant_rewards(bot, member, after)
            text = (
                f"Gave **{amount:,} XP** to {member.mention} — they hit "
                f"**level {after}** ({total:,} XP)."
            )
        else:
            text = (
                f"Gave **{amount:,} XP** to {member.mention} — now level "
                f"**{after}** ({total:,} XP)."
            )
        await ctx.send(embed=success_embed(text, icon="🏆"))

    @bot.command(
        name="removexp",
        help="Take XP away from a member.",
        usage="removexp <member> <amount>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def removexp(
        ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if not 1 <= amount <= MAX_ADJUST:
            await ctx.send(
                embed=error_embed(f"Amount must be between 1 and {MAX_ADJUST:,}.")
            )
            return
        new_total = await levels.remove_xp(
            bot.db, ctx.guild.id, member.id, amount
        )
        if new_total is None:
            await ctx.send(
                embed=error_embed(f"{member.mention} doesn't have any XP yet.")
            )
            return
        level, _, _ = levels.level_progress(new_total)
        await ctx.send(
            embed=success_embed(
                f"Removed **{amount:,} XP** from {member.mention} — they're now "
                f"level **{level}** ({new_total:,} XP).",
                icon="🏆")
        )

    @bot.command(
        name="setxp",
        help="Set a member's total XP.",
        usage="setxp <member> <xp>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setxp(
        ctx: commands.Context, member: discord.Member, xp: int
    ) -> None:
        if not 0 <= xp <= MAX_SET_XP:
            await ctx.send(
                embed=error_embed(f"XP must be between 0 and {MAX_SET_XP:,}.")
            )
            return
        await levels.set_xp(bot.db, ctx.guild.id, member.id, xp)
        level, _, _ = levels.level_progress(xp)
        await _grant_rewards(bot, member, level)
        await ctx.send(
            embed=success_embed(
                f"Set {member.mention} to **{xp:,} XP** — level **{level}**.",
                icon="🏆")
        )

    @bot.command(
        name="setlevel",
        help="Set a member's level.",
        usage="setlevel <member> <level>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setlevel(
        ctx: commands.Context, member: discord.Member, level: int
    ) -> None:
        if not 0 <= level <= MAX_LEVEL:
            await ctx.send(
                embed=error_embed(f"Level must be between 0 and {MAX_LEVEL}.")
            )
            return
        xp = await levels.set_level(bot.db, ctx.guild.id, member.id, level)
        await _grant_rewards(bot, member, level)
        await ctx.send(
            embed=success_embed(
                f"Set {member.mention} to level **{level}** ({xp:,} XP).",
                icon="🏆")
        )

    @bot.command(
        name="addlevel",
        help="Give a member whole levels.",
        usage="addlevel <member> <levels>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addlevel(
        ctx: commands.Context, member: discord.Member, count: int
    ) -> None:
        if not 1 <= count <= MAX_ADD_LEVELS:
            await ctx.send(
                embed=error_embed(
                    f"Levels to add must be between 1 and {MAX_ADD_LEVELS}."
                )
            )
            return
        before, after = await levels.add_levels(
            bot.db, ctx.guild.id, member.id, count
        )
        total, _ = await levels.get_stats(bot.db, ctx.guild.id, member.id)
        await _grant_rewards(bot, member, after)
        plural = "s" if count != 1 else ""
        await ctx.send(
            embed=success_embed(
                f"Gave {member.mention} **{count} level{plural}** — now level "
                f"**{after}** ({total:,} XP).",
                icon="🏆")
        )

    @bot.command(
        name="resetxp",
        help="Wipe a member's XP and message count.",
        usage="resetxp <member>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def resetxp(ctx: commands.Context, member: discord.Member) -> None:
        await levels.reset_xp(bot.db, ctx.guild.id, member.id)
        await ctx.send(
            embed=success_embed(
                f"Reset XP for {member.mention}. They start fresh at level 0.",
                icon="🏆")
        )

    @bot.command(
        name="setxpboost",
        help="Set the server's XP boost multiplier.",
        usage="setxpboost <multiplier>")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setxpboost(ctx: commands.Context, multiplier: float) -> None:
        if not 1.0 <= multiplier <= levels.MAX_XP_BOOST:
            await ctx.send(
                embed=error_embed(
                    f"Multiplier must be between 1.0 and {levels.MAX_XP_BOOST}."
                )
            )
            return
        levels.set_xp_boost(ctx.guild.id, multiplier)
        percent = round((multiplier - 1.0) * 100)
        await ctx.send(
            embed=success_embed(
                f"Server XP boost is now **{multiplier:g}x** "
                f"({percent}% more XP).",
                icon="🏆")
        )

    @bot.command(
        name="xpboost",
        aliases=["boost"],
        help="Show the server's XP boost multiplier.",
        usage="xpboost")
    @commands.guild_only()
    async def xpboost(ctx: commands.Context) -> None:
        boost = levels.get_xp_boost(ctx.guild.id)
        if boost == levels.DEFAULT_XP_BOOST:
            text = "**1x** — no boost set."
        else:
            percent = round((boost - 1.0) * 100)
            text = f"**{boost:g}x** ({percent}% more XP)."
        await ctx.send(
            embed=info_embed(
                title="XP boost", fields=[], description=text
            )
        )

    @bot.group(
        name="levelrewards",
        aliases=["lvrewards"],
        help="Pick roles members unlock automatically at certain levels.",
        usage="levelrewards add <level> <role>|remove <level>|list",
        invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def levelrewards(ctx: commands.Context) -> None:
        await ctx.send(
            embed=error_embed(
                f"Use `{ctx.prefix}levelrewards add <level> <role>`, "
                f"`{ctx.prefix}levelrewards remove <level>` or "
                f"`{ctx.prefix}levelrewards list`."
            )
        )

    @levelrewards.command(
        name="add",
        help="Give a role automatically when a member reaches a level.",
        usage="levelrewards add <level> <role>")
    @commands.has_permissions(manage_guild=True)
    async def levelrewards_add(
        ctx: commands.Context, level: int, role: discord.Role
    ) -> None:
        if not 1 <= level <= MAX_LEVEL:
            await ctx.send(
                embed=error_embed(f"Level must be between 1 and {MAX_LEVEL}.")
            )
            return
        me = ctx.guild.me
        if (
            role.is_default()
            or role.managed
            or (me is not None and role >= me.top_role)
        ):
            await ctx.send(
                embed=error_embed(
                    "I can't hand that role out — pick one that isn't "
                    "@everyone, bot-managed, or above my highest role."
                )
            )
            return
        await levels.set_reward(bot.db, ctx.guild.id, level, role.id)
        await ctx.send(
            embed=success_embed(
                f"Members who reach **level {level}** now get {role.mention}. "
                "Eligible members get it on their next level-up.",
                icon="🏆")
        )

    @levelrewards.command(
        name="remove",
        help="Stop giving a role for a level.",
        usage="levelrewards remove <level>")
    @commands.has_permissions(manage_guild=True)
    async def levelrewards_remove(
        ctx: commands.Context, level: int
    ) -> None:
        if not await levels.remove_reward(bot.db, ctx.guild.id, level):
            await ctx.send(
                embed=error_embed(f"There's no reward at level {level}.")
            )
            return
        await ctx.send(
            embed=success_embed(
                f"Removed the level **{level}** reward. Roles already handed "
                "out stay put."
            )
        )

    @levelrewards.command(
        name="list",
        help="Show every level reward in this server.",
        usage="levelrewards list")
    @commands.has_permissions(manage_guild=True)
    async def levelrewards_list(ctx: commands.Context) -> None:
        rows = await levels.list_rewards(bot.db, ctx.guild.id)
        entries = []
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            label = (
                role.mention
                if role is not None
                else f"deleted role `{row['role_id']}`"
            )
            entries.append((row["level"], label))
        await ctx.send(embed=level_rewards_embed(entries))
