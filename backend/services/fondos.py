"""Fondos — performance de los fondos propios contra su benchmark (sólo superuser, 26/11).

Fuente: los `.txt` que el proceso de la mañana regenera en la biblioteca
compartida (`Delta Bases`, la misma carpeta del histórico de la app):

    Text/Esco/Delta_VCP.txt           cuotaparte y patrimonio por fondo CAFCI / clase / día
    Text/Esco/Delta_Fondos.txt        maestro: CodFondo (ESCO) ↔ CodCAFCI, nombre, tipo, moneda
    Text/Fondos/Delta_Benchmarks.txt  índice del benchmark por fondo y día
    Text/Fondos/Delta_Indices.txt     índices de mercado (A3500, CER, Badlar, Merval, CCL, …)
    Text/Fondos/Delta_SyR_Fondos.txt  suscripciones y rescates por fondo y día
    Fondos/Tabla_Benchmarks.xlsx      pesos del benchmark de cada fondo
    Fondos/Carteras_Diarias_Params.xlsx  hoja Clasif: grupo y CLASE EMBLEMA de cada fondo
    Fondos/Tabla_Fondos_Grupo Latin.xlsx hoja Clases_Grupo Latin: honorario de administración por clase

(`Csv/Delta_VCP.csv` / `Csv/Delta_Benchmarks.csv` quedan como respaldo: son el
formato viejo y terminan en 2023.) `FONDOS_BASES_DIR` pisa la carpeta.

Carga: NUNCA en un request. `asegurar()` dispara un thread (single-flight) que
lee los archivos (pyarrow, ~0,3 s los 55 MB) y arma matrices numpy fechas ×
clases; el request sólo lee memoria. Ya cargado, cada `_RECHEQUEO_S` se
comparan las firmas (mtime + tamaño) y, si el proceso de la mañana regeneró
algo, se recarga en el thread y los memos de las rutas se invalidan solos
(`version()`). Un archivo "sólo en la nube" de OneDrive deja el motivo y el
remedio en `estado()["error"]` y se reintenta.

Todo el cálculo es `fondos_calc` (numpy puro) sobre esas matrices: el tablero
de ~60 fondos × 9 períodos son microsegundos.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.services import deltapaths
from backend.services import fondos_calc as fc

logger = logging.getLogger("backend.fondos")

REPO_ROOT = Path(__file__).resolve().parents[2]

# clave → rutas candidatas relativas a "Delta Bases" (gana la primera que exista)
ARCHIVOS: Dict[str, Tuple[str, ...]] = {
    "vcp": ("Text/Esco/Delta_VCP.txt", "Csv/Delta_VCP.csv"),
    "fondos": ("Text/Esco/Delta_Fondos.txt", "Csv/Delta_Fondos.csv"),
    "bench": ("Text/Fondos/Delta_Benchmarks.txt", "Csv/Delta_Benchmarks.csv"),
    "indices": ("Text/Fondos/Delta_Indices.txt",),
    "syr": ("Text/Fondos/Delta_SyR_Fondos.txt",),
    "tabla_bm": ("Fondos/Tabla_Benchmarks.xlsx",),
    "params": ("Fondos/Carteras_Diarias_Params.xlsx",),
    "fees": ("Fondos/Tabla_Fondos_Grupo Latin.xlsx",),
}
_OBLIGATORIOS = ("vcp",)

_RECHEQUEO_S = 120.0          # cada cuánto se miran las firmas (stats) con la pestaña en uso
_REINTENTO_S = 20.0           # tras un error de carga
_VIEJO_DIAS = 6               # la cuotaparte "atrasada" se avisa a partir de acá
_SYR_ATRASO_DIAS = 5          # suscripciones / rescates: hasta cuántos días antes del fin de la ventana sirven

TIPOS = {"PF": "Money market", "RF": "Renta fija", "MI": "Renta mixta",
         "RV": "Renta variable", "RFI": "Renta fija internacional"}
_ORDEN_TIPO = {"PF": 0, "RF": 1, "MI": 2, "RV": 3, "RFI": 4}

# Fondos que la pestaña sigue de entrada (códigos CAFCI): Renta, Moneda,
# Galileo Argentina, Multimercado I, Ahorro Plus, Crecimiento, Gestión III,
# Gestión V, Renta Dólares y Retorno Real. Cada usuario lo cambia con la ★.
SEGUIDOS_DEFAULT: Tuple[int, ...] = (369, 408, 446, 466, 473, 572, 603, 670, 709, 792)

# Índices de `Delta_Indices.txt`: columna → (clave, etiqueta, tipo). "nivel" =
# precio / índice (rinde su variación diaria); "tasa" = % TNA (devenga /365).
INDICES_DEF: Tuple[Tuple[str, str, str, str], ...] = (
    ("A3500", "a3500", "Dólar A3500", "nivel"),
    ("CER", "cer", "CER", "nivel"),
    ("Badlar_Privada", "badlar", "Badlar privada", "tasa"),
    ("TAMAR", "tamar", "TAMAR", "tasa"),
    ("Merval", "merval", "S&P Merval", "nivel"),
    ("CCL_Delta", "ccl", "CCL", "nivel"),
    ("ETF S&P 500", "spy", "S&P 500 (ETF)", "nivel"),
    ("ETF iShares Latin America 40", "ilf", "Latam 40 (ETF)", "nivel"),
    ("Bovespa", "bovespa", "Bovespa", "nivel"),
    ("Caduceo", "caduceo", "Caduceo", "nivel"),
    ("Caja_Ahorro_USD", "cajausd", "Caja de ahorro USD", "tasa"),
    ("Badlar_USD", "badlarusd", "Badlar USD", "tasa"),
    ("Plazo_Fijo_60_USD", "depositosusd60d", "Plazo fijo USD 60d", "tasa"),
    ("USD_BRL", "usdbrl", "USD/BRL", "nivel"),
)
_IDX_POR_CLAVE = {c: (col, lbl, tipo) for col, c, lbl, tipo in INDICES_DEF}
# columna de Tabla_Benchmarks.xlsx → clave del índice
_TABLA_BM_COLS = {
    "benchmark_a3500": "a3500", "benchmark_cer": "cer", "benchmark_badlarprivada": "badlar",
    "benchmark_spmerval": "merval", "benchmark_ccl": "ccl", "benchmark_spy": "spy",
    "benchmark_ilf": "ilf", "benchmark_cajausd": "cajausd", "benchmark_badlarusd": "badlarusd",
    "benchmark_caduceo": "caduceo", "benchmark_bovespa": "bovespa",
    "benchmark_depositosusd60d": "depositosusd60d", "benchmark_tamar": "tamar",
}


# ── modelo en memoria ────────────────────────────────────────────────────────
@dataclass
class Clase:
    col: int
    cafci: int
    clase: str
    moneda: str


@dataclass
class Fondo:
    cafci: int
    cod: Optional[int]            # CodFondo de ESCO (Composición / PN / SyR)
    nombre: str
    corto: str
    tipo: str                     # PF / RF / MI / RV / RFI ("" si no se sabe)
    moneda: str                   # ARS / USD / USB
    familia: str                  # Delta / Galileo / Cohen
    grupo: str = ""               # grupo del reporte de carteras (CER, Dollar linked, Cash Management, …)
    cols: List[int] = field(default_factory=list)
    principal: int = -1           # columna de la clase emblema (o la de más patrimonio)
    ultimo: int = -1              # índice de la última rueda con cuotaparte


@dataclass
class Datos:
    fechas: np.ndarray                              # ruedas (datetime64[D])
    clases: List[Clase]
    vcp: np.ndarray                                 # [ruedas, clases]
    pn: np.ndarray                                  # patrimonio por clase
    fondos: Dict[int, Fondo]
    bench: Dict[int, np.ndarray]                    # índice del benchmark por fondo, alineado
    bench_nombre: Dict[int, str]
    indices: Dict[str, np.ndarray]                  # índices de referencia como NIVEL, alineados
    pesos_bm: Dict[int, Dict[str, float]]           # Tabla_Benchmarks: {clave: peso, "spread": x}
    fees: Dict[Tuple[int, str], float]              # (cafci, clase corta) → honorario de adm. anual (fracción)
    syr: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]   # cafci → (fechas, suscripciones, rescates)
    fuentes: List[Dict[str, Any]]
    avisos: List[str]
    version: int = 0
    cargado: float = 0.0

    def col(self, cafci: int, clase: Optional[str] = None) -> int:
        f = self.fondos.get(int(cafci))
        if f is None:
            return -1
        if clase:
            for c in f.cols:
                if self.clases[c].clase == clase:
                    return c
        return f.principal

    def pn_fondo(self, cafci: int) -> np.ndarray:
        """Patrimonio total del fondo (suma de clases) por rueda."""
        f = self.fondos[int(cafci)]
        m = self.pn[:, f.cols]
        s = np.nansum(m, axis=1)
        s[~np.isfinite(m).any(axis=1)] = np.nan
        return s


_lock = threading.Lock()
_estado: Dict[str, Any] = {"datos": None, "firma": None, "error": None, "cargando": False,
                           "chequeo": 0.0, "version": 0}


# ── rutas y firmas ───────────────────────────────────────────────────────────
def base_dir() -> Optional[str]:
    """Carpeta 'Delta Bases' (la del histórico de la app) o `FONDOS_BASES_DIR`."""
    env = os.getenv("FONDOS_BASES_DIR")
    if env:
        d = deltapaths.expand(env, want="dir")
        return d if d and os.path.isdir(d) else None
    return deltapaths.historico_dir()


def rutas() -> Dict[str, Optional[str]]:
    base = base_dir()
    out: Dict[str, Optional[str]] = {}
    for clave, candidatos in ARCHIVOS.items():
        out[clave] = None
        if not base:
            continue
        for rel in candidatos:
            p = os.path.join(base, *rel.split("/"))
            if os.path.isfile(p):
                out[clave] = p
                break
    return out


def _firma(rs: Dict[str, Optional[str]]) -> Tuple:
    sig = []
    for clave in sorted(rs):
        p = rs[clave]
        if not p:
            sig.append((clave, None, 0, 0))
            continue
        try:
            st = os.stat(p)
            sig.append((clave, p, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((clave, p, 0, 0))
    return tuple(sig)


# ── lectura ──────────────────────────────────────────────────────────────────
def _sep_de(path: str) -> str:
    with open(path, "rb") as fh:
        cab = fh.readline(4096)
    return ";" if cab.count(b";") > cab.count(b",") else ","


def _leer_csv(path: str, usecols: Optional[Sequence[str]] = None):
    """CSV → DataFrame (pyarrow si está; utf-8 y, si no, latin-1). El
    separador se detecta de la cabecera (los .txt nuevos usan `;` o `,`)."""
    import pandas as pd
    sep = _sep_de(path)
    cols = None
    if usecols is not None:
        cab = pd.read_csv(path, sep=sep, nrows=0, encoding_errors="replace").columns
        cols = [c for c in usecols if c in cab]
    ultimo: Optional[Exception] = None
    for kw in ({"engine": "pyarrow"}, {}, {"encoding": "latin-1"}):
        try:
            return pd.read_csv(path, sep=sep, usecols=cols, **kw)
        except (UnicodeDecodeError, ImportError, ValueError) as exc:   # pyarrow ausente / encoding
            ultimo = exc
        except Exception as exc:  # noqa: BLE001 — pyarrow.lib.ArrowInvalid y parecidos
            if kw.get("engine") != "pyarrow":
                raise
            ultimo = exc
    raise ultimo  # type: ignore[misc]


def _txt(v: Any) -> str:
    s = "" if v is None else str(v)
    return "" if s.lower() in ("nan", "none", "<na>") else s.strip()


def _moneda(v: str) -> str:
    s = _txt(v).upper()
    if s in ("ARS", "USD", "USB"):
        return s
    if "BILLETE" in s or s == "USB":
        return "USB"
    if s.startswith("DOL") or s.startswith("DÓL") or s == "U$S":
        return "USD"
    return "ARS"


def _familia(nombre: str) -> str:
    n = nombre.upper()
    if n.startswith("GALILEO") or n.startswith("SF VALUE"):
        return "Galileo"
    if n.startswith("COHEN"):
        return "Cohen"
    return "Delta"


def _fechas_iso(col) -> np.ndarray:
    """Columna de fechas ISO (texto o fecha) → datetime64[D], factorizando
    primero (cientos de miles de filas, pocos miles de fechas distintas)."""
    import pandas as pd
    codes, uni = pd.factorize(col)
    try:
        u = np.array([str(x)[:10] for x in uni], dtype=fc.D)
    except ValueError:
        u = pd.to_datetime(pd.Series(uni), errors="coerce").to_numpy().astype(fc.D)
    return u[codes]


def _ffill_tramo(m: np.ndarray) -> None:
    """Rellena hacia adelante los NaN INTERIORES de cada columna (una rueda
    sin fila en el archivo), sin estirar antes del primer dato ni después del
    último (una clase que se cerró no sigue cotizando). In-place."""
    n = m.shape[0]
    if n < 2:
        return
    ok = np.isfinite(m)
    idx = np.where(ok, np.arange(n)[:, None], 0)
    np.maximum.accumulate(idx, axis=0, out=idx)
    lleno = np.take_along_axis(m, idx, axis=0)
    hay_antes = np.maximum.accumulate(ok, axis=0)
    hay_despues = np.maximum.accumulate(ok[::-1], axis=0)[::-1]
    interior = hay_antes & hay_despues & ~ok
    m[interior] = lleno[interior]


def _leer_vcp(path: str) -> Dict[str, Any]:
    df = _leer_csv(path, ["CodigoFondo", "Fondo", "NombreCortoFondo", "Moneda", "Fecha",
                          "ValorCuotaparte", "PatrimonioNeto", "Clase"])
    falta = {"CodigoFondo", "Fecha", "ValorCuotaparte", "Clase"} - set(df.columns)
    if falta:
        raise ValueError(f"{os.path.basename(path)}: faltan columnas {sorted(falta)}")
    df = df[df["CodigoFondo"].notna() & df["Fecha"].notna()]
    f = _fechas_iso(df["Fecha"])
    fechas, fi = np.unique(f, return_inverse=True)
    clase = df["Clase"].astype(str).str.strip()
    grp = df.assign(_c=clase.values).groupby(["CodigoFondo", "_c"], sort=False)
    ci = grp.ngroup().to_numpy()
    prim = grp.head(1)
    nc = int(ci.max()) + 1 if len(ci) else 0
    vcp = np.full((len(fechas), nc), np.nan)
    pn = np.full((len(fechas), nc), np.nan)
    v = df["ValorCuotaparte"].to_numpy(dtype=float)
    vcp[fi, ci] = np.where(v > 0, v, np.nan)
    if "PatrimonioNeto" in df.columns:
        pn[fi, ci] = df["PatrimonioNeto"].to_numpy(dtype=float)
    _ffill_tramo(vcp)
    _ffill_tramo(pn)
    # Ruedas = días en que ALGUNA clase movió la cuotaparte (el archivo viejo
    # venía con calendario corrido: sábados y feriados repiten el valor).
    if len(fechas) > 1:
        a, b = vcp[:-1], vcp[1:]
        mov = (np.isfinite(a) & np.isfinite(b) & (a != b)).any(axis=1)
        nace = (~np.isfinite(a) & np.isfinite(b)).any(axis=1)      # primer día de una clase
        keep = np.concatenate([[True], mov | nace])
        fechas, vcp, pn = fechas[keep], vcp[keep], pn[keep]
    clases, nombres = [], {}
    for _, r in prim.iterrows():
        c = int(r["CodigoFondo"])
        clases.append((c, _txt(r["_c"]), _moneda(r.get("Moneda", ""))))
        nombres.setdefault(c, (_txt(r.get("Fondo", "")), _txt(r.get("NombreCortoFondo", ""))))
    return {"fechas": fechas, "vcp": vcp, "pn": pn, "clases": clases, "nombres": nombres,
            "filas": int(len(df))}


def _leer_maestro(path: Optional[str]) -> Dict[int, Dict[str, Any]]:
    """Delta_Fondos → {cafci: {cod, nombre, corto, tipo, moneda}} (formato
    nuevo de ESCO o el viejo de Csv/)."""
    if not path:
        return {}
    df = _leer_csv(path)
    out: Dict[int, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        try:
            cafci = int(float(r.get("CodCAFCI")))
        except (TypeError, ValueError):
            continue
        cod = r.get("CodFondo")
        tipo = _txt(r.get("CodTpFondo", "")) or _txt(r.get("CodInterfaz", ""))
        tipo = {"CM": "PF", "RM": "MI"}.get(tipo.upper(), tipo.upper())
        out[cafci] = {
            "cod": int(float(cod)) if cod is not None and str(cod).strip() not in ("", "nan") else None,
            "nombre": _txt(r.get("Nombre", "")), "corto": _txt(r.get("NombreCorto", "")),
            "tipo": tipo, "moneda": _txt(r.get("Moneda", "")).upper(),
        }
    return out


def _nombre_limpio(nombre: str, corto: str, respaldo: str) -> str:
    """El maestro trae algún nombre sucio ("hoy "): si es muy corto, gana el
    de la serie o el nombre corto."""
    for cand in (nombre, respaldo, corto):
        c = " ".join(cand.split())
        if len(c) >= 6:
            return c
    return " ".join((nombre or corto or respaldo).split()) or "?"


def _leer_bench(path: Optional[str], fechas: np.ndarray) -> Tuple[Dict[int, np.ndarray], Dict[int, str], int]:
    """Delta_Benchmarks → ({cafci: índice alineado a `fechas`}, {cafci: nombre}, filas).
    Un fondo "Sin Benchmark" (índice plano) no entra."""
    if not path:
        return {}, {}, 0
    df = _leer_csv(path, ["fund_code", "Date", "Category", "benchmark_name", "benchmark_value"])
    if not {"fund_code", "Date", "benchmark_value"} <= set(df.columns):
        raise ValueError(f"{os.path.basename(path)}: cabecera inesperada {list(df.columns)}")
    df = df[df["fund_code"].notna() & df["benchmark_value"].notna()]
    f = _fechas_iso(df["Date"])
    cod = df["fund_code"].to_numpy().astype(np.int64)
    val = df["benchmark_value"].to_numpy(dtype=float)
    nom = df["benchmark_name"].astype(str).to_numpy() if "benchmark_name" in df.columns else None
    orden = np.lexsort((f, cod))
    cod, f, val = cod[orden], f[orden], val[orden]
    if nom is not None:
        nom = nom[orden]
    cortes = np.flatnonzero(np.diff(cod)) + 1
    ini = np.concatenate([[0], cortes])
    fin = np.concatenate([cortes, [len(cod)]])
    series: Dict[int, np.ndarray] = {}
    nombres: Dict[int, str] = {}
    for a, b in zip(ini, fin):
        c = int(cod[a])
        ff, vv = f[a:b], val[a:b]
        nombre = _txt(nom[b - 1]) if nom is not None else ""
        # una fecha repetida (dos nombres de benchmark el mismo día): la última
        if len(ff) > 1:
            unico = np.concatenate([ff[1:] != ff[:-1], [True]])
            ff, vv = ff[unico], vv[unico]
        if "sin benchmark" in nombre.lower() or len(vv) < 2 or float(np.nanmax(vv) - np.nanmin(vv)) < 1e-12:
            continue
        series[c] = fc._a_calendario(ff, vv, fechas)
        nombres[c] = nombre
    return series, nombres, int(len(df))


def _clave_col(s: str) -> str:
    """Nombre de columna normalizado para comparar (sin acentos, espacios ni
    signos; un `&amp;` que dejó algún exportador vale como `&`)."""
    s = unicodedata.normalize("NFKD", str(s).replace("&amp;", "&")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _leer_indices(path: Optional[str], fechas: np.ndarray) -> Dict[str, np.ndarray]:
    """Delta_Indices (matriz ancha year;month;day;…) → {clave: NIVEL alineado}.
    Las tasas (% TNA) se llevan a un índice que devenga TNA / 365 por día
    calendario, igual que el benchmark, así todas se comparan como niveles."""
    if not path or not len(fechas):
        return {}
    df = _leer_csv(path)
    cols = {_clave_col(c): c for c in df.columns}
    if not {"year", "month", "day"} <= set(cols):
        logger.warning("[fondos] %s sin columnas year/month/day: no se usan los índices", os.path.basename(path))
        return {}
    y = df[cols["year"]].to_numpy(dtype=float)
    m = df[cols["month"]].to_numpy(dtype=float)
    d = df[cols["day"]].to_numpy(dtype=float)
    ok = np.isfinite(y) & np.isfinite(m) & np.isfinite(d)
    f = np.array([f"{int(a):04d}-{int(b):02d}-{int(c):02d}" for a, b, c in zip(y[ok], m[ok], d[ok])], dtype=fc.D)
    orden = np.argsort(f, kind="stable")
    f = f[orden]
    out: Dict[str, np.ndarray] = {}
    cal = np.arange(fechas[0], fechas[-1] + np.timedelta64(1, "D"))
    pos = np.searchsorted(cal, fechas)
    for col, clave, _lbl, tipo in INDICES_DEF:
        real = cols.get(_clave_col(col))
        if real is None:
            continue
        v = df[real].to_numpy(dtype=float)[ok][orden]
        fin = np.isfinite(v)
        if fin.sum() < 2:
            continue
        ff, vv = f[fin], v[fin]
        if tipo == "tasa":
            var = fc.benchmark_var_calendario(cal, {}, {clave: (ff, vv, 1.0)})
            nivel = fc.indice_desde_var(var)[pos]
        else:
            nivel = fc._a_calendario(ff, vv, fechas)
        if np.isfinite(nivel).sum() >= 2:
            out[clave] = nivel
    return out


def _num_ar(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if np.isfinite(v) else 0.0
    s = str(v).strip().replace("%", "")
    if not s:
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _leer_tabla_bm(path: Optional[str]) -> Dict[int, Dict[str, float]]:
    """Tabla_Benchmarks.xlsx → {cafci: {clave de índice: peso, "spread": anual}}
    sólo con los pesos distintos de cero. Best-effort: sin archivo, {}."""
    if not path:
        return {}
    import pandas as pd
    try:
        df = pd.read_excel(path, sheet_name=0)
    except Exception as exc:  # noqa: BLE001 — la tabla es un extra: sin ella no hay "benchmark propio"
        logger.warning("[fondos] no pude leer %s (%s)", os.path.basename(path), exc)
        return {}
    cols = {_clave_col(c): c for c in df.columns}
    if "fundcode" not in cols:
        return {}
    out: Dict[int, Dict[str, float]] = {}
    for _, r in df.iterrows():
        try:
            c = int(float(r[cols["fundcode"]]))
        except (TypeError, ValueError):
            continue
        pesos: Dict[str, float] = {}
        for col_tabla, clave in _TABLA_BM_COLS.items():
            real = cols.get(_clave_col(col_tabla))
            if real is not None:
                w = _num_ar(r[real])
                if abs(w) > 1e-12:
                    pesos[clave] = w
        sp = cols.get("benchmarkspread")
        if sp is not None and abs(_num_ar(r[sp])) > 1e-12:
            pesos["spread"] = _num_ar(r[sp])
        if pesos:
            out[c] = pesos
    return out


def clase_corta(c: str) -> str:
    """'Clase K Ley N° 27.743' → 'K'; 'B' → 'B' (las tablas de la casa y los
    archivos de ESCO nombran distinto a las clases de la ley 27.743)."""
    t = " ".join(str(c or "").split())
    if t.lower().startswith("clase ") and len(t.split()) > 1:
        return t.split()[1].upper()
    return t.upper()


def _leer_params(path: Optional[str]) -> Dict[int, Dict[str, str]]:
    """Carteras_Diarias_Params.xlsx (hoja Clasif) → {cafci: {grupo, emblema}}."""
    if not path:
        return {}
    import pandas as pd
    try:
        df = pd.read_excel(path, sheet_name="Clasif")
    except Exception as exc:  # noqa: BLE001 — extra: sin él, la clase principal es la de más patrimonio
        logger.warning("[fondos] no pude leer %s (%s)", os.path.basename(path), exc)
        return {}
    cols = {_clave_col(c): c for c in df.columns}
    if "fundcode" not in cols:
        return {}
    out: Dict[int, Dict[str, str]] = {}
    for _, r in df.iterrows():
        try:
            c = int(float(r[cols["fundcode"]]))
        except (TypeError, ValueError):
            continue
        out[c] = {"grupo": _txt(r[cols["sheetname"]]) if "sheetname" in cols else "",
                  "emblema": clase_corta(_txt(r[cols["claseemblema"]])) if "claseemblema" in cols else ""}
    return out


def _leer_fees(path: Optional[str]) -> Dict[Tuple[int, str], float]:
    """Tabla_Fondos_Grupo Latin.xlsx (hoja Clases_Grupo Latin) → {(cafci,
    clase corta): honorario de administración anual como fracción}."""
    if not path:
        return {}
    import pandas as pd
    try:
        df = pd.read_excel(path, sheet_name="Clases_Grupo Latin")
    except Exception as exc:  # noqa: BLE001 — extra: sin él no hay retorno bruto
        logger.warning("[fondos] no pude leer %s (%s)", os.path.basename(path), exc)
        return {}
    cols = {_clave_col(c): c for c in df.columns}
    need = ("codigofondocafci", "clase", "managementfee")
    if not all(k in cols for k in need):
        return {}
    out: Dict[Tuple[int, str], float] = {}
    for _, r in df.iterrows():
        try:
            c = int(float(r[cols["codigofondocafci"]]))
        except (TypeError, ValueError):
            continue
        fee = _num_ar(r[cols["managementfee"]])
        k = clase_corta(_txt(r[cols["clase"]]))
        if k and 0.0 < fee < 25.0:
            out[(c, k)] = fee / 100.0
    return out


def _leer_syr(path: Optional[str], cod_a_cafci: Dict[int, int]) -> Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Delta_SyR_Fondos (CodFondo de ESCO, S / R, fecha, importe) →
    {cafci: (fechas, suscripciones, rescates)} con los importes en positivo."""
    if not path:
        return {}
    df = _leer_csv(path)
    cols = {_clave_col(c): c for c in df.columns}
    need = ("codfondo", "solicitudtipo", "fechaconcertacion", "importe")
    if not all(k in cols for k in need):
        logger.warning("[fondos] %s con cabecera inesperada: sin flujos", os.path.basename(path))
        return {}
    df = df[df[cols["codfondo"]].notna() & df[cols["importe"]].notna()]
    cod = df[cols["codfondo"]].to_numpy().astype(np.int64)
    f = _fechas_iso(df[cols["fechaconcertacion"]])
    tipo = df[cols["solicitudtipo"]].astype(str).str.strip().str.upper().to_numpy()
    imp = np.abs(df[cols["importe"]].to_numpy(dtype=float))
    out: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for c in np.unique(cod):
        cafci = cod_a_cafci.get(int(c))
        if cafci is None:
            continue
        sel = cod == c
        ff, tt, ii = f[sel], tipo[sel], imp[sel]
        dias, inv = np.unique(ff, return_inverse=True)
        s = np.zeros(len(dias))
        r = np.zeros(len(dias))
        np.add.at(s, inv[tt == "S"], ii[tt == "S"])
        np.add.at(r, inv[tt == "R"], ii[tt == "R"])
        out[cafci] = (dias, s, r)
    return out


