import logging

import discord
from discord.ext import commands

from view import (
    error_embed,
    starboard_embed,
    starboard_settings_embed,
    success_embed)

log = logging.getLogger("sekai.starboard")

DEFAULT_EMOJI = "⭐"
MIN_THRESHOLD = 1
MAX_THRESHOLD = 50
MAX_EMOJI = 64


def _flag(raw: str) -> bool | None:
    value = raw.strip().lower()
    if value in {"on", "true", "yes", "enable", "enabled", "1"}:
        return True
    if value in {"off", "false", "no", "disable", "disabled", "0"}:
        return False
    return None


async def _config(bot, guild_id: int):
    return await bot.db.fetchone(
        "SELECT * FROM starboard_config WHERE guild_id = ?", (guild_id,)
    )


async def _is_ignored(bot, guild_id: int, channel_id: int) -> bool:
    row = await bot.db.fetchone(
        "SELECT 1 FROM starboard_ignored WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id))
    return row is not None


async def _ignored_channels(bot, guild, guild_id: int) -> list:
    rows = await bot.db.fetchall(
        "SELECT channel_id FROM starboard_ignored WHERE guild_id = ?", (guild_id,)
    )
    return [
        channel
        for channel in (guild.get_channel(row["channel_id"]) for row in rows)
        if channel is not None
    ]


async def _star_count(message, emoji: str, author_id: int, self_star: bool) -> int:
    for reaction in message.reactions:
        if str(reaction.emoji) != emoji:
            continue
        count = reaction.count
        if not self_star:
            try:
                async for user in reaction.users():
                    if user.id == author_id:
                        count -= 1
                        break
            except discord.HTTPException:
                log.debug("Could not read reactors on %s", message.id)
        return max(count, 0)
    return 0


async def _drop_post(bot, channel, starboard_id: int, message_id: int) -> None:
    if channel is not None:
        try:
            post = await channel.fetch_message(starboard_id)
            await post.delete()
        except discord.HTTPException:
            pass
    await bot.db.execute(
        "DELETE FROM starboard_messages WHERE message_id = ?", (message_id)
    )


async def _refresh(bot, config, message, count: int) -> None:
    channel = bot.get_channel(config["channel_id"])
    row = await bot.db.fetchone(
        "SELECT starboard_id FROM starboard_messages WHERE message_id = ?",
        (message.id))
    if count < config["threshold"]:
        if row is not None:
            await _drop_post(bot, channel, row["starboard_id"], message.id)
        return
    if channel is None:
        return

    embed = starboard_embed(
        message=message,
        stars=count,
        emoji=config["emoji"],
        jump_url=message.jump_url)
    if row is None:
        try:
            post = await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception("Could not post to starboard in %s", message.guild.id)
            return
        await bot.db.execute(
            "INSERT INTO starboard_messages "
            "(message_id, guild_id, channel_id, starboard_id, author_id, stars) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                message.id,
                message.guild.id,
                message.channel.id,
                post.id,
                message.author.id,
                count))
        return

    try:
        post = await channel.fetch_message(row["starboard_id"])
    except discord.NotFound:
        # The repost was deleted by hand — put it back.
        try:
            post = await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception("Could not restore starboard post in %s", message.guild.id)
            return
        await bot.db.execute(
            "UPDATE starboard_messages SET starboard_id = ?, stars = ? "
            "WHERE message_id = ?",
            (post.id, count, message.id))
        return
    except discord.HTTPException:
        log.exception("Could not fetch starboard post in %s", message.guild.id)
        return

    try:
        await post.edit(embed=embed)
    except discord.HTTPException:
        log.exception("Could not edit starboard post in %s", message.guild.id)
        return
    await bot.db.execute(
        "UPDATE starboard_messages SET stars = ? WHERE message_id = ?",
        (count, message.id))


