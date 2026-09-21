"""Cierre completo por rueda → matrices numpy (fechas × símbolos).

Lee las particiones `Delta Bases/cierres/AAAA/AAAA-MM-DD.parquet` que escribe
el autosave (historico_writer._guardar_cierre + la recaptura): una fila por
símbolo del store y rueda con último/cierre/OHLC/puntas/volumen/`opero` y las
métricas de los bonos con ficha. Acá se arman UNA vez por cambio (firma =
cantidad de particiones + mtime de la última) matrices float32 por campo —
`mat["last"][i_fecha, j_símbolo]` — y sobre eso todo es aritmética vectorizada:

    at(sym, fecha)            valor puntual
    serie(sym, campo, n)      serie temporal sin huecos
    ret(sym, n)               retorno a n ruedas
    vector_ref(n)             {código: (precio, fecha)} de la n-ésima rueda
                              anterior — lo que usa el 5D % de Mercado

Costo: carga ~1 s/año en el warmup (executor); consultas en µs-ms. Nada corre
en un request si la firma no cambió. RAM: float64 para último/cierre/TIR/
paridad/duration, float32 para el resto (~13 MB por año con 700 símbolos). Backfill: `importar_base()` convierte la
base px/tasas existente en particiones (fechas que faltan), así la matriz
arranca con toda la historia de bonos y no desde cero.
"""
from __future__ import annotations

import bisect
import logging
import os
import threading
import warnings
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.services import deltapaths
from backend.services.historico_writer import CIERRES_DIRNAME, HIST_FILENAME, _es_habil, _fecha_dato, escribir_particion

logger = logging.getLogger("backend.cierres")

CAMPOS = ("last", "close", "open", "high", "low", "bid", "offer", "volume", "nominal",
          "tirea", "tna", "tem", "paridad", "duration")
# Campos analíticos en float64 (retornos, Δ de TIR en pp, percentiles: el
# float32 pierde el 7º dígito y un Merval de 2.100.000,50 ya no lo guarda);
# el resto (OHLC, puntas, volúmenes) en float32 — mitad de RAM.
_F64 = {"last", "close", "tirea", "paridad", "duration"}
_lock = threading.Lock()
_cache: Dict[str, Any] = {"sig": None, "data": None}
_vref_cache: Dict[tuple, Dict[str, tuple]] = {}


class Matriz:
    def __init__(self, fechas: List[str], simbolos: List[str], codes: List[str], plazos: List[str],
                 mat: Dict[str, np.ndarray], opero: np.ndarray) -> None:
        self.fechas = fechas
        self.idx_f = {f: i for i, f in enumerate(fechas)}
        self.simbolos = simbolos
        self.idx_s = {s: j for j, s in enumerate(simbolos)}
        self.codes = codes
        self.plazos = plazos
        self.mat = mat
        self.opero = opero


def dir_path() -> Optional[str]:
    d = deltapaths.historico_dir()
    return os.path.join(d, CIERRES_DIRNAME) if d else None


def particiones() -> List[Tuple[str, str]]:
    """[(fecha ISO, path)] ascendente de las particiones existentes."""
    root = dir_path()
    if not root or not os.path.isdir(root):
        return []
    out: List[Tuple[str, str]] = []
    try:
        for y in os.listdir(root):
            yd = os.path.join(root, y)
            if not os.path.isdir(yd):
                continue
            for fn in os.listdir(yd):
                if fn.endswith(".parquet") and len(fn) == 18:      # AAAA-MM-DD.parquet
                    out.append((fn[:10], os.path.join(yd, fn)))
    except OSError:
        return []
    return sorted(out)


def signature() -> tuple:
    """(n particiones, última fecha, mtime de la última): cambia con el cierre,
    con la recaptura (pisa la última) y con un backfill."""
    parts = particiones()
    if not parts:
        return (0, "", 0)
    try:
        m = os.stat(parts[-1][1]).st_mtime_ns
    except OSError:
        m = 0
    return (len(parts), parts[-1][0], m)