def _construir(rs: Dict[str, Optional[str]]) -> Datos:
    if not rs.get("vcp"):
        base = base_dir()
        raise FileNotFoundError(
            "No encuentro Delta_VCP.txt" + (f" en {os.path.join(base, 'Text', 'Esco')}" if base else
                                             ": falta configurar la carpeta Delta Bases (DELTA_BASES_DIR / "
                                             "DELTA_HISTORICO_DIR en secrets.txt)"))
    t0 = time.perf_counter()
    crudo = _leer_vcp(rs["vcp"])
    fechas, vcp, pn = crudo["fechas"], crudo["vcp"], crudo["pn"]
    avisos: List[str] = []
    fuentes: List[Dict[str, Any]] = [{"clave": "vcp", "archivo": os.path.basename(rs["vcp"]),
                                      "filas": crudo["filas"], "hasta": str(fechas[-1]) if len(fechas) else None}]

    def _extra(clave: str, fn, *args):
        """Los archivos que no son la cuotaparte son un extra: si alguno
        falla, la pestaña carga igual y lo avisa."""
        p = rs.get(clave)
        if not p:
            fuentes.append({"clave": clave, "archivo": None, "filas": 0, "hasta": None})
            return None
        try:
            return fn(p, *args)
        except Exception as exc:  # noqa: BLE001
            from backend.services import nube
            motivo = nube.remedio(p) if nube.ilegible_por_nube(p, exc) else f"{type(exc).__name__}: {exc}"
            avisos.append(f"{os.path.basename(p)}: {motivo}")
            logger.warning("[fondos] %s no se pudo leer (%s)", os.path.basename(p), motivo)
            fuentes.append({"clave": clave, "archivo": os.path.basename(p), "filas": 0, "hasta": None, "error": motivo})
            return None

    maestro = _extra("fondos", _leer_maestro) or {}
    if rs.get("fondos") and maestro:
        fuentes.append({"clave": "fondos", "archivo": os.path.basename(rs["fondos"]), "filas": len(maestro), "hasta": None})

    params = _extra("params", _leer_params) or {}
    if rs.get("params") and params:
        fuentes.append({"clave": "params", "archivo": os.path.basename(rs["params"]), "filas": len(params), "hasta": None})
    fees = _extra("fees", _leer_fees) or {}
    if rs.get("fees") and fees:
        fuentes.append({"clave": "fees", "archivo": os.path.basename(rs["fees"]), "filas": len(fees), "hasta": None})

    clases: List[Clase] = []
    fondos: Dict[int, Fondo] = {}
    for col, (cafci, clase, mon) in enumerate(crudo["clases"]):
        clases.append(Clase(col=col, cafci=cafci, clase=clase, moneda=mon))
        f = fondos.get(cafci)
        if f is None:
            m = maestro.get(cafci, {})
            largo, corto = crudo["nombres"].get(cafci, ("", ""))
            nombre = _nombre_limpio(m.get("nombre", ""), m.get("corto", "") or corto, largo)
            f = fondos[cafci] = Fondo(
                cafci=cafci, cod=m.get("cod"), nombre=nombre, corto=(m.get("corto") or corto or nombre),
                tipo=m.get("tipo", ""), moneda=(m.get("moneda") or mon), familia=_familia(nombre),
                grupo=params.get(cafci, {}).get("grupo", ""))
        f.cols.append(col)
    for f in fondos.values():
        cols = np.array(f.cols)
        ult = [fc.ultimo_valido(vcp[:, c]) for c in f.cols]
        f.ultimo = max(ult) if ult else -1
        if f.ultimo < 0:
            continue
        # clase principal: la EMBLEMA de la casa si cotiza y tiene patrimonio;
        # si no, la de mayor patrimonio en la última rueda del fondo.
        vivas = [c for c, u in zip(f.cols, ult) if u == f.ultimo]
        pns = [pn[f.ultimo, c] if np.isfinite(pn[f.ultimo, c]) else -1.0 for c in vivas]
        f.principal = vivas[int(np.argmax(pns))] if vivas else int(cols[0])
        emblema = params.get(f.cafci, {}).get("emblema")
        if emblema:
            for c, p_ in zip(vivas, pns):
                if clase_corta(clases[c].clase) == emblema and p_ > 0:
                    f.principal = c
                    break
    fondos = {c: f for c, f in fondos.items() if f.ultimo >= 0}

    r = _extra("bench", _leer_bench, fechas)
    bench, bench_nombre, n_b = r if r else ({}, {}, 0)
    if rs.get("bench") and r:
        ult_b = max((fc.ultimo_valido(s) for s in bench.values()), default=-1)
        fuentes.append({"clave": "bench", "archivo": os.path.basename(rs["bench"]), "filas": n_b,
                        "hasta": str(fechas[ult_b]) if ult_b >= 0 else None})
    indices = _extra("indices", _leer_indices, fechas) or {}
    if rs.get("indices") and indices:
        ult_i = max(fc.ultimo_valido(s) for s in indices.values())
        fuentes.append({"clave": "indices", "archivo": os.path.basename(rs["indices"]), "filas": len(indices),
                        "hasta": str(fechas[ult_i]) if ult_i >= 0 else None})
    pesos = _extra("tabla_bm", _leer_tabla_bm) or {}
    if rs.get("tabla_bm") and pesos:
        fuentes.append({"clave": "tabla_bm", "archivo": os.path.basename(rs["tabla_bm"]), "filas": len(pesos), "hasta": None})
    cod_a_cafci = {f.cod: c for c, f in fondos.items() if f.cod is not None}
    syr = _extra("syr", _leer_syr, cod_a_cafci) or {}
    if rs.get("syr") and syr:
        ult_s = max((str(v[0][-1]) for v in syr.values() if len(v[0])), default=None)
        fuentes.append({"clave": "syr", "archivo": os.path.basename(rs["syr"]),
                        "filas": int(sum(len(v[0]) for v in syr.values())), "hasta": ult_s})

    d = Datos(fechas=fechas, clases=clases, vcp=vcp, pn=pn, fondos=fondos, bench=bench,
              bench_nombre=bench_nombre, indices=indices, pesos_bm=pesos, fees=fees, syr=syr,
              fuentes=fuentes, avisos=avisos, cargado=time.time())
    logger.info("[fondos] cargado en %.2f s: %d fondos · %d clases · %d ruedas (%s → %s) · %d benchmarks · %d índices",
                time.perf_counter() - t0, len(fondos), len(clases), len(fechas),
                fechas[0] if len(fechas) else "—", fechas[-1] if len(fechas) else "—", len(bench), len(indices))
    return d


