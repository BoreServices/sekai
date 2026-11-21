import logging
import math
from contextlib import suppress

import discord

from core.emojis import emoji_partial
from src.pinterest import client as pinterest
from view.error import error_embed
from view.pinterest.embeds import (
    pinterest_board_embed,
    pinterest_boards_embed,
    pinterest_profile_embed,
    pinterest_user_pins_embed)

log = logging.getLogger("sekai.pinterest")

BOARDS_PER_PAGE = 5
PINS_PER_PAGE = 1
MENU_TIMEOUT = 240


def _pages(total: int, per_page: int) -> int:
    return max(1, math.ceil(total / per_page))


def _slice(items: list, page: int, per_page: int) -> list:
    start = (page - 1) * per_page
    return items[start : start + per_page]


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _page_footer(footer: str, page: int, pages: int) -> str:
    return f"{footer}  ·  Page {page}/{pages}"


class _PinterestView(discord.ui.View):
    def __init__(self, *, invoker_id: int, footer: str) -> None:
        super().__init__(timeout=MENU_TIMEOUT)
        self.invoker_id = invoker_id
        self.footer = footer
        self.message: discord.Message | None = None

    def adopt(self, interaction: discord.Interaction) -> None:
        self.message = interaction.message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message(
            embed=error_embed(
                "This Pinterest menu isn't yours — run the command yourself."
            ),
            ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)


async def _close(interaction: discord.Interaction, view: discord.ui.View) -> None:
    for child in view.children:
        child.disabled = True
    await interaction.response.edit_message(view=view)
    view.stop()