def _build(df: pd.DataFrame) -> Optional[Matriz]:
    if df is None or not len(df):
        return None
    df = df.copy()
    df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"]).dt.strftime("%Y-%m-%d")
    df["symbol"] = df["symbol"].astype(str)
    df = df.drop_duplicates(subset=["fecha_hoy", "symbol"], keep="last")
    fechas = sorted(df["fecha_hoy"].unique().tolist())
    simbolos = sorted(df["symbol"].unique().tolist())
    fi = df["fecha_hoy"].map({f: i for i, f in enumerate(fechas)}).to_numpy()
    si = df["symbol"].map({s: j for j, s in enumerate(simbolos)}).to_numpy()
    nf, ns = len(fechas), len(simbolos)
    mat: Dict[str, np.ndarray] = {}
    for c in CAMPOS:
        if c not in df.columns:
            continue
        dt = np.float64 if c in _F64 else np.float32
        m = np.full((nf, ns), np.nan, dtype=dt)
        # Un valor basura en UNA celda (1e39 en una columna float32, ±inf) no
        # puede voltear la matriz entera: rentafija.py sube TODO RuntimeWarning
        # a error a nivel proceso, y el "overflow encountered in cast" del
        # float64 → float32 pasaba a excepción → cierres sin matriz (5D de
        # Mercado y price action de bonos vacíos). Lo que no entra queda NaN.
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            vals = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=np.float64)
            vals = np.where(np.isfinite(vals) & (np.abs(vals) <= np.finfo(dt).max), vals, np.nan)
            m[fi, si] = vals.astype(dt)
        mat[c] = m
    opero = np.zeros((nf, ns), dtype=bool)
    if "opero" in df.columns:
        opero[fi, si] = df["opero"].fillna(False).astype(bool).to_numpy()
    else:
        opero[fi, si] = True
    ultimo = df.drop_duplicates(subset=["symbol"], keep="last").set_index("symbol")
    codes = [str(ultimo.at[s, "code"]) if "code" in ultimo.columns and pd.notna(ultimo.at[s, "code"]) else s
             for s in simbolos]
    plazos = [str(ultimo.at[s, "plazo"]) if "plazo" in ultimo.columns and pd.notna(ultimo.at[s, "plazo"]) else ""
              for s in simbolos]
    return Matriz(fechas, simbolos, codes, plazos, mat, opero)


def _load() -> Optional[Matriz]:
    sig = signature()
    with _lock:
        if _cache["sig"] == sig:
            return _cache["data"]
    data: Optional[Matriz] = None
    parts = particiones()
    if parts:
        frames = []
        for iso, p in parts:
            try:
                frames.append(pd.read_parquet(p))
            except Exception as exc:  # noqa: BLE001 — una partición rota no voltea la matriz
                logger.warning("[cierres] partición ilegible %s: %s", p, exc)
        if frames:
            try:
                data = _build(pd.concat(frames, ignore_index=True))
            except Exception:  # noqa: BLE001
                logger.exception("[cierres] build de la matriz falló")
                data = None
    with _lock:
        _cache["sig"] = sig
        _cache["data"] = data
        _vref_cache.clear()
    if data is not None:
        logger.info("[cierres] matriz: %d ruedas × %d símbolos (%s → %s)",
                    len(data.fechas), len(data.simbolos), data.fechas[0], data.fechas[-1])
    return data


def ensure_loaded() -> Optional[Matriz]:
    return _load()


def refresh() -> None:
    with _lock:
        _cache["sig"] = None
        _cache["data"] = None
        _vref_cache.clear()


def loaded() -> Optional[Matriz]:
    """La matriz si YA está en memoria (sin disparar la carga: para el hot
    path de Mercado, donde la carga la hace el warmup / el cierre)."""
    with _lock:
        return _cache["data"]


def status() -> Dict[str, Any]:
    m = loaded()
    if m is None:
        parts = particiones()
        return {"loaded": False, "n_particiones": len(parts),
                "dmax": parts[-1][0] if parts else None}
    return {"loaded": True, "n_particiones": len(m.fechas), "n_simbolos": len(m.simbolos),
            "dmin": m.fechas[0], "dmax": m.fechas[-1],
            "opero_ultima": int(m.opero[-1].sum())}


