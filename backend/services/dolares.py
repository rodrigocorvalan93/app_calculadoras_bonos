"""Dólares — monitor FX para la pestaña /dolares y el riel lateral.

Construye sobre `services.fx` (mismo método implícito por bonos que el
legacy `OMSweb_app._build_implicit_fx_both`):

  USD (cable, …C) / USB (MEP, …D), por base sobre el book ARS:
    bid   = ARS.bid   / USDleg.offer
    offer = ARS.offer / USDleg.bid
    last  = ARS.last  / USDleg.last
    close = ARS.close / USDleg.close      → var% = last/close − 1

Canje (mismo bono, C vs D — `OMSweb_app._canje_rows_from_snap`):
    last  = C.last  / D.last
    bid   = C.offer / D.bid
    offer = C.bid   / D.offer

Oficial: A3500 (serie macro en memoria; variación día/día con SIGNO
correcto — verde sube / rojo baja) y, si hay `MAE_API_KEY`, SIOPEL en
vivo (UST$T Mayorista) vía un poller en background. El path de request
**nunca hace I/O**: todo lee de caches en memoria (store + historico +
snapshot MAE), así que cumple el target sub-50 ms p95.

Brecha = CCL / oficial − 1.   Canje (ref) = CCL / MEP − 1.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

from backend.cache import LockedTTLCache
from backend.services import fx as fx_svc, historico, marketdata_store, symbols as syms

logger = logging.getLogger("backend.dolares")

LEG_SUFFIX = fx_svc.LEG_SUFFIX  # {"USD": "C", "USB": "D"}

# Las tablas se recomputan barato del store; cacheamos unos segundos para
# que un refresh del riel + el de la pestaña no dupliquen el trabajo.
_cache = LockedTTLCache(maxsize=16, ttl=4)


def _pos(x: object) -> Optional[float]:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _var(last: Optional[float], close: Optional[float]) -> Optional[float]:
    """Variación fraccional last/close − 1 (None si falta algún lado)."""
    if last is None or not close:
        return None
    try:
        return last / close - 1.0
    except ZeroDivisionError:
        return None


# ── Tablas FX implícito por leg (USD cable / USB MEP) ──────────────────────

def _leg_rows(leg: str, plazo: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for lr in fx_svc.leg_table(leg, plazo):
        rows.append({
            "base": lr.base,
            "bid": lr.bid,
            "last": lr.last,
            "offer": lr.offer,
            "close": lr.close,
            "var_pct": _var(lr.last, lr.close),
            "vol_usd_m": lr.vol_usd_m,
        })
    rows.sort(key=lambda r: (r["vol_usd_m"] is None, -(r["vol_usd_m"] or 0.0)))
    return rows


def fx_rows(leg: str, plazo: str = "24hs") -> List[Dict[str, Any]]:
    """Tabla FX implícito de una pata, ordenada por volumen USD desc."""
    return _cache.get_or_compute(("leg", leg.upper(), plazo), lambda: _leg_rows(leg, plazo))


def _reference(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fila de referencia: mayor volumen USD; fallback al primer last válido."""
    priced = [r for r in rows if r["last"] is not None]
    if not priced:
        return None
    with_vol = [r for r in priced if r["vol_usd_m"] is not None]
    if with_vol:
        return max(with_vol, key=lambda r: r["vol_usd_m"] or 0.0)
    return priced[0]


# ── Canje (cable vs MEP, mismo bono) ───────────────────────────────────────

