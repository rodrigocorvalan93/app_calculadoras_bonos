"""Fondos — atribución del rendimiento por tenencias (sólo superuser, 26/11).

Qué activos y categorías explican el retorno de un fondo en una ventana, y
cuánto le sacó cada uno al benchmark. Método (contribución por tenencias):

    contribución_i(t) = peso_i al abrir el día t × retorno_i del día t
    peso_i   = Valor_i(t−1) / Patrimonio(t−1)
    retorno_i = precio implícito (Valor / Cantidad) de t contra t−1

con las carteras diarias de la casa (`Carteras/AAAAMMDD/…_Delta_Composicion.xlsx`
+ `…_Delta_PN.xlsx`). Lo que el precio no ve se completa con datos:

- **cobros** (cupón / amortización): si la tenencia tiene ficha en la app, el
  pago por VN del cronograma (`pricing.cashflow_table`) se suma al retorno del
  día en que el precio cae por el corte (se busca la caída a ±3 días de la
  fecha de pago; sin caída visible no se suma nada);
- **vencimientos**: lo que sale de la cartera el día que vence devenga hasta
  ahí (tasa del plazo fijo; descuento a la par de un cheque / letra; pago
  final de un bono con ficha). Una venta no tiene precio de salida: no suma;
- un **salto** de precio mayor a `SALTO` en un día (cambio de unidad, split)
  no se atribuye y queda listado.

El día t se encadena con el factor de la cuotaparte hasta t−1, así las
contribuciones suman en puntos del retorno de la ventana. La diferencia entre
la cuotaparte y la suma de contribuciones queda EXPLÍCITA: honorarios (se
estiman con la tabla de la casa), operaciones del día a un precio distinto del
cierre y lo que falte. Contra el benchmark: aporte_i = peso × (retorno_i −
retorno del benchmark), encadenado igual.

Carga: los Excel diarios los convierte `backend.tools.fondos_carteras` en un
PROCESO APARTE (≈ 0,2 s por día, un año la primera vez) a un parquet por día en
la carpeta local de la máquina; acá sólo se leen esos parquet, por fondo y a
pedido (≈ 0,3 s la primera vez que se abre la atribución de un fondo, en el
executor) y queda en memoria. Nada de esto corre en un request de los paneles
live.
"""
from __future__ import annotations

import atexit
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from backend.services import estado_local
from backend.services import fondos as fsvc
from backend.services import fondos_calc as fc
from backend.tools import fondos_carteras as fcart

logger = logging.getLogger("backend.fondos.attr")

REPO_ROOT = Path(__file__).resolve().parents[2]

SALTO = 0.35                  # |retorno diario| mayor a esto no se atribuye (cambio de unidad / split)
_RECHEQUEO_S = 600.0          # cada cuánto se mira si hay un día nuevo de carteras
_REFRESCO_ARMANDO_S = 15.0    # mientras el caché se arma, un fondo se relee a lo sumo cada esto
_MAX_FONDOS = 24              # fondos en memoria
_VENTANA_PAGO_D = 3           # días alrededor de la fecha de pago donde se busca el corte de cupón

DIMS: Tuple[Tuple[str, str], ...] = (
    ("clasif", "Tipo de activo"), ("ajuste", "Ajuste"), ("instr", "Instrumento"),
    ("sector", "Sector"), ("pago", "Moneda de pago"),
)
DIM_KEYS = tuple(k for k, _ in DIMS)

F_OK, F_TASA, F_SIN_PRECIO, F_SALTO, F_COBRO, F_VENCE = 0, 1, 2, 3, 4, 5


@dataclass
class FondoAttr:
    cod: int
    dias: np.ndarray                                # días con cartera del fondo (datetime64[D])
    pn: np.ndarray                                  # patrimonio por día
    ev_dia: np.ndarray                              # evento: índice del día (en `dias`) en que rinde
    ev_w: np.ndarray                                # peso al abrir ese día
    ev_r: np.ndarray                                # retorno del día
    ev_fila: np.ndarray                             # fila de la que salen los atributos
    ev_flag: np.ndarray
    fi_dia: np.ndarray                              # filas (tenencia × día): día
    fi_w: np.ndarray                                # peso al cierre
    fi_key: np.ndarray                              # id de la tenencia
    codigos: Dict[str, np.ndarray]                  # dimensión → código por fila
    etiquetas: Dict[str, List[str]]
    key_lbl: List[str]
    key_desc: List[str]
    saltos: List[Dict[str, Any]] = field(default_factory=list)
    firma: Tuple = ()
    cargado: float = 0.0