def status_texto() -> str:
    s = status()
    if not s.get("loaded"):
        return (f"{s['n_particiones']} particiones (sin cargar)" if s.get("n_particiones")
                else "sin particiones todavía")
    return (f"{s['n_particiones']} ruedas · {s['n_simbolos']} símbolos · última {s['dmax']} "
            f"({s['opero_ultima']} operados)")


# ── Consultas ─────────────────────────────────────────────────────────────
def at(simbolo: str, fecha: str, campo: str = "last") -> Optional[float]:
    m = loaded()
    if m is None or campo not in m.mat:
        return None
    i, j = m.idx_f.get(fecha), m.idx_s.get(simbolo)
    if i is None or j is None:
        return None
    v = float(m.mat[campo][i, j])
    return v if v == v else None


def serie(simbolo: str, campo: str = "last", n: int = 0, solo_opero: bool = False) -> Tuple[List[str], List[float]]:
    """(fechas, valores) sin huecos (NaN afuera); `n` = últimas n ruedas con
    dato; `solo_opero` descarta ruedas con precio pegajoso."""
    m = loaded()
    if m is None or campo not in m.mat:
        return [], []
    j = m.idx_s.get(simbolo)
    if j is None:
        return [], []
    col = m.mat[campo][:, j]
    ok = np.isfinite(col)
    if solo_opero:
        ok &= m.opero[:, j]
    idx = np.flatnonzero(ok)
    if n and len(idx) > n:
        idx = idx[-n:]
    return [m.fechas[i] for i in idx], [float(col[i]) for i in idx]


def _ancla(hoy: Optional[date]) -> str:
    """Último día HÁBIL ≤ hoy (un sábado/feriado el último es el del viernes)."""
    if hoy is None:
        from backend.locale_ar import hoy_ba
        hoy = hoy_ba()
    try:
        while not _es_habil(hoy):
            hoy -= timedelta(days=1)
    except Exception:  # noqa: BLE001
        while hoy.weekday() >= 5:
            hoy -= timedelta(days=1)
    return hoy.isoformat()


