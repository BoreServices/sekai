import discord

from src.roblox.client import RobloxPresence, RobloxUser
from view.info import info_embed

BIO_LIMIT = 900
GROUP_LIMIT = 6

STATUS_ICONS = {
    "game": "🟢",
    "online": "🟢",
    "studio": "🟡",
    "offline": "🔴",
}


def _shorten(text: str, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _presence_text(presence: RobloxPresence | None) -> str:
    if presence is None:
        return "Unknown"
    if presence.kind == "game":
        if presence.location and presence.game_url:
            place = _shorten(presence.location, 120)
            return f"In game — [{place}]({presence.game_url})"
        if presence.location:
            return f"In game — {_shorten(presence.location, 120)}"
        return "In game"
    if presence.kind == "online":
        return "Online on the website"
    if presence.kind == "studio":
        return "In Roblox Studio"
    return "Offline"


def _status_field(
    presence: RobloxPresence | None) -> tuple[str, str, bool]:
    icon = STATUS_ICONS.get(presence.kind, "🟡") if presence else "🟡"
    return (f"{icon} Status", _presence_text(presence), True)


def _identity_fields(user: RobloxUser) -> list[tuple[str, str, bool]]:
    fields: list[tuple[str, str, bool]] = [("🆔 User ID", f"`{user.id}`", True)]
    if user.display_name and user.display_name.casefold() != user.username.casefold():
        fields.append(("🏷️ Display name", _shorten(user.display_name, 200), True))
    if user.created:
        fields.append(("📅 Joined", user.created.strftime("%B %d, %Y"), True))
    if user.verified:
        fields.append(("🟢 Verified", "Yes", True))
    if user.banned:
        fields.append(("🔴 Banned", "Yes", True))
    return fields


def _groups_text(user: RobloxUser) -> str:
    if not user.groups:
        return "Not in any groups."
    lines = [
        f"[{_shorten(group.name, 60)}](https://www.roblox.com/groups/{group.id})"
        f" · {_shorten(group.role, 40)}"
        for group in user.groups[:GROUP_LIMIT]
    ]
    rest = len(user.groups) - GROUP_LIMIT
    if rest > 0:
        lines.append(f"**+{rest:,} more**")
    return "\n".join(lines)


def roblox_user_embed(
    user: RobloxUser, *, footer: str | None = None
) -> discord.Embed:
    bio = _shorten(user.description, BIO_LIMIT) or (
        "This player hasn't written a bio yet."
    )
    fields: list[tuple[str, str, bool]] = [
        *_identity_fields(user),
        ("👥 Followers", f"`{user.followers:,}`", True),
        ("👥 Following", f"`{user.following:,}`", True),
        ("👥 Friends", f"`{user.friends:,}`", True),
        _status_field(user.presence),
        ("👤 Groups", _groups_text(user), False),
        ("🔗 Links", f"[Profile]({user.url})", False),
    ]
    return info_embed(
        title=f"👤 {user.username}",
        description=bio,
        fields=fields,
        thumbnail_url=user.headshot_url,
        footer=footer)


def roblox_avatar_embed(
    user: RobloxUser, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"👤 {user.username}'s avatar",
        description=(
            "Full-body avatar render served by Roblox's thumbnail service. "
            "It updates whenever the player changes their look."
        ),
        fields=_identity_fields(user),
        image_url=user.avatar_url,
        footer=footer)


def roblox_headshot_embed(
    user: RobloxUser, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"👤 {user.username}'s headshot",
        description=(
            "Close-up head render served by Roblox's thumbnail service."
        ),
        fields=_identity_fields(user),
        image_url=user.headshot_url,
        footer=footer)