# ── carga en segundo plano ───────────────────────────────────────────────────
def _tarea() -> None:
    try:
        rs = rutas()
        firma = _firma(rs)
        with _lock:
            d0 = _estado["datos"]
            # misma firma y todo leído: nada que hacer. Con un extra que no se
            # pudo leer (marcador de OneDrive: bajarlo NO cambia mtime ni
            # tamaño) se vuelve a intentar en cada re-chequeo.
            if d0 is not None and firma == _estado["firma"] and not d0.avisos:
                return
        try:
            d = _construir(rs)
        except Exception as exc:  # noqa: BLE001 — queda el motivo para la pestaña
            from backend.services import nube
            p = rs.get("vcp")
            motivo = (nube.remedio(p) if p and nube.ilegible_por_nube(p, exc)
                      else (str(exc) if isinstance(exc, (FileNotFoundError, ValueError)) else f"{type(exc).__name__}: {exc}"))
            logger.warning("[fondos] carga falló: %s", motivo, exc_info=not isinstance(exc, FileNotFoundError))
            with _lock:
                _estado["error"] = motivo
                _estado["chequeo"] = time.monotonic() - _RECHEQUEO_S + _REINTENTO_S
            return
        with _lock:
            _estado["version"] += 1
            d.version = _estado["version"]
            _estado["datos"] = d
            _estado["firma"] = firma
            _estado["error"] = None
    finally:
        with _lock:
            _estado["cargando"] = False


