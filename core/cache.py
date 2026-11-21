"""Small hand-rolled caches used instead of pulling in cachetools/redis.

Everything here assumes single-threaded asyncio use: no locks are taken.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Size-bounded TTL cache with LRU eviction."""

    def __init__(
        self,
        maxsize: int = 1024,
        ttl: float = 300.0,
        *,
        clock: Callable[[], float] = time.monotonic) -> None:
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._maxsize = max(1, int(maxsize))
        self._ttl = float(ttl)
        self._clock = clock
        self.hits = 0
        self.misses = 0

    def _alive(self, expires: float, now: float) -> bool:
        return expires > now

    def get(self, key: K, default: V | None = None) -> V | None:
        item = self._data.get(key)
        now = self._clock()
        if item is None or not self._alive(item[0], now):
            if item is not None:
                del self._data[key]
            self.misses += 1
            return default
        self._data.move_to_end(key)
        self.hits += 1
        return item[1]

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        lifetime = self._ttl if ttl is None else float(ttl)
        now = self._clock()
        self._data[key] = (now + lifetime, value)
        self._data.move_to_end(key)
        self.sweep(now)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def pop(self, key: K, default: V | None = None) -> V | None:
        item = self._data.pop(key, None)
        if item is None or not self._alive(item[0], self._clock()):
            return default
        return item[1]

    def delete(self, key: K) -> bool:
        return self._data.pop(key, None) is not None

    def sweep(self, now: float | None = None) -> int:
        moment = self._clock() if now is None else now
        stale = [key for key, (expires, _) in self._data.items() if expires <= moment]
        for key in stale:
            del self._data[key]
        return len(stale)

    def clear(self) -> None:
        self._data.clear()

    def stats(self) -> dict[str, int | float]:
        self.sweep()
        return {
            "size": len(self._data),
            "maxsize": self._maxsize,
            "hits": self.hits,
            "misses": self.misses,
            "ttl": self._ttl,
        }

    def __contains__(self, key: object) -> bool:
        item = self._data.get(key)  # type: ignore[arg-type]
        if item is None:
            return False
        if not self._alive(item[0], self._clock()):
            del self._data[key]  # type: ignore[arg-type]
            return False
        return True

    def __len__(self) -> int:
        self.sweep()
        return len(self._data)


class SlidingWindowLimiter:
    """Counts hits per key inside a rolling window, backed by TTLCache."""

    def __init__(self, limit: int, window: float, *, maxsize: int = 4096) -> None:
        self.limit = max(1, int(limit))
        self.window = float(window)
        self._hits: TTLCache[Hashable, list[float]] = TTLCache(
            maxsize=maxsize, ttl=self.window
        )

    def allow(self, key: Hashable) -> bool:
        now = time.monotonic()
        recent = [
            stamp
            for stamp in self._hits.get(key, [])
            if now - stamp < self.window
        ]
        if len(recent) >= self.limit:
            self._hits.set(key, recent)
            return False
        recent.append(now)
        self._hits.set(key, recent)
        return True