def _canje_rows(plazo: str) -> List[Dict[str, Any]]:
    """Canje CCL/MEP − 1 por bono (convención de la barra: positivo = cable
    más caro que el MEP). Last = CCL_last/MEP_last − 1 = D.last/C.last − 1.

    Bid/offer cruzan el book como un round-trip real (vendo una pata al
    bid, compro la otra al offer), igual que las puntas implícitas:
      bid   = CCL.bid  / MEP.offer − 1   (peor caso al armar el canje)
      offer = CCL.offer/ MEP.bid   − 1
    """
    store = marketdata_store.get_store()
    rows: List[Dict[str, Any]] = []
    for base in fx_svc.fx_bases():
        a = store.get(syms.md_symbol(base, plazo))        # pata ARS (pesos)
        c = store.get(syms.md_symbol(base + "C", plazo))  # pata cable (USD)
        d = store.get(syms.md_symbol(base + "D", plazo))  # pata MEP (USB)
        if a is None or c is None or d is None:
            continue
        a_bid, a_off, a_last, a_close = _pos(a.bid), _pos(a.offer), _pos(a.last), _pos(a.close)
        c_bid, c_off, c_last, c_close, c_vol = _pos(c.bid), _pos(c.offer), _pos(c.last), _pos(c.close), _pos(c.volume)
        d_bid, d_off, d_last, d_close, d_vol = _pos(d.bid), _pos(d.offer), _pos(d.last), _pos(d.close), _pos(d.volume)

        def _div(n: Optional[float], dd: Optional[float]) -> Optional[float]:
            return (n / dd) if (n is not None and dd not in (None, 0)) else None

        # CCL (pata C) y MEP (pata D) implícitos; el peso se cancela en el last.
        ccl_last, mep_last = _div(a_last, c_last), _div(a_last, d_last)
        ccl_close, mep_close = _div(a_close, c_close), _div(a_close, d_close)
        ccl_bid, mep_off = _div(a_bid, c_off), _div(a_off, d_bid)
        ccl_off, mep_bid = _div(a_off, c_bid), _div(a_bid, d_off)

        def _sp(num: Optional[float], den: Optional[float]) -> Optional[float]:
            return (num / den - 1.0) if (num is not None and den not in (None, 0)) else None

        last = _sp(ccl_last, mep_last)
        close = _sp(ccl_close, mep_close)
        bid = _sp(ccl_bid, mep_off)
        offer = _sp(ccl_off, mep_bid)
        if last is None and bid is None and offer is None:
            continue
        rows.append({
            "base": base,
            "bid": bid, "last": last, "offer": offer, "close": close,
            "var_pct": (last - close) if (last is not None and close is not None) else None,
            "vol_c_m": (c_vol / 1e6) if c_vol is not None else None,
            "vol_d_m": (d_vol / 1e6) if d_vol is not None else None,
        })
    rows.sort(key=lambda r: (r["vol_c_m"] is None, -(r["vol_c_m"] or 0.0)))
    return rows


def canje_rows(plazo: str = "24hs") -> List[Dict[str, Any]]:
    return _cache.get_or_compute(("canje", plazo), lambda: _canje_rows(plazo))


# ── Puntas crudas de un bono (para la calculadora de operación) ────────────

def puntas(base: str, leg: str, plazo: str = "24hs") -> Dict[str, Any]:
    """Puntas ARS y de la pata USD/USB de un mismo bono + TC implícitos.

    Sirve a la mini-calculadora: la operación cruzada compra/vende el VN
    del bono en ARS contra su pata dólar.
    """
    base = fx_svc._norm_base(base)
    suf = LEG_SUFFIX[leg.upper()]
    store = marketdata_store.get_store()
    ars = store.get(syms.md_symbol(base, plazo))
    usd = store.get(syms.md_symbol(base + suf, plazo))
    ab = _pos(ars.bid) if ars else None
    ao = _pos(ars.offer) if ars else None
    al = _pos(ars.last) if ars else None
    ub = _pos(usd.bid) if usd else None
    uo = _pos(usd.offer) if usd else None
    ul = _pos(usd.last) if usd else None
    return {
        "base": base, "leg": leg.upper(), "usd_code": base + suf, "plazo": plazo,
        "ars_bid": ab, "ars_offer": ao, "ars_last": al,
        "usd_bid": ub, "usd_offer": uo, "usd_last": ul,
        "bid": (ab / uo) if (ab is not None and uo is not None) else None,
        "last": (al / ul) if (al is not None and ul is not None) else None,
        "offer": (ao / ub) if (ao is not None and ub is not None) else None,
    }


# ── Oficial: SIOPEL (MAE, vía poller) con fallback A3500 (serie macro) ─────

_mae_lock = threading.Lock()
_mae_snap: Dict[str, Any] = {"rows": [], "ts": 0.0, "ust": None}


def _mae_enabled() -> bool:
    return bool(os.getenv("MAE_API_KEY"))


