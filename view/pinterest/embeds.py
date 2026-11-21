import discord

from src.pinterest.client import PinterestBoard, PinterestPin, PinterestUser
from view.info import info_embed

DESCRIPTION_LIMIT = 900


def _shorten(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _when(value) -> str:
    return (
        f"{discord.utils.format_dt(value, 'D')} "
        f"({discord.utils.format_dt(value, 'R')})"
    )


def _site(url: str) -> str:
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


def pinterest_profile_embed(
    user: PinterestUser, *, footer: str | None = None
) -> discord.Embed:
    name = _shorten(user.full_name or user.username, 200)
    title = f"📌 {name}"
    if user.full_name and user.full_name.lower() != user.username.lower():
        title += f" (@{user.username})"

    fields = [
        ("👥 Followers", f"`{user.followers:,}`", True),
        ("🙋 Following", f"`{user.following:,}`", True),
        ("📌 Pins", f"`{user.pin_count:,}`", True),
        ("📖 Boards", f"`{user.board_count:,}`", True),
    ]
    if user.verified:
        fields.append(("✅ Verified", "Pinterest verified account", True))
    if user.private:
        fields.append(
            ("🔒 Private", "Only approved followers can see these pins", True)
        )
    if user.created_at is not None:
        fields.append(("📅 Joined", _when(user.created_at), False))
    if user.website:
        website = (
            user.website
            if "://" in user.website
            else f"https://{user.website}"
        )
        fields.append(("🌐 Website", f"[{_site(website)}]({website})", False))
    fields.append(("🔗 Profile", user.url, False))

    return info_embed(
        title=title,
        description=(
            _shorten(user.about) if user.about else "This account has no bio."
        ),
        fields=fields,
        thumbnail_url=user.avatar_url,
        footer=footer)


def pinterest_boards_embed(
    user: PinterestUser,
    boards: list[PinterestBoard],
    *,
    page: int,
    pages: int,
    loaded: int,
    offset: int,
    footer: str | None = None) -> discord.Embed:
    name = _shorten(user.full_name or user.username, 180)
    title = f"📌 {name}'s boards"

    if not boards:
        description = f"@{user.username} doesn't have any public boards to show."
    else:
        total = max(user.board_count, loaded)
        description = f"Showing **{loaded}** of **{total:,}** latest boards"
        if pages > 1:
            description += f"  ·  page **{page}/{pages}**"
        description += ". Pick one from the menu to look inside."

    fields = []
    for index, board in enumerate(boards, start=offset + 1):
        parts = [
            f"`{board.pin_count:,}` pins",
            f"`{board.followers:,}` followers",
        ]
        if board.privacy and board.privacy.lower() != "public":
            parts.append(board.privacy.title())
        value = " · ".join(parts)
        if board.description:
            value += f"\n{_shorten(board.description, 200)}"
        value += f"\n[Open board]({board.url})"
        fields.append((f"{index}. {_shorten(board.name, 180)}", value, False))

    return info_embed(
        title=title,
        description=description,
        fields=fields,
        thumbnail_url=user.avatar_url,
        footer=footer)


def pinterest_board_embed(
    user: PinterestUser,
    board: PinterestBoard,
    *,
    page: int,
    pages: int,
    loaded: int,
    footer: str | None = None,
    pin: PinterestPin | None = None) -> discord.Embed:
    description = (
        _shorten(board.description)
        if board.description
        else "Pins saved to this board."
    )
    if loaded:
        description += f"\n\nShowing **{loaded}** pins loaded from Pinterest."
    else:
        description += "\n\nThis board has no pins to show."
    if pin is not None and pin.title:
        description += f"\n\n**{_shorten(pin.title, 200)}**"

    fields = [
        ("👤 Owner", f"[@{user.username}]({user.url})", True),
        ("📌 Pins", f"`{max(board.pin_count, loaded):,}`", True),
        ("👥 Followers", f"`{board.followers:,}`", True),
        ("📄 Page", f"`{page}/{pages}`", True),
    ]
    if board.privacy and board.privacy.lower() != "public":
        fields.append(("🔒 Privacy", board.privacy.title(), True))
    if board.created_at is not None:
        fields.append(("📅 Created", _when(board.created_at), True))
    if pin is not None and pin.url:
        fields.append(("🔗 Pin", pin.url, False))
    fields.append(("🔗 Board", board.url, False))

    return info_embed(
        title=f"📌 {_shorten(board.name, 200)}",
        description=description,
        fields=fields,
        thumbnail_url=user.avatar_url,
        image_url=pin.image_url if pin is not None else None,
        footer=footer)


def pinterest_user_pins_embed(
    user: PinterestUser,
    *,
    page: int,
    pages: int,
    loaded: int,
    footer: str | None = None,
    pin: PinterestPin | None = None) -> discord.Embed:
    name = _shorten(user.full_name or user.username, 180)
    description = f"Latest pins saved by [@{user.username}]({user.url})."
    if loaded and loaded < user.pin_count:
        description += (
            f"\nShowing the **{loaded}** most recent pins loaded from Pinterest."
        )
    if pin is not None and pin.title:
        description += f"\n\n**{_shorten(pin.title, 200)}**"

    fields = [
        ("👤 Account", f"[@{user.username}]({user.url})", True),
        ("📌 Pins", f"`{max(user.pin_count, loaded):,}`", True),
        ("👥 Followers", f"`{user.followers:,}`", True),
        ("📄 Page", f"`{page}/{pages}`", True),
    ]
    if pin is not None and pin.url:
        fields.append(("🔗 Pin", pin.url, False))
    fields.append(("🔗 Profile", user.url, False))

    return info_embed(
        title=f"📌 {name}'s pins",
        description=description,
        fields=fields,
        thumbnail_url=user.avatar_url,
        image_url=pin.image_url if pin is not None else None,
        footer=footer)
