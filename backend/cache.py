"""Small TTLCache wrapper with a single lock.

Phase 1 only needs a metrics cache, but the wrapper is generic so later
phases (curves warmup, market snapshot) can reuse it.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Hashable

from cachetools import TTLCache


class LockedTTLCache:
    def __init__(self, maxsize: int, ttl: int) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get_or_compute(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        value = factory()
        with self._lock:
            self._cache[key] = value
        return value

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