def _extract_ust(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """UST$T Mayorista (dólar oficial mayorista) del snapshot SIOPEL."""
    best = None
    for plazo in ("000", "001", None):
        for r in rows:
            if str(r.get("ticker")) != "UST$T" or str(r.get("segmento")) != "Mayorista":
                continue
            if plazo is not None and str(r.get("plazo")) != plazo:
                continue
            last = _pos(r.get("precioUltimo"))
            if last is None:
                continue
            var = r.get("variacion")
            try:
                var = float(var)
            except (TypeError, ValueError):
                var = None
            close = (last / (1.0 + var)) if (var is not None and (1.0 + var) != 0) else None
            best = {
                "last": last,
                "bid": _pos(r.get("precioCompra")),
                "offer": _pos(r.get("precioVenta")),
                "var_pct": var,
                "close": close,
                "volume": _pos(r.get("volumenOperado")),
                "hora": r.get("horaUltima"),
                "plazo": r.get("plazo"),
            }
            return best
    return best


def refresh_mae() -> bool:
    """Relee el snapshot MAE forex (sync, blocking) → cache. Sólo el poller
    o un refresh explícito lo llaman; nunca el path de request."""
    if not _mae_enabled():
        return False
    try:
        import indices  # legacy, correcto: trae el snapshot SIOPEL (requests)
        df = indices.fetch_mae_forex_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dolares] MAE snapshot falló: %s", exc)
        return False
    if df is None or getattr(df, "empty", True):
        return False
    try:
        rows = df.to_dict("records")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        return False
    ust = _extract_ust(rows)
    with _mae_lock:
        _mae_snap["rows"] = rows
        _mae_snap["ts"] = time.time()
        _mae_snap["ust"] = ust
    return True


# Spot mayorista ROFEX (símbolo crudo, no MERV-wrapped). Si está en el store
# (lo sembramos en el WS), da un oficial intradía que SÍ se mueve en ambos
# sentidos — al revés del A3500, que es un crawl casi siempre al alza.
SPOT_SYMBOL = "DLR/SPOT"


def _spot_official() -> Optional[Dict[str, Any]]:
    snap = marketdata_store.get_store().get(SPOT_SYMBOL)
    if snap is None:
        return None
    last = _pos(snap.last)
    if last is None:
        return None
    return {
        "source": "DLR/SPOT",
        "last": last,
        "close": _pos(snap.close),
        "bid": _pos(snap.bid),
        "offer": _pos(snap.offer),
        "var_pct": None,
        "volume": _pos(snap.volume),
        "hora": None,
    }


def _a3500_official() -> Dict[str, Any]:
    """Oficial desde la serie A3500 (en memoria). Variación día/día con
    signo correcto — arregla la flecha que sólo marcaba para arriba."""
    pts = historico.series_points("a3500").get("points") or []
    if not pts:
        return {"source": "none", "last": None, "close": None, "var_pct": None,
                "date": None, "bid": None, "offer": None, "volume": None}
    last_date, last = pts[-1]
    close = pts[-2][1] if len(pts) >= 2 else None
    return {
        "source": "A3500",
        "last": _pos(last),
        "close": _pos(close),
        "var_pct": _var(_pos(last), _pos(close)),
        "date": last_date,
        "bid": None, "offer": None, "volume": None,
    }


def _official_base() -> Dict[str, Any]:
    """Esqueleto del oficial con el set de claves COMPLETO — así el template
    nunca topa con una clave ausente, venga del path que venga."""
    return {"source": "none", "last": None, "close": None, "var_pct": None,
            "bid": None, "offer": None, "volume": None, "hora": None,
            "date": None, "siopel_n": 0}


