# -*- coding: utf-8 -*-

"""OMSweb_app.py — Streamlit

APP_CALCULADORA_BONOS — Refactor (02/2026) 26/02/2026

Cambios incorporados (feedback Rorru):
1) Navegación por PESTAÑAS (no radio en sidebar).
2) Curvas: se ven TODAS juntas (sin seleccionar una por una).
3) Mercado: por defecto "Variación px" al lado de "Variación %".
   Orden default por Duration y los NaN/None abajo.
4) Colores: Variación % y Variación px con barras verde/rojo + Last en verde/rojo según variación.
5) Gráficos: sacar la línea que une puntos del LAST.
6) Gráficos: explicación clara de parámetros NSS (unidades y significado).
7) Bug % vs 0.40: normalización robusta (usa plotter.pct_series) para gráficos y forwards.
8) Switch en gráficos: TIREA <-> TEM (incluye NSS sobre la métrica elegida).
9) Estimar TIR/TEM: queda (ya estaba ok).
10) Futuros: 2 tablas (Minorista vs Mayorista con sufijo 'A'), con color por variación.
11) Total Return: agregar mini explicación de parámetros + anchor duration.

PATCH (02/2026):
- CER Proyectado: evalúa con sufijo 'j' pero marketdata se pide por base (sin sufijo).
- Dual: separa Dual Fija vs Dual Tamar/Variable (evalúa con sufijo 'v' pero marketdata por base).
- Sin tocar especies.py.

PATCH (02/2026 - TR defaults + columnas TR):
- Total Return: defaults (Nivel/Pendiente/Convexidad) pegados a NSS actual.
- Total Return: tabla incluye Px inicial, Px final, Cupones cobrados, P&L Capital.
- Total Return: columna "Total Return" con barra y colores.
- FIX: keys de inputs TR dependen de curva/plazo (Streamlit no re-aplica value si key es fija).
- FIX: conversión robusta de Px/cupones (evita float("1,234") etc).

REFACTOR (02/2026):
- Unificación load_curve_last_table / load_curve_market_table → _load_curve_base.
- Paralelización de metrics_for_price con ThreadPoolExecutor.
- Futuros DLR generados dinámicamente (sin hardcodear meses).
- Credenciales removidas del código fuente (solo env vars).
"""

from __future__ import annotations

import os
import re
import copy
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import MonthEnd

import OMSapi
import OMSmktdata
import OMSprices
import OMSsettings as cfg
import rentafija
import plotter  # usa pct_series + NSS helpers
from dias_habiles import siguiente_dia_habil_ar
from utils import tna_a_tir, tir_a_tna

# Universo de bonos
from especies import *
from especies import todos_los_bonos

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    go = None


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

APP_TITLE = "OMS — Curvas, Mercado, Forwards, Gráficos y Total Return"
DEFAULT_MARKET_ID = "ROFX"
DEFAULT_PLAZO = "24hs"  # "24hs" o "CI"

# Cache TTL (segundos)
TTL_MKT = 15
TTL_METRICS = 15

# Auto-refresh interval (seconds) — Bloomberg-style live update
AUTO_REFRESH_SECS = 15

# Workers para cálculo paralelo de métricas
_METRICS_WORKERS = 8


# ──────────────────────────────────────────────────────────────────────
# Helpers generales
# ──────────────────────────────────────────────────────────────────────

def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _codigo_from_symbol(symbol: str) -> str:
    """Extrae código desde símbolos tipo 'MERV - XMEV - TX26 - 24hs'.
    Si no matchea el patrón, devuelve el symbol tal cual (útil para futuros: 'DLR/FEB26').
    """
    s = _safe_str(symbol).strip()
    parts = s.split(" - ")
    if len(parts) >= 3:
        return parts[2].strip()
    return s


def _build_symbols(codes: Iterable[str], plazo: str) -> List[str]:
    suf = "24hs" if str(plazo).lower().startswith("24") else "CI"
    return [f"MERV - XMEV - {c} - {suf}" for c in codes]


def _settlement_date_str(plazo: str) -> Optional[str]:
    """Devuelve settlement_date en formato dd/mm/YYYY para rentafija, o None."""
    if str(plazo).upper() == "CI":
        d = rentafija.n_dias_laborales(date.today(), 0)
        return d.strftime("%d/%m/%Y")
    return None


def _nss_defaults_level_slope_convex(
    df_last: pd.DataFrame,
    threshold_factor: float = 2.0,
    anchor: float = 1.0,
    which: str = "TIREA",
) -> Optional[Tuple[float, float, float]]:
    """
    Devuelve (level_pct, slope_bps, convex_bps) aproximando NSS por Taylor 2º orden alrededor de anchor.
    - level_pct: puntos porcentuales (ej 42.35)
    - slope_bps: bps por 1 año de duration
    - convex_bps: bps por año^2
    """
    try:
        if df_last is None or df_last.empty:
            return None

        tmp = df_last[["Código", "Duration", "TIREA", "TEM"]].copy()

        popt, _, _ = plotter._fit_nss_cached(
            tmp,
            which=str(which).upper(),
            threshold_factor=float(threshold_factor),
            use_cache=False,
        )
        if popt is None:
            return None

        def f(x: float) -> float:
            # nss_model devuelve puntos porcentuales
            return float(plotter.nss_model(np.array([float(x)], dtype="float64"), *popt)[0])

        a = float(anchor)
        # paso chiquito en años de duration (no muy chico por ruido numérico)
        h = 0.02

        y0 = f(a)
        yp = f(a + h)
        ym = f(a - h)

        # derivadas en % por año y % por año^2
        slope_pct_per_year = (yp - ym) / (2.0 * h)
        convex_pct_per_year2 = (yp - 2.0 * y0 + ym) / (h * h)

        # 1% = 100 bps
        slope_bps = float(slope_pct_per_year * 100.0)
        convex_bps = float(convex_pct_per_year2 * 100.0)

        level_pct = float(y0)
        return level_pct, slope_bps, convex_bps
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# FIX sufijos (j/v) decididos por curva
# ──────────────────────────────────────────────────────────────────────

# Curvas con cashflow alternativo => sufijo en el código de evaluación
CURVE_EVAL_SUFFIX: Dict[str, str] = {
    "cerproy": "j",
    "dualtamar": "v",   # dual tamar siempre con v
}


def _apply_curve_suffix(curve_key: str, base_code: str) -> str:
    suf = CURVE_EVAL_SUFFIX.get(str(curve_key), "")
    return f"{base_code}{suf}" if suf else base_code


def _md_code_from_calc_code(calc_code: str) -> str:
    c = str(calc_code).strip()
    return c[:-1] if c.lower().endswith(("j", "v")) else c


def _bond_obj(code: str):
    """
    Resolver como bymaapi:
    - Si code='TX26j' busca variable global TX26j
    - Si no existe y termina en j/v, cae al base (TX26/TTM26)
    """
    c = str(code).strip()
    obj = globals().get(c)
    if obj is None and c.lower().endswith(("j", "v")):
        obj = globals().get(c[:-1])
    return obj


def _calc_duration_from_state(bond_obj, tirea: float) -> float:
    """Calcula duration usando cashflows ya generados por calcula_tirea (performance)."""
    try:
        cf = bond_obj.cashflow_cpn
        fs = bond_obj.fecha_settlement
        if cf is None or fs is None:
            return float("nan")
        cf = cf[cf["Fechas"] > fs]
        if cf.empty:
            return float("nan")

        totals = cf["Total"].to_numpy(dtype="float64", copy=False)
        fechas = cf["Fechas"].to_list()
        t = np.array([(f - fs).days / 365.0 for f in fechas], dtype="float64")

        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            disc = (1.0 + float(tirea)) ** (-t)
            pv = totals * disc
            price = float(np.nansum(pv))
            if not np.isfinite(price) or price == 0.0:
                return float("nan")
            dur = float(np.nansum(pv * t) / price)
        return dur
    except Exception:
        return float("nan")


def _tna_from_tirea(bond_obj, tirea: float, bond_type: str) -> Optional[float]:
    bt = (bond_type or "").lower()
    try:
        if bt in ("lecap", "tamar", "dlksob"):
            dias = getattr(bond_obj, "dias_remanentes", None)
            return rentafija.tir_a_tna(tirea, dias, 365) if dias else None

        if bt in ("cer", "cerproy"):
            return rentafija.tir_a_tna(tirea, 180, 365)

        if bt in ("hdsob", "bopreal"):
            return rentafija.tir_a_tna(tirea, 180, 360)

        if bt == "dual":
            return rentafija.tir_a_tna(tirea, 30, 365)

        return getattr(bond_obj, "tna", None)
    except Exception:
        return None


_NAN_METRICS = {"TIREA": np.nan, "TNA": np.nan, "TEM": np.nan, "Paridad": np.nan, "Duration": np.nan}

# ── Thread-safety: los objetos bono de especies.py son singletons globales.
#    calcula_tirea() muta .tirea, .cashflow_cpn, .fecha_settlement, etc.
#    Con ThreadPoolExecutor, 2 threads calculando el mismo bono con precios
#    distintos (Bid vs Last) se pisan el estado mutuamente → race condition.
#    Solución: lock por código de bono + copy.copy() del objeto antes de calcular.
_bond_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)


def _bond_obj_copy(code: str):
    """Thread-safe: devuelve una COPIA shallow del objeto bono para cálculos
    que mutan estado (calcula_tirea, generate_cashflows, etc.).
    Cada thread trabaja sobre su propia copia → sin race conditions."""
    obj = _bond_obj(code)
    if obj is None:
        return None
    with _bond_locks[code]:
        return copy.copy(obj)


def metrics_for_price(code: str, price_pct: Any, bond_type: str, settlement_date: Optional[str]) -> Dict[str, Any]:
    """Métricas numéricas (sin formatear). price_pct: ej 145.30.
    THREAD-SAFE: usa copia del objeto bono."""
    if price_pct is None or not np.isfinite(price_pct):
        return dict(_NAN_METRICS)

    bond_obj = _bond_obj_copy(code)
    if bond_obj is None:
        return dict(_NAN_METRICS)

    precio = float(price_pct) / 100.0
    try:
        tirea = float(bond_obj.calcula_tirea(precio, settlement_date))
        tna = _tna_from_tirea(bond_obj, tirea, bond_type)
        tem = (1.0 + tirea) ** (30.0 / 360.0) - 1.0
        paridad = getattr(bond_obj, "paridad", np.nan)
        duration = _calc_duration_from_state(bond_obj, tirea)
        return {"TIREA": tirea, "TNA": tna, "TEM": tem, "Paridad": paridad, "Duration": duration}
    except Exception:
        return dict(_NAN_METRICS)


def _parallel_metrics(codes: np.ndarray, prices: np.ndarray, bond_type: str, settle: Optional[str]) -> pd.DataFrame:
    """Calcula metrics_for_price en paralelo con ThreadPoolExecutor."""
    n = len(codes)
    if n == 0:
        return pd.DataFrame(columns=list(_NAN_METRICS.keys()))

    results: List[Optional[Dict[str, Any]]] = [None] * n

    def _work(idx: int) -> Tuple[int, Dict[str, Any]]:
        return idx, metrics_for_price(codes[idx], prices[idx], bond_type, settle)

    workers = min(_METRICS_WORKERS, n)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_work, i): i for i in range(n)}
        for fut in as_completed(futures):
            idx, m = fut.result()
            results[idx] = m

    return pd.DataFrame(results)


def tirea_for_price(code: str, price_pct: Any, settlement_date: Optional[str]) -> float:
    """THREAD-SAFE: usa copia del objeto bono."""
    if price_pct is None or not np.isfinite(price_pct):
        return float("nan")
    bond_obj = _bond_obj_copy(code)
    if bond_obj is None:
        return float("nan")
    precio = float(price_pct) / 100.0
    try:
        return float(bond_obj.calcula_tirea(precio, settlement_date))
    except Exception:
        return float("nan")


def _parallel_tirea(codes: np.ndarray, prices: np.ndarray, settle: Optional[str]) -> List[float]:
    """Calcula tirea_for_price en paralelo."""
    n = len(codes)
    if n == 0:
        return []

    results: List[float] = [float("nan")] * n

    def _work(idx: int) -> Tuple[int, float]:
        return idx, tirea_for_price(codes[idx], prices[idx], settle)

    workers = min(_METRICS_WORKERS, n)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_work, i): i for i in range(n)}
        for fut in as_completed(futures):
            idx, val = fut.result()
            results[idx] = val

    return results


def _fmt_pct(x: Any) -> str:
    return "" if x is None or not np.isfinite(x) else f"{x:.2%}"


def _fmt_num(x: Any, nd: int = 4) -> str:
    return "" if x is None or not np.isfinite(x) else f"{x:,.{nd}f}"


def _sort_duration_nan_last(df: pd.DataFrame, col: str = "Duration") -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df
    d = pd.to_numeric(df[col], errors="coerce")
    # NaN-safe: sort_values con na_position="last" es lo más portable
    tmp = df.assign(_sort_key_=d)
    tmp = tmp.sort_values("_sort_key_", ascending=True, na_position="last").drop(columns=["_sort_key_"])
    return tmp.reset_index(drop=True)


def _bar_limits(s: pd.Series) -> Tuple[float, float]:
    ser = pd.to_numeric(s, errors="coerce")
    lim = float(np.nanmax(np.abs(ser.to_numpy(dtype="float64")))) if len(ser) else 1.0
    if not np.isfinite(lim) or lim <= 0:
        lim = 1.0
    return -lim, lim


def _diverging_bg(val: Any, lim: float, bold: bool = True) -> str:
    """
    Estilo celda con fondo rojo/verde según signo e intensidad según |val|/lim.
    Funciona bien en st.dataframe aun si la barra se ve poco.
    """
    try:
        x = float(val)
    except Exception:
        return ""

    if not np.isfinite(x) or lim is None or not np.isfinite(lim) or lim <= 0:
        return ""

    a = min(abs(x) / float(lim), 1.0)  # intensidad 0..1

    if x > 0:
        r, g, b = 46, 204, 113
    elif x < 0:
        r, g, b = 231, 76, 60
    else:
        return ""

    alpha = 0.12 + 0.55 * a
    fw = "700" if bold else "400"
    return f"background-color: rgba({r},{g},{b},{alpha:.3f}); font-weight:{fw};"


def _yield_pct_points(series_or_scalar: Any) -> Any:
    """Convierte yields a 'puntos porcentuales' (ej 42.35 => 42.35%).
    Usa plotter.pct_series que detecta 0.40 -> 40, "41.2%" -> 41.2, 3.3 -> 3.3.
    """
    if isinstance(series_or_scalar, pd.Series):
        return plotter.pct_series(series_or_scalar)
    try:
        s = pd.Series([series_or_scalar])
        return float(plotter.pct_series(s).iloc[0])
    except Exception:
        return float("nan")


def _warn_once(key: str, msg: str) -> None:
    """Muestra st.warning una sola vez por sesión y key."""
    k = f"_warn_once::{key}"
    if not st.session_state.get(k, False):
        st.warning(msg)
        st.session_state[k] = True


# ──────────────────────────────────────────────────────────────────────
# Universo de curvas
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CurveDef:
    key: str
    label: str
    bond_type: str


CURVES: List[CurveDef] = [
    CurveDef("cer", "CER", "cer"),
    CurveDef("lecap", "LECAP / Tasa fija", "lecap"),
    CurveDef("tamar", "TAMAR", "tamar"),
    CurveDef("cerproy", "CER Proyectado", "cerproy"),
    CurveDef("dolarlinked", "Dólar Linked", "dlksob"),
    CurveDef("globales", "Globales (Ley Extranjera)", "hdsob"),
    CurveDef("bonares", "Bonares (Ley Argentina)", "hdsob"),
    CurveDef("bopreales", "Bopreales (Ley Argentina)", "bopreal"),

    # Dual separadas:
    CurveDef("dualfija", "Dual Fija (base)", "dual"),
    CurveDef("dualtamar", "Dual Tamar (v)", "dual"),
]


def _codigo_obj(b) -> str:
    return (
        getattr(b, "ticker", None)
        or getattr(b, "codigo", None)
        or getattr(b, "symbol", None)
        or b.__class__.__name__
    )


@st.cache_data(show_spinner=False)
def build_curve_codes() -> Dict[str, List[str]]:
    """Arma listas de códigos con filtros tipo bymaapi — una sola pasada."""
    bonos = list(todos_los_bonos) if isinstance(todos_los_bonos, (list, tuple)) else []

    def has(code: str) -> bool:
        return str(code) in BONDS

    # Agrupar por (industria, clasificacion) en una sola pasada
    by_ind: Dict[str, List[str]] = defaultdict(list)
    by_ind_clas: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    for b in bonos:
        code = _codigo_obj(b)
        ind = getattr(b, "industria", None) or ""
        clas = getattr(b, "clasificacion", None) or ""
        qpc = getattr(b, "quote_price_cnv", None) or ""
        by_ind[ind].append((code, clas, qpc))
        by_ind_clas[(ind, clas)].append((code, qpc))

    cer = sorted({c for c, _, _ in by_ind.get("Soberano Inflación", [])})

    lecap = sorted({
        c for c, clas, _ in (
            by_ind.get("Soberano ARS Tasa Fija", []) +
            by_ind.get("Soberano Letras Zero Cupón (Ledes y Letes)", [])
        )
        if (clas == "Soberano" or c in by_ind.get("Soberano Letras Zero Cupón (Ledes y Letes)", []))
        and has(c)
    })
    # Re-filter lecap more precisely
    lecap_set = set()
    for c, clas, _ in by_ind.get("Soberano ARS Tasa Fija", []):
        if clas == "Soberano" and has(c):
            lecap_set.add(c)
    for c, clas, _ in by_ind.get("Soberano Letras Zero Cupón (Ledes y Letes)", []):
        if has(c):
            lecap_set.add(c)
    lecap = sorted(lecap_set)

    tamar = sorted({c for c, clas, _ in by_ind.get("Soberano ARS TAMAR", []) if has(c)})

    globales = sorted({
        c for c, clas, qpc in by_ind.get("Soberano USD Ley Extranjera", [])
        if qpc == "DIRTY" and has(c)
    })

    dolarlinked = sorted({c for c, clas, _ in by_ind.get("Soberanos Dolar Linked", []) if has(c)})

    # CER Proyectado => calc codes = base + 'j'
    cerproy = sorted({
        _apply_curve_suffix("cerproy", c)
        for c, clas, _ in by_ind.get("Soberano Inflación Proyectado", [])
        if clas == "Soberano"
    })

    # DUAL FIJA (base)
    dualfija = sorted({
        c for c, clas, _ in by_ind.get("Soberano ARS Dual Fija/Tamar", [])
        if clas == "Soberano"
    })

    # DUAL TAMAR/VARIABLE (sufijo v)
    dualtamar = sorted({_apply_curve_suffix("dualtamar", c) for c in dualfija})

    bonares = sorted({
        c for c, qpc in by_ind_clas.get(("Soberano USD Ley Argentina D", "Soberano"), [])
        if qpc == "DIRTY" and has(c)
    })

    bopreales = sorted({
        c for c, qpc in by_ind_clas.get(("Soberanos USD BCRA D", "Soberano"), [])
        if has(c)
    })

    return {
        "cer": cer,
        "lecap": lecap,
        "tamar": tamar,
        "globales": globales,
        "dolarlinked": dolarlinked,
        "cerproy": cerproy,
        "bonares": bonares,
        "bopreales": bopreales,
        "dualfija": dualfija,
        "dualtamar": dualtamar,
    }


# ──────────────────────────────────────────────────────────────────────
# Sesión + Marketdata — SHARED GLOBAL (multi-user safe, bymaapi-speed)
# ──────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_session(username: str, password: str):
    """Sesión autenticada (cache_resource para no loguear en cada rerun).
    Shared across all users since credentials are the same API account."""
    return OMSapi.login(username, password)


def _all_curve_symbols(plazo: str) -> List[str]:
    """Build the FULL list of symbols for ALL curves in one shot (like bymaapi.py)."""
    curves = build_curve_codes()
    all_md_codes: set = set()
    for curve_key, codes in curves.items():
        for c in codes:
            all_md_codes.add(_md_code_from_calc_code(str(c)))
    return _build_symbols(sorted(all_md_codes), plazo)


@st.cache_data(ttl=TTL_MKT, show_spinner=False)
def _fetch_all_marketdata_bulk(
    username: str,
    password: str,
    plazo: str,
    market_id: str = DEFAULT_MARKET_ID,
    entries: str = cfg.ENTRIES,
    depth: int = cfg.DEPTH,
) -> pd.DataFrame:
    """ONE bulk fetch for ALL bond curves (like bymaapi.py main()).
    This is the key performance win: instead of N separate calls per curve,
    we do 1 call with all symbols. Shared cache across all Streamlit users."""
    session = get_session(username, password)
    symbols = _all_curve_symbols(plazo)
    return OMSmktdata.bulk_market_data(session, symbols, market_id=market_id,
                                       entries=entries, depth=depth)


def fetch_marketdata(
    username: str,
    password: str,
    symbols: List[str],
    market_id: str = DEFAULT_MARKET_ID,
    entries: str = cfg.ENTRIES,
    depth: int = cfg.DEPTH,
) -> pd.DataFrame:
    """Wrapper that extracts requested symbols from the global bulk cache.
    For symbols NOT in bonds (e.g. futures), falls back to direct fetch."""
    # Try to get from bulk cache first
    all_raw = _fetch_all_marketdata_bulk(username, password,
                                         st.session_state.get("_plazo_global", "24hs"),
                                         market_id, entries, depth)

    if all_raw is not None and not all_raw.empty:
        # Filter to requested symbols
        available = set(all_raw.index) if all_raw.index.name == "symbol" or isinstance(all_raw.index, pd.Index) else set()
        requested = set(symbols)
        found = requested & available

        if found:
            filtered = all_raw.loc[all_raw.index.isin(found)]
            missing = requested - found
            if missing:
                # Fetch missing symbols directly (e.g. futures)
                session = get_session(username, password)
                extra = OMSmktdata.bulk_market_data(session, list(missing),
                                                    market_id=market_id,
                                                    entries=entries, depth=depth)
                if extra is not None and not extra.empty:
                    return pd.concat([filtered, extra])
            return filtered

    # Fallback: direct fetch (for futures or when bulk is empty)
    session = get_session(username, password)
    return OMSmktdata.bulk_market_data(session, symbols, market_id=market_id,
                                       entries=entries, depth=depth)


def _ensure_codigo_col(df: pd.DataFrame, source: str = "index") -> pd.DataFrame:
    """Garantiza columna 'Código' (para evitar KeyError)."""
    if df is None:
        return pd.DataFrame(columns=["Código"])
    out = df.copy()
    if "Código" in out.columns:
        return out
    if "Codigo" in out.columns:
        return out.rename(columns={"Codigo": "Código"})

    if source == "index":
        if out.index is not None:
            out["Código"] = out.index.map(_codigo_from_symbol)
        else:
            out["Código"] = ""
    return out


# ──────────────────────────────────────────────────────────────────────
# Curvas: base unificada + tablas
# ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=TTL_MKT, show_spinner=False)
def _global_snapshot(username: str, password: str, plazo: str) -> Optional[pd.DataFrame]:
    """Build ONE global snapshot from the bulk fetch — all curves share this."""
    raw = _fetch_all_marketdata_bulk(username, password, plazo)
    if raw is None or raw.empty:
        return None
    snap = OMSprices.market_snapshot(raw)
    if snap is None or snap.empty:
        return None
    snap = _ensure_codigo_col(snap, source="index")
    return snap


@st.cache_data(ttl=TTL_MKT, show_spinner=False)
def _load_curve_base(username: str, password: str, curve_key: str, plazo: str) -> Optional[pd.DataFrame]:
    """
    Carga y prepara el snapshot base para una curva.
    Retorna DataFrame con 'Código' ya mapeado (sufijo j/v si aplica), o None.
    OPTIMIZADO: extrae de _global_snapshot en lugar de hacer fetch independiente.
    """
    curves = build_curve_codes()
    codes = curves.get(curve_key, [])
    if not codes:
        return None

    calc_codes = [str(x) for x in codes]
    md_codes = [_md_code_from_calc_code(c) for c in calc_codes]

    # mapping md -> calc (si hay colisión, mantiene el primero)
    md_to_calc: Dict[str, str] = {}
    for cc, md in zip(calc_codes, md_codes):
        md_to_calc.setdefault(md, cc)

    # Use global snapshot instead of per-curve fetch
    snap = _global_snapshot(username, password, plazo)
    if snap is None or snap.empty:
        return None

    snap = snap[snap["Código"].isin(set(md_codes))].copy()

    if snap.empty:
        return None

    # Re-etiquetar a calc_code SOLO para curvas con sufijo
    if curve_key in CURVE_EVAL_SUFFIX:
        snap["Código"] = snap["Código"].map(lambda x: md_to_calc.get(str(x), str(x)))

    return snap


