from typing import TYPE_CHECKING

from config.settings import settings

if TYPE_CHECKING:
    import discord
    from core.bot import SekaiBot


def default_prefix(bot: "SekaiBot") -> str:
    return settings.dev_prefix if bot.dev else settings.default_prefix


async def get_prefix(bot: "SekaiBot", message: "discord.Message") -> str:
    if message.guild is None:
        return default_prefix(bot)
    return await get_guild_prefix(bot, message.guild.id)


async def get_guild_prefix(bot: "SekaiBot", guild_id: int) -> str:
    if bot.dev:
        return settings.dev_prefix
    cached = bot.prefix_cache.get(guild_id)
    if cached is not None:
        return cached
    row = await bot.db.fetchone(
        "SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,)
    )
    prefix = row["prefix"] if row is not None and row["prefix"] else settings.default_prefix
    bot.prefix_cache[guild_id] = prefix
    return prefix


async def set_guild_prefix(bot: "SekaiBot", guild_id: int, prefix: str) -> None:
    await bot.db.execute(
        "INSERT INTO guild_settings (guild_id, prefix) VALUES (?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix",
        (guild_id, prefix))
    bot.prefix_cache[guild_id] = prefix


async def reset_guild_prefix(bot: "SekaiBot", guild_id: int) -> None:
    await bot.db.execute(
        "UPDATE guild_settings SET prefix = NULL WHERE guild_id = ?", (guild_id,)
    )
    bot.prefix_cache[guild_id] = default_prefix(bot)
