import datetime
from contextlib import suppress
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord

from core.emojis import iconize
from view.base import ERROR_COLOR, base_embed, brand


@dataclass(frozen=True)
class SnipedMessage:
    author: str
    author_avatar: str | None
    created_at: datetime.datetime
    content: str
    # Every file that was attached, in order. These get posted below the embed
    # so Discord shows the real thing instead of just a count.
    files: tuple[str, ...] = ()
    # Anything the deleted message pointed at: typed links, embed URLs, stickers.
    links: tuple[str, ...] = ()
    # Media it showed. The first one becomes the embed picture.
    media: tuple[str, ...] = ()
    jump_url: str | None = None


FIELD_VALUE_LIMIT = 1024
MAX_LINKS = 5
MAX_FILES = 4
MIN_QUOTE = 120
QUOTE_LIMIT = 940

RenderPage = Callable[[int], Awaitable[tuple[str, discord.Embed, int]]]


def _quote(text: str, limit: int = QUOTE_LIMIT) -> str:
    text = text.strip()
    if not text:
        return "*(no text)*"
    quoted = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
    if len(quoted) <= limit:
        return quoted
    return quoted[: limit - 1].rstrip() + "…"


def _extras(message: SnipedMessage, quote: str) -> list[str]:
    """Lines under the quoted text for links the quote itself doesn't show."""
    hidden = [
        url for url in (*message.links, *message.media[1:]) if url not in quote
    ]
    lines = [f"🔗 {url}" for url in hidden[:MAX_LINKS]]
    if len(hidden) > MAX_LINKS:
        lines.append(f"🔗 +{len(hidden) - MAX_LINKS} more")
    return lines


def snipe_media(message: SnipedMessage) -> str:
    """Bare attachment URLs posted as message content so Discord renders the
    files themselves under the embed: pictures and video inline, everything
    else as a file card. Whatever the embed already shows is skipped."""
    picture = {message.media[0]} if message.media else set()
    rest = [url for url in message.files if url not in picture]
    shown = rest[:MAX_FILES]
    if len(rest) > len(shown):
        left = len(rest) - len(shown)
        shown.append(f"…and {left} more attachment{'s' if left != 1 else ''}")
    return "\n".join(shown)


def snipe_embed(
    message: SnipedMessage,
    *,
    index: int,
    total: int,
    prefix: str = "p!",
) -> discord.Embed:
    heading = f"💬 Deleted Message • {index}/{total}"
    quote = _quote(message.content)
    extras = _extras(message, quote)
    budget = FIELD_VALUE_LIMIT - sum(len(line) + 1 for line in extras)
    if budget < len(quote):
        # Long message: shrink the quote so the links below stay visible.
        quote = _quote(message.content, max(MIN_QUOTE, budget))
        extras = _extras(message, quote)
    value = "\n".join([quote, *extras])[:FIELD_VALUE_LIMIT]

    footer = f"Page {index}/{total} • Use {prefix}clearsnipe to clear"
    desc = f"**{heading}**\n*by {message.author}*\n\n{value}\n\n`{footer}`"
    embed = base_embed(description=desc, color=ERROR_COLOR)

    if message.media:
        embed.set_image(url=message.media[0])

    if message.jump_url:
        embed.url = message.jump_url

    embed.add_field(
        name="Deleted",
        value=discord.utils.format_dt(message.created_at, "R"),
        inline=True,
    )
    embed.add_field(name="Channel", value="#snipe", inline=True)

    return brand(embed, footer=footer)


class SnipeView(discord.ui.View):
    """One sniped message per page, with buttons locked to the invoker."""

    def __init__(
        self,
        *,
        author_id: int,
        page: int,
        pages: int,
        render: RenderPage,
    ) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.page = page
        self.pages = pages
        self._render = render
        self._sync()

    def _sync(self) -> None:
        at_first = self.page <= 1
        at_last = self.page >= self.pages
        self.first.disabled = at_first
        self.previous.disabled = at_first
        self.next.disabled = at_last
        self.last.disabled = at_last

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Run the snipe command yourself to flip through its pages.",
            ephemeral=True,
        )
        return False

    async def _go(self, interaction: discord.Interaction, page: int) -> None:
        target = max(1, min(page, self.pages))
        content, embed, pages = await self._render(target)
        self.page = min(target, pages)
        self.pages = pages
        self._sync()
        await interaction.response.edit_message(
            content=content or None,
            embed=embed,
            view=self,
        )

    @discord.ui.button(label="First", style=discord.ButtonStyle.secondary)
    async def first(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._go(interaction, 1)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._go(interaction, self.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._go(interaction, self.page + 1)

    @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
    async def last(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._go(interaction, self.pages)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        message = getattr(self, "message", None)
        if message is not None:
            with suppress(discord.HTTPException):
                await message.edit(view=self)


__all__ = ["SnipedMessage", "SnipeView", "snipe_embed", "snipe_media"]