def official_fx() -> Dict[str, Any]:
    """Dólar oficial mayorista. Prefiere SIOPEL (MAE en vivo) si está
    cacheado; si no, DLR/SPOT del store; si no, A3500 de la serie macro.
    Siempre lee de memoria y NUNCA lanza (devuelve el esqueleto si algo
    raro pasa) — es el núcleo compartido por la página y el riel."""
    out = _official_base()
    try:
        a3500 = _a3500_official()
        with _mae_lock:
            ust = _mae_snap.get("ust")
            n_rows = len(_mae_snap.get("rows") or [])
            ts = _mae_snap.get("ts") or 0.0
        out["siopel_n"] = n_rows
        out["date"] = a3500.get("date")

        # 1) SIOPEL (MAE en vivo).
        if ust and ust.get("last"):
            out.update({
                "source": "SIOPEL", "last": ust.get("last"),
                "close": ust.get("close") or a3500.get("close"),
                "bid": ust.get("bid"), "offer": ust.get("offer"),
                "var_pct": ust.get("var_pct"), "volume": ust.get("volume"),
                "hora": ust.get("hora"), "siopel_ts": ts,
            })
            if out["var_pct"] is None and a3500.get("close"):
                out["var_pct"] = _var(out["last"], a3500["close"])
            return out

        # 2) DLR/SPOT del store: oficial intradía bidireccional.
        spot = _spot_official()
        if spot:
            close = spot.get("close") or a3500.get("last")
            out.update({
                "source": "DLR/SPOT", "last": spot.get("last"), "close": close,
                "bid": spot.get("bid"), "offer": spot.get("offer"),
                "var_pct": _var(spot.get("last"), close), "volume": spot.get("volume"),
            })
            return out

        # 3) A3500 de la serie (día/día).
        out.update({
            "source": a3500.get("source") or "none", "last": a3500.get("last"),
            "close": a3500.get("close"), "var_pct": a3500.get("var_pct"),
            "bid": a3500.get("bid"), "offer": a3500.get("offer"),
            "volume": a3500.get("volume"),
        })
        return out
    except Exception:  # noqa: BLE001
        logger.exception("[dolares] official_fx falló; devuelvo esqueleto")
        return out


def siopel_rows() -> List[Dict[str, Any]]:
    with _mae_lock:
        return list(_mae_snap.get("rows") or [])


# ── Resumen para el riel lateral ───────────────────────────────────────────

def _summary_default(plazo: str) -> Dict[str, Any]:
    return {"plazo": plazo, "usd": None, "usb": None, "canje": None,
            "brecha": None, "brecha_var_pp": None, "oficial": _official_base(),
            "as_of": time.time()}


def summary(plazo: str = "24hs") -> Dict[str, Any]:
    """Payload del riel: USD/USB top-vol con variación, brecha y canje.
    Nunca lanza — el riel se carga en TODAS las pestañas."""
    try:
        usd = _reference(fx_rows("USD", plazo))
        usb = _reference(fx_rows("USB", plazo))
        cj_rows = canje_rows(plazo)
        # Canje: bono de mayor volumen cable (vol_c_m) con last válido.
        cj_priced = [r for r in cj_rows if r["last"] is not None]
        cj = None
        if cj_priced:
            cj_vol = [r for r in cj_priced if r["vol_c_m"] is not None]
            cj = max(cj_vol, key=lambda r: r["vol_c_m"] or 0.0) if cj_vol else cj_priced[0]
        ofi = official_fx()

        def _leg_payload(r: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not r:
                return None
            return {"base": r["base"], "last": r["last"], "var_pct": r["var_pct"],
                    "bid": r["bid"], "offer": r["offer"]}

        ccl = usd["last"] if usd else None
        ccl_close = usd["close"] if usd else None
        brecha = brecha_var_pp = None
        if ccl and ofi.get("last"):
            brecha = ccl / ofi["last"] - 1.0
            if ccl_close and ofi.get("close"):
                brecha_var_pp = brecha - (ccl_close / ofi["close"] - 1.0)

        canje = None
        if cj:
            canje = {"base": cj["base"], "last": cj["last"],   # last ya es CCL/MEP − 1
                     "bid": cj["bid"], "offer": cj["offer"], "var_pct": cj["var_pct"]}

        return {
            "plazo": plazo,
            "usd": _leg_payload(usd), "usb": _leg_payload(usb),
            "canje": canje, "brecha": brecha, "brecha_var_pp": brecha_var_pp,
            "oficial": ofi, "as_of": time.time(),
        }
    except Exception:  # noqa: BLE001
        logger.exception("[dolares] summary falló; devuelvo esqueleto")
        return _summary_default(plazo)


# ── Poller MAE (background, sólo si hay MAE_API_KEY) ───────────────────────

class _MaePoller:
    def __init__(self, interval: float = 20.0) -> None:
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(refresh_mae)
            except Exception:  # noqa: BLE001
                logger.exception("[dolares] poller MAE error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if not _mae_enabled():
            logger.info("[dolares] MAE_API_KEY ausente; SIOPEL deshabilitado (uso A3500)")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("[dolares] poller SIOPEL iniciado (cada %ss)", self.interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


_poller: Optional[_MaePoller] = None


def get_poller() -> _MaePoller:
    global _poller
    if _poller is None:
        _poller = _MaePoller()
    return _poller
