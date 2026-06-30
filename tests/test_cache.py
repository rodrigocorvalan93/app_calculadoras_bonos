"""Tests for backend.cache.LockedTTLCache.

Foco: la estampida (thundering herd). Cuando una entrada vence y N threads la
piden a la vez, sólo UNO debe ejecutar el `factory` pesado; el resto espera y
lee el resultado fresco. El hit path sigue siendo lock-free.
"""
from __future__ import annotations

import threading
import time

from backend.cache import LockedTTLCache


def test_compute_once_under_concurrent_miss() -> None:
    cache = LockedTTLCache(maxsize=16, ttl=60)
    calls = {"n": 0}
    barrier = threading.Barrier(20)

    def factory():
        # Cuenta cada cómputo real y simula trabajo (~5 ms de TIR Newton).
        calls["n"] += 1
        time.sleep(0.005)
        return 42

    def worker():
        barrier.wait()                      # todos arrancan a la vez → miss simultáneo
        assert cache.get_or_compute("k", factory) == 42

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1                  # UN solo cómputo pese a 20 misses concurrentes


def test_recompute_after_ttl_expiry() -> None:
    cache = LockedTTLCache(maxsize=4, ttl=0)   # TTL 0 → siempre vencida
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return calls["n"]

    a = cache.get_or_compute("k", factory)
    b = cache.get_or_compute("k", factory)
    assert (a, b) == (1, 2)                  # con TTL 0 recomputa cada vez (sin cachear de más)


def test_hit_path_does_not_recompute() -> None:
    cache = LockedTTLCache(maxsize=4, ttl=60)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return "v"

    for _ in range(100):
        assert cache.get_or_compute("k", factory) == "v"
    assert calls["n"] == 1                    # 1 cómputo, 99 hits lock-free


def test_none_is_not_cached() -> None:
    cache = LockedTTLCache(maxsize=4, ttl=60)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return None

    cache.get_or_compute("k", factory)
    cache.get_or_compute("k", factory)
    assert calls["n"] == 2                    # None nunca se cachea → recomputa
