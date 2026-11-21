import logging
import math
from contextlib import suppress

import discord
from discord.ext import commands

from config.owners import OWNER_IDS
from config.settings import settings
from core import music, prefix as prefixes
from core.emojis import emoji_partial, iconize, markup
from view import command_usage_embed, error_embed, help_embed

log = logging.getLogger("sekai.help")

CATEGORY_ORDER = [
    "general",
    "misc",
    "moderation",
    "antinuke",
    "automod",
    "honeypot",
    "verification",
    "levels",
    "economy",
    "shop",
    "info",
    "welcome",
    "reactionroles",
    "giveaways",
    "starboard",
    "tags",
    "suggestion",
    "utility",
    "pinterest",
    "minecraft",
    "roblox",
    "social",
    "nsfw",
    "games",
    "fun",
    "music",
    "tempvoice",
    "tickets",
    "owner",
]
CATEGORY_LABELS = {
    "general": "General",
    "misc": "Misc",
    "moderation": "Moderation",
    "antinuke": "Antinuke",
    "automod": "Automod",
    "honeypot": "Honeypot",
    "verification": "Verification",
    "levels": "Levels",
    "economy": "Economy",
    "shop": "Shop",
    "info": "Info",
    "welcome": "Welcome",
    "reactionroles": "Reaction Roles",
    "giveaways": "Giveaways",
    "starboard": "Starboard",
    "tags": "Tags",
    "suggestion": "Suggestions",
    "utility": "Utility",
    "pinterest": "Pinterest",
    "minecraft": "Minecraft",
    "roblox": "Roblox",
    "social": "Social",
    "nsfw": "NSFW",
    "games": "Games",
    "fun": "Fun",
    "music": "Music",
    "tempvoice": "Temp Voice",
    "tickets": "Tickets",
    "owner": "Owner",
}
CATEGORY_BLURBS = {
    "general": "Everyday utilities.",
    "misc": "Smaller cogs, AI chat, prefix, logging setup and this help menu.",
    "moderation": "Kick, ban, time out and keep channels clean.",
    "antinuke": "Punish anyone who mass-bans, mass-deletes or adds bots.",
    "automod": "Automatically remove invites, links, mention spam, message floods and smoking/drug talk.",
    "honeypot": "Trap channels that instantly punish raid bots and self-bots the moment they post.",
    "verification": "Website verification with expiry and custom domains, join gating and raid alerts.",
    "levels": "Earn XP by chatting, climb the leaderboard and set server-wide XP boosts.",
    "economy": "Earn, gamble and trade coins, with a server leaderboard.",
    "shop": "Spend coins on roles and XP boosts, then manage your inventory.",
    "info": "Look up the bot, users, servers, roles and channels.",
    "welcome": "Greet new members with custom cards, say goodbye and assign an autorole.",
    "reactionroles": "Hand out roles when members react to a message.",
    "giveaways": "Button-based giveaways with automatic winners.",
    "starboard": "Repost the messages your members star the most.",
    "tags": "Save and recall reusable snippets with a trigger word.",
    "suggestion": "Collect ideas from members and let staff approve or deny them.",
    "utility": "AFK status and reminders.",
    "pinterest": "Look up Pinterest profiles, boards and pins.",
    "minecraft": "Look up players, skins, capes and server status.",
    "roblox": "Look up players, avatars and profile stats.",
    "social": "Hug, pat and cuddle with random gifs, plus cute animal pictures.",
    "nsfw": "Age-restricted PurrBot pictures — only usable in NSFW channels.",
    "games": "Mini-games you can play against the bot or each other.",
    "fun": "Silly meters, random verdicts and the very scientific dih meter.",
    "music": "Playback controls for your voice channel.",
    "tempvoice": "Join-to-create voice channels that clean themselves up.",
    "tickets": "Private support tickets with staff claims and transcripts.",
    "owner": "Bot-owner tools: restart, kill, server invites and the dev01 role.",
}
CATEGORY_EMOJIS = {
    "overview": "📖",
    "general": "🧰",
    "misc": "🧩",
    "moderation": "🛡️",
    "antinuke": "🚨",
    "automod": "🛡️",
    "honeypot": "🍯",
    "verification": "🔐",
    "levels": "🏆",
    "economy": "💰",
    "shop": "🛒",
    "info": "📊",
    "welcome": "👋",
    "reactionroles": "🎭",
    "giveaways": "🎉",
    "starboard": "⭐",
    "tags": "🏷️",
    "suggestion": "📝",
    "utility": "⏳",
    "pinterest": "📌",
    "minecraft": "🖥️",
    "roblox": "🎮",
    "social": "💞",
    "nsfw": "🔞",
    "games": "🎮",
    "fun": "🥳",
    "music": "🎵",
    "tempvoice": "🔊",
    "tickets": "🎫",
    "owner": "👑",
}
# Paste real custom emoji markup here to override the entries above, e.g.
#   "gamecontroller": "<:gamecontroller:1566486121582567434>",
# Used verbatim in embed titles and parsed for the dropdown's select options,
# so both agree. Anything that is not valid custom-emoji markup is ignored and
# the Unicode/app-emoji entry above is used instead.
CATEGORY_EMOJIS_CUSTOM: dict[str, str] = {}
CATEGORY_EMOJI_NAMES = {
    "overview": "paper",
    "general": "wrench",
    "misc": "wrench",
    "moderation": "shield",
    "antinuke": "shield",
    "automod": "shield",
    "honeypot": "honeypot",
    "verification": "checkmark",
    "levels": "crown",
    "economy": "moneybag",
    "shop": "shoppingcart",
    "info": "settings",
    "welcome": "slightlysmilingface",
    "reactionroles": "user",
    "giveaways": "confetti",
    "starboard": "star",
    "tags": "paper",
    "suggestion": "paper",
    "utility": "timer",
    "pinterest": "pin",
    "minecraft": "server",
    "roblox": "user",
    "social": "slightlysmilingface",
    "nsfw": "warning",
    "games": "gamecontroller",
    "fun": "confetti",
    "music": "music",
    "tempvoice": "music",
    "tickets": "ticket",
    "owner": "crown",
}
DEFAULT_EMOJI = "🧰"
FIELD_CHUNK = 24
# Discord caps a string select at 25 options, so the category dropdown is
# paginated: each page shows at most this many categories and the rest are
# reachable with the category arrows. Without this, a 26th category makes
# Discord reject the whole help message (400) and nothing renders.
CATEGORY_CHUNK = 25
MIN_CATEGORY_COMMANDS = 5


