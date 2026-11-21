import logging
from dataclasses import dataclass

log = logging.getLogger("sekai.honeypot")

DEFAULT_PUNISH = "ban"
PUNISHMENTS = ("ban", "kick", "timeout")


@dataclass
class Settings:
    enabled: bool = False
    punish: str = DEFAULT_PUNISH


_settings: dict[int, Settings] = {}
_channels: dict[int, set[int]] = {}
_loaded = False


async def load_state(bot) -> None:
    global _loaded
    settings: dict[int, Settings] = {}
    channels: dict[int, set[int]] = {}
    for row in await bot.db.fetchall(
        "SELECT guild_id, enabled, punish FROM honeypot_settings"
    ):
        settings[row["guild_id"]] = Settings(
            enabled=bool(row["enabled"]),
            punish=row["punish"])
    for row in await bot.db.fetchall(
        "SELECT guild_id, channel_id FROM honeypot_channels"
    ):
        channels.setdefault(row["guild_id"], set()).add(row["channel_id"])

    # Only swap the cache once both queries succeeded, so a transient database
    # error cannot leave the trap looking empty forever.
    _settings.clear()
    _settings.update(settings)
    _channels.clear()
    _channels.update(channels)
    _loaded = True


def get(guild_id: int) -> Settings | None:
    return _settings.get(guild_id)


def channels(guild_id: int) -> set[int]:
    return set(_channels.get(guild_id, set()))


def is_honeypot(guild_id: int, channel_id: int) -> bool:
    return channel_id in _channels.get(guild_id, set())


async def save(bot, guild_id: int, settings: Settings) -> None:
    _settings[guild_id] = settings
    await bot.db.execute(
        """
        INSERT INTO honeypot_settings (guild_id, enabled, punish)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            enabled = excluded.enabled,
            punish = excluded.punish,
            updated_at = datetime('now')
        """,
        (guild_id, int(settings.enabled), settings.punish))


async def add_channel(bot, guild_id: int, channel_id: int) -> None:
    _channels.setdefault(guild_id, set()).add(channel_id)
    await bot.db.execute(
        """
        INSERT INTO honeypot_channels (guild_id, channel_id)
        VALUES (?, ?)
        ON CONFLICT (guild_id, channel_id) DO NOTHING
        """,
        (guild_id, channel_id))


async def remove_channel(bot, guild_id: int, channel_id: int) -> bool:
    removed = channel_id in _channels.get(guild_id, set())
    if removed:
        _channels[guild_id].discard(channel_id)
        await bot.db.execute(
            "DELETE FROM honeypot_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id))
    return removed