_lock = threading.Lock()
_estado: Dict[str, Any] = {"cargando": False, "chequeo": 0.0, "error": None, "progreso": None,
                           "version": 0, "listo": False, "proc": None}
_fondos: Dict[int, FondoAttr] = {}
_fondo_locks: Dict[int, threading.Lock] = {}
_pagos_memo: Dict[Tuple[str, str], Optional[Tuple[List[Tuple[np.datetime64, float]], bool]]] = {}


# ── carpetas ─────────────────────────────────────────────────────────────────
def carteras_dir() -> Optional[str]:
    env = os.getenv("FONDOS_CARTERAS_DIR")
    if env:
        return env if os.path.isdir(env) else None
    base = fsvc.base_dir()
    if not base:
        return None
    p = os.path.join(base, "Carteras")
    return p if os.path.isdir(p) else None


def cache_dir() -> str:
    return str(estado_local.ruta("fondos_carteras", "FONDOS_ATTR_CACHE"))


def dias_atras() -> int:
    try:
        return max(30, int(os.getenv("FONDOS_ATTR_DIAS") or fcart.DIAS_DEFAULT))
    except ValueError:
        return fcart.DIAS_DEFAULT


def _archivos() -> List[str]:
    """Parquets del caché (AAAAMMDD.parquet) ascendentes."""
    try:
        return sorted(n for n in os.listdir(cache_dir()) if len(n) == 16 and n.endswith(".parquet") and n[:8].isdigit())
    except OSError:
        return []


# ── armado del caché (proceso aparte) ────────────────────────────────────────
def _matar_hijo() -> None:
    p = _estado.get("proc")
    if p is not None and p.poll() is None:
        try:
            p.terminate()
        except OSError:
            pass


atexit.register(_matar_hijo)


def _convertir(carteras: str, out: str) -> None:
    """Corre el conversor y va dejando el avance en memoria. En un proceso
    aparte (`FONDOS_ATTR_SUBPROCESO=0` lo corre acá: tests y herramientas)."""
    if (os.getenv("FONDOS_ATTR_SUBPROCESO") or "1") == "0":
        fcart.correr(carteras, out, dias_atras())
        return
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.tools.fondos_carteras", "--carteras", carteras, "--out", out,
         "--dias", str(dias_atras()), "--quiet"],
        cwd=str(REPO_ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags)
    _estado["proc"] = proc
    prog_path = os.path.join(out, "progreso.json")
    while proc.poll() is None:
        time.sleep(1.0)
        p = fcart.leer_json(prog_path)
        if p.get("pid") == proc.pid:
            with _lock:
                _estado["progreso"] = {"total": p.get("total", 0), "hechos": p.get("hechos", 0)}
                _estado["version"] += 1 if p.get("hechos") else 0
    _estado["proc"] = None
    if proc.returncode not in (0, None):
        raise RuntimeError(f"el conversor de carteras terminó con código {proc.returncode}")


