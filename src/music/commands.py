"""
src/music/commands.py — music commands powered by Wavelink + public NodeLink servers.

Playback runs on the NodeLink/Lavalink servers listed in config/nodelink.py;
no local FFmpeg or yt-dlp is needed. Plain queries search YouTube, URLs are
resolved by the node (YouTube, SoundCloud, Spotify, Apple Music, … depending
on the node's plugins).

Commands:
    p!join / p!connect
    p!play <query or URL>      (alias: p!p)
    p!search <query>           (alias: p!find)
    p!forceplay <query or URL> (alias: p!fp)
    p!pause
    p!resume
    p!skip
    p!stop
    p!queue                    (alias: p!q)
    p!nowplaying               (alias: p!np)
    p!loop [off|track|queue]   (alias: p!repeat)
    p!volume [0-100]           (alias: p!vol)
    p!leave / p!disconnect
"""

from __future__ import annotations

import asyncio
import logging

import discord
import wavelink
from discord.ext import commands

from core import music as engine
from view import (
    error_embed,
    now_playing_embed,
    playlist_embed,
    queue_embed,
    search_embed,
    success_embed,
    track_added_embed)

log = logging.getLogger("sekai.music")

# guild_id -> last search results
_search_cache: dict[int, list[wavelink.Playable]] = {}

RICKROLL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
RICKROLL_REQUESTS = {"rick", "rickroll", "rick astley", "never gonna give you up"}
SEARCH_LIMIT = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_player(ctx: commands.Context) -> wavelink.Player | None:
    return engine.get_player(ctx.guild.id)


async def _ensure_voice(ctx: commands.Context) -> wavelink.Player | None:
    """Connect to the author's VC (or return existing player). Sends error on failure."""
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send(embed=error_embed("Join a voice channel first."))
        return None

    existing = _get_player(ctx)
    if existing is not None:
        if existing.channel != ctx.author.voice.channel:
            await ctx.send(embed=error_embed("I'm already in another voice channel."))
            return None
        if isinstance(ctx.channel, discord.TextChannel):
            existing.text_channel = ctx.channel
        return existing

    try:
        player = await engine.connect_channel(
            ctx.author.voice.channel,
            text_channel=ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None,
            requester_id=ctx.author.id)
    except wavelink.InvalidNodeException:
        await ctx.send(embed=error_embed(
            "No music servers are available right now — try again in a minute."
        ))
        return None
    except asyncio.TimeoutError:
        await ctx.send(embed=error_embed(
            "Timed out connecting to your voice channel. "
            "Make sure the bot has permission to join it."
        ))
        return None
    except Exception:
        log.exception("Failed to connect to voice in guild %s", ctx.guild.id)
        await ctx.send(embed=error_embed("Couldn't join your voice channel."))
        return None

    return player


def _voice_control():
    """Check: caller must be in the same VC as the bot."""
    async def predicate(ctx: commands.Context) -> bool:
        player = _get_player(ctx)
        if player is None:
            raise commands.CheckFailure("I'm not playing anything right now.")
        voice = getattr(ctx.author, "voice", None)
        if voice is None or voice.channel is None:
            raise commands.CheckFailure("Join my voice channel to control the music.")
        if voice.channel != player.channel:
            raise commands.CheckFailure(
                f"Only members in {player.channel.mention} can control the music."
            )
        return True
    return commands.check(predicate)


def _leave_blocker(player: wavelink.Player, ctx: commands.Context) -> str | None:
    owner_id = getattr(player, "session_owner", None)
    if owner_id is not None and owner_id != ctx.author.id:
        return f"Only <@{owner_id}> can make me leave — they started this session."
    return None