@st.cache_data(ttl=TTL_METRICS, show_spinner=False)
def load_curve_last_table(username: str, password: str, curve_key: str, plazo: str) -> pd.DataFrame:
    snap = _load_curve_base(username, password, curve_key, plazo)
    if snap is None or snap.empty:
        return pd.DataFrame()

    snap = snap.rename(columns={"close": "Close", "last": "Last", "variation": "Variación %", "volume": "Volumen"})

    bond_type = next((c.bond_type for c in CURVES if c.key == curve_key), "lecap")
    settle = _settlement_date_str(plazo)

    codes_arr = snap["Código"].astype(str).to_numpy()
    last_arr = pd.to_numeric(snap["Last"], errors="coerce").to_numpy(dtype="float64")

    mdf = _parallel_metrics(codes_arr, last_arr, bond_type, settle)

    out = pd.concat([snap.reset_index(drop=True), mdf], axis=1)
    out = _sort_duration_nan_last(out, "Duration")

    out["tem_spread"] = pd.to_numeric(out.get("TEM"), errors="coerce").diff().fillna(0.0)

    cols = [
        "Código",
        "Close",
        "Last",
        "Variación %",
        "TIREA",
        "TNA",
        "TEM",
        "Paridad",
        "Duration",
        "tem_spread",
        "Volumen",
    ]
    cols = [c for c in cols if c in out.columns]
    return out[cols].copy()


@st.cache_data(ttl=TTL_METRICS, show_spinner=False)
def load_curve_market_table(username: str, password: str, curve_key: str, plazo: str) -> pd.DataFrame:
    """Tabla Mercado: incluye OLH + book + TIRs."""
    snap = _load_curve_base(username, password, curve_key, plazo)
    if snap is None or snap.empty:
        return pd.DataFrame()

    snap = snap.rename(
        columns={
            "open": "Open",
            "close": "Close",
            "low": "Low",
            "high": "High",
            "last": "Last Price",
            "variation": "Variación %",
            "change": "Variación px",
            "bid_size": "Bid Size",
            "bid_price": "Bid Price",
            "offer_price": "Offer Price",
            "offer_size": "Offer Size",
            "volume": "Volumen",
        }
    )

    bond_type = next((c.bond_type for c in CURVES if c.key == curve_key), "lecap")
    settle = _settlement_date_str(plazo)

    codes_arr = snap["Código"].astype(str).to_numpy()
    last_arr = pd.to_numeric(snap["Last Price"], errors="coerce").to_numpy(dtype="float64")
    m_last_df = _parallel_metrics(codes_arr, last_arr, bond_type, settle)

    bid_arr = pd.to_numeric(snap.get("Bid Price"), errors="coerce").to_numpy(dtype="float64") if "Bid Price" in snap.columns else np.full(len(snap), np.nan)
    off_arr = pd.to_numeric(snap.get("Offer Price"), errors="coerce").to_numpy(dtype="float64") if "Offer Price" in snap.columns else np.full(len(snap), np.nan)

    bid_tir = _parallel_tirea(codes_arr, bid_arr, settle)
    off_tir = _parallel_tirea(codes_arr, off_arr, settle)

    out = pd.concat([snap.reset_index(drop=True), m_last_df], axis=1)
    out["Bid TIREA"] = bid_tir
    out["Offer TIREA"] = off_tir

    cols = [
        "Código",
        "Open",
        "Close",
        "Low",
        "High",
        "Variación %",
        "Variación px",
        "Bid Size",
        "Bid Price",
        "Bid TIREA",
        "Last Price",
        "TIREA",
        "Duration",
        "Offer Price",
        "Offer TIREA",
        "Offer Size",
        "Volumen",
    ]
    cols = [c for c in cols if c in out.columns]
    out = out[cols].copy()

    out = _sort_duration_nan_last(out, "Duration")
    return out


# ──────────────────────────────────────────────────────────────────────
# Estilos (pandas Styler) — unificados
# ──────────────────────────────────────────────────────────────────────

def _apply_variation_bar(sty: "pd.io.formats.style.Styler", df: pd.DataFrame, col: str) -> "pd.io.formats.style.Styler":
    """Aplica barra divergente verde/rojo + fondo a una columna de variación."""
    if col not in df.columns:
        return sty
    vmin, vmax = _bar_limits(df[col])
    lim = max(abs(vmin), abs(vmax))
    sty = sty.bar(subset=[col], align="mid", color=["#fa7a7a", "#8bf58b"], vmin=vmin, vmax=vmax)
    sty = sty.map(lambda x: _diverging_bg(x, lim), subset=[col])
    return sty


def _apply_color_by_variation(sty: "pd.io.formats.style.Styler", df: pd.DataFrame, var_col: str, target_col: str) -> "pd.io.formats.style.Styler":
    """Colorea target_col en verde/rojo según el signo de var_col."""
    if var_col not in df.columns or target_col not in df.columns:
        return sty

    def _color_row(row):
        v = row.get(var_col)
        if pd.isna(v):
            return [""] * len(row)
        col = (
            "color: #1b8a3a; font-weight: 800;"
            if v > 0 else
            "color: #b02a37; font-weight: 800;"
            if v < 0 else
            ""
        )
        styles = [""] * len(row)
        try:
            idx = list(row.index).index(target_col)
            styles[idx] = col
        except Exception:
            pass
        return styles

    sty = sty.apply(_color_row, axis=1)
    return sty


def style_curvas(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Close": "{:,.2f}",
        "Last": "{:,.2f}",
        "Variación %": "{:+.2%}",
        "TIREA": "{:.2%}",
        "TNA": "{:.2%}",
        "TEM": "{:.2%}",
        "Paridad": "{:.2%}",
        "Duration": "{:.2f}",
        "tem_spread": "{:+.2%}",
        "Volumen": "{:,.0f}",
    }

    sty = df.style.format(fmt)
    sty = _apply_variation_bar(sty, df, "Variación %")

    if "tem_spread" in df.columns:
        v = pd.to_numeric(df["tem_spread"], errors="coerce")
        lim2 = float(np.nanmax(np.abs(v.to_numpy(dtype="float64")))) if len(v) else 0.0
        if not np.isfinite(lim2) or lim2 <= 0:
            lim2 = 1.0
        sty = sty.map(lambda x: _diverging_bg(x, lim2, bold=False), subset=["tem_spread"])

    sty = _apply_color_by_variation(sty, df, "Variación %", "Last")
    _navy_hdr = [
        {"selector": "thead tr th", "props": "background-color: #1B3A6B; color: #FFFFFF; font-size: 11px; font-weight: 600; padding: 5px 8px; text-align: center; border-bottom: 2px solid #2ECC71;"},
        {"selector": "tbody tr:nth-child(even) td", "props": "background-color: rgba(27,58,107,0.05);"},
        {"selector": "td", "props": "font-size: 11px; padding: 3px 6px;"},
    ]
    sty = sty.set_table_styles(_navy_hdr, overwrite=False)
    return sty


def style_mercado(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Open": "{:,.2f}",
        "Close": "{:,.2f}",
        "Low": "{:,.2f}",
        "High": "{:,.2f}",
        "Bid Size": "{:,.0f}",
        "Bid Price": "{:,.2f}",
        "Bid TIREA": "{:.2%}",
        "Last Price": "{:,.2f}",
        "TIREA": "{:.2%}",
        "Duration": "{:.2f}",
        "Offer Price": "{:,.2f}",
        "Offer TIREA": "{:.2%}",
        "Offer Size": "{:,.0f}",
        "Volumen": "{:,.0f}",
        "Variación %": "{:+.2%}",
        "Variación px": "{:+.2f}",
    }

    sty = df.style.format(fmt)
    sty = _apply_variation_bar(sty, df, "Variación %")
    sty = _apply_variation_bar(sty, df, "Variación px")
    sty = _apply_color_by_variation(sty, df, "Variación %", "Last Price")

    table_styles = []
    if "Bid Size" in df.columns:
        j = df.columns.get_loc("Bid Size")
        table_styles.append({"selector": f"th.col{j}", "props": "border-left: 3px solid #444;"})
        table_styles.append({"selector": f"td.col{j}", "props": "border-left: 3px solid #444;"})
    if "Volumen" in df.columns:
        j = df.columns.get_loc("Volumen")
        table_styles.append({"selector": f"th.col{j}", "props": "border-left: 3px solid #444;"})
        table_styles.append({"selector": f"td.col{j}", "props": "border-left: 3px solid #444;"})
    if table_styles:
        sty = sty.set_table_styles(table_styles, overwrite=False)
    _navy_hdr_m = [
        {"selector": "thead tr th", "props": "background-color: #1B3A6B; color: #FFFFFF; font-size: 11px; font-weight: 600; padding: 5px 8px; text-align: center; border-bottom: 2px solid #2ECC71;"},
        {"selector": "tbody tr:nth-child(even) td", "props": "background-color: rgba(27,58,107,0.05);"},
        {"selector": "td", "props": "font-size: 11px; padding: 3px 6px;"},
    ]
    sty = sty.set_table_styles(_navy_hdr_m, overwrite=False)
    return sty


def style_forwards(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style
    sty = df.style.format("{:.2f}%")
    try:
        sty = sty.background_gradient(cmap="Blues", axis=None)
    except Exception:
        pass
    return sty


def style_total_return(df: pd.DataFrame, tr_col: str = "_tr_num") -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style

    if tr_col not in df.columns:
        return df.style  # no rompas si cambió el nombre

    tr_lim = float(np.nanmax(np.abs(pd.to_numeric(df[tr_col], errors="coerce").to_numpy(dtype="float64"))))
    if not np.isfinite(tr_lim) or tr_lim <= 0:
        tr_lim = 0.01

    fmt = {
        "Duration": "{:.4f}",
        "Px inicial": "{:,.4f}",
        "Px final": "{:,.4f}",
        "Cupones cobrados": "{:,.4f}",
        "P&L Capital": "{:,.4f}",
        "TIREA inicial": "{:.2%}",
        "TIREA final": "{:.2%}",
        tr_col: "{:+.2%}",
    }

    sty = df.style.format(fmt)

    sty = sty.bar(
        subset=[tr_col],
        align="mid",
        color=["#fa7a7a", "#8bf58b"],
        vmin=-tr_lim,
        vmax=tr_lim,
    )
    sty = sty.map(lambda x: _diverging_bg(x, tr_lim), subset=[tr_col])
    sty = _apply_color_by_variation(sty, df, tr_col, tr_col)

    return sty


def style_futuros(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Estilo para tabla de futuros DLR."""
    fmt = {
        "Close Price": "{:,.4f}",
        "Last Price": "{:,.4f}",
        "Variación": "{:+.2%}",
        "Dias Vto": "{:,.0f}",
        "Tasa Directa": "{:+.2%}",
        "TNA": "{:.2%}",
        "TEA": "{:.2%}",
    }
    sty = df.style.format(fmt)
    sty = _apply_variation_bar(sty, df, "Variación")
    return sty


# ──────────────────────────────────────────────────────────────────────
# Forwards
# ──────────────────────────────────────────────────────────────────────

def maturity_map_for_codes(codes: Iterable[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for c in codes:
        obj = _bond_obj(c)
        if obj is not None and hasattr(obj, "vencimiento"):
            out[str(c)] = getattr(obj, "vencimiento")
    return out


def forwards_matrix(df_curve: pd.DataFrame) -> pd.DataFrame:
    if df_curve is None or df_curve.empty:
        return pd.DataFrame()
    if "Código" not in df_curve.columns or "TIREA" not in df_curve.columns or "Duration" not in df_curve.columns:
        return pd.DataFrame()

    fwd = plotter.matriz_forwards_tir(
        df_curve[["Código", "TIREA", "Duration"]].copy(),
        y_col="TIREA",
        code_col="Código",
        comp="ea",
        t_col="Duration",
    )
    return fwd



# ──────────────────────────────────────────────────────────────────────
# Gráficos (Plotly)
# ──────────────────────────────────────────────────────────────────────

def plot_curve_plotly(
    df_curve_last: pd.DataFrame,
    df_curve_mkt: Optional[pd.DataFrame] = None,
    title: str = "Curva",
    show_nss: bool = True,
    threshold_factor: float = 2.0,
    which: str = "TIREA",  # "TIREA" o "TEM"
) -> Tuple[Optional["go.Figure"], Optional[np.ndarray]]:
    """Devuelve figura Plotly y params NSS (si aplica)."""
    if go is None:
        return None, None

    which = (which or "TIREA").upper()
    if which not in ("TIREA", "TEM"):
        which = "TIREA"

    if df_curve_last is None or df_curve_last.empty:
        fig = go.Figure()
        fig.update_layout(title=title)
        return fig, None

    df = df_curve_last.copy()
    if "Duration" not in df.columns or which not in df.columns:
        fig = go.Figure()
        fig.update_layout(title=title)
        return fig, None

    y_last_pct = _yield_pct_points(df[which])  # puntos porcentuales

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["Duration"],
            y=y_last_pct,
            mode="markers",
            name=f"LAST ({which})",
            text=df.get("Código"),
            hovertemplate="%{text}<br>Dur=%{x:.3f}<br>Yield=%{y:.2f}%<extra></extra>",
        )
    )

    if df_curve_mkt is not None and not df_curve_mkt.empty and "Duration" in df_curve_mkt.columns:
        m = df_curve_mkt.copy()

        def _tem_from_tirea_decimal(tirea_dec: pd.Series) -> pd.Series:
            t = pd.to_numeric(tirea_dec, errors="coerce")
            return (1.0 + t) ** (30.0 / 360.0) - 1.0

        if "Bid TIREA" in m.columns:
            bid_dec = pd.to_numeric(m["Bid TIREA"], errors="coerce")
            bid_series = bid_dec if which == "TIREA" else _tem_from_tirea_decimal(bid_dec)
            bid_pct = _yield_pct_points(bid_series)
            fig.add_trace(
                go.Scatter(
                    x=m["Duration"],
                    y=bid_pct,
                    mode="markers",
                    name=f"BID ({which})",
                    text=m.get("Código"),
                    hovertemplate="%{text}<br>Dur=%{x:.3f}<br>Bid=%{y:.2f}%<extra></extra>",
                )
            )

        if "Offer TIREA" in m.columns:
            off_dec = pd.to_numeric(m["Offer TIREA"], errors="coerce")
            off_series = off_dec if which == "TIREA" else _tem_from_tirea_decimal(off_dec)
            off_pct = _yield_pct_points(off_series)
            fig.add_trace(
                go.Scatter(
                    x=m["Duration"],
                    y=off_pct,
                    mode="markers",
                    name=f"OFFER ({which})",
                    text=m.get("Código"),
                    hovertemplate="%{text}<br>Dur=%{x:.3f}<br>Offer=%{y:.2f}%<extra></extra>",
                )
            )

    popt = None
    if show_nss:
        try:
            tmp = df[["Código", "Duration", "TIREA", "TEM"]].copy()
            popt, x_min, x_max = plotter._fit_nss_cached(
                tmp,
                which=which,
                threshold_factor=float(threshold_factor),
                use_cache=False,
            )

            npts = int(df[["Duration", which]].dropna().shape[0])
            if npts < 6 and popt is not None and len(popt) >= 4 and abs(float(popt[3])) < 1e-12:
                _warn_once(
                    f"ns_fallback::graficos::{title}",
                    "Curva con pocos puntos: ajustando con fallback Nelson–Siegel (β3=0).",
                )

            xs = np.linspace(float(x_min), float(x_max), 160)
            ys_pct = plotter.nss_model(xs, *popt)  # ya devuelve % puntos
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys_pct,
                    mode="lines",
                    name=f"NSS fit ({which})",
                    hovertemplate="Dur=%{x:.3f}<br>NSS=%{y:.2f}%<extra></extra>",
                )
            )
        except Exception as e:
            popt = None
            _warn_once(f"nss_fail::graficos::{title}", f"No se pudo ajustar NSS/NS: {e}")

    fig.update_layout(
        title=title,
        xaxis_title="Duration",
        yaxis_title=f"{which} (%)",
        hovermode="closest",
        legend_orientation="h",
        legend_yanchor="bottom",
        legend_y=1.02,
        legend_xanchor="left",
        legend_x=0,
        margin=dict(l=10, r=10, t=60, b=10),
        height=520,
    )

    return fig, popt


# ──────────────────────────────────────────────────────────────────────
# Total Return (escenario)
# ──────────────────────────────────────────────────────────────────────

def _scenario_curve_params(durations: np.ndarray, level_pct: float, slope_bps: float, convex_bps: float, anchor: float = 1.0) -> np.ndarray:
    """Devuelve TIREA final (decimal) por duration."""
    x = durations.astype("float64")
    dx = x - float(anchor)

    level = float(level_pct) / 100.0
    slope = float(slope_bps) / 10000.0
    convex = float(convex_bps) / 10000.0

    y = level + slope * dx + convex * (dx ** 2)
    y = np.clip(y, -0.99, 5.0)
    return y


def _scenario_curve_points(durations: np.ndarray, pts: pd.DataFrame) -> np.ndarray:
    """Interpolación lineal sobre puntos (Duration, TIREA%)."""
    if pts is None or pts.empty:
        return np.full_like(durations, np.nan, dtype="float64")
    if "Duration" not in pts.columns or "TIREA %" not in pts.columns:
        return np.full_like(durations, np.nan, dtype="float64")

    x = pd.to_numeric(pts["Duration"], errors="coerce").to_numpy(dtype="float64")
    y_pct = pd.to_numeric(pts["TIREA %"], errors="coerce").to_numpy(dtype="float64")

    m = np.isfinite(x) & np.isfinite(y_pct)
    x = x[m]
    y = y_pct[m] / 100.0

    if len(x) < 2:
        return np.full_like(durations, np.nan, dtype="float64")

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    return np.interp(durations.astype("float64"), x, y, left=y[0], right=y[-1])


def _pct_str_to_dec(x: Any) -> float:
    """'12.345600%' -> 0.123456  | si ya es float, lo devuelve."""
    if x is None:
        return float("nan")
    if isinstance(x, (int, float, np.floating)):
        return float(x)
    try:
        s = str(x).strip().replace(",", ".")
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        return float(s)
    except Exception:
        return float("nan")


def compute_total_return_table(
    df_curve_last: pd.DataFrame,
    plazo: str,
    terminal_date: date,
    scenario_y: np.ndarray
) -> pd.DataFrame:
    """Aplica calcula_total_return por bono y devuelve tabla horizontal."""
    if df_curve_last is None or df_curve_last.empty:
        return pd.DataFrame()

    settle = _settlement_date_str(plazo)
    term_str = terminal_date.strftime("%d/%m/%Y")

    out_rows = []
    df_in = df_curve_last.reset_index(drop=True)

    for i, row in df_in.iterrows():
        code = str(row.get("Código", "")).strip()
        dur = row.get("Duration")
        y0 = row.get("TIREA")
        y1 = scenario_y[i] if i < len(scenario_y) else np.nan

        if not code or not np.isfinite(y0) or not np.isfinite(y1):
            continue

        bond_obj = _bond_obj(code)
        if bond_obj is None or not hasattr(bond_obj, "calcula_total_return"):
            continue

        try:
            tr_v = bond_obj.calcula_total_return(float(y0), float(y1), term_str, settle)

            def _get(name: str):
                try:
                    return tr_v.loc[name, "Total Return Valores"]
                except Exception:
                    return np.nan

            px0 = _get("Px inicial")
            px1 = _get("Px final")
            cpn = _get("Cupones Cobrados")
            pnl_cap = _get("P&L Capital")
            tr = _get("Total Return")
            inv = _get("Inverse P&L")

            # FIX conversión robusta (evita float("1,234") / strings raros)
            px0_n = pd.to_numeric(px0, errors="coerce")
            px1_n = pd.to_numeric(px1, errors="coerce")
            cpn_n = pd.to_numeric(cpn, errors="coerce")
            pnl_n = pd.to_numeric(pnl_cap, errors="coerce")

            out_rows.append(
                {
                    "Código": code,
                    "Duration": dur,
                    "Px inicial": float(px0_n) if np.isfinite(px0_n) else np.nan,
                    "Px final": float(px1_n) if np.isfinite(px1_n) else np.nan,
                    "Cupones cobrados": float(cpn_n) if np.isfinite(cpn_n) else np.nan,
                    "P&L Capital": float(pnl_n) if np.isfinite(pnl_n) else np.nan,
                    "TIREA inicial": float(y0),
                    "TIREA final": float(y1),
                    # guardo numérico para estilo
                    "_tr_num": _pct_str_to_dec(tr),
                    "_inv_num": _pct_str_to_dec(inv),
                }
            )
        except Exception:
            continue

    df_out = pd.DataFrame(out_rows)
    if df_out.empty:
        return df_out

    df_out = _sort_duration_nan_last(df_out, "Duration")
    return df_out


# ──────────────────────────────────────────────────────────────────────
# Breakeven Inflación: CER vs Tasa Fija
# ──────────────────────────────────────────────────────────────────────

def _cer_effective_maturity_date(bond_obj) -> Optional[date]:
    """Fecha en la que el bono CER toma su último índice CER.
    Para bonos CER, el CER se fija ~10 días hábiles antes del vencimiento.
    Eso corresponde a datos del CER de mediados del mes anterior al vencimiento,
    que refleja la inflación de 2 meses antes del vencimiento."""
    if bond_obj is None:
        return None
    venc = getattr(bond_obj, "vencimiento", None)
    lag = getattr(bond_obj, "dias_lag_ajuste", None)
    if venc is None:
        return None
    if lag is not None:
        try:
            from dias_habiles import n_dias_laborales
            return n_dias_laborales(venc, lag)
        except Exception:
            pass
    # Default: -10 business days
    try:
        from dias_habiles import n_dias_laborales
        return n_dias_laborales(venc, -10)
    except Exception:
        return venc


def _inflation_month_for_cer_date(cer_date: date) -> str:
    """Given a CER fixing date, determine which month's inflation is the LAST one
    embedded in that CER value (i.e. the last MOM that the market doesn't know yet
    when pricing today).

    CER publication calendar:
    - CER values from day 16 of month M to day 15 of month M+1
      reflect the MOM inflation of month M-1.
    - Example: CER values from Mar 16 to Apr 15 reflect Feb inflation
      (published ~Mar 12).

    So if the CER fix date falls:
    - Between the 16th and end of month M → that CER incorporates MOM of M-1
    - Between the 1st and 15th of month M → that CER incorporates MOM of M-2
      (because it's in the cycle published from day 16 of M-1 to 15 of M,
       which reflects MOM of M-2)

    The "inflación de referencia" is the LAST inflation month embedded.

    Examples:
    - CER fix = Apr 30 → day >= 16 in Apr → reflects Mar MOM → "Mar-2026"
    - CER fix = May 14 → day < 16 in May → reflects Mar MOM → "Mar-2026"
    - CER fix = Oct 19 → day >= 16 in Oct → reflects Sep MOM → "Sep-2026"
      Wait — Sep MOM gets published ~Oct 12, updates CER from Oct 16.
      So CER on Oct 19 DOES have Sep MOM. ✓
    - CER fix = Sep 16 → day >= 16 in Sep → reflects Aug MOM → "Aug-2026" ✓
    - CER fix = Nov 13 → day < 16 in Nov → reflects Sep MOM → "Sep-2026"
      (cycle Oct16→Nov15 reflects Sep MOM) ✓
    """
    if cer_date.day >= 16:
        # In the cycle that runs from day 16 of this month → reflects MOM of (month - 1)
        ref = cer_date.replace(day=1) - relativedelta(months=1)
    else:
        # In the cycle that runs from day 16 of previous month to day 15 of this month
        # → reflects MOM of (month - 2)
        ref = cer_date.replace(day=1) - relativedelta(months=2)
    return ref.strftime("%b-%Y")


def compute_breakeven_table(
    df_cer_last: pd.DataFrame,
    df_lecap_last: pd.DataFrame,
    plazo: str,
) -> pd.DataFrame:
    """Computes inflation breakeven for each CER bond by matching
    duration against the LECAP/tasa fija curve (NSS interpolated).

    For each CER bond:
    1. Get its TIREA (real yield over CER)
    2. Find the equivalent nominal yield from the LECAP curve at the same duration
    3. breakeven = (1 + nominal) / (1 + real) - 1  (Fisher equation)
    4. Express as TEM and TIREA

    Also accounts for the fact that CER bonds become fixed-rate
    ~10 bdays before maturity (using the CER index from that date).
    """
    if (df_cer_last is None or df_cer_last.empty or
        df_lecap_last is None or df_lecap_last.empty):
        return pd.DataFrame()

    # Need NSS fit on LECAP curve for interpolation
    try:
        tmp_lecap = df_lecap_last[["Código", "Duration", "TIREA", "TEM"]].copy()
        popt_lecap, xmin_l, xmax_l = plotter._fit_nss_cached(
            tmp_lecap, which="TIREA", threshold_factor=2.0, use_cache=False)
    except Exception:
        return pd.DataFrame()

    if popt_lecap is None:
        return pd.DataFrame()

    # Also fit CER curve NSS for interpolation reference
    try:
        tmp_cer = df_cer_last[["Código", "Duration", "TIREA", "TEM"]].copy()
        popt_cer, xmin_c, xmax_c = plotter._fit_nss_cached(
            tmp_cer, which="TIREA", threshold_factor=2.0, use_cache=False)
    except Exception:
        popt_cer = None

    settle = _settlement_date_str(plazo)
    rows = []

    for _, row in df_cer_last.iterrows():
        code = str(row.get("Código", "")).strip()
        dur = row.get("Duration")
        tirea_real = row.get("TIREA")
        tem_real = row.get("TEM")

        if not code or not np.isfinite(dur) or not np.isfinite(tirea_real):
            continue

        bond_obj = _bond_obj(code)
        vencimiento = getattr(bond_obj, "vencimiento", None) if bond_obj else None

        # CER effective maturity: when the CER index is fixed
        cer_eff_date = _cer_effective_maturity_date(bond_obj)
        infla_month = _inflation_month_for_cer_date(cer_eff_date) if cer_eff_date else "—"

        # Interpolate nominal yield from LECAP NSS at this duration
        dur_clipped = np.clip(float(dur), float(xmin_l), float(xmax_l))
        nominal_yield_pct = float(plotter.nss_model(np.array([dur_clipped]), *popt_lecap)[0])
        nominal_yield = nominal_yield_pct / 100.0  # decimal

        # Fisher equation: (1 + nominal) = (1 + real) * (1 + breakeven)
        # => breakeven = (1 + nominal) / (1 + real) - 1
        if np.isfinite(nominal_yield) and np.isfinite(tirea_real):
            be_tirea = (1.0 + nominal_yield) / (1.0 + tirea_real) - 1.0
            be_tem = (1.0 + be_tirea) ** (30.0 / 360.0) - 1.0
        else:
            be_tirea = np.nan
            be_tem = np.nan

        # Days to CER fixing vs maturity
        today = date.today()
        days_to_mat = (vencimiento - today).days if vencimiento else np.nan
        days_to_cer_fix = (cer_eff_date - today).days if cer_eff_date else np.nan
        # "Fija desde" = period from CER fixing to maturity where the bond is effectively fixed rate
        days_fixed = (days_to_mat - days_to_cer_fix) if (np.isfinite(days_to_mat or np.nan) and np.isfinite(days_to_cer_fix or np.nan)) else np.nan

        rows.append({
            "Código": code,
            "Vencimiento": vencimiento,
            "Duration": dur,
            "TIREA CER (real)": tirea_real,
            "TEM CER (real)": tem_real if np.isfinite(tem_real) else np.nan,
            "TIREA Nominal (NSS)": nominal_yield,
            "TEM Nominal (NSS)": (1.0 + nominal_yield) ** (30.0 / 360.0) - 1.0 if np.isfinite(nominal_yield) else np.nan,
            "BE TIREA": be_tirea,
            "BE TEM": be_tem,
            "Fecha CER Fix": cer_eff_date,
            "Días a CER Fix": days_to_cer_fix,
            "Inflación ref.": infla_month,
            "Días fija": days_fixed,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = _sort_duration_nan_last(df, "Duration")
    return df


def style_breakeven(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Duration": "{:.4f}",
        "TIREA CER (real)": "{:.2%}",
        "TEM CER (real)": "{:.2%}",
        "TIREA Nominal (NSS)": "{:.2%}",
        "TEM Nominal (NSS)": "{:.2%}",
        "BE TIREA": "{:.2%}",
        "BE TEM": "{:.2%}",
        "Días a CER Fix": "{:.0f}",
        "Días fija": "{:.0f}",
    }

    sty = df.style.format(fmt)

    # Highlight breakeven columns
    if "BE TEM" in df.columns:
        be_vals = pd.to_numeric(df["BE TEM"], errors="coerce")
        lim = float(np.nanmax(np.abs(be_vals.to_numpy(dtype="float64")))) if len(be_vals) else 0.01
        if not np.isfinite(lim) or lim <= 0:
            lim = 0.01
        sty = sty.background_gradient(subset=["BE TEM"], cmap="YlOrRd", vmin=0, vmax=lim * 1.2)

    if "BE TIREA" in df.columns:
        sty = sty.background_gradient(subset=["BE TIREA"], cmap="YlOrRd")

    return sty


# ──────────────────────────────────────────────────────────────────────
# Futuros DLR: generación dinámica de símbolos
# ──────────────────────────────────────────────────────────────────────

_MESES_3L = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_MESES_INV = {v: k for k, v in _MESES_3L.items()}


def _generate_futures_symbols(n_months: int = 18) -> List[str]:
    """Genera los próximos n_months símbolos DLR/MMMYY dinámicamente."""
    base = date.today().replace(day=1)
    symbols = []
    for i in range(n_months):
        d = base + relativedelta(months=i)
        mmm = _MESES_INV[d.month]
        yy = d.strftime("%y")
        symbols.append(f"DLR/{mmm}{yy}")
    return symbols


def _parsear_vencimiento_futuro(code: str) -> Optional[date]:
    """Parsea 'DLR/FEB26' o 'DLR/FEB26A' → último día hábil del mes."""
    if not isinstance(code, str):
        return None
    m = re.match(r"^DLR/([A-Z]{3})(\d{2})([A-Z]*)$", code.strip().upper())
    if not m:
        return None
    mes_abbr, yy, _suf = m.groups()
    mes = _MESES_3L.get(mes_abbr)
    if mes is None:
        return None
    year = 2000 + int(yy)
    first_day = pd.Timestamp(year=year, month=mes, day=1)
    last_day = first_day + MonthEnd(0)
    return siguiente_dia_habil_ar(last_day.date())


# ──────────────────────────────────────────────────────────────────────
# Theme: Bloomberg dark mode (CSS injection — zero overhead en Python)
# ──────────────────────────────────────────────────────────────────────

_BLOOMBERG_CSS = """
<style>
/* ── Bloomberg Terminal Dark Theme ── */

/* Main background */
.stApp, [data-testid="stAppViewContainer"] {
    background-color: #0d1117 !important;
    color: #e6e6e6 !important;
}

/* Sidebar */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background-color: #161b22 !important;
    color: #e6e6e6 !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] p {
    color: #e6e6e6 !important;
}

/* Headers */
h1, h2, h3, h4, h5, h6,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    color: #ff9800 !important;
}