def _category(command: commands.Command) -> str:
    parts = command.callback.__module__.split(".")
    if len(parts) >= 3 and parts[0] == "src":
        return parts[1]
    return "other"


def _usage(command: commands.Command) -> str:
    return getattr(command, "usage", None) or command.qualified_name


def _custom_partial(key: str) -> discord.PartialEmoji | None:
    """A CATEGORY_EMOJIS_CUSTOM entry as a PartialEmoji, for the select menu.

    Select options need a real PartialEmoji rather than raw markup, so an entry
    that does not parse into a custom emoji is ignored.
    """
    raw = CATEGORY_EMOJIS_CUSTOM.get(key)
    if not raw:
        return None
    partial = discord.PartialEmoji.from_str(raw.strip())
    return partial if partial.id is not None else None


def _category_icon(key: str) -> str:
    """Embed-title emoji: custom markup first, then app emoji, then Unicode."""
    partial = _custom_partial(key)
    if partial is not None:
        return str(partial)
    return markup(
        CATEGORY_EMOJI_NAMES.get(key, "wrench"),
        CATEGORY_EMOJIS.get(key, DEFAULT_EMOJI))


def _entries(commands_list: list[commands.Command]) -> list[commands.Command]:
    entries: list[commands.Command] = []
    for command in commands_list:
        if isinstance(command, commands.Group):
            entries.extend(sorted(command.commands, key=lambda sub: sub.name))
        else:
            entries.append(command)
    return entries


def _grouped(bot) -> tuple[dict[str, list[commands.Command]], list[str]]:
    grouped: dict[str, list[commands.Command]] = {}
    for command in bot.commands:
        grouped.setdefault(_category(command), []).append(command)
    for commands_list in grouped.values():
        commands_list.sort(key=lambda command: command.name)

    # Cogs too small for their own page belong in Misc instead.
    merged = grouped.pop("misc", [])
    for key in list(grouped):
        # Suggestions are small but deserve their own page.
        if key == "suggestion":
            continue
        if len(_entries(grouped[key])) < MIN_CATEGORY_COMMANDS:
            merged.extend(grouped.pop(key))
    if merged:
        merged.sort(key=lambda command: command.name)
        grouped["misc"] = merged

    keys = [key for key in CATEGORY_ORDER if key in grouped]
    keys += sorted(key for key in grouped if key not in CATEGORY_ORDER)
    return grouped, ["overview", *keys]


async def _is_bot_owner(bot, user) -> bool:
    """Same rule as the owner commands: OWNER_IDS or the application owner."""
    if user.id in OWNER_IDS:
        return True
    try:
        return await bot.is_owner(user)
    except discord.HTTPException:
        return False


def _uptime(bot) -> str:
    total = int((discord.utils.utcnow() - bot.start_time).total_seconds())
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


