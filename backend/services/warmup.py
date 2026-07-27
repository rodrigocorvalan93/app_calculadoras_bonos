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
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

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
    "dualfija", "dualcer", "dualdlk", "dualtamar",
    "cerproy", "todos_ars_proyectado",
    "corp_badlar", "corp_tasafija", "corp_uva",
    "corp_tamar", "corp_dlk", "corp_hdmep", "corp_hdcable",
)


# Small, dedicated pool. Kept modest so background warming never starves
# the request handlers (the < 50 ms p95 target). The per-bond TIR is the
# only CPU-bound bit; cache hits return immediately.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="warmup")

# ── Refresh vespertino del A3500 oficial ──────────────────────────────────
# El BCRA publica el A3500 del día ~16:00-17:00. La app carga los índices al
# BOOT (para no pagar nada por request), así que un server levantado a la
# mañana valuaba los DLK toda la tarde con el A3500 de AYER aunque el de hoy
# ya estuviera publicado. Dentro de esta ventana reintentamos el refresh de
# índices (BCRA + backup json) cada _A3500_RETRY hasta ver publicado el de
# hoy — todo en el pool, jamás en el path de request ni en el arranque.
# Bonus: el autosave de 17:01 valúa los DLK con el oficial fresco, y el riel
# muestra la fecha del A3500 girar a hoy.
_A3500_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
_A3500_WINDOW = ((16, 0), (19, 0))     # [desde, hasta) hora BA
_A3500_RETRY_SECONDS = 900.0           # cada 15 min: alcanza de sobra y no molesta


def a3500_refresh_due(now_ba: datetime, last_iso: Optional[str]) -> bool:
    """Pura (testeable): ¿corresponde intentar el refresh vespertino?
    Día hábil + dentro de la ventana + el último A3500 publicado es viejo."""
    if now_ba.weekday() >= 5:
        return False
    t = (now_ba.hour, now_ba.minute)
    if not (_A3500_WINDOW[0] <= t < _A3500_WINDOW[1]):
        return False
    return (last_iso or "") < now_ba.date().isoformat()


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


def prime_aux_loaders() -> None:
    """Absorbe los loads de disco perezosos que, si no, corrían en el primer
    request de su pestaña (bloqueando el event loop):

      - `delta_especies` y `positions`: `pd.read_excel` bajo lock.
      - `credito`: lee `credit_scores.json` + scorea todos los emisores.

    Cada uno es idempotente y auto-guardado; los llamamos en el pool de warmup
    al boot así la primera visita a YAS / Posiciones / Créditos ya los encuentra
    cargados. Defensivo: un fallo acá nunca debe tumbar el warmup."""
    # Import perezoso: estos módulos arrastran pandas/OMScredit, que no queremos
    # cargar al importar warmup.
    from backend.services import credito, delta_especies, positions

    for label, loader in (
        ("delta_especies", delta_especies.ensure_loaded),
        ("positions", positions.ensure_loaded),
        ("credito", credito._ensure),
    ):
        try:
            loader()
            logger.info("[warmup] %s primed", label)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[warmup] %s prime failed: %s", label, exc)