/* Tabs */
[data-testid="stTabs"] button {
    color: #8b949e !important;
    background-color: transparent !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #ff9800 !important;
    border-bottom: 2px solid #ff9800 !important;
}
[data-testid="stTabs"] button:hover {
    color: #ffb74d !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    padding: 8px 12px !important;
}
[data-testid="stMetric"] label {
    color: #8b949e !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #ff9800 !important;
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    color: #8b949e !important;
}

/* DataFrames / tables */
[data-testid="stDataFrame"], .stDataFrame {
    border: 1px solid #30363d !important;
}

/* Inputs */
input, select, textarea,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
.stSelectbox > div > div {
    background-color: #161b22 !important;
    color: #e6e6e6 !important;
    border-color: #30363d !important;
}

/* Primary buttons */
.stButton > button[kind="primary"],
.stButton > button {
    background-color: #ff9800 !important;
    color: #0d1117 !important;
    border: none !important;
    font-weight: 700 !important;
}
.stButton > button:hover {
    background-color: #ffb74d !important;
}

/* Expanders */
[data-testid="stExpander"] {
    border-color: #30363d !important;
    background-color: #161b22 !important;
}
[data-testid="stExpander"] summary span {
    color: #ff9800 !important;
}

/* Captions and labels */
.stCaption, .stMarkdown small, figcaption {
    color: #8b949e !important;
}

/* Info / Warning / Error boxes */
[data-testid="stAlert"] {
    background-color: #161b22 !important;
    border-color: #30363d !important;
    color: #e6e6e6 !important;
}

/* Dividers */
hr {
    border-color: #30363d !important;
}