def ret(simbolo: str, n: int = 5, campo: str = "last", hoy: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Retorno del último valor (rueda ≤ ancla) contra la n-ésima rueda con dato
    anterior al ancla. None si faltan ruedas."""
    m = loaded()
    if m is None or campo not in m.mat:
        return None
    j = m.idx_s.get(simbolo)
    if j is None:
        return None
    ancla = _ancla(hoy)
    k = bisect.bisect_left(m.fechas, ancla)          # ruedas < ancla
    col = m.mat[campo][:, j]
    prev = np.flatnonzero(np.isfinite(col[:k]) & (col[:k] > 0))
    if len(prev) < n:
        return None
    i0 = int(prev[-n])
    k1 = bisect.bisect_right(m.fechas, ancla)         # ruedas ≤ ancla
    cur = np.flatnonzero(np.isfinite(col[:k1]) & (col[:k1] > 0))
    if not len(cur):
        return None
    i1 = int(cur[-1])
    if i1 <= i0:
        return None
    p0, p1 = float(col[i0]), float(col[i1])
    return {"ret": p1 / p0 - 1.0, "desde": m.fechas[i0], "hasta": m.fechas[i1], "px0": p0, "px1": p1}


def vector_ref(n: int = 5, hoy: Optional[date] = None, campo: str = "last",
               plazo: str = "24hs") -> Dict[str, tuple]:
    """{código: (precio, fecha)} de la n-ésima rueda ANTERIOR al ancla con
    precio > 0, para los símbolos del plazo — misma semántica que
    historico_byma.ref_5d, sobre TODOS los símbolos del cierre completo.
    Cacheado por (firma, ancla, n, campo, plazo)."""
    m = loaded()
    if m is None or campo not in m.mat:
        return {}
    ancla = _ancla(hoy)
    key = (id(m), ancla, int(n), campo, plazo)
    with _lock:
        c = _vref_cache.get(key)
    if c is not None:
        return c
    k = bisect.bisect_left(m.fechas, ancla)
    out: Dict[str, tuple] = {}
    if k >= n:
        sub = m.mat[campo][:k, :]
        valid = np.isfinite(sub) & (sub > 0)
        cnt = valid.sum(axis=0)
        for j in np.flatnonzero(cnt >= n):
            if plazo and m.plazos[j] != plazo:
                continue
            idx = np.flatnonzero(valid[:, j])
            i = int(idx[-n])
            out[m.codes[j]] = (float(sub[i, j]), date.fromisoformat(m.fechas[i]))
    with _lock:
        if len(_vref_cache) > 32:
            _vref_cache.clear()
        _vref_cache[key] = out
    return out


# ── Backfill desde la base px/tasas ───────────────────────────────────────
def importar_base(force: bool = False) -> Dict[str, Any]:
    """Convierte la base px/tasas (espejo parquet) en particiones para las
    fechas que todavía no tienen una — la matriz arranca con toda la historia
    de bonos. Sólo la máquina writer (salvo `force`); idempotente."""
    from backend.config import settings
    from backend.services import symbols as syms

    if not settings.historico_base_writer and not force:
        return {"skipped": "base_writer=0"}
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        return {"skipped": "sin carpeta Delta Bases"}
    pq = os.path.splitext(os.path.join(hist_dir, HIST_FILENAME))[0] + ".parquet"
    if not os.path.isfile(pq):
        return {"skipped": "sin espejo parquet de la base"}
    try:
        df = pd.read_parquet(pq)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"base ilegible: {exc}"}
    if not len(df) or "symbol" not in df.columns or "fecha_hoy" not in df.columns:
        return {"skipped": "base sin filas"}
    existentes = {f for f, _ in particiones()}
    df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"]).dt.date
    n = 0
    for fecha, g in df.groupby("fecha_hoy"):
        if fecha.isoformat() in existentes:
            continue
        # la variante base gana sobre la proyectada (mismo símbolo)
        g = g.assign(_j=g["Código"].astype(str).str.endswith("j")).sort_values("_j")
        g = g.drop_duplicates(subset=["symbol"], keep="first")
        rows = []
        for r in g.to_dict("records"):
            sym = str(r["symbol"])
            code, plazo = syms.split_md_symbol(sym)
            src = r.get("Price Source")
            rows.append({
                "fecha_hoy": fecha, "symbol": sym, "code": code, "plazo": plazo,
                "last": r.get("Last Price"), "last_size": None, "last_ts": (str(r["Price Date"]) if r.get("Price Date") is not None else None),
                "close": r.get("Close Price"), "close_ts": None,
                "open": None, "high": None, "low": None, "bid": None, "bid_size": None,
                "offer": None, "offer_size": None, "volume": None, "nominal": None, "trade_count": None,
                "opero": bool(src == "LA" and _fecha_dato(r.get("Price Date")) == fecha),
                "codigo_calc": r.get("Código"), "price_ref": r.get("Last Price"), "price_source": src,
                "tirea": r.get("TIREA"), "tna": r.get("TNA"), "tem": r.get("TEM"),
                "paridad": r.get("Paridad"), "duration": r.get("Duration"),
            })
        out = pd.DataFrame(rows)
        for col in ("symbol", "code", "plazo", "last_ts", "close_ts", "price_source", "codigo_calc"):
            out[col] = out[col].astype("string")
        escribir_particion(out, hist_dir, fecha)
        n += 1
    if n:
        refresh()
        logger.info("[cierres] backfill desde la base: %d particiones nuevas", n)
    return {"importadas": n, "existentes": len(existentes)}


def prime() -> None:
    """Warmup: si no hay particiones y la base existe, backfill (writer);
    después carga la matriz."""
    try:
        if not particiones():
            r = importar_base()
            if r.get("importadas"):
                logger.info("[cierres] backfill inicial: %s", r)
    except Exception:  # noqa: BLE001
        logger.exception("[cierres] backfill inicial falló")
    ensure_loaded()