async def _handle(bot, payload) -> None:
    if payload.guild_id is None:
        return
    member = getattr(payload, "member", None)
    if member is not None and member.bot:
        return

    config = await _config(bot, payload.guild_id)
    if config is None or str(payload.emoji) != config["emoji"]:
        return
    if payload.channel_id == config["channel_id"]:
        return
    if await _is_ignored(bot, payload.guild_id, payload.channel_id):
        return

    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.HTTPException:
        return
    if message.author.bot or not (
        message.content or message.attachments or message.stickers
    ):
        return

    count = await _star_count(
        message, config["emoji"], message.author.id, bool(config["self_star"])
    )
    await _refresh(bot, config, message, count)


def setup(bot) -> None:
    @bot.listen("on_raw_reaction_add")
    async def starboard_reaction_add(payload) -> None:
        await _handle(bot, payload)

    @bot.listen("on_raw_reaction_remove")
    async def starboard_reaction_remove(payload) -> None:
        await _handle(bot, payload)

    @bot.group(
        name="starboard",
        aliases=["sb"],
        help="Repost the messages your members star the most.",
        usage="starboard",
        invoke_without_command=True)
    @commands.guild_only()
    async def starboard(ctx: commands.Context) -> None:
        config = await _config(bot, ctx.guild.id)
        if config is None:
            await ctx.send(
                embed=error_embed(
                    "Starboard isn't set up yet — run "
                    f"`{ctx.prefix}starboard setup <channel>`."
                )
            )
            return
        ignored = await _ignored_channels(bot, ctx.guild, ctx.guild.id)
        await ctx.send(
            embed=starboard_settings_embed(
                guild_name=ctx.guild.name,
                channel=ctx.guild.get_channel(config["channel_id"]),
                emoji=config["emoji"],
                threshold=config["threshold"],
                self_star=bool(config["self_star"]),
                ignored=ignored)
        )

    @starboard.command(
        name="setup",
        help="Choose the channel stars are reposted to.",
        usage="starboard setup <channel> [emoji]")
    @commands.has_permissions(manage_guild=True)
    async def starboard_setup(
        ctx: commands.Context,
        channel: discord.TextChannel,
        emoji: discord.PartialEmoji | None = None) -> None:
        if ctx.guild.me is not None and not channel.permissions_for(
            ctx.guild.me
        ).send_messages:
            await ctx.send(
                embed=error_embed("I can't post in that channel.")
            )
            return
        label = str(emoji) if emoji is not None else DEFAULT_EMOJI
        if len(label) > MAX_EMOJI:
            await ctx.send(embed=error_embed("That emoji is too long."))
            return

        existing = await _config(bot, ctx.guild.id)
        if existing is None:
            await bot.db.execute(
                "INSERT INTO starboard_config (guild_id, channel_id, emoji) "
                "VALUES (?, ?, ?)",
                (ctx.guild.id, channel.id, label))
        else:
            await bot.db.execute(
                "UPDATE starboard_config SET channel_id = ?, emoji = ?, "
                "updated_at = datetime('now') WHERE guild_id = ?",
                (channel.id, label, ctx.guild.id))
        await ctx.send(
            embed=success_embed(
                f"Starboard posts go to {channel.mention} with {label}.",
                icon="⭐")
        )

    @starboard.command(
        name="threshold",
        help="Set how many reactions earn a repost.",
        usage="starboard threshold <count>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_threshold(ctx: commands.Context, count: int) -> None:
        if not MIN_THRESHOLD <= count <= MAX_THRESHOLD:
            await ctx.send(
                embed=error_embed(
                    f"Threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD}."
                )
            )
            return
        if await _config(bot, ctx.guild.id) is None:
            await ctx.send(
                embed=error_embed("Set the starboard channel up first.")
            )
            return
        await bot.db.execute(
            "UPDATE starboard_config SET threshold = ?, updated_at = datetime('now') "
            "WHERE guild_id = ?",
            (count, ctx.guild.id))
        await ctx.send(
            embed=success_embed(
                f"Messages now need **{count}** reaction"
                f"{'s' if count != 1 else ''} to hit the starboard.",
                icon="⭐")
        )

    @starboard.command(
        name="emoji",
        help="Pick which reaction counts as a star.",
        usage="starboard emoji <emoji>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_emoji(
        ctx: commands.Context, emoji: discord.PartialEmoji
    ) -> None:
        label = str(emoji)
        if await _config(bot, ctx.guild.id) is None:
            await ctx.send(embed=error_embed("Set the starboard channel up first."))
            return
        await bot.db.execute(
            "UPDATE starboard_config SET emoji = ?, updated_at = datetime('now') "
            "WHERE guild_id = ?",
            (label, ctx.guild.id))
        await ctx.send(
            embed=success_embed(f"Stars are now counted with {label}.", icon="⭐")
        )

    @starboard.command(
        name="selfstar",
        help="Allow the message author to star their own message.",
        usage="starboard selfstar <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_selfstar(ctx: commands.Context, value: str) -> None:
        flag = _flag(value)
        if flag is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        if await _config(bot, ctx.guild.id) is None:
            await ctx.send(embed=error_embed("Set the starboard channel up first."))
            return
        await bot.db.execute(
            "UPDATE starboard_config SET self_star = ?, updated_at = datetime('now') "
            "WHERE guild_id = ?",
            (1 if flag else 0, ctx.guild.id))
        await ctx.send(
            embed=success_embed(
                f"Self-starring is now **{'allowed' if flag else 'ignored'}**.",
                icon="⭐")
        )

    @starboard.command(
        name="ignore",
        help="Keep a channel out of the starboard.",
        usage="starboard ignore <channel>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_ignore(
        ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        if await _is_ignored(bot, ctx.guild.id, channel.id):
            await ctx.send(
                embed=error_embed(f"{channel.mention} is already ignored.")
            )
            return
        await bot.db.execute(
            "INSERT INTO starboard_ignored (guild_id, channel_id) VALUES (?, ?)",
            (ctx.guild.id, channel.id))
        await ctx.send(
            embed=success_embed(f"{channel.mention} is now ignored.", icon="⭐")
        )

    @starboard.command(
        name="unignore",
        help="Start watching a channel again.",
        usage="starboard unignore <channel>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_unignore(
        ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        if not await _is_ignored(bot, ctx.guild.id, channel.id):
            await ctx.send(
                embed=error_embed(f"{channel.mention} isn't ignored.")
            )
            return
        await bot.db.execute(
            "DELETE FROM starboard_ignored WHERE guild_id = ? AND channel_id = ?",
            (ctx.guild.id, channel.id))
        await ctx.send(
            embed=success_embed(f"{channel.mention} is watched again.", icon="⭐")
        )

    @starboard.command(
        name="remove",
        help="Take a message off the starboard, even if it's still starred.",
        usage="starboard remove <message link>")
    @commands.has_permissions(manage_guild=True)
    async def starboard_remove(
        ctx: commands.Context, message: discord.Message
    ) -> None:
        row = await bot.db.fetchone(
            "SELECT starboard_id FROM starboard_messages WHERE message_id = ?",
            (message.id))
        if row is None:
            await ctx.send(
                embed=error_embed("That message isn't on the starboard.")
            )
            return
        config = await _config(bot, ctx.guild.id)
        channel = (
            bot.get_channel(config["channel_id"]) if config is not None else None
        )
        await _drop_post(bot, channel, row["starboard_id"], message.id)
        await ctx.send(embed=success_embed("Removed it from the starboard."))

    @starboard.command(
        name="disable",
        help="Turn the starboard off and forget its settings.",
        usage="starboard disable")
    @commands.has_permissions(manage_guild=True)
    async def starboard_disable(ctx: commands.Context) -> None:
        if await _config(bot, ctx.guild.id) is None:
            await ctx.send(embed=error_embed("Starboard is already off."))
            return
        await bot.db.execute(
            "DELETE FROM starboard_config WHERE guild_id = ?", (ctx.guild.id)
        )
        await bot.db.execute(
            "DELETE FROM starboard_ignored WHERE guild_id = ?", (ctx.guild.id)
        )
        await ctx.send(
            embed=success_embed(
                "Starboard is off. Existing posts stay put; set it up again "
                "any time.",
                icon="⭐")
        )
