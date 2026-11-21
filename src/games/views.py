"""Interactive views for the games cog.

Every view belongs to a single message (nothing here is persistent), so they
are plain `discord.ui.View` subclasses with a short timeout and per-player
interaction checks.
"""

import random
from contextlib import suppress

import discord

from src.games import stats
from core.emojis import markup
from view import (
    ERROR_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    connectfour_embed,
    games_embed,
    hangman_embed,
    tictactoe_embed,
    trivia_embed,
    wyr_embed)

TRIVIA_LETTERS = ("A", "B", "C", "D")

HANGMAN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

TICTACTOE_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6))

RPS_CHOICES = ("rock", "paper", "scissors")
RPS_LABELS = {
    "rock": f"{markup('gamecontroller', '🪨')} Rock",
    "paper": f"{markup('paper', '📄')} Paper",
    "scissors": f"{markup('crossmark', '✂️')} Scissors",
}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


def _rps_winner(first: str, second: str) -> str:
    if first == second:
        return "draw"
    return "first" if RPS_BEATS[first] == second else "second"


class TriviaView(discord.ui.View):
    """One multiple-choice question; only the invoker may answer."""

    def __init__(
        self,
        *,
        bot,
        author_id: int,
        guild_id: int,
        category: str,
        question: str,
        options: list[str],
        answer: int) -> None:
        super().__init__(timeout=45)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.category = category
        self.question = question
        self.options = options
        self.answer = answer
        self.done = False
        self.message: discord.Message | None = None
        for index, option in enumerate(options):
            button = discord.ui.Button(
                label=f"{TRIVIA_LETTERS[index]}. {option}"[:80],
                style=discord.ButtonStyle.primary)
            button.callback = self._on_click(index)
            self.add_item(button)

    def embed(self) -> discord.Embed:
        return trivia_embed(
            question=self.question,
            options=self.options,
            category=self.category)

    def _on_click(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self._answer(interaction, index)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This isn't your trivia round — start your own with `trivia`.",
            ephemeral=True)
        return False

    async def _answer(self, interaction: discord.Interaction, index: int) -> None:
        if self.done:
            await interaction.response.send_message(
                "This round is already over.", ephemeral=True
            )
            return
        self.done = True
        correct = index == self.answer
        for position, child in enumerate(self.children):
            child.disabled = True
            if position == self.answer:
                child.style = discord.ButtonStyle.success
            elif position == index:
                child.style = discord.ButtonStyle.danger

        paid = await stats.award(
            self.bot.db,
            self.guild_id,
            interaction.user.id,
            "trivia",
            stats.TRIVIA_REWARD,
            won=correct)
        embed = trivia_embed(
            question=self.question,
            options=self.options,
            category=self.category,
            answer=self.answer,
            chosen=index,
            color=SUCCESS_COLOR if correct else ERROR_COLOR,
            footer=f"+{paid} coins" if correct else "Better luck next time!")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        if self.done:
            return
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)


