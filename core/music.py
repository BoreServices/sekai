"""
core/music.py — Wavelink music engine backed by public NodeLink/Lavalink servers.

Servers come from config/nodelink.py (NODELINKS). Wavelink picks the least
loaded connected node per player and reconnects dropped nodes automatically;
a small health loop retries nodes that were unreachable at startup.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import discord
import wavelink

from config.nodelink import NODELINKS

log = logging.getLogger("sekai.music")

_bot: discord.Client | None = None
_connect_task: asyncio.Task | None = None
_health_task: asyncio.Task | None = None
_listeners_registered = False

INACTIVE_TIMEOUT = 300
HEALTH_INTERVAL = 60


# ---------------------------------------------------------------------------
# Player registry (thin wrappers over wavelink state)
# ---------------------------------------------------------------------------

def get_player(guild_id: int) -> wavelink.Player | None:
    if _bot is None:
        return None
    guild = _bot.get_guild(guild_id)
    if guild is None:
        return None
    player = guild.voice_client
    return player if isinstance(player, wavelink.Player) else None


def all_players() -> dict[int, wavelink.Player]:
    players: dict[int, wavelink.Player] = {}
    for node in wavelink.Pool.nodes.values():
        players.update(node.players)
    return players


def player_count() -> int:
    return len(all_players())


def connected_nodes() -> list[wavelink.Node]:
    return [
        node
        for node in wavelink.Pool.nodes.values()
        if node.status is wavelink.NodeStatus.CONNECTED
    ]


# ---------------------------------------------------------------------------
# Connection helpers used by the commands
# ---------------------------------------------------------------------------

async def connect_channel(
    channel: discord.VoiceChannel,
    *,
    text_channel: discord.TextChannel | None = None,
    requester_id: int | None = None) -> wavelink.Player:
    """Connect a wavelink Player to a voice channel.

    Raises wavelink.InvalidNodeException when no NodeLink server is available.
    """
    player: wavelink.Player = await channel.connect(
        cls=wavelink.Player, self_deaf=True, timeout=30.0
    )
    # partial = play through the queue automatically, but never fetch
    # recommended tracks once the queue runs out.
    player.autoplay = wavelink.AutoPlayMode.partial
    player.inactive_timeout = INACTIVE_TIMEOUT
    player.text_channel = text_channel
    player.session_owner = requester_id
    return player


async def search_tracks(
    query: str, *, requester_id: int | None = None
) -> list[wavelink.Playable] | wavelink.Playlist:
    """Resolve a URL (any node-supported source) or search YouTube."""
    is_url = "://" in query or query.startswith("www.")
    source = None if is_url else wavelink.TrackSource.YouTube
    results = await wavelink.Playable.search(query, source=source)
    if isinstance(results, wavelink.Playlist):
        tracks = results.tracks
    else:
        tracks = results
    for track in tracks:
        track.extras.requester = requester_id
    return results


# ---------------------------------------------------------------------------
# Status (same dict shape web/status.py and botinfo read)
# ---------------------------------------------------------------------------

def music_status() -> dict:
    nodes = connected_nodes()
    current = min(nodes, key=lambda n: len(n.players)) if nodes else None
    return {
        "node_name": current.identifier if current else None,
        "node_url": current.uri if current else None,
        "status": "Connected" if nodes else "Disconnected",
        "connected": bool(nodes),
        "players": player_count(),
        "latency_ms": None,
        "available": [node.identifier for node in nodes],
    }


# ---------------------------------------------------------------------------
# Event listeners
# ---------------------------------------------------------------------------

async def _on_node_ready(payload: wavelink.NodeReadyEventPayload) -> None:
    log.info(
        "NodeLink node %s ready (resumed=%s)", payload.node.identifier, payload.resumed
    )


async def _on_track_start(payload: wavelink.TrackStartEventPayload) -> None:
    player = payload.player
    if player is None:
        return
    track = payload.original or payload.track
    # Commands announce the track they start themselves; auto-advanced
    # queue tracks are announced here.
    if getattr(track.extras, "announced", False):
        return
    channel = getattr(player, "text_channel", None)
    if channel is None:
        return
    from view import now_playing_embed

    with suppress(discord.HTTPException):
        await channel.send(embed=now_playing_embed(track))


async def _on_track_end(payload: wavelink.TrackEndEventPayload) -> None:
    player = payload.player
    if player is None:
        return
    if (
        payload.reason == "finished"
        and player.queue.is_empty()
        and player.queue.mode is wavelink.QueueMode.normal
    ):
        channel = getattr(player, "text_channel", None)
        if channel is not None:
            from view import success_embed

            with suppress(discord.HTTPException):
                await channel.send(
                    embed=success_embed(
                        "Queue finished — use `p!play` to add more.", icon="🎵"
                    )
                )


async def _on_track_exception(payload: wavelink.TrackExceptionEventPayload) -> None:
    message = payload.exception.get("message") or "unknown error"
    log.warning(
        "Track exception on %s: %s (%s)",
        payload.player.node.identifier if payload.player else "?",
        payload.track.title,
        message)
    player = payload.player
    channel = getattr(player, "text_channel", None) if player else None
    if channel is not None:
        from view import error_embed

        with suppress(discord.HTTPException):
            await channel.send(
                embed=error_embed(
                    f"Couldn't play **{discord.utils.escape_markdown(payload.track.title)}** — skipping."
                )
            )


async def _on_track_stuck(payload: wavelink.TrackStuckEventPayload) -> None:
    player = payload.player
    if player is None:
        return
    log.warning("Track stuck: %s — skipping", payload.track.title)
    channel = getattr(player, "text_channel", None)
    if channel is not None:
        from view import error_embed

        with suppress(discord.HTTPException):
            await channel.send(
                embed=error_embed(
                    f"**{discord.utils.escape_markdown(payload.track.title)}** got stuck — skipping."
                )
            )
    if player.current is not None or not player.queue.is_empty():
        with suppress(Exception):
            await player.skip()


async def _on_inactive_player(player: wavelink.Player) -> None:
    channel = getattr(player, "text_channel", None)
    log.info("Disconnecting inactive player in guild %s", player.guild.id)
    await player.disconnect()
    if channel is not None:
        from view import success_embed

        with suppress(discord.HTTPException):
            await channel.send(
                embed=success_embed("Left voice — nothing playing.", icon="👋")
            )


def _register_listeners(bot: discord.Client) -> None:
    global _listeners_registered
    if _listeners_registered:
        return
    bot.add_listener(_on_node_ready, "on_wavelink_node_ready")
    bot.add_listener(_on_track_start, "on_wavelink_track_start")
    bot.add_listener(_on_track_end, "on_wavelink_track_end")
    bot.add_listener(_on_track_exception, "on_wavelink_track_exception")
    bot.add_listener(_on_track_stuck, "on_wavelink_track_stuck")
    bot.add_listener(_on_inactive_player, "on_wavelink_inactive_player")
    _listeners_registered = True


# ---------------------------------------------------------------------------
# Lifecycle hooks called by core/bot.py
# ---------------------------------------------------------------------------

def _build_nodes() -> list[wavelink.Node]:
    return [
        wavelink.Node(
            identifier=server.name,
            uri=server.resolved_url,
            password=server.password,
            # Finite retries so a dead node doesn't block the ones after it;
            # the health loop picks disconnected nodes back up later.
            retries=1,
            inactive_player_timeout=INACTIVE_TIMEOUT,
            inactive_channel_tokens=3)
        for server in NODELINKS
    ]


async def _connect_nodes(bot: discord.Client) -> None:
    nodes = _build_nodes()
    # One Pool.connect per node so attempts run concurrently instead of
    # sequentially blocking on unreachable servers. return_exceptions keeps a
    # node with a rejected password from killing the whole connect task.
    results = await asyncio.gather(
        *(wavelink.Pool.connect(nodes=[node], client=bot) for node in nodes),
        return_exceptions=True)
    for node, result in zip(nodes, results):
        if isinstance(result, Exception):
            log.warning("NodeLink %s failed to connect: %s", node.identifier, result)
    log.info(
        "Music engine: %d/%d NodeLink servers connected",
        len(connected_nodes()),
        len(nodes))


async def _node_health_loop() -> None:
    while True:
        await asyncio.sleep(HEALTH_INTERVAL)
        try:
            if any(
                node.status is wavelink.NodeStatus.DISCONNECTED
                for node in wavelink.Pool.nodes.values()
            ):
                await wavelink.Pool.reconnect()
        except Exception:
            log.exception("NodeLink health check failed")


def start_music_node(bot: discord.Client) -> None:
    """Called from setup_hook — connect to the public NodeLink servers."""
    global _bot, _connect_task, _health_task
    _bot = bot
    _register_listeners(bot)
    _connect_task = asyncio.create_task(_connect_nodes(bot), name="music-connect")
    _health_task = asyncio.create_task(_node_health_loop(), name="music-health")


async def close_music_nodes() -> None:
    """Called from bot.close() — disconnect players and close node sockets."""
    global _connect_task, _health_task
    for task in (_connect_task, _health_task):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    _connect_task = _health_task = None
    await wavelink.Pool.close()
    log.info("Music engine closed")