def _tarea() -> None:
    try:
        carteras = carteras_dir()
        if not carteras:
            with _lock:
                _estado["error"] = ("No encuentro la carpeta Carteras dentro de Delta Bases: la atribución necesita "
                                    "las carteras diarias (Carteras\\AAAAMMDD\\…_Delta_Composicion.xlsx).")
                _estado["listo"] = bool(_archivos())
            return
        out = cache_dir()
        os.makedirs(out, exist_ok=True)
        try:
            falta, _man, viejos = fcart.pendientes(carteras, out, fcart.desde_de(dias_atras()))
            if falta or viejos:
                with _lock:
                    _estado["progreso"] = {"total": len(falta), "hechos": 0}
                t0 = time.perf_counter()
                _convertir(carteras, out)
                prog = fcart.leer_json(os.path.join(out, "progreso.json"))
                errores = prog.get("errores") or []
                logger.info("[fondos] carteras: %d día(s) al caché en %.1f s%s", len(falta), time.perf_counter() - t0,
                            f" · {len(errores)} sin leer ({errores[0]['dia']}: {errores[0]['error']})" if errores else "")
                with _lock:
                    _estado["version"] += 1
                    _estado["error"] = (f"{len(errores)} día(s) de carteras no se pudieron leer (el primero, "
                                        f"{errores[0]['dia']}: {errores[0]['error']}). Se reintenta solo."
                                        if errores else None)
            else:
                with _lock:
                    _estado["error"] = None
        except Exception as exc:  # noqa: BLE001 — queda el motivo para la pestaña
            logger.warning("[fondos] no pude armar el caché de carteras: %s", exc, exc_info=True)
            with _lock:
                _estado["error"] = f"No pude armar la historia de carteras: {type(exc).__name__}: {exc}"
        with _lock:
            _estado["listo"] = True
    finally:
        with _lock:
            _estado["cargando"] = False
            _estado["progreso"] = None


def asegurar() -> Dict[str, Any]:
    """Estado del caché de carteras; dispara (en un thread) el armado o el
    chequeo de días nuevos. Nunca lee disco acá."""
    ahora = time.monotonic()
    lanzar = False
    with _lock:
        if not _estado["cargando"] and ahora - _estado["chequeo"] >= _RECHEQUEO_S:
            _estado["cargando"] = True
            _estado["chequeo"] = ahora
            lanzar = True
    if lanzar:
        threading.Thread(target=_tarea, name="fondos-carteras", daemon=True).start()
    return estado()


def armar_ahora() -> Dict[str, Any]:
    """Armado síncrono (tests y herramientas)."""
    with _lock:
        _estado["cargando"] = True
        _estado["chequeo"] = time.monotonic()
    _tarea()
    return estado()


def estado() -> Dict[str, Any]:
    with _lock:
        return {"cargando": bool(_estado["cargando"]), "error": _estado["error"], "listo": bool(_estado["listo"]),
                "progreso": dict(_estado["progreso"]) if _estado["progreso"] else None,
                "version": int(_estado["version"])}


def reset() -> None:
    with _lock:
        _estado.update({"cargando": False, "chequeo": 0.0, "error": None, "progreso": None, "listo": False})
        _estado["version"] += 1
    _fondos.clear()
    _pagos_memo.clear()


# ── cobros de la ficha ───────────────────────────────────────────────────────
def _pagos(ticker: str, isin: str, pago: str) -> Optional[Tuple[List[Tuple[np.datetime64, float]], bool]]:
    """([(fecha de pago, fracción del VN que entra)], el bono paga en dólares)
    del cronograma de la ficha de la app para una tenencia, o None si no tiene
    ficha. Memo por código y día."""
    t = (ticker or "").strip()
    if not t or t.upper() == "NC":
        return None
    hoy = str(np.datetime64("today", "D"))
    k = (f"{t}|{isin}|{pago}", hoy)
    if k in _pagos_memo:
        return _pagos_memo[k]
    out: Optional[Tuple[List[Tuple[np.datetime64, float]], bool]] = None
    try:
        from backend.services import bond_universe, esco, pricing
        code = bond_universe.resolve(t)
        if code is None:
            f = esco.resolver(t, isin or None, pago or None, None)
            code = f.calc if f is not None else None
        if code is not None:
            tabla = pricing.cashflow_table(code, None, "todos")
            pagos: List[Tuple[np.datetime64, float]] = []
            for r in tabla.get("rows") or []:
                fecha = r.get("fecha_pmt") or r.get("fecha_cpn")
                tot = r.get("total")
                if fecha is None or tot is None or not np.isfinite(tot) or tot <= 0:
                    continue
                pagos.append((np.datetime64(str(fecha)[:10], "D"), float(tot)))
            meta = pricing.bond_meta(code) or {}
            out = (pagos, str(meta.get("moneda") or "").upper() in ("USD", "USB"))
    except Exception as exc:  # noqa: BLE001 — una ficha rara no rompe la atribución
        logger.debug("[fondos] sin cronograma para %s: %s", t, exc)
        out = None
    if len(_pagos_memo) > 4000:
        _pagos_memo.clear()
    _pagos_memo[k] = out
    return out


