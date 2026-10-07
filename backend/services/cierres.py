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
import time
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
# Single-flight de la RECARGA: dos threads con la firma vencida (price action +
# Históricos disparados juntos tras el cierre) leían las N particiones y
# armaban la matriz DOS veces a la vez — el pico de RAM de la recarga se
# duplicaba (frames + concat + matrices × 2). El segundo espera y usa la del
# primero (auditoría 30/09). Corre en executors, nunca en el event loop.
_load_lock = threading.Lock()
# `completa`: la matriz publicada se armó con TODAS las particiones legibles;
# `retry_at`: hasta cuándo no volver a intentar una carga degradada.
_cache: Dict[str, Any] = {"sig": None, "data": None, "completa": True, "retry_at": 0.0,
                          "degradada_sig": None}
_vref_cache: Dict[tuple, Dict[str, tuple]] = {}
_RETRY_S = 60.0
# Firma memoizada por los mtimes de las carpetas por año: `signature()`
# listaba el árbol cierres/ entero (un listdir de ~250 entradas por año) y la
# llaman las rutas de Históricos EN CADA REQUEST para la key de su cache de
# HTML — sobre OneDrive un listado grande cuesta decenas de ms. Toda
# partición nueva / pisada / sincronizada entra por un rename dentro de su
# carpeta de año, y el rename toca el mtime de la carpeta: alcanza con
# listar la raíz (pocas entradas) y hacer un stat por año para saber si el
# listado completo sigue valiendo. `refresh()` lo borra igual.
_sig_memo: Dict[str, Any] = {"dirs": None, "sig": None}


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


def particiones(strict: bool = False) -> List[Tuple[str, str]]:
    """[(fecha ISO, path)] ascendente de las particiones existentes.

    `strict=True` (los que ESCRIBEN: `importar_base` / `prime`): un error al
    listar (OneDrive a medio sincronizar, permisos) sube en vez de leerse como
    "no hay particiones" — con [] el backfill daba por faltante cada fecha de
    la base y `escribir_particion` PISABA las particiones reales (OHLC, puntas,
    volumen y todos los símbolos sin ficha) con filas sólo-base."""
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
        if strict:
            raise
        return []
    return sorted(out)


def _signature_disco() -> tuple:
    parts = particiones()
    if not parts:
        return (0, "", 0, ())
    try:
        m = os.stat(parts[-1][1]).st_mtime_ns
    except OSError:
        m = 0
    dm = []
    for d in sorted({os.path.dirname(p) for _, p in parts}):
        try:
            dm.append(os.stat(d).st_mtime_ns)
        except OSError:
            dm.append(0)
    return (len(parts), parts[-1][0], m, tuple(dm))


def _carpetas_anio() -> tuple:
    """((carpeta, mtime_ns), …) de las carpetas por año: la huella barata que
    decide si el listado completo memoizado sigue valiendo."""
    root = dir_path()
    if not root or not os.path.isdir(root):
        return ()
    out = []
    try:
        for y in sorted(os.listdir(root)):
            yd = os.path.join(root, y)
            try:
                st = os.stat(yd)
            except OSError:
                continue
            if os.path.isdir(yd):
                out.append((y, st.st_mtime_ns))
    except OSError:
        return ()
    return tuple(out)


def signature() -> tuple:
    """(n particiones, última fecha, mtime de la última, mtimes de las carpetas
    por año): cambia con el cierre, con la recaptura (pisa la última), con un
    backfill y con la corrección de una partición VIEJA — `os.replace` toca el
    mtime del directorio aunque la última no cambie (antes esa corrección no
    invalidaba la matriz hasta reiniciar). El listado completo se memoiza
    mientras las carpetas por año no cambien de mtime (ver `_sig_memo`)."""
    dirs = _carpetas_anio()
    with _lock:
        if _sig_memo["sig"] is not None and _sig_memo["dirs"] == dirs:
            return _sig_memo["sig"]
    sig = _signature_disco()
    with _lock:
        _sig_memo["sig"] = sig
        _sig_memo["dirs"] = dirs
    return sig


def _build(df: pd.DataFrame, copy: bool = True) -> Optional[Matriz]:
    """Matriz densa desde las filas de las particiones. `copy=False` cuando el
    frame es propio (el concat de `_load`): la copia duplicaba el DataFrame
    entero durante la recarga (auditoría 30/09: la matriz de 5 años son
    ~190 MB de arrays; el frame que la origina, otro tanto)."""
    if df is None or not len(df):
        return None
    if copy:
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