/* Radio / Toggle / Checkbox labels */
[data-testid="stRadio"] label,
.stCheckbox label {
    color: #e6e6e6 !important;
}
[data-testid="stSlider"] label {
    color: #e6e6e6 !important;
}
.stNumberInput label, .stSelectbox label, .stTextInput label {
    color: #e6e6e6 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #161b22; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #484f58; }
</style>
"""


def _inject_theme(dark: bool) -> None:
    """Inyecta CSS Bloomberg dark o no hace nada (light = default Streamlit)."""
    if dark:
        st.markdown(_BLOOMBERG_CSS, unsafe_allow_html=True)


def _plotly_theme(fig, dark: bool) -> None:
    """Aplica template dark a figura Plotly si Bloomberg mode está activo."""
    if not dark or fig is None:
        return
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font_color="#e6e6e6",
        title_font_color="#ff9800",
        legend_font_color="#e6e6e6",
        xaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
        yaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    )


def _st_plotly(fig) -> None:
    """Renderiza plotly chart con theme automático según session_state."""
    _plotly_theme(fig, st.session_state.get("bbg_theme", False))
    st.plotly_chart(fig, width="stretch")


# ──────────────────────────────────────────────────────────────────────
# Sidebar: datos BCRA / macro
# ──────────────────────────────────────────────────────────────────────

def _render_sidebar_macro():
    """Muestra variables macro (BCRA) en el sidebar sin dtype."""
    inp = rentafija.inputs
    if not isinstance(inp, dict):
        return

    st.sidebar.divider()
    st.sidebar.header("📊 Variables macro")

    def _last_val(key: str, col: str):
        df = inp.get(key)
        if df is None or df.empty:
            return None, None
        row = df.iloc[-1]
        fecha = df.index[-1]
        val = row[col] if col in row.index else row.iloc[0]
        return fecha, val

    # A3500
    f, v = _last_val("a3500", "tca3500")
    if v is not None:
        st.sidebar.metric("A3500 (mayorista)", f"{v:,.2f}", delta=f"al {f}")

    # Badlar
    f, v = _last_val("badlar", "BADLAR")
    if v is not None:
        st.sidebar.metric("Badlar", f"{v:.4f}%", delta=f"al {f}")

    # Tamar
    f, v = _last_val("tamar", "TAMAR")
    tamar_5d = tamar_10d = tamar_tem = None
    if v is not None:
        st.sidebar.metric("Tamar", f"{v:.4f}%", delta=f"al {f}")
        df_t = inp.get("tamar")
        if df_t is not None and len(df_t) >= 5:
            tamar_5d = df_t.tail(5)["TAMAR"].mean()
            tamar_10d = df_t.tail(10)["TAMAR"].mean()
            tamar_tem = 100 * (((1 + ((tamar_10d / 100) / (365 / 32))) ** (365 / 32)) ** (1 / 12) - 1)
            st.sidebar.caption(
                f"Tamar 5d: {tamar_5d:.4f}% · "
                f"10d: {tamar_10d:.4f}% · "
                f"TEM 10d: {tamar_tem:.2f}%"
            )

    # CER
    f, v = _last_val("CER", "CER")
    if v is not None:
        st.sidebar.metric("CER", f"{v:,.5f}", delta=f"al {f}")

    # Inflación MOM — último dato observado (no proyectado)
    df_inflam = inp.get("inflamom")
    if df_inflam is not None and not df_inflam.empty and "inflacionmom" in df_inflam.columns:
        # inflamom es hist+proy (combine_first). Filtramos solo fechas <= hoy
        # y descartamos meses futuros (proyección). El dato BCRA real siempre
        # tiene fecha = último día del mes observado, anterior al mes en curso.
        hoy = date.today()
        primer_dia_mes = hoy.replace(day=1)
        obs = df_inflam[df_inflam.index < primer_dia_mes]
        if not obs.empty:
            f_inf = obs.index[-1]
            v_inf = obs.iloc[-1]["inflacionmom"]
            st.sidebar.metric("Inflación MOM (obs.)", f"{v_inf:.1f}%", delta=f"al {f_inf}")

    # UVA
    f, v = _last_val("UVA", "UVA")
    if v is not None:
        st.sidebar.metric("UVA", f"{v:,.2f}", delta=f"al {f}")


# ──────────────────────────────────────────────────────────────────────
# Análisis de Yields (YAS-style) — genera ticket unificado
# ──────────────────────────────────────────────────────────────────────

def _all_bond_codes() -> List[str]:
    """Lista de todos los códigos de bonos disponibles, incluyendo variantes j/v."""
    bonos = list(todos_los_bonos) if isinstance(todos_los_bonos, (list, tuple)) else []
    base_codes = {_codigo_obj(b) for b in bonos}

    # Agregar variantes con sufijo de las curvas (ej TX26j, TTJ26v)
    curves = build_curve_codes()
    all_codes = set(base_codes)
    for codes in curves.values():
        all_codes.update(codes)

    return sorted(all_codes)


def _ticket_raw(code: str, mode: str, value: float, nominales: int,
                settle: Optional[str], tc: Optional[float] = None) -> Optional[pd.DataFrame]:
    """
    Ejecuta genera_ticket / genera_ticket_tir / genera_ticket_tna / genera_ticket_tna_margen
    y devuelve el DataFrame crudo (sin formateo pesado — trabajamos con los numéricos internos).
    mode: 'precio' | 'tir' | 'tna' | 'margen'
    """
    obj = _bond_obj(code)
    if obj is None:
        return None
    try:
        if mode == "precio":
            return obj.genera_ticket(value / 100.0 , nominales, settle, tc)
        elif mode == "tir":
            return obj.genera_ticket_tir(value, nominales, settle, tc)
        elif mode == "tna":
            return obj.genera_ticket_tna(value, nominales, settle, tc)
        elif mode == "margen":
            return obj.genera_ticket_tna_margen(value, nominales, settle)
        return None
    except Exception as e:
        st.error(f"Error calculando ticket para {code}: {e}")
        return None


def _ticket_numeric(code: str, mode: str, value: float,
                    settle: Optional[str], tc: Optional[float] = None) -> Dict[str, Any]:
    """
    Devuelve dict con métricas numéricas crudas (no formateadas) para display YAS.
    """
    obj = _bond_obj(code)
    if obj is None:
        return {}
    try:
        if mode == "precio":
            # value ya viene en la escala de calcula_tirea (ej 100 = par para VN=100)
            obj.calcula_tirea(value / 100.0, settle)
            obj.calcula_intereses_corridos(settle)
        elif mode == "tir":
            precio_pct = obj.calcula_precio(value, settle) * 100.0
            obj.calcula_intereses_corridos(settle)
        elif mode == "tna":
            cnv = (obj.vencimiento - obj.fecha_settlement).days if obj.cnv_tna == 'plazo remanente' else obj.cnv_tna
            tir = tna_a_tir(value, int(cnv), int(obj.convencion_base))
            precio_pct = obj.calcula_precio(tir, settle) * 100.0
            obj.calcula_intereses_corridos(settle)
        elif mode == "margen":
            inp = rentafija.inputs
            idx = getattr(obj, "index", None)
            if idx == "BADLAR":
                ajuste = inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean()
            elif idx == "TAMAR":
                ajuste = inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean()
            else:
                ajuste = 0.0
            tna_total = (ajuste / 100.0) + value
            cnv = (obj.vencimiento - obj.fecha_settlement).days if obj.cnv_tna == 'plazo remanente' else obj.cnv_tna
            tir = tna_a_tir(tna_total, int(cnv), int(obj.convencion_base))
            precio_pct = obj.calcula_precio(tir, settle) * 100.0
            obj.calcula_intereses_corridos(settle)
        else:
            return {}

        tirea = getattr(obj, "tirea", np.nan)
        tna = getattr(obj, "tna", np.nan)
        tem = (1 + tirea) ** (30 / 360) - 1 if np.isfinite(tirea) else np.nan
        dur = obj.calcula_duration(tirea, settle) if np.isfinite(tirea) else np.nan
        paridad = getattr(obj, "paridad", np.nan)

        # Margen sobre índice
        margen_tna = np.nan
        idx = getattr(obj, "index", None)
        tipo = getattr(obj, "tipo_tasa_interes", None)
        if tipo in ("VARIABLE", "VARIABLE_CAP") and idx:
            inp = rentafija.inputs
            if idx == "BADLAR":
                ajuste = inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean()
            elif idx == "TAMAR":
                ajuste = inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean()
            else:
                ajuste = 0.0
            if np.isfinite(tna) and np.isfinite(ajuste):
                margen_tna = tna - ajuste / 100.0

        return {
            "Código": code,
            "Nombre": getattr(obj, "nombre_security", code),
            "Vencimiento": getattr(obj, "vencimiento", None),
            "Fecha Liquidación": getattr(obj, "fecha_settlement", None),
            "Precio": getattr(obj, "precio", np.nan),
            "TIREA": tirea,
            "TNA": tna,
            "TEM": tem,
            "Duration": dur,
            "Paridad": paridad,
            "Intereses Corridos": getattr(obj, "intereses_corridos", np.nan),
            "Días Devengados": getattr(obj, "dias_corridos", np.nan),
            "Valor Residual": getattr(obj, "valor_residual", np.nan),
            "Moneda": getattr(obj, "moneda", ""),
            "Index": idx or "",
            "Margen TNA": margen_tna,
            "Callable": getattr(obj, "callable", ""),
            "Calificación": getattr(obj, "calificacion", ""),
        }
    except Exception as e:
        st.error(f"Error en cálculo: {e}")
        return {}


def _find_curve_for_bond(code: str) -> Optional[str]:
    """Busca a qué curva pertenece un código (para superponer en gráfico)."""
    curves = build_curve_codes()
    base = _md_code_from_calc_code(code)
    for curve_key, codes in curves.items():
        md_codes = [_md_code_from_calc_code(c) for c in codes]
        if base in md_codes:
            return curve_key
    return None


# ──────────────────────────────────────────────────────────────────────
# Inflation projection → CER recalculation helpers
# ──────────────────────────────────────────────────────────────────────

def _recalculate_cer_proyectado(new_proy: dict, idx_module=None):
    """Recalculate CER proyectado from scratch using a custom inflation vector
    and inject it into rentafija.inputs so ALL tabs use the new CER.

    This is the critical function: it rebuilds the daily CER series using
    calcular_CER_diario_proyectado() from indices.py and replaces the
    'cer_proyectado', 'inflamom', and 'uva_proyectado' entries in
    rentafija.inputs — which is the global dict that every bond object
    reads when it calls generate_cashflows() with ajuste='CER PROYECTADO'.
    """
    if idx_module is None:
        import indices as idx_module

    inp = rentafija.inputs
    combined_df_cer = inp.get("CER")
    combined_df_inflamom_obs = inp.get("inflamom_observado", inp.get("inflamom"))

    if combined_df_cer is None or combined_df_cer.empty:
        return False

    # Build proyección inflation dataframe from dict
    proy_inf_df = pd.DataFrame(
        list(new_proy.items()), columns=["d", "inflacionmomproy"]
    )
    proy_inf_df["d"] = pd.to_datetime(proy_inf_df["d"], format="%b-%y").dt.strftime("%Y-%m-%d")
    proy_inf_df.set_index("d", inplace=True)
    proy_inf_df.index = (
        pd.to_datetime(proy_inf_df.index)
        .to_period("M")
        .to_timestamp("M")
        .date
    )
    proy_inf_df.rename(columns={"inflacionmomproy": "inflacionmom"}, inplace=True)
    proy_inf_df.index.name = "fecha"
    proy_inf_df.sort_index(inplace=True)

    # Combine observed + projection
    if combined_df_inflamom_obs is not None and not combined_df_inflamom_obs.empty:
        df_inflamom_new = combined_df_inflamom_obs.combine_first(proy_inf_df)
    else:
        df_inflamom_new = proy_inf_df.copy()
    df_inflamom_new.sort_index(inplace=True)

    # Recalculate daily CER
    cer_inicial = combined_df_cer["CER"].iloc[-1]
    fecha_inicial_cer = combined_df_cer.index[-1]
    df_cer_proy_new = idx_module.calcular_CER_diario_proyectado(
        df_inflamom_new, cer_inicial, fecha_inicial_cer,
    )
    cer_completo_new = pd.concat(
        [combined_df_cer.iloc[:-1], df_cer_proy_new], axis=0,
    )

    # Inject into rentafija.inputs — this is what bonds read
    rentafija.inputs["cer_proyectado"] = cer_completo_new
    rentafija.inputs["inflamom"] = df_inflamom_new

    # UVA proyectado from CER
    uva_completo_new = cer_completo_new * 2.5217
    uva_completo_new.columns = ["UVA"]
    rentafija.inputs["uva_proyectado"] = uva_completo_new

    # Also update the module-level dict so future calls to indices.main()
    # would use the new projection (though we bypass main() here)
    idx_module.proyeccion_inflacion_mensual = new_proy

    return True


def _apply_custom_inflation_if_needed():
    """Called on EVERY rerun to re-apply custom inflation from session_state.

    The problem: when Streamlit reruns, Python module cache means
    rentafija.inputs already has the CER from the ORIGINAL indices.main().
    If the user edited inflation, we need to re-inject the custom CER
    into rentafija.inputs on every rerun, BEFORE any tab computes metrics.

    We check st.session_state["_custom_inflation_proy"] — if it exists,
    we recalculate and inject. This is idempotent and fast (~50ms).
    """
    if "_custom_inflation_proy" not in st.session_state:
        return
    custom_proy = st.session_state["_custom_inflation_proy"]
    if not custom_proy:
        return
    _recalculate_cer_proyectado(custom_proy)


# ──────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)

    # ── CRITICAL: apply custom inflation BEFORE any tab computes metrics ──
    # If the user edited inflation in a previous rerun, re-inject the custom
    # CER into rentafija.inputs NOW, before load_curve_last_table() etc.
    _apply_custom_inflation_if_needed()

    # Sidebar: solo conexión + parámetros globales
    with st.sidebar:
        st.header("Conexión")
        default_user = os.getenv("OMS_USER", "")
        default_pass = os.getenv("OMS_PASS", "")

        username = st.text_input("Usuario", value=default_user)
        password = st.text_input("Password", value=default_pass, type="password")

        st.divider()
        st.header("Parámetros globales")
        plazo = st.selectbox("Plazo", options=["24hs", "CI"], index=0 if DEFAULT_PLAZO == "24hs" else 1)
        st.session_state["_plazo_global"] = plazo

        st.divider()
        bloomberg_mode = st.toggle("🖥️ Bloomberg mode", value=False, key="bbg_theme")
        auto_refresh = st.toggle("⚡ Auto-refresh (live)", value=True, key="auto_refresh")
        if auto_refresh:
            refresh_interval = st.slider("Intervalo (seg)", min_value=5, max_value=60,
                                          value=AUTO_REFRESH_SECS, step=5, key="refresh_interval")
        else:
            refresh_interval = None

        if st.button("🔄 Recargar (limpiar cache)"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

    # Inyectar theme (puro CSS, zero overhead Python)
    _inject_theme(bloomberg_mode)

    # Sidebar: datos macro BCRA
    _render_sidebar_macro()

    if not username or not password:
        st.warning("Ingresá usuario y password para conectarte a la API.")
        st.stop()

    curves = build_curve_codes()
    curve_labels = {c.key: c.label for c in CURVES}

    # Navegación: pestañas
    tab_curvas, tab_mercado, tab_curvas_ars, tab_normalizada, tab_curva_nominal, tab_trading, tab_fwds, tab_graficos, tab_futuros, tab_tr, tab_yas, tab_comp, tab_breakeven = st.tabs(
        ["Curvas", "Mercado", "Curvas ARS Real", "Normalizada", "Curva Nominal", "Trading", "Forwards", "Gráficos", "Futuros", "Total Return", "Análisis Yields", "Comparador Yields", "Breakeven Inflación"]
    )

    # ─────────────────────────
    # Curvas (todas juntas) — auto-refresh via st.fragment
    # ─────────────────────────
    with tab_curvas:
        @st.fragment(run_every=refresh_interval)
        def _curvas_live():
            st.caption(f"🔴 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}")
            for c in CURVES:
                if c.key not in curves:
                    continue
                st.subheader(c.label)
                df = load_curve_last_table(username, password, c.key, plazo)
                if df is None or df.empty:
                    st.info("Sin datos (mercado cerrado o sin respuesta de marketdata).")
                else:
                    n_rows = len(df)
                    st.dataframe(style_curvas(df), width="stretch", height=min(38 * n_rows + 40, 800))
        _curvas_live()

    # ─────────────────────────
    # Mercado — auto-refresh
    # ─────────────────────────
    with tab_mercado:
        curve_key_mkt = st.selectbox(
            "Curva",
            options=[c.key for c in CURVES if c.key in curves],
            format_func=lambda k: curve_labels.get(k, k),
            key="mkt_curve",
        )

        @st.fragment(run_every=refresh_interval)
        def _mercado_live():
            st.caption(f"🔴 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}")
            dfm = load_curve_market_table(username, password, curve_key_mkt, plazo)
            if dfm is None or dfm.empty:
                st.info("Sin datos (mercado cerrado o sin respuesta de marketdata).")
            else:
                st.dataframe(style_mercado(dfm), width="stretch", height=680)

        _mercado_live()

    # ─────────────────────────
    # Curvas ARS Real — tab entre Mercado y Forwards
    # ─────────────────────────

    # ── Proyecciones default (del Excel "Proyecciones_para_Claude.xlsx") ──────
    _PROY_FX_DEFAULT: Dict[str, float] = {
        "2026-01-31": 1449.80, "2026-02-28": 1408.63, "2026-03-31": 1436.81,
        "2026-04-30": 1451.17, "2026-05-31": 1436.66, "2026-06-30": 1429.48,
        "2026-07-31": 1465.22, "2026-08-31": 1494.52, "2026-09-30": 1524.41,
        "2026-10-31": 1562.52, "2026-11-30": 1593.77, "2026-12-31": 1609.71,
        "2027-01-31": 1617.76, "2027-02-28": 1630.70, "2027-03-31": 1643.75,
        "2027-04-30": 1648.68, "2027-05-31": 1653.62, "2027-06-30": 1658.58,
        "2027-07-31": 1666.88, "2027-08-31": 1671.88, "2027-09-30": 1683.58,
        "2027-10-31": 1695.37, "2027-11-30": 1707.23, "2027-12-31": 1710.65,
    }
    _PROY_TAMAR_DEFAULT: Dict[str, float] = {
        "2026-01-31": 35.0, "2026-02-28": 32.0, "2026-03-31": 30.0,
        "2026-04-30": 25.0, "2026-05-31": 23.0, "2026-06-30": 23.0,
        "2026-07-31": 25.0, "2026-08-31": 23.0, "2026-09-30": 27.0,
        "2026-10-31": 23.0, "2026-11-30": 23.0, "2026-12-31": 25.0,
        "2027-01-31": 25.0, "2027-02-28": 25.0, "2027-03-31": 25.0,
        "2027-04-30": 25.0, "2027-05-31": 25.0, "2027-06-30": 25.0,
        "2027-07-31": 25.0, "2027-08-31": 25.0, "2027-09-30": 25.0,
        "2027-10-31": 25.0, "2027-11-30": 25.0, "2027-12-31": 25.0,
    }
    _PROY_INFLA_DEFAULT: Dict[str, float] = {
        "Mar-26": 3.1, "Apr-26": 2.6, "May-26": 2.0, "Jun-26": 1.8,
        "Jul-26": 1.5, "Aug-26": 1.3, "Sep-26": 1.3, "Oct-26": 1.3,
        "Nov-26": 1.3, "Dec-26": 1.3, "Jan-27": 1.2, "Feb-27": 1.3,
        "Mar-27": 1.3, "Apr-27": 1.0, "May-27": 0.6, "Jun-27": 0.5,
        "Jul-27": 0.5, "Aug-27": 0.5, "Sep-27": 0.5, "Oct-27": 0.5,
        "Nov-27": 0.5, "Dec-27": 0.5,
    }

    # ── Auto-carga del Excel de proyecciones desde ruta fija ────────────────
    _PROY_EXCEL_PATH = os.path.join(
        "C:\\", "Users", "juan.paolicchi",
        "DELTA ASSET MANAGEMENT S.A",
        "Inversiones - Documentos", "Codes",
        "app_calculadoras_bonos", "Proyecciones_para_Claude.xlsx"
    )

    def _autoload_proyecciones_excel() -> bool:
        """
        Lee el Excel de proyecciones desde la ruta fija al arrancar la app.
        Solo lo hace una vez por sesión (flag 'ars_proy_autoloaded').
        Devuelve True si cargó exitosamente.
        """
        if st.session_state.get("ars_proy_autoloaded"):
            return True
        try:
            if not os.path.exists(_PROY_EXCEL_PATH):
                return False
            df_up = pd.read_excel(_PROY_EXCEL_PATH, header=1)
            df_up.columns = ["fecha", "inflacion_mom", "FX", "TAMAR"]
            df_up["fecha"] = pd.to_datetime(df_up["fecha"])
            new_fx    = {r["fecha"].strftime("%Y-%m-%d"): float(r["FX"])
                         for _, r in df_up.iterrows() if pd.notna(r.get("FX"))}
            new_tamar = {r["fecha"].strftime("%Y-%m-%d"): float(r["TAMAR"])
                         for _, r in df_up.iterrows() if pd.notna(r.get("TAMAR"))}
            new_infla = {}
            for _, r in df_up.iterrows():
                if pd.notna(r.get("inflacion_mom")):
                    lbl = r["fecha"].strftime("%b-%y")
                    v = float(r["inflacion_mom"])
                    new_infla[lbl] = v * 100.0 if v < 1.0 else v
            if new_fx:
                st.session_state["ars_proy_fx"]    = new_fx
            if new_tamar:
                st.session_state["ars_proy_tamar"] = new_tamar
            if new_infla:
                st.session_state["ars_proy_infla"] = new_infla
                st.session_state["_custom_inflation_proy"] = new_infla
                _recalculate_cer_proyectado(new_infla)
            st.session_state["ars_proy_autoloaded"] = True
            return True
        except Exception:
            st.session_state["ars_proy_autoloaded"] = True  # no reintentar si falla
            return False

    # Ejecutar auto-carga al inicio de cada sesión
    _autoload_proyecciones_excel()

    def _interpolar_diario_ars(proyeccion_mensual: Dict[str, float], valor_hoy: float) -> pd.Series:
        hoy_d = date.today()
        fechas_sorted = sorted(proyeccion_mensual.keys())
        puntos = [(hoy_d, valor_hoy)] + [
            (pd.to_datetime(f).date(), proyeccion_mensual[f]) for f in fechas_sorted
        ]
        fecha_fin = puntos[-1][0]
        rango = pd.date_range(hoy_d, fecha_fin, freq="D")
        xs = np.array([(d.date() - hoy_d).days for d in rango], dtype=float)
        xp = np.array([(p[0] - hoy_d).days for p in puntos], dtype=float)
        yp = np.array([p[1] for p in puntos], dtype=float)
        return pd.Series(np.interp(xs, xp, yp), index=rango.date, name="valor")

    def _calcular_cer_proy_ars(proy_infla: Dict[str, float]) -> pd.Series:
        """Recalcula CER proyectado diario desde una proyección de inflación MOM."""
        try:
            import indices as _idx_mod
            df_cer_obs = rentafija.inputs.get("CER")
            if df_cer_obs is None or df_cer_obs.empty:
                return pd.Series(dtype=float)
            cer_inicial = float(df_cer_obs.iloc[-1].iloc[0])
            fecha_inicial = pd.to_datetime(df_cer_obs.index[-1])
            # Armar df inflación con formato que espera calcular_CER_diario_proyectado
            proy_rows = []
            for mes_label, valor in proy_infla.items():
                try:
                    fecha_mes = pd.to_datetime(mes_label, format="%b-%y")
                    fecha_fin_mes = (fecha_mes + pd.offsets.MonthEnd(0)).date()
                    proy_rows.append({"fecha": fecha_fin_mes, "inflacionmom": float(valor)})
                except Exception:
                    pass
            if not proy_rows:
                return pd.Series(dtype=float)
            df_infla_proy = pd.DataFrame(proy_rows).set_index("fecha")
            df_infla_proy.index = pd.to_datetime(df_infla_proy.index)
            # Combinar con histórico
            df_infla_hist = rentafija.inputs.get("inflamom_observado") or rentafija.inputs.get("inflamom")
            if df_infla_hist is not None and not df_infla_hist.empty:
                df_infla_hist = df_infla_hist.copy()
                df_infla_hist.index = pd.to_datetime(df_infla_hist.index)
                df_infla_comb = df_infla_hist.combine_first(df_infla_proy)
            else:
                df_infla_comb = df_infla_proy.copy()
            df_infla_comb.sort_index(inplace=True)
            df_cer_nuevo = _idx_mod.calcular_CER_diario_proyectado(df_infla_comb, cer_inicial, fecha_inicial)
            if df_cer_nuevo is None or df_cer_nuevo.empty:
                return pd.Series(dtype=float)
            s = df_cer_nuevo.iloc[:, 0]
            s.index = pd.to_datetime(s.index).date
            return s
        except Exception as e:
            return pd.Series(dtype=float)

    def _get_cer_proy_ars(proy_infla: Optional[Dict[str, float]] = None) -> pd.Series:
        if proy_infla is not None:
            return _calcular_cer_proy_ars(proy_infla)
        try:
            df = rentafija.inputs.get("cer_proyectado")
            if df is not None and not df.empty:
                s = df.iloc[:, 0].copy()
                s.index = pd.to_datetime(s.index).date
                return s
        except Exception:
            pass
        return pd.Series(dtype=float)

    def _fisher_real_ars(tir_nominal: float, tasa_infla_anual: float) -> float:
        if not np.isfinite(tir_nominal) or not np.isfinite(tasa_infla_anual):
            return float("nan")
        if abs(1.0 + tasa_infla_anual) < 1e-9:
            return float("nan")
        return (1.0 + tir_nominal) / (1.0 + tasa_infla_anual) - 1.0

    def _ref_real_ars(tirea: float, curve_key: str, duration: float,
                      cer_proy: pd.Series, fx_proy: pd.Series, fx_spot: float) -> float:
        if not np.isfinite(tirea) or not np.isfinite(duration) or duration <= 0:
            return float("nan")
        hoy_d = date.today()
        fecha_target = hoy_d + timedelta(days=max(1, int(duration * 365)))
        if curve_key == "cer":
            return tirea
        elif curve_key in ("lecap", "tamar", "dualtamar"):
            if cer_proy.empty:
                return float("nan")
            idx_hoy = cer_proy.index <= hoy_d
            if not idx_hoy.any():
                return float("nan")
            cer_h = float(cer_proy[idx_hoy].iloc[-1])
            idx_fut = cer_proy.index <= fecha_target
            if not idx_fut.any():
                return float("nan")
            cer_f = float(cer_proy[idx_fut].iloc[-1])
            infla_acum = cer_f / cer_h - 1.0
            infla_anual = (1.0 + infla_acum) ** (1.0 / duration) - 1.0
            return _fisher_real_ars(tirea, infla_anual)
        elif curve_key == "dolarlinked":
            if fx_proy.empty or not np.isfinite(fx_spot) or fx_spot <= 0:
                return float("nan")
            idx_fut = fx_proy.index <= fecha_target
            if not idx_fut.any():
                return float("nan")
            fx_f = float(fx_proy[idx_fut].iloc[-1])
            devalu_acum = fx_f / fx_spot - 1.0
            devalu_anual = (1.0 + devalu_acum) ** (1.0 / duration) - 1.0
            return _fisher_real_ars(tirea, devalu_anual)
        return float("nan")

    @st.cache_data(ttl=TTL_METRICS, show_spinner=False)
    def _load_ars_curve_data(username: str, password: str, curve_key: str,
                              eval_suffix: str, plazo: str) -> pd.DataFrame:
        curves = build_curve_codes()
        raw_codes = curves.get(curve_key, [])
        if not raw_codes:
            return pd.DataFrame()
        md_codes   = [_md_code_from_calc_code(str(c)) for c in raw_codes]
        calc_codes = [f"{m}{eval_suffix}" for m in md_codes] if eval_suffix else [str(c) for c in raw_codes]
        snap = _global_snapshot(username, password, plazo)
        if snap is None or snap.empty:
            return pd.DataFrame()
        snap = snap[snap["Código"].isin(set(md_codes))].copy()
        if snap.empty:
            return pd.DataFrame()
        if eval_suffix:
            md_to_calc = dict(zip(md_codes, calc_codes))
            snap["Código"] = snap["Código"].map(lambda x: md_to_calc.get(str(x), str(x)))
        bond_type_map = {
            "cer": "cer", "lecap": "lecap", "tamar": "tamar",
            "dolarlinked": "dlksob", "dualtamar": "dual",
        }
        bond_type = bond_type_map.get(curve_key, "lecap")
        settle    = _settlement_date_str(plazo)
        codes_arr = snap["Código"].astype(str).to_numpy()
        last_arr  = pd.to_numeric(snap.get("last"),        errors="coerce").to_numpy(dtype="float64")
        bid_arr   = pd.to_numeric(snap.get("bid_price"),   errors="coerce").to_numpy(dtype="float64")
        off_arr   = pd.to_numeric(snap.get("offer_price"), errors="coerce").to_numpy(dtype="float64")
        m_last  = _parallel_metrics(codes_arr, last_arr, bond_type, settle)
        bid_tir = _parallel_tirea(codes_arr, bid_arr, settle)
        off_tir = _parallel_tirea(codes_arr, off_arr, settle)
        out = snap.reset_index(drop=True).copy()
        out = pd.concat([out, m_last], axis=1)
        out["Bid TIREA"]   = bid_tir
        out["Offer TIREA"] = off_tir
        out["Bid Price"]   = bid_arr
        out["Offer Price"] = off_arr
        out["Last Price"]  = last_arr
        return _sort_duration_nan_last(out, "Duration")

    _ARS_CURVES_DEF = [
        ("cer",         "CER",          "",  "TEA real"),
        ("lecap",       "Tasa Fija",    "",  "TEM nominal"),
        ("tamar",       "TAMAR",        "",  "Spread (bps)"),
        ("dolarlinked", "Dólar Linked", "",  "TEA vs devalu"),
        ("dualtamar",   "Dual (v)",     "v", "TEM (TAMAR)"),
    ]

    def _ref_metric_ars(row: pd.Series, curve_key: str, tamar_tna: float) -> float:
        tirea = float(row.get("TIREA", float("nan")) or float("nan"))
        tem   = float(row.get("TEM",   float("nan")) or float("nan"))
        tna   = float(row.get("TNA",   float("nan")) or float("nan"))
        if curve_key == "cer":
            return tirea
        elif curve_key == "lecap":
            return tem
        elif curve_key == "tamar":
            return (tna - tamar_tna / 100.0) * 10000.0 if np.isfinite(tna) else float("nan")
        elif curve_key in ("dolarlinked", "dualtamar"):
            return tem
        return float("nan")

    def _fmt_ref_ars(val: float, curve_key: str) -> str:
        if not np.isfinite(val):
            return "—"
        if curve_key == "tamar":
            return f"{val:+.0f} bps"
        return f"{val:+.2%}"

    with tab_curvas_ars:
        st.subheader("Curvas Soberanas ARS — Análisis Real")

        # Session state proyecciones (autoload ya corrió arriba; estos son fallbacks)
        if "ars_proy_fx"    not in st.session_state:
            st.session_state["ars_proy_fx"]    = _PROY_FX_DEFAULT.copy()
        if "ars_proy_tamar" not in st.session_state:
            st.session_state["ars_proy_tamar"] = _PROY_TAMAR_DEFAULT.copy()
        if "ars_proy_infla" not in st.session_state:
            st.session_state["ars_proy_infla"] = _PROY_INFLA_DEFAULT.copy()

        # Expander proyecciones
        _excel_exists = os.path.exists(_PROY_EXCEL_PATH)
        _excel_status = "✅ Excel cargado automáticamente" if _excel_exists else "⚠️ Excel no encontrado en ruta fija — usando defaults"
        with st.expander(f"⚙️ Proyecciones — FX, TAMAR e Inflación  |  {_excel_status}", expanded=False):
            if _excel_exists:
                st.caption(f"Leyendo automáticamente: `{_PROY_EXCEL_PATH}`")
                if st.button("🔄 Recargar Excel", key="ars_reload_excel"):
                    st.session_state["ars_proy_autoloaded"] = False
                    st.cache_data.clear()
                    st.rerun()
            st.caption(
                "O subí un Excel manual con: **col A** = fecha (fin de mes), "
                "**col B** = inflación MOM (%), **col C** = FX (ARS/USD), "
                "**col D** = TAMAR TNA (%). Primera fila = header."
            )
            uploaded_proy = st.file_uploader("Excel de proyecciones (override manual)", type=["xlsx"], key="ars_proy_upload")
            if uploaded_proy is not None:
                try:
                    df_up = pd.read_excel(uploaded_proy, header=1)
                    df_up.columns = ["fecha", "inflacion_mom", "FX", "TAMAR"]
                    df_up["fecha"] = pd.to_datetime(df_up["fecha"])
                    new_fx    = {r["fecha"].strftime("%Y-%m-%d"): float(r["FX"])
                                 for _, r in df_up.iterrows() if pd.notna(r.get("FX"))}
                    new_tamar = {r["fecha"].strftime("%Y-%m-%d"): float(r["TAMAR"])
                                 for _, r in df_up.iterrows() if pd.notna(r.get("TAMAR"))}
                    new_infla = {}
                    for _, r in df_up.iterrows():
                        if pd.notna(r.get("inflacion_mom")):
                            lbl = r["fecha"].strftime("%b-%y")
                            v = float(r["inflacion_mom"])
                            # Si viene en decimal (0.031) lo paso a % (3.1)
                            new_infla[lbl] = v * 100.0 if v < 1.0 else v
                    if new_fx:
                        st.session_state["ars_proy_fx"] = new_fx
                    if new_tamar:
                        st.session_state["ars_proy_tamar"] = new_tamar
                    if new_infla:
                        st.session_state["ars_proy_infla"] = new_infla
                        # Propagar al mecanismo global: impacta en TODOS los tabs que usan CER proyectado
                        # (Total Return, Curvas CER Proy, Breakeven, etc.)
                        st.session_state["_custom_inflation_proy"] = new_infla
                        _recalculate_cer_proyectado(new_infla)
                    st.success(f"Cargados: {len(new_fx)} pts FX · {len(new_tamar)} TAMAR · {len(new_infla)} inflación.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error leyendo Excel: {e}")

            # Editor manual de inflación
            st.markdown("**Editar inflación MOM (%) manualmente**")
            proy_infla_actual = st.session_state["ars_proy_infla"] or _PROY_INFLA_DEFAULT
            df_infla_edit = pd.DataFrame([
                {"Mes": k, "Inflación MOM (%)": float(v)}
                for k, v in proy_infla_actual.items()
            ])
            df_infla_editado = st.data_editor(
                df_infla_edit, num_rows="dynamic", use_container_width=True,
                key="ars_infla_editor",
                column_config={
                    "Mes": st.column_config.TextColumn("Mes", disabled=True),
                    "Inflación MOM (%)": st.column_config.NumberColumn(
                        "Inflación MOM (%)", min_value=0.0, max_value=30.0, step=0.1, format="%.1f",
                    ),
                },
            )
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("✅ Aplicar inflación", key="ars_apply_infla", type="primary"):
                    nueva_infla = {
                        row["Mes"]: float(row["Inflación MOM (%)"])
                        for _, row in df_infla_editado.iterrows()
                        if pd.notna(row.get("Inflación MOM (%)"))
                    }
                    st.session_state["ars_proy_infla"] = nueva_infla
                    # Propagar al mecanismo global — afecta Total Return, CER Proy, Breakeven, etc.
                    st.session_state["_custom_inflation_proy"] = nueva_infla
                    _recalculate_cer_proyectado(nueva_infla)
                    st.cache_data.clear()
                    st.rerun()
            with col_b2:
                if st.button("↩️ Restaurar defaults", key="ars_restore_infla"):
                    st.session_state["ars_proy_infla"] = None
                    # Limpiar override global para que vuelva al CER original de indices.py
                    if "_custom_inflation_proy" in st.session_state:
                        del st.session_state["_custom_inflation_proy"]
                    import indices as _idx_mod_ars
                    _recalculate_cer_proyectado(
                        getattr(_idx_mod_ars, "proyeccion_inflacion_mensual", _PROY_INFLA_DEFAULT)
                    )
                    st.cache_data.clear()
                    st.rerun()

        # Macro inputs
        fx_spot_ars = 1270.0
        df_a3500_ars = rentafija.inputs.get("a3500")
        if df_a3500_ars is not None and not df_a3500_ars.empty:
            fx_spot_ars = float(df_a3500_ars.iloc[-1].iloc[0])

        tamar_tna_ars = 30.0
        df_tamar_ars = rentafija.inputs.get("tamar")
        if df_tamar_ars is not None and len(df_tamar_ars) >= 5:
            tamar_tna_ars = float(df_tamar_ars.tail(5).iloc[:, 0].mean())

        proy_infla_ars = st.session_state.get("ars_proy_infla")
        cer_proy_ars   = _get_cer_proy_ars(proy_infla_ars)
        fx_proy_ars    = _interpolar_diario_ars(st.session_state["ars_proy_fx"],    fx_spot_ars)
        tamar_proy_ars = _interpolar_diario_ars(st.session_state["ars_proy_tamar"], tamar_tna_ars)

        @st.fragment(run_every=refresh_interval)
        def _curvas_ars_live():
            ts = datetime.now().strftime("%H:%M:%S")
            st.caption(
                (f"🔴 LIVE  |  Actualizado: {ts}  |  Plazo: {plazo}  |  "
                 f"FX spot: {fx_spot_ars:,.0f}  |  TAMAR 5d: {tamar_tna_ars:.2f}%")
                if auto_refresh else f"Actualizado: {ts}  |  Plazo: {plazo}"
            )

            for curve_key, curve_lbl, eval_sfx, ref_lbl in _ARS_CURVES_DEF:
                df_raw = _load_ars_curve_data(username, password, curve_key, eval_sfx, plazo)

                with st.expander(curve_lbl, expanded=(curve_key in ("cer", "lecap"))):
                    if df_raw is None or df_raw.empty:
                        st.info("Sin datos de mercado.")
                        continue

                    rows = []
                    bond_type_map = {
                        "cer":"cer","lecap":"lecap","tamar":"tamar",
                        "dolarlinked":"dlksob","dualtamar":"dual",
                    }
                    _bt = bond_type_map.get(curve_key, "lecap")
                    _settle = _settlement_date_str(plazo)
                    for _, row in df_raw.iterrows():
                        codigo = str(row.get("Código", ""))
                        dur    = float(row.get("Duration",    np.nan) or np.nan)
                        tirea  = float(row.get("TIREA",       np.nan) or np.nan)
                        bid_p  = float(row.get("Bid Price",   np.nan) or np.nan)
                        off_p  = float(row.get("Offer Price", np.nan) or np.nan)
                        last_p = float(row.get("Last Price",  np.nan) or np.nan)
                        var_p  = float(row.get("variation",   np.nan) or np.nan)

                        otc_ss = f"ars_otc_{curve_key}"
                        if otc_ss not in st.session_state:
                            st.session_state[otc_ss] = {}
                        otc_val = st.session_state[otc_ss].get(codigo, np.nan)

                        # Si hay OTC, recalcular TIREA y Duration con ese precio
                        if pd.notna(otc_val) and np.isfinite(otc_val):
                            m_otc = metrics_for_price(codigo, otc_val, _bt, _settle)
                            tirea_use = m_otc.get("TIREA", tirea)
                            dur_use   = m_otc.get("Duration", dur)
                            if not np.isfinite(tirea_use):
                                tirea_use = tirea
                            if not np.isfinite(dur_use):
                                dur_use = dur
                        else:
                            tirea_use = tirea
                            dur_use   = dur

                        # Build a synthetic row with OTC-recalculated metrics for ref
                        row_for_ref = row.copy()
                        row_for_ref["TIREA"] = tirea_use
                        row_for_ref["TEM"]   = (1.0+tirea_use)**(30.0/360.0)-1.0 if np.isfinite(tirea_use) else np.nan
                        row_for_ref["TNA"]   = rentafija.tir_a_tna(tirea_use, int(dur_use*365) if np.isfinite(dur_use) and dur_use>0 else 180, 365) if np.isfinite(tirea_use) else np.nan

                        ref_val  = _ref_metric_ars(row_for_ref, curve_key, tamar_tna_ars)
                        real_val = _ref_real_ars(tirea_use, curve_key, dur_use,
                                                 cer_proy_ars, fx_proy_ars, fx_spot_ars)

                        rows.append({
                            "Código":   codigo,
                            "McD":      dur_use,
                            "Bid":      bid_p,
                            "Offer":    off_p,
                            "Last":     last_p,
                            "Var %":    var_p,
                            "OTC":      otc_val,
                            "Ref":      _fmt_ref_ars(ref_val, curve_key),
                            "Ref Real": real_val,
                        })

                    df_show = pd.DataFrame(rows)

                    # Styling Ref Real con calor verde/rojo
                    real_num = pd.to_numeric(df_show["Ref Real"], errors="coerce")
                    lim_real = float(np.nanmax(np.abs(real_num.to_numpy(dtype="float64")))) if real_num.notna().any() else 0.10
                    if not np.isfinite(lim_real) or lim_real == 0:
                        lim_real = 0.10

                    edited = st.data_editor(
                        df_show,
                        column_config={
                            "OTC":      st.column_config.NumberColumn("OTC", help="Precio OTC — editá acá", format="%.4f", step=0.01),
                            "McD":      st.column_config.NumberColumn("McD",   format="%.2f"),
                            "Bid":      st.column_config.NumberColumn("Bid",   format="%.4f"),
                            "Offer":    st.column_config.NumberColumn("Offer", format="%.4f"),
                            "Last":     st.column_config.NumberColumn("Last",  format="%.4f"),
                            "Var %":    st.column_config.NumberColumn("Var %", format="%.2f%%"),
                            "Ref Real": st.column_config.NumberColumn("Ref Real (TEA real)", format="%.2f%%"),
                        },
                        disabled=[c for c in df_show.columns if c != "OTC"],
                        hide_index=True,
                        use_container_width=True,
                        key=f"ars_editor_{curve_key}",
                    )

                    # Persistir OTC
                    if edited is not None and "OTC" in edited.columns and "Código" in edited.columns:
                        otc_ss = f"ars_otc_{curve_key}"
                        for _, erow in edited.iterrows():
                            v = erow.get("OTC")
                            st.session_state[otc_ss][str(erow["Código"])] = float(v) if pd.notna(v) else np.nan

        _curvas_ars_live()

    # ─────────────────────────
    # Normalizada
    # ─────────────────────────
    with tab_normalizada:
        st.subheader("Curvas ARS — Vista Normalizada")
        _tamar_norm = 30.0
        _df_t_norm = rentafija.inputs.get("tamar")
        if _df_t_norm is not None and len(_df_t_norm) >= 5:
            _tamar_norm = float(_df_t_norm.tail(5).iloc[:, 0].mean())

        @st.cache_data(ttl=TTL_METRICS, show_spinner=False)
        def _build_normalizada(username: str, password: str, plazo: str, tamar_tna: float, _cer_hash: int = 0) -> pd.DataFrame:
            """
            Para cada bono, convierte su TIREA a TODAS las unidades de la tabla.
            Proyecciones usadas: CER proy (infla), FX proy (devalua), TAMAR actual.
            """
            settle = _settlement_date_str(plazo)
            snap = _global_snapshot(username, password, plazo)
            if snap is None or snap.empty:
                return pd.DataFrame()
            curves_c = build_curve_codes()

            # Proyecciones — siempre disponibles
            proy_infla_n = st.session_state.get("ars_proy_infla") or _PROY_INFLA_DEFAULT
            cer_proy_n   = _get_cer_proy_ars(proy_infla_n)
            fx_spot_n    = 1270.0
            _a3 = rentafija.inputs.get("a3500")
            if _a3 is not None and not _a3.empty:
                fx_spot_n = float(_a3.iloc[-1].iloc[0])
            fx_proy_n  = _interpolar_diario_ars(st.session_state.get("ars_proy_fx", _PROY_FX_DEFAULT), fx_spot_n)

            badlar_s = rentafija.inputs.get("badlar")
            badlar_v = float(badlar_s.tail(5).iloc[:,0].mean()) / 100.0 if badlar_s is not None and len(badlar_s)>=5 else 0.30

            def _to_real_cer(tirea, dur):
                """Deflactar por inflacion CER proyectada al plazo."""
                return _ref_real_ars(tirea, "lecap", dur, cer_proy_n, pd.Series(dtype=float), 1.0)

            def _to_real_fx(tirea, dur):
                """Deflactar por devaluacion FX proyectada al plazo."""
                return _ref_real_ars(tirea, "dolarlinked", dur, cer_proy_n, fx_proy_n, fx_spot_n)

            def _cer_to_nominal(tirea_real, dur):
                """CER real → nominal proyectada vía Fisher con CER proy."""
                if not np.isfinite(tirea_real) or not np.isfinite(dur) or dur <= 0 or cer_proy_n.empty:
                    return np.nan
                hoy_d = date.today()
                ft = hoy_d + timedelta(days=max(1, int(dur*365)))
                ih = cer_proy_n.index <= hoy_d
                ift = cer_proy_n.index <= ft
                if not ih.any() or not ift.any():
                    return np.nan
                ch = float(cer_proy_n[ih].iloc[-1])
                cf = float(cer_proy_n[ift].iloc[-1])
                if ch <= 0:
                    return np.nan
                infla_a = (cf/ch)**(1.0/dur) - 1.0
                return (1.0 + tirea_real) * (1.0 + infla_a) - 1.0

            def _cer_to_fx(tirea_real, dur):
                """CER real → DL equiv: (1+real_cer)/(1+real_fx) - 1."""
                real_fx = _to_real_fx(_cer_to_nominal(tirea_real, dur) or np.nan, dur)
                return real_fx  # same real basis

            rows = []
            for curve_key, bond_type, eval_sfx, tipo in [
                ("cer","cer","","CER"), ("lecap","lecap","","Fija"),
                ("tamar","tamar","","TAMAR"), ("dolarlinked","dlksob","","DL"),
                ("dualtamar","dual","v","Dual"),
            ]:
                raw_codes = curves_c.get(curve_key, [])
                if not raw_codes:
                    continue
                md_codes   = [_md_code_from_calc_code(str(c)) for c in raw_codes]
                calc_codes = [f"{m}{eval_sfx}" for m in md_codes] if eval_sfx else [str(c) for c in raw_codes]
                sub = snap[snap["Código"].isin(set(md_codes))].copy()
                if sub.empty:
                    continue
                if eval_sfx:
                    md2c = dict(zip(md_codes, calc_codes))
                    sub["Código"] = sub["Código"].map(lambda x: md2c.get(str(x), str(x)))
                codes_arr = sub["Código"].astype(str).to_numpy()
                last_arr  = pd.to_numeric(sub.get("last"), errors="coerce").to_numpy(dtype="float64")
                m = _parallel_metrics(codes_arr, last_arr, bond_type, settle)
                sub = sub.reset_index(drop=True)
                sub = pd.concat([sub, m], axis=1)

                for i, row in sub.iterrows():
                    tirea = float(row.get("TIREA", np.nan) or np.nan)
                    tna   = float(row.get("TNA",   np.nan) or np.nan)
                    tem   = float(row.get("TEM",   np.nan) or np.nan)
                    dur   = float(row.get("Duration", np.nan) or np.nan)
                    if not np.isfinite(tirea):
                        continue

                    # ── Convert to ALL units ──────────────────────────────────
                    # CER (real TEA / TNA 180/365)
                    if curve_key == "cer":
                        cer_tea = tirea
                        nom_tea = _cer_to_nominal(tirea, dur)
                    else:
                        # Nominal → real via CER proy
                        cer_tea = _to_real_cer(tirea, dur)
                        nom_tea = tirea  # already nominal

                    cer_tna = rentafija.tir_a_tna(cer_tea,180,365) if np.isfinite(cer_tea) else np.nan

                    # DL (TEA / TNA 180/360) — spread over FX path
                    if curve_key == "dolarlinked":
                        dl_tea = tirea  # already over FX
                    else:
                        # nominal → real over FX
                        dl_tea = _to_real_fx(nom_tea if np.isfinite(nom_tea) else tirea, dur)
                    dl_tna = rentafija.tir_a_tna(dl_tea,180,360) if np.isfinite(dl_tea) else np.nan

                    # Nominal (TEA / TEM / Directo / TNA 30/365)
                    nom_tem    = (1.0+nom_tea)**(30.0/360.0)-1.0 if np.isfinite(nom_tea) else np.nan
                    nom_tna_m  = tna if np.isfinite(tna) else np.nan
                    nom_tna30  = rentafija.tir_a_tna(nom_tea,30,365) if np.isfinite(nom_tea) else np.nan

                    # Variable (Badlar / Tamar spread / TNA 90/365)
                    if curve_key in ("tamar","dualtamar"):
                        badlar_spr = (tna - badlar_v) if np.isfinite(tna) else np.nan
                        tamar_spr  = (tna - tamar_tna/100.0) if np.isfinite(tna) else np.nan
                        tna90      = rentafija.tir_a_tna(tirea,90,365) if np.isfinite(tirea) else np.nan
                    else:
                        # For non-TAMAR: compute equivalent TAMAR spread assuming same nominal
                        nom_for_spread = nom_tea if np.isfinite(nom_tea) else tirea
                        tna_equiv = rentafija.tir_a_tna(nom_for_spread,90,365) if np.isfinite(nom_for_spread) else np.nan
                        badlar_spr = (tna_equiv - badlar_v) if np.isfinite(tna_equiv) else np.nan
                        tamar_spr  = (tna_equiv - tamar_tna/100.0) if np.isfinite(tna_equiv) else np.nan
                        tna90      = tna_equiv

                    rows.append({
                        "Tipo": tipo, "Activo": str(row.get("Código","")), "McD": dur,
                        "CER TEA":          cer_tea,
                        "CER TNA(180/360)": cer_tna,
                        "DL TEA":           dl_tea,
                        "DL TNA(180/360)":  dl_tna,
                        "Nom TEA":          nom_tea,
                        "Nom TEM":          nom_tem,
                        "Directo":          nom_tna_m,
                        "TNA(Mat/365)":     nom_tna_m,
                        "TNA(30/365)":      nom_tna30,
                        "Badlar":           badlar_spr,
                        "Tamar":            tamar_spr,
                        "TNA(90/365)":      tna90,
                    })
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows).sort_values(["Tipo","McD"]).reset_index(drop=True)

        @st.fragment(run_every=refresh_interval)
        def _normalizada_live():
            st.caption(f"🔴 LIVE  |  {datetime.now().strftime('%H:%M:%S')}  |  {plazo}" if auto_refresh else datetime.now().strftime('%H:%M:%S'))
            try:
                _cp_n = _get_cer_proy_ars(st.session_state.get("ars_proy_infla") or _PROY_INFLA_DEFAULT)
                _cer_h_n = hash(tuple(_cp_n.values[:5].tolist())) if not _cp_n.empty else 0
            except Exception:
                _cer_h_n = 0
            df_n = _build_normalizada(username, password, plazo, _tamar_norm, _cer_h_n)
            if df_n is None or df_n.empty:
                st.info("Sin datos.")
                return
            pct_cols = [c for c in df_n.columns if c not in ("Tipo","Activo","McD")]
            def _fmt_pct(x):
                if x is None or (isinstance(x, float) and not np.isfinite(x)):
                    return "—"
                v = float(x)
                return f"{v:.2%}" if v >= 0 else f"{v:.2%}"
            fmt = {c: _fmt_pct for c in pct_cols}
            fmt["McD"] = "{:.2f}"
            sty = df_n.style.format(fmt, na_rep="—")
            # Navy headers
            sty = sty.set_table_styles([
                {"selector":"thead tr th","props":"background-color:#1B3A6B;color:#FFFFFF;font-size:11px;font-weight:600;padding:5px 8px;text-align:center;border-bottom:2px solid #2ECC71;"},
                {"selector":"tbody tr:nth-child(even) td","props":"background-color:rgba(27,58,107,0.06);"},
                {"selector":"td","props":"font-size:11px;padding:3px 6px;"},
            ], overwrite=False)
            # Color only negative values red (positive neutral)
            for col in pct_cols:
                vals = pd.to_numeric(df_n[col], errors="coerce")
                lim = float(np.nanmax(np.abs(vals.dropna().to_numpy(dtype="float64")))) if vals.notna().any() else 0.1
                if np.isfinite(lim) and lim > 0:
                    sty = sty.map(
                        lambda x, _l=lim: (
                            f"color:#e74c3c;font-weight:600;" if isinstance(x,float) and np.isfinite(x) and x < 0
                            else ("color:#1B3A6B;" if isinstance(x,float) and np.isfinite(x) and x > 0 else "")
                        ),
                        subset=[col]
                    )
            st.dataframe(sty, width="stretch", height=min(38*len(df_n)+60, 900))
        _normalizada_live()

    # ─────────────────────────
    # Curva Nominal
    # ─────────────────────────
    with tab_curva_nominal:
        st.subheader("Curva Nominal")
        st.caption("Activo · McD · TEM · Tasa Real (CER) · TIR Nominal proyectada en pesos. Sin DL. Ordenado por McD.")

        @st.cache_data(ttl=TTL_METRICS, show_spinner=False)
        def _build_curva_nominal(username: str, password: str, plazo: str,
                                  _cer_proy_hash: int,
                                  cer_proy_vals_json: str = "[]") -> pd.DataFrame:
            """
            cer_proy_vals_json: JSON-serialized CER proy values (for cache key + use inside).
            Passed from outside cache so session_state is accessible.
            """
            import json as _json
            settle = _settlement_date_str(plazo)
            snap = _global_snapshot(username, password, plazo)
            if snap is None or snap.empty:
                return pd.DataFrame()
            curves_c = build_curve_codes()

            # Reconstruct CER proy series from passed values
            try:
                _cp_data = _json.loads(cer_proy_vals_json)
                if _cp_data:
                    cer_proy_n = pd.Series(
                        [v for _, v in _cp_data],
                        index=[date.fromisoformat(d) for d, _ in _cp_data],
                    )
                else:
                    cer_proy_n = pd.Series(dtype=float)
            except Exception:
                cer_proy_n = pd.Series(dtype=float)

            rows = []
            # Excluir dolarlinked
            for curve_key, bond_type, eval_sfx in [
                ("lecap","lecap",""), ("cer","cer",""),
                ("tamar","tamar",""), ("dualtamar","dual","v"),
            ]:
                raw_codes = curves_c.get(curve_key, [])
                if not raw_codes:
                    continue
                md_codes   = [_md_code_from_calc_code(str(c)) for c in raw_codes]
                calc_codes = [f"{m}{eval_sfx}" for m in md_codes] if eval_sfx else [str(c) for c in raw_codes]
                sub = snap[snap["Código"].isin(set(md_codes))].copy()
                if sub.empty:
                    continue
                if eval_sfx:
                    md2c = dict(zip(md_codes, calc_codes))
                    sub["Código"] = sub["Código"].map(lambda x: md2c.get(str(x), str(x)))
                codes_arr = sub["Código"].astype(str).to_numpy()
                last_arr  = pd.to_numeric(sub.get("last"), errors="coerce").to_numpy(dtype="float64")
                m = _parallel_metrics(codes_arr, last_arr, bond_type, settle)
                sub = sub.reset_index(drop=True)
                sub = pd.concat([sub, m], axis=1)
                for _, row in sub.iterrows():
                    codigo = str(row.get("Código",""))
                    dur    = float(row.get("Duration", np.nan) or np.nan)
                    tirea  = float(row.get("TIREA",    np.nan) or np.nan)
                    tem    = float(row.get("TEM",      np.nan) or np.nan)

                    # CER (real): para bonos CER = TIREA directamente (es la tasa real de mercado).
                    # Para Fija/TAMAR: real via Fisher con CER proy.
                    if curve_key == "cer":
                        cer_real = tirea
                    else:
                        cer_real = _ref_real_ars(
                            tirea, curve_key, dur, cer_proy_n,
                            pd.Series(dtype=float), 1.0
                        )

                    # TIR Nominal proyectada en pesos:
                    # - CER: Fisher → nominal = (1+real)*(1+inflación_anual_proy) - 1
                    # - Resto: TIREA ya es nominal
                    nom_proy = np.nan
                    if curve_key == "cer" and np.isfinite(tirea) and not cer_proy_n.empty and np.isfinite(dur) and dur > 0:
                        hoy_d = date.today()
                        ft = hoy_d + timedelta(days=max(1, int(dur * 365)))
                        ih  = cer_proy_n.index <= hoy_d
                        ift = cer_proy_n.index <= ft
                        if ih.any() and ift.any():
                            ch = float(cer_proy_n[ih].iloc[-1])
                            cf = float(cer_proy_n[ift].iloc[-1])
                            if ch > 0:
                                infla_anual = (cf / ch) ** (1.0 / dur) - 1.0
                                # Fisher directo: nominal = (1+real)*(1+infla) - 1
                                nom_proy = (1.0 + tirea) * (1.0 + infla_anual) - 1.0
                    elif np.isfinite(tirea):
                        nom_proy = tirea  # Fija/TAMAR/Dual: TIREA ya es TIR nominal

                    rows.append({
                        "Activo": codigo,
                        "McD": dur,
                        "TEM": tem,
                        "CER (real)": cer_real,
                        "TIR Nom. proy.": nom_proy,
                    })
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows).sort_values("McD").reset_index(drop=True)

        @st.fragment(run_every=refresh_interval)
        def _curva_nominal_live():
            st.caption(
                (f"🔴 LIVE  |  {datetime.now().strftime('%H:%M:%S')}  |  "
                 "CER (real) = TIR real s/CER  ·  TEM = tasa efectiva mensual nominal  ·  TIR Nom proy = Fisher(real × CER proy)")
                if auto_refresh else
                "CER (real) = TIR real s/CER  ·  TEM = efectiva mensual nominal  ·  TIR Nom proy = Fisher(real × CER proy)"
            )
            try:
                _cp = _get_cer_proy_ars(st.session_state.get("ars_proy_infla") or _PROY_INFLA_DEFAULT)
                _hash = hash(tuple(_cp.values[:10].tolist())) if not _cp.empty else 0
                import json as _json_cn
                # Serialize a sample of CER proy for passing into cache fn
                _cp_json = _json_cn.dumps(
                    [(str(d), float(v)) for d, v in zip(_cp.index[:500], _cp.values[:500])]
                ) if not _cp.empty else "[]"
            except Exception:
                _hash = 0
                _cp_json = "[]"
            df_cn = _build_curva_nominal(username, password, plazo, _hash, _cp_json)
            if df_cn is None or df_cn.empty:
                st.info("Sin datos.")
                return

            cer_col = "CER (real)"

            def _fmt_pct_cn(x):
                if x is None or (isinstance(x, float) and not np.isfinite(x)):
                    return "—"
                return f"{float(x):.2%}"

            fmt = {"McD": "{:.2f}", "TEM": _fmt_pct_cn, cer_col: _fmt_pct_cn, "TIR Nom. proy.": _fmt_pct_cn}
            sty = df_cn.style.format(fmt, na_rep="—")

            # Degradé rojo→verde en CER real
            vals = pd.to_numeric(df_cn[cer_col], errors="coerce") if cer_col in df_cn.columns else pd.Series(dtype=float)
            lim_cer = float(np.nanmax(np.abs(vals.dropna().to_numpy(dtype="float64")))) if vals.notna().any() else 0.10
            if not np.isfinite(lim_cer) or lim_cer == 0:
                lim_cer = 0.10
            sty = sty.map(lambda x: _diverging_bg(x, lim_cer, bold=True), subset=[cer_col])

            # Navy headers
            sty = sty.set_table_styles([
                {"selector":"thead tr th","props":"background-color:#1B3A6B;color:#FFFFFF;font-size:11px;font-weight:600;padding:5px 8px;text-align:center;border-bottom:2px solid #2ECC71;"},
                {"selector":"tbody tr:nth-child(even) td","props":"background-color:rgba(27,58,107,0.06);"},
                {"selector":"td","props":"font-size:11px;padding:3px 6px;"},
            ], overwrite=False)

            st.dataframe(
                sty, width="stretch", height=min(38*len(df_cn)+60, 900),
                column_config={
                    "Activo": st.column_config.TextColumn("Activo", width=85),
                    "McD":    st.column_config.TextColumn("McD",    width=55),
                    "TEM":    st.column_config.TextColumn("TEM nominal", width=90),
                    cer_col:  st.column_config.TextColumn("CER (real)", width=90),
                    "TIR Nom. proy.": st.column_config.TextColumn("TIR Nom proy", width=105),
                },
            )
        _curva_nominal_live()

    # ─────────────────────────
    # Trading
    # ─────────────────────────
    with tab_trading:
        st.subheader("Trading — Soberanos ARS")

        if "trading_otc" not in st.session_state:
            st.session_state["trading_otc"] = {}

        @st.cache_data(ttl=TTL_METRICS, show_spinner=False)
        def _build_trading_table(username: str, password: str, plazo: str) -> pd.DataFrame:
            settle = _settlement_date_str(plazo)
            snap = _global_snapshot(username, password, plazo)
            if snap is None or snap.empty:
                return pd.DataFrame()
            curves_c = build_curve_codes()
            rows = []
            tamar_v = 30.0
            _dt = rentafija.inputs.get("tamar")
            if _dt is not None and len(_dt) >= 5:
                tamar_v = float(_dt.tail(5).iloc[:,0].mean())
            for curve_key, bond_type, eval_sfx in [
                ("cer","cer",""), ("lecap","lecap",""), ("tamar","tamar",""),
                ("dolarlinked","dlksob",""), ("dualtamar","dual","v"),
            ]:
                raw_codes = curves_c.get(curve_key, [])
                if not raw_codes:
                    continue
                md_codes   = [_md_code_from_calc_code(str(c)) for c in raw_codes]
                calc_codes = [f"{m}{eval_sfx}" for m in md_codes] if eval_sfx else [str(c) for c in raw_codes]
                sub = snap[snap["Código"].isin(set(md_codes))].copy()
                if sub.empty:
                    continue
                if eval_sfx:
                    md2c = dict(zip(md_codes, calc_codes))
                    sub["Código"] = sub["Código"].map(lambda x: md2c.get(str(x), str(x)))
                codes_arr = sub["Código"].astype(str).to_numpy()
                last_arr  = pd.to_numeric(sub.get("last"),       errors="coerce").to_numpy(dtype="float64")
                bid_arr   = pd.to_numeric(sub.get("bid_price"),  errors="coerce").to_numpy(dtype="float64")
                off_arr   = pd.to_numeric(sub.get("offer_price"),errors="coerce").to_numpy(dtype="float64")
                clos_arr  = pd.to_numeric(sub.get("close"),      errors="coerce").to_numpy(dtype="float64")
                m_last  = _parallel_metrics(codes_arr, last_arr, bond_type, settle)
                bid_tir = _parallel_tirea(codes_arr, bid_arr,  settle)
                off_tir = _parallel_tirea(codes_arr, off_arr,  settle)
                sub = sub.reset_index(drop=True)
                sub = pd.concat([sub, m_last], axis=1)
                for i, row in sub.iterrows():
                    codigo  = str(row.get("Código",""))
                    tirea   = float(row.get("TIREA",    np.nan) or np.nan)
                    tna     = float(row.get("TNA",      np.nan) or np.nan)
                    tem     = float(row.get("TEM",      np.nan) or np.nan)
                    dur     = float(row.get("Duration", np.nan) or np.nan)
                    paridad = float(row.get("Paridad",  np.nan) or np.nan)
                    lp   = last_arr[i]  if i < len(last_arr)  else np.nan
                    bp   = bid_arr[i]   if i < len(bid_arr)   else np.nan
                    op   = off_arr[i]   if i < len(off_arr)   else np.nan
                    cl   = clos_arr[i]  if i < len(clos_arr)  else np.nan
                    mid  = (bp + op) / 2.0 if np.isfinite(bp) and np.isfinite(op) else lp
                    chg_px  = lp - cl if np.isfinite(lp) and np.isfinite(cl) else np.nan
                    bid_t = float(bid_tir[i]) if i < len(bid_tir) else np.nan
                    chg_yld = bid_t - tirea if np.isfinite(bid_t) and np.isfinite(tirea) else np.nan
                    if curve_key == "cer":
                        ref = tirea          # TIR real (decimal)
                    elif curve_key == "lecap":
                        ref = tem            # TEM nominal (decimal)
                    elif curve_key in ("tamar","dualtamar"):
                        ref = (tna - tamar_v/100.0) if np.isfinite(tna) else np.nan  # spread % (decimal)
                    elif curve_key == "dolarlinked":
                        ref = tirea          # TEA sobre devalu (decimal)
                    else:
                        ref = tem
                    bond_o = _bond_obj(codigo)
                    conv = np.nan
                    if bond_o is not None and np.isfinite(tirea):
                        try:
                            conv = bond_o.calcula_convexidad(tirea, settle) if hasattr(bond_o, "calcula_convexidad") else np.nan
                        except Exception:
                            pass
                    rows.append({
                        "Código": codigo, "Price": lp, "Bid": bp, "Offer": op,
                        "Mid": mid, "OTC": np.nan, "Ref": ref, "McD": dur,
                        "Convexity": conv, "Paridad": paridad,
                        "LTD Price": cl, "LTD Change": chg_px,
                        "Yield": tirea, "Yld Chg": chg_yld,
                    })
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows).sort_values("McD").reset_index(drop=True)

        @st.fragment(run_every=refresh_interval)
        def _trading_live():
            st.caption(f"🔴 LIVE  |  {datetime.now().strftime('%H:%M:%S')}  |  {plazo}"
                       if auto_refresh else datetime.now().strftime('%H:%M:%S'))
            df_tr = _build_trading_table(username, password, plazo)
            if df_tr is None or df_tr.empty:
                st.info("Sin datos.")
                return

            # Apply saved OTC
            df_tr["OTC"] = df_tr["Código"].map(
                lambda c: st.session_state["trading_otc"].get(c, np.nan)
            )

            _settle_tr = _settlement_date_str(plazo)
            _tamar_tr = 30.0
            _dt_tr = rentafija.inputs.get("tamar")
            if _dt_tr is not None and len(_dt_tr) >= 5:
                _tamar_tr = float(_dt_tr.tail(5).iloc[:,0].mean())

            def _bt_for_bond_tr(codigo):
                _obj = _bond_obj(codigo)
                if _obj is None:
                    return "lecap"
                _ind = (getattr(_obj, "industria", "") or "").upper()
                if "CER" in _ind or "INFLAC" in _ind:
                    return "cer"
                if "TAMAR" in _ind or "DUAL" in _ind:
                    return "tamar"
                if "DOLAR" in _ind or "LINKED" in _ind:
                    return "dlksob"
                return "lecap"

            def _recalc_row_otc(row):
                """Recalculate all metrics from OTC price if present."""
                otc = row.get("OTC")
                if not (pd.notna(otc) and np.isfinite(float(otc))):
                    return row
                codigo = str(row["Código"])
                bt = _bt_for_bond_tr(codigo)
                m_o = metrics_for_price(codigo, float(otc), bt, _settle_tr)
                tirea_new = m_o.get("TIREA", np.nan)
                tna_new   = m_o.get("TNA",   np.nan)
                tem_new   = m_o.get("TEM",   np.nan)
                dur_new   = m_o.get("Duration", row.get("McD", np.nan))
                if not np.isfinite(tirea_new):
                    return row
                # Recompute Ref
                if bt == "cer":
                    ref_new = tirea_new
                elif bt == "lecap":
                    ref_new = tem_new
                elif bt in ("tamar","dual"):
                    ref_new = (tna_new - _tamar_tr/100.0) if np.isfinite(tna_new) else np.nan
                else:
                    ref_new = tirea_new
                row = row.copy()
                row["Yield"] = tirea_new
                row["McD"]   = dur_new
                row["Ref"]   = ref_new
                return row

            df_tr = df_tr.apply(_recalc_row_otc, axis=1)

            disp_cols = ["Código","Price","Bid","Offer","Mid","OTC","Ref",
                         "McD","Convexity","Paridad","LTD Price","LTD Change","Yield","Yld Chg"]
            disp = df_tr[[c for c in disp_cols if c in df_tr.columns]].copy()

            def _fp(x):  # format price
                if x is None or (isinstance(x,float) and not np.isfinite(x)): return "—"
                return f"{float(x):,.2f}"
            def _fr(x):  # format rate (no + for positive)
                if x is None or (isinstance(x,float) and not np.isfinite(x)): return "—"
                return f"{float(x):.2%}"
            def _fc(x):  # format change px (+ only if positive)
                if x is None or (isinstance(x,float) and not np.isfinite(x)): return "—"
                v = float(x)
                return f"+{v:.2f}" if v > 0 else f"{v:.2f}"
            def _fyc(x):  # format yield change bps
                if x is None or (isinstance(x,float) and not np.isfinite(x)): return "—"
                v = float(x) * 10000  # to bps
                return f"+{v:.1f}bp" if v > 0 else f"{v:.1f}bp"

            fmt = {
                "Price":_fp,"Bid":_fp,"Offer":_fp,"Mid":_fp,"OTC":_fp,
                "LTD Price":_fp,
                "Ref":_fr, "Paridad":_fr, "Yield":_fr,
                "McD":"{:.2f}", "Convexity":"{:.2f}",
                "LTD Change":_fc, "Yld Chg":_fyc,
            }
            sty = disp.style.format(fmt, na_rep="—")

            # Navy headers
            sty = sty.set_table_styles([
                {"selector":"thead tr th","props":"background-color:#1B3A6B;color:#FFFFFF;font-size:11px;"
                 "font-weight:600;padding:5px 8px;text-align:center;border-bottom:2px solid #2ECC71;"},
                {"selector":"tbody tr:nth-child(even) td","props":"background-color:rgba(27,58,107,0.06);"},
                {"selector":"td","props":"font-size:11px;padding:3px 6px;"},
            ], overwrite=False)

            # LTD Change color
            if "LTD Change" in disp.columns:
                lim_c = max(float(np.nanmax(np.abs(
                    pd.to_numeric(disp["LTD Change"],errors="coerce").dropna().to_numpy(dtype="float64")
                ))), 0.01)
                sty = sty.map(lambda x: _diverging_bg(x, lim_c, bold=True), subset=["LTD Change"])

            # Yld Chg color
            if "Yld Chg" in disp.columns:
                lim_y = max(float(np.nanmax(np.abs(
                    pd.to_numeric(disp["Yld Chg"],errors="coerce").dropna().to_numpy(dtype="float64")
                ))), 0.0001)
                sty = sty.map(lambda x: _diverging_bg(x, lim_y, bold=False), subset=["Yld Chg"])

            edited_tr = st.data_editor(
                disp, hide_index=True, use_container_width=True, key="trading_editor",
                column_config={"OTC": st.column_config.NumberColumn("OTC", format="%.2f", step=0.01)},
                disabled=[c for c in disp.columns if c != "OTC"],
            )
            if edited_tr is not None and "OTC" in edited_tr.columns:
                for _, r in edited_tr.iterrows():
                    v = r.get("OTC")
                    st.session_state["trading_otc"][str(r["Código"])] = (
                        float(v) if pd.notna(v) else np.nan
                    )
        _trading_live()

    # ─────────────────────────
    # Forwards
    # ─────────────────────────
    with tab_fwds:
        st.subheader("Forwards implícitos (TEM) — tiempo real")
        st.caption("Diagonal = spot. Celda (fila i, col j) = tasa forward entre vencimiento i y j. Rojo = bajo vs extender, Verde = alto.")

        # ── Persistence helpers (disco, sobrevive reinicios) ─────────────────
        _FWD_EXCL_FILE = os.path.join(os.path.dirname(__file__) if "__file__" in dir() else ".", "fwd_exclusions.json")

        def _fwd_load_excl() -> Dict[str, List[str]]:
            try:
                if os.path.exists(_FWD_EXCL_FILE):
                    import json as _json
                    with open(_FWD_EXCL_FILE) as _f:
                        return _json.load(_f)
            except Exception:
                pass
            return {}

        def _fwd_save_excl(d: Dict[str, List[str]]) -> None:
            try:
                import json as _json
                with open(_FWD_EXCL_FILE, "w") as _f:
                    _json.dump(d, _f)
            except Exception:
                pass

        # Load from disk into session_state once per session
        if "fwd_excl_loaded" not in st.session_state:
            st.session_state["fwd_excl_all"] = _fwd_load_excl()
            st.session_state["fwd_excl_loaded"] = True

        # ── Build BONTAM (duales v + TAMAR soberanos) ─────────────────────────
        @st.cache_data(ttl=TTL_METRICS, show_spinner=False)
        def _load_bontam_last(username: str, password: str, plazo: str) -> pd.DataFrame:
            settle = _settlement_date_str(plazo)
            snap = _global_snapshot(username, password, plazo)
            if snap is None or snap.empty:
                return pd.DataFrame()
            curves_c = build_curve_codes()
            rows = []
            for ck, bt, sfx in [("dualtamar","dual","v"), ("tamar","tamar","")]:
                raw = curves_c.get(ck, [])
                if not raw:
                    continue
                md = [_md_code_from_calc_code(str(c)) for c in raw]
                calc = [f"{m}{sfx}" for m in md] if sfx else [str(c) for c in raw]
                sub = snap[snap["Código"].isin(set(md))].copy()
                if sub.empty:
                    continue
                if sfx:
                    md2c = dict(zip(md, calc))
                    sub["Código"] = sub["Código"].map(lambda x: md2c.get(str(x), str(x)))
                ca = sub["Código"].astype(str).to_numpy()
                la = pd.to_numeric(sub.get("last"), errors="coerce").to_numpy(dtype="float64")
                m = _parallel_metrics(ca, la, bt, settle)
                sub = sub.reset_index(drop=True)
                sub = pd.concat([sub, m], axis=1)
                rows.append(sub)
            if not rows:
                return pd.DataFrame()
            return _sort_duration_nan_last(pd.concat(rows, ignore_index=True), "Duration")

        def _forwards_tem(df_curve: pd.DataFrame) -> pd.DataFrame:
            """
            Matriz triangular superior de TEM forward entre pares de instrumentos.
            Fila i = instrumento corto, col j = instrumento largo (j > i).
            """
            if df_curve is None or df_curve.empty:
                return pd.DataFrame()
            if not all(c in df_curve.columns for c in ("Código","TIREA","Duration")):
                return pd.DataFrame()
            df = df_curve[["Código","TIREA","Duration"]].dropna().copy()
            df["TIREA"] = pd.to_numeric(df["TIREA"], errors="coerce")
            df["Duration"] = pd.to_numeric(df["Duration"], errors="coerce")
            df = df.dropna().sort_values("Duration").reset_index(drop=True)
            codes = list(df["Código"])
            tirs  = df["TIREA"].to_numpy(dtype="float64")
            durs  = df["Duration"].to_numpy(dtype="float64")
            n = len(codes)
            mat = np.full((n, n), np.nan)
            for i in range(n):
                for j in range(i, n):
                    if i == j:
                        # diagonal = TEM spot del instrumento
                        mat[i, j] = (1.0 + tirs[i]) ** (30.0/360.0) - 1.0
                    else:
                        d_i, d_j = durs[i], durs[j]
                        t_i, t_j = tirs[i], tirs[j]
                        if d_j > d_i and np.isfinite(t_i) and np.isfinite(t_j):
                            try:
                                fwd_tea = ((1.0+t_j)**d_j / (1.0+t_i)**d_i) ** (1.0/(d_j-d_i)) - 1.0
                                mat[i, j] = (1.0 + fwd_tea) ** (30.0/360.0) - 1.0
                            except Exception:
                                pass
            df_mat = pd.DataFrame(mat * 100.0, index=codes, columns=codes)
            df_mat.index.name = "Forwards (TEM)"
            return df_mat

        def _style_fwd_rg(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
            """Triangular sup rojo→verde, celdas anchas, diagonal en gris."""
            if df is None or df.empty:
                return pd.DataFrame().style
            num = df.copy().astype(float)
            vals_flat = num.to_numpy(dtype="float64").flatten()
            finite = vals_flat[np.isfinite(vals_flat)]
            lim = float(np.max(np.abs(finite))) if len(finite) else 5.0

            def _cell(v):
                if v is None or (isinstance(v, float) and not np.isfinite(v)):
                    return ""
                try:
                    x = float(v) / 100.0
                except Exception:
                    return ""
                a = min(abs(x) / (lim/100.0), 1.0)
                if x > 0:
                    r, g, b = 46, 204, 113
                elif x < 0:
                    r, g, b = 231, 76, 60
                else:
                    return "background-color: rgba(100,100,100,0.3);"
                alpha = 0.15 + 0.60 * a
                return f"background-color: rgba({r},{g},{b},{alpha:.3f}); font-weight: 600;"

            fmt = {c: lambda x: f"{x:.2f}%" if isinstance(x, float) and np.isfinite(x) else "—"
                   for c in df.columns}
            sty = df.style.format(fmt)
            sty = sty.map(_cell)
            # Wide cells via table styles
            sty = sty.set_table_styles([
                {"selector": "th", "props": "min-width: 62px; text-align: center; font-size: 11px; padding: 4px 6px;"},
                {"selector": "td", "props": "min-width: 62px; text-align: center; font-size: 11px; padding: 4px 6px;"},
            ])
            return sty

        # ── Render each curve ─────────────────────────────────────────────────
        _fwd_curves = {"CER": "cer", "LECAP / Tasa Fija": "lecap", "BONTAM": "_bontam"}

        for fwd_title, fwd_ck in _fwd_curves.items():
            st.markdown(f"### {fwd_title}")

            if fwd_ck == "_bontam":
                df_fwd_raw = _load_bontam_last(username, password, plazo)
            else:
                df_fwd_raw = load_curve_last_table(username, password, fwd_ck, plazo)

            if df_fwd_raw is None or df_fwd_raw.empty:
                st.info(f"Sin datos {fwd_title}.")
                continue

            all_bonds_fwd = list(df_fwd_raw["Código"].astype(str)) if "Código" in df_fwd_raw.columns else []
            excl_key = f"excl_{fwd_ck}"
            saved_excl = st.session_state["fwd_excl_all"].get(excl_key, [])

            with st.expander(f"⚙️ Excluir ilíquidos — {fwd_title}", expanded=False):
                cols_cb = st.columns(min(max(len(all_bonds_fwd), 1), 10))
                new_excl = []
                for idx_cb, bond_cb in enumerate(all_bonds_fwd):
                    with cols_cb[idx_cb % len(cols_cb)]:
                        checked = st.checkbox(
                            bond_cb,
                            value=(bond_cb not in saved_excl),
                            key=f"fwd_cb_{fwd_ck}_{bond_cb}"
                        )
                        if not checked:
                            new_excl.append(bond_cb)
                # Persist to disk if changed
                if set(new_excl) != set(saved_excl):
                    st.session_state["fwd_excl_all"][excl_key] = new_excl
                    _fwd_save_excl(st.session_state["fwd_excl_all"])

            # Apply exclusions
            active_excl = st.session_state["fwd_excl_all"].get(excl_key, [])
            if active_excl and "Código" in df_fwd_raw.columns:
                df_fwd_raw = df_fwd_raw[~df_fwd_raw["Código"].astype(str).isin(active_excl)].reset_index(drop=True)

            fwd_mat = _forwards_tem(df_fwd_raw)
            if fwd_mat is None or fwd_mat.empty:
                st.info(f"Pocos instrumentos para matriz {fwd_title}.")
            else:
                n_r = len(fwd_mat)
                # Height: enough rows, overflow scroll horizontally
                st.dataframe(
                    _style_fwd_rg(fwd_mat),
                    width="stretch",
                    height=min(42 * n_r + 60, 900),
                )

    # ─────────────────────────
    # Gráficos
    # ─────────────────────────
    with tab_graficos:
        st.subheader("Curva — Duration vs Yield (bid / last / offer) + NSS")

        curve_key = st.selectbox(
            "Curva",
            options=[c.key for c in CURVES if c.key in curves],
            format_func=lambda k: curve_labels.get(k, k),
            key="chart_curve",
        )

        if go is None:
            st.error("Plotly no está instalado en este entorno. Instalá: pip install plotly")
        else:
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                which = st.selectbox("Métrica", options=["TIREA", "TEM"], index=0)
            with c2:
                show_nss = st.checkbox("Mostrar NSS", value=True)
            with c3:
                thr = st.slider("Filtro outliers (threshold)", min_value=1.0, max_value=4.0, value=2.0, step=0.1)
            with c4:
                st.caption("TIP: si la curva tiene pocos puntos, NSS puede fallar.")

            df_last = load_curve_last_table(username, password, curve_key, plazo)
            df_mkt = load_curve_market_table(username, password, curve_key, plazo)

            if df_last is None or df_last.empty:
                st.info("Sin datos para graficar (mercado cerrado o sin marketdata).")
            else:
                fig, popt = plot_curve_plotly(
                    df_last,
                    df_curve_mkt=df_mkt,
                    title=f"{curve_labels.get(curve_key, curve_key)} — {plazo} ({which})",
                    show_nss=show_nss,
                    threshold_factor=float(thr),
                    which=which,
                )
                _st_plotly(fig)

                with st.expander("NSS: fórmula, parámetros y unidades", expanded=False):
                    st.markdown(
                        """
La función Nelson–Siegel–Svensson (NSS) usada (yield en **%**, i.e. *puntos porcentuales*) es:

`y(x) = β0 + β1 * ((1 - e^{-x/τ1})/(x/τ1)) + β2 * (((1 - e^{-x/τ1})/(x/τ1)) - e^{-x/τ1}) + β3 * (((1 - e^{-x/τ2})/(x/τ2)) - e^{-x/τ2}))`

**Interpretación (regla práctica):**
- `x` = **Duration (años)**.
- `y(x)` = **yield en %** (ej: 42.35 significa 42.35%).
- `β0` (**%**) ≈ "nivel" de largo plazo.
- `β1` (**%**) ≈ "pendiente" (impacta más al corto).
- `β2` (**%**) ≈ "curvatura" del tramo corto/medio (hump alrededor de `τ1`).
- `β3` (**%**) ≈ segunda curvatura (hump alrededor de `τ2`).
- `τ1`, `τ2` (**años de duration**) controlan *dónde* están esas curvaturas (escala temporal).

> Nota: los β están en **puntos porcentuales**, no en bps.
"""
                    )
                    if popt is None:
                        st.info("No se pudo ajustar NSS (pocos puntos / outliers / curva rara).")
                    else:
                        b0, b1, b2, b3, t1, t2 = [float(v) for v in popt]
                        st.write(
                            {
                                "beta0 (%, nivel LT)": b0,
                                "beta1 (%, pendiente corto)": b1,
                                "beta2 (%, curvatura 1)": b2,
                                "beta3 (%, curvatura 2)": b3,
                                "tau1 (años duration)": t1,
                                "tau2 (años duration)": t2,
                            }
                        )

                st.markdown("### Estimar TIR/TEM por Duration (NSS)")
                dur_in = st.number_input("Duration objetivo", min_value=0.0, value=1.0, step=0.05)

                try:
                    est = plotter.estimar_dur_tirtem_nss(float(dur_in), df_last, threshold_factor=float(thr), clip=True, use_cache=False)
                    if which == "TIREA":
                        st.write(
                            {
                                "Duration usada": est["duration_used"],
                                "TIREA": f"{est['TIREA_pct']:.2f}%",
                                "TEM": f"{est['TEM_pct']:.2f}%",
                                "Rango duration curva": (est["x_min"], est["x_max"]),
                            }
                        )
                    else:
                        st.write(
                            {
                                "Duration usada": est["duration_used"],
                                "TEM": f"{est['TEM_pct']:.2f}%",
                                "TIREA": f"{est['TIREA_pct']:.2f}%",
                                "Rango duration curva": (est["x_min"], est["x_max"]),
                            }
                        )
                except Exception as e:
                    st.info(f"No se pudo estimar NSS: {e}")

    # ─────────────────────────
    # Futuros
    # ─────────────────────────
    with tab_futuros:
        st.subheader("Futuros DLR (ROFEX) — implícitas vs A3500")
        st.caption("2 tablas (Minorista vs Mayorista con sufijo 'A'). Símbolos generados dinámicamente.")

        FUTUROS_BASE = _generate_futures_symbols(n_months=18)
        FUTUROS_MAY = [f"{s}A" for s in FUTUROS_BASE]

        def get_a3500_spot_fallback(default: float = 1300.0) -> float:
            import requests
            api_key = os.environ.get("MAE_API_KEY")
            if not api_key:
                return float(default)
            try:
                url = "https://openapi.mae.com.ar/openapi/v1/marketdata/" + "dolar"
                headers = {"X-API-Key": api_key}
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                data = res.json()
                return float(data.get("precio") or data.get("price") or default)
            except Exception:
                return float(default)

        colS1, colS2 = st.columns([1, 1])
        with colS1:
            a3500_auto = get_a3500_spot_fallback()
            a3500 = st.number_input("A3500 spot (mayorista)", value=float(a3500_auto), step=0.5)
        with colS2:
            st.caption("Si no hay MAE_API_KEY, usá input manual.")

        entries_fut = "LA,CL,SE"
        symbols_all = FUTUROS_BASE + FUTUROS_MAY
        raw = fetch_marketdata(username, password, symbols_all, market_id=DEFAULT_MARKET_ID, entries=entries_fut, depth=1)
        if raw is None or raw.empty:
            st.info("Sin datos de futuros (puede ser horario o mercado cerrado).")
        else:
            snap = OMSprices.market_snapshot(raw)
            snap = _ensure_codigo_col(snap, source="index")
            snap["Código"] = snap["Código"].astype(str)

            if "SE" in raw.columns:
                se = raw["SE"].map(OMSprices.extract_price)
                if "close" in snap.columns:
                    snap["close"] = snap["close"].fillna(se)
                else:
                    snap["close"] = se

            maturities = snap["Código"].map(_parsear_vencimiento_futuro)
            today = date.today()
            dias_vto = maturities.map(lambda d: (d - today).days if isinstance(d, date) else np.nan)

            lp = pd.to_numeric(snap.get("last"), errors="coerce")
            cp = pd.to_numeric(snap.get("close"), errors="coerce")

            with np.errstate(divide="ignore", invalid="ignore"):
                var = lp / cp - 1
                tasa_directa = lp / float(a3500) - 1
                tna = tasa_directa * 365.0 / dias_vto
                tea = (1.0 + tasa_directa * 30.0 / dias_vto) ** 12 - 1.0

            canal = snap["Código"].map(lambda s: "Mayorista" if str(s).upper().endswith("A") else "Minorista")

            out = pd.DataFrame(
                {
                    "Código": snap["Código"],
                    "Canal": canal,
                    "Close Price": cp,
                    "Last Price": lp,
                    "Variación": var,
                    "Dias Vto": dias_vto,
                    "Tasa Directa": tasa_directa,
                    "TNA": tna,
                    "TEA": tea,
                }
            ).replace([np.inf, -np.inf], np.nan)

            out = out.sort_values(by="Dias Vto", ascending=True).reset_index(drop=True)

            mostrar_mayorista = st.toggle("Mostrar Mayorista", value=False, key="fut_toggle_may")
            df_min = out[out["Canal"] == "Minorista"].drop(columns=["Canal"]).reset_index(drop=True)
            df_may = out[out["Canal"] == "Mayorista"].drop(columns=["Canal"]).reset_index(drop=True)
            if mostrar_mayorista:
                colA, colB = st.columns(2)
                with colA:
                    st.markdown("### Minorista (DLR/MMMYY)")
                    if df_min.empty:
                        st.info("Sin datos minorista.")
                    else:
                        st.dataframe(style_futuros(df_min), width="stretch", height=560)
                with colB:
                    st.markdown("### Mayorista (DLR/MMMYYA)")
                    if df_may.empty:
                        st.info("Sin datos mayorista.")
                    else:
                        st.dataframe(style_futuros(df_may), width="stretch", height=560)
            else:
                st.markdown("### Minorista (DLR/MMMYY)")
                if df_min.empty:
                    st.info("Sin datos minorista.")
                else:
                    st.dataframe(style_futuros(df_min), width="stretch", height=560)

    # ─────────────────────────
    # Total Return
    # ─────────────────────────
    with tab_tr:
        st.subheader("Total Return real (calcula_total_return)")

        curve_key = st.selectbox(
            "Curva",
            options=[c.key for c in CURVES if c.key in curves],
            format_func=lambda k: curve_labels.get(k, k),
            key="tr_curve",
        )

        df_last = load_curve_last_table(username, password, curve_key, plazo)
        if df_last is None or df_last.empty:
            st.info("Sin datos de curva (mercado cerrado o sin marketdata).")
        elif go is None:
            st.error("Plotly no está instalado en este entorno. Instalá: pip install plotly")
        else:
            st.caption(
                "Escenario por parámetros: "
                "**Nivel** (TIREA %), **Pendiente** (bps por 1 año de duration), "
                "**Convexidad** (bps por año²). "
                "**Anchor duration** = duration donde el nivel se fija (pivot de la parábola)."
            )

            colA, colB = st.columns([1, 1])
            with colA:
                terminal_date = st.date_input("Fecha terminal (horizonte)", value=date.today())
                mode = st.radio("Escenario", options=["Nivel/Pendiente/Convexidad", "Puntos (interpolación)"])

            durations = pd.to_numeric(df_last.get("Duration"), errors="coerce").to_numpy(dtype="float64")

            with colB:
                if mode.startswith("Nivel"):
                    # Anchor default: duration mediana de la curva (más representativo que 1.0 fijo)
                    durs = pd.to_numeric(df_last.get("Duration"), errors="coerce").to_numpy(dtype="float64")
                    d_med = float(np.nanmedian(durs)) if np.isfinite(durs).any() else 1.0

                    # defaults por curva/plazo
                    ss_key = f"tr_defaults::{curve_key}::{plazo}"
                    if ss_key not in st.session_state:
                        st.session_state[ss_key] = {}

                    # Si todavía no hay defaults calculados, los calculamos con NSS
                    if not st.session_state[ss_key]:
                        anchor0 = d_med
                        dflt = _nss_defaults_level_slope_convex(df_last, threshold_factor=2.0, anchor=anchor0, which="TIREA")
                        if dflt is None:
                            level0 = float(np.nanmedian(df_last["TIREA"]) * 100.0) if "TIREA" in df_last.columns else 40.0
                            slope0 = 0.0
                            convex0 = 0.0
                        else:
                            level0, slope0, convex0 = dflt

                        st.session_state[ss_key] = {
                            "anchor": float(anchor0),
                            "level_pct": float(level0),
                            "slope_bps": float(slope0),
                            "convex_bps": float(convex0),
                            "_last_anchor_used": float(anchor0),
                        }

                    # FIX CLAVE: keys únicas por curva/plazo (si no, Streamlit "pega" valores viejos)
                    k_anchor = f"tr_anchor::{curve_key}::{plazo}"
                    k_level  = f"tr_level::{curve_key}::{plazo}"
                    k_slope  = f"tr_slope::{curve_key}::{plazo}"
                    k_convex = f"tr_convex::{curve_key}::{plazo}"

                    anchor = st.number_input(
                        "Anchor duration",
                        value=float(st.session_state[ss_key]["anchor"]),
                        step=0.25,
                        key=k_anchor,
                    )

                    # Si cambiás anchor, recalculamos defaults NSS alrededor del nuevo anchor
                    last_anchor = st.session_state[ss_key].get("_last_anchor_used")
                    if last_anchor is None or abs(float(last_anchor) - float(anchor)) > 1e-12:
                        dflt2 = _nss_defaults_level_slope_convex(df_last, threshold_factor=2.0, anchor=float(anchor), which="TIREA")
                        if dflt2 is not None:
                            level0, slope0, convex0 = dflt2
                            st.session_state[ss_key]["level_pct"] = float(level0)
                            st.session_state[ss_key]["slope_bps"] = float(slope0)
                            st.session_state[ss_key]["convex_bps"] = float(convex0)
                        st.session_state[ss_key]["anchor"] = float(anchor)
                        st.session_state[ss_key]["_last_anchor_used"] = float(anchor)

                        # además, pisamos los widgets para que se actualicen visualmente
                        if k_level in st.session_state:
                            st.session_state[k_level] = float(st.session_state[ss_key]["level_pct"])
                        if k_slope in st.session_state:
                            st.session_state[k_slope] = float(st.session_state[ss_key]["slope_bps"])
                        if k_convex in st.session_state:
                            st.session_state[k_convex] = float(st.session_state[ss_key]["convex_bps"])

                    level_pct = st.number_input(
                        "Nivel (TIREA %)",
                        value=float(st.session_state[ss_key]["level_pct"]),
                        step=0.25,
                        key=k_level,
                    )
                    slope_bps = st.number_input(
                        "Pendiente (bps por año)",
                        value=float(st.session_state[ss_key]["slope_bps"]),
                        step=25.0,
                        key=k_slope,
                    )
                    convex_bps = st.number_input(
                        "Convexidad (bps por año²)",
                        value=float(st.session_state[ss_key]["convex_bps"]),
                        step=10.0,
                        key=k_convex,
                    )

                    scenario_y = _scenario_curve_params(durations, level_pct, slope_bps, convex_bps, anchor=anchor)

                else:
                    dmin = float(np.nanmin(durations)) if np.isfinite(durations).any() else 0.5
                    dmax = float(np.nanmax(durations)) if np.isfinite(durations).any() else 2.0
                    dmid = float((dmin + dmax) / 2)
                    y0 = float(np.nanmedian(df_last["TIREA"]) * 100.0) if "TIREA" in df_last.columns else 40.0

                    pts_default = pd.DataFrame({"Duration": [dmin, dmid, dmax], "TIREA %": [y0, y0, y0]})
                    pts_editor = st.data_editor(pts_default, num_rows="dynamic", width="stretch")
                    scenario_y = _scenario_curve_points(durations, pts_editor)

            cN1, cN2 = st.columns([1, 2])
            with cN1:
                show_nss_tr = st.checkbox("Mostrar NSS (curva actual)", value=True, key="tr_show_nss")
            with cN2:
                thr_tr = st.slider(
                    "Filtro outliers NSS (TR)",
                    min_value=1.0,
                    max_value=4.0,
                    value=2.0,
                    step=0.1,
                    key="tr_thr",
                )

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=df_last["Duration"],
                    y=_yield_pct_points(df_last["TIREA"]),
                    mode="markers",
                    name="Actual (LAST)",
                    text=df_last["Código"],
                    hovertemplate="%{text}<br>Dur=%{x:.3f}<br>TIREA=%{y:.2f}%<extra></extra>",
                )
            )

            if show_nss_tr:
                try:
                    tmp = df_last[["Código", "Duration", "TIREA", "TEM"]].copy()
                    popt_tr, x_min_tr, x_max_tr = plotter._fit_nss_cached(
                        tmp,
                        which="TIREA",
                        threshold_factor=float(thr_tr),
                        use_cache=False,
                    )

                    npts_tr = int(df_last[["Duration", "TIREA"]].dropna().shape[0])
                    if npts_tr < 6 and abs(float(popt_tr[3])) < 1e-12:
                        _warn_once(
                            f"ns_fallback::tr::{curve_key}",
                            "Curva TR con pocos puntos: ajustando con fallback Nelson–Siegel (β3=0).",
                        )

                    xs = np.linspace(float(x_min_tr), float(x_max_tr), 160)
                    ys_pct = plotter.nss_model(xs, *popt_tr)
                    fig.add_trace(
                        go.Scatter(
                            x=xs,
                            y=ys_pct,
                            mode="lines",
                            name="NSS (Actual)",
                            line=dict(dash="dash"),
                            hovertemplate="Dur=%{x:.3f}<br>NSS=%{y:.2f}%<extra></extra>",
                        )
                    )
                except Exception as e:
                    _warn_once(f"nss_fail::tr::{curve_key}", f"Curva TR: no se pudo ajustar NSS/NS: {e}")

            fig.add_trace(
                go.Scatter(
                    x=df_last["Duration"],
                    y=scenario_y * 100.0,
                    mode="lines",
                    name="Escenario",
                    hovertemplate="Dur=%{x:.3f}<br>y=%{y:.2f}%<extra></extra>",
                )
            )

            fig.update_layout(
                title="Curva escenario",
                xaxis_title="Duration",
                yaxis_title="TIREA (%)",
                height=420,
                margin=dict(l=10, r=10, t=50, b=10),
            )
            _st_plotly(fig)

            st.markdown("### Total Return por instrumento")
            tr_df = compute_total_return_table(df_last, plazo=plazo, terminal_date=terminal_date, scenario_y=scenario_y)
            if tr_df.empty:
                st.info("No se pudo calcular Total Return (faltan datos o bonos sin método).")
            else:
                cols_show = [
                    "Código",
                    "Duration",
                    "Px inicial",
                    "Px final",
                    "Cupones cobrados",
                    "P&L Capital",
                    "TIREA inicial",
                    "TIREA final",
                    "_tr_num",
                ]
                cols_show = [c for c in cols_show if c in tr_df.columns]
                tr_show = tr_df[cols_show].copy()

                tr_show = tr_show.rename(columns={"_tr_num": "Total Return"})
                # opcional (queda muy visual):
                tr_show = tr_show.sort_values("Total Return", ascending=False, na_position="last").reset_index(drop=True)

                st.dataframe(
                    style_total_return(tr_show, tr_col="Total Return"),
                    width="stretch",
                    height=620,
                )

    # ─────────────────────────
    # Análisis de Yields (YAS)
    # ─────────────────────────
    with tab_yas:
        st.subheader("Análisis de Yields (YAS)")
        st.caption("Ingresá Precio, TIR, TNA o Margen → obtenés las métricas del bono + posición en la curva.")

        all_codes = _all_bond_codes()
        if not all_codes:
            st.info("No hay bonos disponibles en el universo.")
        else:
            col_sel, col_inp = st.columns([1, 2])

            with col_sel:
                yas_code = st.selectbox("Bono", options=all_codes, key="yas_bond")
                yas_mode = st.radio(
                    "Input",
                    options=["Precio", "TIREA", "TNA", "Margen TNA"],
                    horizontal=True,
                    key="yas_mode",
                )
                yas_nominales = st.number_input(
                    "VN (nominales)", value=1_000_000, step=100_000, key="yas_nom",
                )

            # Defaults inteligentes según bono elegido
            bond_obj_yas = _bond_obj(yas_code)
            settle_yas = _settlement_date_str(plazo)

            with col_inp:
                if yas_mode == "Precio":
                    yas_val = st.number_input("Precio (% VN)", value=100.0, step=0.01, format="%.4f", key="yas_val_px")
                    mode_key = "precio"
                elif yas_mode == "TIREA":
                    yas_val = st.number_input("TIREA (decimal, ej 0.42)", value=0.40, step=0.005, format="%.6f", key="yas_val_tir")
                    mode_key = "tir"
                elif yas_mode == "TNA":
                    yas_val = st.number_input("TNA (decimal, ej 0.38)", value=0.38, step=0.005, format="%.6f", key="yas_val_tna")
                    mode_key = "tna"
                else:  # Margen TNA
                    yas_val = st.number_input("Margen TNA (decimal, ej 0.02)", value=0.02, step=0.005, format="%.6f", key="yas_val_m")
                    mode_key = "margen"

                yas_tc = None
                if bond_obj_yas and getattr(bond_obj_yas, "ajuste_sobre_capital", None) == "DLK":
                    yas_tc = st.number_input("TC aplicable (A3500)", value=1300.0, step=0.5, key="yas_tc")

            if st.button("Calcular", key="yas_calc", type="primary"):
                # Ejecutar genera_ticket una sola vez (calcula TIREA + intereses internamente)
                ticket_df = _ticket_raw(yas_code, mode_key, yas_val, yas_nominales, settle_yas, yas_tc)

                # Extraer métricas del estado del bono (ya calculado por genera_ticket)
                bond_obj_calc = _bond_obj(yas_code)
                if bond_obj_calc is not None:
                    tirea = getattr(bond_obj_calc, "tirea", np.nan)
                    tna_calc = getattr(bond_obj_calc, "tna", np.nan)
                    tem_calc = (1 + tirea) ** (30 / 360) - 1 if np.isfinite(tirea) else np.nan
                    dur_calc = bond_obj_calc.calcula_duration(tirea, settle_yas) if np.isfinite(tirea) else np.nan
                    par_calc = getattr(bond_obj_calc, "paridad", np.nan)

                    # Margen sobre índice
                    margen_calc = np.nan
                    idx = getattr(bond_obj_calc, "index", None)
                    tipo = getattr(bond_obj_calc, "tipo_tasa_interes", None)
                    if tipo in ("VARIABLE", "VARIABLE_CAP") and idx:
                        inp = rentafija.inputs
                        if idx == "BADLAR":
                            ajuste = inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean()
                        elif idx == "TAMAR":
                            ajuste = inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean()
                        else:
                            ajuste = 0.0
                        if np.isfinite(tna_calc) and np.isfinite(ajuste):
                            margen_calc = tna_calc - ajuste / 100.0

                    metrics = {
                        "Código": yas_code,
                        "Nombre": getattr(bond_obj_calc, "nombre_security", yas_code),
                        "Vencimiento": getattr(bond_obj_calc, "vencimiento", None),
                        "Fecha Liquidación": getattr(bond_obj_calc, "fecha_settlement", None),
                        "Precio": getattr(bond_obj_calc, "precio", np.nan),
                        "TIREA": tirea,
                        "TNA": tna_calc,
                        "TEM": tem_calc,
                        "Duration": dur_calc,
                        "Paridad": par_calc,
                        "Intereses Corridos": getattr(bond_obj_calc, "intereses_corridos", np.nan),
                        "Días Devengados": getattr(bond_obj_calc, "dias_corridos", np.nan),
                        "Valor Residual": getattr(bond_obj_calc, "valor_residual", np.nan),
                        "Moneda": getattr(bond_obj_calc, "moneda", ""),
                        "Index": idx or "",
                        "Margen TNA": margen_calc,
                        "Callable": getattr(bond_obj_calc, "callable", ""),
                        "Calificación": getattr(bond_obj_calc, "calificacion", ""),
                    }
                else:
                    metrics = {}

                if metrics:
                    # ── Bloque YAS-style ──
                    st.markdown("---")
                    hdr1, hdr2, hdr3 = st.columns(3)
                    with hdr1:
                        st.markdown(f"### {metrics.get('Código', '')}")
                        st.caption(f"{metrics.get('Nombre', '')}")
                    with hdr2:
                        vto = metrics.get("Vencimiento")
                        fl = metrics.get("Fecha Liquidación")
                        st.caption(f"Vto: {vto.strftime('%d/%m/%Y') if vto else '—'}")
                        st.caption(f"Settle: {fl.strftime('%d/%m/%Y') if fl else '—'}")
                    with hdr3:
                        st.caption(f"Moneda: {metrics.get('Moneda', '—')} · {metrics.get('Calificación', '—')}")
                        if metrics.get("Index"):
                            st.caption(f"Index: {metrics['Index']}")

                    # Métricas principales
                    m1, m2, m3, m4, m5 = st.columns(5)
                    px = metrics.get("Precio", np.nan)
                    tirea = metrics.get("TIREA", np.nan)
                    tna_v = metrics.get("TNA", np.nan)
                    tem_v = metrics.get("TEM", np.nan)
                    dur_v = metrics.get("Duration", np.nan)

                    with m1:
                        st.metric("Precio", f"{px:.4f}" if np.isfinite(px) else "—")
                    with m2:
                        st.metric("TIREA", f"{tirea:.4%}" if np.isfinite(tirea) else "—")
                    with m3:
                        st.metric("TNA", f"{tna_v:.4%}" if np.isfinite(tna_v) else "—")
                    with m4:
                        st.metric("TEM", f"{tem_v:.4%}" if np.isfinite(tem_v) else "—")
                    with m5:
                        st.metric("Duration", f"{dur_v:.4f}" if np.isfinite(dur_v) else "—")

                    # Fila secundaria
                    s1, s2, s3, s4 = st.columns(4)
                    par = metrics.get("Paridad", np.nan)
                    ic = metrics.get("Intereses Corridos", np.nan)
                    dd = metrics.get("Días Devengados", np.nan)
                    vr = metrics.get("Valor Residual", np.nan)
                    margen = metrics.get("Margen TNA", np.nan)

                    with s1:
                        st.metric("Paridad", f"{par:.2%}" if np.isfinite(par) else "—")
                    with s2:
                        st.metric("Int. Corridos", f"{ic:.6f}" if np.isfinite(ic) else "—")
                    with s3:
                        st.metric("Días Dev.", f"{int(dd)}" if np.isfinite(dd) else "—")
                    with s4:
                        if np.isfinite(margen):
                            st.metric("Margen TNA", f"{margen:.4%}")
                        else:
                            st.metric("Val. Residual", f"{vr:.2f}%" if np.isfinite(vr) else "—")

                    # Ticket completo (DataFrame) — ya calculado arriba
                    with st.expander("Ver ticket completo (DataFrame)", expanded=False):
                        if ticket_df is not None:
                            st.dataframe(ticket_df, width="stretch")
                        else:
                            st.info("No se pudo generar el ticket.")

                    # ── Gráfico: punto en la curva ──
                    if go is not None and np.isfinite(dur_v) and np.isfinite(tirea):
                        curve_key_yas = _find_curve_for_bond(yas_code)
                        if curve_key_yas:
                            df_curve_yas = load_curve_last_table(username, password, curve_key_yas, plazo)
                            if df_curve_yas is not None and not df_curve_yas.empty:
                                fig_yas = go.Figure()

                                # Curva (todos los puntos)
                                y_pct = _yield_pct_points(df_curve_yas["TIREA"])
                                fig_yas.add_trace(go.Scatter(
                                    x=df_curve_yas["Duration"], y=y_pct,
                                    mode="markers",
                                    name=f"Curva {curve_labels.get(curve_key_yas, curve_key_yas)}",
                                    text=df_curve_yas["Código"],
                                    hovertemplate="%{text}<br>Dur=%{x:.3f}<br>TIREA=%{y:.2f}%<extra></extra>",
                                    marker=dict(size=8, opacity=0.6),
                                ))

                                # NSS fit
                                try:
                                    tmp = df_curve_yas[["Código", "Duration", "TIREA", "TEM"]].copy()
                                    popt_yas, x_min_yas, x_max_yas = plotter._fit_nss_cached(
                                        tmp, which="TIREA", threshold_factor=2.0, use_cache=True,
                                    )
                                    xs = np.linspace(float(x_min_yas), float(x_max_yas), 160)
                                    ys = plotter.nss_model(xs, *popt_yas)
                                    fig_yas.add_trace(go.Scatter(
                                        x=xs, y=ys, mode="lines", name="NSS",
                                        line=dict(dash="dash", width=1.5),
                                        hovertemplate="Dur=%{x:.3f}<br>NSS=%{y:.2f}%<extra></extra>",
                                    ))
                                except Exception:
                                    pass

                                # Punto del bono analizado
                                tirea_pct = _yield_pct_points(tirea)
                                fig_yas.add_trace(go.Scatter(
                                    x=[dur_v], y=[tirea_pct],
                                    mode="markers",
                                    name=f"▶ {yas_code}",
                                    marker=dict(size=14, color="red", symbol="diamond"),
                                    hovertemplate=f"{yas_code}<br>Dur={dur_v:.3f}<br>TIREA={tirea_pct:.2f}%<extra></extra>",
                                ))

                                fig_yas.update_layout(
                                    title=f"{yas_code} en curva {curve_labels.get(curve_key_yas, curve_key_yas)} — {plazo}",
                                    xaxis_title="Duration",
                                    yaxis_title="TIREA (%)",
                                    height=420,
                                    margin=dict(l=10, r=10, t=50, b=10),
                                    hovermode="closest",
                                )
                                _st_plotly(fig_yas)
                        else:
                            st.caption("(Bono no pertenece a ninguna curva cargada — sin gráfico de curva)")

    # ─────────────────────────
    # Comparador Yields
    # ─────────────────────────
    with tab_comp:
        st.subheader("Comparador de Yields")
        st.caption("Compará dos bonos por precio o TNA (equivalente a .comparar_precio() / .comparar_tna()).")

        all_codes_c = _all_bond_codes()
        if not all_codes_c:
            st.info("No hay bonos disponibles.")
        else:
            comp_mode = st.radio(
                "Modo comparación",
                options=["Por Precio", "Por TNA"],
                horizontal=True,
                key="comp_mode",
            )

            colA, colB = st.columns(2)
            with colA:
                st.markdown("#### Bono A")
                code_a = st.selectbox("Bono A", options=all_codes_c, key="comp_a")
                if comp_mode == "Por Precio":
                    val_a = st.number_input("Precio A (% VN)", value=100.0, step=0.01, format="%.4f", key="comp_val_a")
                else:
                    val_a = st.number_input("TNA A (decimal)", value=0.38, step=0.005, format="%.6f", key="comp_val_a")

            with colB:
                st.markdown("#### Bono B")
                code_b = st.selectbox("Bono B", options=all_codes_c, key="comp_b")
                if comp_mode == "Por Precio":
                    val_b = st.number_input("Precio B (% VN)", value=100.0, step=0.01, format="%.4f", key="comp_val_b")
                else:
                    val_b = st.number_input("TNA B (decimal)", value=0.38, step=0.005, format="%.6f", key="comp_val_b")

            comp_nom = st.number_input("VN (nominales)", value=1_000_000, step=100_000, key="comp_nom")
            settle_comp = _settlement_date_str(plazo)

            if st.button("Comparar", key="comp_calc", type="primary"):
                obj_a = _bond_obj(code_a)
                obj_b = _bond_obj(code_b)

                if obj_a is None or obj_b is None:
                    st.error(f"No se encontró el bono {'A' if obj_a is None else 'B'}.")
                else:
                    try:
                        if comp_mode == "Por Precio":
                            comp_df = obj_a.comparar_precio(obj_b, val_a / 100.0, val_b / 100.0, comp_nom, settle_comp)
                        else:
                            comp_df = obj_a.comparar_tna(obj_b, val_a, val_b, comp_nom, settle_comp)

                        if comp_df is not None and not comp_df.empty:
                            # FIX: comparar_* hace pd.concat → columnas duplicadas ("Valores","Valores")
                            if comp_df.columns.duplicated().any():
                                comp_df.columns = [f"{code_a}" if i == 0 else f"{code_b}"
                                                   for i, _ in enumerate(comp_df.columns)]
                            # Métricas lado a lado (YAS-style)
                            # Extraemos del estado del bono (comparar_* ya corrió calcula_tirea)
                            st.markdown("---")

                            def _metrics_from_state(obj, code):
                                """Extrae métricas del estado del bono ya calculado."""
                                tirea = getattr(obj, "tirea", np.nan)
                                tna_v = getattr(obj, "tna", np.nan)
                                tem_v = (1 + tirea) ** (30 / 360) - 1 if np.isfinite(tirea) else np.nan
                                try:
                                    dur_v = obj.calcula_duration(tirea, settle_comp) if np.isfinite(tirea) else np.nan
                                except Exception:
                                    dur_v = np.nan
                                margen_v = np.nan
                                idx = getattr(obj, "index", None)
                                tipo = getattr(obj, "tipo_tasa_interes", None)
                                if tipo in ("VARIABLE", "VARIABLE_CAP") and idx:
                                    inp = rentafija.inputs
                                    if idx == "BADLAR":
                                        ajuste = inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean()
                                    elif idx == "TAMAR":
                                        ajuste = inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean()
                                    else:
                                        ajuste = 0.0
                                    if np.isfinite(tna_v) and np.isfinite(ajuste):
                                        margen_v = tna_v - ajuste / 100.0
                                return {
                                    "Código": code,
                                    "Nombre": getattr(obj, "nombre_security", code),
                                    "Precio": getattr(obj, "precio", np.nan),
                                    "TIREA": tirea,
                                    "TNA": tna_v,
                                    "TEM": tem_v,
                                    "Duration": dur_v,
                                    "Paridad": getattr(obj, "paridad", np.nan),
                                    "Margen TNA": margen_v,
                                }

                            met_a = _metrics_from_state(obj_a, code_a)
                            met_b = _metrics_from_state(obj_b, code_b)

                            if met_a and met_b:
                                head_a, head_b = st.columns(2)
                                with head_a:
                                    st.markdown(f"### {met_a.get('Código', '')}")
                                    st.caption(f"{met_a.get('Nombre', '')}")
                                with head_b:
                                    st.markdown(f"### {met_b.get('Código', '')}")
                                    st.caption(f"{met_b.get('Nombre', '')}")

                                def _comp_row(label: str, key: str, fmt: str = "{:.4%}"):
                                    c1, c2, c3 = st.columns([2, 2, 1])
                                    va = met_a.get(key, np.nan)
                                    vb = met_b.get(key, np.nan)
                                    with c1:
                                        st.metric(label, fmt.format(va) if np.isfinite(va) else "—")
                                    with c2:
                                        st.metric(label, fmt.format(vb) if np.isfinite(vb) else "—")
                                    with c3:
                                        if np.isfinite(va) and np.isfinite(vb):
                                            diff = vb - va
                                            if "%" in fmt:
                                                st.metric("Δ", f"{diff:+.4%}")
                                            else:
                                                st.metric("Δ", f"{diff:+.4f}")
                                        else:
                                            st.metric("Δ", "—")

                                _comp_row("Precio", "Precio", "{:.4f}")
                                _comp_row("TIREA", "TIREA", "{:.4%}")
                                _comp_row("TNA", "TNA", "{:.4%}")
                                _comp_row("TEM", "TEM", "{:.4%}")
                                _comp_row("Duration", "Duration", "{:.4f}")
                                _comp_row("Paridad", "Paridad", "{:.2%}")
                                if np.isfinite(met_a.get("Margen TNA", np.nan)) or np.isfinite(met_b.get("Margen TNA", np.nan)):
                                    _comp_row("Margen TNA", "Margen TNA", "{:.4%}")

                            # Tabla completa
                            with st.expander("Ver tabla completa (comparar_precio/tna)", expanded=False):
                                st.dataframe(comp_df, width="stretch")

                            # Gráfico comparativo en la curva
                            if go is not None and met_a and met_b:
                                dur_a = met_a.get("Duration", np.nan)
                                dur_b = met_b.get("Duration", np.nan)
                                tir_a = met_a.get("TIREA", np.nan)
                                tir_b = met_b.get("TIREA", np.nan)

                                if np.isfinite(dur_a) and np.isfinite(dur_b):
                                    curve_a = _find_curve_for_bond(code_a)
                                    curve_b = _find_curve_for_bond(code_b)
                                    # Usar la primera curva que tenga datos
                                    curve_use = curve_a or curve_b

                                    fig_comp = go.Figure()

                                    if curve_use:
                                        df_c = load_curve_last_table(username, password, curve_use, plazo)
                                        if df_c is not None and not df_c.empty:
                                            fig_comp.add_trace(go.Scatter(
                                                x=df_c["Duration"],
                                                y=_yield_pct_points(df_c["TIREA"]),
                                                mode="markers",
                                                name=f"Curva {curve_labels.get(curve_use, curve_use)}",
                                                text=df_c["Código"],
                                                hovertemplate="%{text}<br>Dur=%{x:.3f}<br>TIREA=%{y:.2f}%<extra></extra>",
                                                marker=dict(size=7, opacity=0.5),
                                            ))
                                            try:
                                                tmp = df_c[["Código", "Duration", "TIREA", "TEM"]].copy()
                                                popt_c, xmin_c, xmax_c = plotter._fit_nss_cached(
                                                    tmp, which="TIREA", threshold_factor=2.0, use_cache=False)
                                                xs = np.linspace(float(xmin_c), float(xmax_c), 160)
                                                fig_comp.add_trace(go.Scatter(
                                                    x=xs, y=plotter.nss_model(xs, *popt_c),
                                                    mode="lines", name="NSS", line=dict(dash="dash", width=1.5),
                                                ))
                                            except Exception:
                                                pass

                                    # Puntos de los 2 bonos
                                    fig_comp.add_trace(go.Scatter(
                                        x=[dur_a], y=[_yield_pct_points(tir_a)],
                                        mode="markers", name=f"▶ {code_a}",
                                        marker=dict(size=14, color="red", symbol="diamond"),
                                        hovertemplate=f"{code_a}<br>Dur={dur_a:.3f}<br>TIREA={_yield_pct_points(tir_a):.2f}%<extra></extra>",
                                    ))
                                    fig_comp.add_trace(go.Scatter(
                                        x=[dur_b], y=[_yield_pct_points(tir_b)],
                                        mode="markers", name=f"▶ {code_b}",
                                        marker=dict(size=14, color="blue", symbol="diamond"),
                                        hovertemplate=f"{code_b}<br>Dur={dur_b:.3f}<br>TIREA={_yield_pct_points(tir_b):.2f}%<extra></extra>",
                                    ))

                                    fig_comp.update_layout(
                                        title=f"Comparación: {code_a} vs {code_b}",
                                        xaxis_title="Duration",
                                        yaxis_title="TIREA (%)",
                                        height=420,
                                        margin=dict(l=10, r=10, t=50, b=10),
                                        hovermode="closest",
                                    )
                                    _st_plotly(fig_comp)

                    except Exception as e:
                        st.error(f"Error al comparar: {e}")

    # ─────────────────────────
    # Breakeven Inflación
    # ─────────────────────────
    with tab_breakeven:
        st.subheader("Breakeven de Inflación — CER vs Tasa Fija")
        st.caption(
            "Compara la curva CER (tasa real) contra LECAP/Tasa Fija (tasa nominal) "
            "para obtener la inflación implícita (breakeven) por plazo.\n\n"
            "**Fisher**: (1 + nominal) = (1 + real) × (1 + breakeven)  →  "
            "**BE = (1 + TIR_nominal) / (1 + TIR_real) - 1**\n\n"
            "Los bonos CER toman su último ajuste CER ~10 días hábiles antes del vencimiento. "
            "Ese CER refleja la inflación MOM del mes *anterior* al de la fijación "
            "(ej: TZXO6 vence 30/10/26, CER fix ~mediados Sep, refleja inflación de Ago)."
        )

        col_be1, col_be2 = st.columns([1, 1])
        with col_be1:
            be_cer_key = st.selectbox(
                "Curva CER",
                options=["cer", "cerproy"],
                format_func=lambda k: {"cer": "CER (observado)", "cerproy": "CER Proyectado"}.get(k, k),
                key="be_cer_curve",
            )
        with col_be2:
            be_nom_key = st.selectbox(
                "Curva Nominal (Tasa Fija)",
                options=["lecap"],
                format_func=lambda k: {"lecap": "LECAP / Tasa Fija"}.get(k, k),
                key="be_nom_curve",
            )

        df_cer_be = load_curve_last_table(username, password, be_cer_key, plazo)
        df_lecap_be = load_curve_last_table(username, password, be_nom_key, plazo)

        # ── Proyección de inflación editable ──
        with st.expander("📊 Editar proyección de inflación MOM (%)", expanded=False):
            st.caption(
                "Modificá la proyección de inflación mensual. Al aplicar, se recalcula "
                "el CER proyectado y se actualiza en **todas las tabs** (Curvas CER Proy, "
                "Análisis Yields, Total Return, etc.)."
            )
            # Load current projection from indices.py
            import indices as _idx_module

            # Si hay un override custom en session_state, usarlo como base
            if "_custom_inflation_proy" in st.session_state:
                proy_base = st.session_state["_custom_inflation_proy"]
            else:
                proy_base = getattr(_idx_module, "proyeccion_inflacion_mensual", {})

            # Build editable dataframe
            proy_rows = []
            for mes_label, valor in proy_base.items():
                proy_rows.append({"Mes": mes_label, "Inflación MOM (%)": float(valor)})
            proy_df = pd.DataFrame(proy_rows)

            proy_edited = st.data_editor(
                proy_df,
                num_rows="dynamic",
                width="stretch",
                key="be_inflation_editor",
                column_config={
                    "Mes": st.column_config.TextColumn("Mes", disabled=True),
                    "Inflación MOM (%)": st.column_config.NumberColumn(
                        "Inflación MOM (%)",
                        min_value=-5.0,
                        max_value=30.0,
                        step=0.1,
                        format="%.1f",
                    ),
                },
            )

            # Detect changes vs original indices.py (not session override)
            orig_proy = getattr(_idx_module, "proyeccion_inflacion_mensual", {})
            orig_rows = [{"Mes": k, "Inflación MOM (%)": float(v)} for k, v in orig_proy.items()]
            orig_df = pd.DataFrame(orig_rows)
            is_custom = "_custom_inflation_proy" in st.session_state
            proy_changed = (proy_edited is not None and not proy_edited.equals(proy_df))

            if is_custom:
                st.info("📌 Usando proyección custom. Apretá 'Restaurar original' para volver.")
            if proy_changed:
                st.warning("⚠️ Proyección modificada — apretá 'Aplicar' para recalcular.")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                apply_clicked = st.button(
                    "🔄 Aplicar y recalcular CER proyectado", key="be_recalc",
                    type="primary", disabled=not proy_changed,
                )
            with col_btn2:
                restore_clicked = st.button(
                    "↩️ Restaurar original", key="be_restore",
                    disabled=not is_custom,
                )

            if restore_clicked:
                # Remove custom override → next rerun uses original
                if "_custom_inflation_proy" in st.session_state:
                    del st.session_state["_custom_inflation_proy"]
                _recalculate_cer_proyectado(orig_proy, _idx_module)
                st.cache_data.clear()
                st.rerun()

            if apply_clicked and proy_edited is not None:
                new_proy = {}
                for _, row in proy_edited.iterrows():
                    new_proy[row["Mes"]] = float(row["Inflación MOM (%)"])

                # Persist in session_state so it survives reruns
                st.session_state["_custom_inflation_proy"] = new_proy
                _recalculate_cer_proyectado(new_proy, _idx_module)
                st.cache_data.clear()
                st.rerun()

        # Apply custom inflation if exists in session_state (for EVERY rerun)
        _apply_custom_inflation_if_needed()

        if df_cer_be is None or df_cer_be.empty:
            st.info("Sin datos de curva CER (mercado cerrado o sin marketdata).")
        elif df_lecap_be is None or df_lecap_be.empty:
            st.info("Sin datos de curva LECAP/Tasa Fija (mercado cerrado o sin marketdata).")
        else:
            be_df = compute_breakeven_table(df_cer_be, df_lecap_be, plazo)
            if be_df.empty:
                st.warning("No se pudo calcular breakeven (pocos datos o NSS no ajustó).")
            else:
                # Show key metrics
                cols_show_be = [
                    "Código", "Vencimiento", "Duration",
                    "TIREA CER (real)", "TEM CER (real)",
                    "TIREA Nominal (NSS)", "TEM Nominal (NSS)",
                    "BE TIREA", "BE TEM",
                    "Fecha CER Fix", "Días a CER Fix", "Inflación ref.", "Días fija",
                ]
                cols_show_be = [c for c in cols_show_be if c in be_df.columns]
                be_show = be_df[cols_show_be].copy()

                st.dataframe(
                    style_breakeven(be_show),
                    width="stretch",
                    height=620,
                )

                # Breakeven chart
                if go is not None:
                    fig_be = go.Figure()

                    # CER real yield
                    fig_be.add_trace(go.Scatter(
                        x=be_df["Duration"],
                        y=_yield_pct_points(be_df["TIREA CER (real)"]),
                        mode="markers+text",
                        name=f"CER Real ({be_cer_key})",
                        text=be_df["Código"],
                        textposition="top center",
                        textfont=dict(size=8),
                        hovertemplate="%{text}<br>Dur=%{x:.3f}<br>Real=%{y:.2f}%<extra></extra>",
                        marker=dict(size=9, color="#2ecc71"),
                    ))

                    # Nominal NSS yield
                    fig_be.add_trace(go.Scatter(
                        x=be_df["Duration"],
                        y=_yield_pct_points(be_df["TIREA Nominal (NSS)"]),
                        mode="markers",
                        name=f"Nominal NSS ({be_nom_key})",
                        hovertemplate="Dur=%{x:.3f}<br>Nominal=%{y:.2f}%<extra></extra>",
                        marker=dict(size=7, color="#3498db", symbol="diamond"),
                    ))

                    # Breakeven
                    fig_be.add_trace(go.Scatter(
                        x=be_df["Duration"],
                        y=_yield_pct_points(be_df["BE TIREA"]),
                        mode="markers+lines",
                        name="Breakeven Inflación",
                        text=be_df["Código"],
                        hovertemplate="%{text}<br>Dur=%{x:.3f}<br>BE=%{y:.2f}%<extra></extra>",
                        marker=dict(size=10, color="#e74c3c"),
                        line=dict(dash="dot", width=2, color="#e74c3c"),
                    ))

                    # NSS fits as reference lines
                    try:
                        tmp_l = df_lecap_be[["Código", "Duration", "TIREA", "TEM"]].copy()
                        popt_l, xmin_l, xmax_l = plotter._fit_nss_cached(
                            tmp_l, which="TIREA", threshold_factor=2.0, use_cache=False)
                        if popt_l is not None:
                            xs = np.linspace(float(xmin_l), float(xmax_l), 120)
                            fig_be.add_trace(go.Scatter(
                                x=xs, y=plotter.nss_model(xs, *popt_l),
                                mode="lines", name="NSS Nominal",
                                line=dict(dash="dash", width=1.5, color="#3498db"),
                            ))
                    except Exception:
                        pass

                    try:
                        tmp_c = df_cer_be[["Código", "Duration", "TIREA", "TEM"]].copy()
                        popt_c, xmin_c, xmax_c = plotter._fit_nss_cached(
                            tmp_c, which="TIREA", threshold_factor=2.0, use_cache=False)
                        if popt_c is not None:
                            xs = np.linspace(float(xmin_c), float(xmax_c), 120)
                            fig_be.add_trace(go.Scatter(
                                x=xs, y=plotter.nss_model(xs, *popt_c),
                                mode="lines", name="NSS CER Real",
                                line=dict(dash="dash", width=1.5, color="#2ecc71"),
                            ))
                    except Exception:
                        pass

                    fig_be.update_layout(
                        title="Curvas CER (real) vs Nominal + Breakeven Inflación",
                        xaxis_title="Duration",
                        yaxis_title="TIREA (%)",
                        height=560,
                        margin=dict(l=10, r=10, t=60, b=10),
                        hovermode="closest",
                        legend_orientation="h",
                        legend_yanchor="bottom",
                        legend_y=1.02,
                        legend_xanchor="left",
                        legend_x=0,
                    )
                    _st_plotly(fig_be)

                # ── Gráfico original: BE TEM por instrumento (barras únicas, Plotly) ──
                if go is not None:
                    fig_be_tem = go.Figure()
                    be_tem_pct_orig = _yield_pct_points(be_df["BE TEM"])
                    fig_be_tem.add_trace(go.Bar(
                        x=be_df["Código"] if "Código" in be_df.columns else be_df.index,
                        y=be_tem_pct_orig,
                        name="BE TEM",
                        marker_color="#e74c3c",
                        text=[f"{v:.2f}%" if np.isfinite(v) else "" for v in be_tem_pct_orig],
                        textposition="outside",
                        textfont=dict(size=11),
                        hovertemplate="%{x}<br>BE TEM=%{y:.2f}%<extra></extra>",
                    ))
                    # Inflación observada
                    _df_inflam_orig = rentafija.inputs.get("inflamom")
                    if _df_inflam_orig is not None and not _df_inflam_orig.empty and "inflacionmom" in _df_inflam_orig.columns:
                        _hoy_orig = date.today()
                        _obs_orig = _df_inflam_orig[_df_inflam_orig.index < _hoy_orig.replace(day=1)]
                        if not _obs_orig.empty:
                            _obs_v = _obs_orig.iloc[-1]["inflacionmom"]
                            fig_be_tem.add_hline(
                                y=_obs_v, line_dash="dash", line_color="#ff9800",
                                annotation_text=f"Inflación MOM obs: {_obs_v:.1f}%",
                                annotation_position="top left",
                            )
                    fig_be_tem.update_layout(
                        title="Breakeven Inflación MOM (TEM) por instrumento CER",
                        xaxis_title="Instrumento", yaxis_title="BE TEM (%)",
                        height=420, margin=dict(l=10, r=10, t=60, b=10),
                    )
                    _st_plotly(fig_be_tem)

                # ── Gráfico estilo Delta: barras dobles π breakeven vs π sendero ──
                if go is not None:
                    # Sendero CPI = proyección inflación mensual del usuario
                    proy_infla_be = st.session_state.get("ars_proy_infla") or _PROY_INFLA_DEFAULT

                    be_tem_pct = _yield_pct_points(be_df["BE TEM"])

                    # Para cada bono CER, buscar la inflación del sendero al mismo vencimiento
                    def _sendero_para_bono(vto):
                        """Inflación MOM proyectada del mes de vencimiento del bono."""
                        if pd.isna(vto):
                            return np.nan
                        try:
                            vto_dt = pd.to_datetime(vto)
                            mes_lbl = vto_dt.strftime("%b-%y")
                            # Buscar en el dict de proyección
                            v = proy_infla_be.get(mes_lbl)
                            if v is not None:
                                return float(v)
                            # Si no está exacto, interpolar con el más cercano
                            meses = {pd.to_datetime(k, format="%b-%y"): float(val)
                                     for k, val in proy_infla_be.items()}
                            if not meses:
                                return np.nan
                            closest = min(meses.keys(), key=lambda d: abs(d - vto_dt))
                            return meses[closest]
                        except Exception:
                            return np.nan

                    sendero_vals = []
                    if "Vencimiento" in be_df.columns:
                        sendero_vals = [_sendero_para_bono(v) for v in be_df["Vencimiento"]]
                    else:
                        sendero_vals = [np.nan] * len(be_df)

                    # Pares CER vs tasa fija como subtítulo eje x
                    if "Código" in be_df.columns:
                        cer_codes = list(be_df["Código"].astype(str))
                    else:
                        cer_codes = [str(i) for i in range(len(be_df))]

                    # Buscar el lecap comparable (mismo mes de vencimiento)
                    pair_labels = []
                    if "Vencimiento" in be_df.columns and df_lecap_be is not None and not df_lecap_be.empty:
                        for vto in be_df["Vencimiento"]:
                            try:
                                vto_dt = pd.to_datetime(vto)
                                lec_vtos = pd.to_datetime(df_lecap_be.get("Vencimiento", pd.Series()), errors="coerce")
                                diffs = (lec_vtos - vto_dt).abs()
                                idx_min = diffs.idxmin()
                                pair_labels.append(f"vs {df_lecap_be.loc[idx_min,'Código']}" if "Código" in df_lecap_be.columns else "")
                            except Exception:
                                pair_labels.append("")
                    else:
                        pair_labels = [""] * len(cer_codes)

                    fig_be_bar = go.Figure()

                    # π breakeven (verde Delta)
                    # ── Colores Delta AM (imagen de referencia) ──────────────
                    _COLOR_MERCADO  = "#3E8C4B"   # verde Delta
                    _COLOR_DELTA_AM = "#1B3A6B"   # azul marino Delta

                    sendero_pct = [
                        float(v) if (v is not None and np.isfinite(float(v))) else None
                        for v in sendero_vals
                    ]

                    fig_be_bar = go.Figure()

                    # Barra Mercado (breakeven)
                    fig_be_bar.add_trace(go.Bar(
                        name="Mercado",
                        x=cer_codes,
                        y=[v for v in be_tem_pct],
                        marker_color=_COLOR_MERCADO,
                        text=[f"{v:.1f}%" if np.isfinite(v) else ""
                              for v in be_tem_pct],
                        textposition="outside",
                        textfont=dict(size=10, color=_COLOR_MERCADO, family="Arial"),
                        hovertemplate="%{x}<br>Mercado=%{y:.2f}%<extra></extra>",
                        width=0.35,
                    ))

                    # Barra Delta AM (sendero CPI proyectado)
                    fig_be_bar.add_trace(go.Bar(
                        name="Delta AM",
                        x=cer_codes,
                        y=sendero_pct,
                        marker_color=_COLOR_DELTA_AM,
                        text=[f"{v:.1f}%" if (v is not None and np.isfinite(v)) else ""
                              for v in sendero_pct],
                        textposition="outside",
                        textfont=dict(size=10, color=_COLOR_DELTA_AM, family="Arial"),
                        hovertemplate="%{x}<br>Delta AM=%{y:.2f}%<extra></extra>",
                        width=0.35,
                    ))

                    fig_be_bar.update_layout(
                        title=dict(
                            text="<b>Inflación Breakeven</b><br>"
                                 "<span style='font-size:13px;color:#555'>Promedio mensual por período</span>",
                            font=dict(size=16, color="#1B3A6B", family="Arial"),
                            x=0.5, xanchor="center", y=0.97,
                        ),
                        barmode="group",
                        bargap=0.30,
                        bargroupgap=0.04,
                        xaxis=dict(
                            ticktext=[f"{c}<br><span style='font-size:9px;color:#888'>{p}</span>"
                                      for c, p in zip(cer_codes, pair_labels)],
                            tickvals=cer_codes,
                            tickfont=dict(size=11, family="Arial", color="#1B3A6B"),
                            showgrid=False,
                            linecolor="rgba(27,58,107,0.2)",
                            linewidth=1,
                        ),
                        yaxis=dict(
                            tickformat=".1%",
                            tickfont=dict(size=11, family="Arial", color="#555"),
                            gridcolor="rgba(27,58,107,0.12)",
                            gridwidth=1,
                            zeroline=True,
                            zerolinecolor="rgba(27,58,107,0.2)",
                            zerolinewidth=1,
                            showline=False,
                            rangemode="tozero",
                        ),
                        legend=dict(
                            orientation="v",
                            x=0.88, y=0.98,
                            xanchor="left", yanchor="top",
                            bgcolor="rgba(255,255,255,0.9)",
                            bordercolor="rgba(27,58,107,0.2)",
                            borderwidth=1,
                            font=dict(size=11, family="Arial", color="#1B3A6B"),
                            itemsizing="constant",
                        ),
                        plot_bgcolor="white",
                        paper_bgcolor="white",
                        font=dict(family="Arial", color="#1B3A6B"),
                        height=480,
                        margin=dict(l=50, r=20, t=90, b=70),
                        uniformtext=dict(mode="hide", minsize=9),
                    )
                    _st_plotly(fig_be_bar)

                # ── Breakeven mensual por fecha de vencimiento ─────────────
                st.markdown("### Inflación Breakeven — Serie Mensual Implícita")
                st.caption("Para cada fin de mes: par CER vs Tasa Fija más cercano → inflación mensual breakeven implícita.")
                if go is not None and "Vencimiento" in be_df.columns and "BE TEM" in be_df.columns:
                    try:
                        df_be_ser = be_df[["Código","Vencimiento","BE TEM","Duration"]].copy()
                        df_be_ser = df_be_ser.dropna(subset=["Vencimiento","BE TEM"])
                        df_be_ser["Vencimiento"] = pd.to_datetime(df_be_ser["Vencimiento"], errors="coerce")
                        df_be_ser = df_be_ser.dropna(subset=["Vencimiento"])
                        df_be_ser["Mes"] = df_be_ser["Vencimiento"].dt.to_period("M").dt.to_timestamp("M")
                        # Per month: keep bond closest to end-of-month
                        df_be_ser["dias_a_eom"] = (df_be_ser["Vencimiento"] - df_be_ser["Mes"]).abs().dt.days
                        df_be_monthly = df_be_ser.sort_values("dias_a_eom").groupby("Mes").first().reset_index()
                        df_be_monthly = df_be_monthly.sort_values("Mes")
                        be_tem_pct2 = _yield_pct_points(df_be_monthly["BE TEM"])
                        fig_be_ser = go.Figure()
                        fig_be_ser.add_trace(go.Scatter(
                            x=df_be_monthly["Mes"],
                            y=be_tem_pct2,
                            mode="lines+markers+text",
                            name="BE Inflación MOM",
                            text=df_be_monthly["Código"],
                            textposition="top center",
                            textfont=dict(size=9),
                            line=dict(color="#1B3A6B", width=2.5),
                            marker=dict(size=8, color="#1B3A6B"),
                            hovertemplate="%{text}<br>%{x|%b-%y}<br>BE=%{y:.2f}%<extra></extra>",
                        ))
                        # Inflación observada como referencia
                        df_inf_obs = rentafija.inputs.get("inflamom_observado") or rentafija.inputs.get("inflamom")
                        if df_inf_obs is not None and not df_inf_obs.empty and "inflacionmom" in df_inf_obs.columns:
                            df_inf_hist = df_inf_obs.copy()
                            df_inf_hist.index = pd.to_datetime(df_inf_hist.index)
                            df_inf_hist = df_inf_hist[df_inf_hist.index < pd.Timestamp(date.today().replace(day=1))]
                            df_inf_hist = df_inf_hist.tail(24)
                            if not df_inf_hist.empty:
                                fig_be_ser.add_trace(go.Scatter(
                                    x=df_inf_hist.index,
                                    y=df_inf_hist["inflacionmom"],
                                    mode="lines+markers",
                                    name="Inflación MOM observada",
                                    line=dict(color="#2ECC71", width=2, dash="dot"),
                                    marker=dict(size=5, color="#2ECC71"),
                                    hovertemplate="%{x|%b-%y}<br>MOM=%{y:.2f}%<extra></extra>",
                                ))
                        fig_be_ser.update_layout(
                            title="Serie de Inflación Breakeven Mensual Implícita",
                            xaxis_title="Fecha de vencimiento (fin de mes)",
                            yaxis_title="BE Inflación MOM (%)",
                            height=480,
                            margin=dict(l=10, r=10, t=60, b=10),
                            hovermode="x unified",
                            plot_bgcolor="#0F1C2E",
                            paper_bgcolor="#0F1C2E",
                            font=dict(color="#FFFFFF"),
                            xaxis=dict(gridcolor="#1B3A6B", tickformat="%b-%y"),
                            yaxis=dict(gridcolor="#1B3A6B"),
                            legend=dict(orientation="h", y=1.02, x=0),
                        )
                        _st_plotly(fig_be_ser)
                    except Exception as e:
                        st.caption(f"No se pudo construir serie mensual: {e}")

                # Summary expander with methodology
                with st.expander("Metodología y supuestos", expanded=False):
                    st.markdown("""
**Breakeven de inflación** mide la inflación implícita que iguala el retorno de un bono CER
(ajustado por inflación) con un bono a tasa fija del mismo plazo.

**Fórmula Fisher**: `(1 + TIR_nominal) = (1 + TIR_real) × (1 + BE_inflación)`

**Particularidades CER:**
- Los bonos CER toman su índice CER con un *lag* de ~10 días hábiles antes de cada cupón/vencimiento
- El CER publicado del día 16 al 15 del mes siguiente refleja la inflación MOM del mes *anterior*
- Por lo tanto, un bono CER que vence en octubre (TZXO6) fija su CER a mediados de septiembre,
  que refleja la inflación de agosto
- Esto implica que los últimos ~10-15 días hábiles antes del vencimiento, el bono CER
  es efectivamente un bono a tasa fija (ya conocés el CER que vas a recibir)

**Columnas:**
- **TIREA CER (real)**: Yield real del bono CER sobre el índice CER
- **TIREA Nominal (NSS)**: Yield nominal interpolado de la curva LECAP a la misma duration
- **BE TIREA**: Breakeven inflación anualizado (TIREA)
- **BE TEM**: Breakeven inflación mensual (TEM) — comparable con inflación MOM
- **Fecha CER Fix**: Fecha en la que se fija el último CER para ese bono
- **Inflación ref.**: Mes de inflación que refleja ese CER
- **Días fija**: Cantidad de días en los que el bono CER es "tasa fija" (post CER fix)
""")


if __name__ == "__main__":
    main()