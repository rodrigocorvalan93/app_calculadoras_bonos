"""Serie diaria de acciones / CEDEARs / Merval (Delta - historico_acciones.parquet).

El archivo lo escribe el autosave del cierre (historico_writer._guardar_acciones,
también la captura headless) — una fila por (fecha, ticker) con cierre, OHLC,
VWAP y volumen — y, opcionalmente, el backfill (backend/tools/backfill_acciones).
Acá sólo lectura: cache por (path, mtime) → releer pasa a lo sumo una vez por
día y arma de una vez el índice por ticker (arrays numpy listos para el
price action); el resto de los hits es un lookup en memoria.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.services import deltapaths
from backend.services.historico_writer import ACCIONES_FILENAME, MERVAL_TICKER

PANEL_ORDEN = {"L": 0, "G": 1, "C": 2, "I": 3}
PANEL_LABEL = {"L": "Líderes", "G": "General", "C": "CEDEARs", "I": "Índice"}

_lock = threading.Lock()
_cache: Dict[str, Any] = {}      # {"sig": (path, mtime), "data": {...}|None}


def path() -> Optional[str]:
    d = deltapaths.historico_dir()
    if not d:
        return None
    p = os.path.join(d, ACCIONES_FILENAME)
    return p if os.path.isfile(p) else None


def signature() -> tuple:
    """(path, mtime) — cambia 1 vez por día (autosave) o tras un backfill.
    Clave del cache de render de la pestaña."""
    p = path()
    if p is None:
        return ("", 0.0)
    try:
        return (p, os.path.getmtime(p))
    except OSError:
        return (p, 0.0)


def _build(df: pd.DataFrame) -> Dict[str, Any]:
    df = df.copy()
    df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"]).dt.strftime("%Y-%m-%d")
    df = (df.dropna(subset=["ultimo"])
            .drop_duplicates(subset=["ticker", "fecha_hoy"], keep="last")
            .sort_values(["ticker", "fecha_hoy"]))
    by: Dict[str, Dict[str, Any]] = {}
    tiene_panel = "panel" in df.columns
    tiene_vol = "volumen" in df.columns
    for t, g in df.groupby("ticker", sort=False):
        t = str(t)
        by[t] = {
            "ticker": t,
            "panel": (str(g["panel"].iloc[-1]) if tiene_panel and pd.notna(g["panel"].iloc[-1]) else ""),
            "fechas": g["fecha_hoy"].tolist(),
            "ultimo": g["ultimo"].to_numpy(dtype=float),
            "volumen": (g["volumen"].to_numpy(dtype=float) if tiene_vol else None),
            "n": int(len(g)),
        }
    tickers = [{"ticker": e["ticker"], "panel": e["panel"],
                "panel_label": PANEL_LABEL.get(e["panel"], "Otros"),
                "n": e["n"], "ultima": e["fechas"][-1], "ultimo": float(e["ultimo"][-1])}
               for e in sorted(by.values(), key=lambda e: (PANEL_ORDEN.get(e["panel"], 9), e["ticker"]))]
    fechas = df["fecha_hoy"]
    return {"by": by, "tickers": tickers,
            "status": {"loaded": True, "n_tickers": len(by), "n_dias": int(fechas.nunique()),
                       "n_filas": int(len(df)), "dmin": str(fechas.min()), "dmax": str(fechas.max()),
                       "merval": MERVAL_TICKER in by}}


def _load() -> Optional[Dict[str, Any]]:
    p = path()
    if p is None:
        return None
    try:
        mtime = os.path.getmtime(p)
    except OSError:
        return None
    with _lock:
        if _cache.get("sig") == (p, mtime):
            return _cache.get("data")
    try:
        data = _build(pd.read_parquet(p))
    except Exception:  # noqa: BLE001 — un parquet ilegible no voltea la pestaña
        data = None
    with _lock:
        _cache["sig"] = (p, mtime)
        _cache["data"] = data
    return data


def refresh() -> None:
    with _lock:
        _cache.clear()


def status() -> Dict[str, Any]:
    d = _load()
    if not d:
        return {"loaded": False}
    return dict(d["status"])


def tickers() -> List[Dict[str, Any]]:
    """[{ticker, panel, panel_label, n, ultima, ultimo}] ordenados por panel
    (Líderes, General, CEDEARs, Índice) y nombre."""
    d = _load()
    return list(d["tickers"]) if d else []


def serie(ticker: str) -> Optional[Dict[str, Any]]:
    """{"fechas": [ISO], "ultimo": ndarray, "volumen": ndarray|None, "panel"}
    de un ticker (arrays compartidos: NO mutar)."""
    d = _load()
    if not d:
        return None
    return d["by"].get((ticker or "").strip().upper())


def merval() -> Optional[Dict[str, Any]]:
    return serie(MERVAL_TICKER)