# ── carga de un fondo ────────────────────────────────────────────────────────
def _leer_filas(cod: int, archivos: List[str]):
    import pyarrow as pa
    import pyarrow.parquet as pq
    base = cache_dir()
    tablas = []
    for i, nombre in enumerate(archivos):
        try:
            t = pq.read_table(os.path.join(base, nombre), filters=[("cod", "=", int(cod))])
        except Exception as exc:  # noqa: BLE001 — un parquet a medio escribir: se saltea
            logger.debug("[fondos] %s ilegible (%s)", nombre, exc)
            continue
        if t.num_rows:
            tablas.append(t.append_column("gdia", pa.array(np.full(t.num_rows, i, dtype=np.int32))))
    if not tablas:
        return None
    return pa.concat_tables(tablas, promote_options="default").to_pandas()


def _armar_fondo(cod: int, archivos: List[str], moneda: str,
                 ccl_en: Optional[Callable[[np.datetime64], Optional[float]]] = None,
                 con_fichas: bool = True) -> Optional[FondoAttr]:
    import pandas as pd
    df = _leer_filas(cod, archivos)
    if df is None or not len(df):
        return None
    es_pn = (df["instr"] == fcart.FILA_PN).to_numpy()
    dfp = df[es_pn]
    df = df[~es_pn]
    if not len(df):
        return None
    g = df["gdia"].to_numpy()
    gdias = np.unique(g)                                    # días (globales) con cartera del fondo
    dias = np.array([f"{archivos[i][:4]}-{archivos[i][4:6]}-{archivos[i][6:8]}" for i in gdias], dtype=fc.D)
    t_loc = np.searchsorted(gdias, g).astype(np.int32)
    T = len(gdias)
    v = df["v"].to_numpy(dtype=float)
    q = df["q"].to_numpy(dtype=float)
    # patrimonio por día: el del archivo de PN o, si falta, la suma de la cartera
    pn = np.full(T, np.nan)
    if len(dfp):
        tp = np.searchsorted(gdias, dfp["gdia"].to_numpy())
        okp = (tp < T)
        okp[okp] &= gdias[tp[okp]] == dfp["gdia"].to_numpy()[okp]
        pn[tp[okp]] = dfp["v"].to_numpy(dtype=float)[okp]
    suma = np.bincount(t_loc, weights=v, minlength=T)
    pn = np.where(np.isfinite(pn) & (pn > 0), pn, suma)
    pn[pn <= 0] = np.nan

    ident = (df["isin"].astype(str) + "|" + df["ticker"].astype(str) + "|" + df["inv"].astype(str) + "|"
             + df["vto"].astype(str))
    key, _uni = pd.factorize(ident)
    orden = np.lexsort((t_loc, key))
    df = df.iloc[orden]
    key, t_loc, v, q = key[orden].astype(np.int32), t_loc[orden], v[orden], q[orden]
    tasa = df["tasa"].to_numpy(dtype=float)
    vd = pd.to_datetime(df["vto"].astype(str).replace({"": None}), errors="coerce").to_numpy().astype(fc.D)
    n = len(df)
    w = v / pn[t_loc]
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.where(q != 0, v / q, np.nan)

    # etiquetas y dimensiones
    codigos: Dict[str, np.ndarray] = {}
    etiquetas: Dict[str, List[str]] = {}
    for dim in DIM_KEYS:
        c, cats = pd.factorize(df[dim].astype(str).replace({"": "Sin dato"}))
        codigos[dim] = c.astype(np.int32)
        etiquetas[dim] = [str(x) for x in cats]
    tick = df["ticker"].astype(str).to_numpy()
    inv = df["inv"].astype(str).to_numpy()
    primera = np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]]))   # primera fila de cada tenencia
    key_lbl = [tick[i] if tick[i] and tick[i].upper() != "NC" else (inv[i] or "?") for i in primera]
    key_desc = [inv[i] for i in primera]

    # eventos de las tenencias que SIGUEN de un día al otro
    sigue = np.zeros(n, dtype=bool)
    sigue[1:] = (key[1:] == key[:-1]) & (t_loc[1:] == t_loc[:-1] + 1)
    j = np.flatnonzero(sigue)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(np.isfinite(p[j]) & np.isfinite(p[j - 1]) & (p[j - 1] != 0), p[j] / p[j - 1] - 1.0, 0.0)
    ev_dia = [t_loc[j]]
    ev_w = [w[j - 1]]
    ev_r = [r]
    ev_fila = [j]
    ev_flag = [np.zeros(len(j), dtype=np.int8)]

    # cobros (cupón / amortización) de las tenencias con ficha: el pago por VN
    # se suma el día en que el precio muestra el corte.
    paga_usd: Dict[int, bool] = {}
    cronos: Dict[int, List[Tuple[np.datetime64, float]]] = {}
    if con_fichas and len(j):
        pago_txt = df["pago"].astype(str).to_numpy()
        isin = df["isin"].astype(str).to_numpy()
        for k in np.unique(key[j]):
            i0 = primera[k]
            if not tick[i0] or tick[i0].upper() == "NC" or q[i0] == 0:
                continue
            pg = _pagos(tick[i0], isin[i0], pago_txt[i0])
            if pg is None or not pg[0]:
                continue
            en_rango = [(f, tot) for f, tot in pg[0] if dias[0] - 5 <= f <= dias[-1] + 5]
            if en_rango:
                cronos[int(k)] = en_rango
                paga_usd[int(k)] = pg[1]
        if cronos:
            kj = key[j]
            fondo_usd = moneda in ("USD", "USB")
            for k, pagos in cronos.items():
                pos = np.flatnonzero(kj == k)               # eventos de la tenencia (ordenados por día)
                if not len(pos):
                    continue
                dk = dias[t_loc[j[pos]]]
                for fpago, tot in pagos:
                    cerca = np.flatnonzero(np.abs((dk - fpago).astype(int)) <= _VENTANA_PAGO_D)
                    if not len(cerca):
                        continue
                    e = pos[cerca[np.argmin(r[pos[cerca]])]]   # el día del corte: la caída más fuerte
                    pprev = p[j[e] - 1]
                    if not np.isfinite(pprev) or pprev <= 0:
                        continue
                    conv = 1.0
                    if paga_usd[k] != fondo_usd:
                        fx = ccl_en(dias[t_loc[j[e]]]) if ccl_en is not None else None
                        if not fx:
                            continue
                        conv = fx if paga_usd[k] else 1.0 / fx
                    ingreso = tot * conv / pprev
                    if not (0 < ingreso < 1.2) or r[e] > -0.3 * ingreso:
                        continue                              # sin corte visible en el precio: no se suma nada
                    r[e] += ingreso
                    ev_flag[0][e] = F_COBRO

    # tenencias que SALEN: sólo rinden si vencieron (lo demás es una venta sin precio)
    sale = np.ones(n, dtype=bool)
    sale[:-1] = ~((key[1:] == key[:-1]) & (t_loc[1:] == t_loc[:-1] + 1))
    sale &= t_loc < T - 1
    s = np.flatnonzero(sale)
    if len(s):
        dsig = dias[t_loc[s] + 1]
        gap = (dsig - dias[t_loc[s]]).astype(int).astype(float)
        rs = np.zeros(len(s))
        fl = np.full(len(s), F_SIN_PRECIO, dtype=np.int8)
        sin_vto = np.isnat(vd[s])
        vence = ~sin_vto & (vd[s] <= dsig)
        # plazo fijo / caución: la tasa de la fila hasta el día siguiente
        con_tasa = np.isfinite(tasa[s]) & (tasa[s] > 0) & (tasa[s] < 500) & (vence | sin_vto)
        rs[con_tasa] = tasa[s][con_tasa] / 100.0 * gap[con_tasa] / 365.0
        fl[con_tasa] = F_TASA
        # descuento (cheque / pagaré / letra) que llega a la par
        par = vence & ~con_tasa & np.isfinite(p[s]) & (p[s] > 0.8) & (p[s] <= 1.0)
        rs[par] = 1.0 / p[s][par] - 1.0
        fl[par] = F_VENCE
        # bono con ficha: el pago final contra el último precio
        if cronos:
            for idx in np.flatnonzero(vence & ~con_tasa & ~par):
                k = int(key[s[idx]])
                pagos = cronos.get(k)
                if not pagos or not np.isfinite(p[s[idx]]) or p[s[idx]] <= 0:
                    continue
                f_ult, tot = pagos[-1]
                if abs(int((f_ult - dsig[idx]).astype(int))) > 6:
                    continue
                conv = 1.0
                if paga_usd[k] != (moneda in ("USD", "USB")):
                    fx = ccl_en(dsig[idx]) if ccl_en is not None else None
                    if not fx:
                        continue
                    conv = fx if paga_usd[k] else 1.0 / fx
                rr = tot * conv / p[s[idx]] - 1.0
                if abs(rr) < 0.15:
                    rs[idx] = rr
                    fl[idx] = F_VENCE
        ev_dia.append(t_loc[s] + 1)
        ev_w.append(w[s])
        ev_r.append(rs)
        ev_fila.append(s)
        ev_flag.append(fl)

    e_dia = np.concatenate(ev_dia).astype(np.int32)
    e_w = np.concatenate(ev_w)
    e_r = np.concatenate(ev_r)
    e_fila = np.concatenate(ev_fila).astype(np.int32)
    e_flag = np.concatenate(ev_flag)
    e_w = np.where(np.isfinite(e_w), e_w, 0.0)
    e_r = np.where(np.isfinite(e_r), e_r, 0.0)
    # saltos: no se atribuyen y quedan a la vista
    saltos: List[Dict[str, Any]] = []
    fuera = np.flatnonzero(np.abs(e_r) > SALTO)
    for e in fuera[np.argsort(-np.abs(e_w[fuera] * e_r[fuera]))][:12]:
        saltos.append({"activo": key_lbl[key[e_fila[e]]], "fecha": str(dias[e_dia[e]]), "r": float(e_r[e]),
                       "w": float(e_w[e])})
    e_flag[fuera] = F_SALTO
    e_r[fuera] = 0.0
    o = np.argsort(e_dia, kind="stable")
    return FondoAttr(cod=int(cod), dias=dias, pn=pn, ev_dia=e_dia[o], ev_w=e_w[o], ev_r=e_r[o], ev_fila=e_fila[o],
                     ev_flag=e_flag[o], fi_dia=t_loc, fi_w=np.where(np.isfinite(w), w, 0.0), fi_key=key,
                     codigos=codigos, etiquetas=etiquetas, key_lbl=key_lbl, key_desc=key_desc, saltos=saltos,
                     cargado=time.monotonic())


