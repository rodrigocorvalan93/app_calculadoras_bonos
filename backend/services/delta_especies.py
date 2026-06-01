"""Delta - Especies.xlsx — metadata extra de bonos (carga ÚNICA, cacheada).

Lee la hoja 'Base RF' (multi-header) una sola vez, la indexa por BYMA (ticker)
y expone `info(code)` con campos útiles (emisor, sector, industria, ajuste,
tasa, calificaciones, ISIN/Bloomberg, etc.) para YAS / Comparador. Sirve del
cache → sin I/O de Excel por request. Failure-silent.

Paths (env, que OMSsecrets carga del secrets.txt):
  DELTA_ESPECIES_PATH (ruta completa)  |  DELTA_HISTORICO_DIR | DELTA_BASES_DIR
  → busca 'Delta - Especies.xlsx' en esas carpetas (y un nivel arriba).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.delta_especies")

_ESPECIES_FILENAME = "Delta - Especies.xlsx"
_SHEET = "Base RF"
_HEADER_ROWS = [2, 3]

# Subconjunto de columnas a exponer (en orden de display).
_KEEP: List[str] = [
    "Emisor / Sponsor", "Grupo Emisor", "Sector", "Grupo Industria", "Industria",
    "Sub Industria", "Sector Delta", "Clase de Activo", "Subclase de Activo",
    "Ajuste", "Tasa", "Cupón", "Legislación", "Plazo", "Subyacente",
    "Califica_Local", "Califica_Extranjera", "Calificadora", "Clasificacion_especifico",
    "ISIN", "BLOOM", "BYMA_API",
]

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None


def _resolve_path() -> Optional[str]:
    env = os.getenv("DELTA_ESPECIES_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env
    for base_env in ("DELTA_HISTORICO_DIR", "DELTA_BASES_DIR"):
        base = os.getenv(base_env)
        if not base:
            continue
        base = os.path.expandvars(os.path.expanduser(base)).rstrip("\\/")
        for cand in (os.path.join(base, _ESPECIES_FILENAME),
                     os.path.join(os.path.dirname(base), _ESPECIES_FILENAME)):
            if os.path.isfile(cand):
                return cand
    return None


def _flatten(cols) -> List[str]:
    out = []
    for c in cols:
        if isinstance(c, tuple):
            a, b = c[0], c[-1]
            name = b if (isinstance(b, str) and not str(b).startswith("Unnamed")) else a
        else:
            name = c
        out.append(str(name).strip())
    return out


def _clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        if isinstance(v, float) and v != v:  # NaN
            return None
    except TypeError:
        pass
    if hasattr(v, "item"):  # numpy scalar
        try:
            v = v.item()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(v, "date"):  # Timestamp/datetime → fecha corta
        try:
            return v.strftime("%d/%m/%Y")
        except Exception:  # noqa: BLE001
            pass
    return v


def _load() -> Dict[str, Any]:
    out: Dict[str, Any] = {"loaded": False, "error": None, "by_code": {}, "path": None}
    path = _resolve_path()
    out["path"] = path
    if not path:
        out["error"] = ("No se encontró 'Delta - Especies.xlsx' — configurá "
                        "DELTA_ESPECIES_PATH o DELTA_HISTORICO_DIR en secrets.txt.")
        return out
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"pandas no disponible: {exc}"
        return out
    try:
        df = pd.read_excel(path, sheet_name=_SHEET, header=_HEADER_ROWS)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"Error leyendo especies: {exc}"
        return out
    df.columns = _flatten(df.columns)
    if "BYMA" not in df.columns:
        out["error"] = "La hoja 'Base RF' no tiene columna 'BYMA'."
        return out
    keep = [c for c in _KEEP if c in df.columns]
    by_code: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        byma = r.get("BYMA")
        if byma is None or (isinstance(byma, float) and byma != byma):
            continue
        key = str(byma).strip().upper()
        if not key or key in ("NAN", "NC", "NONE"):
            continue
        rec = {}
        for c in keep:
            cv = _clean(r.get(c))
            if cv is not None and str(cv).strip() not in ("", "nan"):
                rec[c] = cv
        if rec:
            by_code[key] = rec
    out["by_code"] = by_code
    out["loaded"] = True
    logger.info("[delta_especies] %d especies, %d cols", len(by_code), len(keep))
    return out


def ensure_loaded() -> Dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache


def refresh() -> Dict[str, Any]:
    global _cache
    with _lock:
        _cache = _load()
        return _cache


def status() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "path": c["path"], "n": len(c["by_code"])}


def info(code: Optional[str]) -> Optional[Dict[str, Any]]:
    if not code:
        return None
    return ensure_loaded()["by_code"].get(str(code).strip().upper())