class HelpView(discord.ui.View):
    def __init__(
        self,
        bot,
        user: discord.User | discord.Member,
        command_prefix: str,
        grouped: dict[str, list[commands.Command]],
        keys: list[str]) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.command_prefix = command_prefix
        self.grouped = grouped
        self.keys = keys
        self.page = 0
        self.subpage = 0
        self.category_page = 0
        self.category_pages = max(1, math.ceil(len(keys) / CATEGORY_CHUNK))
        self.message: discord.Message | None = None
        self.select = CategorySelect(self)
        self.add_item(self.select)
        self.prev_page = discord.ui.Button(
            label="Previous", style=discord.ButtonStyle.secondary, disabled=True, row=1
        )
        self.prev_page.callback = self._previous_subpage
        self.next_page = discord.ui.Button(
            label="Next", style=discord.ButtonStyle.secondary, disabled=True, row=1
        )
        self.next_page.callback = self._next_subpage
        # Category arrows only appear when the dropdown spans more than one page.
        self.prev_category = discord.ui.Button(
            label="◂ Categories", style=discord.ButtonStyle.secondary, row=1
        )
        self.prev_category.callback = self._previous_categories
        self.next_category = discord.ui.Button(
            label="Categories ▸", style=discord.ButtonStyle.secondary, row=1
        )
        self.next_category.callback = self._next_categories
        if self.category_pages > 1:
            self.add_item(self.prev_category)
            self.add_item(self.next_category)
            self._sync_category_pager()

    async def _previous_categories(self, interaction: discord.Interaction) -> None:
        self.category_page = max(0, self.category_page - 1)
        self.select.rebuild()
        self._sync_category_pager()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def _next_categories(self, interaction: discord.Interaction) -> None:
        self.category_page = min(self.category_pages - 1, self.category_page + 1)
        self.select.rebuild()
        self._sync_category_pager()
        await interaction.response.edit_message(embed=self.render(), view=self)

    def _sync_category_pager(self) -> None:
        self.prev_category.disabled = self.category_page == 0
        self.next_category.disabled = self.category_page >= self.category_pages - 1

    async def _previous_subpage(self, interaction: discord.Interaction) -> None:
        self.subpage = max(0, self.subpage - 1)
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def _next_subpage(self, interaction: discord.Interaction) -> None:
        self.subpage += 1
        await interaction.response.edit_message(embed=self.render(), view=self)

    def _sync_pager(self, pages: int) -> None:
        # Discord caps embeds at 25 fields, so big categories get their own pages.
        needed = pages > 1
        present = self.prev_page in self.children
        if needed and not present:
            self.add_item(self.prev_page)
            self.add_item(self.next_page)
        elif not needed and present:
            self.remove_item(self.prev_page)
            self.remove_item(self.next_page)
        if needed:
            self.prev_page.disabled = self.subpage == 0
            self.next_page.disabled = self.subpage >= pages - 1

    @property
    def total(self) -> int:
        return len(self.keys)

    def _icon(self) -> str | None:
        return self.bot.user.display_avatar.url if self.bot.user else None

    def _command_list(self, commands_list: list[commands.Command]) -> list[str]:
        lines = []
        for command in _entries(commands_list):
            usage = f"{self.command_prefix}{_usage(command)}"
            help_text = command.help or "No description."
            lines.append(f"`{usage}` — {help_text}")
        return lines

    @staticmethod
    def _chunk_lines(lines: list[str], limit: int = 1000) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for line in lines:
            extra = len(line) + 1
            if current and size + extra > limit:
                chunks.append("\n".join(current))
                current = [line]
                size = extra
            else:
                current.append(line)
                size += extra
        if current:
            chunks.append("\n".join(current))
        return chunks or ["No commands."]

    def _overview(self) -> tuple[str, str, list[tuple[str, str]]]:
        guilds = len(self.bot.guilds)
        members = sum(guild.member_count or 0 for guild in self.bot.guilds)
        latency = round(self.bot.latency * 1000) if math.isfinite(self.bot.latency) else 0
        command_count = sum(
            len(_entries(commands_list)) for commands_list in self.grouped.values()
        )
        category_count = max(len(self.keys) - 1, 0)
        default_prefix = prefixes.default_prefix(self.bot)

        title = f"{_category_icon('overview')} {settings.bot_name} Help"
        description = (
            f"Use the category menu below to browse commands.\n"
            f"Need details? Run `{self.command_prefix}help <command>`."
        )
        fields = [
            (
                "At a glance",
                (
                    f"• Prefix (this server): `{self.command_prefix}`\n"
                    f"• Default prefix: `{default_prefix}`\n"
                    f"• Categories: `{category_count}`\n"
                    f"• Commands: `{command_count}`"
                ),
            ),
            (
                "Bot status",
                (
                    f"• Servers: `{guilds:,}`\n"
                    f"• Members: `{members:,}`\n"
                    f"• Latency: `{latency} ms`\n"
                    f"• Uptime: `{_uptime(self.bot)}`"
                ),
            ),
            (
                "Links",
                f"[Website]({settings.website_url}) • [Community]({settings.invite_url})",
            ),
        ]
        return title, description, fields

    def render(self, index: int | None = None) -> discord.Embed:
        if index is not None:
            self.page = index

        key = self.keys[self.page]
        pages = 1
        fields: list[tuple[str, str]] = []
        if key == "overview":
            title, description, fields = self._overview()
        else:
            commands_list = self.grouped[key]
            label = CATEGORY_LABELS.get(key, key.title())
            icon = _category_icon(key)
            entries = _entries(commands_list)
            title = f"{icon} {label}"
            lines = self._command_list(commands_list)
            chunks = self._chunk_lines(lines)
            if key == "music":
                status = music.music_status()
                players = status.get("players", 0)
                nodes = len(status.get("available", []))
                chunks.append(f"NodeLink: {nodes} node(s) online • {players} active player(s)")
            pages = max(1, len(chunks))
            self.subpage = min(self.subpage, pages - 1)
            blurb = CATEGORY_BLURBS.get(key, "Commands in this category.")
            meta = f"**Commands:** {len(entries)}"
            if pages > 1:
                meta += f" • part {self.subpage + 1}/{pages}"
            description = f"> {blurb}\n\n{meta}\n\n{chunks[self.subpage]}"
        self._sync_pager(pages)

        return help_embed(
            title=title,
            description=description,
            fields=fields,
            page=self.page + 1,
            pages=self.total,
            prefix=self.command_prefix,
            icon_url=self._icon())

    async def show(self, interaction: discord.Interaction, value: str) -> None:
        index = self.keys.index(value)
        self.subpage = 0
        embed = self.render(index)
        self.select.rebuild()
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user.id:
            return True
        await interaction.response.send_message(
            f"{markup('crossmark', '❌')} This help menu isn't yours — "
            f"run `{self.command_prefix}help` to open your own.",
            ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)


