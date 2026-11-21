import logging
from contextlib import suppress

import discord
from discord.ext import commands

from src.reactionroles import state
from view import error_embed, info_embed, success_embed

log = logging.getLogger("sekai.reactionroles")

MAX_LIST = 25


def _role_problem(guild: discord.Guild, role: discord.Role) -> str | None:
    me = guild.me
    if role.is_default():
        return "You can't assign @everyone."
    if role.managed:
        return "That role belongs to an integration and can't be assigned."
    if me is None or not me.guild_permissions.manage_roles:
        return "I need the Manage Roles permission to hand out that role."
    if role >= me.top_role:
        return "Move my role above that one first."
    return None


def _message_url(mapping: state.Mapping) -> str:
    return (
        f"https://discord.com/channels/{mapping.guild_id}/"
        f"{mapping.channel_id}/{mapping.message_id}"
    )


async def _apply(bot, payload: discord.RawReactionActionEvent, *, add: bool) -> None:
    if payload.guild_id is None or bot.user is None:
        return
    if payload.user_id == bot.user.id:
        return
    if not state._loaded:
        await state.load_state(bot)
    mapping = state.get(payload.message_id, str(payload.emoji))
    if mapping is None:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    member = payload.member or guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.HTTPException:
            return
    if member.bot:
        return

    role = guild.get_role(mapping.role_id)
    if role is None:
        return
    try:
        if add and role not in member.roles:
            await member.add_roles(role, reason="Reaction role")
        elif not add and role in member.roles:
            await member.remove_roles(role, reason="Reaction role removed")
    except discord.HTTPException as exc:
        log.warning(
            "Could not update reaction role %s for %s: %s", role.id, member.id, exc
        )
        return
    if add:
        log.info(
            "Reaction role %s given to %s in guild %s",
            role.id,
            member.id,
            guild.id)
    else:
        log.info(
            "Reaction role %s removed from %s in guild %s",
            role.id,
            member.id,
            guild.id)


