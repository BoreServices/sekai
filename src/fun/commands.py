import random
import re
import unicodedata
import zlib

import discord
from discord.ext import commands

from config.owners import OWNER_IDS
from view import dih_embed, fun_meter_embed

# Command name -> (embed title, emoji). Add an entry here and the command
# registers itself, shows up on the Fun help page and behaves the same way.
METERS: dict[str, tuple[str, str]] = {
    "howgay": ("How gay", "🌈"),
    "howlesbian": ("How lesbian", "🌈"),
    "howfurry": ("How furry", "🐾"),
    "howfemboy": ("How femboy", "🎀"),
    "howsimp": ("How simp", "💸"),
    "howcute": ("How cute", "🥺"),
    "howsmart": ("How smart", "🧠"),
    "howdumb": ("How dumb", "🪨"),
    "howrich": ("How rich", "💰"),
    "howdrunk": ("How drunk", "🍺"),
    "howevil": ("How evil", "😈"),
    "howcat": ("How cat", "🐱"),
    "howdog": ("How dog", "🐶"),
}

# Command name -> member ID -> score, for people who always get the joke number
# no matter what. Everybody else keeps their normal roll.
FIXED: dict[str, dict[int, int]] = {
    "howgay": {1482241459343065088: 999999999999999999999999},
    "howfemboy": {1482241459343065088: 999999999999999999999999},
    "howgay": {1539448518354272308: 9999999999999999999999999999999},
    "howdumb": {1546968812522311703: 0}
}

# The dih command measures in inches. Members listed in config/owners.py
# get OWNER_BOOST on top, which is what pushes them past the normal ceiling.
BASE_MAX = 12
OWNER_BOOST = 50
MAX_SIZE = BASE_MAX + OWNER_BOOST

VERDICTS: list[tuple[int, str]] = [
    (0, "Nothing down there — it's an innie."),
    (2, "It's… there. Technically."),
    (4, "A grower, not a shower."),
    (6, "Perfectly average. Nothing to write home about."),
    (8, "Solid. Respectable, even."),
    (10, "Impressive — you've been blessed."),
    (12, "An absolute unit. Handle with care."),
    (MAX_SIZE, "DAMNNNNNNNNNNNNNNN"),
]


def _roll(key: str, user_id: int, span: int) -> int:
    """Stable number for a member, so re-running a command repeats the result."""
    return zlib.crc32(f"{key}:{user_id}".encode()) % (span + 1)


def _verdict(size: int) -> str:
    for limit, text in VERDICTS:
        if size <= limit:
            return text
    return VERDICTS[-1][1]


# Anyone who says 67 gets roasted, and so does anyone hiding behind an
# invisible nickname. Only pings and links are spared: everything else people
# hide the digits in (markdown, zero-width characters, keycap emoji, spaces or
# punctuation between the 6 and the 7, "six seven") still counts, so there is
# no way to slip past the roast.
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"<@[!&]?\d+>|<#\d+>|<a?:\w+:\d+>", re.IGNORECASE)
INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad\ufe0f\u20e3]")
# Everything people stick between the 6 and the 7 to break the match.
SPLIT_67_RE = re.compile(
    r"(?<!\w)6[\s\-.+,;:!?/\\|*_~`'\"()\[\]{}<>^=@#$%&]+7(?!\w)"
)
SIXTY_SEVEN_WORD_RE = re.compile(r"\bsixty[-\s]*seven\b", re.IGNORECASE)
SIX_RE = re.compile(r"\bsix\b", re.IGNORECASE)
SEVEN_RE = re.compile(r"\bseven\b", re.IGNORECASE)
SIXTY_SEVEN_RE = re.compile(r"(?<!\w)67(?!\w)")

ROASTS: list[str] = [
    "you typed **67** and every braincell you own clocked out for lunch",
    "**67**? your parents' disappointment just got a sequel",
    "nobody asked, nobody cares, and you still typed **67**",
    "your whole personality is two numbers and neither of them is impressive",
    "you are the reason this server needs a slowmode",
    "**67** from you hits different — like a participation trophy for being useless",
    "imagine being so boring that **67** is your entire material",
    "I would roast you harder, but your ego already got deleted with your last message",
    "you say **67** because it's the only thing you can get right",
    "even my error logs contribute more than your **67**",
    "**67** — the only thing you commit to, and you still can't do it properly",
    "you are a load-bearing nothing with a keyboard",
    "if being annoying were a competition, **67** would be your trophy",
    "your presence in this chat is a bug nobody can patch",
    "**67** is the mating call of someone with nothing else to offer",
    "you bring **67** and vibes of failure. pick a struggle.",
    "the confidence in that **67** is the only impressive thing about you",
    "I wish your typing privileges came with a captcha",
    "you would lose a battle of wits to a rock, and the rock says nothing",
    "**67** again? that is not a personality, that is a symptom",
    "you typed **67** so confidently for someone with no hobbies and no friends",
    "the bar was on the floor and your **67** still managed to dig under it",
]

