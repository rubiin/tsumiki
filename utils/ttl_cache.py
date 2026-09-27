"""A bounded TTL cache, shared by the stat cache and the plugin session cache.

Both stored ``key -> (expiry, value)`` and evicted the oldest entry past the
cap; only the clock and the locking differed.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

#: Sentinel returned by :meth:`TTLCache.get` on a miss, so a cached ``None`` hits.
CACHE_MISS = object()


class TTLCache:
    """Key -> value with a per-entry expiry and a bounded size.

    Expiry uses :func:`time.monotonic`, so an NTP step or DST change cannot
    mislabel an entry. Past *maxsize*, expired entries go first, then oldest.
    """

    def __init__(
        self,
        maxsize: int = 128,
        default_ttl: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[Any, tuple[float, Any]] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get(self, key: Any, default: Any = CACHE_MISS) -> Any:
        """Return the live value for *key*, or *default* if absent or expired."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return default
            expires_at, value = entry
            if expires_at <= self._clock():
                del self._entries[key]
                return default
            return value

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        """Store *value* under *key*; a ``None``/non-positive *ttl* is a no-op."""
        ttl = self.default_ttl if ttl is None else ttl
        if ttl is None or ttl <= 0:
            return
        with self._lock:
            self._entries[key] = (self._clock() + ttl, value)
            if len(self._entries) <= self.maxsize:
                return
            self._evict_locked()

    def get_or_produce(
        self, key: Any, producer: Callable[[], Any], ttl: float | None = None
    ) -> Any:
        """Return the live value for *key*, calling *producer* on a miss.

        *producer* runs outside the lock, so an expensive one does not block
        other threads. Racing threads on the same cold key can both produce.
        """
        value = self.get(key)
        if value is not CACHE_MISS:
            return value
        value = producer()
        self.put(key, value, ttl=ttl)
        return value

    def invalidate(self, key: Any) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _evict_locked(self) -> None:
        """Drop expired entries, then the oldest, until back under the cap."""
        now = self._clock()
        for expired in [k for k, (exp, _) in self._entries.items() if exp <= now]:
            del self._entries[expired]
        while len(self._entries) > self.maxsize:
            self._entries.pop(next(iter(self._entries)))
