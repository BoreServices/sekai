import logging

import discord
from discord.ext import commands

from view import (
    error_embed,
    info_embed,
    success_embed,
    tag_list_embed,
    tag_show_embed)

log = logging.getLogger("sekai.tags")

MAX_NAME = 32
MAX_CONTENT = 1500
MAX_TAGS = 200
PER_PAGE = 50


def _clean_name(raw: str) -> str | None:
    """Tag names are single lowercase words so `tag <name>` parses cleanly."""
    name = raw.strip().lower()
    if not name or len(name) > MAX_NAME or any(char.isspace() for char in name):
        return None
    return name


def _clean_content(raw: str) -> str | None:
    content = raw.strip()
    if not content or len(content) > MAX_CONTENT:
        return None
    return content


async def _lookup(bot, guild_id: int, name: str):
    return await bot.db.fetchone(
        "SELECT name, content, author_id, uses FROM tags "
        "WHERE guild_id = ? AND name = ?",
        (guild_id, name))


def setup(bot) -> None:
    @bot.group(
        name="tag",
        help="Show a saved tag, or manage them with the subcommands.",
        usage="tag <name>",
        invoke_without_command=True)
    @commands.guild_only()
    async def tag(ctx: commands.Context, name: str | None = None) -> None:
        if name is None:
            await ctx.send(
                embed=error_embed(
                    f"Use `{ctx.prefix}tag <name>` to show one, "
                    f"`{ctx.prefix}tags` to list them all."
                )
            )
            return

        cleaned = _clean_name(name)
        row = await _lookup(bot, ctx.guild.id, cleaned) if cleaned else None
        if row is None:
            await ctx.send(embed=error_embed(f"There's no tag named `{name}` here."))
            return

        await bot.db.execute(
            "UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?",
            (ctx.guild.id, row["name"]))
        await ctx.send(
            embed=tag_show_embed(
                name=row["name"],
                content=row["content"],
                author=f"<@{row['author_id']}>",
                uses=row["uses"] + 1)
        )

    @tag.command(
        name="add",
        aliases=["create"],
        help="Save a tag members can recall later.",
        usage="tag add <name> <content>")
    @commands.has_permissions(manage_messages=True)
    async def tag_add(ctx: commands.Context, name: str, *, content: str) -> None:
        cleaned = _clean_name(name)
        if cleaned is None:
            await ctx.send(
                embed=error_embed(
                    f"Tag names are single words, up to {MAX_NAME} characters."
                )
            )
            return
        text = _clean_content(content)
        if text is None:
            await ctx.send(
                embed=error_embed(
                    f"Give the tag some content, under {MAX_CONTENT} characters."
                )
            )
            return
        if await _lookup(bot, ctx.guild.id, cleaned) is not None:
            await ctx.send(embed=error_embed(f"`{cleaned}` already exists."))
            return

        total = await bot.db.fetchone(
            "SELECT COUNT(*) AS total FROM tags WHERE guild_id = ?", (ctx.guild.id)
        )
        if total is not None and total["total"] >= MAX_TAGS:
            await ctx.send(
                embed=error_embed(
                    f"This server already has {MAX_TAGS} tags — remove one first."
                )
            )
            return

        await bot.db.execute(
            "INSERT INTO tags (guild_id, name, content, author_id) "
            "VALUES (?, ?, ?, ?)",
            (ctx.guild.id, cleaned, text, ctx.author.id))
        await ctx.send(
            embed=success_embed(
                f"Saved tag `{cleaned}` — members can open it with "
                f"`{ctx.prefix}tag {cleaned}`.",
                icon="🏷️")
        )

    @tag.command(
        name="edit",
        help="Replace the content of an existing tag.",
        usage="tag edit <name> <content>")
    @commands.has_permissions(manage_messages=True)
    async def tag_edit(ctx: commands.Context, name: str, *, content: str) -> None:
        cleaned = _clean_name(name)
        text = _clean_content(content)
        if cleaned is None or text is None:
            await ctx.send(
                embed=error_embed(
                    f"Use `{ctx.prefix}tag edit <name> <content>` — tag names are "
                    "single words and content stays under "
                    f"{MAX_CONTENT} characters."
                )
            )
            return
        if await _lookup(bot, ctx.guild.id, cleaned) is None:
            await ctx.send(embed=error_embed(f"There's no tag named `{cleaned}`."))
            return

        await bot.db.execute(
            "UPDATE tags SET content = ? WHERE guild_id = ? AND name = ?",
            (text, ctx.guild.id, cleaned))
        await ctx.send(embed=success_embed(f"Updated tag `{cleaned}`.", icon="🏷️"))

    @tag.command(
        name="rename",
        help="Give a tag a new name.",
        usage="tag rename <name> <new name>")
    @commands.has_permissions(manage_messages=True)
    async def tag_rename(ctx: commands.Context, name: str, new_name: str) -> None:
        cleaned = _clean_name(name)
        renamed = _clean_name(new_name)
        if cleaned is None or renamed is None:
            await ctx.send(
                embed=error_embed("Both names must be single words.")
            )
            return
        if await _lookup(bot, ctx.guild.id, cleaned) is None:
            await ctx.send(embed=error_embed(f"There's no tag named `{cleaned}`."))
            return
        if cleaned != renamed and await _lookup(bot, ctx.guild.id, renamed) is not None:
            await ctx.send(embed=error_embed(f"`{renamed}` already exists."))
            return

        await bot.db.execute(
            "UPDATE tags SET name = ? WHERE guild_id = ? AND name = ?",
            (renamed, ctx.guild.id, cleaned))
        await ctx.send(
            embed=success_embed(f"Renamed `{cleaned}` to `{renamed}`.", icon="🏷️")
        )

    @tag.command(
        name="remove",
        aliases=["delete"],
        help="Delete a tag for good.",
        usage="tag remove <name>")
    @commands.has_permissions(manage_messages=True)
    async def tag_remove(ctx: commands.Context, name: str) -> None:
        cleaned = _clean_name(name)
        if cleaned is None or await _lookup(bot, ctx.guild.id, cleaned) is None:
            await ctx.send(embed=error_embed(f"There's no tag named `{name}`."))
            return

        await bot.db.execute(
            "DELETE FROM tags WHERE guild_id = ? AND name = ?",
            (ctx.guild.id, cleaned))
        log.info("Tag %s removed in %s by %s", cleaned, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=success_embed(f"Deleted tag `{cleaned}`."))

    @tag.command(
        name="info",
        help="See who wrote a tag, how often it's used and its content.",
        usage="tag info <name>")
    async def tag_info(ctx: commands.Context, name: str) -> None:
        cleaned = _clean_name(name)
        row = (
            await bot.db.fetchone(
                "SELECT name, content, author_id, uses, "
                "strftime('%s', created_at) AS created_unix FROM tags "
                "WHERE guild_id = ? AND name = ?",
                (ctx.guild.id, cleaned))
            if cleaned
            else None
        )
        if row is None:
            await ctx.send(embed=error_embed(f"There's no tag named `{name}`."))
            return

        preview = discord.utils.escape_markdown(row["content"])[:1000]
        await ctx.send(
            embed=info_embed(
                title=f"🏷️ {discord.utils.escape_markdown(row['name'])}",
                fields=[
                    ("Author", f"<@{row['author_id']}>", True),
                    ("Uses", f"{row['uses']:,}", True),
                    ("Created", f"<t:{row['created_unix']}:R>", True),
                    ("Content", f"```\n{preview}\n```", False),
                ])
        )

    @bot.command(
        name="tags",
        aliases=["taglist"],
        help="List every tag saved in this server.",
        usage="tags [member]")
    @commands.guild_only()
    async def tags(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        clause = "guild_id = ?"
        parameters: list[int] = [ctx.guild.id]
        title = f"🏷️ Tags in {ctx.guild.name}"
        if member is not None:
            clause += " AND author_id = ?"
            parameters.append(member.id)
            title = f"🏷️ Tags by {member.display_name}"

        count = await bot.db.fetchone(
            f"SELECT COUNT(*) AS total FROM tags WHERE {clause}", parameters
        )
        rows = await bot.db.fetchall(
            f"SELECT name, uses FROM tags WHERE {clause} "
            "ORDER BY name ASC LIMIT ?",
            [*parameters, PER_PAGE])
        await ctx.send(
            embed=tag_list_embed(
                title=title,
                entries=rows,
                total=count["total"] if count is not None else 0)
        )
