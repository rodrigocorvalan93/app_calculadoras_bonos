"""Series diarias FX + caución (Delta - historico_fx) para Históricos.

El archivo lo escribe el autosave del cierre (historico_writer._guardar_fx):
UNA fila por día. Acá sólo lectura, con cache por (path, mtime) — releer pasa
a lo sumo una vez por día (cuando el autosave escribió) y cuesta ~ms sobre un
archivo de cientos de filas; el resto de los hits son un lookup en memoria.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.services import deltapaths
from backend.services.historico_writer import FX_FILENAME

# Especificación de cada serie del archivo. `escala` lleva el valor crudo a la
# unidad mostrada (el canje se guarda como fracción → ×100 para %); las TNA de
# caución ya vienen en puntos de % desde el feed (31.0 = 31%). `plazo_col`
# acompaña a las series de caución para que la tabla muestre 1D/3D/4D.
SERIES: List[Dict[str, Any]] = [
    {"key": "caucion_tna_vwap", "col": "caucion_tna_vwap", "plazo_col": "caucion_plazo_d",
     "label": "Caución $ o/n — TNA VWAP", "unit": "%", "dec": 2, "escala": 1.0},
    {"key": "caucion_tna", "col": "caucion_tna", "plazo_col": "caucion_plazo_d",
     "label": "Caución $ o/n — TNA cierre", "unit": "%", "dec": 2, "escala": 1.0},
    {"key": "caucion_monto", "col": "caucion_monto", "plazo_col": "caucion_plazo_d",
     "label": "Caución $ o/n — monto operado", "unit": "$", "dec": 0, "escala": 1.0},
    {"key": "caucion_usd_tna_vwap", "col": "caucion_usd_tna_vwap", "plazo_col": "caucion_usd_plazo_d",
     "label": "Caución US$ o/n — TNA VWAP", "unit": "%", "dec": 2, "escala": 1.0},
    {"key": "caucion_usd_tna", "col": "caucion_usd_tna", "plazo_col": "caucion_usd_plazo_d",
     "label": "Caución US$ o/n — TNA cierre", "unit": "%", "dec": 2, "escala": 1.0},
    {"key": "caucion_usd_monto", "col": "caucion_usd_monto", "plazo_col": "caucion_usd_plazo_d",
     "label": "Caución US$ o/n — monto operado", "unit": "$", "dec": 0, "escala": 1.0},
    {"key": "ccl", "col": "ccl", "label": "CCL implícito", "unit": "", "dec": 2, "escala": 1.0},
    {"key": "mep", "col": "mep", "label": "MEP implícito", "unit": "", "dec": 2, "escala": 1.0},
    {"key": "canje", "col": "canje", "label": "Canje CCL/MEP", "unit": "%", "dec": 2, "escala": 100.0},
    {"key": "oficial_a3500", "col": "oficial_a3500", "label": "Oficial A3500", "unit": "", "dec": 2, "escala": 1.0},
]

_lock = threading.Lock()
_cache: Dict[str, Any] = {}      # {"sig": (path, mtime), "df": DataFrame|None}


def _path() -> Optional[str]:
    d = deltapaths.historico_dir()
    if not d:
        return None
    xlsx = os.path.join(d, FX_FILENAME)
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    if os.path.isfile(pq):
        return pq
    if os.path.isfile(xlsx):
        return xlsx
    return None


def _load() -> Optional[pd.DataFrame]:
    path = _path()
    if path is None:
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _lock:
        if _cache.get("sig") == (path, mtime):
            return _cache.get("df")
    try:
        df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_excel(path)
        df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"]).dt.date
        df = df.sort_values("fecha_hoy").reset_index(drop=True)
    except Exception:  # noqa: BLE001 — un FX ilegible no voltea la pestaña
        df = None
    with _lock:
        _cache["sig"] = (path, mtime)
        _cache["df"] = df
    return df


def refresh() -> None:
    with _lock:
        _cache.clear()


def signature() -> tuple:
    """(path, mtime) del archivo — cambia a lo sumo 1 vez por día (cuando el
    autosave escribe). Clave del cache de render de la pestaña."""
    path = _path()
    if path is None:
        return ("", 0.0)
    try:
        return (path, os.path.getmtime(path))
    except OSError:
        return (path, 0.0)


def status() -> Dict[str, Any]:
    df = _load()
    if df is None or not len(df):
        return {"loaded": False}
    return {"loaded": True, "n": int(len(df)),
            "dmin": df["fecha_hoy"].iloc[0].isoformat(),
            "dmax": df["fecha_hoy"].iloc[-1].isoformat()}


def series_list() -> List[Dict[str, Any]]:
    """Series disponibles EN el archivo (columna presente y con algún dato) —
    un archivo viejo sin las columnas de caución no rompe nada."""
    df = _load()
    if df is None or not len(df):
        return []
    return [dict(s) for s in SERIES
            if s["col"] in df.columns and df[s["col"]].notna().any()]


def series_rows(key: str, dias: int = 0) -> Optional[Dict[str, Any]]:
    """{"meta", "rows"} con las filas ASC de la serie: fecha ISO, valor (ya
    escalado), Δ y Δ% contra el ÚLTIMO DÍA CON DATO (los días sin dato no
    cortan la serie ni generan Δ falsas) y el plazo o/n si aplica.
    `dias` recorta la ventana al final (0 = todo); la Δ de la primera fila
    visible se calcula antes del recorte, así sigue siendo real."""
    df = _load()
    spec = next((s for s in SERIES if s["key"] == key), None)
    if df is None or spec is None or spec["col"] not in df.columns:
        return None
    cols = ["fecha_hoy", spec["col"]]
    pc = spec.get("plazo_col")
    if pc and pc in df.columns:
        cols.append(pc)
    sub = df[cols].dropna(subset=[spec["col"]])
    esc = float(spec.get("escala", 1.0))
    fechas = sub["fecha_hoy"].tolist()
    vals = (sub[spec["col"]].astype(float) * esc).tolist()
    plazos = sub[pc].tolist() if (pc and pc in sub.columns) else [None] * len(vals)
    rows: List[Dict[str, Any]] = []
    prev: Optional[float] = None
    for f, v, p in zip(fechas, vals, plazos):
        d: Dict[str, Any] = {
            "fecha": f.isoformat(), "valor": v,
            "var": (v - prev) if prev is not None else None,
            "var_pct": ((v / prev - 1.0) * 100.0) if prev else None,
        }
        if p is not None and p == p:            # NaN-safe
            d["plazo"] = int(p)
        rows.append(d)
        prev = v
    if dias and len(rows) > dias:
        rows = rows[-dias:]
    meta = dict(spec)
    meta["n_total"] = int(len(sub))
    return {"meta": meta, "rows": rows}
