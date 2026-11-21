import discord
from discord.ext import commands

from view.base import base_embed, brand

JOIN_COLOR = 0x57F287
LEAVE_COLOR = 0xED4245
MESSAGE_COLOR = 0xFEE75C
CHANNEL_COLOR = 0x5865F2
UPDATE_COLOR = 0x9B59B6
ROLE_COLOR = 0xE67E22
VOICE_COLOR = 0x1ABC9C
INVITE_COLOR = 0x2ECC71
THREAD_COLOR = 0x3498DB
EMOJI_COLOR = 0xF1C40F
AUDIT_COLOR = 0xEB459E
COMMAND_COLOR = 0x57F287
PRESENCE_COLOR = 0x99AAB5
EVENT_COLOR = 0xF47FFF
STAGE_COLOR = 0x9B59B6
AUTOMOD_COLOR = 0xED4245
STICKER_COLOR = 0xF1C40F

MAX_FIELD = 1024


def _limit(text: str, limit: int = MAX_FIELD) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _truncate(text: str | None, limit: int = 1000) -> str:
    text = (text or "").strip()
    if not text:
        return "*empty*"
    return _limit(text, limit)


def _user(user: discord.abc.User) -> str:
    return f"{user.mention} (`{user.id}`)"


def _channel(channel) -> str:
    mention = getattr(channel, "mention", None)
    if mention:
        return f"{mention} (`{channel.id}`)"
    return f"`{getattr(channel, 'name', 'unknown')}` (`{channel.id}`)"


def _channel_or_none(channel) -> str:
    return _channel(channel) if channel is not None else "None"


def _when(value) -> str:
    return discord.utils.format_dt(value, "F") if value else "Unknown"


def _enum(value) -> str:
    text = getattr(value, "name", None) or str(value)
    return text.replace("_", " ").title()


def _color(value) -> str:
    return str(value) if value is not None else "None"


def _target_label(target) -> str:
    mention = getattr(target, "mention", None)
    if mention:
        return mention
    name = getattr(target, "name", None)
    if name:
        return name
    return f"ID {getattr(target, 'id', target)}"


def _field(embed: discord.Embed, name: str, value: str | None, *, inline: bool = False) -> None:
    if value:
        embed.add_field(name=name, value=_limit(str(value)), inline=inline)


def _embed(title: str, color: int, *, description: str | None = None) -> discord.Embed:
    embed = base_embed(title=title, description=description, color=color)
    brand(embed, footer="Server logs")
    return embed


def _actor_fields(embed: discord.Embed, entry) -> discord.Embed:
    """Add who did it and their audit-log reason, when known."""
    if entry is None:
        return embed
    user = getattr(entry, "user", None)
    user_id = getattr(entry, "user_id", None) or getattr(user, "id", None)
    if user is not None:
        _field(embed, "By", _user(user))
    elif user_id:
        _field(embed, "By", f"<@{user_id}> (`{user_id}`)")
    reason = getattr(entry, "reason", None)
    if reason:
        _field(embed, "Reason", reason)
    return embed


def _channel_ref(channel) -> str:
    """Name-first reference that survives deletion (mentions render as #deleted-channel)."""
    name = getattr(channel, "name", "unknown")
    if getattr(channel, "type", None) is discord.ChannelType.category:
        return f"**{name}** (`{channel.id}`)"
    return f"**#{name}** (`{channel.id}`)"


def logging_setup_embed(
    channels: dict[str, discord.TextChannel]) -> discord.Embed:
    category = next(iter(channels.values())).category
    embed = _embed(
        "Server Logging On",
        JOIN_COLOR,
        description=(
            "Logging is on for this server. Each log type has its own "
            f"channel in the **{category.name if category else 'Logs'}** "
            "category:"
        ))
    for kind, channel in channels.items():
        _field(embed, _enum(kind), _channel(channel))
    return embed


def logging_disabled_embed() -> discord.Embed:
    return _embed(
        "Server Logging Off",
        LEAVE_COLOR,
        description=(
            "Logging is off for this server. The log channels were left "
            "in place; run `logs` to turn logging back on."
        ))


