"""Small TTL cache with a LOCK-FREE hit path.

El hit es el 99 % de los accesos (curvas anchas: ~700 lecturas por request,
abanicadas en varios threads del pool). `cachetools.TTLCache` exige lock en
TODA operación (su `get` hace housekeeping mutante), así que el lock se volvía
un punto de contención bajo el fan-out. Acá la lectura es un `dict.get` plano
—atómico bajo el GIL en CPython— con chequeo de expiración manual; el lock
sólo se toma para escribir/evictar. Misma API pública que antes
(`get_or_compute / invalidate / clear`).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Hashable, Tuple


class LockedTTLCache:
    def __init__(self, maxsize: int, ttl: int) -> None:
        self._ttl = float(ttl)
        self._maxsize = int(maxsize)
        self._store: Dict[Hashable, Tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get_or_compute(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        now = time.monotonic()
        ent = self._store.get(key)            # lock-free: dict.get es atómico (GIL)
        if ent is not None and ent[1] > now:
            return ent[0]
        value = factory()
        # `None` no se cachea (mismo efecto que el wrapper anterior: se
        # recomputa la próxima) — ningún productor cachea None de todos modos.
        if value is not None:
            with self._lock:
                self._store[key] = (value, now + self._ttl)
                if len(self._store) > self._maxsize:
                    self._evict_locked(now)
        return value

    def _evict_locked(self, now: float) -> None:
        # Primero los expirados; si aún sobra, el bloque de menor expiry.
        for k in [k for k, (_, exp) in self._store.items() if exp <= now]:
            self._store.pop(k, None)
        over = len(self._store) - self._maxsize
        if over > 0:
            oldest = sorted(self._store, key=lambda k: self._store[k][1])
            for k in oldest[: over + self._maxsize // 10 + 1]:
                self._store.pop(k, None)

    def touch(self, key: Hashable) -> bool:
        """Extiende el TTL de una entrada YA presente, SIN recomputar. Para un
        keep-warm gentil (no compite por el GIL recalculando). True si estaba."""
        now = time.monotonic()
        ent = self._store.get(key)
        if ent is None or ent[1] <= now:
            return False
        with self._lock:
            cur = self._store.get(key)
            if cur is None:
                return False
            self._store[key] = (cur[0], now + self._ttl)
        return True

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
