"""Posiciones / tenencias Delta — carga ÚNICA y cacheada.

Lee los Excel de carteras una sola vez y los cachea en memoria; releer es
explícito (`refresh()`), por lo que las rutas sirven SIN I/O de Excel por
request (prioridad: velocidad). Failure-silent: si faltan los archivos,
devuelve estructura vacía con `error` para que la UI lo muestre.

Archivos (paths desde env, que OMSsecrets carga del secrets.txt):
  - Delta_Composicion.xlsx  (DELTA_COMPOSICION_PATH | DELTA_BASES_DIR)
  - Delta_PN.xlsx           (DELTA_PN_PATH          | DELTA_BASES_DIR)
  - Delta_Fondos.txt        (DELTA_FONDOS_PATH)  → CodFondo → Nombre (opcional)

Esquema (igual que OMSposiciones.py legacy):
  Composición: CodFondo, Cod_Delta, Cantidad, Valor, (Clase de Activo, Vto…)
  PN:          CodFondo, PN
  %PN = Valor / PN.  Cod_Delta (upper/strip) matchea el ticker del universo.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.positions")

_COMPOSICION_FILE = "Delta_Composicion.xlsx"
_PN_FILE = "Delta_PN.xlsx"

# Fallback CodFondo → Nombre (de OMSposiciones). Se usa si Delta_Fondos.txt
# no está disponible / no parsea, así nunca se muestran sólo números.
_FONDO_NOMBRES_FALLBACK: Dict[int, str] = {
    1: "Acciones", 2: "Ahorro", 13: "Ahorro Plus", 39: "Cohen Pesos",
    18: "Crecimiento", 37: "CRF DOL", 14: "FEDERAL I", 15: "Gestion I",
    16: "Gestion II", 19: "Gestion III", 9: "Gestion IV", 28: "Gestion IX",
    41: "Gestion Pyme", 21: "Gestion V", 23: "Gestión VI", 24: "Gestion VII",
    25: "Gestion VIII", 34: "Gestion X", 40: "Gestion XI", 8: "Internacional",
    3: "Latinoamerica", 7: "Moneda", 12: "Multimercado I", 35: "MULTIMERCADO II",
    27: "Patrimonio I", 20: "Performance", 5: "Pesos", 36: "PLUS", 11: "Pyme",
    38: "PYMES", 6: "Recursos", 4: "Renta", 22: "Renta Dolares",
    26: "DOLARES PLUS", 10: "Select", 42: "Gestion XIII",
}

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None


# ── paths ────────────────────────────────────────────────────────────────
def _resolve(filename: str, env_override: str) -> Optional[str]:
    p = os.getenv(env_override)
    if p and os.path.isfile(p):
        return p
    base = os.getenv("DELTA_BASES_DIR")
    if base:
        cand = os.path.join(base, filename)
        if os.path.isfile(cand):
            return cand
    return None


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None  # descarta NaN
    except (TypeError, ValueError):
        return None


def _norm_code(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().upper()
    return None if s in ("NC", "NAN", "NONE", "") else s


# ── fondos (CodFondo → Nombre), parser tolerante ──────────────────────────
def _parse_fondos(path: str) -> Dict[int, str]:
    raw: Optional[str] = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, OSError):
            continue
    if not raw:
        return {}
    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return {}
    delim = max(["\t", "|", ";", ","], key=lambda d: sum(1 for ln in lines[:10] if d in ln))
    if any(delim in ln for ln in lines[:10]):
        rows = [[c.strip() for c in ln.split(delim)] for ln in lines]
    else:
        rows = [re.split(r"\s{2,}|\t+", ln.strip()) for ln in lines]
    if not rows or len(rows[0]) < 2:
        return {}
    header = [c.strip().lower() for c in rows[0]]
    is_header = any(t in h for h in header for t in ("cod", "id", "num")) and \
        any(t in h for h in header for t in ("nombre", "denomi", "descri", "fondo"))

    col_code, col_name = 0, 1
    if is_header:
        # columna de código
        for i, h in enumerate(header):
            if any(t in h for t in ("codfondo", "cod_fondo", "cod fondo")) or h in ("cod", "id"):
                col_code = i
                break
        # columna de nombre por prioridad (token específico primero; 'corto'
        # genérico al final para que 'NombreCorto' gane sobre una col 'Corto').
        col_name = -1
        for token in ("nombrecorto", "nombre corto", "denomi", "nombre", "descri", "corto"):
            for i, h in enumerate(header):
                if i != col_code and token in h:
                    col_name = i
                    break
            if col_name >= 0:
                break
        if col_name < 0:
            col_name = 1 if col_code != 1 else (2 if len(header) > 2 else 1)
        data_rows = rows[1:]
    else:
        data_rows = rows

    out: Dict[int, str] = {}
    for r in data_rows:
        if len(r) <= max(col_code, col_name):
            continue
        try:
            cod = int(float(str(r[col_code]).strip().strip('"').strip("'")))
        except (TypeError, ValueError):
            continue
        name = str(r[col_name]).strip().strip('"').strip("'")
        if name:
            out[cod] = name
    return out


def _find_ci(dirpath: str, fname: str) -> Optional[str]:
    """Busca un archivo en dirpath case-insensitive (robusto en Linux)."""
    if not dirpath or not os.path.isdir(dirpath):
        return None
    target = fname.lower()
    try:
        for f in os.listdir(dirpath):
            if f.lower() == target:
                return os.path.join(dirpath, f)
    except OSError:
        return None
    return None


def _fondos_path() -> Optional[str]:
    """Resuelve Delta_Fondos.txt. Prioridad: DELTA_FONDOS_PATH, luego bajo
    DELTA_HISTORICO_DIR y DELTA_BASES_DIR (en Text/Esco/, ../Text/Esco/, raíz),
    case-insensitive (el archivo suele ser 'Delta_fondos.txt')."""
    env = os.getenv("DELTA_FONDOS_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env
    for base_env in ("DELTA_HISTORICO_DIR", "DELTA_BASES_DIR"):
        base = os.getenv(base_env)
        if not base:
            continue
        base = os.path.expandvars(os.path.expanduser(base)).rstrip("\\/")
        parent = os.path.dirname(base)
        for d in (os.path.join(base, "Text", "Esco"), base,
                  os.path.join(parent, "Text", "Esco"), parent):
            hit = _find_ci(d, "Delta_Fondos.txt")
            if hit:
                return hit
    return None


def _fondo_names() -> Dict[int, str]:
    path = _fondos_path()
    if path:
        try:
            parsed = _parse_fondos(path)
            if parsed:
                return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning("[positions] fondos parse failed: %s", exc)
    return dict(_FONDO_NOMBRES_FALLBACK)


# ── carga ──────────────────────────────────────────────────────────────────
def _load() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "loaded": False, "error": None, "holdings": [], "pn": {}, "fondos": {},
        "paths": {},
    }
    comp_path = _resolve(_COMPOSICION_FILE, "DELTA_COMPOSICION_PATH")
    pn_path = _resolve(_PN_FILE, "DELTA_PN_PATH")
    out["paths"] = {"composicion": comp_path, "pn": pn_path}
    if comp_path is None:
        out["error"] = ("No se encontró Delta_Composicion.xlsx — configurá "
                        "DELTA_BASES_DIR o DELTA_COMPOSICION_PATH en secrets.txt.")
        return out

    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"pandas no disponible: {exc}"
        return out

    try:
        dfc = pd.read_excel(comp_path, sheet_name="Sheet1")
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"Error leyendo composición: {exc}"
        return out

    if "CodFondo" not in dfc.columns:
        out["error"] = "Delta_Composicion.xlsx no tiene columna 'CodFondo'."
        return out

    dfc = dfc.dropna(subset=["CodFondo"]).copy()
    dfc["CodFondo"] = pd.to_numeric(dfc["CodFondo"], errors="coerce")
    dfc = dfc.dropna(subset=["CodFondo"])
    for col in ("Cantidad", "Valor"):
        if col in dfc.columns:
            dfc[col] = pd.to_numeric(dfc[col], errors="coerce")

    holdings: List[Dict[str, Any]] = []
    has_cd = "Cod_Delta" in dfc.columns
    has_esp = "Especie" in dfc.columns
    has_clase = "Clase de Activo" in dfc.columns
    for _, r in dfc.iterrows():
        cod_delta = _norm_code(r.get("Cod_Delta")) if has_cd else None
        holdings.append({
            "cod_fondo": int(r["CodFondo"]),
            "cod_delta": cod_delta,
            "especie": (str(r.get("Especie")).strip() if has_esp and r.get("Especie") == r.get("Especie") else None) or cod_delta or "—",
            "cantidad": _f(r.get("Cantidad")),
            "valor": _f(r.get("Valor")),
            "clase": (str(r.get("Clase de Activo")).strip() if has_clase and r.get("Clase de Activo") == r.get("Clase de Activo") else None),
        })

    pn: Dict[int, float] = {}
    if pn_path:
        try:
            dfp = pd.read_excel(pn_path, sheet_name="Sheet1")
            dfp["CodFondo"] = pd.to_numeric(dfp["CodFondo"], errors="coerce")
            dfp["PN"] = pd.to_numeric(dfp["PN"], errors="coerce")
            for _, r in dfp.dropna(subset=["CodFondo", "PN"]).iterrows():
                pn[int(r["CodFondo"])] = float(r["PN"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("[positions] PN load failed: %s", exc)

    out["holdings"] = holdings
    out["pn"] = pn
    out["fondos"] = _fondo_names()
    # Índice por Cod_Delta → posición agregada (O(1) en position_for).
    by_code: Dict[str, Dict[str, Any]] = {}
    for h in holdings:
        code = h["cod_delta"]
        if not code:
            continue
        agg = by_code.setdefault(code, {
            "especie": h["especie"], "total_cantidad": 0.0, "total_valor": 0.0, "funds": [],
        })
        agg["total_cantidad"] += (h["cantidad"] or 0.0)
        agg["total_valor"] += (h["valor"] or 0.0)
        agg["funds"].append({"cod_fondo": h["cod_fondo"], "cantidad": h["cantidad"], "valor": h["valor"]})
    out["by_code"] = by_code
    out["loaded"] = True
    logger.info("[positions] cargado: %d holdings, %d fondos con PN", len(holdings), len(pn))
    return out


# ── API pública ────────────────────────────────────────────────────────────
def ensure_loaded() -> Dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache


def refresh() -> Dict[str, Any]:
    """Fuerza relectura de los Excel (botón 'actualizar')."""
    global _cache
    with _lock:
        _cache = _load()
        return _cache


def status() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "paths": c["paths"],
            "n_holdings": len(c["holdings"]), "n_fondos_pn": len(c["pn"])}


def fondo_label(cod: int) -> str:
    c = ensure_loaded()
    nombre = c["fondos"].get(cod)
    return f"{cod} — {nombre}" if nombre else f"Fondo {cod}"


def fondos() -> List[Dict[str, Any]]:
    """Lista de fondos presentes en la composición, con su PN."""
    c = ensure_loaded()
    cods = sorted({h["cod_fondo"] for h in c["holdings"]})
    return [{"cod": cod, "nombre": fondo_label(cod), "pn": c["pn"].get(cod)} for cod in cods]


def holdings(cod_fondo: int) -> List[Dict[str, Any]]:
    c = ensure_loaded()
    return [h for h in c["holdings"] if h["cod_fondo"] == cod_fondo]


def pn_of(cod_fondo: int) -> Optional[float]:
    return ensure_loaded()["pn"].get(cod_fondo)


def especies_universe() -> List[str]:
    """Cod_Delta únicos (para la matriz especies×fondos)."""
    c = ensure_loaded()
    return sorted({h["cod_delta"] for h in c["holdings"] if h["cod_delta"]})


def position_for(code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Posición agregada en un instrumento (suma de todos los fondos).

    `code` matchea Cod_Delta (upper). None si no se tiene el papel. Incluye
    el detalle por fondo (nombre + % PN) ordenado por valor.
    """
    if not code:
        return None
    from . import symbols as syms  # normaliza sufijos j/v igual que el path de precios
    c = ensure_loaded()
    by = c.get("by_code", {})
    key = str(code).strip().upper()
    agg = by.get(key)
    if not agg:                       # fallback: TTS26v / TX26j → TTS26 / TX26 (md_symbol)
        key = syms.calc_to_md_code(key).upper()
        agg = by.get(key)
    if not agg:
        return None
    funds = []
    for f in agg["funds"]:
        pn = c["pn"].get(f["cod_fondo"])
        funds.append({
            "cod_fondo": f["cod_fondo"],
            "nombre": fondo_label(f["cod_fondo"]),
            "cantidad": f["cantidad"],
            "valor": f["valor"],
            "pct_pn": (f["valor"] / pn) if (f["valor"] and pn and pn > 0) else None,
        })
    funds.sort(key=lambda x: (x["valor"] or 0.0), reverse=True)
    return {
        "code": key,
        "total_cantidad": agg["total_cantidad"],
        "total_valor": agg["total_valor"],
        "n_fondos": len(funds),
        "funds": funds,
    }
