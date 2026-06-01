"""MAE Market Data (A3 Mercados) — fuente OTC/SIOPEL para cauciones, repo y
renta fija, complementaria al book de BYMA.

Mismo patrón que el snapshot de forex (`indices.fetch_mae_forex_snapshot`):
un poller en background refresca snapshots en memoria; el path de request
SÓLO lee de cache → cumple el target sub-50 ms y nunca pega a la API. Sin
`MAE_API_KEY` (o si la API falla) degrada a vacío y la app sigue andando.

La API es REST paginada (`pageNumber` + header `x-pagination`); cada fila es
una `EntidadCotizacion` (renta fija/cauciones) o `Repo`. OJO: renta fija trae
último/cierre/mín/máx/volumen/variación pero **NO** bid/offer/profundidad —
es cinta + volumen, complementaria al libro de BYMA (no lo reemplaza).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.mae")

_API_BASE = "https://api.mae.com.ar/MarketData/v1/mercado"
_TIMEOUT = 4
_MAX_PAGES = 25            # tope defensivo de paginación
_TTL = 20.0                # frescura del snapshot (s)

# Moneda MAE (anexo del doc) → leg de la app. X = Dólar Transferencia ≈ cable;
# D = USD (MEP/local); $ y T = pesos. Es un hint para elegir la fila correcta
# por bono; el match cae a "cualquier moneda" si no encuentra la preferida.
_LEG_MONEDAS = {"USD": ("X", "D"), "USB": ("D", "X"), "ARS": ("$", "T"), "native": ()}

_lock = threading.Lock()
_snap: Dict[str, Any] = {"rentafija": [], "cauciones": [], "repo": [],
                         "by_ticker": {}, "ts": 0.0}


def enabled() -> bool:
    return bool(os.getenv("MAE_API_KEY"))


def _num(x: object) -> Optional[float]:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ── Fetch (sólo el poller/refresh lo llama; nunca el path de request) ───────

def _get_all(path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Trae TODAS las páginas de un endpoint MAE. [] si no hay key o falla."""
    api_key = os.getenv("MAE_API_KEY")
    if not api_key:
        return []
    import requests  # lazy: legacy ya lo usa para forex
    headers = {"x-api-key": api_key}
    out: List[Dict[str, Any]] = []
    page = 1
    while page <= _MAX_PAGES:
        q = dict(params or {})
        q["pageNumber"] = page
        try:
            r = requests.get(f"{_API_BASE}/{path}", headers=headers, params=q, timeout=_TIMEOUT)
            if not r.ok:
                break
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[mae] %s page %d falló: %s", path, page, exc)
            break
        if not isinstance(data, list) or not data:
            break
        out.extend(d for d in data if isinstance(d, dict))
        # Paginación por header x-pagination (Page/TotalPages); si no está, corto.
        total_pages = None
        try:
            xp = r.headers.get("x-pagination")
            if xp:
                total_pages = int(json.loads(xp).get("TotalPages"))
        except Exception:  # noqa: BLE001
            total_pages = None
        if total_pages is None or page >= total_pages:
            break
        page += 1
    return out


def refresh() -> bool:
    """Relee los snapshots MAE (sync, blocking). Sólo el poller lo llama."""
    if not enabled():
        return False
    rf = _get_all("cotizaciones/rentafija")
    ca = _get_all("cotizaciones/cauciones")
    rp = _get_all("cotizaciones/repo")
    # Índice por ticker para el match cross-venue (renta fija).
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for row in rf:
        t = str(row.get("ticker") or "").strip().upper()
        if t:
            by_ticker.setdefault(t, []).append(row)
    with _lock:
        _snap["rentafija"], _snap["cauciones"], _snap["repo"] = rf, ca, rp
        _snap["by_ticker"] = by_ticker
        _snap["ts"] = time.time()
    logger.info("[mae] snapshot: %d rentafija, %d cauciones, %d repo", len(rf), len(ca), len(rp))
    return True


# ── Lectura (path de request: sólo cache en memoria) ────────────────────────

def status() -> Dict[str, Any]:
    with _lock:
        return {"enabled": enabled(), "ts": _snap["ts"],
                "n_rentafija": len(_snap["rentafija"]), "n_cauciones": len(_snap["cauciones"]),
                "n_repo": len(_snap["repo"]), "fresh": (time.time() - _snap["ts"]) < _TTL}


