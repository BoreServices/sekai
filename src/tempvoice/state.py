import asyncio
import logging
from contextlib import suppress

import discord

log = logging.getLogger("sekai.voicemaster")

MAX_USER_LIMIT = 99
OWNER_PERMISSIONS = (
    "manage_channels",
    "move_members",
    "mute_members",
    "deafen_members",
    "stream",
    "priority_speaker")

# guild_id -> (category_id, trigger_id, menu_channel_id)
_configs: dict[int, tuple[int, int, int | None]] = {}
# temp channel_id -> owner_id
_owners: dict[int, int] = {}
# temp channel_id -> claim prompt message id posted when the owner leaves
_claim_prompts: dict[int, int] = {}
# temp channel_id -> control panel message id inside the channel's chat
_panels: dict[int, int] = {}
_loaded = False

_panel_hook = None
_refresh_tasks: dict[int, asyncio.Task] = {}


def set_panel_hook(hook) -> None:
    """Register the async callback that posts/updates a channel's panel."""
    global _panel_hook
    _panel_hook = hook


async def refresh_panel(channel: discord.VoiceChannel) -> None:
    if _panel_hook is None:
        return
    try:
        await _panel_hook(channel)
    except Exception:
        log.exception("Could not refresh the VoiceMaster panel for %s", channel.id)


def schedule_refresh(channel: discord.VoiceChannel, delay: float = 0.75) -> None:
    """Debounce panel edits caused by bursts of voice-state events."""
    if _panel_hook is None:
        return
    previous = _refresh_tasks.pop(channel.id, None)
    if previous is not None and not previous.done():
        previous.cancel()
    _refresh_tasks[channel.id] = asyncio.create_task(
        _delayed_refresh(channel, delay), name=f"voicemaster-panel-{channel.id}"
    )


async def _delayed_refresh(channel: discord.VoiceChannel, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        await refresh_panel(channel)
    finally:
        if _refresh_tasks.get(channel.id) is asyncio.current_task():
            _refresh_tasks.pop(channel.id, None)


async def delete_temp(bot, channel: discord.VoiceChannel) -> None:
    _owners.pop(channel.id, None)
    _claim_prompts.pop(channel.id, None)
    _panels.pop(channel.id, None)
    task = _refresh_tasks.pop(channel.id, None)
    if task is not None and not task.done():
        task.cancel()
    await bot.db.execute(
        "DELETE FROM tempvoice_channels WHERE channel_id = ?", (channel.id)
    )
    with suppress(discord.HTTPException):
        await channel.delete(reason="VoiceMaster channel is empty")


async def create_temp(
    bot, member: discord.Member, trigger: discord.VoiceChannel
) -> discord.VoiceChannel | None:
    guild = member.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, connect=True
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            manage_channels=True,
            move_members=True,
            mute_members=True,
            deafen_members=True,
            stream=True,
            priority_speaker=True),
    }
    # The category can deny Send Messages; the panel lives in this channel's chat.
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True)
    try:
        channel = await guild.create_voice_channel(
            f"{member.display_name}"[:100],
            category=trigger.category,
            overwrites=overwrites,
            reason=f"VoiceMaster channel for {member} ({member.id})")
    except discord.HTTPException as exc:
        log.warning("Could not create VoiceMaster channel for %s: %s", member, exc)
        return None

    _owners[channel.id] = member.id
    await bot.db.execute(
        "INSERT OR REPLACE INTO tempvoice_channels (channel_id, guild_id, owner_id) "
        "VALUES (?, ?, ?)",
        (channel.id, guild.id, member.id))
    try:
        await member.move_to(channel, reason="VoiceMaster channel")
    except discord.HTTPException as exc:
        log.warning("Could not move %s into VoiceMaster channel: %s", member, exc)
        await delete_temp(bot, channel)
        return None
    await refresh_panel(channel)
    return channel


def is_hidden(channel: discord.VoiceChannel) -> bool:
    return channel.overwrites_for(channel.guild.default_role).view_channel is False


async def set_locked(
    channel: discord.VoiceChannel, locked: bool, *, reason: str
) -> None:
    # view_channel is left alone so locking never reveals a hidden channel.
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.connect = not locked
    await channel.set_permissions(
        channel.guild.default_role, overwrite=overwrite, reason=reason
    )
    await refresh_panel(channel)


async def set_hidden(
    channel: discord.VoiceChannel, hidden: bool, *, reason: str
) -> None:
    """Hide the channel from the server's list while keeping its lock state."""
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.view_channel = not hidden
    await channel.set_permissions(
        channel.guild.default_role, overwrite=overwrite, reason=reason
    )
    await refresh_panel(channel)


async def transfer_owner(
    bot,
    channel: discord.VoiceChannel,
    new_owner: discord.Member,
    *,
    reason: str) -> None:
    old_id = _owners.get(channel.id)
    old_owner = channel.guild.get_member(old_id) if old_id else None

    _owners[channel.id] = new_owner.id
    await bot.db.execute(
        "UPDATE tempvoice_channels SET owner_id = ? WHERE channel_id = ?",
        (new_owner.id, channel.id))

    if old_owner is not None and old_owner.id != new_owner.id:
        overwrite = channel.overwrites_for(old_owner)
        for name in OWNER_PERMISSIONS:
            setattr(overwrite, name, None)
        with suppress(discord.HTTPException):
            await channel.set_permissions(
                old_owner, overwrite=overwrite, reason=reason
            )

    overwrite = channel.overwrites_for(new_owner)
    overwrite.view_channel = True
    overwrite.connect = True
    for name in OWNER_PERMISSIONS:
        setattr(overwrite, name, True)
    await channel.set_permissions(new_owner, overwrite=overwrite, reason=reason)
    await refresh_panel(channel)


async def set_permitted(
    channel: discord.VoiceChannel,
    member: discord.Member,
    allowed: bool,
    *,
    reason: str,
    disconnect: bool = False) -> None:
    overwrite = channel.overwrites_for(member)
    overwrite.view_channel = True
    overwrite.connect = allowed
    await channel.set_permissions(member, overwrite=overwrite, reason=reason)
    if disconnect and not allowed:
        with suppress(discord.HTTPException):
            await member.move_to(None, reason=reason)
    await refresh_panel(channel)


async def load_state(bot) -> None:
    global _loaded
    _loaded = True

    for row in await bot.db.fetchall(
        "SELECT guild_id, category_id, trigger_id, menu_channel_id FROM tempvoice"
    ):
        _configs[row["guild_id"]] = (
            row["category_id"],
            row["trigger_id"],
            row["menu_channel_id"])

    for row in await bot.db.fetchall(
        "SELECT channel_id, owner_id, panel_message_id FROM tempvoice_channels"
    ):
        channel = bot.get_channel(row["channel_id"])
        if channel is None:
            with suppress(discord.HTTPException):
                channel = await bot.fetch_channel(row["channel_id"])
        if not isinstance(channel, discord.VoiceChannel):
            await bot.db.execute(
                "DELETE FROM tempvoice_channels WHERE channel_id = ?",
                (row["channel_id"]))
            continue
        if channel.members:
            _owners[channel.id] = row["owner_id"]
            if row["panel_message_id"]:
                _panels[channel.id] = row["panel_message_id"]
            await refresh_panel(channel)
        else:
            await delete_temp(bot, channel)

    # Members left sitting in a trigger across a restart still get a channel.
    for _, trigger_id, _ in _configs.values():
        trigger = bot.get_channel(trigger_id)
        if isinstance(trigger, discord.VoiceChannel):
            for member in list(trigger.members):
                if not member.bot:
                    await create_temp(bot, member, trigger)