def _vigente(sig: tuple, now: float) -> bool:
    """Bajo `_lock`: la matriz en memoria sirve para esta firma (o hasta que
    venza el reintento de una carga degradada / parcial)."""
    if _cache["sig"] == sig and (_cache["completa"] or now < _cache["retry_at"]):
        return True
    # intento degradado reciente: la anterior hasta el reintento
    return _cache["degradada_sig"] == sig and now < _cache["retry_at"]


def _leer_particiones() -> Tuple[Optional[Matriz], int]:
    """(matriz, particiones fallidas). Los frames por partición se sueltan
    apenas existe el concat: durante la recarga conviven el frame unido y las
    matrices, no además las N piezas."""
    data: Optional[Matriz] = None
    fallidas = 0
    parts = particiones()
    if not parts:
        return None, 0
    frames = []
    for _iso, p in parts:
        try:
            frames.append(pd.read_parquet(p))
        except Exception as exc:  # noqa: BLE001 — una partición rota no voltea la matriz
            fallidas += 1
            logger.warning("[cierres] partición ilegible %s: %s", p, exc)
    if frames:
        try:
            df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
            del frames
            data = _build(df, copy=False)
        except Exception:  # noqa: BLE001
            logger.exception("[cierres] build de la matriz falló")
            data = None
            fallidas += 1
    return data, fallidas


def _load() -> Optional[Matriz]:
    sig = signature()
    now = time.monotonic()
    with _lock:
        if _vigente(sig, now):
            return _cache["data"]
    with _load_lock:                        # single-flight: UNA lectura por recarga
        now = time.monotonic()
        with _lock:
            if _vigente(sig, now):          # otro thread la cargó mientras esperábamos
                return _cache["data"]
            previa, previa_completa = _cache["data"], _cache["completa"]
        data, fallidas = _leer_particiones()
        return _publicar(sig, now, data, fallidas, previa, previa_completa)


def _publicar(sig: tuple, now: float, data: Optional[Matriz], fallidas: int,
              previa: Optional[Matriz], previa_completa: bool) -> Optional[Matriz]:
    with _lock:
        if fallidas and previa is not None and previa_completa:
            # Carga DEGRADADA (un lock de OneDrive, un parquet a medio bajar):
            # no se publica una matriz a la que le falta un día como si fuera
            # completa — antes ese día desaparecía hasta un refresh explícito.
            # Se conserva la íntegra anterior y se reintenta en _RETRY_S.
            _cache["degradada_sig"] = sig
            _cache["retry_at"] = now + _RETRY_S
            logger.warning("[cierres] %d partición(es) ilegible(s): sigo con la matriz anterior "
                           "(%s → %s) y reintento en %d s", fallidas, previa.fechas[0], previa.fechas[-1], int(_RETRY_S))
            return previa
        _cache["sig"] = sig
        _cache["data"] = data
        _cache["completa"] = fallidas == 0
        _cache["retry_at"] = now + _RETRY_S
        _cache["degradada_sig"] = None
        _vref_cache.clear()
    if fallidas:
        logger.warning("[cierres] matriz PARCIAL (%d partición(es) ilegible(s)): reintento en %d s",
                       fallidas, int(_RETRY_S))
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
        _cache["completa"] = True
        _cache["retry_at"] = 0.0
        _cache["degradada_sig"] = None
        _sig_memo["sig"] = None
        _sig_memo["dirs"] = None
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
    from backend.services import symbols as syms
    from backend.services.historico_writer import writer_estado

    we = writer_estado()
    if not we["writer"] and not force:
        return {"skipped": we["motivo"]}
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
    try:
        existentes = {f for f, _ in particiones(strict=True)}
    except OSError as exc:
        return {"error": f"no pude listar las particiones ({exc}): no importo para no pisarlas"}
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
                # "RC" = fila reconstruida desde el cierre previo con fecha que
                # mandó el feed: si esa fecha es la rueda, el bono operó ese día.
                "opero": bool(src in ("LA", "RC") and _fecha_dato(r.get("Price Date")) == fecha),
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
        if not particiones(strict=True):
            r = importar_base()
            if r.get("importadas"):
                logger.info("[cierres] backfill inicial: %s", r)
            elif r.get("error"):
                logger.warning("[cierres] backfill inicial: %s", r["error"])
    except Exception:  # noqa: BLE001
        logger.exception("[cierres] backfill inicial falló")
    ensure_loaded()