class PinterestProfileView(_PinterestView):
    def __init__(
        self, *, invoker_id: int, profile: pinterest.ProfileResult, footer: str
    ) -> None:
        super().__init__(invoker_id=invoker_id, footer=footer)
        self.profile = profile
        self.boards_button.emoji = emoji_partial("pin") or "📌"
        self.pins_button.emoji = emoji_partial("paper") or "🗂️"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"

    def embed(self) -> discord.Embed:
        return pinterest_profile_embed(self.profile.user, footer=self.footer)

    @discord.ui.button(label="Boards", style=discord.ButtonStyle.primary)
    async def boards_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PinterestBoardsView(
            invoker_id=self.invoker_id, profile=self.profile, footer=self.footer
        )
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.embed(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Pins", style=discord.ButtonStyle.secondary)
    async def pins_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.profile.pins:
            await interaction.response.send_message(
                embed=error_embed(
                    f"@{self.profile.user.username} doesn't have any public pins."
                ),
                ephemeral=True)
            return
        view = PinterestPinsView(
            invoker_id=self.invoker_id, profile=self.profile, footer=self.footer
        )
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.render(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _close(interaction, self)


class BoardSelect(discord.ui.Select):
    def __init__(self, menu: "PinterestBoardsView") -> None:
        self.menu = menu
        super().__init__(
            placeholder="Choose a board…", row=0, options=menu.options()
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.menu.open_board(interaction, self.values[0])


class PinterestBoardsView(_PinterestView):
    def __init__(
        self,
        *,
        invoker_id: int,
        profile: pinterest.ProfileResult,
        footer: str,
        page: int = 1) -> None:
        super().__init__(invoker_id=invoker_id, footer=footer)
        self.profile = profile
        self.pages = _pages(len(profile.boards), BOARDS_PER_PAGE)
        self.page = max(1, min(page, self.pages))
        self.select: BoardSelect | None = None
        if profile.boards:
            self.select = BoardSelect(self)
            self.add_item(self.select)
        self.profile_button.emoji = emoji_partial("user") or "👤"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"
        self._sync()

    def options(self) -> list[discord.SelectOption]:
        options = []
        for board in _slice(self.profile.boards, self.page, BOARDS_PER_PAGE):
            options.append(
                discord.SelectOption(
                    label=_clip(board.name, 100),
                    value=board.id or board.url_path,
                    description=_clip(
                        f"{board.pin_count:,} pins · "
                        f"{board.followers:,} followers",
                        100),
                    emoji=emoji_partial("pin") or "📌")
            )
        return options

    def _sync(self) -> None:
        self.previous_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.pages
        if self.select is not None:
            self.select.options = self.options()

    def embed(self) -> discord.Embed:
        return pinterest_boards_embed(
            self.profile.user,
            _slice(self.profile.boards, self.page, BOARDS_PER_PAGE),
            page=self.page,
            pages=self.pages,
            loaded=len(self.profile.boards),
            offset=(self.page - 1) * BOARDS_PER_PAGE,
            footer=_page_footer(self.footer, self.page, self.pages))

    async def _show(self, interaction: discord.Interaction, page: int) -> None:
        self.page = max(1, min(page, self.pages))
        self._sync()
        self.adopt(interaction)
        await interaction.response.edit_message(
            embed=self.embed(), view=self, attachments=[]
        )

    async def open_board(
        self, interaction: discord.Interaction, board_id: str
    ) -> None:
        board = next(
            (item for item in self.profile.boards if item.id == board_id), None
        )
        if board is None:
            await interaction.response.send_message(
                embed=error_embed("That board isn't available anymore."),
                ephemeral=True)
            return

        await interaction.response.defer()
        try:
            result = await pinterest.fetch_board(
                self.profile.user.username, board.url_path
            )
        except pinterest.PinterestError as exc:
            await interaction.followup.send(
                embed=error_embed(str(exc)), ephemeral=True
            )
            return
        except Exception:
            log.exception("Pinterest board lookup failed for %s", board.url_path)
            await interaction.followup.send(
                embed=error_embed("I couldn't load that board — try again."),
                ephemeral=True)
            return

        view = PinterestBoardView(
            invoker_id=self.invoker_id,
            profile=self.profile,
            result=result,
            footer=self.footer,
            boards_page=self.page)
        view.adopt(interaction)
        await interaction.edit_original_response(
            embed=view.render(), attachments=[], view=view
        )
        self.stop()

    @discord.ui.button(
        label="Previous", style=discord.ButtonStyle.secondary, row=1
    )
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=1)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page + 1)

    @discord.ui.button(
        label="Profile", style=discord.ButtonStyle.secondary, row=1
    )
    async def profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PinterestProfileView(
            invoker_id=self.invoker_id, profile=self.profile, footer=self.footer
        )
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.embed(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=1)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _close(interaction, self)


class PinterestBoardView(_PinterestView):
    def __init__(
        self,
        *,
        invoker_id: int,
        profile: pinterest.ProfileResult,
        result: pinterest.BoardResult,
        footer: str,
        page: int = 1,
        boards_page: int = 1) -> None:
        super().__init__(invoker_id=invoker_id, footer=footer)
        self.profile = profile
        self.result = result
        self.pages = _pages(len(result.pins), PINS_PER_PAGE)
        self.page = max(1, min(page, self.pages))
        self.boards_page = boards_page
        self.boards_button.emoji = emoji_partial("pin") or "📌"
        self.profile_button.emoji = emoji_partial("user") or "👤"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"
        self._sync()

    def _sync(self) -> None:
        self.previous_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.pages

    def render(self) -> discord.Embed:
        pins = _slice(self.result.pins, self.page, PINS_PER_PAGE)
        return pinterest_board_embed(
            self.profile.user,
            self.result.board,
            page=self.page,
            pages=self.pages,
            loaded=len(self.result.pins),
            footer=_page_footer(self.footer, self.page, self.pages),
            pin=pins[0] if pins else None)

    async def _show(self, interaction: discord.Interaction, page: int) -> None:
        self.page = max(1, min(page, self.pages))
        self._sync()
        self.adopt(interaction)
        await interaction.response.edit_message(
            embed=self.render(), view=self, attachments=[]
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page + 1)

    @discord.ui.button(label="Boards", style=discord.ButtonStyle.secondary)
    async def boards_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PinterestBoardsView(
            invoker_id=self.invoker_id,
            profile=self.profile,
            footer=self.footer,
            page=self.boards_page)
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.embed(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.secondary)
    async def profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PinterestProfileView(
            invoker_id=self.invoker_id, profile=self.profile, footer=self.footer
        )
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.embed(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _close(interaction, self)


class PinterestPinsView(_PinterestView):
    def __init__(
        self,
        *,
        invoker_id: int,
        profile: pinterest.ProfileResult,
        footer: str,
        page: int = 1) -> None:
        super().__init__(invoker_id=invoker_id, footer=footer)
        self.profile = profile
        self.pages = _pages(len(profile.pins), PINS_PER_PAGE)
        self.page = max(1, min(page, self.pages))
        self.profile_button.emoji = emoji_partial("user") or "👤"
        self.close_button.emoji = emoji_partial("crossmark") or "❌"
        self._sync()

    def _sync(self) -> None:
        self.previous_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.pages

    def render(self) -> discord.Embed:
        pins = _slice(self.profile.pins, self.page, PINS_PER_PAGE)
        return pinterest_user_pins_embed(
            self.profile.user,
            page=self.page,
            pages=self.pages,
            loaded=len(self.profile.pins),
            footer=_page_footer(self.footer, self.page, self.pages),
            pin=pins[0] if pins else None)

    async def _show(self, interaction: discord.Interaction, page: int) -> None:
        self.page = max(1, min(page, self.pages))
        self._sync()
        self.adopt(interaction)
        await interaction.response.edit_message(
            embed=self.render(), view=self, attachments=[]
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page + 1)

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.secondary)
    async def profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PinterestProfileView(
            invoker_id=self.invoker_id, profile=self.profile, footer=self.footer
        )
        view.adopt(interaction)
        await interaction.response.edit_message(
            embed=view.embed(), view=view, attachments=[]
        )
        self.stop()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _close(interaction, self)