class CategorySelect(discord.ui.Select):
    def __init__(self, menu: HelpView) -> None:
        self.menu = menu
        super().__init__(
            placeholder="Choose a category…",
            min_values=1,
            max_values=1,
            options=[],
            row=0)
        self.rebuild()

    def rebuild(self) -> None:
        """(Re)build the options for the current dropdown page (≤25)."""
        menu = self.menu
        start = menu.category_page * CATEGORY_CHUNK
        chunk = menu.keys[start : start + CATEGORY_CHUNK]
        current = menu.keys[menu.page]
        options = []
        for value in chunk:
            if value == "overview":
                label = "Overview"
                description = "Stats, links and how to use the bot"
            else:
                label = (
                    f"{CATEGORY_LABELS.get(value, value.title())} "
                    f"({len(_entries(menu.grouped[value]))})"
                )
                description = CATEGORY_BLURBS.get(value, "Commands in this category")
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    emoji=_custom_partial(value)
                    or emoji_partial(CATEGORY_EMOJI_NAMES.get(value, "wrench"))
                    or CATEGORY_EMOJIS.get(value, DEFAULT_EMOJI),
                    default=value == current)
            )
        self.options = options
        if menu.category_pages > 1:
            end = start + len(chunk)
            self.placeholder = (
                f"Categories {start + 1}–{end} of {len(menu.keys)} — pick one"
            )
        else:
            self.placeholder = "Choose a category…"

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.menu.show(interaction, self.values[0])


def setup(bot) -> None:
    @bot.command(
        name="help",
        help="Open the command menu, or show a command's format and example.",
        usage="help [command]",
        extras={"example": "help ticket setup"})
    async def help_command(
        ctx: commands.Context, *, command: str | None = None
    ) -> None:
        if ctx.guild is None:
            command_prefix = prefixes.default_prefix(bot)
        else:
            command_prefix = await prefixes.get_guild_prefix(bot, ctx.guild.id)

        if command is not None:
            found = bot.get_command(command.strip())
            if (
                found is not None
                and _category(found) == "owner"
                and not await _is_bot_owner(bot, ctx.author)
            ):
                found = None
            if found is None:
                await ctx.send(
                    embed=error_embed(
                        f"No command called `{discord.utils.escape_markdown(command.strip())}`"
                        f" — run `{command_prefix}help` to browse them all."
                    )
                )
                return
            await ctx.send(
                embed=command_usage_embed(found, prefix=command_prefix)
            )
            return

        grouped, keys = _grouped(bot)
        if not await _is_bot_owner(bot, ctx.author):
            keys = [key for key in keys if key != "owner"]
            grouped.pop("owner", None)

        menu = HelpView(bot, ctx.author, command_prefix, grouped, keys)
        menu.message = await ctx.send(embed=menu.render(0), view=menu)
