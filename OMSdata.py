# -*- coding: utf-8 -*-
"""OMSdata.py

Módulo común para:
- Curvas (listas dinámicas desde `todos_los_bonos`)
- Helpers de futuros ROFEX (A3500 spot + vencimientos)
- Helpers de settlement según plazo (CI vs 24hs)
- Matrices de forwards (a partir de TIREA y vencimientos)

Objetivo: que OMSweb_app y OMScli no dependan uno del otro.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date
from functools import lru_cache
import re



import numpy as np
import pandas as pd
import requests
from pandas.tseries.offsets import MonthEnd

from dias_habiles import siguiente_dia_habil_ar
import rentafija
from especies import todos_los_bonos, BONDS

# -----------------------------------------------------------------------------
# BYMA tickers "reales" (evita pedir market data de variantes internas: *j, *v)
# Convención actual del repo: variantes internas usan sufijo en minúscula.
# -----------------------------------------------------------------------------

def is_byma_ticker(code: str) -> bool:
    return isinstance(code, str) and (code == code.upper())


BYMA_TICKERS: list[str] = sorted([c for c in BONDS.keys() if is_byma_ticker(str(c))])


# -----------------------------------------------------------------------------
# Maturity map
# -----------------------------------------------------------------------------

def _get_codigo(b) -> str | None:
    return getattr(b, "codigo", None) or getattr(b, "ticker", None) or getattr(b, "symbol", None)


def _to_ts(x) -> pd.Timestamp:
    with suppress(Exception):
        if x is None:
            return pd.NaT
        return pd.Timestamp(x)
    return pd.NaT


MATURITY_MAP: dict[str, pd.Timestamp] = {
    _get_codigo(b): _to_ts(getattr(b, "vencimiento", None))
    for b in todos_los_bonos
    if _get_codigo(b)
}


def sort_by_maturity(codes: list[str]) -> list[str]:
    """Ordena por vencimiento (cuando existe)."""
    # Uniquear preservando primero aparición
    codes_u = list(dict.fromkeys([c for c in codes if isinstance(c, str)]))

    far = pd.Timestamp.max
    return sorted(codes_u, key=lambda c: MATURITY_MAP.get(c, far) if pd.notna(MATURITY_MAP.get(c, pd.NaT)) else far)


# -----------------------------------------------------------------------------
# Curvas dinámicas (mismo criterio que en bymaapi)
# -----------------------------------------------------------------------------

def _norm(x) -> str:
    return str(x or "").strip().lower()


def build_curvas() -> dict[str, list[str]]:
    """Arma curvas desde `todos_los_bonos` usando filtros por industria/clasificación.

    Se intenta ser tolerante a pequeñas variaciones de texto en `industria`.
    """
    cer: list[str] = []
    tasafijaars: list[str] = []
    tamar: list[str] = []
    globales: list[str] = []
    dolarlinked: list[str] = []
    dual_fija: list[str] = []
    bonar: list[str] = []

    for b in todos_los_bonos:
        code = getattr(b, "codigo", None) or getattr(b, "ticker", None) or getattr(b, "symbol", None)
        if not code or not is_byma_ticker(code):
            continue

        ind = _norm(getattr(b, "industria", None))
        cla = _norm(getattr(b, "clasificacion", None))
        quote = _norm(getattr(b, "quote_price_cnv", None))

        # CER
        if ("inflación" in ind) or ("inflacion" in ind):
            cer.append(code)

        # Tasa fija ARS (Boncap/Lecap/Ledes/Letes)
        if (
            (("ars" in ind) and ("tasa fija" in ind) and (cla == "soberano"))
            or ("letras zero cupón" in ind)
            or ("letras zero cupon" in ind)
        ):
            tasafijaars.append(code)

        # TAMAR
        if "tamar" in ind:
            tamar.append(code)

        # Globales (ley extranjera, dirty)
        if ("ley extranjera" in ind) and (quote == "dirty"):
            globales.append(code)

        # Dólar linked
        if ("dolar linked" in ind) or ("dólar linked" in ind):
            dolarlinked.append(code)

        # Dual fija / TAMAR
        if (cla == "soberano") and ("dual" in ind) and (("fija" in ind) or ("tamar" in ind)):
            dual_fija.append(code)

        # Bonar (ley argentina, dirty)
        if (cla == "soberano") and ("ley argentina" in ind) and (quote == "dirty"):
            bonar.append(code)

    # Orden por vencimiento (cuando aplica)
    curvas = {
        "tasafijaars": sort_by_maturity(tasafijaars),
        "cer": sort_by_maturity(cer),
        "tamar": sort_by_maturity(tamar),
        "dolarlinked": sort_by_maturity(dolarlinked),
        "dual_fija": sort_by_maturity(dual_fija),
        "globales": sort_by_maturity(globales),
        "bonar": sort_by_maturity(bonar),
    }

    # Limpieza: elimina listas vacías (así la app no muestra secciones vacías)
    return {k: v for k, v in curvas.items() if v}


CURVAS: dict[str, list[str]] = build_curvas()


# Labels opcionales para UI
CURVAS_LABELS: dict[str, str] = {
    "tasafijaars": "Tasa fija ARS",
    "cer": "CER",
    "tamar": "TAMAR",
    "dolarlinked": "Dólar linked",
    "dual_fija": "Dual fija/TAMAR",
    "globales": "Globales (ley extranjera)",
    "bonar": "Bonar (ley argentina)",
}

# -----------------------------------------------------------------------------
# Futuros ROFEX dólar A3500
# -----------------------------------------------------------------------------

# HTTP session (keep-alive) para MAE
#_HTTP = requests.Session()
#_HTTP.headers.update({"x-api-key": "nuDX73vj2483KSUgvenkj9t50oA0vgvA4WcuRAER"})

# Meses en castellano (3 letras)
MESES_3L = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}

# Regex: MES (3 letras) + AÑO (2 dígitos) + SUFIJO ALFABÉTICO OPCIONAL
CODIGO_REGEX = re.compile(r"[A-Z]+/([A-ZÁ]{3})(\d{2})([A-Z]*)$")




def _parsear_vencimiento_unit(code: str) -> pd.Timestamp:
    """Parsea un solo código (DLR/AGO25, DLR/AGO25A, etc.) → primer hábil AR tras fin de mes."""
    if not isinstance(code, str):
        return pd.NaT
    m = CODIGO_REGEX.search(code.strip().upper())
    if not m:
        return pd.NaT
    mes_abbr, yy, _suf = m.groups()
    mnum = MESES_3L.get(mes_abbr)
    if mnum is None:
        return pd.NaT
    year = 2000 + int(yy)
    fin_mes = pd.Timestamp(year, mnum, 1) + MonthEnd(0)
    return pd.Timestamp(siguiente_dia_habil_ar(fin_mes))


@lru_cache(maxsize=512)
def parsear_vencimiento(code: str) -> pd.Timestamp:
    """Cached: evita recalcular lo mismo en cada refresh."""
    return _parsear_vencimiento_unit(code)


# Lista fija (podés cambiar a generador si querés)
FUTUROS_DLR: list[str] = [
    "DLR/OCT25",
    "DLR/OCT25A",
    "DLR/NOV25",
    "DLR/NOV25A",
    "DLR/DIC25",
    "DLR/DIC25A",
    "DLR/ENE26",
    "DLR/ENE26A",
    "DLR/FEB26",
    "DLR/FEB26A",
    "DLR/MAR26",
    "DLR/MAR26A",
    "DLR/ABR26",
    "DLR/ABR26A",
    "DLR/MAY26",
    "DLR/MAY26A",
    "DLR/JUN26",
    "DLR/JUN26A",
    "DLR/JUL26",
    "DLR/JUL26A",
]



# -----------------------------------------------------------------------------
# Settlement helpers
# -----------------------------------------------------------------------------

def settlement_offset_from_plazo(plazo: str) -> int:
    """Retorna offset de días hábiles para settlement según plazo."""
    p = str(plazo or "").strip().upper()
    if p == "CI":
        return 0
    # Convención del repo: '24hs' = T+1
    return 1


def settlement_date_from_plazo(plazo: str) -> date:
    """Fecha de settlement (date) según plazo (usa n_dias_laborales de rentafija)."""
    offset = settlement_offset_from_plazo(plazo)
    return rentafija.n_dias_laborales(date.today(), offset)


def settlement_str_from_plazo(plazo: str) -> str | None:
    """Fecha de settlement en formato dd/mm/YYYY, o None si no aplica."""
    # Para mantener compat con los métodos de rentafija, siempre devolvemos string.
    d = settlement_date_from_plazo(plazo)
    return d.strftime("%d/%m/%Y")


# -----------------------------------------------------------------------------
# Forwards
# -----------------------------------------------------------------------------

def forwards_matrix_from_df(
    df: pd.DataFrame,
    plazo: str,
    code_col: str = "Código",
    yield_col: str = "TIREA",
    maturity_map: dict[str, pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """Matriz de forwards anualizados implícitos entre vencimientos.

    Se calcula con comp efectiva anual:
        DF(t) = (1+y)^(-t)
        f(t1,t2) = (DF(t1)/DF(t2))^(1/(t2-t1)) - 1

    Devuelve matriz (rows=corto, cols=largo) con NaN en diagonal e inferior.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    mm = maturity_map or MATURITY_MAP

    tmp = df[[code_col, yield_col]].copy()
    tmp[yield_col] = pd.to_numeric(tmp[yield_col], errors="coerce")
    tmp["maturity"] = tmp[code_col].map(mm)
    tmp = tmp.dropna(subset=[yield_col, "maturity"])

    if tmp.empty:
        return pd.DataFrame()

    # Orden por vencimiento
    tmp = tmp.sort_values("maturity").reset_index(drop=True)

    settle = pd.Timestamp(settlement_date_from_plazo(plazo))
    t = (tmp["maturity"] - settle).dt.days.astype(float) / 365.0
    y = tmp[yield_col].astype(float)

    # Evitar t <= 0
    valid = t > 0
    tmp = tmp.loc[valid].reset_index(drop=True)
    t = t.loc[valid].reset_index(drop=True)
    y = y.loc[valid].reset_index(drop=True)

    if len(tmp) < 2:
        return pd.DataFrame()

    codes = tmp[code_col].astype(str).tolist()
    tvals = t.to_numpy()
    yvals = y.to_numpy()

    # Discount factors
    with np.errstate(over="ignore", invalid="ignore"):
        dfac = np.power(1.0 + yvals, -tvals)

    n = len(codes)
    mat = np.full((n, n), np.nan, dtype=float)

    for i in range(n):
        for j in range(i + 1, n):
            dt = tvals[j] - tvals[i]
            if not np.isfinite(dt) or dt <= 0:
                continue
            if not (np.isfinite(dfac[i]) and np.isfinite(dfac[j])):
                continue
            with np.errstate(over="ignore", invalid="ignore"):
                fwd = np.power(dfac[i] / dfac[j], 1.0 / dt) - 1.0
            mat[i, j] = fwd

    return pd.DataFrame(mat, index=codes, columns=codes)
