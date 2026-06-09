"""CAFCI — vector de precios de la Cámara Argentina de FCI.

Lee el Excel diario que genera el bot en la carpeta `Precios Cafci/AAAMMDD.xlsx`
(t-1 hábil): una hoja `fx…` (USD/USB/…) y otra `vector…` con la valuación de los
activos. Resuelve el más reciente, lo pre-indexa para búsqueda server-side (el
vector tiene ~6k filas: NO se renderiza entero) → sub-50 ms.

Config (secrets.txt → os.environ vía OMSsecrets, igual que delta_especies):
  DELTA_CAFCI_PATH  → ruta completa a un .xlsx puntual, o
  DELTA_CAFCI_DIR   → carpeta; toma el .xlsx cuyo nombre contiene la fecha
                      AAAMMDD más nueva (acepta prefijos/sufijos).
Si no se setea ninguna, se auto-descubre la carpeta 'Precios Cafci' al lado de
las bases Delta ya configuradas (DELTA_BASES_DIR / histórico / especies) → en
el layout normal del OneDrive del equipo anda sin tocar nada.
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
    return {"loaded": False, "error": error, "path": None, "resolved": None,
            "fecha": None, "fx": {}, "rows": [], "n": 0}


def _dir_candidates(d: str) -> List[str]:
    """Rutas .xlsx con fecha AAAMMDD en `d`, ordenadas por prioridad:
      1) fecha más nueva,
      2) ante la MISMA fecha, nombre canónico (stem == AAAMMDD) antes que
         decorados → '20260608.xlsx' gana a '20260608_Planilla_Diaria.xlsx',
      3) y luego el nombre más corto (menos 'ruido').
    Saltea lock files ~$ y archivos no-excel. El caller prueba en orden y se
    queda con el primero que tenga hojas CAFCI reales (ver `_parse_cafci`).
    """
    if not os.path.isdir(d):
        return []
    scored = []
    for fn in os.listdir(d):
        if fn.startswith("~$") or not fn.lower().endswith((".xlsx", ".xls")):
            continue
        m = _DATE_RE.search(fn)
        if not m:
            continue
        exact = 1 if os.path.splitext(fn)[0] == m.group(1) else 0
        scored.append(((m.group(1), exact, -len(fn)), os.path.join(d, fn)))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored]


# Profundidad máxima al buscar una carpeta '*cafci*' bajo las bases Delta.
# El layout real es …\Inversiones - Documentos\{Delta Bases, Equipo RF\Precios
# Cafci}: CAFCI es una rama vecina, un nivel más abajo → hace falta depth 2.
_DISCOVER_DEPTH = 2


def _discover_dirs() -> List[str]:
    """Carpetas candidatas a 'Precios Cafci', derivadas de las rutas Delta que
    el usuario YA tiene configuradas (DELTA_BASES_DIR/Carteras, histórico,
    especies). Así CAFCI anda sin setear DELTA_CAFCI_* si la carpeta cuelga del
    mismo árbol de OneDrive del equipo — aunque sea una rama vecina.

    Búsqueda acotada: desde cada raíz (la carpeta y un nivel arriba) baja hasta
    `_DISCOVER_DEPTH` niveles buscando una subcarpeta cuyo nombre contenga
    'cafci', con early-exit al primer match. Corre como mucho 1×/`_RECHECK_SEC`
    y fuera del path caliente, así que no afecta el target de 50 ms.
    """
    roots: List[str] = []

    def add_root(p: Optional[str], *, is_file: bool = False) -> None:
        if not p:
            return
        p = os.path.expandvars(os.path.expanduser(p)).rstrip("\\/")
        base = os.path.dirname(p) if is_file else p
        for r in (base, os.path.dirname(base)):   # la carpeta y un nivel arriba
            if r and r not in roots:
                roots.append(r)

    add_root(os.getenv("DELTA_BASES_DIR"))
    add_root(os.getenv("DELTA_HISTORICO_DIR"))
    add_root(os.getenv("DELTA_HISTORICO_PATH"), is_file=True)
    add_root(os.getenv("DELTA_ESPECIES_PATH"), is_file=True)

    found: List[str] = []

    def scan(d: str, depth: int) -> None:
        try:
            entries = sorted(os.listdir(d))
        except OSError:                            # inexistente / sin permiso
            return
        subdirs: List[str] = []
        for name in entries:
            if name.startswith((".", "$", "~")):   # ignorar ocultas / del sistema
                continue
            full = os.path.join(d, name)
            if not os.path.isdir(full):
                continue
            if "cafci" in name.lower():
                found.append(full)
                return                             # match en este nivel → listo
            subdirs.append(full)
        if depth > 0:
            for sd in subdirs:
                scan(sd, depth - 1)
                if found:
                    return

    for root in roots:
        scan(root, _DISCOVER_DEPTH)
        if found:
            break
    return found


def _resolve_candidates() -> List[str]:
    """Archivos .xlsx candidatos al vector CAFCI, en orden de prioridad.
    DELTA_CAFCI_PATH (archivo puntual) gana; si no, DELTA_CAFCI_DIR; si no,
    la carpeta auto-descubierta. Dentro de una carpeta, ver `_dir_candidates`."""
    env = os.getenv("DELTA_CAFCI_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return [env]
    env_dir = os.getenv("DELTA_CAFCI_DIR")
    if env_dir:
        cands = _dir_candidates(os.path.expandvars(os.path.expanduser(env_dir)))
        if cands:
            return cands
    # Sin DELTA_CAFCI_* explícito: descubrir 'Precios Cafci' junto a las
    # carpetas Delta ya configuradas (cero config para el caso normal).
    for d in _discover_dirs():
        cands = _dir_candidates(d)
        if cands:
            return cands
    return []


def _resolve_path() -> Optional[str]:
    """Mejor candidato (el primero). Lo usa `ensure_loaded` para detectar el
    archivo del día nuevo de forma estable, independiente de cuál termine
    cargando `_load` si el mejor resultara no ser un vector CAFCI."""
    cands = _resolve_candidates()
    return cands[0] if cands else None


def _parse_cafci(path: str) -> Optional[Dict[str, Any]]:
    """Parsea un .xlsx CAFCI (hojas `fx…` / `vector…`). Devuelve None si el
    archivo NO es el vector CAFCI — sin hojas fx/vector, o con ellas vacías —
    para que el caller pruebe el siguiente candidato (p.ej. una planilla
    distinta con la misma fecha en el nombre: '20260608_Planilla_Diaria.xlsx')."""
    import pandas as pd
    xl = pd.ExcelFile(path)
    fx_sheet = next((s for s in xl.sheet_names if str(s).lower().startswith("fx")), None)
    vec_sheet = next((s for s in xl.sheet_names if str(s).lower().startswith("vector")), None)
    if fx_sheet is None and vec_sheet is None:
        return None                                     # no es el vector CAFCI
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

    if not rows and not fx:
        return None                                     # hojas fx/vector vacías → no sirve
    return {"loaded": True, "error": None, "path": path, "fecha": fecha,
            "fx": fx, "rows": rows, "n": len(rows)}


def _load() -> Dict[str, Any]:
    cands = _resolve_candidates()
    if not cands:
        return _empty("No se encontró el Excel CAFCI. Se buscó una carpeta 'Precios Cafci' "
                      "junto a tus bases Delta y no apareció — configurá DELTA_CAFCI_DIR "
                      "(carpeta) o DELTA_CAFCI_PATH (archivo) en secrets.txt.")
    resolved = cands[0]
    tried: List[str] = []
    for path in cands:
        try:
            parsed = _parse_cafci(path)
        except Exception as exc:  # noqa: BLE001  — archivo corrupto / bloqueado
            logger.warning("[cafci] no pude leer %s: %s", os.path.basename(path), exc)
            tried.append(os.path.basename(path))
            continue
        if parsed is not None:
            parsed["resolved"] = resolved
            logger.info("[cafci] %s · %d fx · %d filas", os.path.basename(path), len(parsed["fx"]), parsed["n"])
            return parsed
        tried.append(os.path.basename(path))            # tenía fecha pero no es el vector
    out = _empty("Encontré archivos en la carpeta pero ninguno tiene las hojas CAFCI "
                 "(fx… / vector…): " + ", ".join(tried[:6]) + ". ¿Es la carpeta correcta?")
    out["resolved"] = resolved
    return out


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
        # Recargar sólo si es la 1ª vez o apareció un archivo más nuevo (otro
        # día). Comparo contra `resolved` (mejor candidato), no contra el path
        # cargado: así no recargo en loop si el mejor no es un vector CAFCI.
        if _cache is None or (latest and latest != _cache.get("resolved")):
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
