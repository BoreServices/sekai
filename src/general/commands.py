import re
from collections import deque

import discord
from discord.ext import commands

from core.emojis import markup
from view import error_embed, ping_embed, snipe_embed, snipe_media, success_embed
from view.snipe import SnipedMessage, SnipeView

# Deleted messages kept per channel, and the most pages snipe can page through.
SNIPE_LIMIT = 25

URL_RE = re.compile(r"https?://\S+")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
TRAILING_PUNCTUATION = ">.,!?;:\"'"

_snipes: dict[int, deque[SnipedMessage]] = {}


def _clean(url: str | None) -> str | None:
    """Strip the punctuation people leave behind a pasted link."""
    if not url:
        return None
    return url.rstrip(TRAILING_PUNCTUATION) or None


def _is_image(attachment: discord.Attachment) -> bool:
    if (attachment.content_type or "").startswith("image/"):
        return True
    return (attachment.filename or "").lower().endswith(IMAGE_SUFFIXES)


def _unique(values: list[str | None]) -> tuple[str, ...]:
    seen: set[str] = set()
    found: list[str] = []
    for value in values:
        url = _clean(value)
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    return tuple(found)


def _sniped(message: discord.Message) -> SnipedMessage:
    """Everything snipe needs to rebuild the message: text, files and links."""
    attachments = list(message.attachments)
    files = _unique([a.url for a in attachments])
    links: list[str | None] = [m.group() for m in URL_RE.finditer(message.content)]
    media: list[str | None] = [a.url for a in attachments if _is_image(a)]
    for embed in message.embeds:
        if embed.url:
            links += [embed.url]
        if embed.image and embed.image.url:
            media += [embed.image.url]
        if embed.thumbnail and embed.thumbnail.url:
            media += [embed.thumbnail.url]
    links += [sticker.url for sticker in message.stickers]
    avatar_url = None
    if message.author.avatar:
        avatar_url = message.author.avatar.url
    elif message.author.default_avatar:
        avatar_url = message.author.default_avatar.url
    return SnipedMessage(
        author=str(message.author),
        author_avatar=avatar_url,
        created_at=message.created_at,
        content=message.content,
        files=files,
        links=_unique(links),
        media=_unique(media),
        jump_url=message.jump_url)


def setup(bot) -> None:
    @bot.listen("on_message_delete")
    async def _remember_deleted(message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        _snipes.setdefault(
            message.channel.id, deque(maxlen=SNIPE_LIMIT)
        ).appendleft(_sniped(message))

    @bot.command(name="ping", help="Check the bot's latency.", usage="ping")
    async def ping(ctx: commands.Context) -> None:
        await ctx.send(embed=ping_embed(bot))

    @bot.command(
        name="snipe",
        aliases=["s"],
        help=(
            "Show a recently deleted message in this channel, newest first, "
            "files and all. "
            f"One message per page, up to {SNIPE_LIMIT} kept."
        ),
        usage="snipe [page]")
    @commands.guild_only()
    async def snipe(ctx: commands.Context, page: int = 1) -> None:
        cache = _snipes.get(ctx.channel.id)
        if not cache:
            await ctx.send(
                embed=error_embed("Nothing was deleted in this channel recently.")
            )
            return
        if not 1 <= page <= len(cache):
            await ctx.send(
                embed=error_embed(f"Page must be between 1 and {len(cache)}.")
            )
            return

        async def render(target: int) -> tuple[str, discord.Embed, int]:
            messages = list(_snipes.get(ctx.channel.id, ()))
            if not messages:
                return (
                    "",
                    error_embed("There is nothing left to snipe in this channel."),
                    1)
            total = len(messages)
            target = max(1, min(target, total))
            sniped = messages[target - 1]
            return (
                snipe_media(sniped),
                snipe_embed(
                    sniped,
                    index=target,
                    total=total,
                    prefix=ctx.prefix),
                total)

        content, embed, pages = await render(page)
        await ctx.send(
            content=content or None,
            embed=embed,
            view=SnipeView(
                author_id=ctx.author.id,
                page=page,
                pages=pages,
                render=render))

    @bot.command(
        name="clearsnipe",
        aliases=["cs"],
        help="Clear this channel's snipe history.",
        usage="clearsnipe")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(ctx: commands.Context) -> None:
        _snipes.pop(ctx.channel.id, None)
        await ctx.send(
            embed=success_embed(
                "Snipe history cleared for this channel.", icon=markup("trash", "🗑️")
            )
        )
