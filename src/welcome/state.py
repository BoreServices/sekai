from dataclasses import dataclass
from pathlib import Path

import discord

from config.settings import settings
from view.base import ERROR_COLOR, SUCCESS_COLOR

DEFAULT_WELCOME = "Welcome {user} to **{server}**! You're member #{count}."
DEFAULT_LEAVE = "**{name}** left **{server}**. We're now at {count} members."
MAX_MESSAGE = 1500
BACKGROUND_DIR = settings.emoji_dir.parent / "data" / "welcome_cards"


@dataclass
class WelcomeConfig:
    welcome_channel: int | None = None
    welcome_message: str | None = None
    leave_channel: int | None = None
    leave_message: str | None = None
    autorole_id: int | None = None
    welcome_card_enabled: bool = True
    leave_card_enabled: bool = True
    welcome_card_bg: str | None = None
    leave_card_bg: str | None = None
    welcome_card_color: str | None = None
    leave_card_color: str | None = None


_configs: dict[int, WelcomeConfig] = {}
_loaded = False


async def load_state(bot) -> None:
    global _loaded
    _loaded = True
    _configs.clear()
    for row in await bot.db.fetchall(
        "SELECT guild_id, welcome_channel, welcome_message, leave_channel, "
        "leave_message, autorole_id, welcome_card_enabled, leave_card_enabled, "
        "welcome_card_bg, leave_card_bg, welcome_card_color, leave_card_color "
        "FROM welcome_config"
    ):
        _configs[row["guild_id"]] = WelcomeConfig(
            welcome_channel=row["welcome_channel"],
            welcome_message=row["welcome_message"],
            leave_channel=row["leave_channel"],
            leave_message=row["leave_message"],
            autorole_id=row["autorole_id"],
            welcome_card_enabled=bool(row["welcome_card_enabled"]),
            leave_card_enabled=bool(row["leave_card_enabled"]),
            welcome_card_bg=row["welcome_card_bg"],
            leave_card_bg=row["leave_card_bg"],
            welcome_card_color=row["welcome_card_color"],
            leave_card_color=row["leave_card_color"])


def get(guild_id: int) -> WelcomeConfig | None:
    return _configs.get(guild_id)


async def save(bot, guild_id: int, config: WelcomeConfig) -> None:
    _configs[guild_id] = config
    await bot.db.execute(
        """
        INSERT INTO welcome_config (
            guild_id, welcome_channel, welcome_message, leave_channel,
            leave_message, autorole_id, welcome_card_enabled,
            leave_card_enabled, welcome_card_bg, leave_card_bg,
            welcome_card_color, leave_card_color
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            welcome_channel = excluded.welcome_channel,
            welcome_message = excluded.welcome_message,
            leave_channel = excluded.leave_channel,
            leave_message = excluded.leave_message,
            autorole_id = excluded.autorole_id,
            welcome_card_enabled = excluded.welcome_card_enabled,
            leave_card_enabled = excluded.leave_card_enabled,
            welcome_card_bg = excluded.welcome_card_bg,
            leave_card_bg = excluded.leave_card_bg,
            welcome_card_color = excluded.welcome_card_color,
            leave_card_color = excluded.leave_card_color,
            updated_at = datetime('now')
        """,
        (
            guild_id,
            config.welcome_channel,
            config.welcome_message,
            config.leave_channel,
            config.leave_message,
            config.autorole_id,
            int(config.welcome_card_enabled),
            int(config.leave_card_enabled),
            config.welcome_card_bg,
            config.leave_card_bg,
            config.welcome_card_color,
            config.leave_card_color))


def render(template: str, member: discord.Member, count: int | None) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{name}", discord.utils.escape_markdown(member.display_name))
        .replace("{server}", discord.utils.escape_markdown(member.guild.name))
        .replace("{count}", f"{count:,}" if count is not None else "?")
    )


def resolve_role(guild: discord.Guild, value: str) -> discord.Role | None:
    raw = value.strip()
    if raw.startswith("<@&") and raw.endswith(">"):
        raw = raw[3:-1]
    if raw.isdigit():
        return guild.get_role(int(raw))
    lowered = raw.lower()
    return discord.utils.find(lambda role: role.name.lower() == lowered, guild.roles)


def parse_color(value: str | None) -> str | None:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) != 6:
        return None
    try:
        int(raw, 16)
    except ValueError:
        return None
    return f"#{raw.upper()}"


def accent_rgb(config: WelcomeConfig, *, leaving: bool) -> tuple[int, int, int]:
    raw = config.leave_card_color if leaving else config.welcome_card_color
    value = parse_color(raw)
    color = (
        int(value[1:], 16)
        if value is not None
        else (ERROR_COLOR if leaving else SUCCESS_COLOR)
    )
    return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


def card_enabled(config: WelcomeConfig, *, leaving: bool) -> bool:
    return config.leave_card_enabled if leaving else config.welcome_card_enabled


def path_for(guild_id: int, *, leaving: bool) -> Path:
    kind = "leave" if leaving else "welcome"
    return BACKGROUND_DIR / f"{guild_id}-{kind}.jpg"


def background_path(
    config: WelcomeConfig, guild_id: int, *, leaving: bool
) -> Path | None:
    raw = config.leave_card_bg if leaving else config.welcome_card_bg
    if not raw:
        return None
    path = BACKGROUND_DIR / Path(raw).name
    return path if path.is_file() else None