def fondo(d: fsvc.Datos, cafci: int) -> Optional[FondoAttr]:
    """Atribución base de un fondo (lee su historia del caché la primera vez:
    llamar desde el executor). None si el fondo no tiene código de ESCO o no
    hay carteras suyas en el caché."""
    f = d.fondos.get(int(cafci))
    if f is None or f.cod is None:
        return None
    cod = int(f.cod)
    archivos = _archivos()
    firma = (len(archivos), archivos[0] if archivos else "", archivos[-1] if archivos else "", estado()["version"])
    hit = _fondos.get(cod)
    if hit is not None:
        if hit.firma == firma:
            return hit
        # mientras el caché se arma, no releer el fondo en cada sondeo
        if estado()["cargando"] and time.monotonic() - hit.cargado < _REFRESCO_ARMANDO_S:
            return hit
    lk = _fondo_locks.setdefault(cod, threading.Lock())
    with lk:
        hit = _fondos.get(cod)
        if hit is not None and hit.firma == firma:
            return hit
        if not archivos:
            return None
        ccl = d.indices.get("ccl")

        def ccl_en(fecha: np.datetime64) -> Optional[float]:
            if ccl is None:
                return None
            i = int(np.searchsorted(d.fechas, fecha, side="right")) - 1
            while i >= 0 and not np.isfinite(ccl[i]):
                i -= 1
            return float(ccl[i]) if i >= 0 and ccl[i] > 0 else None

        t0 = time.perf_counter()
        fa = _armar_fondo(cod, archivos, f.moneda, ccl_en)
        if fa is None:
            return None
        fa.firma = firma
        if len(_fondos) >= _MAX_FONDOS:
            _fondos.pop(min(_fondos, key=lambda c: _fondos[c].cargado), None)
        _fondos[cod] = fa
        logger.info("[fondos] atribución de %s: %d días · %d eventos en %.2f s", f.corto, len(fa.dias),
                    len(fa.ev_dia), time.perf_counter() - t0)
        return fa


