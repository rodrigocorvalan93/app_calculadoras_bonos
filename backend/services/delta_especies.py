"""Delta - Especies.xlsx — metadata extra de bonos (carga ÚNICA, cacheada).

Lee la hoja 'Base RF' (multi-header) una sola vez, la indexa por BYMA (ticker)
y expone `info(code)` con campos útiles (emisor, sector, industria, ajuste,
tasa, calificaciones, ISIN/Bloomberg, etc.) para YAS / Comparador. Sirve del
cache → sin I/O de Excel por request. Failure-silent.

Renta variable (17/11): del MISMO archivo, abierto una sola vez, la hoja
'Base RV' (misma cabecera de dos filas) → `info_rv(code)` / `sector_rv(code)`:
instrumento (acción / CEDEAR / ADR / ETF), sector del desk ('Sector Delta') y
GICS, emisor. Va en un índice APARTE de `info()` — la clasificación de bonos
por texto no ve estas filas — y es best-effort: sin hoja, o con la hoja rota,
la Base RF carga igual y `status()["error_rv"]` dice por qué.

Paths (env, que OMSsecrets carga del secrets.txt):
  DELTA_ESPECIES_PATH (ruta completa)  |  DELTA_HISTORICO_DIR | DELTA_BASES_DIR
  → busca 'Delta - Especies.xlsx' en esas carpetas (y un nivel arriba).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from backend.services import deltapaths

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

# Hoja de renta variable: misma cabecera de dos filas que la Base RF.
_SHEET_RV = "Base RV"
_KEEP_RV: List[str] = [
    "Descripción", "Instrumento", "Sector Delta", "Sector", "Grupo Industria",
    "Industria", "Sub Industria", "Emisor / Sponsor", "Geografía",
    "Valuación Ref.", "CNV_Local_Extranjero", "Subyacente", "ISIN", "BLOOM",
    "BYMA_API",
]
_VACIOS = frozenset({"", "NAN", "NC", "NONE", "#N/A", "#N/D", "-", "0"})

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None


def _resolve_path() -> Optional[str]:
    env = os.getenv("DELTA_ESPECIES_PATH")
    if env:
        env = deltapaths.expand(env, want="file")
        if os.path.isfile(env):
            return env
    for base_env in ("DELTA_HISTORICO_DIR", "DELTA_BASES_DIR"):
        base = os.getenv(base_env)
        if not base:
            continue
        base = deltapaths.expand(base, want="dir").rstrip("\\/")
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


def _txt(v: Any) -> Optional[str]:
    """Texto de una celda, sin espacios de más ('Consumo ' = 'Consumo')."""
    v = _clean(v)
    if v is None:
        return None
    # un 0 numérico es el "no encontré" de una fórmula de la planilla (una
    # columna de fórmulas toda en 0 llega float: "0.0" no estaba en _VACIOS)
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0:
        return None
    t = " ".join(str(v).split())
    # "#REF!" / "#VALUE!" / "#N/A": una fórmula rota de la planilla (Sector y
    # Grupo Industria salen de un BUSCARV sobre la hoja GICS) no es un dato
    if t.upper() in _VACIOS or t.startswith("#"):
        return None
    return t


def _indexar_rf(df) -> Dict[str, Dict[str, Any]]:
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
    return by_code


def _sin_duplicadas(df, hoja: str):
    """Dos columnas con el mismo nombre después de `_flatten` (una celda de
    cabecera combinada, el mismo campo bajo dos grupos) hacen que `r.get(c)`
    devuelva una Series y la celda salga como texto basura: queda la primera."""
    dup = df.columns.duplicated()
    if dup.any():
        logger.warning("[delta_especies] hoja '%s': columnas repetidas, uso la primera de cada una: %s",
                       hoja, ", ".join(sorted({str(c) for c in df.columns[dup]})[:10]))
        df = df.loc[:, ~dup]
    return df


def _indexar_rv(df) -> Dict[str, Any]:
    """Base RV → {clave: fila}. Clave principal = BYMA (ticker de pantalla);
    alias = `Cod_Delta` tal cual ('VIST US', sin BYMA cargado) y normalizado
    como el ticker de una tenencia (`positions._norm_code`: 'GGAL AR' → GGAL,
    'CENCOSUD CI' → CENCOSUD), que NUNCA pisan un BYMA. No hay alias por
    "primer token": 'AGRO US' (Adecoagro) no es AGRO (Agrometal). Un BYMA
    repetido en dos filas (TSM, con sectores distintos) → manda la primera,
    pero la segunda conserva su Cod_Delta completo (el ADR 'TSM US')."""
    from backend.services.positions import _norm_code
    keep = [c for c in _KEEP_RV if c in df.columns]
    has_cd = "Cod_Delta" in df.columns
    by_code: Dict[str, Dict[str, Any]] = {}
    alias: List[Any] = []
    repetidos: List[str] = []
    n = 0
    for _, r in df.iterrows():
        byma = _txt(r.get("BYMA"))
        cd = _txt(r.get("Cod_Delta")) if has_cd else None
        if not byma and not cd:
            continue
        rec: Dict[str, Any] = {}
        for c in keep:
            cv = _txt(r.get(c))
            if cv is not None:
                rec[c] = cv
        if not rec:
            continue
        n += 1
        repetido = False
        if byma:
            key = byma.upper()
            if key in by_code:
                repetidos.append(key)
                repetido = True
            else:
                rec["BYMA"] = key
                by_code[key] = rec
        if cd:
            alias.append((cd.upper(), rec, repetido))
    # Dos pasadas: primero TODOS los Cod_Delta completos (match exacto de la
    # tenencia), después los normalizados — así el orden de la hoja no decide.
    for cd, rec, _ in alias:
        by_code.setdefault(cd, rec)
    for cd, rec, repetido in alias:
        corto = _norm_code(cd)
        if corto and not repetido:
            by_code.setdefault(corto, rec)
    return {"by_code": by_code, "n": n, "repetidos": repetidos}


def _load() -> Dict[str, Any]:
    out: Dict[str, Any] = {"loaded": False, "error": None, "by_code": {}, "path": None,
                           "by_code_rv": {}, "n_rv": 0, "error_rv": None}
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
    # UNA apertura del archivo para las dos hojas (el zip y las cadenas
    # compartidas se parsean una vez; openpyxl lee cada hoja a demanda).
    try:
        xls = pd.ExcelFile(path)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"Error leyendo especies: {exc}"
        return out
    try:
        try:
            df = pd.read_excel(xls, sheet_name=_SHEET, header=_HEADER_ROWS)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"Error leyendo especies: {exc}"
            return out
        df.columns = _flatten(df.columns)
        df = _sin_duplicadas(df, _SHEET)
        if "BYMA" not in df.columns:
            out["error"] = "La hoja 'Base RF' no tiene columna 'BYMA'."
            return out
        out["by_code"] = _indexar_rf(df)
        out["loaded"] = True
        # Renta variable: best-effort, nunca voltea la Base RF.
        try:
            if _SHEET_RV not in xls.sheet_names:
                out["error_rv"] = f"El archivo no tiene la hoja '{_SHEET_RV}'."
            else:
                dfv = pd.read_excel(xls, sheet_name=_SHEET_RV, header=_HEADER_ROWS)
                dfv.columns = _flatten(dfv.columns)
                dfv = _sin_duplicadas(dfv, _SHEET_RV)
                if "BYMA" not in dfv.columns and "Cod_Delta" not in dfv.columns:
                    out["error_rv"] = f"La hoja '{_SHEET_RV}' no tiene columna 'BYMA' ni 'Cod_Delta'."
                else:
                    rv = _indexar_rv(dfv)
                    out["by_code_rv"] = rv["by_code"]
                    out["n_rv"] = rv["n"]
                    if rv["repetidos"]:
                        logger.info("[delta_especies] Base RV: ticker repetido (manda la primera fila): %s",
                                    ", ".join(sorted(set(rv["repetidos"]))[:10]))
        except Exception as exc:  # noqa: BLE001
            out["error_rv"] = f"Error leyendo '{_SHEET_RV}': {exc}"
        if out["error_rv"]:
            logger.warning("[delta_especies] renta variable sin datos: %s", out["error_rv"])
    finally:
        try:
            xls.close()
        except Exception:  # noqa: BLE001
            pass
    logger.info("[delta_especies] %d especies de renta fija, %d de renta variable",
                len(out["by_code"]), out["n_rv"])
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
    return {"loaded": c["loaded"], "error": c["error"], "path": c["path"], "n": len(c["by_code"]),
            "n_rv": c.get("n_rv", 0), "error_rv": c.get("error_rv")}


def info(code: Optional[str]) -> Optional[Dict[str, Any]]:
    if not code:
        return None
    return ensure_loaded()["by_code"].get(str(code).strip().upper())


def info_rv(code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fila de la hoja 'Base RV' (acciones / CEDEARs / ADRs / ETFs) del
    ticker: lookup en memoria, µs. None si no es renta variable de la base."""
    if not code:
        return None
    return (ensure_loaded().get("by_code_rv") or {}).get(str(code).strip().upper())


def sector_rv(code: Optional[str]) -> Optional[str]:
    """Sector para agrupar renta variable: 'Sector Delta' (el del desk, en
    castellano) y, si la fila no lo tiene, el GICS 'Sector'."""
    rec = info_rv(code)
    if not rec:
        return None
    return rec.get("Sector Delta") or rec.get("Sector") or None