async def _resolve(
    ctx: commands.Context, query: str
) -> tuple[list[wavelink.Playable], wavelink.Playlist | None] | None:
    """Resolve query to tracks. Returns (tracks, playlist or None), or None on error."""
    if query.strip().lower() in RICKROLL_REQUESTS:
        query = RICKROLL_URL

    # Numeric → pick from last search
    if query.strip().isdigit():
        number = int(query.strip())
        cache = _search_cache.get(ctx.guild.id, [])
        if not cache or not 1 <= number <= len(cache):
            await ctx.send(embed=error_embed(
                f"No result **#{number}**. Run `{ctx.prefix}search <song>` first."
            ))
            return None
        return [cache[number - 1]], None

    async with ctx.typing():
        try:
            results = await engine.search_tracks(query, requester_id=ctx.author.id)
        except wavelink.InvalidNodeException:
            await ctx.send(embed=error_embed(
                "No music servers are available right now — try again in a minute."
            ))
            return None
        except Exception:
            log.exception("Error resolving %r", query)
            await ctx.send(embed=error_embed(
                "Couldn't load that — the music server rejected the query or is unavailable."
            ))
            return None

    if isinstance(results, wavelink.Playlist):
        if not results.tracks:
            await ctx.send(embed=error_embed("That playlist is empty."))
            return None
        return results.tracks, results

    if not results:
        await ctx.send(embed=error_embed("No results found for that search."))
        return None

    # For plain text searches keep only the best match
    is_url = "://" in query or query.startswith("www.")
    tracks = results if is_url else results[:1]
    return tracks, None


def _playlist_response(
    tracks: list[wavelink.Playable],
    playlist: wavelink.Playlist | None,
    description: str) -> discord.Embed:
    first = tracks[0]
    return playlist_embed(
        playlist.name if playlist else "Playlist",
        count=len(tracks),
        description=description,
        source=first.source,
        url=playlist.url if playlist else None,
        artwork_url=(playlist.artwork if playlist else None) or first.artwork)


async def _play_tracks(
    ctx: commands.Context,
    player: wavelink.Player,
    tracks: list[wavelink.Playable],
    playlist: wavelink.Playlist | None,
    *,
    force: bool = False) -> None:
    """Queue tracks and start/replace playback, then send the response embed."""
    idle = player.current is None

    if idle:
        first = tracks[0]
        if len(tracks) > 1:
            player.queue.extend(tracks[1:])
        first.extras.announced = True
        try:
            await player.play(first)
        except Exception:
            log.exception("Failed to start playback in guild %s", ctx.guild.id)
            player.queue.clear()
            if player.connected:
                await player.disconnect()
            await ctx.send(embed=error_embed("Couldn't start playback — try again."))
            return
        if playlist is not None:
            await ctx.send(embed=_playlist_response(
                tracks, playlist,
                f"Playing **{discord.utils.escape_markdown(first.title)}** "
                f"and queued **{len(tracks) - 1}** more."))
        else:
            await ctx.send(embed=now_playing_embed(first))
        return

    if force:
        tracks[0].extras.announced = True
        for track in reversed(tracks):
            player.queue.put_at(0, track)
        try:
            if player.paused:
                await player.pause(False)
            await player.skip()
        except Exception:
            log.exception("Failed to force-play in guild %s", ctx.guild.id)
            await ctx.send(embed=error_embed("Couldn't switch to that track — try again."))
            return
        if playlist is not None:
            await ctx.send(embed=_playlist_response(
                tracks, playlist,
                f"Force playing **{discord.utils.escape_markdown(tracks[0].title)}** "
                f"and **{len(tracks) - 1}** more."))
        else:
            await ctx.send(embed=now_playing_embed(tracks[0]))
        return

    start = len(player.queue) + 1
    player.queue.extend(tracks)
    if playlist is not None:
        await ctx.send(embed=_playlist_response(
            tracks, playlist,
            f"Queued **{len(tracks)}** tracks (#{start}–#{start + len(tracks) - 1})."))
    else:
        await ctx.send(embed=track_added_embed(tracks[0], start))


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------