def member_join_embed(
    member: discord.Member, member_count: int | None = None
) -> discord.Embed:
    embed = _embed(
        "Member Joined", JOIN_COLOR, description=f"{_user(member)} joined the server."
    )
    _field(embed, "Account created", _when(member.created_at))
    if member_count is not None:
        _field(embed, "Members", str(member_count), inline=True)
    _field(embed, "Avatar", f"[Open]({member.display_avatar.url})", inline=True)
    if member.guild_avatar is not None:
        _field(embed, "Server avatar", f"[Open]({member.guild_avatar.url})", inline=True)
    if member.bot:
        _field(embed, "Account", "Bot", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def member_leave_embed(
    member: discord.Member, member_count: int | None = None
) -> discord.Embed:
    embed = _embed(
        "Member Left", LEAVE_COLOR, description=f"{_user(member)} left the server."
    )
    _field(embed, "Joined", _when(member.joined_at))
    if member_count is not None:
        _field(embed, "Members", str(member_count), inline=True)
    roles = [role.mention for role in member.roles if role != member.guild.default_role]
    _field(embed, "Roles", " ".join(roles[:25]) or "None")
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def member_update_embed(
    before: discord.Member, after: discord.Member
) -> discord.Embed | None:
    changes: list[tuple[str, str]] = []
    if before.nick != after.nick:
        changes.append(
            ("Nickname", f"{before.nick or '*none*'} → {after.nick or '*none*'}")
        )

    added = [role.mention for role in after.roles if role not in before.roles]
    removed = [role.mention for role in before.roles if role not in after.roles]
    if added:
        changes.append(("Roles added", " ".join(added)))
    if removed:
        changes.append(("Roles removed", " ".join(removed)))

    if before.guild_avatar != after.guild_avatar:
        before_url = before.guild_avatar.url if before.guild_avatar else "none"
        after_url = after.guild_avatar.url if after.guild_avatar else "none"
        changes.append(("Server avatar", f"[Before]({before_url}) · [After]({after_url})"))

    if before.timed_out_until != after.timed_out_until:
        changes.append(
            (
                "Timeout",
                _when(after.timed_out_until)
                if after.timed_out_until
                else "Removed")
        )

    before_boost = getattr(before, "premium_since", None)
    after_boost = getattr(after, "premium_since", None)
    if before_boost != after_boost:
        changes.append(
            ("Server boost", _when(after_boost) if after_boost else "Ended")
        )

    before_pending = getattr(before, "pending", False)
    after_pending = getattr(after, "pending", False)
    if before_pending != after_pending:
        changes.append(("Screening", "Pending" if after_pending else "Passed"))

    if not changes:
        return None

    embed = _embed("Member Updated", UPDATE_COLOR, description=_user(after))
    for name, value in changes:
        _field(embed, name, value)
    embed.set_thumbnail(url=after.display_avatar.url)
    return embed


def user_update_embed(
    before: discord.abc.User, after: discord.abc.User
) -> discord.Embed | None:
    avatar_changed = before.display_avatar.url != after.display_avatar.url
    changes: list[tuple[str, str]] = []
    if before.name != after.name:
        changes.append(("Username", f"{before.name} → {after.name}"))
    if before.global_name != after.global_name:
        changes.append(
            (
                "Display name",
                f"{before.global_name or '*none*'} → {after.global_name or '*none*'}")
        )

    before_banner = getattr(before, "banner", None)
    after_banner = getattr(after, "banner", None)
    if before_banner != after_banner:
        before_url = before_banner.url if before_banner else "none"
        after_url = after_banner.url if after_banner else "none"
        changes.append(("Banner", f"[Before]({before_url}) · [After]({after_url})"))

    before_accent = getattr(before, "accent_color", None)
    after_accent = getattr(after, "accent_color", None)
    if before_accent != after_accent:
        changes.append(("Accent color", f"{_color(before_accent)} → {_color(after_accent)}"))

    if not avatar_changed and not changes:
        return None

    title = "Avatar Changed" if avatar_changed and not changes else "User Updated"
    embed = _embed(title, UPDATE_COLOR, description=_user(after))
    if avatar_changed:
        old_url = before.display_avatar.url
        new_url = after.display_avatar.url
        changes.append(("Avatar", f"[Before]({old_url}) · [After]({new_url})"))
        embed.set_thumbnail(url=old_url)
        embed.set_image(url=new_url)
    for name, value in changes:
        _field(embed, name, value)
    return embed


def message_delete_embed(message: discord.Message) -> discord.Embed:
    embed = _embed(
        "Message Deleted",
        LEAVE_COLOR,
        description=(
            f"Message by {_user(message.author)} deleted in "
            f"{_channel(message.channel)}."
        ))
    _field(embed, "Content", _truncate(message.content))
    if message.attachments:
        _field(
            embed,
            "Attachments",
            ", ".join(attachment.filename for attachment in message.attachments[:10]))
    if message.stickers:
        _field(embed, "Stickers", ", ".join(sticker.name for sticker in message.stickers))
    _field(embed, "Message ID", str(message.id), inline=True)
    return embed


def message_edit_embed(
    before: discord.Message, after: discord.Message
) -> discord.Embed | None:
    if before.content == after.content and before.attachments == after.attachments:
        return None

    embed = _embed(
        "Message Edited",
        MESSAGE_COLOR,
        description=(
            f"Message by {_user(after.author)} edited in {_channel(after.channel)}."
        ))
    _field(embed, "Before", _truncate(before.content))
    _field(embed, "After", _truncate(after.content))
    _field(embed, "Jump", f"[Go to message]({after.jump_url})")
    return embed


def bulk_delete_embed(
    channel: discord.abc.GuildChannel, messages: list[discord.Message]
) -> discord.Embed:
    embed = _embed(
        "Messages Bulk Deleted",
        LEAVE_COLOR,
        description=(
            f"**{len(messages)}** messages deleted in {_channel(channel)}."
        ))
    lines = []
    for message in messages[:8]:
        snippet = _truncate(message.content, 100).replace("\n", " ")
        author = getattr(message.author, "mention", str(message.author))
        lines.append(f"{author}: {snippet}")
    if len(messages) > 8:
        lines.append(f"…and **{len(messages) - 8}** more")
    _field(embed, "Messages", "\n".join(lines))
    return embed


def _overwrite_diff(before, after) -> list[str]:
    lines = []
    for target, new in after.overwrites.items():
        old = before.overwrites.get(target)
        label = _target_label(target)
        if old is None:
            lines.append(f"`{label}`: added")
            continue
        if old == new:
            continue
        old_allow = {name for name, value in old.pair()[0] if value}
        new_allow = {name for name, value in new.pair()[0] if value}
        parts = [f"+{name}" for name in sorted(new_allow - old_allow)[:5]]
        parts += [f"-{name}" for name in sorted(old_allow - new_allow)[:5]]
        if old.pair()[1] != new.pair()[1]:
            parts.append("deny changed")
        lines.append(f"`{label}`: {', '.join(parts) or 'changed'}")
    for target in before.overwrites:
        if target not in after.overwrites:
            lines.append(f"`{_target_label(target)}`: removed")
    return lines[:10]


def channel_embed(
    kind: str,
    channel,
    before=None,
    after=None,
    entry=None) -> discord.Embed | None:
    if kind in ("create", "delete"):
        created = kind == "create"
        embed = _embed(
            "Channel Created" if created else "Channel Deleted",
            JOIN_COLOR if created else LEAVE_COLOR,
            description=(
                f"{_channel_ref(channel)} (type: {_enum(channel.type)}) was "
                f"{'created' if created else 'deleted'}."
            ))
        _field(embed, "Position", str(getattr(channel, "position", "?")), inline=True)
        category = getattr(channel, "category", None)
        if category is not None:
            _field(embed, "Category", category.name)
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before.type != after.type:
        changes.append(("Type", f"{_enum(before.type)} → {_enum(after.type)}"))
    if before.name != after.name:
        changes.append(("Name", f"{before.name} → {after.name}"))
    if getattr(before, "topic", None) != getattr(after, "topic", None):
        changes.append(
            ("Topic", f"{_truncate(before.topic, 400)} → {_truncate(after.topic, 400)}")
        )
    if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
        changes.append(("NSFW", "On" if after.nsfw else "Off"))
    if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
        changes.append(("Slowmode", f"{after.slowmode_delay}s"))
    if getattr(before, "category_id", None) != getattr(after, "category_id", None):
        category = getattr(after, "category", None)
        changes.append(("Category", category.name if category else "None"))
    if before.position != after.position:
        changes.append(("Position", f"{before.position} → {after.position}"))
    if getattr(before, "bitrate", None) != getattr(after, "bitrate", None):
        changes.append(("Bitrate", f"{round(after.bitrate / 1000)} kbps"))
    if getattr(before, "user_limit", None) != getattr(after, "user_limit", None):
        changes.append(
            ("User limit", str(after.user_limit) if after.user_limit else "Unlimited")
        )
    if getattr(before, "rtc_region", None) != getattr(after, "rtc_region", None):
        changes.append(("Region", after.rtc_region or "Automatic"))
    if getattr(before, "video_quality_mode", None) != getattr(
        after, "video_quality_mode", None
    ):
        changes.append(("Video quality", _enum(after.video_quality_mode)))
    if getattr(before, "default_auto_archive_duration", None) != getattr(
        after, "default_auto_archive_duration", None
    ):
        changes.append(
            ("Archive after", f"{after.default_auto_archive_duration} min")
        )
    overwrites = _overwrite_diff(before, after)
    if overwrites:
        changes.append(("Permissions", "\n".join(overwrites)))
    if not changes:
        return None

    embed = _embed("Channel Updated", CHANNEL_COLOR, description=_channel(after))
    for name, value in changes:
        _field(embed, name, value, inline=len(value) <= 200)
    return _actor_fields(embed, entry)


def _permission_names(permissions: discord.Permissions) -> set[str]:
    return {name for name, value in permissions if value}


def role_embed(
    kind: str,
    role: discord.Role,
    before: discord.Role | None = None,
    after: discord.Role | None = None,
    entry=None) -> discord.Embed | None:
    if kind == "create":
        embed = _embed(
            "Role Created",
            JOIN_COLOR,
            description=f"Role **{role.name}** (`{role.id}`) was created.")
        _field(embed, "Color", str(role.color), inline=True)
        _field(embed, "Hoisted", "Yes" if role.hoist else "No", inline=True)
        _field(embed, "Mentionable", "Yes" if role.mentionable else "No", inline=True)
        _field(embed, "Position", str(role.position), inline=True)
        return _actor_fields(embed, entry)

    if kind == "delete":
        embed = _embed(
            "Role Deleted",
            LEAVE_COLOR,
            description=f"Role **{role.name}** (`{role.id}`) was deleted.")
        _field(embed, "Color", str(role.color), inline=True)
        _field(embed, "Position", str(role.position), inline=True)
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before.name != after.name:
        changes.append(("Name", f"{before.name} → {after.name}"))
    if before.color != after.color:
        changes.append(("Color", f"{before.color} → {after.color}"))
    if before.hoist != after.hoist:
        changes.append(("Hoisted", "Yes" if after.hoist else "No"))
    if before.mentionable != after.mentionable:
        changes.append(("Mentionable", "Yes" if after.mentionable else "No"))
    if before.position != after.position:
        changes.append(("Position", f"{before.position} → {after.position}"))
    if getattr(before, "unicode_emoji", None) != getattr(after, "unicode_emoji", None):
        changes.append(
            (
                "Emoji",
                f"{before.unicode_emoji or '*none*'} → {after.unicode_emoji or '*none*'}")
        )
    if getattr(before, "icon", None) != getattr(after, "icon", None):
        before_url = before.icon.url if getattr(before, "icon", None) else "none"
        after_url = after.icon.url if getattr(after, "icon", None) else "none"
        changes.append(("Icon", f"[Before]({before_url}) · [After]({after_url})"))
    if before.permissions != after.permissions:
        before_names = _permission_names(before.permissions)
        after_names = _permission_names(after.permissions)
        gained = sorted(after_names - before_names)
        lost = sorted(before_names - after_names)
        if gained:
            changes.append(("Permissions granted", ", ".join(gained[:15])))
        if lost:
            changes.append(("Permissions removed", ", ".join(lost[:15])))
        if not gained and not lost:
            changes.append(("Permissions", "Changed"))
    if not changes:
        return None

    embed = _embed("Role Updated", ROLE_COLOR, description=f"**{after.name}** (`{after.id}`)")
    for name, value in changes:
        _field(embed, name, value)
    return _actor_fields(embed, entry)


def guild_update_embed(
    before: discord.Guild, after: discord.Guild
) -> discord.Embed | None:
    changes: list[tuple[str, str]] = []
    if before.name != after.name:
        changes.append(("Name", f"{before.name} → {after.name}"))

    checks = (
        ("Description", before.description, after.description, lambda v: v or "None"),
        ("Verification level", before.verification_level, after.verification_level, _enum),
        ("Content filter", before.explicit_content_filter, after.explicit_content_filter, _enum),
        ("Notifications", before.default_notifications, after.default_notifications, _enum),
        ("MFA level", before.mfa_level, after.mfa_level, _enum),
        ("Boost tier", before.premium_tier, after.premium_tier, str),
        ("Boosts", before.premium_subscription_count, after.premium_subscription_count, str),
        ("Locale", before.preferred_locale, after.preferred_locale, str),
        ("Owner", before.owner_id, after.owner_id, lambda v: f"<@{v}>"),
        ("AFK channel", before.afk_channel, after.afk_channel, _channel_or_none),
        ("AFK timeout", before.afk_timeout, after.afk_timeout, lambda v: f"{v // 60} min"),
        ("System channel", before.system_channel, after.system_channel, _channel_or_none),
        ("Rules channel", before.rules_channel, after.rules_channel, _channel_or_none),
        (
            "Updates channel",
            before.public_updates_channel,
            after.public_updates_channel,
            _channel_or_none),
        (
            "Vanity URL",
            before.vanity_url_code,
            after.vanity_url_code,
            lambda v: f"discord.gg/{v}" if v else "None"))
    for label, old, new, formatter in checks:
        if old != new:
            changes.append((label, f"{formatter(old)} → {formatter(new)}"))

    embed_icon = None
    if before.icon != after.icon:
        before_url = before.icon.url if before.icon else "none"
        after_url = after.icon.url if after.icon else "none"
        changes.append(("Icon", f"[Before]({before_url}) · [After]({after_url})"))
        if after.icon is not None:
            embed_icon = after.icon.url
    if before.banner != after.banner:
        before_url = before.banner.url if before.banner else "none"
        after_url = after.banner.url if after.banner else "none"
        changes.append(("Banner", f"[Before]({before_url}) · [After]({after_url})"))
    if not changes:
        return None

    embed = _embed("Server Updated", UPDATE_COLOR, description=after.name)
    for name, value in changes:
        _field(embed, name, value, inline=len(value) <= 200)
    if embed_icon is not None:
        embed.set_image(url=embed_icon)
    return embed


def emoji_embed(
    kind: str,
    emoji: discord.Emoji,
    before: discord.Emoji | None = None,
    entry=None) -> discord.Embed:
    if kind == "create":
        embed = _embed(
            "Emoji Created",
            EMOJI_COLOR,
            description=f"{emoji} `:{emoji.name}:` (`{emoji.id}`) was added.")
        return _actor_fields(embed, entry)
    if kind == "delete":
        embed = _embed(
            "Emoji Deleted",
            LEAVE_COLOR,
            description=f"`:{emoji.name}:` (`{emoji.id}`) was removed.")
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before is not None and before.name != emoji.name:
        changes.append(("Name", f"{before.name} → {emoji.name}"))
    embed = _embed("Emoji Updated", EMOJI_COLOR, description=f"{emoji} `:{emoji.name}:`")
    for name, value in changes:
        _field(embed, name, value)
    return _actor_fields(embed, entry)


def sticker_embed(
    kind: str,
    sticker: discord.Sticker,
    before: discord.Sticker | None = None,
    entry=None) -> discord.Embed:
    if kind == "create":
        embed = _embed(
            "Sticker Added",
            STICKER_COLOR,
            description=f"**{sticker.name}** (`{sticker.id}`) was added.")
        if sticker.description:
            _field(embed, "Description", _truncate(sticker.description, 300))
        if getattr(sticker, "emoji", None):
            _field(embed, "Emoji", str(sticker.emoji), inline=True)
        _field(embed, "Format", _enum(getattr(sticker, "format", "unknown")), inline=True)
        if getattr(sticker, "url", None):
            embed.set_thumbnail(url=sticker.url)
        return _actor_fields(embed, entry)
    if kind == "delete":
        embed = _embed(
            "Sticker Removed",
            LEAVE_COLOR,
            description=f"**{sticker.name}** (`{sticker.id}`) was removed.")
        if getattr(sticker, "url", None):
            embed.set_thumbnail(url=sticker.url)
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before is not None and before.name != sticker.name:
        changes.append(("Name", f"{before.name} → {sticker.name}"))
    if before is not None and before.description != sticker.description:
        changes.append(
            (
                "Description",
                f"{_truncate(before.description, 200)} → {_truncate(sticker.description, 200)}")
        )
    embed = _embed(
        "Sticker Updated", STICKER_COLOR, description=f"**{sticker.name}** (`{sticker.id}`)"
    )
    for name, value in changes:
        _field(embed, name, value)
    return _actor_fields(embed, entry)


def voice_embed(before, after, member) -> discord.Embed | None:
    changes: list[tuple[str, str]] = []
    if before.channel is None and after.channel is not None:
        title = "Voice Joined"
        changes.append(("Channel", _channel(after.channel)))
    elif before.channel is not None and after.channel is None:
        title = "Voice Left"
        changes.append(("Channel", _channel(before.channel)))
    elif before.channel != after.channel:
        title = "Voice Moved"
        changes.append(("From", _channel(before.channel)))
        changes.append(("To", _channel(after.channel)))
    else:
        title = "Voice Updated"

    toggles = (
        ("Microphone muted", before.self_mute, after.self_mute),
        ("Headphones deafened", before.self_deaf, after.self_deaf),
        ("Server muted", before.mute, after.mute),
        ("Server deafened", before.deaf, after.deaf),
        ("Streaming", before.self_stream, after.self_stream),
        ("Camera", before.self_video, after.self_video))
    for label, was, now in toggles:
        if bool(was) != bool(now):
            changes.append((label, "On" if now else "Off"))

    if not changes:
        return None

    embed = _embed(title, VOICE_COLOR, description=_user(member))
    for name, value in changes:
        _field(embed, name, value, inline=True)
    return embed


def invite_embed(kind: str, invite: discord.Invite) -> discord.Embed:
    channel = getattr(invite, "channel", None)
    where = _channel(channel) if channel is not None else "an unknown channel"
    created = kind == "create"
    embed = _embed(
        "Invite Created" if created else "Invite Deleted",
        INVITE_COLOR if created else LEAVE_COLOR,
        description=f"`{invite.code}` in {where}.")
    if invite.inviter is not None:
        _field(embed, "Inviter", _user(invite.inviter))
    uses = f"{invite.uses or 0}" if invite.uses is not None else "Unknown"
    limit = "Unlimited" if not invite.max_uses else str(invite.max_uses)
    _field(embed, "Uses", f"{uses} / {limit}", inline=True)
    if invite.expires_at is not None:
        _field(embed, "Expires", _when(invite.expires_at), inline=True)
    else:
        _field(embed, "Expires", "Never", inline=True)
    return embed


def thread_embed(
    kind: str,
    thread: discord.Thread,
    before: discord.Thread | None = None,
    after: discord.Thread | None = None,
    entry=None) -> discord.Embed | None:
    parent = getattr(thread, "parent", None)
    if kind == "create":
        embed = _embed(
            "Thread Created",
            JOIN_COLOR,
            description=f"**{thread.name}** (`{thread.id}`) was created"
            + (f" in {_channel(parent)}." if parent is not None else "."))
        if thread.owner is not None:
            _field(embed, "Owner", _user(thread.owner))
        return _actor_fields(embed, entry)

    if kind == "delete":
        embed = _embed(
            "Thread Deleted",
            LEAVE_COLOR,
            description=f"**{thread.name}** (`{thread.id}`) was deleted"
            + (f" in {_channel(parent)}." if parent is not None else "."))
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before.name != after.name:
        changes.append(("Name", f"{before.name} → {after.name}"))
    if before.archived != after.archived:
        changes.append(("Archived", "Yes" if after.archived else "No"))
    if before.locked != after.locked:
        changes.append(("Locked", "Yes" if after.locked else "No"))
    if before.slowmode_delay != after.slowmode_delay:
        changes.append(("Slowmode", f"{after.slowmode_delay}s"))
    if not changes:
        return None

    embed = _embed("Thread Updated", THREAD_COLOR, description=f"**{after.name}** (`{after.id}`)")
    for name, value in changes:
        _field(embed, name, value, inline=True)
    return _actor_fields(embed, entry)


def ban_embed(
    kind: str, user: discord.abc.User, entry=None
) -> discord.Embed:
    banned = kind == "ban"
    embed = _embed(
        "Member Banned" if banned else "Member Unbanned",
        LEAVE_COLOR if banned else JOIN_COLOR,
        description=(
            f"{_user(user)} was {'banned from' if banned else 'unbanned in'} the server."
        ))
    embed.set_thumbnail(url=user.display_avatar.url)
    return _actor_fields(embed, entry)


def webhook_embed(channel: discord.abc.GuildChannel) -> discord.Embed:
    return _embed(
        "Webhooks Updated",
        UPDATE_COLOR,
        description=f"Webhooks in {_channel(channel)} were changed.")


def pins_embed(
    channel: discord.abc.GuildChannel, last_pin=None
) -> discord.Embed:
    embed = _embed(
        "Pins Updated",
        MESSAGE_COLOR,
        description=f"Pinned messages changed in {_channel(channel)}.")
    if last_pin is not None:
        _field(embed, "Last pin", _when(last_pin), inline=True)
    return embed


def stage_embed(
    kind: str,
    stage: discord.StageInstance,
    before: discord.StageInstance | None = None,
    entry=None) -> discord.Embed | None:
    channel = getattr(stage, "channel", None)
    where = _channel(channel) if channel is not None else "an unknown channel"

    if kind == "create":
        embed = _embed("Stage Started", STAGE_COLOR, description=f"Stage in {where} started.")
        _field(embed, "Topic", _truncate(stage.topic, 500))
        _field(embed, "Privacy", _enum(stage.privacy_level), inline=True)
        if stage.scheduled_event is not None:
            _field(
                embed,
                "Scheduled event",
                stage.scheduled_event.name,
                inline=True)
        return _actor_fields(embed, entry)

    if kind == "delete":
        embed = _embed("Stage Ended", STAGE_COLOR, description=f"Stage in {where} ended.")
        _field(embed, "Topic", _truncate(getattr(stage, "topic", None), 500))
        return _actor_fields(embed, entry)

    changes: list[tuple[str, str]] = []
    if before.topic != stage.topic:
        changes.append(
            (
                "Topic",
                f"{_truncate(before.topic, 400)} → {_truncate(stage.topic, 400)}")
        )
    if before.privacy_level != stage.privacy_level:
        changes.append(
            ("Privacy", f"{_enum(before.privacy_level)} → {_enum(stage.privacy_level)}")
        )
    if before.discoverable_disabled != stage.discoverable_disabled:
        changes.append(
            (
                "Discoverable",
                "No" if stage.discoverable_disabled else "Yes")
        )
    if not changes:
        return None

    embed = _embed("Stage Updated", STAGE_COLOR, description=where)
    for name, value in changes:
        _field(embed, name, value)
    return _actor_fields(embed, entry)


def scheduled_event_embed(
    kind: str,
    event: discord.ScheduledEvent,
    before: discord.ScheduledEvent | None = None,
    entry=None) -> discord.Embed | None:
    if kind == "create":
        embed = _embed(
            "Event Created", EVENT_COLOR, description=f"**{event.name}**"
        )
    elif kind == "delete":
        embed = _embed(
            "Event Deleted", EVENT_COLOR, description=f"**{event.name}**"
        )
    else:
        changes: list[tuple[str, str]] = []
        if before.name != event.name:
            changes.append(("Name", f"{before.name} → {event.name}"))
        if before.description != event.description:
            changes.append(
                (
                    "Description",
                    f"{_truncate(before.description, 300)} → {_truncate(event.description, 300)}")
            )
        if before.start_time != event.start_time:
            changes.append(("Start", f"{_when(before.start_time)} → {_when(event.start_time)}"))
        if before.end_time != event.end_time:
            changes.append(("End", f"{_when(before.end_time)} → {_when(event.end_time)}"))
        if before.status != event.status:
            changes.append(("Status", f"{_enum(before.status)} → {_enum(event.status)}"))
        if before.location != event.location:
            changes.append(
                (
                    "Location",
                    f"{_event_location(before)} → {_event_location(event)}")
            )
        if not changes:
            return None
        embed = _embed("Event Updated", EVENT_COLOR, description=f"**{event.name}**")
        for name, value in changes:
            _field(embed, name, value)
        return _actor_fields(embed, entry)

    _field(embed, "Start", _when(event.start_time), inline=True)
    _field(embed, "End", _when(event.end_time), inline=True)
    _field(embed, "Status", _enum(event.status), inline=True)
    _field(embed, "Location", _event_location(event))
    _field(embed, "Interested", str(event.user_count), inline=True)
    if event.creator is not None:
        _field(embed, "Creator", _user(event.creator), inline=True)
    if event.description:
        _field(embed, "Description", _truncate(event.description, 500))
    _field(embed, "Link", f"[Open event]({event.url})")
    return _actor_fields(embed, entry)


def _event_location(event: discord.ScheduledEvent) -> str:
    location = event.location
    if location is None:
        return "None"
    if isinstance(location, str):
        return location
    return _channel(location)


def automod_embed(execution) -> discord.Embed:
    embed = _embed(
        "Automod Triggered",
        AUTOMOD_COLOR,
        description=f"Rule `{execution.rule_id}` matched a message.")
    member = execution.member
    if member is not None:
        _field(embed, "Member", _user(member))
    else:
        _field(embed, "User", f"<@{execution.user_id}> (`{execution.user_id}`)")
    channel = execution.channel
    if channel is not None:
        _field(embed, "Channel", _channel(channel), inline=True)
    _field(
        embed, "Trigger", _enum(execution.rule_trigger_type), inline=True
    )
    action = getattr(execution, "action", None)
    if action is not None:
        _field(embed, "Action", _enum(action.type), inline=True)
    if getattr(execution, "matched_keyword", None):
        _field(embed, "Keyword", f"`{execution.matched_keyword}`")
    if getattr(execution, "matched_content", None):
        _field(embed, "Matched content", _truncate(execution.matched_content, 400))
    return embed


def _entry_target(entry):
    """entry.target, without letting a null target id crash the converter."""
    if getattr(entry, "_target_id", None) is None:
        return getattr(entry, "__dict__", {}).get("target")
    try:
        return entry.target
    except (TypeError, AttributeError):
        return None


def audit_embed(entry) -> discord.Embed:
    action = _enum(entry.action)
    embed = _embed(f"Audit: {action}", AUDIT_COLOR)
    if entry.user is not None:
        _field(embed, "Actor", _user(entry.user))
    target = _entry_target(entry)
    if target is not None:
        _field(embed, "Target", _target_label(target))
    _field(embed, "Reason", entry.reason or "No reason given")

    changes = []
    try:
        for name, diff in entry.changes:
            before = getattr(diff, "before", None)
            after = getattr(diff, "after", None)
            changes.append(f"{name}: {before} → {after}")
    except (TypeError, AttributeError):
        changes = []
    if changes:
        _field(embed, "Changes", "\n".join(changes[:8]))
    _field(embed, "Entry ID", str(entry.id), inline=True)
    return embed


def command_embed(ctx: commands.Context) -> discord.Embed:
    command = ctx.command.qualified_name if ctx.command else "unknown"
    embed = _embed(
        "Command Used",
        COMMAND_COLOR,
        description=(
            f"`{ctx.prefix}{command}` by {_user(ctx.author)} in "
            f"{_channel(ctx.channel)}."
        ))
    content = (getattr(ctx.message, "content", "") or "").strip()
    if content:
        _field(embed, "Message", _truncate(content, 500))
    return embed


def _activity(activity) -> str:
    if activity is None:
        return "None"
    name = getattr(activity, "name", None) or ""
    kind = getattr(activity, "type", None)
    label = _enum(kind) if kind is not None else "Activity"
    return f"{label}: {name}" if name else label


def presence_embed(
    before: discord.Member, after: discord.Member
) -> discord.Embed | None:
    changes: list[tuple[str, str]] = []
    if before.status != after.status:
        changes.append(("Status", f"{_enum(before.status)} → {_enum(after.status)}"))
    if _activity(before.activity) != _activity(after.activity):
        changes.append(
            (
                "Activity",
                f"{_activity(before.activity)} → {_activity(after.activity)}")
        )
    if getattr(before, "mobile_status", None) != getattr(after, "mobile_status", None):
        changes.append(("Mobile", _enum(after.mobile_status)))
    if not changes:
        return None

    embed = _embed("Presence Updated", PRESENCE_COLOR, description=_user(after))
    for name, value in changes:
        _field(embed, name, value)
    embed.set_thumbnail(url=after.display_avatar.url)
    return embed