class HangmanView(discord.ui.View):
    """Guess the hidden word letter by letter with two select menus."""

    MAX_WRONG = 6

    def __init__(
        self, *, bot, author_id: int, guild_id: int, word: str, hint: str
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.word = word.upper()
        self.hint = hint
        self.guessed: set[str] = set()
        self.wrong = 0
        self.finished = False
        self.message: discord.Message | None = None
        self._build()

    @property
    def display(self) -> str:
        return " ".join(
            letter if letter in self.guessed else "_" for letter in self.word
        )

    def embed(self, *, color=None, footer=None) -> discord.Embed:
        return hangman_embed(
            display=self.display,
            guessed=self.guessed,
            wrong=self.wrong,
            max_wrong=self.MAX_WRONG,
            hint=self.hint,
            color=color,
            footer=footer)

    def _build(self) -> None:
        self.clear_items()
        for row, letters in enumerate(
            (HANGMAN_LETTERS[:13], HANGMAN_LETTERS[13:])
        ):
            remaining = [letter for letter in letters if letter not in self.guessed]
            options = [
                discord.SelectOption(label=letter, value=letter)
                for letter in remaining
            ] or [discord.SelectOption(label="—", value="__none__")]
            select = discord.ui.Select(
                placeholder="Guess a letter",
                min_values=1,
                max_values=1,
                options=options,
                disabled=not remaining,
                row=row)
            select.callback = self._on_guess
            self.add_item(select)

    async def _on_guess(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This isn't your hangman game — run `hangman` to start one.",
                ephemeral=True)
            return
        if self.finished:
            await interaction.response.send_message(
                "This game is already over.", ephemeral=True
            )
            return

        values = interaction.data.get("values") or []
        letter = values[0] if values else None
        if not letter or letter == "__none__" or letter in self.guessed:
            await interaction.response.defer()
            return

        self.guessed.add(letter)
        if letter not in self.word:
            self.wrong += 1

        won = all(letter in self.guessed for letter in self.word)
        lost = self.wrong >= self.MAX_WRONG
        if won or lost:
            self.finished = True
            for child in self.children:
                child.disabled = True
            paid = await stats.award(
                self.bot.db,
                self.guild_id,
                interaction.user.id,
                "hangman",
                stats.HANGMAN_REWARD,
                won=won)
            footer = f"+{paid} coins" if won else f"The word was **{self.word}**."
            embed = self.embed(
                color=SUCCESS_COLOR if won else ERROR_COLOR, footer=footer
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        self._build()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class TicTacToeView(discord.ui.View):
    """Three-in-a-row against the bot (`vs_bot`) or another member."""

    def __init__(
        self,
        *,
        bot,
        guild_id: int,
        x_id: int,
        x_name: str,
        o_id: int,
        o_name: str,
        vs_bot: bool) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.x_id = x_id
        self.x_name = x_name
        self.o_id = o_id
        self.o_name = o_name
        self.vs_bot = vs_bot
        self.board: list[str | None] = [None] * 9
        self.turn = "X"
        self.finished = False
        self.message: discord.Message | None = None
        for index in range(9):
            button = discord.ui.Button(
                label=str(index + 1),
                style=discord.ButtonStyle.secondary,
                row=index // 3)
            button.callback = self._on_click(index)
            self.add_item(button)

    def embed(self, *, result=None, color=None, footer=None) -> discord.Embed:
        turn_name = None
        if result is None:
            turn_name = self.x_name if self.turn == "X" else self.o_name
        return tictactoe_embed(
            board=self.board,
            x_name=self.x_name,
            o_name=self.o_name,
            turn_name=turn_name,
            result=result,
            color=color,
            footer=footer)

    def _on_click(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self._play(interaction, index)

        return callback

    def _outcome(self) -> str | None:
        for first, second, third in TICTACTOE_LINES:
            mark = self.board[first]
            if mark is not None and mark == self.board[second] == self.board[third]:
                return mark
        if all(cell is not None for cell in self.board):
            return "draw"
        return None

    def _bot_move(self) -> int | None:
        empty = [i for i, cell in enumerate(self.board) if cell is None]
        if not empty:
            return None
        for mark in ("O", "X"):
            for index in empty:
                self.board[index] = mark
                wins = self._outcome() == mark
                self.board[index] = None
                if wins:
                    return index
        if 4 in empty:
            return 4
        corners = [i for i in (0, 2, 6, 8) if i in empty]
        if corners:
            return random.choice(corners)
        return random.choice(empty)

    def _sync(self) -> None:
        for index, child in enumerate(self.children):
            mark = self.board[index]
            if mark is None:
                child.label = str(index + 1)
                child.style = discord.ButtonStyle.secondary
            else:
                child.label = markup("crossmark", "❌") if mark == "X" else markup("checkmark", "⭕")
                child.style = (
                    discord.ButtonStyle.danger
                    if mark == "X"
                    else discord.ButtonStyle.success
                )

    async def _finish(self, outcome: str) -> tuple[str, int | None, str | None]:
        if outcome == "draw":
            return "It's a draw!", WARNING_COLOR, "Nobody wins"

        winner_name = self.x_name if outcome == "X" else self.o_name
        if self.vs_bot:
            if outcome == "X":
                paid = await stats.award(
                    self.bot.db,
                    self.guild_id,
                    self.x_id,
                    "tictactoe",
                    stats.TICTACTOE_REWARD,
                    won=True)
                return f"**{winner_name}** wins!", SUCCESS_COLOR, f"+{paid} coins"
            await stats.record(
                self.bot.db, self.guild_id, self.x_id, "tictactoe", won=False
            )
            return f"**{winner_name}** wins!", ERROR_COLOR, "Better luck next time!"

        loser_id = self.o_id if outcome == "X" else self.x_id
        loser_name = self.o_name if outcome == "X" else self.x_name
        winner_id = self.x_id if outcome == "X" else self.o_id
        await stats.record(
            self.bot.db, self.guild_id, winner_id, "tictactoe", won=True
        )
        await stats.record(
            self.bot.db, self.guild_id, loser_id, "tictactoe", won=False
        )
        return f"**{winner_name}** beats **{loser_name}**!", SUCCESS_COLOR, None

    async def _play(self, interaction: discord.Interaction, index: int) -> None:
        if self.finished:
            await interaction.response.send_message(
                "This game has already ended.", ephemeral=True
            )
            return
        if self.board[index] is not None:
            await interaction.response.send_message(
                "That square is already taken.", ephemeral=True
            )
            return

        if self.vs_bot:
            if interaction.user.id != self.x_id:
                await interaction.response.send_message(
                    "This match is against the bot — it's your board.",
                    ephemeral=True)
                return
            self.board[index] = "X"
            outcome = self._outcome()
            if outcome is None:
                bot_index = self._bot_move()
                if bot_index is not None:
                    self.board[bot_index] = "O"
                outcome = self._outcome()
        else:
            current = self.x_id if self.turn == "X" else self.o_id
            if interaction.user.id != current:
                await interaction.response.send_message(
                    "It's not your turn.", ephemeral=True
                )
                return
            self.board[index] = self.turn
            self.turn = "O" if self.turn == "X" else "X"
            outcome = self._outcome()

        if outcome is None:
            self._sync()
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return

        self.finished = True
        for child in self.children:
            child.disabled = True
        result, color, footer = await self._finish(outcome)
        await interaction.response.edit_message(
            embed=self.embed(result=result, color=color, footer=footer), view=self
        )


class ConnectFourView(discord.ui.View):
    """Drop discs into columns against the bot or another member."""

    def __init__(
        self,
        *,
        bot,
        guild_id: int,
        red_id: int,
        red_name: str,
        yellow_id: int,
        yellow_name: str,
        vs_bot: bool) -> None:
        super().__init__(timeout=240)
        self.bot = bot
        self.guild_id = guild_id
        self.red_id = red_id
        self.red_name = red_name
        self.yellow_id = yellow_id
        self.yellow_name = yellow_name
        self.vs_bot = vs_bot
        self.grid: list[list[str | None]] = [[None] * 6 for _ in range(7)]
        self.turn = "X"
        self.finished = False
        self.message: discord.Message | None = None
        for col in range(7):
            button = discord.ui.Button(
                label=str(col + 1), style=discord.ButtonStyle.secondary
            )
            button.callback = self._on_drop(col)
            self.add_item(button)

    def embed(self, *, result=None, color=None, footer=None) -> discord.Embed:
        turn_name = None
        if result is None:
            turn_name = self.red_name if self.turn == "X" else self.yellow_name
        return connectfour_embed(
            grid=self.grid,
            x_name=self.red_name,
            o_name=self.yellow_name,
            turn_name=turn_name,
            result=result,
            color=color,
            footer=footer)

    def _on_drop(self, col: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self._play(interaction, col)

        return callback

    def _free_row(self, col: int) -> int | None:
        for row in range(6):
            if self.grid[col][row] is None:
                return row
        return None

    def _drop(self, col: int, mark: str) -> int | None:
        row = self._free_row(col)
        if row is None:
            return None
        self.grid[col][row] = mark
        return row

    def _winner(self) -> str | None:
        for col in range(7):
            for row in range(6):
                mark = self.grid[col][row]
                if mark is None:
                    continue
                if col + 3 < 7 and all(
                    self.grid[col + i][row] == mark for i in range(4)
                ):
                    return mark
                if row + 3 < 6 and all(
                    self.grid[col][row + i] == mark for i in range(4)
                ):
                    return mark
                if (
                    col + 3 < 7
                    and row + 3 < 6
                    and all(self.grid[col + i][row + i] == mark for i in range(4))
                ):
                    return mark
                if (
                    col + 3 < 7
                    and row - 3 >= 0
                    and all(self.grid[col + i][row - i] == mark for i in range(4))
                ):
                    return mark
        return None

    def _full(self) -> bool:
        return all(self.grid[col][5] is not None for col in range(7))

    def _bot_column(self) -> int | None:
        legal = [col for col in range(7) if self.grid[col][5] is None]
        if not legal:
            return None
        order = (3, 2, 4, 1, 5, 0, 6)
        for mark in ("O", "X"):
            for col in order:
                if col not in legal:
                    continue
                row = self._free_row(col)
                self.grid[col][row] = mark
                wins = self._winner() == mark
                self.grid[col][row] = None
                if wins:
                    return col
        for col in order:
            if col in legal:
                return col
        return None

    async def _finish(self, outcome: str) -> tuple[str, int | None, str | None]:
        if outcome == "draw":
            return "It's a draw — the board is full!", WARNING_COLOR, None

        winner_name = self.red_name if outcome == "X" else self.yellow_name
        if self.vs_bot:
            if outcome == "X":
                paid = await stats.award(
                    self.bot.db,
                    self.guild_id,
                    self.red_id,
                    "connectfour",
                    stats.CONNECT4_REWARD,
                    won=True)
                return f"**{winner_name}** wins!", SUCCESS_COLOR, f"+{paid} coins"
            await stats.record(
                self.bot.db, self.guild_id, self.red_id, "connectfour", won=False
            )
            return f"**{winner_name}** wins!", ERROR_COLOR, "Better luck next time!"

        winner_id = self.red_id if outcome == "X" else self.yellow_id
        loser_id = self.yellow_id if outcome == "X" else self.red_id
        loser_name = self.yellow_name if outcome == "X" else self.red_name
        await stats.record(
            self.bot.db, self.guild_id, winner_id, "connectfour", won=True
        )
        await stats.record(
            self.bot.db, self.guild_id, loser_id, "connectfour", won=False
        )
        return f"**{winner_name}** beats **{loser_name}**!", SUCCESS_COLOR, None

    async def _play(self, interaction: discord.Interaction, col: int) -> None:
        if self.finished:
            await interaction.response.send_message(
                "This game has already ended.", ephemeral=True
            )
            return
        if self.grid[col][5] is not None:
            await interaction.response.send_message(
                "That column is full.", ephemeral=True
            )
            return

        if self.vs_bot:
            if interaction.user.id != self.red_id:
                await interaction.response.send_message(
                    "This match is against the bot — it's your board.",
                    ephemeral=True)
                return
            self._drop(col, "X")
            outcome = self._winner()
            if outcome is None and not self._full():
                bot_col = self._bot_column()
                if bot_col is not None:
                    self._drop(bot_col, "O")
                outcome = self._winner()
        else:
            current = self.red_id if self.turn == "X" else self.yellow_id
            if interaction.user.id != current:
                await interaction.response.send_message(
                    "It's not your turn.", ephemeral=True
                )
                return
            self._drop(col, self.turn)
            self.turn = "O" if self.turn == "X" else "X"
            outcome = self._winner()

        if outcome is None and self._full():
            outcome = "draw"

        if outcome is None:
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return

        self.finished = True
        for child in self.children:
            child.disabled = True
        result, color, footer = await self._finish(outcome)
        await interaction.response.edit_message(
            embed=self.embed(result=result, color=color, footer=footer), view=self
        )


class RPSView(discord.ui.View):
    """Rock-paper-scissors against the bot or another member."""

    def __init__(
        self,
        *,
        bot,
        guild_id: int,
        author_id: int,
        author_name: str,
        opponent_id: int | None,
        opponent_name: str) -> None:
        super().__init__(timeout=90)
        self.bot = bot
        self.guild_id = guild_id
        self.author_id = author_id
        self.author_name = author_name
        self.opponent_id = opponent_id
        self.opponent_name = opponent_name
        self.picks: dict[int, str] = {}
        self.finished = False
        self.message: discord.Message | None = None
        for key in RPS_CHOICES:
            button = discord.ui.Button(
                label=RPS_LABELS[key], style=discord.ButtonStyle.primary
            )
            button.callback = self._on_pick(key)
            self.add_item(button)

    def embed(
        self, *, description: str | None = None, color=None, footer=None
    ) -> discord.Embed:
        if description is None:
            description = (
                "Pick your move — the bot answers instantly."
                if self.opponent_id is None
                else "Both players pick a move; the result appears once you've both chosen."
            )
        return games_embed(
            title=f"{markup('gamecontroller', '✊')} Rock, paper, scissors",
            description=f"**{self.author_name}** vs **{self.opponent_name}**\n\n{description}",
            color=color,
            footer=footer)

    def _on_pick(self, key: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self._choose(interaction, key)

        return callback

    def _disable(self) -> None:
        for child in self.children:
            child.disabled = True

    async def _choose(self, interaction: discord.Interaction, key: str) -> None:
        if self.finished:
            await interaction.response.send_message(
                "This match has already ended.", ephemeral=True
            )
            return
        players = (
            (self.author_id)
            if self.opponent_id is None
            else (self.author_id, self.opponent_id)
        )
        if interaction.user.id not in players:
            await interaction.response.send_message(
                "You're not playing in this match.", ephemeral=True
            )
            return

        if self.opponent_id is None:
            bot_key = random.choice(RPS_CHOICES)
            outcome = _rps_winner(key, bot_key)
            self.finished = True
            self._disable()
            if outcome == "first":
                paid = await stats.award(
                    self.bot.db,
                    self.guild_id,
                    self.author_id,
                    "rps",
                    stats.RPS_REWARD,
                    won=True)
                color, footer, result = SUCCESS_COLOR, f"+{paid} coins", "You win!"
            elif outcome == "second":
                await stats.record(
                    self.bot.db, self.guild_id, self.author_id, "rps", won=False
                )
                color, footer, result = ERROR_COLOR, None, "The bot wins!"
            else:
                color, footer, result = WARNING_COLOR, None, "It's a draw!"
            description = (
                f"You played {RPS_LABELS[key]}, the bot played "
                f"{RPS_LABELS[bot_key]}.\n\n**{result}**"
            )
            await interaction.response.edit_message(
                embed=self.embed(description=description, color=color, footer=footer),
                view=self)
            return

        self.picks[interaction.user.id] = key
        if len(self.picks) < 2:
            await interaction.response.send_message(
                f"You picked {RPS_LABELS[key]}. Waiting for your opponent…",
                ephemeral=True)
            return

        first = self.picks[self.author_id]
        second = self.picks[self.opponent_id]
        self.finished = True
        self._disable()
        outcome = _rps_winner(first, second)
        reveal = (
            f"{self.author_name} played {RPS_LABELS[first]}, "
            f"{self.opponent_name} played {RPS_LABELS[second]}.\n\n"
        )
        if outcome == "draw":
            await interaction.response.edit_message(
                embed=self.embed(
                    description=reveal + "**It's a draw!**", color=WARNING_COLOR
                ),
                view=self)
            return
        if outcome == "first":
            winner_id, winner_name = self.author_id, self.author_name
            loser_id = self.opponent_id
        else:
            winner_id, winner_name = self.opponent_id, self.opponent_name
            loser_id = self.author_id
        await stats.record(
            self.bot.db, self.guild_id, winner_id, "rps", won=True
        )
        await stats.record(
            self.bot.db, self.guild_id, loser_id, "rps", won=False
        )
        await interaction.response.edit_message(
            embed=self.embed(
                description=reveal + f"**{winner_name} wins!**", color=SUCCESS_COLOR
            ),
            view=self)


class WouldYouRatherView(discord.ui.View):
    """Two buttons that tally votes for the message's lifetime."""

    def __init__(self, *, option_a: str, option_b: str) -> None:
        super().__init__(timeout=300)
        self.option_a = option_a
        self.option_b = option_b
        self.votes: dict[str, set[int]] = {"a": set(), "b": set()}
        self.message: discord.Message | None = None
        self.first.label = f"A) {option_a}"[:80]
        self.second.label = f"B) {option_b}"[:80]

    def embed(self) -> discord.Embed:
        return wyr_embed(
            option_a=self.option_a,
            option_b=self.option_b,
            votes_a=len(self.votes["a"]),
            votes_b=len(self.votes["b"]))

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def first(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._vote(interaction, "a")

    @discord.ui.button(label="B", style=discord.ButtonStyle.danger)
    async def second(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._vote(interaction, "b")

    async def _vote(self, interaction: discord.Interaction, key: str) -> None:
        other = "b" if key == "a" else "a"
        self.votes[key].add(interaction.user.id)
        self.votes[other].discard(interaction.user.id)
        await interaction.response.edit_message(embed=self.embed(), view=self)


__all__ = [
    "ConnectFourView",
    "HangmanView",
    "RPSView",
    "TicTacToeView",
    "TriviaView",
    "WouldYouRatherView",
]