def setup(bot) -> None:
    @bot.listen("on_ready")
    async def load_reaction_roles() -> None:
        if not state._loaded:
            await state.load_state(bot)

    @bot.listen("on_raw_reaction_add")
    async def reaction_role_add(payload: discord.RawReactionActionEvent) -> None:
        await _apply(bot, payload, add=True)

    @bot.listen("on_raw_reaction_remove")
    async def reaction_role_remove(payload: discord.RawReactionActionEvent) -> None:
        await _apply(bot, payload, add=False)

    @bot.listen("on_raw_message_delete")
    async def forget_deleted_message(payload: discord.RawMessageDeleteEvent) -> None:
        if payload.message_id in state._mappings:
            await state.clear_message(bot, payload.message_id)

    @bot.listen("on_raw_bulk_message_delete")
    async def forget_deleted_messages(
        payload: discord.RawBulkMessageDeleteEvent) -> None:
        for message_id in payload.message_ids:
            if message_id in state._mappings:
                await state.clear_message(bot, message_id)

    @bot.group(
        name="reactionroles",
        aliases=["reactionrole"],
        help="Give roles when members react to a message.",
        usage="reactionroles",
        invoke_without_command=True)
    @commands.guild_only()
    async def reactionroles(ctx: commands.Context) -> None:
        await ctx.send(
            embed=info_embed(
                title="Reaction roles",
                description=(
                    "Pick a message, an emoji and a role — members get the role "
                    "by reacting and lose it when they remove the reaction."
                ),
                fields=[
                    (
                        "Commands",
                        "`reactionroles add <message> <emoji> <role>`\n"
                        "`reactionroles edit <message> <emoji> <role>`\n"
                        "`reactionroles remove <message> <emoji>`\n"
                        "`reactionroles refresh <message>`\n"
                        "`reactionroles list` · `reactionroles clear <message>`",
                        False)
                ])
        )

    @reactionroles.command(
        name="add",
        help="Let members get a role by reacting with an emoji.",
        usage="reactionroles add <message> <emoji> <role>")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rr_add(
        ctx: commands.Context,
        message: discord.Message,
        emoji: str,
        role: discord.Role) -> None:
        if message.guild is None or message.guild.id != ctx.guild.id:
            await ctx.send(embed=error_embed("That message isn't in this server."))
            return
        problem = _role_problem(ctx.guild, role)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        parsed = discord.PartialEmoji.from_str(emoji)
        key = str(parsed)
        mapping = state.Mapping(
            guild_id=ctx.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            emoji=key,
            role_id=role.id)
        await state.add(bot, mapping)
        try:
            await message.add_reaction(parsed)
        except discord.HTTPException as exc:
            log.warning("Could not add reaction to %s: %s", message.id, exc)
            await ctx.send(
                embed=error_embed(
                    "Saved, but I couldn't add that reaction — check my "
                    "**Add Reactions** and **Read Message History** permissions."
                )
            )
            return
        await ctx.send(
            embed=success_embed(
                f"Reacting with {parsed} now gives {role.mention}.", icon="🎭"
            )
        )

    @reactionroles.command(
        name="remove",
        help="Stop using an emoji on a message as a reaction role.",
        usage="reactionroles remove <message> <emoji>")
    @commands.has_permissions(manage_roles=True)
    async def rr_remove(
        ctx: commands.Context, message: discord.Message, emoji: str
    ) -> None:
        parsed = discord.PartialEmoji.from_str(emoji)
        if not await state.remove(bot, message.id, str(parsed)):
            await ctx.send(
                embed=error_embed(
                    "That emoji isn't set up as a reaction role on that message."
                )
            )
            return
        me = ctx.guild.me
        if me is not None:
            with suppress(discord.HTTPException):
                await message.remove_reaction(parsed, me)
        await ctx.send(
            embed=success_embed(
                f"Removed {parsed} from that message's reaction roles."
            )
        )

    @reactionroles.command(
        name="edit",
        help="Change the role an existing reaction gives.",
        usage="reactionroles edit <message> <emoji> <role>")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rr_edit(
        ctx: commands.Context,
        message: discord.Message,
        emoji: str,
        role: discord.Role) -> None:
        if message.guild is None or message.guild.id != ctx.guild.id:
            await ctx.send(embed=error_embed("That message isn't in this server."))
            return
        parsed = discord.PartialEmoji.from_str(emoji)
        mapping = state.get(message.id, str(parsed))
        if mapping is None or mapping.guild_id != ctx.guild.id:
            await ctx.send(
                embed=error_embed(
                    "That emoji isn't a reaction role on that message — add it "
                    "first."
                )
            )
            return
        problem = _role_problem(ctx.guild, role)
        if problem:
            await ctx.send(embed=error_embed(problem))
            return
        mapping.role_id = role.id
        mapping.channel_id = message.channel.id
        await state.add(bot, mapping)
        await ctx.send(
            embed=success_embed(
                f"{parsed} now gives {role.mention}.", icon="🎭"
            )
        )

    @reactionroles.command(
        name="refresh",
        help="Re-add the bot's reactions that were removed from a message.",
        usage="reactionroles refresh <message>")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(
        add_reactions=True, read_message_history=True
    )
    async def rr_refresh(
        ctx: commands.Context, message: discord.Message
    ) -> None:
        if message.guild is None or message.guild.id != ctx.guild.id:
            await ctx.send(embed=error_embed("That message isn't in this server."))
            return
        mappings = state.for_message(message.id)
        if not mappings:
            await ctx.send(
                embed=error_embed("That message has no reaction roles.")
            )
            return
        me = ctx.guild.me
        restored = 0
        failed = 0
        for mapping in mappings:
            reaction = next(
                (
                    item
                    for item in message.reactions
                    if str(item.emoji) == mapping.emoji
                ),
                None)
            if reaction is not None and (me is None or reaction.me):
                continue
            try:
                await message.add_reaction(
                    discord.PartialEmoji.from_str(mapping.emoji)
                )
                restored += 1
            except discord.HTTPException:
                failed += 1
        if failed:
            await ctx.send(
                embed=error_embed(
                    f"Re-added {restored} reaction(s); {failed} failed — check "
                    "my **Add Reactions** and **Read Message History** "
                    "permissions."
                )
            )
        elif restored:
            await ctx.send(
                embed=success_embed(
                    f"Re-added {restored} reaction(s) on that message.",
                    icon="🎭")
            )
        else:
            await ctx.send(
                embed=success_embed(
                    "Every reaction is already in place.", icon="🎭"
                )
            )

    @reactionroles.command(
        name="list",
        aliases=["show"],
        help="List the reaction roles in this server.",
        usage="reactionroles list")
    async def rr_list(ctx: commands.Context) -> None:
        mappings = state.for_guild(ctx.guild.id)
        if not mappings:
            await ctx.send(
                embed=error_embed(
                    "No reaction roles in this server yet — add one with "
                    "`reactionroles add`."
                )
            )
            return
        fields = []
        shown = mappings[:MAX_LIST]
        for mapping in shown:
            role = ctx.guild.get_role(mapping.role_id)
            fields.append(
                (
                    f"{mapping.emoji} → {role.mention if role else '*deleted role*'}",
                    f"[Message]({_message_url(mapping)})",
                    False)
            )
        description = f"{len(mappings)} mapping(s) in this server."
        if len(mappings) > MAX_LIST:
            description = (
                f"Showing the first {MAX_LIST} of {len(mappings)} mappings."
            )
        await ctx.send(
            embed=info_embed(
                title="Reaction roles", description=description, fields=fields
            )
        )

    @reactionroles.command(
        name="clear",
        help="Remove every reaction role from a message.",
        usage="reactionroles clear <message>")
    @commands.has_permissions(manage_roles=True)
    async def rr_clear(ctx: commands.Context, message: discord.Message) -> None:
        emojis = await state.clear_message(bot, message.id)
        if not emojis:
            await ctx.send(
                embed=error_embed("That message has no reaction roles.")
            )
            return
        me = ctx.guild.me
        if me is not None:
            for emoji in emojis:
                with suppress(discord.HTTPException):
                    await message.remove_reaction(
                        discord.PartialEmoji.from_str(emoji), me
                    )
        await ctx.send(
            embed=success_embed(
                f"Cleared {len(emojis)} reaction role(s) from that message."
            )
        )