def setup(bot) -> None:

    # ------------------------------------------------------------------
    @bot.command(name="join", aliases=["connect"],
                 help="Join your voice channel.", usage="join")
    @commands.guild_only()
    async def join(ctx: commands.Context) -> None:
        player = await _ensure_voice(ctx)
        if player is not None:
            await ctx.send(embed=success_embed(
                f"Joined `{player.channel.name}`.", icon="🔊"
            ))

    # ------------------------------------------------------------------
    @bot.command(
        name="search", aliases=["find"],
        help="Search for a song and get numbered results. Then use `play <number>`.",
        usage="search <song name>",
        extras={"example": "search daft punk"})
    @commands.guild_only()
    async def search(ctx: commands.Context, *, query: str) -> None:
        async with ctx.typing():
            try:
                results = await engine.search_tracks(query, requester_id=ctx.author.id)
            except wavelink.InvalidNodeException:
                await ctx.send(embed=error_embed(
                    "No music servers are available right now — try again in a minute."
                ))
                return
            except Exception:
                log.exception("Search failed for %r", query)
                await ctx.send(embed=error_embed("Search failed — try again in a moment."))
                return

        playlist = results if isinstance(results, wavelink.Playlist) else None
        tracks = playlist.tracks if playlist else results
        if not tracks:
            await ctx.send(embed=error_embed("No results found."))
            return

        shown = tracks[:SEARCH_LIMIT]
        _search_cache[ctx.guild.id] = shown
        await ctx.send(embed=search_embed(
            query, shown,
            prefix=ctx.prefix,
            playlist_name=playlist.name if playlist else None,
            total=len(tracks)))

    # ------------------------------------------------------------------
    @bot.command(
        name="play", aliases=["p"],
        help=(
            "Play a song or playlist from YouTube, SoundCloud, Spotify and more. "
            "Also accepts a number from your last `search`."
        ),
        usage="play <song, URL or search number>",
        extras={"example": "play never gonna give you up"})
    @commands.guild_only()
    async def play(ctx: commands.Context, *, query: str) -> None:
        player = await _ensure_voice(ctx)
        if player is None:
            return
        resolved = await _resolve(ctx, query)
        if resolved is None:
            return
        tracks, playlist = resolved
        await _play_tracks(ctx, player, tracks, playlist)

    # ------------------------------------------------------------------
    @bot.command(
        name="forceplay", aliases=["fp"],
        help="Play a track immediately, interrupting whatever is playing.",
        usage="forceplay <song, URL or search number>",
        extras={"example": "forceplay https://youtu.be/dQw4w9WgXcQ"})
    @commands.guild_only()
    async def forceplay(ctx: commands.Context, *, query: str) -> None:
        player = await _ensure_voice(ctx)
        if player is None:
            return
        resolved = await _resolve(ctx, query)
        if resolved is None:
            return
        tracks, playlist = resolved
        await _play_tracks(ctx, player, tracks, playlist, force=True)

    # ------------------------------------------------------------------
    @bot.command(name="pause", help="Pause playback.", usage="pause")
    @commands.guild_only()
    @_voice_control()
    async def pause(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        if player.current is None:
            await ctx.send(embed=error_embed("Nothing is playing right now."))
            return
        if player.paused:
            await ctx.send(embed=error_embed("Playback is already paused."))
            return
        await player.pause(True)
        await ctx.send(embed=success_embed("Paused.", icon="⏸️"))

    # ------------------------------------------------------------------
    @bot.command(name="resume", help="Resume playback.", usage="resume")
    @commands.guild_only()
    @_voice_control()
    async def resume(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        if not player.paused:
            await ctx.send(embed=error_embed("Playback isn't paused."))
            return
        await player.pause(False)
        await ctx.send(embed=success_embed("Resumed.", icon="▶️"))

    # ------------------------------------------------------------------
    @bot.command(name="skip", help="Skip the current track.", usage="skip")
    @commands.guild_only()
    @_voice_control()
    async def skip(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        if player.current is None:
            await ctx.send(embed=error_embed("Nothing is playing right now."))
            return
        old = await player.skip()
        title = old.title if old else "track"
        await ctx.send(embed=success_embed(
            f"Skipped **{discord.utils.escape_markdown(title)}**.", icon="⏭️"
        ))

    # ------------------------------------------------------------------
    @bot.command(name="stop", help="Stop playback and clear the queue.", usage="stop")
    @commands.guild_only()
    @_voice_control()
    async def stop(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        player.queue.reset()
        if player.current is not None:
            await player.stop()
        await ctx.send(embed=success_embed("Stopped and cleared the queue.", icon="⏹️"))

    # ------------------------------------------------------------------
    @bot.command(
        name="queue", aliases=["q"],
        help="Show the current queue.", usage="queue")
    @commands.guild_only()
    async def queue_cmd(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        if player is None or (player.queue.is_empty() and player.current is None):
            await ctx.send(embed=error_embed("The queue is empty."))
            return
        await ctx.send(embed=queue_embed(player))

    # ------------------------------------------------------------------
    @bot.command(
        name="nowplaying", aliases=["np"],
        help="Show the current track.", usage="nowplaying")
    @commands.guild_only()
    async def nowplaying(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        if player is None or player.current is None:
            await ctx.send(embed=error_embed("I'm not playing anything right now."))
            return
        await ctx.send(embed=now_playing_embed(player.current))

    # ------------------------------------------------------------------
    @bot.command(
        name="loop", aliases=["repeat"],
        help="Repeat the current track, the whole queue, or turn off.",
        usage="loop [off|track|queue]",
        extras={"example": "loop queue"})
    @commands.guild_only()
    @_voice_control()
    async def loop(ctx: commands.Context, mode: str | None = None) -> None:
        player = _get_player(ctx)
        current = player.queue.mode
        labels = {
            wavelink.QueueMode.normal: "off",
            wavelink.QueueMode.loop: "track",
            wavelink.QueueMode.loop_all: "queue",
        }
        if mode is None:
            await ctx.send(embed=success_embed(
                f"Loop is **{labels[current]}**.", icon="🔁"
            ))
            return

        mode = mode.casefold()
        if mode in {"off", "none", "disable", "0"}:
            player.queue.mode = wavelink.QueueMode.normal
            await ctx.send(embed=success_embed("Loop is now **off**.", icon="🔁"))
        elif mode in {"track", "song", "one", "single", "current", "1"}:
            player.queue.mode = wavelink.QueueMode.loop
            await ctx.send(embed=success_embed("Looping **the current track**.", icon="🔁"))
        elif mode in {"queue", "all", "playlist", "2"}:
            player.queue.mode = wavelink.QueueMode.loop_all
            await ctx.send(embed=success_embed("Looping **the whole queue**.", icon="🔁"))
        else:
            raise commands.BadArgument("Mode must be `off`, `track` or `queue`.")

    # ------------------------------------------------------------------
    @bot.command(
        name="volume", aliases=["vol"],
        help="Show or set the volume (0–100).", usage="volume [0-100]",
        extras={"example": "volume 75"})
    @commands.guild_only()
    @_voice_control()
    async def volume(ctx: commands.Context, level: int | None = None) -> None:
        player = _get_player(ctx)
        if level is None:
            await ctx.send(embed=success_embed(
                f"Volume is **{player.volume}%**.", icon="🔊"
            ))
            return
        if not 0 <= level <= 100:
            raise commands.BadArgument("Volume must be between 0 and 100.")
        await player.set_volume(level)
        await ctx.send(embed=success_embed(f"Volume set to **{level}%**.", icon="🔊"))

    # ------------------------------------------------------------------
    @bot.command(
        name="leave", aliases=["disconnect"],
        help="Disconnect from voice.", usage="leave")
    @commands.guild_only()
    @_voice_control()
    async def leave(ctx: commands.Context) -> None:
        player = _get_player(ctx)
        blocker = _leave_blocker(player, ctx)
        if blocker:
            await ctx.send(embed=error_embed(blocker))
            return
        await player.disconnect()
        await ctx.send(embed=success_embed("Disconnected.", icon="👋"))