def _warm_code(code: str, plazo: str) -> bool:
    """Populate the metrics cache for one code at its current live price.

    Mirrors the cached path of `routes.curves._row_for_code` exactly so
    the cache key lines up: same `md_symbol`, same precio de referencia y el
    MISMO settle explícito de la pestaña (`settlement_date_str(plazo)`) — si
    acá fuera None y la tabla pasara la fecha, la key no coincidiría y el
    warmup calentaría entradas que nadie lee. Returns True if warmed.

    Clave para curvas anchas y COMBINADAS: la tabla usa `last` si el bono
    operó hoy, y si no **cae a `close`**. Antes sólo calentábamos `last`, así
    que los bonos que no operaron (ilíquidos: muchos corporativos) quedaban
    fríos en CADA render — ~18 ms de cálculo por bono. Ahora calentamos el
    precio de referencia REAL (last o, si no hay, close), más bid/offer para
    el libro. Eso saca el cold recurrente de las combinadas de ilíquidos.
    """
    snap = marketdata_store.get_store().get(syms.md_symbol(code, plazo))
    if snap is None:
        return False
    if snap.last is not None:
        prices = [snap.last, snap.bid, snap.offer]
    elif snap.close is not None:
        prices = [snap.close]                 # fallback que usa la tabla (CL)
    else:
        return False
    warmed = False
    settle = pricing.settlement_date_str(plazo)
    for px in prices:
        if px is None:
            continue
        try:
            pricing.metrics_for_market_price(code, px, settle)
            warmed = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[warmup] warm %s @ %s failed: %s", code, px, exc)
    return warmed


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
        self._esc_warmed = False        # escenario: 1 warm frío al boot, luego touch
        self._last_index_day: Optional[date] = None   # rollover → refresca inputs (CER/UVA/A3500)
        self._a3500_last_try = 0.0      # rate-limit del refresh vespertino del A3500
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
            self._last_index_day = datetime.now(_A3500_TZ).date()   # el prime cargó los índices de HOY (fecha BA)
        except Exception:  # noqa: BLE001
            logger.exception("[warmup] prime step failed")

        # Loads de disco perezosos (delta_especies / positions / credito): off
        # the loop, así su primer request no paga el pd.read_excel / scoring.
        try:
            await loop.run_in_executor(_pool, prime_aux_loaders)
        except Exception:  # noqa: BLE001
            logger.exception("[warmup] aux loaders prime failed")

        while not self._stop.is_set():
            await self._maybe_refresh_indices()          # rollover de fecha → CER/UVA/A3500 frescos
            await self._maybe_refresh_a3500_oficial()    # 16-19 h: A3500 del día apenas el BCRA lo publica
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
                try:                                # escenario: warm frío 1 vez (boot),
                    from backend.routes.escenario import warm_escenario_default  # luego touch
                    first = not self._esc_warmed
                    ew = await warm_escenario_default(self.plazo, refresh_only=not first)
                    self._esc_warmed = True
                    if ew:
                        logger.debug("[warmup] escenario %s: %d bonos",
                                     "warm" if first else "touch", ew)
                except Exception:  # noqa: BLE001
                    logger.exception("[warmup] escenario warm failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
                break  # stop set during the wait
            except asyncio.TimeoutError:
                pass

    async def _maybe_refresh_indices(self) -> None:
        """En rollover de fecha, re-corre indices.main() para refrescar
        rentafija.inputs (CER/UVA/A3500/TAMAR). Sin esto un server de varios días
        price con los índices del boot (drift ~0,05-0,1%/día en los ajustados).
        HTTP bloqueante → al pool. Best-effort: un fallo reintenta al día siguiente
        (o en el próximo ciclo si `refresh` devolvió False)."""
        today = datetime.now(_A3500_TZ).date()   # rollover por fecha BA, no la del server
        if self._last_index_day is None:      # aún no primó; el prime lo siembra
            return
        if today == self._last_index_day:
            return
        try:
            import rentafija
            loop = asyncio.get_running_loop()
            ok = await loop.run_in_executor(_pool, rentafija.inputs.refresh)
            if ok:
                self._last_index_day = today
                # Floaters: el cupón se congela en Bono.__init__, el refresh de
                # inputs NO lo actualiza — recomputarlo acá o las TAMAR/BADLAR
                # siguen con la proyección del boot. En el pool (hace pandas).
                nf = await loop.run_in_executor(_pool, pricing.refresh_floater_coupons)
                # Los caches de métricas keyean por día + fingerprint del índice
                # (ver pricing): las TIRs viejas se recalculan solas con inputs
                # ya fresco.
                logger.info("[warmup] índices refrescados por rollover de fecha (%s); "
                            "%d cupones floater recomputados", today, nf)
            else:
                logger.warning("[warmup] refresh de índices sin datos; reintenta en el próximo ciclo")
        except Exception:  # noqa: BLE001
            logger.exception("[warmup] refresh de índices falló")

    async def _maybe_refresh_a3500_oficial(self) -> None:
        """Ventana vespertina (16-19 h BA, hábiles): reintenta el refresh de
        índices cada 10 min hasta que el BCRA publique el A3500 de HOY. El
        fetch corre en el pool (I/O de red, nunca en el loop) y al lograrlo
        re-lee la serie macro → el riel muestra la fecha nueva y el cache de
        métricas (keyeado por índice) recalcula los DLK solo."""
        from backend.services import historico

        try:
            pts = historico.series_points("a3500").get("points") or []
        except Exception:  # noqa: BLE001
            return
        last_iso = pts[-1][0] if pts else None
        if not a3500_refresh_due(datetime.now(_A3500_TZ), last_iso):
            return
        if time.monotonic() - self._a3500_last_try < _A3500_RETRY_SECONDS:
            return
        self._a3500_last_try = time.monotonic()
        try:
            import rentafija
            loop = asyncio.get_running_loop()
            ok = await loop.run_in_executor(_pool, rentafija.inputs.refresh)
            if not ok:
                logger.info("[warmup] A3500 vespertino: BCRA sin dato nuevo todavía; reintento en %.0f min",
                            _A3500_RETRY_SECONDS / 60)
                return
            # Índices frescos → re-leer el backup para el riel / series macro.
            snap = await loop.run_in_executor(_pool, historico.refresh)
            pts = (snap.get("series", {}).get("a3500") or {}).get("points") or []
            nuevo = pts[-1] if pts else None
            if nuevo and nuevo[0] == datetime.now(_A3500_TZ).date().isoformat():
                logger.info("[warmup] A3500 OFICIAL del día publicado: %s = %s", nuevo[0], nuevo[1])
            else:
                logger.info("[warmup] índices refrescados; A3500 de hoy aún no publicado")
        except Exception:  # noqa: BLE001
            logger.exception("[warmup] refresh vespertino del A3500 falló")

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
