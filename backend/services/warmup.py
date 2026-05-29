"""Background warmup daemon — Phase 2.

Two cold-path costs make the first request after boot slow; this daemon
absorbs both off the request path:

1. Calc-engine prime. The first `compute_metrics` ever triggers the lazy
   `indices.main()` / `rentafija.inputs` load (the multi-second BCRA
   backup read). We force it once at startup so neither the first YAS
   calc nor the first curve visit pays it. This runs even with no broker
   (dev), which is the mitigation `backend/README.md` promised for Fase 2.

2. Curve cache warm. The curves table computes one TIREA per bond; a wide
   curve (corp_hdmep / corp_hdcable) is ~1.4 s cold. We sweep the curve
   buckets in priority order and pre-fill `pricing.metrics_for_market_price`
   for every bond that has a live price, so the table hits the 20 s metrics
   cache instead of paying the TIR math on the first visit.

Ported from `OMSweb_app._curves_warmup_loop` / `_CURVES_WARMUP_KEYS`,
adapted to the async lifespan: an asyncio task drives the loop and the
CPU-bound calc is fanned out across a small thread pool so it never blocks
the event loop or starves request handling. When the store is empty
(broker offline) the sweep is a cheap no-op and the loop backs off.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from backend.services import (
    bond_universe,
    curves,
    marketdata_store,
    pricing,
    symbols as syms,
)

logger = logging.getLogger("backend.warmup")


# Priority order: critical/cheap first (cer/lecap/tamar), then sovereign
# USD / duals, then corporates last — corp_hdmep / corp_hdcable are the
# slowest cold (complex USD cashflows). Same ordering the legacy used so a
# user who opens Curvas in the first seconds finds at least cer/lecap warm.
WARMUP_CURVE_KEYS = (
    "cer", "lecap", "tamar",
    "globales", "bonares", "dolarlinked", "bopreales",
    "dualfija", "dualcer", "dualtamar",
    "cerproy", "todos_ars_proyectado",
    "corp_badlar", "corp_tasafija", "corp_uva",
    "corp_tamar", "corp_dlk", "corp_hdmep", "corp_hdcable",
)


# Small, dedicated pool. Kept modest so background warming never starves
# the request handlers (the < 50 ms p95 target). The per-bond TIR is the
# only CPU-bound bit; cache hits return immediately.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="warmup")


def prime_calc_engine() -> float:
    """Force the lazy `indices.main()` / `rentafija.inputs` load once.

    Runs a single throwaway `compute_metrics` (synthetic price, no live
    data needed) on a representative bond so the heavy global state is
    resident before the first real request. Sequential by design — the
    lazy load must happen under one thread, not raced by the fan-out.
    Returns elapsed seconds (0.0 if nothing could be primed).
    """
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    # Prefer a cheap LECAP; fall back to any code in any curve, then the
    # raw universe (covers a universe with no curve membership at all).
    candidates: List[str] = list(table.get("lecap") or [])
    if not candidates:
        for key in WARMUP_CURVE_KEYS:
            candidates = list(table.get(key) or [])
            if candidates:
                break
    if not candidates:
        candidates = list(bond_universe.all_codes()[:5])

    t0 = time.perf_counter()
    for code in candidates[:5]:
        try:
            pricing.compute_metrics(code, mode="precio", value=100.0, include_cashflows=False)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[warmup] prime via %s failed: %s", code, exc)
            continue
        elapsed = time.perf_counter() - t0
        logger.info("[warmup] calc engine primed via %s in %.2fs", code, elapsed)
        return elapsed
    logger.warning("[warmup] could not prime calc engine (no usable bond)")
    return 0.0


def _warm_code(code: str, plazo: str) -> bool:
    """Populate the metrics cache for one code at its current live price.

    Mirrors the cached path of `routes.curves._row_for_code` exactly so
    the cache key lines up: same `md_symbol`, same `snap.last`, settle
    defaulted to None. Returns True if a live price was present and warmed.
    """
    snap = marketdata_store.get_store().get(syms.md_symbol(code, plazo))
    if snap is None or snap.last is None:
        return False
    try:
        pricing.metrics_for_market_price(code, snap.last)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("[warmup] warm %s failed: %s", code, exc)
        return False


async def warm_curves_once(plazo: str = "24hs") -> Dict[str, int]:
    """One sweep over every curve in priority order. Fans the per-bond TIR
    out across `_pool`; cache hits make steady-state sweeps cheap. Returns
    `{curves, codes, warmed}` counts for logging / stats."""
    codes_by_curve = curves.build_curve_codes()
    loop = asyncio.get_running_loop()
    total = warmed = touched_curves = 0
    for key in WARMUP_CURVE_KEYS:
        codes = codes_by_curve.get(key) or []
        if not codes:
            continue
        touched_curves += 1
        total += len(codes)
        results = await asyncio.gather(
            *(loop.run_in_executor(_pool, _warm_code, c, plazo) for c in codes)
        )
        warmed += sum(1 for r in results if r)
    return {"curves": touched_curves, "codes": total, "warmed": warmed}


class WarmupDaemon:
    """Owns the asyncio task: prime once, then keep the curve cache warm."""

    def __init__(self, plazo: str = "24hs", interval: float = 8.0) -> None:
        self.plazo = plazo
        self.interval = max(float(interval), 1.0)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._primed = False
        self._stats: Dict[str, float | int] = {
            "sweeps": 0,
            "last_warmed": 0,
            "prime_seconds": 0.0,
        }

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="warmup")
        logger.info(
            "[warmup] daemon started (plazo=%s, interval=%.0fs)",
            self.plazo, self.interval,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("[warmup] daemon stopped")

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            self._stats["prime_seconds"] = await loop.run_in_executor(_pool, prime_calc_engine)
            self._primed = True
        except Exception:  # noqa: BLE001
            logger.exception("[warmup] prime step failed")

        while not self._stop.is_set():
            has_data = marketdata_store.get_store().stats().get("symbols", 0) > 0
            wait = self.interval if has_data else self.interval * 4
            if has_data:
                t0 = time.perf_counter()
                try:
                    res = await warm_curves_once(self.plazo)
                    self._stats["sweeps"] = int(self._stats["sweeps"]) + 1
                    self._stats["last_warmed"] = res["warmed"]
                    if res["warmed"]:
                        logger.info(
                            "[warmup] sweep %d: %d/%d codes warm in %.2fs",
                            self._stats["sweeps"], res["warmed"], res["codes"],
                            time.perf_counter() - t0,
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("[warmup] sweep failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
                break  # stop set during the wait
            except asyncio.TimeoutError:
                pass

    def stats(self) -> Dict[str, float | int | bool]:
        s: Dict[str, float | int | bool] = dict(self._stats)
        s["primed"] = self._primed
        s["running"] = bool(self._task and not self._task.done())
        return s


_daemon: Optional[WarmupDaemon] = None


def get_daemon() -> WarmupDaemon:
    """Process-wide singleton, configured from settings."""
    global _daemon
    if _daemon is None:
        from backend.config import settings  # noqa: WPS433  (avoid import cycle at module load)

        _daemon = WarmupDaemon(
            plazo=settings.default_plazo,
            interval=settings.warmup_interval_seconds,
        )
    return _daemon