def asegurar() -> Optional[Datos]:
    """Los datos en memoria (None mientras se cargan por primera vez). Nunca
    lee disco acá: dispara la carga / el re-chequeo de firmas en un thread."""
    ahora = time.monotonic()
    with _lock:
        d = _estado["datos"]
        if _estado["cargando"] or ahora - _estado["chequeo"] < _RECHEQUEO_S:
            return d
        _estado["cargando"] = True
        _estado["chequeo"] = ahora
    threading.Thread(target=_tarea, name="fondos-carga", daemon=True).start()
    return d


def precargar() -> None:
    """Dispara la carga en segundo plano si todavía no se hizo (la llama Inicio
    cuando entra un superuser: la pestaña abre con los datos ya en memoria).
    `FONDOS_PRECARGA=0` la apaga. Con los datos cargados no hace nada: el
    re-chequeo de firmas queda para cuando la pestaña está en uso."""
    if (os.getenv("FONDOS_PRECARGA") or "1") == "0":
        return
    with _lock:
        if _estado["datos"] is not None or _estado["cargando"] or _estado["error"]:
            return
    asegurar()


def cargar_ahora() -> Optional[Datos]:
    """Carga síncrona (tests, herramientas y el botón Releer vía executor)."""
    with _lock:
        _estado["cargando"] = True
        _estado["chequeo"] = time.monotonic()
        _estado["firma"] = None
    _tarea()
    return _estado["datos"]


