import discord

from src.minecraft.client import MinecraftProfile, MinecraftServer
from view.info import info_embed

VALUE_LIMIT = 1000
LIST_LIMIT = 20


def _shorten(text: str, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _listing(items: list[str], *, extra: int = 0) -> str:
    shown = ", ".join(items[:LIST_LIMIT])
    rest = len(items) - LIST_LIMIT + extra
    if rest > 0:
        shown += f"  ·  **+{rest:,} more**"
    return _shorten(shown, VALUE_LIMIT)


def _identity_fields(profile: MinecraftProfile) -> list[tuple[str, str, bool]]:
    return [
        ("🆔 UUID", f"`{profile.uuid}`", False),
        ("🎨 Model", profile.model.title(), True),
        (
            "🧵 Cape",
            "Equipped" if profile.cape else "Not equipped",
            True),
    ]


def mc_profile_embed(
    profile: MinecraftProfile, *, footer: str | None = None
) -> discord.Embed:
    links = [f"[{profile.username} on NameMC]({profile.namemc})"]
    if profile.skin_url:
        links.append(f"[Skin PNG]({profile.skin_url})")
    if profile.cape_url:
        links.append(f"[Cape PNG]({profile.cape_url})")
    return info_embed(
        title=f"👤 {profile.username}",
        description=(
            "Java Edition player profile read from Mojang's session servers."
        ),
        fields=[
            *_identity_fields(profile),
            ("🔗 Links", "  ·  ".join(links), False),
        ],
        thumbnail_url="attachment://skin.png" if profile.skin else None,
        footer=footer)


def mc_skin_embed(
    profile: MinecraftProfile, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"🎨 {profile.username}'s skin",
        description=(
            "The raw texture sheet Mojang stores for this account. "
            "The 3D page is built from these same pixels."
        ),
        fields=_identity_fields(profile),
        image_url="attachment://skin.png",
        footer=footer)


def mc_skin_3d_embed(
    profile: MinecraftProfile, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"👤 {profile.username} in 3D",
        description=(
            "Isometric render of the skin, generated locally from the "
            "texture sheet."
        ),
        fields=_identity_fields(profile),
        image_url="attachment://skin_3d.png",
        footer=footer)


def mc_cape_embed(
    profile: MinecraftProfile, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"🧵 {profile.username}'s cape",
        description="The cape artwork Mojang stores for this account.",
        fields=_identity_fields(profile),
        image_url="attachment://cape.png",
        footer=footer)


def mc_cape_3d_embed(
    profile: MinecraftProfile, *, footer: str | None = None
) -> discord.Embed:
    return info_embed(
        title=f"🧵 {profile.username}'s cape in 3D",
        description=(
            "The cape on the player model, seen from behind. "
            "Generated locally from the same texture."
        ),
        fields=_identity_fields(profile),
        image_url="attachment://cape_3d.png",
        footer=footer)


def mc_server_embed(
    server: MinecraftServer, *, footer: str | None = None
) -> discord.Embed:
    online = server.online
    lines = [line.strip() for line in server.motd if line.strip()]
    motd = "\n".join(lines) if lines else "_No MOTD set._"
    description = motd if len(motd) <= 1000 else f"{motd[:999]}…"
    if not online:
        description += (
            "\n\nThe server didn't answer a ping. It might be offline, "
            "restarting or hiding behind a firewall."
        )

    fields: list[tuple[str, str, bool]] = [
        (
            f"{'🟢' if online else '🔴'} Status",
            "Online" if online else "Offline",
            True),
        ("🌐 Edition", server.edition, True),
        ("🎨 Version", server.version or "Unknown", True),
        (
            "👥 Players",
            f"`{server.players_online:,}/{server.players_max:,}`",
            True),
    ]

    if online:
        if server.software:
            fields.append(("⚙️ Software", _shorten(server.software, 200), True))
        if server.gamemode:
            fields.append(("🎯 Gamemode", server.gamemode.title(), True))
        if server.map_name:
            fields.append(("📖 Map", _shorten(server.map_name, 200), True))
        if server.players:
            unnamed = max(0, server.players_online - len(server.players))
            fields.append(
                (
                    "🙋 Online players",
                    _listing(server.players, extra=unnamed),
                    False)
            )
        if server.plugins:
            fields.append(("🧩 Plugins", _listing(server.plugins), False))
        if server.mods:
            fields.append(("🧵 Mods", _listing(server.mods), False))
        if server.hostname and server.hostname.lower() != server.host.lower():
            fields.append(("📡 Hostname", f"`{server.hostname}`", True))
        if server.srv:
            fields.append(("🛰️ SRV record", "Yes", True))

    target = f"{server.host}:{server.port}" if server.port else server.host
    fields.append(("🏠 Address", f"`{target}`", True))

    return info_embed(
        title=f"🖥️ {server.address}",
        description=description,
        fields=fields,
        thumbnail_url="attachment://icon.png" if server.icon else None,
        footer=footer)