# Blank / zero-width characters people pad their nickname with so it renders as
# nothing (or goes invisible) in chat.
NAME_INVISIBLE_RE = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e"
    "\u200b\u200c\u200e\u200f\u2028-\u202f\u2060-\u2064\u206a-\u206f"
    "\u2800\u3000\u3164\ufeff\uffa0"
    "\u00a0\u1680\u2000-\u200a\u205f"
    "\ufe00-\ufe0f\U000e0100-\U000e01ef"
    "\U000e0000-\U000e007f"
    "\U000f0000-\U000fffff"
    "\ufffd]"
)
# Zalgo: a stack of combining marks piled on a letter until nobody can read it.
COMBINING_RE = re.compile(
    "[\u0300-\u036f\u0483-\u0489\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20f0"
    "\ufe20-\ufe2f]"
)

# --- Additional Exploits Detection ---

# RTL Spoofing / Directional Overrides (prevents text reversal and visual spoofing attacks)
RTL_SPOOFING_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")

# Common Homoglyphs (Latin characters spoofed using Cyrillic/Greek lookalikes)
# Example: Cyrillic 'а' (U+0430) instead of Latin 'a' (U+0061)
HOMOGLYPH_RE = re.compile(
    "[\u0430\u043e\u0455\u0456\u0458\u0441\u0440\u0445]"
)

NAME_ROASTS: list[str] = [
    "your name is invisible because even you know nobody wants to read it",
    "you made your name unreadable so nobody can ping you when they need someone useful",
    "hiding behind invisible characters is the most effort you have ever put into anything",
    "your name is blank space and your personality got there first",
    "even your nickname is trying to leave the conversation",
    "your name renders as nothing — finally, some honesty",
    "invisible name, invisible impact, invisible skill",
    "you made yourself unreadable just to feel something",
    "your entire identity is a bug in the text renderer",
    "you stacked invisible characters instead of getting a personality",
    "nobody can read you and nobody wants to, so the invisible name is on brand",
    "you are so irrelevant you had to hide your own name to get noticed",
]


def _plain(content: str) -> str:
    """Message text with pings and links removed, plus the usual hiding tricks."""
    text = unicodedata.normalize("NFKC", content)
    text = URL_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = INVISIBLE_RE.sub("", text)
    text = SIXTY_SEVEN_WORD_RE.sub("67", text)
    text = SIX_RE.sub("6", text)
    return SEVEN_RE.sub("7", text)


def _said_67(text: str) -> bool:
    """True for a plain 67, and for the 6 7 people space or punctuate apart."""
    return (
        SIXTY_SEVEN_RE.search(text) is not None
        or SPLIT_67_RE.search(text) is not None
    )


def _hidden_name(member: discord.abc.User) -> bool:
    """True when a nickname is padded with invisible junk, spoofed with RTL
    overrides or homoglyphs, or buried under stacked zalgo."""
    for name in (member.display_name, member.name):
        if not name:
            continue
        if NAME_INVISIBLE_RE.search(name):
            return True
        if RTL_SPOOFING_RE.search(name):
            return True
        if HOMOGLYPH_RE.search(name):
            return True
        marks = len(COMBINING_RE.findall(name))
        if marks >= 5 and marks > len(name) / 2:
            return True
    return False


def _register_meter(bot, name: str, label: str, icon: str) -> None:
    noun = label.removeprefix("How ")

    @bot.command(
        name=name,
        help=(
            f"Measures how {noun} the member is. Just for fun — the same "
            "person always scores the same."
        ),
        usage=f"{name} [member]")
    @commands.guild_only()
    async def meter(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        percent = FIXED.get(name, {}).get(target.id)
        if percent is None:
            percent = _roll(name, target.id, 100)
        await ctx.send(
            embed=fun_meter_embed(
                user=target,
                label=label,
                icon=icon,
                percent=percent)
        )


def setup(bot) -> None:
    for name, (label, icon) in METERS.items():
        _register_meter(bot, name, label, icon)

    @bot.listen("on_message")
    async def _roast_offenders(message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        hidden = _hidden_name(message.author)
        if _said_67(_plain(message.content)):
            roast = random.choice(ROASTS)
        elif hidden:
            roast = random.choice(NAME_ROASTS)
        else:
            return
        # An invisible nickname would print as nothing, so ping them instead.
        who = message.author.mention if hidden else f"**{message.author.display_name}**"
        await message.reply(f"{who}, {roast}")

    @bot.command(
        name="dih",
        help=(
            "Runs the very scientific dih meter on a member."
        ),
        usage="dih [member]")
    @commands.guild_only()
    async def dih(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        size = _roll("dih", target.id, BASE_MAX)
        if target.id in OWNER_IDS:
            size = min(size + OWNER_BOOST, MAX_SIZE)
        await ctx.send(
            embed=dih_embed(
                user=target,
                size=size,
                maximum=MAX_SIZE,
                verdict=_verdict(size))
        )
