from dataclasses import dataclass


@dataclass
class Mapping:
    guild_id: int
    channel_id: int
    message_id: int
    emoji: str
    role_id: int


_mappings: dict[int, dict[str, Mapping]] = {}
_loaded = False


async def load_state(bot) -> None:
    global _loaded
    _loaded = True
    _mappings.clear()
    for row in await bot.db.fetchall(
        "SELECT guild_id, channel_id, message_id, emoji, role_id "
        "FROM reaction_roles"
    ):
        _mappings.setdefault(row["message_id"], {})[row["emoji"]] = Mapping(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            emoji=row["emoji"],
            role_id=row["role_id"])


def get(message_id: int, emoji: str) -> Mapping | None:
    return _mappings.get(message_id, {}).get(emoji)


def for_guild(guild_id: int) -> list[Mapping]:
    return [
        mapping
        for by_emoji in _mappings.values()
        for mapping in by_emoji.values()
        if mapping.guild_id == guild_id
    ]


def for_message(message_id: int) -> list[Mapping]:
    return list(_mappings.get(message_id, {}).values())


async def add(bot, mapping: Mapping) -> None:
    _mappings.setdefault(mapping.message_id, {})[mapping.emoji] = mapping
    await bot.db.execute(
        """
        INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (message_id, emoji) DO UPDATE SET
            guild_id = excluded.guild_id,
            channel_id = excluded.channel_id,
            role_id = excluded.role_id
        """,
        (
            mapping.guild_id,
            mapping.channel_id,
            mapping.message_id,
            mapping.emoji,
            mapping.role_id))


async def remove(bot, message_id: int, emoji: str) -> bool:
    by_emoji = _mappings.get(message_id)
    if by_emoji is None or emoji not in by_emoji:
        return False
    by_emoji.pop(emoji)
    if not by_emoji:
        _mappings.pop(message_id, None)
    await bot.db.execute(
        "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?",
        (message_id, emoji))
    return True


async def clear_message(bot, message_id: int) -> list[str]:
    emojis = list(_mappings.pop(message_id, {}).keys())
    if not emojis:
        return []
    await bot.db.execute(
        "DELETE FROM reaction_roles WHERE message_id = ?", (message_id)
    )
    return emojis
