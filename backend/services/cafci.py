"""CAFCI — vector de precios de la Cámara Argentina de FCI.

Lee el Excel diario que genera el bot en la carpeta `Precios Cafci/AAAMMDD.xlsx`
(t-1 hábil): una hoja `fx…` (USD/USB/…) y otra `vector…` con la valuación de los
activos. Resuelve el más reciente, lo pre-indexa para búsqueda server-side (el
vector tiene ~6k filas: NO se renderiza entero) → sub-50 ms.

Config (secrets.txt → os.environ vía OMSsecrets, igual que delta_especies):
  DELTA_CAFCI_PATH  → ruta completa a un .xlsx puntual, o
  DELTA_CAFCI_DIR   → carpeta; toma el .xlsx cuyo nombre contiene la fecha
                      AAAMMDD más nueva (acepta prefijos/sufijos).
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_last_check: float = 0.0
# El archivo es diario (AAAMMDD.xlsx). NO releemos el Excel en cada request: sólo
# re-escaneamos la carpeta cada _RECHECK_SEC y, si apareció uno más nuevo, lo
# cargamos (una vez por día en la práctica). El read pesado va en threadpool.
_RECHECK_SEC = 300.0

# (columna en el Excel, key de salida)
_FIELDS = [
    ("ISIN", "isin"), ("BYMA", "byma"), ("CAFCI", "cafci"), ("Valuación", "moneda"),
    ("Cdo.", "cdo"), ("Variación Cdo. [%]", "var_cdo"), ("Mod. Duration", "mod_dur"),
    ("TIR [%]", "tir"), ("TNA [%]", "tna"), ("Spread [%]", "spread"), ("Z-Spread [%]", "zspread"),
]
_DATE_RE = re.compile(r"(\d{8})")


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _empty(error: Optional[str] = None) -> Dict[str, Any]:
    return {"loaded": False, "error": error, "path": None, "fecha": None, "fx": {}, "rows": [], "n": 0}


def _resolve_path() -> Optional[str]:
    env = os.getenv("DELTA_CAFCI_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env
    env_dir = os.getenv("DELTA_CAFCI_DIR")
    if env_dir:
        env_dir = os.path.expandvars(os.path.expanduser(env_dir))
        if os.path.isdir(env_dir):
            cands = []
            for fn in os.listdir(env_dir):
                # Saltear lock files de Excel (~$AAAMMDD.xlsx mientras está abierto).
                if fn.startswith("~$") or not fn.lower().endswith((".xlsx", ".xls")):
                    continue
                # Aceptar cualquier nombre que CONTENGA la fecha AAAMMDD:
                # 20260605.xlsx, CAFCI 20260605.xlsx, vector_20260605.xlsx, …
                m = _DATE_RE.search(fn)
                if m:
                    cands.append((m.group(1), os.path.join(env_dir, fn)))
            if cands:
                return max(cands)[1]          # el de fecha (AAAMMDD) más reciente
    return None


def _load() -> Dict[str, Any]:
    path = _resolve_path()
    if not path:
        return _empty("No se encontró el Excel CAFCI (configurá DELTA_CAFCI_PATH o DELTA_CAFCI_DIR).")
    try:
        import pandas as pd
        xl = pd.ExcelFile(path)
        fx_sheet = next((s for s in xl.sheet_names if str(s).lower().startswith("fx")), None)
        vec_sheet = next((s for s in xl.sheet_names if str(s).lower().startswith("vector")), None)
        m = _DATE_RE.search(str(vec_sheet or os.path.basename(path)))
        fecha = m.group(1) if m else None

        fx: Dict[str, float] = {}
        if fx_sheet is not None:
            fxdf = pd.read_excel(path, sheet_name=fx_sheet, header=None)
            for _, r in fxdf.iterrows():
                k, v = str(r.iloc[0]).strip().upper(), _num(r.iloc[1])
                if k.isalpha() and 2 <= len(k) <= 4 and v is not None:   # USD/USB/USM/… (no índices)
                    fx[k] = v

        rows: List[Dict[str, Any]] = []
        if vec_sheet is not None:
            vdf = pd.read_excel(path, sheet_name=vec_sheet)
            cols = set(vdf.columns)
            _txt = {"isin", "byma", "cafci", "moneda"}
            for _, r in vdf.iterrows():
                row: Dict[str, Any] = {}
                for col, key in _FIELDS:
                    if col not in cols:
                        continue
                    v = r[col]
                    if key in _txt:
                        row[key] = str(v).strip() if (v is not None and v == v) else None
                    else:
                        row[key] = _num(v)
                # sólo activos con algún identificador
                if not (row.get("isin") or row.get("byma") or row.get("cafci")):
                    continue
                row["_key"] = " ".join(str(row.get(k) or "") for k in ("isin", "byma", "cafci")).lower()
                rows.append(row)
        logger.info("[cafci] %s · %d fx · %d filas", os.path.basename(path), len(fx), len(rows))
        return {"loaded": bool(rows or fx), "error": None, "path": path, "fecha": fecha,
                "fx": fx, "rows": rows, "n": len(rows)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[cafci] load falló")
        return _empty(f"Error leyendo el Excel CAFCI: {exc}")


def ensure_loaded() -> Dict[str, Any]:
    global _cache, _last_check
    c = _cache
    now = time.time()
    # Fast path: cache caliente y chequeado hace poco → sin tocar disco.
    if c is not None and (now - _last_check) < _RECHECK_SEC:
        return c
    with _lock:
        if _cache is not None and (time.time() - _last_check) < _RECHECK_SEC:
            return _cache
        _last_check = time.time()
        latest = _resolve_path()
        # Recargar sólo si es la 1ª vez o apareció un archivo más nuevo (otro día).
        if _cache is None or (latest and latest != _cache.get("path")):
            _cache = _load()
        return _cache


def refresh() -> Dict[str, Any]:
    """Refresh manual (botón): relee el Excel ya mismo."""
    global _cache, _last_check
    with _lock:
        _cache = _load()
        _last_check = time.time()
    return _cache


def status() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "fecha": c["fecha"], "n": c["n"], "fx": c["fx"]}


def search(q: str = "", limit: int = 200) -> Tuple[List[Dict[str, Any]], int]:
    """Filas que matchean `q` (ISIN/BYMA/CAFCI), capadas a `limit`. Devuelve
    (filas, total_match) — no renderiza las ~6k filas enteras."""
    c = ensure_loaded()
    rows = c["rows"]
    ql = (q or "").strip().lower()
    if ql:
        rows = [r for r in rows if ql in r["_key"]]
    return rows[:limit], len(rows)
