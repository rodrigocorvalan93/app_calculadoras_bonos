"""Históricos · Base — ver y bajar los archivos compartidos de Delta Bases.

El desk a veces necesita la base tal cual (13/10: "dónde puedo ver y
descargar la base, eso debería estar en Históricos"). Hasta acá sólo había
un botón "Guardar base de hoy" y un CSV de Qué pasó; los archivos vivían en
OneDrive y había que ir a buscarlos a mano.

Qué expone (todo lectura; NUNCA se escribe nada desde acá):

- `archivos()`: tarjeta con los archivos — base px/tasas (xlsx + espejo
  parquet, ¿espejo fiel?, ruedas / filas / reales / desde-hasta del resumen
  que el writer ya cachea por firma), serie FX diaria (xlsx + parquet), cierre
  completo (particiones por rueda: cuántas, desde-hasta, bytes) y acciones.
  Tamaño y mtime salen de un `os.stat` por archivo; las particiones se listan
  una vez por `cierres.signature()`.
- `vista(codigo, desde, hasta, n)`: las últimas N filas de la base px/tasas
  (todas las columnas, pre-formateadas es-AR) filtradas por Código y rango.
  La base completa se lee UNA vez por firma (parquet si el espejo es fiel,
  si no el Excel — segundos, por eso corre en el executor) y queda en
  memoria compacta (textos como `category`, ~10 MB por 250 ruedas); después
  cada filtro es una máscara sobre el frame, ~ms. `historico_byma` guarda
  sólo seis métricas por código: para ver symbol / cierre previo / fuente /
  hora hace falta el frame.
- `csv_base(...)`: las mismas filas filtradas como CSV es-AR (`;`, coma
  decimal, BOM: Excel lo abre directo), fechas `DD/MM/AAAA`, hasta
  `CSV_MAX_FILAS`; para la base ENTERA está el parquet / xlsx.
- `csv_cierre(path)`: una partición del cierre completo como CSV.
- `archivo_descargable(que)` / `particion_descargable(fecha)`: la ruta real
  de lo que se puede bajar, SIEMPRE desde una lista cerrada (clave o fecha
  que existe en `cierres.particiones()`), nunca desde texto del usuario.

Nada de esto corre en el event loop: las rutas mandan todo al executor y
cachean el HTML por (parámetros, firmas de los archivos).
"""
from __future__ import annotations

import csv
import io
import logging
import os
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.services import cierres, deltapaths, espejo, fx_hist
from backend.services import historico_writer as hw

logger = logging.getLogger(__name__)

CSV_MAX_FILAS = 250_000
VISTA_MAX = 2_000                 # tope de filas en pantalla
VISTA_DEFAULT = 200

# Columnas de la base en el orden que se muestran y se exportan.
COLUMNAS = ("fecha_hoy", "Código", "symbol", "Last Price", "Close Price", "Variación %",
            "TIREA", "TNA", "TEM", "Paridad", "Duration", "Price Source", "Price Date", "Pata", "FX")
_PCT = ("Variación %", "TIREA", "TNA", "TEM", "Paridad")
_NUM = ("Last Price", "Close Price", "Duration", "FX")
_CAT = ("Código", "symbol", "Price Source", "Pata")