def reset() -> None:
    with _lock:
        _estado.update({"datos": None, "firma": None, "error": None, "cargando": False, "chequeo": 0.0})


def version() -> int:
    return int(_estado["version"])


def estado() -> Dict[str, Any]:
    with _lock:
        d: Optional[Datos] = _estado["datos"]
        out: Dict[str, Any] = {"cargado": d is not None, "cargando": bool(_estado["cargando"]),
                               "error": _estado["error"], "version": _estado["version"]}
    if d is not None:
        hasta = d.fechas[-1] if len(d.fechas) else None
        out.update({"fondos": len(d.fondos), "clases": len(d.clases), "ruedas": len(d.fechas),
                    "desde": str(d.fechas[0]) if len(d.fechas) else None,
                    "hasta": str(hasta) if hasta is not None else None,
                    "fuentes": d.fuentes, "avisos": d.avisos, "cargado_ts": d.cargado,
                    "atraso_dias": (int((np.datetime64("today", "D") - hasta).astype(int)) if hasta is not None else None)})
    return out


# ── preferencias por usuario (fondos seguidos, clase y comparación elegidas) ──
_PREFS_DEFAULT = REPO_ROOT / "data" / "fondos_prefs.json"
_prefs_lock = threading.Lock()
_prefs_memo: Dict[str, Any] = {"sig": None, "data": None}


