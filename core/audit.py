import asyncio
import logging
import time

log = logging.getLogger("sekai.audit")

RECENT_WINDOW = 10.0
WAIT_TIMEOUT = 2.0

# (guild id, action name, target id) -> (monotonic time, entry). Entries can
# arrive before or after the raw gateway event they belong to, so both orders
# are cached/bridged here instead of querying the rate-limited audit endpoint.
_recent: dict[tuple[int, str, int], tuple[float, object]] = {}
_waiters: dict[tuple[int, str, int], list[asyncio.Future]] = {}


def _key(guild, action, target_id) -> tuple[int, str, int] | None:
    if guild is None or target_id is None:
        return None
    name = getattr(action, "name", str(action))
    return (guild.id, name, target_id)


def entry_key(entry) -> tuple[int, str, int] | None:
    target_id = getattr(entry, "_target_id", None)
    if target_id is None:
        # Some entries carry a null target id; accessing .target would make
        # discord.py's converters build Object(id=None) and raise TypeError.
        cached = getattr(entry, "__dict__", {}).get("target")
        target_id = getattr(cached, "id", None)
    return _key(getattr(entry, "guild", None), getattr(entry, "action", None), target_id)


def deliver(entry) -> None:
    key = entry_key(entry)
    if key is None:
        return
    _recent[key] = (time.monotonic(), entry)
    for future in _waiters.pop(key, []):
        if not future.done():
            future.set_result(entry)


def _prune(now: float) -> None:
    for key, (stamp, _) in list(_recent.items()):
        if now - stamp > RECENT_WINDOW:
            _recent.pop(key, None)


def available(guild) -> bool:
    me = getattr(guild, "me", None)
    permissions = getattr(me, "guild_permissions", None)
    return bool(getattr(permissions, "view_audit_log", False))


async def wait_for_entry(
    guild, action, target_id, *, timeout: float | None = None
):
    """Return the audit entry for an action, waiting briefly if it is in flight."""
    if target_id is None or not available(guild):
        return None
    key = _key(guild, action, target_id)
    if key is None:
        return None
    if timeout is None:
        timeout = WAIT_TIMEOUT

    now = time.monotonic()
    _prune(now)
    recent = _recent.get(key)
    if recent is not None:
        return recent[1]

    future = asyncio.get_running_loop().create_future()
    waiters = _waiters.setdefault(key, [])
    waiters.append(future)
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        if future in waiters:
            waiters.remove(future)
        if not waiters:
            _waiters.pop(key, None)