# ── consulta ─────────────────────────────────────────────────────────────────
def _ffill(a: np.ndarray) -> np.ndarray:
    ok = np.isfinite(a)
    idx = np.where(ok, np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = a[idx]
    out[~np.maximum.accumulate(ok)] = np.nan
    return out


def atribucion(fa: FondoAttr, d: fsvc.Datos, cafci: int, clase: Optional[str], vs: str, i0: int, i1: int,
               dim: str = "clasif", top: int = 10) -> Optional[Dict[str, Any]]:
    """Atribución del fondo entre las ruedas `i0` (base) e `i1` de `d.fechas`.
    Se acota a los días con cartera: la ventana efectiva arranca en la primera
    cartera ≥ la base. None si no hay dos carteras en la ventana."""
    dim = dim if dim in DIM_KEYS else "clasif"
    f = d.fondos[int(cafci)]
    col = d.col(cafci, clase)
    y = d.vcp[:, col]
    D0, D1 = d.fechas[i0], d.fechas[i1]
    t0 = int(np.searchsorted(fa.dias, D0, side="left"))
    t1 = int(np.searchsorted(fa.dias, D1, side="right")) - 1
    if t1 - t0 < 1:
        return None
    tramo = fa.dias[t0:t1 + 1]
    pos = np.clip(np.searchsorted(d.fechas, tramo, side="right") - 1, 0, len(d.fechas) - 1)
    yv = _ffill(y[pos].astype(float))
    if not np.isfinite(yv[0]) or not np.isfinite(yv[-1]):
        k = np.flatnonzero(np.isfinite(yv))
        if len(k) < 2:
            return None
        t0, t1 = t0 + int(k[0]), t0 + int(k[-1])
        tramo, pos, yv = fa.dias[t0:t1 + 1], pos[k[0]:k[-1] + 1], yv[k[0]:k[-1] + 1]
    F = yv / yv[0]                                           # factor de la cuotaparte al cierre de cada día
    total = float(F[-1] - 1.0)
    nd = t1 - t0                                             # días de cartera con retorno
    a = int(np.searchsorted(fa.ev_dia, t0 + 1, side="left"))
    b = int(np.searchsorted(fa.ev_dia, t1, side="right"))
    e_dia = fa.ev_dia[a:b] - t0                              # 1..nd
    e_w, e_r, e_fila, e_flag = fa.ev_w[a:b], fa.ev_r[a:b], fa.ev_fila[a:b], fa.ev_flag[a:b]
    Fp = F[e_dia - 1]
    C = e_w * e_r * Fp
    ref, ref_nombre = fsvc.serie_referencia(d, cafci, vs)
    E = None
    bench = None
    if ref is not None:
        bv = _ffill(ref[pos].astype(float))
        if np.isfinite(bv[0]) and bv[0] > 0:
            br = np.zeros(nd + 1)
            br[1:] = bv[1:] / bv[:-1] - 1.0
            br = np.where(np.isfinite(br), br, 0.0)
            E = e_w * (e_r - br[e_dia]) * Fp
            bench = float(bv[-1] / bv[0] - 1.0)
    cartera = float(C.sum())
    dias_corr = int((tramo[-1] - tramo[0]).astype(int))
    fee = d.fees.get((f.cafci, fsvc.clase_corta(d.clases[col].clase)))
    fee_est = None
    if fee is not None:
        # el honorario devenga por día corrido sobre el patrimonio: se encadena igual
        gaps = np.diff(tramo).astype(int).astype(float)
        fee_est = float(-(fee / 365.0 * gaps * F[:-1]).sum())
    residual = total - cartera

    def _grupos(cod_fila: np.ndarray, etiquetas: List[str]) -> List[Dict[str, Any]]:
        g = cod_fila[e_fila]
        n = len(etiquetas)
        c = np.bincount(g, weights=C, minlength=n)
        wp = np.bincount(g, weights=e_w, minlength=n) / nd
        ex = np.bincount(g, weights=E, minlength=n) if E is not None else None
        hoy = fa.fi_dia == t1
        wh = np.bincount(cod_fila[hoy], weights=fa.fi_w[hoy], minlength=n)
        out = []
        for i in np.flatnonzero((np.abs(c) > 1e-12) | (np.abs(wp) > 1e-9) | (np.abs(wh) > 1e-9)):
            out.append({"i": int(i), "nombre": etiquetas[i], "w_prom": float(wp[i]), "w_hoy": float(wh[i]),
                        "c": float(c[i]), "ret": float(c[i] / wp[i]) if abs(wp[i]) > 1e-6 else None,
                        "e": float(ex[i]) if ex is not None else None})
        return out

    grupos = _grupos(fa.codigos[dim], fa.etiquetas[dim])
    grupos.sort(key=lambda r: -abs(r["c"]))
    activos = _grupos(fa.fi_key, fa.key_lbl)
    cod_grupo = np.zeros(len(fa.key_lbl), dtype=np.int64)
    cod_grupo[fa.fi_key] = fa.codigos[dim]                    # grupo de cada tenencia (el de su última fila)
    for r in activos:
        r["desc"] = fa.key_desc[r["i"]]
        r["grupo"] = fa.etiquetas[dim][cod_grupo[r["i"]]]
    activos.sort(key=lambda r: -r["c"])
    suben = [r for r in activos[:top] if r["c"] > 0]
    bajan = [r for r in activos[::-1][:top] if r["c"] < 0]

    # series: cuotaparte vs lo que explica la cartera, y contribución acumulada por grupo
    por_dia = np.bincount(e_dia, weights=C, minlength=nd + 1)
    acum = np.cumsum(por_dia)
    nombres = [g["nombre"] for g in grupos[:6]]
    idx_g = {n: i for i, n in enumerate(fa.etiquetas[dim])}
    gcod = fa.codigos[dim][e_fila]
    series = []
    for nmb in nombres:
        m = gcod == idx_g[nmb]
        series.append({"nombre": nmb, "y": (np.cumsum(np.bincount(e_dia[m], weights=C[m], minlength=nd + 1)) * 100.0)})
    ms = fsvc._muestreo(nd + 1)
    serie = {"x": fsvc._epoch(tramo[ms]), "fondo": fsvc._lista(((F - 1.0) * 100.0)[ms]),
             "cartera": fsvc._lista((acum * 100.0)[ms]),
             "grupos": [{"nombre": s["nombre"], "y": fsvc._lista(s["y"][ms])} for s in series]}

    cuenta = {int(k): int(v) for k, v in zip(*np.unique(e_flag, return_counts=True))}
    sin_precio = e_flag == F_SIN_PRECIO
    return {
        "dim": dim, "desde": str(tramo[0]), "hasta": str(tramo[-1]), "dias": dias_corr, "ruedas": nd,
        "pedido_desde": str(D0), "recortada": bool(tramo[0] > D0),
        "total": total, "cartera": cartera, "residual": residual, "fee": fee, "fee_est": fee_est,
        "otros": (residual - fee_est) if fee_est is not None else None,
        "bench": bench, "ref": ref_nombre if bench is not None else None,
        "exceso": (total - bench) if bench is not None else None,
        "exceso_cartera": float(E.sum()) if E is not None else None,
        "grupos": grupos, "suben": suben, "bajan": bajan, "n_activos": len(activos), "serie": serie,
        "peso_abierto": float(np.bincount(e_dia, weights=e_w, minlength=nd + 1)[1:].mean()) if nd else None,
        "cobros": cuenta.get(F_COBRO, 0), "vencidos": cuenta.get(F_TASA, 0) + cuenta.get(F_VENCE, 0),
        "sin_precio": int(sin_precio.sum()),
        "sin_precio_peso": float(e_w[sin_precio].sum() / nd) if nd else 0.0,
        "saltos": [s for s in fa.saltos if str(tramo[0]) < s["fecha"] <= str(tramo[-1])],
        "cobertura": {"desde": str(fa.dias[0]), "hasta": str(fa.dias[-1]), "dias": int(len(fa.dias))},
    }