def _prefs_path() -> Path:
    return Path(os.getenv("FONDOS_PREFS_PATH") or _PREFS_DEFAULT)


def _prefs_all(strict: bool = False) -> Dict[str, Any]:
    p = _prefs_path()
    try:
        st = p.stat()
    except OSError:
        return {"v": 1, "users": {}}
    sig = (str(p), st.st_mtime_ns, st.st_size)
    if _prefs_memo["sig"] == sig and _prefs_memo["data"] is not None:
        return _prefs_memo["data"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        users = data.get("users") if isinstance(data, dict) else None
        data = {"v": 1, "users": users if isinstance(users, dict) else {}}
    except (OSError, ValueError) as exc:
        if strict:
            raise OSError(f"fondos_prefs ilegible: {exc}") from exc
        logger.warning("[fondos] prefs ilegibles (%s): se usa la lista por defecto", exc)
        return {"v": 1, "users": {}}
    _prefs_memo.update({"sig": sig, "data": data})
    return data


def seguidos(user: str) -> List[int]:
    """Códigos CAFCI que sigue el usuario (la lista por defecto hasta que toque una ★)."""
    ent = _prefs_all()["users"].get(str(user)[:64])
    lst = ent.get("seguidos") if isinstance(ent, dict) else None
    if not isinstance(lst, list):
        return list(SEGUIDOS_DEFAULT)
    out = []
    for x in lst:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def seguir(user: str, cafci: int, on: Optional[bool] = None) -> List[int]:
    """Agrega / quita un fondo de los seguidos (on=None alterna). Escritura
    atómica; un archivo ilegible NO se pisa (OSError)."""
    user = str(user)[:64]
    cafci = int(cafci)
    with _prefs_lock:
        todo = _prefs_all(strict=True)
        actual = seguidos(user)
        esta = cafci in actual
        quiero = (not esta) if on is None else bool(on)
        if quiero and not esta:
            actual.append(cafci)
        elif not quiero and esta:
            actual = [c for c in actual if c != cafci]
        nuevo = {"v": 1, "users": dict(todo["users"])}
        ent = dict(nuevo["users"].get(user) or {})
        ent["seguidos"] = actual
        nuevo["users"][user] = ent
        p = _prefs_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(nuevo, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        _prefs_memo.update({"sig": None, "data": None})
        return actual


# ── consultas ────────────────────────────────────────────────────────────────
def referencias(d: Datos) -> List[Tuple[str, str]]:
    """[(clave, etiqueta)] de los índices contra los que se puede comparar."""
    return [(c, lbl) for _col, c, lbl, _t in INDICES_DEF if c in d.indices]


def serie_referencia(d: Datos, cafci: int, vs: str = "bm") -> Tuple[Optional[np.ndarray], str]:
    """(índice alineado, etiqueta) contra el que se compara el fondo:
    `bm` = su benchmark oficial; una clave de `referencias`; `f:<cafci>[:<clase>]`
    = otro fondo. (None, motivo) si no hay."""
    vs = (vs or "bm").strip()
    if vs == "bm":
        s = d.bench.get(int(cafci))
        if s is None:
            return None, "Sin benchmark"
        return s, d.bench_nombre.get(int(cafci)) or "Benchmark"
    if vs.startswith("f:"):
        partes = vs.split(":")
        try:
            otro = int(partes[1])
        except (IndexError, ValueError):
            return None, "Fondo inválido"
        c = d.col(otro, partes[2] if len(partes) > 2 and partes[2] else None)
        if c < 0:
            return None, "Fondo sin datos"
        return d.vcp[:, c], f"{d.fondos[otro].corto} {d.clases[c].clase}"
    if vs in d.indices:
        return d.indices[vs], _IDX_POR_CLAVE[vs][1]
    return None, "Sin benchmark"


def rango_indices(d: Datos, i_fin: int, rango: str = "ytd", desde: Optional[str] = None,
                  hasta: Optional[str] = None) -> Tuple[int, int]:
    """(i0, i1) de la ventana: `desde` / `hasta` ISO mandan; si no, `rango` es
    un período de `fondos_calc` o `max`. i0 es la rueda BASE (retorno 0)."""
    i1 = i_fin
    if hasta:
        try:
            i1 = min(i_fin, fc.idx_hasta(d.fechas, hasta))
        except ValueError:
            pass
    if i1 < 0:
        return -1, -1
    if desde:
        try:
            i0 = fc.idx_hasta(d.fechas, np.datetime64(desde, "D") - np.timedelta64(1, "D"))
            return max(i0, 0), i1
        except ValueError:
            pass
    if rango == "max":
        return 0, i1
    try:
        i0 = fc.corte_periodo(d.fechas, i1, rango)
    except ValueError:
        i0 = fc.corte_periodo(d.fechas, i1, "ytd")
    return max(i0, 0), i1


def fila_tablero(d: Datos, f: Fondo, vs: str = "bm", clase: Optional[str] = None) -> Dict[str, Any]:
    """Una fila del tablero: retornos por período del fondo (clase principal o
    la pedida), de su referencia y el exceso (fondo − referencia, en puntos)."""
    col = d.col(f.cafci, clase)
    y = d.vcp[:, col]
    i = fc.ultimo_valido(y)
    ref, ref_nombre = serie_referencia(d, f.cafci, vs)
    rf = fc.retornos_periodos(d.fechas, y, i)
    rb = fc.retornos_periodos(d.fechas, ref, i) if ref is not None else {}
    per: Dict[str, Dict[str, Optional[float]]] = {}
    for p in fc.PERIODO_KEYS:
        a, b = rf.get(p), rb.get(p)
        per[p] = {"f": a, "b": b, "x": (a - b) if a is not None and b is not None else None}
    pn = d.pn_fondo(f.cafci)
    k = fc.ultimo_valido(pn)
    i365 = fc.corte_periodo(d.fechas, i, "d365") if i > 0 else -1
    rg = fc.riesgo(d.fechas, y, ref, max(i365, 0), i) if i > 0 else {}
    return {"cafci": f.cafci, "cod": f.cod, "nombre": f.nombre, "corto": f.corto, "tipo": f.tipo,
            "moneda": f.moneda, "familia": f.familia, "grupo": f.grupo, "clase": d.clases[col].clase,
            "n_clases": len(f.cols), "fecha": str(d.fechas[i]) if i >= 0 else None,
            "vcp": float(y[i]) if i >= 0 else None,
            "pn": float(pn[k]) if k >= 0 else None,
            "bm": ref_nombre if ref is not None else None, "per": per,
            "vol": rg.get("vol"), "te": rg.get("te"), "max_dd": rg.get("max_dd"),
            "atrasado": bool(i >= 0 and (len(d.fechas) - 1 - i) > 3)}


def tablero(d: Datos, vs: str = "bm") -> List[Dict[str, Any]]:
    """Filas de todos los fondos con cuotaparte, ordenadas por tipo y nombre."""
    filas = [fila_tablero(d, f, vs) for f in d.fondos.values()]
    filas.sort(key=lambda r: (_ORDEN_TIPO.get(r["tipo"], 9), r["grupo"] or "~", r["nombre"]))
    return filas


def _epoch(fechas: np.ndarray) -> List[int]:
    return fechas.astype("datetime64[s]").astype(np.int64).tolist()


def _lista(y: np.ndarray, dec: int = 4) -> List[Optional[float]]:
    """Vector → lista JSON-able (NaN → None), redondeada. Vectorizado: una
    ventana «Máx» son miles de puntos por serie."""
    y = np.asarray(y, dtype=float)
    fin = np.isfinite(y)
    out = np.round(np.where(fin, y, 0.0), dec).astype(object)
    out[~fin] = None
    return out.tolist()


MAX_PUNTOS = 800              # puntos por serie que se mandan al gráfico


def _muestreo(n: int, max_pts: Optional[int] = None) -> np.ndarray:
    """Índices (ascendentes, con el primero y el último) para dibujar una
    serie de `n` puntos con a lo sumo `max_pts` (default `MAX_PUNTOS`): el
    gráfico mide ~600 px y una ventana de 20 años son 4.400 ruedas. Las
    cuentas van siempre con todo."""
    max_pts = MAX_PUNTOS if max_pts is None else max_pts
    if n <= max_pts:
        return np.arange(n)
    return np.unique(np.round(np.linspace(0, n - 1, max_pts)).astype(int))


def detalle(d: Datos, cafci: int, clase: Optional[str] = None, vs: str = "bm",
            rango: str = "ytd", desde: Optional[str] = None, hasta: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Todo lo del panel de un fondo: períodos, ventana elegida (retorno,
    riesgo, serie base 100 y exceso acumulado), meses, clases y flujos."""
    f = d.fondos.get(int(cafci))
    if f is None:
        return None
    col = d.col(f.cafci, clase)
    y = d.vcp[:, col]
    i_fin = fc.ultimo_valido(y)
    if i_fin < 0:
        return None
    ref, ref_nombre = serie_referencia(d, f.cafci, vs)
    base = fila_tablero(d, f, vs, d.clases[col].clase)
    i0, i1 = rango_indices(d, i_fin, rango, desde, hasta)
    k0 = fc.ultimo_valido_desde(y, i0)            # la clase puede nacer dentro de la ventana
    if 0 <= k0 <= i1:
        i0 = k0
    dias = int((d.fechas[i1] - d.fechas[i0]).astype(int)) if i1 > i0 else 0
    rf = fc.retorno(y, i0, i1)
    rb = fc.retorno(ref, i0, i1) if ref is not None else None
    ventana = {"desde": str(d.fechas[i0]), "hasta": str(d.fechas[i1]), "dias": dias, "ruedas": i1 - i0,
               "f": rf, "b": rb, "x": (rf - rb) if rf is not None and rb is not None else None,
               "f_tna": fc.tna(rf, dias), "b_tna": fc.tna(rb, dias),
               "f_tea": fc.anualizar(rf, dias), "b_tea": fc.anualizar(rb, dias)}
    # bruto de honorarios (aprox.): la cuotaparte ya viene neta del honorario
    # de administración de la clase, que devenga fee / 365 por día corrido.
    fee = d.fees.get((f.cafci, clase_corta(d.clases[col].clase)))
    ventana["fee"] = fee
    if fee is not None and rf is not None:
        bruto = (1.0 + rf) * (1.0 + fee / 365.0) ** dias - 1.0
        ventana["f_bruto"] = bruto
        ventana["x_bruto"] = (bruto - rb) if rb is not None else None
    riesgo = fc.riesgo(d.fechas, y, ref, i0, i1)
    # serie del gráfico: fondo y referencia base 100 + exceso acumulado (cociente)
    xs = d.fechas[i0:i1 + 1]
    ms = _muestreo(len(xs))
    yf = fc.base100(y, i0, i1)
    serie: Dict[str, Any] = {"x": _epoch(xs[ms]), "f": _lista(yf[ms]), "b": None, "x_exc": None,
                             "nombre": f"{f.corto} {d.clases[col].clase}", "ref": ref_nombre if ref is not None else None}
    if ref is not None:
        yb = fc.base100(ref, i0, i1)
        serie["b"] = _lista(yb[ms])
        with np.errstate(divide="ignore", invalid="ignore"):
            exc = (yf / yb - 1.0) * 100.0
        serie["x_exc"] = _lista(exc[ms])
    # drawdown del fondo en la ventana
    v = y[i0:i1 + 1]
    pico = np.fmax.accumulate(np.where(np.isfinite(v), v, -np.inf))
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(np.isfinite(v) & (pico > 0), (v / pico - 1.0) * 100.0, np.nan)
    serie["dd"] = _lista(dd[ms])
    # meses (13) del fondo y la referencia
    mf = fc.mensuales(d.fechas, y, i_fin, 13)
    mb = dict(fc.mensuales(d.fechas, ref, i_fin, 13)) if ref is not None else {}
    meses = [{"mes": m, "f": a, "b": mb.get(m), "x": (a - mb[m]) if a is not None and mb.get(m) is not None else None}
             for m, a in mf]
    # clases del fondo
    clases = []
    for c in f.cols:
        yc = d.vcp[:, c]
        ic = fc.ultimo_valido(yc)
        if ic < 0:
            continue
        rc = fc.retornos_periodos(d.fechas, yc, ic, ("d1", "mtd", "d30", "ytd", "d365"))
        clases.append({"clase": d.clases[c].clase, "fee": d.fees.get((f.cafci, clase_corta(d.clases[c].clase))),
                       "vcp": float(yc[ic]), "fecha": str(d.fechas[ic]),
                       "pn": float(d.pn[ic, c]) if np.isfinite(d.pn[ic, c]) else None,
                       "viva": ic == f.ultimo, "principal": c == f.principal, "elegida": c == col, "per": rc})
    clases.sort(key=lambda r: -(r["pn"] or 0.0))
    return {"fondo": f, "fila": base, "clase": d.clases[col].clase, "vs": vs,
            "ref": ref_nombre if ref is not None else None, "ventana": ventana, "riesgo": riesgo,
            "serie": serie, "meses": meses, "clases": clases,
            "flujos": flujos(d, f.cafci, i0, i1), "pesos": d.pesos_bm.get(f.cafci)}


def flujos(d: Datos, cafci: int, i0: int, i1: int) -> Dict[str, Any]:
    """Patrimonio y suscripciones netas del fondo en la ventana. Con
    `Delta_SyR_Fondos` son las reales (suscripciones y rescates por separado);
    si no, la estimación PN_t − PN_{t−1} × (1 + rendimiento) con la clase
    principal. Devuelve totales y la serie diaria para el gráfico."""
    f = d.fondos[int(cafci)]
    pn = d.pn_fondo(cafci)
    xs = d.fechas[i0:i1 + 1]
    ms = _muestreo(len(xs))

    def _tramos(v: np.ndarray) -> List[Optional[float]]:
        """Flujo por punto dibujado: la SUMA de las ruedas que el muestreo
        junta en cada punto (hasta él inclusive), no el valor de una sola."""
        if len(ms) == len(v):
            return _lista(v, 2)
        acum = np.cumsum(np.where(np.isfinite(v), v, 0.0))
        return _lista(np.diff(np.concatenate([[0.0], acum[ms]])), 2)

    out: Dict[str, Any] = {"fuente": None, "x": _epoch(xs[ms]), "pn": _lista(pn[i0:i1 + 1][ms], 2),
                           "neto": None, "total_neto": None,
                           "pn_ini": float(pn[i0]) if np.isfinite(pn[i0]) else None,
                           "pn_fin": float(pn[i1]) if np.isfinite(pn[i1]) else None}
    s = d.syr.get(int(cafci))
    # Con el archivo de ESCO sólo si cubre TODA la ventana (arranca en 2023 y
    # no siempre está al día): una ventana que lo excede daría un total
    # parcial → va la estimación.
    if (s is not None and len(s[0]) and len(xs) and s[0][0] <= xs[0]
            and s[0][-1] >= xs[-1] - np.timedelta64(_SYR_ATRASO_DIAS, "D")):
        fs, su, re = s
        # un movimiento concertado en un día sin rueda cae en la rueda siguiente
        pos = np.searchsorted(xs, fs)
        ok = (pos < len(xs)) & (fs > xs[0])
        if ok.any():
            a = np.zeros(len(xs))
            b = np.zeros(len(xs))
            np.add.at(a, pos[ok], su[ok])
            np.add.at(b, pos[ok], re[ok])
            out.update({"fuente": "syr", "neto": _tramos(a - b), "total_susc": float(a.sum()),
                        "total_resc": float(b.sum()), "total_neto": float((a - b).sum())})
            return out
    est = fc.flujos_netos(pn, d.vcp[:, f.principal])[i0:i1 + 1]
    if len(est):
        est[0] = np.nan                      # el flujo de la rueda base no es de la ventana
    if np.isfinite(est).any():
        out.update({"fuente": "estimado", "neto": _tramos(est), "total_neto": float(np.nansum(est))})
    return out