def cauciones_rows() -> List[Dict[str, Any]]:
    """Cauciones normalizadas (tasa/plazo/volumen), ordenadas por plazo."""
    with _lock:
        raw = list(_snap["cauciones"])
    rows = []
    for r in raw:
        rows.append({
            "plazo": str(r.get("plazo") or "").strip(),
            "moneda": r.get("moneda") or r.get("monedaCodigo") or "$",
            "tasa": _num(r.get("ultimatasa")) or _num(r.get("ultimaTasa")),
            "tasa_cierre": _num(r.get("precioCierreAnterior")) or _num(r.get("cierreAyer")),
            "var_pct": _num(r.get("variacion")),
            "volumen": _num(r.get("volumenAcumulado")) or _num(r.get("volumen")),
            "monto": _num(r.get("montoAcumulado")),
            "min": _num(r.get("precioMinimo")), "max": _num(r.get("precioMaximo")),
        })
    rows.sort(key=lambda x: _plazo_key(x["plazo"]))
    return rows


def repo_rows() -> List[Dict[str, Any]]:
    with _lock:
        raw = list(_snap["repo"])
    rows = []
    for r in raw:
        rows.append({
            "rueda": r.get("rueda"), "plazo": str(r.get("plazo") or "").strip(),
            "moneda": r.get("moneda") or "$",
            "tasa_pp": _num(r.get("tasaPP")), "tasa_ult": _num(r.get("ultimaTasa")),
            "tasa_apertura": _num(r.get("tasaApertura")),
            "tasa_min": _num(r.get("tasaMinima")) or _num(r.get("tasaMinimo")),
            "tasa_max": _num(r.get("tasaMaxima")) or _num(r.get("tasaMaximo")),
            "var_pct": _num(r.get("variacion")), "volumen": _num(r.get("volumen")),
            "cant_op": r.get("cantOperaciones"),
        })
    rows.sort(key=lambda x: _plazo_key(x["plazo"]))
    return rows


def _plazo_key(p: str) -> tuple:
    """Ordena plazos tipo '001','003','007' numéricamente; texto al final."""
    try:
        return (0, int(p))
    except (TypeError, ValueError):
        return (1, 0)


def match(code: str, leg: str = "native") -> Optional[Dict[str, Any]]:
    """Mejor fila MAE de renta fija para un bono nuestro (best-effort).

    Matchea por ticker == código base (sin sufijo C/D); si el `leg` sugiere una
    moneda (cable→X, MEP→D), prioriza esa; si no, la de mayor volumen. Devuelve
    último/var/mín/máx/volumen/monto/segmento/moneda — NO trae bid/offer.
    """
    if not code:
        return None
    base = code[:-1].upper() if code[-1:] in ("C", "D") else code.upper()
    with _lock:
        rows = list(_snap["by_ticker"].get(base, []))
    if not rows:
        return None
    pref = _LEG_MONEDAS.get(leg, ())
    pool = [r for r in rows if str(r.get("moneda")) in pref] or rows
    best = max(pool, key=lambda r: _num(r.get("volumenAcumulado")) or 0.0)
    return {
        "ticker": best.get("ticker"), "segmento": best.get("segmento"),
        "moneda": best.get("moneda"), "plazo": best.get("plazo"),
        "last": _num(best.get("precioUltimo")),
        "close": _num(best.get("precioCierreAnterior")),
        "var_pct": _num(best.get("variacion")),
        "min": _num(best.get("precioMinimo")), "max": _num(best.get("precioMaximo")),
        "volumen": _num(best.get("volumenAcumulado")),   # VN nominal
        "monto": _num(best.get("montoAcumulado")),       # $ operado
    }


def volume_for(code: str, leg: str = "native") -> Optional[float]:
    """Volumen MAE (VN nominal) del bono en su leg — para sumar al de BYMA."""
    m = match(code, leg)
    return m["volumen"] if m else None


# ── Poller (background, sólo si hay MAE_API_KEY) ────────────────────────────

class _Poller:
    def __init__(self, interval: float = 20.0) -> None:
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(refresh)
            except Exception:  # noqa: BLE001
                logger.exception("[mae] poller error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if not enabled():
            logger.info("[mae] MAE_API_KEY ausente; renta fija/cauciones/repo deshabilitado")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("[mae] poller iniciado (cada %ss)", self.interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


_poller: Optional[_Poller] = None


def get_poller() -> _Poller:
    global _poller
    if _poller is None:
        _poller = _Poller()
    return _poller
