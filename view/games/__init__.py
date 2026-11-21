"""Embeds for the games cog."""

import discord

from view.base import ERROR_COLOR, INFO_COLOR, SUCCESS_COLOR, base_embed, brand

TRIVIA_LETTERS = ("A", "B", "C", "D")

# Indexed by wrong guesses, 0 through 6.
HANGMAN_STAGES = [
    "  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========",
    "  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========",
]

TICTACTOE_MARKS = {"X": "❌", "O": "⭕"}
CONNECT_MARKS = {None: "⚫", "X": "🔴", "O": "🟡"}
COLUMN_LABELS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣")


def games_embed(
    *,
    title: str,
    description: str | None = None,
    fields: list[tuple[str, str, bool]] = (),
    footer: str | None = None,
    color: int | discord.Color | None = None) -> discord.Embed:
    embed = base_embed(title=title, description=description, color=color)
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    return brand(embed, footer=footer)


def trivia_embed(
    *,
    question: str,
    options: list[str],
    category: str,
    answer: int | None = None,
    chosen: int | None = None,
    color: int | None = None,
    footer: str | None = None) -> discord.Embed:
    lines = []
    for index, option in enumerate(options):
        marker = ""
        if answer is not None:
            if index == answer:
                marker = " ✅"
            elif index == chosen:
                marker = " ❌"
        lines.append(f"**{TRIVIA_LETTERS[index]}.** {option}{marker}")

    embed = base_embed(
        title=f"❓ {category.title()} trivia",
        description=f"{question}\n\n" + "\n".join(lines),
        color=color if color is not None else INFO_COLOR)
    return brand(embed, footer=footer)


def hangman_embed(
    *,
    display: str,
    guessed: set[str],
    wrong: int,
    max_wrong: int,
    hint: str,
    color: int | None = None,
    footer: str | None = None) -> discord.Embed:
    art = HANGMAN_STAGES[min(wrong, max_wrong)]
    embed = base_embed(
        title="🪢 Hangman",
        description=f"```\n{art}\n```\n`{display}`",
        color=color if color is not None else INFO_COLOR)
    embed.add_field(name="Hint", value=hint, inline=True)
    embed.add_field(name="Lives", value=f"{max_wrong - wrong} left", inline=True)
    embed.add_field(
        name="Guessed",
        value=", ".join(sorted(guessed)) or "—",
        inline=False)
    return brand(embed, footer=footer)


def tictactoe_embed(
    *,
    board: list[str | None],
    x_name: str,
    o_name: str,
    turn_name: str | None = None,
    result: str | None = None,
    color: int | None = None,
    footer: str | None = None) -> discord.Embed:
    rows = []
    for row in range(3):
        cells = [
            TICTACTOE_MARKS.get(board[row * 3 + col], str(row * 3 + col + 1))
            for col in range(3)
        ]
        rows.append("  ".join(cells))

    embed = base_embed(
        title="⭕ Tic-tac-toe",
        description="\n".join(rows),
        color=color if color is not None else INFO_COLOR)
    embed.add_field(name="❌ X", value=x_name, inline=True)
    embed.add_field(name="⭕ O", value=o_name, inline=True)
    if result:
        embed.add_field(name="Result", value=result, inline=False)
    elif turn_name:
        embed.add_field(name="Turn", value=turn_name, inline=False)
    return brand(embed, footer=footer)


def connectfour_embed(
    *,
    grid: list[list[str | None]],
    x_name: str,
    o_name: str,
    turn_name: str | None = None,
    result: str | None = None,
    color: int | None = None,
    footer: str | None = None) -> discord.Embed:
    rows = [
        " ".join(CONNECT_MARKS[grid[col][row]] for col in range(7))
        for row in reversed(range(6))
    ]
    rows.append(" ".join(COLUMN_LABELS))

    embed = base_embed(
        title="🔴 Connect Four",
        description="\n".join(rows),
        color=color if color is not None else INFO_COLOR)
    embed.add_field(name="🔴 Red", value=x_name, inline=True)
    embed.add_field(name="🟡 Yellow", value=o_name, inline=True)
    if result:
        embed.add_field(name="Result", value=result, inline=False)
    elif turn_name:
        embed.add_field(name="Turn", value=turn_name, inline=False)
    return brand(embed, footer=footer)


def wyr_embed(
    *,
    option_a: str,
    option_b: str,
    votes_a: int,
    votes_b: int,
    footer: str | None = None) -> discord.Embed:
    embed = base_embed(
        title="🤔 Would you rather…",
        description="Vote below — you can change your mind any time.",
        color=INFO_COLOR)
    embed.add_field(
        name=f"A) {option_a}"[:256],
        value=f"**{votes_a}** vote{'s' if votes_a != 1 else ''}",
        inline=True)
    embed.add_field(
        name=f"B) {option_b}"[:256],
        value=f"**{votes_b}** vote{'s' if votes_b != 1 else ''}",
        inline=True)
    return brand(embed, footer=footer)


__all__ = [
    "COLUMN_LABELS",
    "CONNECT_MARKS",
    "ERROR_COLOR",
    "HANGMAN_STAGES",
    "INFO_COLOR",
    "SUCCESS_COLOR",
    "TICTACTOE_MARKS",
    "TRIVIA_LETTERS",
    "connectfour_embed",
    "games_embed",
    "hangman_embed",
    "tictactoe_embed",
    "trivia_embed",
    "wyr_embed",
]