# Archivos descargables por clave: (etiqueta, nombre de archivo relativo a Delta Bases, media type)
_ARCHIVOS: Dict[str, Tuple[str, str, str]] = {
    "px_xlsx": ("Base px/tasas (Excel)", hw.HIST_FILENAME,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "px_parquet": ("Base px/tasas (parquet)", os.path.splitext(hw.HIST_FILENAME)[0] + ".parquet",
                   "application/vnd.apache.parquet"),
    "fx_xlsx": ("Series diarias FX + caución (Excel)", hw.FX_FILENAME,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "fx_parquet": ("Series diarias FX + caución (parquet)", os.path.splitext(hw.FX_FILENAME)[0] + ".parquet",
                   "application/vnd.apache.parquet"),
    "acciones": ("Acciones / CEDEARs (parquet)", hw.ACCIONES_FILENAME, "application/vnd.apache.parquet"),
}

_lock = threading.Lock()
# single-flight: UNA lectura por cambio de firma (patrón de cierres._load_lock);
# `_lock` sólo protege los dicts, nunca se sostiene durante una lectura.
_load_lock = threading.Lock()
_frame: Dict[str, Any] = {"key": None, "df": None, "error": None}
_part_memo: Dict[str, Any] = {"sig": None, "lista": [], "bytes": 0}


# ── Archivos ─────────────────────────────────────────────────────────────────
def _stat(path: Optional[str]) -> Dict[str, Any]:
    """Existencia, bytes y mtime (hora BA) de un archivo. Nunca tira."""
    if not path:
        return {"path": "", "existe": False, "bytes": 0, "mtime": None}
    try:
        st = os.stat(path)
    except OSError:
        return {"path": path, "existe": False, "bytes": 0, "mtime": None}
    return {"path": path, "existe": True, "bytes": int(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime, hw._TZ).strftime("%d/%m/%Y %H:%M")}


def fmt_bytes(n: int) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{n / 1024 ** 3:.2f} GB".replace(".", ",")


def _dmy(d: Any) -> str:
    if d is None:
        return "—"
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    s = str(d)[:10]
    try:
        return date.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return s


def _particiones_memo() -> Tuple[List[Tuple[str, str]], int]:
    """[(fecha, path)] + bytes totales, memoizado por `cierres.signature()`."""
    sig = cierres.signature()
    with _lock:
        if _part_memo["sig"] == sig:
            return _part_memo["lista"], _part_memo["bytes"]
    lista = cierres.particiones()
    total = 0
    for _f, p in lista:
        try:
            total += os.stat(p).st_size
        except OSError:
            pass
    with _lock:
        _part_memo.update(sig=sig, lista=lista, bytes=total)
    return lista, total


def archivos() -> Dict[str, Any]:
    """Metadata de todo lo descargable. Un stat por archivo + resúmenes ya
    cacheados por firma (writer / fx_hist / cierres)."""
    hist_dir = deltapaths.historico_dir()
    # `historico_dir()` da None sin variable Y con la variable puesta pero la
    # carpeta ausente en ESTA máquina (OneDrive sin sincronizar / sin sesión):
    # el aviso distingue los dos casos. A la pestaña va sólo el NOMBRE de la
    # carpeta (el HTML se cachea sin rol: nada de rutas absolutas de usuario).
    cfg = os.getenv("DELTA_HISTORICO_DIR") or os.getenv("DELTA_BASES_DIR") or ""
    out: Dict[str, Any] = {"hist_dir": hist_dir or "", "configurado": bool(hist_dir),
                           "carpeta": os.path.basename(os.path.normpath(hist_dir)) if hist_dir else "",
                           "cfg": bool(cfg)}
    if not hist_dir:
        return out
    xlsx = os.path.join(hist_dir, hw.HIST_FILENAME)
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    px = {"xlsx": _stat(xlsx), "parquet": _stat(pq), "espejo_fiel": False,
          "ruedas": 0, "filas": 0, "reales": 0, "desde": "—", "hasta": "—"}
    if px["parquet"]["existe"] and px["xlsx"]["existe"]:
        try:
            px["espejo_fiel"] = bool(espejo.espejo_valido(pq, xlsx))
        except Exception:  # noqa: BLE001
            px["espejo_fiel"] = False
    if px["xlsx"]["existe"] or px["parquet"]["existe"]:
        try:
            res = hw._resumen_base_cached(xlsx)
        except Exception as exc:  # noqa: BLE001 — una base ilegible no voltea la tarjeta
            logger.warning("[base] resumen de la base: %s", exc)
            res = {}
        if res:
            px.update(ruedas=len(res), filas=sum(n for n, _s in res.values()),
                      reales=sum(s for _n, s in res.values()),
                      desde=_dmy(min(res)), hasta=_dmy(max(res)))
    out["px"] = px

    fx_x = os.path.join(hist_dir, hw.FX_FILENAME)
    fx_p = os.path.splitext(fx_x)[0] + ".parquet"
    st_fx = fx_hist.status()
    out["fx"] = {"xlsx": _stat(fx_x), "parquet": _stat(fx_p),
                 "n": int(st_fx.get("n") or 0), "desde": _dmy(st_fx.get("dmin")), "hasta": _dmy(st_fx.get("dmax"))}

    lista, total = _particiones_memo()
    out["cierres"] = {"dir": cierres.dir_path() or "", "n": len(lista), "bytes": total,
                      "desde": _dmy(lista[0][0]) if lista else "—", "hasta": _dmy(lista[-1][0]) if lista else "—",
                      "mtime": _stat(lista[-1][1])["mtime"] if lista else None,    # la partición más nueva
                      "fechas": [f for f, _p in reversed(lista)]}                  # TODAS, las más nuevas primero
    out["hay_base"] = bool(px["xlsx"]["existe"] or px["parquet"]["existe"])
    out["acciones"] = _stat(os.path.join(hist_dir, hw.ACCIONES_FILENAME))
    return out


def archivo_descargable(que: str) -> Optional[Tuple[str, str, str]]:
    """(ruta, nombre para el navegador, media type) de una clave de `_ARCHIVOS`,
    sólo si el archivo existe. Clave desconocida / sin base → None."""
    ent = _ARCHIVOS.get(que or "")
    hist_dir = deltapaths.historico_dir()
    if not ent or not hist_dir:
        return None
    path = os.path.join(hist_dir, ent[1])
    if not os.path.isfile(path):
        return None
    return path, ent[1], ent[2]


def probar_lectura(path: str) -> None:
    """Abre y lee 1 byte ANTES de prometer el 200: FileResponse manda los
    headers y recién después abre / lee, así que un marcador de OneDrive sin
    bajar (ReadFile → EINVAL), un archivo en uso o uno borrado en el medio
    dejaban un 200 con el cuerpo cortado o un 500. El byte también dispara
    la bajada del marcador (la descarga lo necesita igual). Tira OSError."""
    with open(path, "rb") as f:
        f.read(1)


def particion_descargable(fecha: str) -> Optional[Tuple[str, str]]:
    """(ruta, nombre) de la partición de ESA fecha, buscada en la lista real de
    particiones (nunca se arma la ruta con el texto del usuario)."""
    f = (fecha or "").strip()
    if len(f) != 10:
        return None
    lista, _b = _particiones_memo()
    for fe, p in lista:
        if fe == f:
            return p, os.path.basename(p)
    return None


# ── Frame de la base ─────────────────────────────────────────────────────────
def _leer_frame(xlsx: str):
    """La base completa, de la fuente fiel: parquet si el espejo vale, si no el
    Excel (segundos). Sólo lectura (sin apartar nada, sin regenerar espejos)."""
    import pandas as pd
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    if os.path.isfile(pq) and (not os.path.isfile(xlsx) or espejo.espejo_valido(pq, xlsx)):
        df = pd.read_parquet(pq)
    elif os.path.isfile(xlsx):
        df = pd.read_excel(xlsx, sheet_name="Sheet1")
    else:
        return None
    df = espejo.normalizar_numericas(df, "base")
    cols = [c for c in COLUMNAS if c in df.columns]
    df = df[cols].copy()
    df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"], errors="coerce")
    df = df.dropna(subset=["fecha_hoy"])
    for c in _CAT:
        if c in df.columns:
            df[c] = df[c].astype("string").fillna("").astype("category")
    if "Price Date" in df.columns:
        df["Price Date"] = df["Price Date"].astype("string").fillna("")
    df = df.sort_values(["fecha_hoy", "Código"], kind="stable").reset_index(drop=True)
    return df


def frame():
    """El frame de la base, cacheado por las firmas (mtime + tamaño) del parquet
    y del Excel: una lectura por cambio de archivo (cada autosave)."""
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        return None
    xlsx = os.path.join(hist_dir, hw.HIST_FILENAME)
    key = hw._firmas_base(xlsx)
    if key == (None, None):
        return None
    with _lock:
        if _frame["key"] == key:
            return _frame["df"]
    with _load_lock:                            # los que esperan usan la lectura del primero
        with _lock:
            if _frame["key"] == key:
                return _frame["df"]
        try:
            df = _leer_frame(xlsx)
            err = None
        except Exception as exc:  # noqa: BLE001 — se informa en la pestaña, no se cae
            logger.warning("[base] no pude leer la base para la vista: %s", exc)
            # sin la ruta absoluta de la carpeta compartida (la pestaña la ve cualquier usuario)
            df, err = None, f"{type(exc).__name__}: {exc}".replace(hist_dir, "…")
        with _lock:
            _frame.update(key=key, df=df, error=err)
        return df


def frame_error() -> Optional[str]:
    with _lock:
        return _frame["error"]


def invalidar() -> None:
    with _lock:
        _frame.update(key=None, df=None, error=None)
        _part_memo.update(sig=None, lista=[], bytes=0)


def _filtrar(df, codigo: str, desde: Optional[str], hasta: Optional[str]):
    """Máscara sobre el frame: el código se resuelve contra las CATEGORÍAS
    (sin distinguir mayúsculas: el usuario tipea 'al30d', la base tiene
    'S31L6j' con la j minúscula del proyectado) y después `isin` sobre la
    columna categórica — ~1 ms; pasar 119k strings a mayúsculas costaba 15."""
    import pandas as pd
    m = None
    cod = (codigo or "").strip().upper()
    if cod:
        cats = [c for c in df["Código"].cat.categories if str(c).upper() == cod]
        m = df["Código"].isin(cats)
    if desde:
        mm = df["fecha_hoy"] >= pd.Timestamp(desde)
        m = mm if m is None else (m & mm)
    if hasta:
        mm = df["fecha_hoy"] <= pd.Timestamp(hasta)
        m = mm if m is None else (m & mm)
    return df if m is None else df[m]


def _fmt_fila(r: Dict[str, Any]) -> Dict[str, str]:
    from backend.locale_ar import fmt_num, fmt_pct, fmt_ts
    out: Dict[str, str] = {}
    for c in COLUMNAS:
        v = r.get(c)
        if c == "fecha_hoy":
            out[c] = _dmy(v)
        elif c in _PCT:
            out[c] = fmt_pct(v, 2)
        elif c in _NUM:
            out[c] = fmt_num(v, 2)
        elif c == "Price Date":
            out[c] = fmt_ts(v) if v not in (None, "") else "—"
        else:
            out[c] = "" if v is None else str(v)
    return out


def vista(codigo: str = "", desde: Optional[str] = None, hasta: Optional[str] = None,
          n: int = VISTA_DEFAULT) -> Dict[str, Any]:
    """Últimas `n` filas (más nuevas primero) de la base filtrada."""
    df = frame()
    if df is None:
        return {"ok": False, "error": frame_error() or "no hay base", "filas": [], "total": 0, "n": 0,
                "codigos": [], "columnas": list(COLUMNAS)}
    n = max(1, min(int(n or VISTA_DEFAULT), VISTA_MAX))
    sub = _filtrar(df, codigo, desde, hasta)
    total = int(len(sub))
    cola = sub.tail(n).iloc[::-1]
    filas = [_fmt_fila(r) for r in cola.to_dict("records")]
    codigos = sorted(str(c) for c in df["Código"].cat.categories) if "Código" in df.columns else []
    return {"ok": True, "error": None, "filas": filas, "total": total, "n": len(filas),
            "codigos": codigos, "columnas": [c for c in COLUMNAS if c in df.columns],
            "desde_base": _dmy(df["fecha_hoy"].iloc[0]) if len(df) else "—",
            "hasta_base": _dmy(df["fecha_hoy"].iloc[-1]) if len(df) else "—",
            "filas_base": int(len(df))}


# ── CSV ──────────────────────────────────────────────────────────────────────
def _csv_es_ar(cols: List[str], filas: List[List[Any]]) -> str:
    """`;` + coma decimal + BOM: Excel es-AR lo abre con un doble click."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(cols)
    for f in filas:
        w.writerow(f)
    return "﻿" + buf.getvalue()


# Punto decimal entre dígitos, salvo los segundos fraccionarios de un
# timestamp ISO ("16:59:00.123": el ":dd" de antes lo excluye).
_RE_DEC = __import__("re").compile(r"(?<=\d)(?<!:\d\d)\.(?=\d)")
# Filas por llamada C (to_csv + replace + encode): ~20 ms de GIL por tramo y
# el event loop lo recupera entre tramos (medido con la base entera: lag del
# loop p95 14 ms); de una sola vez eran 1,2 s de GIL seguidos.
CSV_CHUNK = 2_500
_BOM = "\ufeff".encode("utf-8")


def _to_csv_es_ar(df, chunk: int = CSV_CHUNK) -> bytes:
    """`DataFrame.to_csv` (C) por tramos: `;` + coma decimal + fechas
    DD/MM/AAAA + BOM, en BYTES UTF-8 (un str con emoji / acentos sería UCS-4).
    Un loop por celda tardaba 3,8 s para la base entera (119k filas)."""
    import pandas as pd
    df = df.copy()
    con_punto = False                      # ¿alguna columna de texto trae un punto?
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            # strftime sobre 119k filas = 0,5 s; sobre las ~250 fechas únicas
            # (categorías) = ms
            cat = s.astype("category")
            df[c] = cat.cat.rename_categories([d.strftime("%d/%m/%Y") for d in cat.cat.categories])
        elif isinstance(s.dtype, pd.CategoricalDtype):
            con_punto = con_punto or any("." in str(x) for x in s.cat.categories)
        elif s.dtype == object or pd.api.types.is_string_dtype(s):
            if len(s) and isinstance(s.iloc[0], (date, datetime)):
                df[c] = s.map(lambda v: v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else v)
            else:
                con_punto = con_punto or bool(s.astype("string").str.contains(".", regex=False).fillna(False).any())
    # `decimal=","` manda a pandas por el camino lento (2,8 s la base entera):
    # se escribe con punto por el camino C y se cambia el punto decimal
    # después — plano si ningún texto lleva punto (ms), si no sólo entre
    # dígitos. %.15g = 15 dígitos significativos (la precisión de Excel) y
    # nunca notación científica debajo de 1e15: con %.10g un volumen de
    # 912.000 M salía "9,12e+11" y un nominal grande perdía los centavos.
    partes = [_BOM]
    n = len(df)
    cabecera = True
    for i in range(0, max(n, 1), max(1, int(chunk))):
        texto = df.iloc[i:i + chunk].to_csv(sep=";", index=False, header=cabecera,
                                            lineterminator="\r\n", float_format="%.15g")
        cabecera = False
        texto = _RE_DEC.sub(",", texto) if con_punto else texto.replace(".", ",")
        partes.append(texto.encode("utf-8"))
    return b"".join(partes)


def csv_base(codigo: str = "", desde: Optional[str] = None, hasta: Optional[str] = None) -> Tuple[bytes, int]:
    """(csv en bytes UTF-8 con BOM, filas) de la base filtrada, más viejas
    primero, hasta CSV_MAX_FILAS."""
    df = frame()
    if df is None:
        return _csv_es_ar(list(COLUMNAS), []).encode("utf-8"), 0
    sub = _filtrar(df, codigo, desde, hasta).tail(CSV_MAX_FILAS)
    cols = [c for c in COLUMNAS if c in sub.columns]
    return _to_csv_es_ar(sub[cols]), int(len(sub))


def csv_cierre(path: str) -> Tuple[bytes, int]:
    """Una partición del cierre completo como CSV es-AR."""
    import pandas as pd
    df = pd.read_parquet(path)
    if "fecha_hoy" in df.columns:
        df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"], errors="coerce")
    return _to_csv_es_ar(df), int(len(df))


def nombre_csv(prefijo: str, codigo: str = "", desde: Optional[str] = None, hasta: Optional[str] = None) -> str:
    partes = [prefijo]
    if codigo:
        partes.append(codigo.strip().upper())
    if desde or hasta:
        partes.append(f"{(desde or '')}_{(hasta or '')}".strip("_"))
    return "_".join(p for p in partes if p) + ".csv"
