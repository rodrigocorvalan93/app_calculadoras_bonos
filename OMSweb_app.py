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

import copy
import os
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import MonthEnd

import OMSapi
import OMScauciones
import OMScredit
import OMSmktdata
import OMSnews
import OMSposiciones
import OMSprices
import OMSsecrets  # noqa: F401  — auto-carga secrets.txt a os.environ
import OMSsettings as cfg
import OMSticker
import plotter  # usa pct_series + NSS helpers
import rentafija
from dias_habiles import ar_holidays, siguiente_dia_habil_ar

# Universo de bonos
from especies import *
from especies import todos_los_bonos

OMScredit.init(todos_los_bonos)
from indices import (
    fx_status_text,
    get_fx_hoy,
    invalidate_fx_cache,
    refresh_a3500_in_rentafija,
)
from utils import tir_a_tna, tna_a_tir

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    go = None

if TYPE_CHECKING:
    import plotly.graph_objects as go


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
    threshold_factor: float = 3.0,
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

# ── NUEVO: Curvas donde ticker BYMA ≠ código Python del objeto bono ──
# Para corp_hdmep: PECIO (objeto Python) → PECIOD (ticker BYMA para marketdata)
# Para corp_hdcable: los códigos ya son los tickers C (BYCHC etc.) que existen en BONDS
CURVE_BYMA_REMAP: Dict[str, str] = {
    "corp_hdmep": "mep",    # PECIO -> PECIOD (O->D)
    "corp_hdcable": "cable", # BYCHO -> BYCHC (ya son los tickers C en la lista)
}


def _apply_curve_suffix(curve_key: str, base_code: str) -> str:
    suf = CURVE_EVAL_SUFFIX.get(str(curve_key), "")
    return f"{base_code}{suf}" if suf else base_code

def _byma_ticker_from_code(code: str, curve_key: str) -> str:
    """Convierte código Python -> ticker BYMA según curva."""
    remap = CURVE_BYMA_REMAP.get(curve_key)
    if remap == "mep":
        # ON MEP: xxxO -> xxxD (reemplazar última O por D)
        c = str(code)
        return c[:-1] + "D" if c.endswith("O") else c
    # Para cable: los códigos ya son los tickers C (BYCHC, etc.)
    return str(code)

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

        if bt == "corp_dlk":
            return rentafija.tir_a_tna(tirea, 90, 365)

        if bt in ("hdsob", "bopreal"):
            return rentafija.tir_a_tna(tirea, 180, 360)

        if bt == "dual":
            return rentafija.tir_a_tna(tirea, 30, 365)
        
        if bt in ("hdmep", "hdcable"):
            return rentafija.tir_a_tna(tirea, 180, 365)

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
    arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64")
    if arr.size == 0 or np.all(np.isnan(arr)):
        return -1.0, 1.0
    lim = float(np.nanmax(np.abs(arr)))
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

def _safe_median_pct(series, default: float = 40.0) -> float:
    """Mediana segura de una serie de yields (decimales) → porcentaje.

    Devuelve `default` si la serie es None, está vacía, o no tiene valores
    finitos. Evita el RuntimeWarning 'All-NaN slice encountered' de
    np.nanmedian cuando la columna viene toda en NaN (carga inicial del
    panel antes del primer tick de WS, mercado cerrado, etc.).
    """
    if series is None:
        return float(default)
    vals = pd.to_numeric(series, errors="coerce")
    if not vals.notna().any():
        return float(default)
    med = float(np.nanmedian(vals))
    return float(med * 100.0) if np.isfinite(med) else float(default)


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
# Market hours (BYMA: 10:30 a 17:00 hora Argentina, lun-vie)
# ──────────────────────────────────────────────────────────────────────

# Horario BYMA (hora local Argentina)
_BYMA_OPEN = (10, 30)   # 10:30
_BYMA_CLOSE = (17, 0)   # 17:00


def is_market_open(now: Optional[datetime] = None) -> bool:
    """True si el mercado BYMA está operativo (lun-vie, 10:30-17:00 AR,
    excluyendo feriados del calendario argentino de dias_habiles.ar_holidays).
    """
    if now is None:
        now = datetime.now()

    # Fin de semana
    if now.weekday() >= 5:
        return False

    # Feriado argentino
    if now.date() in ar_holidays:
        return False

    # Ventana horaria
    t_open = now.replace(hour=_BYMA_OPEN[0], minute=_BYMA_OPEN[1], second=0, microsecond=0)
    t_close = now.replace(hour=_BYMA_CLOSE[0], minute=_BYMA_CLOSE[1], second=0, microsecond=0)
    return t_open <= now <= t_close


def _effective_price_series(df: pd.DataFrame, last_col: str = "Last",
                            close_col: str = "Close") -> pd.Series:
    """Devuelve la serie de 'precio efectivo' para cálculos.

    Regla: si hay `Last` válido se usa; si no, se cae a `Close`.
    Esto permite que con mercado cerrado (o primeros minutos sin ticks)
    la app calcule TIREA/TNA/Duration sobre el último cierre conocido.
    """
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    if last_col in df.columns:
        last = pd.to_numeric(df[last_col], errors="coerce")
    else:
        last = pd.Series(np.nan, index=df.index, dtype="float64")

    if close_col in df.columns:
        close = pd.to_numeric(df[close_col], errors="coerce")
    else:
        close = pd.Series(np.nan, index=df.index, dtype="float64")

    # Prioridad: Last -> Close
    return last.where(last.notna() & np.isfinite(last), close)


def market_status_caption(plazo: str, auto_refresh: bool = False) -> str:
    """Construye el caption de estado de mercado (LIVE / CERRADO + timestamp + FX)."""
    now = datetime.now()
    ts = now.strftime("%H:%M:%S")
    is_open = is_market_open(now)

    try:
        fx_txt = fx_status_text()
    except Exception:
        fx_txt = ""

    if is_open:
        dot = "🔴 LIVE"
        estado = ""
    else:
        dot = "⚪ CERRADO"
        estado = " · calculando con Close del último cierre"

    prefix = f"{dot}  |  " if (auto_refresh or not is_open) else ""
    fx_part = f"  |  {fx_txt}" if fx_txt else ""
    return f"{prefix}Actualizado: {ts}  |  Plazo: {plazo}{estado}{fx_part}"


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
    CurveDef("dualcer", "Dual CER (base)", "dual"),


    # --- Corporativos ---
    CurveDef("corp_tamar", "Corp. TAMAR", "tamar"),
    CurveDef("corp_badlar", "Corp. BADLAR", "tamar"),
    CurveDef("corp_tasafija", "Corp. Tasa Fija", "lecap"),
    CurveDef("corp_uva", "Corp. UVA/CER", "cer"),
    CurveDef("corp_dlk", "Corp. Dólar Linked", "corp_dlk"),
    CurveDef("corp_hdmep", "Corp. USD MEP", "hdmep"),
    CurveDef("corp_hdcable", "Corp. USD Cable", "hdcable"),
]


def _codigo_obj(b) -> str:
    return (
        getattr(b, "ticker", None)
        or getattr(b, "codigo", None)
        or getattr(b, "symbol", None)
        or b.__class__.__name__
    )


# ──────────────────────────────────────────────────────────────────────
# Histórico BYMA (archivo local OneDrive)
# ──────────────────────────────────────────────────────────────────────

# Resolver ruta del histórico: se configura vía secrets.txt (env vars).
# No hay fallback hardcodeado para evitar exponer info interna en el repo.
_HISTORICO_FILENAME = "Delta - historico_byma_px_tasas.xlsx"


def _resolve_historico_path() -> Optional[str]:
    """Resuelve la ruta al Excel histórico.

    Config vía secrets.txt — prioridad:
    1. DELTA_HISTORICO_PATH (ruta completa al archivo).
    2. DELTA_HISTORICO_DIR  (carpeta) + filename default.
    3. DELTA_BASES_DIR      (carpeta común Carteras) + '..' + filename
                            (por si el histórico vive un nivel arriba de Carteras).
    """
    # 1) Ruta completa al archivo
    env = os.getenv("DELTA_HISTORICO_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env

    # 2) Carpeta override + filename
    env_dir = os.getenv("DELTA_HISTORICO_DIR")
    if env_dir:
        env_dir = os.path.expandvars(os.path.expanduser(env_dir))
        candidate = os.path.join(env_dir, _HISTORICO_FILENAME)
        if os.path.isfile(candidate):
            return candidate

    # 3) Derivar desde DELTA_BASES_DIR (Carteras → parent)
    env_bases = os.getenv("DELTA_BASES_DIR")
    if env_bases:
        env_bases = os.path.expandvars(os.path.expanduser(env_bases))
        candidate = os.path.join(os.path.dirname(env_bases), _HISTORICO_FILENAME)
        if os.path.isfile(candidate):
            return candidate

    return None


@st.cache_data(ttl=3600, show_spinner="Cargando histórico BYMA…")
def load_historico_byma() -> pd.DataFrame:
    """Carga el Excel histórico con TIREA/Precio/Duration por bono y fecha.

    Incluye limpieza de:
    - Duplicados exactos (Código, fecha) → conserva el último.
    - Filas muertas (TIREA/Duration/Paridad todas en 0) — capturas fallidas.
    - TIREA absurdas (>200% ó <-90%) — errores de escala de precio.
    """
    path = _resolve_historico_path()
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"Error leyendo histórico: {e}")
        return pd.DataFrame()

    df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"], errors="coerce")
    df = df.dropna(subset=["fecha_hoy", "Código"]).copy()
    df["Código"] = df["Código"].astype(str)

    for col in ("Last Price", "TIREA", "TNA", "TEM", "Paridad", "Duration", "tem_spread"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 1) Deduplicar por (Código, fecha) → quedarnos con el último registro del día
    df = df.sort_values(["Código", "fecha_hoy"]).drop_duplicates(
        subset=["Código", "fecha_hoy"], keep="last"
    )

    # 2) Filas muertas (todo 0 en las métricas clave)
    dead_mask = (
        (df["TIREA"].fillna(0) == 0) &
        (df["Duration"].fillna(0) == 0) &
        (df["Paridad"].fillna(0) == 0)
    )

    # 3) TIREAs absurdas (errores de captura: -100% floor del solver o escalas raras)
    extreme_mask = (df["TIREA"] > 2.0) | (df["TIREA"] <= -0.99)

    bad_mask = dead_mask | extreme_mask
    if bad_mask.any():
        df = df[~bad_mask].copy()

    df = df.sort_values(["Código", "fecha_hoy"]).reset_index(drop=True)
    return df


def _hist_codigos_disponibles(df_hist: pd.DataFrame) -> List[str]:
    if df_hist is None or df_hist.empty:
        return []
    return sorted(df_hist["Código"].unique().tolist())


def _hist_last_update(df_hist: pd.DataFrame) -> Optional[pd.Timestamp]:
    if df_hist is None or df_hist.empty:
        return None
    return df_hist["fecha_hoy"].max()


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

    # DUAL CER (base)
    dualcer = sorted({
        c for c, clas, _ in by_ind.get("Soberano ARS Dual CER/Tamar", [])
        if clas == "Soberano"
    })

    # DUAL TAMAR/VARIABLE (sufijo v)
    dualtamar = sorted({_apply_curve_suffix("dualtamar", c) for c in dualfija + dualcer})

    bonares = sorted({
        c for c, qpc in by_ind_clas.get(("Soberano USD Ley Argentina D", "Soberano"), [])
        if qpc == "DIRTY" and has(c)
    })

    bopreales = sorted({
        c for c, qpc in by_ind_clas.get(("Soberanos USD BCRA D", "Soberano"), [])
        if has(c)
    })

    # ── Corporativos ──────────────────────────────────────────────
    corp_tamar_set = set()
    corp_badlar_set = set()
    corp_tasafija_set = set()
    corp_uva_set = set()
    corp_hdmep_set = set()
    corp_hdcable_set = set()
    corp_dlk_set = set()

    for b in bonos:
        code = _codigo_obj(b)
        clas = (getattr(b, "clasificacion", None) or "").strip()
        qpc = (getattr(b, "quote_price_cnv", None) or "").strip().upper()
        if not code or not has(code):
            continue

        if clas == "Corporativo TAMAR":
            corp_tamar_set.add(code)
        elif clas == "Corporativo BADLAR":
            corp_badlar_set.add(code)
        elif clas == "Corporativo Tasa Fija":
            corp_tasafija_set.add(code)
        elif clas == "Corporativo UVA":
            corp_uva_set.add(code)
        elif clas == "Corporativo Dolar Linked":
            corp_dlk_set.add(code)
        elif clas == "Corporativo Hard Dolar MEP":
            corp_hdmep_set.add(code)
        elif clas == "Corporativo Hard Dolar":
            # Solo los que tienen versión DIRTY (ticker con C) disponible
            # O sea: los que están cargados CLEAN y tienen análogo C en BONDS
            byma_c = code[:-1] + "C" if code.endswith("O") else code
            if has(byma_c) and qpc == "CLEAN":
                corp_hdcable_set.add(byma_c)  # usamos el ticker DIRTY
            elif qpc == "DIRTY":
                corp_hdcable_set.add(code)  # ya está como dirty


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
        "dualcer": dualcer,
        "dualtamar": dualtamar,
        "corp_tamar": sorted(corp_tamar_set),
        "corp_badlar": sorted(corp_badlar_set),
        "corp_tasafija": sorted(corp_tasafija_set),
        "corp_uva": sorted(corp_uva_set),
        "corp_dlk": sorted(corp_dlk_set),
        "corp_hdmep": sorted(corp_hdmep_set),
        "corp_hdcable": sorted(corp_hdcable_set)
    }


# ──────────────────────────────────────────────────────────────────────
# Sesión + Marketdata — SHARED GLOBAL (multi-user safe, bymaapi-speed)
# ──────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_session(username: str, password: str):
    """Sesión autenticada (cache_resource para no loguear en cada rerun).
    Shared across all users since credentials are the same API account.

    Side effect: al crear sesión nueva, resetea la blacklist de símbolos
    muertos. Así si se reconecta después de un crash o cambio de credenciales,
    los primeros fetches pueden ver todos los símbolos (no quedan residuos
    de la sesión anterior)."""
    session = OMSapi.login(username, password)
    # Reset blacklist + grace period para que el primer fetch post-login
    # no herede estado de una sesión anterior.
    try:
        OMSmktdata.clear_dead_symbols()
    except Exception:
        pass
    return session


def _all_curve_symbols(plazo: str) -> List[str]:
    """Build the FULL list of symbols for ALL curves in one shot (like bymaapi.py)."""
    curves = build_curve_codes()
    all_md_codes: set = set()
    for curve_key, codes in curves.items():
        for c in codes:
            base = _md_code_from_calc_code(str(c))
            md = _byma_ticker_from_code(base, curve_key)
            all_md_codes.add(md)
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
    md_codes = [_byma_ticker_from_code(_md_code_from_calc_code(c), curve_key)
            for c in calc_codes]

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
    if curve_key in CURVE_EVAL_SUFFIX or curve_key in CURVE_BYMA_REMAP:
        snap["Código"] = snap["Código"].map(lambda x: md_to_calc.get(str(x), str(x)))

    return snap


@st.cache_data(ttl=TTL_METRICS, show_spinner=False)
def load_curve_last_table(username: str, password: str, curve_key: str, plazo: str) -> pd.DataFrame:
    snap = _load_curve_base(username, password, curve_key, plazo)
    if snap is None or snap.empty:
        return pd.DataFrame()

    # Normalización defensiva: el snapshot puede venir con mayúsculas, minúsculas
    # o mix según la versión de OMSprices. Detectamos y renombramos sólo lo
    # que existe realmente en el DataFrame.
    col_map_lower = {c.lower(): c for c in snap.columns}

    def _rename_if_exists(src_lower: str, dst: str):
        """Renombra src (case-insensitive) → dst si existe."""
        if src_lower in col_map_lower and col_map_lower[src_lower] != dst:
            snap.rename(columns={col_map_lower[src_lower]: dst}, inplace=True)
            col_map_lower[dst.lower()] = dst

    _rename_if_exists("close", "Close")
    _rename_if_exists("last", "Last")
    _rename_if_exists("variation", "Variación %")
    _rename_if_exists("volume", "Volumen")

    bond_type = next((c.bond_type for c in CURVES if c.key == curve_key), "lecap")
    settle = _settlement_date_str(plazo)

    codes_arr = snap["Código"].astype(str).to_numpy()
    # Precio efectivo para cálculos: Last si hay; si no, Close (mercado cerrado / feriado).
    price_eff = _effective_price_series(snap, last_col="Last", close_col="Close")
    price_arr = price_eff.to_numpy(dtype="float64")

    mdf = _parallel_metrics(codes_arr, price_arr, bond_type, settle)

    out = pd.concat([snap.reset_index(drop=True), mdf], axis=1)
    out = _sort_duration_nan_last(out, "Duration")

    out["tem_spread"] = pd.to_numeric(out.get("TEM"), errors="coerce").diff().fillna(0.0)

    # Margen TNA para curvas con tasa variable (TAMAR/BADLAR)
    if bond_type in ("tamar",):
        inp = rentafija.inputs
        # Determinar benchmark según el index de cada bono
        margen_col = []
        for code in out["Código"].astype(str).tolist():
            obj = _bond_obj(code)
            idx = getattr(obj, "index", None) if obj else None
            tipo = getattr(obj, "tipo_tasa_interes", None) if obj else None
            if tipo in ("VARIABLE", "VARIABLE_CAP") and idx:
                if idx == "TAMAR":
                    bench = inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean() / 100.0
                elif idx == "BADLAR":
                    bench = inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean() / 100.0
                else:
                    bench = 0.0
                tna_val = out.loc[out["Código"] == code, "TNA"]
                if not tna_val.empty:
                    tna_f = pd.to_numeric(tna_val.iloc[0], errors="coerce")
                    margen_col.append(tna_f - bench if np.isfinite(tna_f) else np.nan)
                else:
                    margen_col.append(np.nan)
            else:
                margen_col.append(np.nan)
        out["Margen TNA"] = margen_col

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
        "Margen TNA",
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
    # Precio efectivo: Last Price si hay; si no, Close (mercado cerrado / feriado).
    price_eff = _effective_price_series(snap, last_col="Last Price", close_col="Close")
    price_arr = price_eff.to_numpy(dtype="float64")
    m_last_df = _parallel_metrics(codes_arr, price_arr, bond_type, settle)

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

def _apply_variation_bar(sty: pd.io.formats.style.Styler, df: pd.DataFrame, col: str) -> pd.io.formats.style.Styler:
    """Aplica barra divergente verde/rojo + fondo a una columna de variación."""
    if col not in df.columns:
        return sty
    vmin, vmax = _bar_limits(df[col])
    lim = max(abs(vmin), abs(vmax))
    sty = sty.bar(subset=[col], align="mid", color=["#fa7a7a", "#8bf58b"], vmin=vmin, vmax=vmax)
    sty = sty.map(lambda x: _diverging_bg(x, lim), subset=[col])
    return sty


def _apply_color_by_variation(sty: pd.io.formats.style.Styler, df: pd.DataFrame, var_col: str, target_col: str) -> pd.io.formats.style.Styler:
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


def style_curvas(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Close": "{:,.4f}",
        "Last": "{:,.4f}",
        "Variación %": "{:+.2%}",
        "TIREA": "{:.2%}",
        "TNA": "{:.2%}",
        "TEM": "{:.2%}",
        "Paridad": "{:.2%}",
        "Duration": "{:.4f}",
        "tem_spread": "{:+.2%}",
        "Margen TNA": "{:+.2%}",
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
    return sty


def style_mercado(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Open": "{:,.4f}",
        "Close": "{:,.4f}",
        "Low": "{:,.4f}",
        "High": "{:,.4f}",
        "Bid Size": "{:,.0f}",
        "Bid Price": "{:,.4f}",
        "Bid TIREA": "{:.2%}",
        "Bid TEM": "{:.2%}",
        "Last Price": "{:,.4f}",
        "TIREA": "{:.2%}",
        "TEM": "{:.2%}",
        "Duration": "{:.4f}",
        "Offer Price": "{:,.4f}",
        "Offer TIREA": "{:.2%}",
        "Offer TEM": "{:.2%}",
        "Offer Size": "{:,.0f}",
        "Volumen": "{:,.0f}",
        "Variación %": "{:+.2%}",
        "Variación px": "{:+.4f}",
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

    return sty


def style_forwards(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style
    sty = df.style.format("{:.2f}%", na_rep="")

    # background_gradient se computa lazy en Styler._compute(); un try/except
    # acá NO lo atrapa. Si la matriz no tiene rango finito (todo NaN o un
    # único valor), pandas hace rng = smax - smin con NaN y dispara
    # RuntimeWarning("invalid value encountered in scalar multiply").
    flat = pd.to_numeric(pd.Series(df.values.ravel()), errors="coerce")
    finite = flat[np.isfinite(flat)]
    if len(finite) >= 2:
        vmin, vmax = float(finite.min()), float(finite.max())
        if vmin < vmax:
            sty = sty.background_gradient(
                cmap="Blues", axis=None, vmin=vmin, vmax=vmax,
            )

    sty = sty.map(lambda v: "background-color: transparent;" if pd.isna(v) else "")
    return sty



def style_total_return(df: pd.DataFrame, tr_col: str = "_tr_num") -> pd.io.formats.style.Styler:
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


def style_futuros(df: pd.DataFrame) -> pd.io.formats.style.Styler:
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

def _style_futuros_mercado(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Estilo para la tabla de mercado completa de futuros DLR.
    Min en azul sutil, May en violeta sutil, variaciones con barras."""
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Open": "{:,.4f}", "Close": "{:,.4f}", "High": "{:,.4f}", "Low": "{:,.4f}",
        "Last": "{:,.4f}", "Bid": "{:,.4f}", "Offer": "{:,.4f}",
        "Δ Last-Close": "{:+,.4f}",
        "Variación %": "{:+.2%}",
        "Bid Size": "{:,.0f}", "Offer Size": "{:,.0f}",
        "OI": "{:,.0f}", "Volumen": "{:,.0f}",
        "Dias Vto": "{:,.0f}",
        "Fecha Vto": lambda d: d.strftime("%d-%m-%Y") if isinstance(d, date) else "—",
        "Rdto Directo Bid": "{:+.2%}", "Rdto Directo Offer": "{:+.2%}",
        "TEM Bid": "{:.2%}", "TEM Offer": "{:.2%}",
        "TNA Bid": "{:.2%}", "TNA Offer": "{:.2%}",
        "TEA Bid": "{:.2%}", "TEA Offer": "{:.2%}",
    }
    sty = df.style.format(fmt, na_rep="—")

    # Coloreado por tipo (filas enteras, sutil)
    def _row_tipo(row):
        if row.get("Tipo") == "May":
            return ["background-color: rgba(155, 89, 182, 0.08);"] * len(row)
        return ["background-color: rgba(52, 152, 219, 0.06);"] * len(row)
    sty = sty.apply(_row_tipo, axis=1)

    # Barras + colores en variaciones
    sty = _apply_variation_bar(sty, df, "Variación %")
    sty = _apply_variation_bar(sty, df, "Δ Last-Close")
    sty = _apply_color_by_variation(sty, df, "Variación %", "Last")

    # Bid verde / Offer rojo en las columnas de book
    if "Bid" in df.columns:
        sty = sty.map(lambda v: "color: #1b8a3a; font-weight:600;" if pd.notna(v) else "",
                      subset=["Bid"])
    if "Offer" in df.columns:
        sty = sty.map(lambda v: "color: #b02a37; font-weight:600;" if pd.notna(v) else "",
                      subset=["Offer"])

    # Separadores visuales para agrupar zonas (book / tasas / vol)
    table_styles = []
    for col_anchor in ("Bid Size", "Rdto Directo Bid", "OI"):
        if col_anchor in df.columns:
            j = df.columns.get_loc(col_anchor)
            table_styles.append({"selector": f"th.col{j}", "props": "border-left: 2px solid #555;"})
            table_styles.append({"selector": f"td.col{j}", "props": "border-left: 2px solid #555;"})
    if table_styles:
        sty = sty.set_table_styles(table_styles, overwrite=False)

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


def _fwd_bond_filter(curve_key: str, codes: List[str], plazo: str) -> List[str]:
    """Renderiza checkboxes para filtrar bonos de una matriz de forwards.

    Devuelve la lista de códigos que el usuario dejó tildados. Por defecto
    todos vienen tildados. El estado persiste por (curve_key, plazo) gracias
    a las keys de los widgets.
    """
    if not codes:
        return list(codes)

    state_root = f"fwd_filter::{curve_key}::{plazo}"

    # Botones rápidos para tildar / destildar todo
    cbtn1, cbtn2, _spacer = st.columns([1, 1, 6])
    with cbtn1:
        if st.button("☑ Todos", key=f"{state_root}::all", use_container_width=True):
            for c in codes:
                st.session_state[f"{state_root}::{c}"] = True
            st.rerun()
    with cbtn2:
        if st.button("☐ Ninguno", key=f"{state_root}::none", use_container_width=True):
            for c in codes:
                st.session_state[f"{state_root}::{c}"] = False
            st.rerun()

    n_per_row = 8
    selected: List[str] = []
    for i in range(0, len(codes), n_per_row):
        chunk = codes[i:i + n_per_row]
        cols = st.columns(len(chunk))
        for j, code in enumerate(chunk):
            with cols[j]:
                checked = st.checkbox(code, value=True, key=f"{state_root}::{code}")
                if checked:
                    selected.append(code)
    return selected


# ──────────────────────────────────────────────────────────────────────
# Helpers cacheados para el what-if de forwards (performance)
# ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=TTL_METRICS, show_spinner=False)
def _wi_metrics_cached(
    codes_tuple: Tuple[str, ...],
    prices_tuple: Tuple[float, ...],
    bond_type: str,
    settle: Optional[str],
) -> pd.DataFrame:
    """Cachea _parallel_metrics por la tupla (codes, prices, bond_type, settle).

    Si el usuario vuelve a un vector de precios ya visto en la sesión, devuelve
    el resultado sin recomputar. Key hasheable = tupla de tuplas.
    """
    codes = np.asarray(codes_tuple, dtype=object)
    prices = np.asarray(prices_tuple, dtype="float64")
    return _parallel_metrics(codes, prices, bond_type, settle)


@st.cache_data(ttl=TTL_METRICS, show_spinner=False)
def _wi_forwards_matrix_cached(
    codes_tuple: Tuple[str, ...],
    tirea_tuple: Tuple[float, ...],
    duration_tuple: Tuple[float, ...],
) -> pd.DataFrame:
    """Cachea la matriz de forwards por (codes, TIREA, Duration). NaN se
    serializan como None para que la tupla sea hasheable y estable."""
    df = pd.DataFrame({
        "Código": list(codes_tuple),
        "TIREA": list(tirea_tuple),
        "Duration": list(duration_tuple),
    }).dropna(subset=["TIREA", "Duration"])
    if len(df) < 2:
        return pd.DataFrame()
    return plotter.matriz_forwards_tir(
        df, y_col="TIREA", code_col="Código", comp="ea", t_col="Duration",
    )


def _to_tuple_safe(values: np.ndarray) -> Tuple:
    """Convierte un array numérico en tupla hasheable, normalizando NaN→None."""
    out = []
    for v in values:
        if v is None:
            out.append(None)
        elif isinstance(v, float) and not np.isfinite(v):
            out.append(None)
        else:
            out.append(float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v)
    return tuple(out)



# ──────────────────────────────────────────────────────────────────────
# Gráficos (Plotly)
# ──────────────────────────────────────────────────────────────────────

def plot_curve_plotly(
    df_curve_last: pd.DataFrame,
    df_curve_mkt: Optional[pd.DataFrame] = None,
    title: str = "Curva",
    show_nss: bool = True,
    threshold_factor: float = 3.0,
    which: str = "TIREA",  # "TIREA" o "TEM"
) -> Tuple[Optional[go.Figure], Optional[np.ndarray]]:
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
            mode="markers+text",
            name=f"LAST ({which})",
            text=df.get("Código"),
            texttemplate="%{text} %{y:.1f}%",
            textposition="top center",
            textfont=dict(size=9),
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
def _breakeven_iter_tem(
    bond_obj_cer_base,
    price_cer_pct: float,
    tir_nominal_anual: float,
    settle_str: Optional[str],
    idx_module=None,
    tol: float = 1e-5,
    max_iter: int = 40,
) -> Optional[float]:
    """Breakeven de inflación por iteración (método correcto con sufijo `j`).

    Los bonos con sufijo `j` (TZX26j, TX28j, etc.) son la variante evaluada
    sobre CER PROYECTADO. Cuando cambiamos la proyección de inflación y
    pedimos `bond_j.calcula_tirea(precio_mkt)`, lo que devuelve es
    efectivamente la TIR nominal implícita (porque el CER proyectado
    expresa los flujos en pesos a fecha futura).

    Algoritmo:
      1. Buscamos el bono `j` correspondiente al bono CER base.
      2. Bisección sobre `i_mensual` (inflación constante futura):
         a) Inyectamos CER proyectado con esa inflación.
         b) Calculamos la TIREA del bono `j` al precio de mercado.
         c) Comparamos con `tir_nominal_anual` (TIR del LECAP vecino).
      3. `i*` donde TIREA(bono_j, px) == TIR_LECAP es el breakeven.

    Parámetros:
      bond_obj_cer_base: el objeto bono CER base (ej TZX26, no TZX26j).
      price_cer_pct: precio de mercado en % del nominal (ej 378.65).
      tir_nominal_anual: TIR objetivo (la del LECAP vecino, decimal).

    Retorna: i_mensual decimal (ej 0.023 = 2.3% TEM), o None si falla.
    """
    if idx_module is None:
        import indices as idx_module

    if (bond_obj_cer_base is None
        or not np.isfinite(price_cer_pct)
        or not np.isfinite(tir_nominal_anual)):
        return None

    # Resolver el bono `j` correspondiente.
    bond_j, _ = _resolve_bond_j(bond_obj_cer_base)
    if bond_j is None:
        return None

    target_tir_nom = float(tir_nominal_anual)

    # Backup del estado original de rentafija.inputs y de la proyección del módulo.
    # Sin este backup, _recalculate_cer_proyectado muta idx_module.proyeccion_inflacion_mensual
    # y la proyección "default" del usuario queda pisada al terminar el bootstrap.
    inp = rentafija.inputs
    original_cer = inp.get("cer_proyectado")
    original_uva = inp.get("uva_proyectado")
    original_inflamom = inp.get("inflamom")
    original_module_proy = dict(getattr(idx_module, "proyeccion_inflacion_mensual", {}))

    combined_df_cer = inp.get("CER")
    if combined_df_cer is None or combined_df_cer.empty:
        return None

    # Truncar proyección al vencimiento del bono + buffer (acelera ~10x)
    venc = getattr(bond_j, "vencimiento", None) or getattr(bond_obj_cer_base, "vencimiento", None)
    max_proj_date = (venc + relativedelta(months=2)) if venc else None

    try:
        def _tir_bono_j(i_mensual: float) -> float:
            """Inyecta inflación constante y devuelve TIREA del bono `j`."""
            today = date.today()
            # Horizonte limitado al vencimiento del bono (en vez de 36 meses fijos)
            if venc is not None:
                horizon_months = max(2, (venc.year - today.year) * 12 + (venc.month - today.month) + 2)
            else:
                horizon_months = 36
            proy = {}
            d = today.replace(day=1) + relativedelta(months=1)
            for _ in range(horizon_months):
                proy[d.strftime("%b-%y")] = float(i_mensual * 100.0)
                d = d + relativedelta(months=1)

            _recalculate_cer_proyectado(proy, idx_module, max_proj_date=max_proj_date)

            try:
                return float(bond_j.calcula_tirea(float(price_cer_pct) / 100.0, settle_str))
            except Exception:
                return float("nan")

        # Bracket amplio: Argentina tiene escenarios extremos y bonos muy cortos
        # pueden requerir i_mensual > 20% para alcanzar target.
        lo, hi = -0.05, 0.50
        f_lo = _tir_bono_j(lo) - target_tir_nom
        f_hi = _tir_bono_j(hi) - target_tir_nom

        if not (np.isfinite(f_lo) and np.isfinite(f_hi)):
            return None

        # Mayor inflación → mayor VR → mayor TIR nominal del bono j.
        # Así que f(i) = TIREA_j(i) − target debería ir de negativo a positivo.
        if f_lo * f_hi > 0:
            return None

        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            f_mid = _tir_bono_j(mid) - target_tir_nom
            if not np.isfinite(f_mid):
                return None
            if abs(f_mid) < tol:
                return mid
            if f_lo * f_mid < 0:
                hi = mid
                f_hi = f_mid
            else:
                lo = mid
                f_lo = f_mid

        return 0.5 * (lo + hi)

    finally:
        # Restaurar estado original (rentafija.inputs + idx_module.proyeccion_inflacion_mensual)
        if original_cer is not None:
            rentafija.inputs["cer_proyectado"] = original_cer
        if original_uva is not None:
            rentafija.inputs["uva_proyectado"] = original_uva
        if original_inflamom is not None:
            rentafija.inputs["inflamom"] = original_inflamom
        if original_module_proy:
            idx_module.proyeccion_inflacion_mensual = original_module_proy


# ──────────────────────────────────────────────────────────────────────
# Bootstrap de inflación implícita desde la curva CER vs LECAP
# ──────────────────────────────────────────────────────────────────────

# Umbral: si el CER fix está a menos de este número de días hábiles, el bono
# es demasiado corto para hacer bootstrap (su inflación de referencia ya está
# prácticamente fija o publicada). Para esos usamos Fisher directo.
BOOTSTRAP_MIN_BDAYS_TO_CER_FIX = 15


def _mes_ref_key(bond_obj) -> Optional[str]:
    """Devuelve la key mes-año en formato '%b-%y' que el bono espera inyectar
    como inflación de referencia. Ej: 'Abr-26'. None si no se puede resolver."""
    cer_fix = _cer_effective_maturity_date(bond_obj)
    if cer_fix is None:
        return None
    try:
        label_full = _inflation_month_for_cer_date(cer_fix)  # 'Abr-2026'
        return pd.to_datetime(label_full, format="%b-%Y").strftime("%b-%y")
    except Exception:
        return None


def _bdays_to_cer_fix(bond_obj) -> Optional[int]:
    """Días hábiles hasta el CER fix. None si no se puede calcular."""
    cer_fix = _cer_effective_maturity_date(bond_obj)
    if cer_fix is None:
        return None
    try:
        from dias_habiles import ar_holidays as _hol
        d = date.today()
        n = 0
        while d < cer_fix:
            d = d + relativedelta(days=1)
            if d.weekday() < 5 and d not in _hol:
                n += 1
        return n
    except Exception:
        # fallback: días calendario / 1.4 (aprox días hábiles)
        return int((cer_fix - date.today()).days / 1.4)


def _resolve_bond_j(bond_obj_cer_base):
    """Devuelve (bond_j, base_code_str). bond_j es None si no existe la variante `j`."""
    base_code = (
        getattr(bond_obj_cer_base, "ticker", None)
        or getattr(bond_obj_cer_base, "codigo", None)
        or bond_obj_cer_base.__class__.__name__
    )
    base_code = str(base_code)
    if base_code.lower().endswith("j"):
        return bond_obj_cer_base, base_code
    return globals().get(f"{base_code}j"), base_code


def _solve_month_inflation(
    bond_obj_cer_base,
    price_cer_pct: float,
    tir_target: float,
    mes_key: str,
    current_proy: dict,
    settle_str: Optional[str],
    idx_module,
    tol: float = 5e-5,
    max_iter: int = 40,
) -> Tuple[Optional[float], str]:
    """Resuelve la inflación del mes `mes_key` que hace que TIREA(bono_j, px) == tir_target.

    Se mueve SOLO `current_proy[mes_key]`, los demás meses quedan fijos.
    Retorna (valor_resuelto_decimal_o_None, motivo_diagnostico_str).
    """
    bond_j, base_code = _resolve_bond_j(bond_obj_cer_base)
    if bond_j is None:
        return None, f"sin variante `{base_code}j`"

    # Truncar el horizonte de CER proyectado al vencimiento del bono + buffer
    # (evita recalcular ~5 años de CER diario cuando sólo necesitamos hasta el fix)
    venc = getattr(bond_j, "vencimiento", None) or getattr(bond_obj_cer_base, "vencimiento", None)
    max_proj_date = (venc + relativedelta(months=2)) if venc else None

    def _tir_j_at(i_decimal: float) -> float:
        proy_try = dict(current_proy)
        proy_try[mes_key] = float(i_decimal * 100.0)  # dict lleva porcentaje
        _recalculate_cer_proyectado(proy_try, idx_module, max_proj_date=max_proj_date)
        try:
            return float(bond_j.calcula_tirea(float(price_cer_pct) / 100.0, settle_str))
        except Exception:
            return float("nan")

    # Bracket amplio para contemplar curvas de crédito y escenarios extremos
    lo, hi = -0.05, 0.50
    f_lo = _tir_j_at(lo) - tir_target
    f_hi = _tir_j_at(hi) - tir_target

    if not (np.isfinite(f_lo) and np.isfinite(f_hi)):
        return None, f"TIREA_j NaN (f_lo={f_lo}, f_hi={f_hi})"
    if f_lo * f_hi > 0:
        return None, (
            f"target {tir_target:.2%} fuera del bracket "
            f"[TIREA_j({lo:.0%})={f_lo + tir_target:.2%}, "
            f"TIREA_j({hi:.0%})={f_hi + tir_target:.2%}]"
        )

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = _tir_j_at(mid) - tir_target
        if not np.isfinite(f_mid):
            return None, "NaN en la bisección"
        if abs(f_mid) < tol:
            return mid, "OK"
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    return 0.5 * (lo + hi), "OK (max_iter)"


def compute_inflation_bootstrap(
    df_cer_last: pd.DataFrame,
    df_lecap_last: pd.DataFrame,
    plazo: str,
    idx_module=None,
) -> Dict[str, Any]:
    """Bootstrap de inflación implícita.

    Para cada bono CER con CER fix > BOOTSTRAP_MIN_BDAYS_TO_CER_FIX días hábiles:
      1. Identificar su mes de referencia.
      2. Encontrar el LECAP vecino por duration → TIR target.
      3. Resolver i* en ese mes que iguala TIREA(bono_j, px) con el target.

    Si varios bonos comparten mes → promedio ponderado por Volumen.
    Meses sin bono ancla → interpolación lineal con sus vecinos.

    Bonos demasiado cortos → Fisher directo (BE = (1+tir_nom)/(1+tir_real) - 1).

    Retorna dict con:
      - 'inflacion_implicita': dict {mes_key: i_decimal}
      - 'per_bond': lista con detalle por bono (código, mes ref, método, BE)
      - 'warnings': lista de avisos
    """
    if idx_module is None:
        import indices as idx_module

    if df_cer_last is None or df_cer_last.empty or df_lecap_last is None or df_lecap_last.empty:
        return {"inflacion_implicita": {}, "per_bond": [], "warnings": ["Curvas vacías"]}

    settle = _settlement_date_str(plazo)

    # Precomputar LECAP arrays para nearest-neighbor por duration
    lecap_durs = pd.to_numeric(df_lecap_last["Duration"], errors="coerce")
    lecap_tirs = pd.to_numeric(df_lecap_last["TIREA"], errors="coerce")
    lecap_codes = df_lecap_last["Código"].astype(str)
    ok_lecap = np.isfinite(lecap_durs) & np.isfinite(lecap_tirs)

    # Backup de estado (vamos a mutar rentafija.inputs y la proyección del módulo).
    # _recalculate_cer_proyectado también reasigna idx_module.proyeccion_inflacion_mensual,
    # así que hay que preservarla para volver al default del usuario al terminar.
    inp = rentafija.inputs
    backup = {
        "cer_proyectado": inp.get("cer_proyectado"),
        "uva_proyectado": inp.get("uva_proyectado"),
        "inflamom": inp.get("inflamom"),
    }
    backup_module_proy = dict(getattr(idx_module, "proyeccion_inflacion_mensual", {}))

    warnings_: List[str] = []
    per_bond_info: List[Dict[str, Any]] = []
    # Agrupamos los bonos por mes de referencia
    by_month: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    short_bonds: List[Dict[str, Any]] = []  # se resuelven por Fisher

    try:
        for _, row in df_cer_last.iterrows():
            code = str(row.get("Código", "")).strip()
            dur = pd.to_numeric(row.get("Duration"), errors="coerce")
            tirea_real = pd.to_numeric(row.get("TIREA"), errors="coerce")
            if not code or not np.isfinite(dur) or not np.isfinite(tirea_real):
                continue

            obj_base = _bond_obj(code)
            if obj_base is None:
                continue

            # Precio de mercado
            px_last = pd.to_numeric(row.get("Last"), errors="coerce")
            px_close = pd.to_numeric(row.get("Close"), errors="coerce")
            px = float(px_last if np.isfinite(px_last) else px_close)
            if not np.isfinite(px):
                continue

            volumen = float(pd.to_numeric(row.get("Volumen"), errors="coerce") or 0.0)

            # Target LECAP (nearest por duration)
            if not ok_lecap.any():
                continue
            sub_d = lecap_durs[ok_lecap]
            nidx = (sub_d - float(dur)).abs().idxmin()
            tir_target = float(lecap_tirs.loc[nidx])
            cod_target = str(lecap_codes.loc[nidx])

            # ¿Es corto? → Fisher directo, sin bootstrap
            bdays = _bdays_to_cer_fix(obj_base)
            if bdays is not None and bdays < BOOTSTRAP_MIN_BDAYS_TO_CER_FIX:
                # Fisher directo sobre TIREA anualizada
                be_tirea = (1.0 + tir_target) / (1.0 + float(tirea_real)) - 1.0
                be_tem_fisher = (1.0 + be_tirea) ** (30.0 / 360.0) - 1.0
                short_bonds.append({
                    "Código": code,
                    "Duration": float(dur),
                    "Volumen": volumen,
                    "Mes ref": _mes_ref_key(obj_base),
                    "Método": "Fisher (corto)",
                    "LECAP ref": cod_target,
                    "TIR target": tir_target,
                    "TIREA real": float(tirea_real),
                    "BE TEM": be_tem_fisher,
                    "bdays_to_fix": bdays,
                })
                continue

            # Pre-filtro: si el bono no tiene variante `j` no sirve iterar.
            # Va directo a Fisher (corto) para no malgastar 2 rebuilds de CER.
            bond_j_obj, _ = _resolve_bond_j(obj_base)
            if bond_j_obj is None:
                be_tirea = (1.0 + tir_target) / (1.0 + float(tirea_real)) - 1.0
                be_tem_fisher = (1.0 + be_tirea) ** (30.0 / 360.0) - 1.0
                short_bonds.append({
                    "Código": code,
                    "Duration": float(dur),
                    "Volumen": volumen,
                    "Mes ref": _mes_ref_key(obj_base),
                    "Método": "Fisher (sin `j`)",
                    "LECAP ref": cod_target,
                    "TIR target": tir_target,
                    "TIREA real": float(tirea_real),
                    "BE TEM": be_tem_fisher,
                    "bdays_to_fix": bdays,
                })
                warnings_.append(f"{code}: sin variante `{code}j`, resuelto por Fisher")
                continue

            # Bono para bootstrap: identificar mes de referencia
            mes_key = _mes_ref_key(obj_base)
            if mes_key is None:
                warnings_.append(f"{code}: no se pudo determinar el mes de referencia")
                continue

            by_month[mes_key].append({
                "code": code,
                "obj_base": obj_base,
                "px": px,
                "dur": float(dur),
                "volumen": volumen,
                "tir_target": tir_target,
                "cod_target": cod_target,
                "tirea_real": float(tirea_real),
                "bdays": bdays,
            })

        # Proyección base de arranque (combina observados de BCRA + la proy que esté cargada)
        base_proy = dict(getattr(idx_module, "proyeccion_inflacion_mensual", {}))

        # Ordenar meses temporalmente
        def _month_sort_key(k: str) -> date:
            try:
                return pd.to_datetime(k, format="%b-%y").date()
            except Exception:
                return date(2099, 1, 1)

        meses_ordenados = sorted(by_month.keys(), key=_month_sort_key)

        # Acá iremos fijando las inflaciones resueltas
        inflacion_resuelta: Dict[str, float] = {}  # {mes_key: i_decimal}

        for mes_key in meses_ordenados:
            bonos_mes = by_month[mes_key]

            # Estado de la proyección al momento de resolver este mes:
            #   - base_proy + meses ya resueltos (en porcentaje como espera _recalculate...)
            current_proy = dict(base_proy)
            for k, v in inflacion_resuelta.items():
                current_proy[k] = float(v * 100.0)

            resultados_mes: List[Dict[str, Any]] = []
            for b in bonos_mes:
                i_sol, motivo = _solve_month_inflation(
                    bond_obj_cer_base=b["obj_base"],
                    price_cer_pct=b["px"],
                    tir_target=b["tir_target"],
                    mes_key=mes_key,
                    current_proy=current_proy,
                    settle_str=settle,
                    idx_module=idx_module,
                )
                metodo = "Iter bootstrap"
                if i_sol is None:
                    # Fallback a Fisher si no bracketea, pero con mensaje específico
                    be_tirea = (1.0 + b["tir_target"]) / (1.0 + b["tirea_real"]) - 1.0
                    i_sol_tem = (1.0 + be_tirea) ** (30.0 / 360.0) - 1.0
                    i_sol = i_sol_tem
                    metodo = "Fisher (fallback)"
                    warnings_.append(f"{b['code']}: {motivo} — fallback Fisher")

                resultados_mes.append({
                    "code": b["code"],
                    "i_sol": i_sol,
                    "volumen": b["volumen"],
                    "metodo": metodo,
                    "cod_target": b["cod_target"],
                    "tir_target": b["tir_target"],
                    "tirea_real": b["tirea_real"],
                    "dur": b["dur"],
                    "bdays": b["bdays"],
                })

            # Promedio ponderado por volumen (opción 3 que elegiste)
            vols = np.array([r["volumen"] for r in resultados_mes], dtype="float64")
            i_vals = np.array([r["i_sol"] for r in resultados_mes], dtype="float64")
            vmask = np.isfinite(i_vals) & (vols > 0)
            if vmask.any():
                i_mes = float(np.average(i_vals[vmask], weights=vols[vmask]))
            elif np.isfinite(i_vals).any():
                i_mes = float(np.nanmean(i_vals))
            else:
                i_mes = float("nan")
                warnings_.append(f"{mes_key}: ningún bono convergió")

            inflacion_resuelta[mes_key] = i_mes

            for r in resultados_mes:
                per_bond_info.append({
                    "Código": r["code"],
                    "Duration": r["dur"],
                    "Mes ref": mes_key,
                    "Método": r["metodo"],
                    "LECAP ref": r["cod_target"],
                    "TIR target": r["tir_target"],
                    "TIREA real": r["tirea_real"],
                    "BE TEM": r["i_sol"],
                    "bdays_to_fix": r["bdays"],
                })

        # Agregar los bonos cortos al per_bond_info (sin modificar inflacion_resuelta)
        for sb in short_bonds:
            per_bond_info.append({
                "Código": sb["Código"],
                "Duration": sb["Duration"],
                "Mes ref": sb["Mes ref"],
                "Método": sb["Método"],
                "LECAP ref": sb["LECAP ref"],
                "TIR target": sb["TIR target"],
                "TIREA real": sb["TIREA real"],
                "BE TEM": sb["BE TEM"],
                "bdays_to_fix": sb["bdays_to_fix"],
            })

        # Interpolación lineal sobre meses sin ancla dentro del rango cubierto
        if inflacion_resuelta:
            meses_con_dato = sorted(
                [(pd.to_datetime(k, format="%b-%y").date(), k, v)
                 for k, v in inflacion_resuelta.items() if np.isfinite(v)],
                key=lambda x: x[0],
            )
            if len(meses_con_dato) >= 2:
                full_range = []
                cur = meses_con_dato[0][0]
                last = meses_con_dato[-1][0]
                while cur <= last:
                    full_range.append(cur)
                    cur = (cur.replace(day=1) + relativedelta(months=1)) - relativedelta(days=1)
                    cur = cur.replace(day=28) + relativedelta(days=4)
                    cur = cur.replace(day=1)
                # Simplificamos: generamos mes a mes
                full_range = []
                d0 = meses_con_dato[0][0].replace(day=1)
                d1 = meses_con_dato[-1][0].replace(day=1)
                while d0 <= d1:
                    full_range.append(d0)
                    d0 = d0 + relativedelta(months=1)

                xs = np.array([d.toordinal() for d, _, _ in meses_con_dato], dtype="float64")
                ys = np.array([v for _, _, v in meses_con_dato], dtype="float64")

                for d in full_range:
                    k = d.strftime("%b-%y")
                    if k not in inflacion_resuelta or not np.isfinite(inflacion_resuelta.get(k, np.nan)):
                        # interpolar
                        inflacion_resuelta[k] = float(np.interp(d.toordinal(), xs, ys))

        return {
            "inflacion_implicita": inflacion_resuelta,
            "per_bond": per_bond_info,
            "warnings": warnings_,
        }

    finally:
        # Restaurar estado original (rentafija.inputs + proyección del módulo)
        for k, v in backup.items():
            if v is not None:
                rentafija.inputs[k] = v
        if backup_module_proy:
            idx_module.proyeccion_inflacion_mensual = backup_module_proy


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
    method: str = "fisher",  # "fisher" | "iter" | "both"
) -> pd.DataFrame:
    """Computes inflation breakeven for each CER bond by matching
    duration against the LECAP/tasa fija curve (NSS interpolated).

    method:
      - "fisher": BE_TEM = (1 + TIR_nom) / (1 + TIR_real) − 1 — anualizado y mensualizado.
      - "iter":   Iteración de inflación mensual constante hasta que la TIR nominal
                  implícita del CER coincida con la TIR del LECAP de misma duration.
                  Más preciso para bonos cortos donde Fisher distorsiona.
      - "both":   Calcula los dos métodos y devuelve ambas columnas.
    """
    if (df_cer_last is None or df_cer_last.empty or
        df_lecap_last is None or df_lecap_last.empty):
        return pd.DataFrame()

    # NSS sobre LECAP para interpolación
    try:
        tmp_lecap = df_lecap_last[["Código", "Duration", "TIREA", "TEM"]].copy()
        popt_lecap, xmin_l, xmax_l = plotter._fit_nss_cached(
            tmp_lecap, which="TIREA", threshold_factor=3.0, use_cache=False)
    except Exception:
        return pd.DataFrame()

    if popt_lecap is None:
        return pd.DataFrame()

    # NSS CER (referencia, opcional)
    try:
        tmp_cer = df_cer_last[["Código", "Duration", "TIREA", "TEM"]].copy()
        popt_cer, xmin_c, xmax_c = plotter._fit_nss_cached(
            tmp_cer, which="TIREA", threshold_factor=3.0, use_cache=False)
    except Exception:
        popt_cer = None

    settle = _settlement_date_str(plazo)
    rows = []

    # Pre-armar índices para nearest neighbor sobre LECAP
    lecap_durs = pd.to_numeric(df_lecap_last["Duration"], errors="coerce")
    lecap_tirs = pd.to_numeric(df_lecap_last["TIREA"], errors="coerce")
    lecap_codes = df_lecap_last["Código"].astype(str)
    ok_lecap = np.isfinite(lecap_durs) & np.isfinite(lecap_tirs)

    do_iter = method in ("iter", "both")
    do_fisher = method in ("fisher", "both")

    for _, row in df_cer_last.iterrows():
        code = str(row.get("Código", "")).strip()
        dur = row.get("Duration")
        tirea_real = row.get("TIREA")
        tem_real = row.get("TEM")

        if not code or not np.isfinite(dur) or not np.isfinite(tirea_real):
            continue

        bond_obj = _bond_obj(code)
        vencimiento = getattr(bond_obj, "vencimiento", None) if bond_obj else None
        cer_eff_date = _cer_effective_maturity_date(bond_obj)
        infla_month = _inflation_month_for_cer_date(cer_eff_date) if cer_eff_date else "—"

        # (1) TIR nominal por NSS
        dur_clipped = np.clip(float(dur), float(xmin_l), float(xmax_l))
        nominal_yield_pct = float(plotter.nss_model(np.array([dur_clipped]), *popt_lecap)[0])
        nominal_yield = nominal_yield_pct / 100.0

        # (2) TIR nominal por vecino más cercano (sin NSS)
        nominal_nearest = np.nan
        nominal_nearest_code = ""
        if ok_lecap.any():
            sub_durs = lecap_durs[ok_lecap]
            nearest_idx = (sub_durs - float(dur)).abs().idxmin()
            nominal_nearest = float(lecap_tirs.loc[nearest_idx])
            nominal_nearest_code = str(lecap_codes.loc[nearest_idx])

        # (3) Breakeven Fisher (dos versiones: NSS y nearest)
        be_tirea_nss = be_tem_nss = np.nan
        be_tirea_near = be_tem_near = np.nan

        if do_fisher:
            if np.isfinite(nominal_yield) and np.isfinite(tirea_real):
                be_tirea_nss = (1.0 + nominal_yield) / (1.0 + tirea_real) - 1.0
                be_tem_nss = (1.0 + be_tirea_nss) ** (30.0 / 360.0) - 1.0
            if np.isfinite(nominal_nearest) and np.isfinite(tirea_real):
                be_tirea_near = (1.0 + nominal_nearest) / (1.0 + tirea_real) - 1.0
                be_tem_near = (1.0 + be_tirea_near) ** (30.0 / 360.0) - 1.0

        # (4) Breakeven por iteración — sobre bono nominal MÁS CERCANO
        be_tem_iter = np.nan
        if do_iter and bond_obj is not None and np.isfinite(nominal_nearest):
            price_cer_pct = getattr(bond_obj, "precio", np.nan)
            if not np.isfinite(price_cer_pct):
                price_cer_pct = float(pd.to_numeric(row.get("Last") or row.get("Close"), errors="coerce"))
            if np.isfinite(price_cer_pct):
                try:
                    _iter_result = _breakeven_iter_tem(
                        bond_obj_cer_base=bond_obj,
                        price_cer_pct=price_cer_pct * 100.0 if price_cer_pct < 10 else price_cer_pct,
                        tir_nominal_anual=float(nominal_nearest),
                        settle_str=settle,
                    )
                    be_tem_iter = float(_iter_result) if _iter_result is not None else np.nan
                except Exception:
                    be_tem_iter = np.nan

        # Días a fixing
        today = date.today()
        days_to_mat = (vencimiento - today).days if vencimiento else np.nan
        days_to_cer_fix = (cer_eff_date - today).days if cer_eff_date else np.nan
        days_fixed = (days_to_mat - days_to_cer_fix) if (
            np.isfinite(days_to_mat) and np.isfinite(days_to_cer_fix)
        ) else np.nan

        rows.append({
            "Código": code,
            "Vencimiento": vencimiento,
            "Duration": dur,
            "TIREA CER (real)": tirea_real,
            "TEM CER (real)": tem_real if np.isfinite(tem_real) else np.nan,
            "TIREA Nominal (NSS)": nominal_yield,
            "TIR Nom. (vecino)": nominal_nearest,
            "Bono ref.": nominal_nearest_code,
            "BE TIREA (Fisher NSS)": be_tirea_nss,
            "BE TEM (Fisher NSS)": be_tem_nss,
            "BE TEM (Fisher vecino)": be_tem_near,
            "BE TEM (Iter)": be_tem_iter,
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


def style_breakeven(df: pd.DataFrame) -> pd.io.formats.style.Styler:
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
        "TIR Nom. (vecino)": "{:.2%}",
        "BE TEM (Fisher NSS)": "{:.2%}",
        "BE TEM (Fisher vecino)": "{:.2%}",
        "BE TEM (Iter)": "{:.2%}"
    }

    sty = df.style.format(fmt, na_rep="—")

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
    
    def _fecha_str(f) -> str:
        if f is None:
            return ""
        try:
            return f.strftime("%d/%m/%Y")
        except Exception:
            return str(f)

    # A3500
    f, v = _last_val("a3500", "tca3500")
    if v is not None:
        st.sidebar.metric("A3500 (mayorista)", f"{v:,.2f}", delta=f"al {_fecha_str(f)}")

    # Badlar
    f, v = _last_val("badlar", "BADLAR")
    if v is not None:
        st.sidebar.metric("Badlar", f"{v:.4f}%", delta=f"al {_fecha_str(f)}")

    # Tamar
    f, v = _last_val("tamar", "TAMAR")
    tamar_5d = tamar_10d = tamar_tem = None
    if v is not None:
        st.sidebar.metric("Tamar", f"{v:.4f}%", delta=f"al {_fecha_str(f)}")
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
        st.sidebar.metric("CER", f"{v:,.5f}", delta=f"al {_fecha_str(f)}")

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
        st.sidebar.metric("UVA", f"{v:,.2f}", delta=f"al {_fecha_str(f)}")


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

def _recalculate_cer_proyectado(new_proy: dict, idx_module=None, max_proj_date=None):
    """Recalculate CER proyectado from scratch using a custom inflation vector
    and inject it into rentafija.inputs so ALL tabs use the new CER.

    This is the critical function: it rebuilds the daily CER series using
    calcular_CER_diario_proyectado() from indices.py and replaces the
    'cer_proyectado', 'inflamom', and 'uva_proyectado' entries in
    rentafija.inputs — which is the global dict that every bond object
    reads when it calls generate_cashflows() with ajuste='CER PROYECTADO'.

    Parámetros:
      max_proj_date: si se provee (date), trunca la proyección a esa fecha
        + 1 mes (suficiente para bonos con fix antes de esa fecha).
        Acelera significativamente el bootstrap porque calcular_CER_diario_proyectado
        es un loop Python sobre días y proyectar 5 años vs 6 meses es ~10x más lento.
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

    # Truncar el horizonte si nos pidieron acelerar (bootstrap por bono)
    if max_proj_date is not None:
        cutoff = max_proj_date + relativedelta(months=1)
        df_inflamom_new = df_inflamom_new[df_inflamom_new.index <= cutoff]

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

    # Mutación controlada del dict del módulo. compute_inflation_bootstrap
    # y _breakeven_iter_tem hacen backup/restore en finally, pero si algún caller
    # sólo quiere aplicar una proyección definitiva (ej: Aplicar curva implícita),
    # este write queda como el nuevo default.
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

# ──────────────────────────────────────────────────────────────────────
# YAS — Análisis de Yields (función nivel módulo para estabilidad de fragment)
# ──────────────────────────────────────────────────────────────────────

@st.fragment
def _render_yas(username, password, plazo, curve_labels):
    """Cuerpo del tab YAS decorado como @st.fragment a nivel módulo.

    CRÍTICO: el @st.fragment DEBE estar sobre la función que CONTIENE los
    widgets (no sobre un wrapper). Si los widgets están en una función y
    el @st.fragment está en otra, Streamlit no asocia widgets↔fragment,
    y los cambios NO disparan re-ejecución."""
    # [DIAGNÓSTICO] — este print indica que el fragment se re-ejecutó
    print(f"[YAS fragment] re-exec @ {datetime.now().strftime('%H:%M:%S.%f')[:-3]}", flush=True)
    st.subheader("Análisis de Yields (YAS)")
    st.caption("Ingresá Precio, TIR, TNA o Margen → obtenés las métricas del bono.")

    _all_codes_yas = _all_bond_codes()
    if not _all_codes_yas:
        st.info("No hay bonos disponibles en el universo.")
    else:
        col_sel, col_inp = st.columns([1, 2])

        with col_sel:
            yas_code = st.selectbox("Bono", options=_all_codes_yas, key="yas_bond")
            yas_mode = st.radio(
                "Input",
                options=["Precio", "TIREA", "TNA", "Margen TNA"],
                horizontal=True,
                key="yas_mode",
            )
            yas_nominales = st.number_input(
                "VN (nominales)", value=1_000_000, step=100_000, key="yas_nom",
            )

        # [DIAGNÓSTICO] — log del bono leído para detectar si el
        # widget cambió pero el fragment no respondió
        print(f"[YAS fragment] yas_code={yas_code}, mode={yas_mode}", flush=True)

        bond_obj_yas = _bond_obj(yas_code)
        settle_yas_default = _settlement_date_str(plazo)  # dd/mm/YYYY o None para CI

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
            else:
                yas_val = st.number_input("Margen TNA (decimal, ej 0.02)", value=0.02, step=0.005, format="%.6f", key="yas_val_m")
                mode_key = "margen"

            # ── Overrides opcionales (mismo patrón que .genera_ticket) ──
            # Settlement: por defecto usa el plazo activo; se puede sobreescribir.
            ovr_cols = st.columns(2)
            with ovr_cols[0]:
                use_custom_settle = st.checkbox(
                    "Settlement custom", value=False, key="yas_ovr_settle",
                    help="Por defecto usa el plazo activo. Activá para elegir fecha.",
                )
            settle_yas = settle_yas_default
            if use_custom_settle:
                # Default del date_input: hoy si CI, sino el default del plazo
                try:
                    if settle_yas_default:
                        _d0 = datetime.strptime(settle_yas_default, "%d/%m/%Y").date()
                    else:
                        _d0 = date.today()
                except Exception:
                    _d0 = date.today()
                with ovr_cols[1]:
                    _d_sel = st.date_input(
                        "Fecha de liquidación", value=_d0,
                        format="DD/MM/YYYY", key="yas_settle_date",
                    )
                settle_yas = _d_sel.strftime("%d/%m/%Y") if _d_sel else settle_yas_default

            # FX: editable siempre (útil para DLK y en general para sensibilizar TC)
            # Se muestra sugerencia del A3500 hoy si está disponible.
            yas_tc = None
            _fx_default = 1300.0
            try:
                # Prefer get_fx_hoy (waterfall MAE → BYMA DLR → serie A3500)
                _v = get_fx_hoy(session=get_session(username, password))
                if _v is not None and np.isfinite(float(_v)) and float(_v) > 0:
                    _fx_default = float(_v)
            except Exception:
                try:
                    # Fallback: última fila de rentafija.inputs['a3500']
                    _df_a3500 = rentafija.inputs.get("a3500")
                    if _df_a3500 is not None and len(_df_a3500) > 0:
                        _v2 = float(_df_a3500.iloc[-1]["tca3500"])
                        if np.isfinite(_v2) and _v2 > 0:
                            _fx_default = _v2
                except Exception:
                    pass
            _is_dlk = bool(bond_obj_yas and getattr(bond_obj_yas, "ajuste_sobre_capital", None) == "DLK")
            tc_cols = st.columns(2)
            with tc_cols[0]:
                use_custom_fx = st.checkbox(
                    "TC aplicable (FX)", value=_is_dlk, key="yas_ovr_fx",
                    help="Necesario para DLK; opcional en otros bonos para sensibilidad.",
                )
            if use_custom_fx:
                with tc_cols[1]:
                    yas_tc = st.number_input(
                        "TC (A3500)", value=_fx_default, step=0.5,
                        format="%.4f", key="yas_tc",
                    )

        # ── Cálculo directo, sin fragment ni spinner ──
        # El flow es idéntico a bymaapi.py: obj.genera_ticket(...)
        import time as _tp
        _t_yas_0 = _tp.perf_counter()

        if bond_obj_yas is None:
            st.error(f"Bono {yas_code} no encontrado en rentafija.")
        else:
            try:
                ticket_df_yas = _ticket_raw(yas_code, mode_key, yas_val, yas_nominales, settle_yas, yas_tc)
                _t_yas_1 = _tp.perf_counter()

                tirea_y = float(getattr(bond_obj_yas, "tirea", np.nan))
                tna_y = float(getattr(bond_obj_yas, "tna", np.nan))
                tem_y = (1 + tirea_y) ** (30 / 360) - 1 if np.isfinite(tirea_y) else np.nan
                dur_y = bond_obj_yas.calcula_duration(tirea_y, settle_yas) if np.isfinite(tirea_y) else np.nan
                par_y = float(getattr(bond_obj_yas, "paridad", np.nan))
                ic_y = float(getattr(bond_obj_yas, "intereses_corridos", np.nan))
                dd_y = getattr(bond_obj_yas, "dias_corridos", np.nan)
                vr_y = float(getattr(bond_obj_yas, "valor_residual", np.nan))
                px_y = float(getattr(bond_obj_yas, "precio", np.nan))
                moneda_y = getattr(bond_obj_yas, "moneda", "")
                vto_y = getattr(bond_obj_yas, "vencimiento", None)
                fl_y = getattr(bond_obj_yas, "fecha_settlement", None)
                nombre_y = getattr(bond_obj_yas, "nombre_security", yas_code)

                _t_yas_2 = _tp.perf_counter()
                print(f"[YAS {yas_code}] ticket={1000*(_t_yas_1-_t_yas_0):.0f}ms attrs={1000*(_t_yas_2-_t_yas_1):.0f}ms", flush=True)

                # ── Display ──
                st.markdown("---")
                hdr1, hdr2, hdr3 = st.columns(3)
                with hdr1:
                    st.markdown(f"### {yas_code}")
                    st.caption(nombre_y)
                with hdr2:
                    st.caption(f"Vto: {vto_y.strftime('%d/%m/%Y') if vto_y else '—'}")
                    st.caption(f"Settle: {fl_y.strftime('%d/%m/%Y') if fl_y else '—'}")
                with hdr3:
                    st.caption(f"Moneda: {moneda_y}")

                m1, m2, m3, m4, m5 = st.columns(5)
                with m1:
                    st.metric("Precio", f"{px_y:.4f}" if np.isfinite(px_y) else "—")
                with m2:
                    st.metric("TIREA", f"{tirea_y:.4%}" if np.isfinite(tirea_y) else "—")
                with m3:
                    st.metric("TNA", f"{tna_y:.4%}" if np.isfinite(tna_y) else "—")
                with m4:
                    st.metric("TEM", f"{tem_y:.4%}" if np.isfinite(tem_y) else "—")
                with m5:
                    st.metric("Duration", f"{dur_y:.4f}" if np.isfinite(dur_y) else "—")

                s1, s2, s3, s4 = st.columns(4)
                with s1:
                    # paridad/valor_residual ya vienen expresados como porcentaje (100.0 = 100%)
                    st.metric("Paridad", f"{par_y:.2f}%" if np.isfinite(par_y) else "—")
                with s2:
                    st.metric("Int. Corridos", f"{ic_y:.6f}" if np.isfinite(ic_y) else "—")
                with s3:
                    st.metric("Días Dev.", f"{dd_y}" if dd_y is not None else "—")
                with s4:
                    st.metric("Val. Residual", f"{vr_y:.2f}%" if np.isfinite(vr_y) else "—")

                with st.expander("Ver ticket completo (DataFrame)", expanded=False):
                    if ticket_df_yas is not None:
                        # Cast columnas object-mixed a str para evitar ArrowTypeError
                        # (comparar_* / genera_ticket hacen concat con tipos heterogéneos)
                        _show = ticket_df_yas.copy()
                        for _col in _show.columns:
                            if _show[_col].dtype == object:
                                _show[_col] = _show[_col].astype(str)
                        st.dataframe(_show, width="stretch")
                    else:
                        st.info("No se pudo generar el ticket.")

                # Gráfico de la curva (lazy - sólo si se abre)
                with st.expander("📈 Ver en la curva (NSS)", expanded=False):
                    if go is not None and np.isfinite(dur_y) and np.isfinite(tirea_y):
                        curve_key_yas = _find_curve_for_bond(yas_code)
                        if curve_key_yas:
                            with st.spinner(f"Cargando curva…"):
                                df_curve_yas = load_curve_last_table(username, password, curve_key_yas, plazo)
                            if df_curve_yas is not None and not df_curve_yas.empty:
                                fig_yas = go.Figure()
                                y_pct_y = _yield_pct_points(df_curve_yas["TIREA"])
                                fig_yas.add_trace(go.Scatter(
                                    x=df_curve_yas["Duration"], y=y_pct_y, mode="markers+text",
                                    name=f"Curva {curve_labels.get(curve_key_yas, curve_key_yas)}",
                                    text=df_curve_yas["Código"],
                                    texttemplate="%{text} %{y:.1f}%",
                                    textposition="top center",
                                    textfont=dict(size=9),
                                    hovertemplate="%{text}<br>Dur=%{x:.3f}<br>TIREA=%{y:.2f}%<extra></extra>",
                                    marker=dict(size=8, opacity=0.6),
                                ))
                                try:
                                    tmp = df_curve_yas[["Código", "Duration", "TIREA", "TEM"]].copy()
                                    popt_y, xmin_y, xmax_y = plotter._fit_nss_cached(
                                        tmp, which="TIREA", threshold_factor=3.0, use_cache=True,
                                    )
                                    xs_y = np.linspace(float(xmin_y), float(xmax_y), 160)
                                    ys_y = plotter.nss_model(xs_y, *popt_y)
                                    fig_yas.add_trace(go.Scatter(
                                        x=xs_y, y=ys_y, mode="lines", name="NSS",
                                        line=dict(dash="dash", width=1.5),
                                    ))
                                except Exception:
                                    pass
                                tirea_pct_y = _yield_pct_points(tirea_y)
                                fig_yas.add_trace(go.Scatter(
                                    x=[dur_y], y=[tirea_pct_y], mode="markers",
                                    name=f"▶ {yas_code}",
                                    marker=dict(size=14, color="red", symbol="diamond"),
                                ))
                                fig_yas.update_layout(
                                    title=f"{yas_code} en curva {curve_labels.get(curve_key_yas, curve_key_yas)} — {plazo}",
                                    xaxis_title="Duration", yaxis_title="TIREA (%)",
                                    height=420, margin=dict(l=10, r=10, t=50, b=10),
                                )
                                _st_plotly(fig_yas)
                        else:
                            st.caption("(Bono no pertenece a ninguna curva cargada)")

            except Exception as e:
                st.error(f"Error: {type(e).__name__}: {e}")
                import traceback
                print(f"[YAS ERROR {yas_code}]\n{traceback.format_exc()}", flush=True)





def main():
    # [PROFILING TEMPORAL] — detectar si main() se re-ejecuta en cada cambio
    import time as _t_main
    _main_start = _t_main.perf_counter()
    print(f"\n━━━ main() started at {_t_main.strftime('%H:%M:%S', _t_main.localtime())} ━━━", flush=True)

    def _lap(label):
        """Profiling por etapas."""
        nonlocal _main_start
        _t_now = _t_main.perf_counter()
        _dur = (_t_now - _main_start) * 1000
        print(f"[main] {label} @ +{_dur:.0f}ms", flush=True)
        _main_start = _t_now

    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    _lap("after set_page_config+title")

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

        # Diagnóstico de secrets.txt (no expone valores, sólo estado)
        _sec_status = OMSsecrets.status()
        if _sec_status["found"]:
            st.caption(
                f"🔐 secrets.txt: {_sec_status['n_loaded']} vars cargadas"
            )
        else:
            st.caption("🔐 secrets.txt: no encontrado (usando env vars del sistema)")

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
            try:
                OMSmktdata.clear_dead_symbols()
            except Exception:
                pass
            st.rerun()

        # Diagnóstico: símbolos en blacklist (útil para ver qué se está saltando)
        try:
            _n_dead, _dead_list = OMSmktdata.dead_symbols_info()
            if _n_dead > 0:
                with st.expander(f"⚫ {_n_dead} símbolos sin datos hoy", expanded=False):
                    st.caption(
                        "Estos no operaron recientemente y están en blacklist temporal (2min). "
                        "Se reintentan automáticamente al expirar."
                    )
                    st.code(", ".join(_dead_list[:50]) + ("…" if len(_dead_list) > 50 else ""), language=None)
        except Exception:
            pass

    # Inyectar theme (puro CSS, zero overhead Python)
    _inject_theme(bloomberg_mode)
    _lap("after sidebar+theme")

    # Sidebar: datos macro BCRA
    _render_sidebar_macro()
    _lap("after _render_sidebar_macro")

    if not username or not password:
        st.warning("Ingresá usuario y password para conectarte a la API.")
        st.stop()

    # ── MARQUESINAS (News + Ticker) ──
    OMSnews.start_news_background(interval=120)
    _lap("after OMSnews.start_news_background")

    session = get_session(username, password)
    _lap("after get_session")

    # Curvas para el ticker (selección parametrizable por duration).
    # NOTA CRÍTICA: `load_curve_last_table` tiene TTL=15s, que expira muy
    # rápido y hace que cada rerun de main() recompute las curvas completas
    # (4-8 min con mercado cerrado). Acá usamos un cache más longevo
    # específico para el ticker — el ticker se refresca cada 15s via su
    # propio fragment, no necesita datos frescos en cada rerun de main().
    @st.cache_data(ttl=300, show_spinner=False)  # 5 minutos
    def _ticker_curve_tables_cached(_username: str, _password: str, _plazo: str):
        out = {}
        for _ck in ("cer", "lecap"):
            try:
                out[_ck] = load_curve_last_table(_username, _password, _ck, _plazo)
            except Exception:
                pass
        return out

    _ticker_curve_tables = _ticker_curve_tables_cached(username, password, plazo)
    _lap("after _ticker_curve_tables_cached")

    # Armar lista: parametrizables primero, fijos después
    _ticker_assets = OMSticker.build_parametric_symbols(_ticker_curve_tables, plazo) + list(OMSticker.FIXED_ASSETS)

    OMSticker.start_ticker_background(session, _ticker_assets, interval=15)
    _lap("after start_ticker_background")

    _is_dark = st.session_state.get("bbg_theme", False)

    @st.fragment(run_every=15)
    def _render_bars():
        ticker_data = OMSticker.get_ticker_data(session=session, assets=_ticker_assets)
        
        # ── A3500: inyectar desde indices (MAE waterfall) vs BCRA ayer ──
        try:
            fx_hoy = get_fx_hoy(session=session)
            df_a3500 = rentafija.inputs.get("a3500")
            fx_ayer = float(df_a3500.iloc[-2]["tca3500"]) if df_a3500 is not None and len(df_a3500) >= 2 else fx_hoy
            fx_var = (fx_hoy / fx_ayer - 1.0) if fx_ayer > 0 else 0.0
            ticker_data.append(OMSticker.TickerData(
                label="A3500", last=fx_hoy, close=fx_ayer,
                variation=fx_var, is_tna=False,
            ))
        except Exception:
            pass

        if ticker_data:
            st.markdown(
                OMSticker.ticker_marquee_html(ticker_data, speed=35, dark=_is_dark),
                unsafe_allow_html=True,
            )

        news = OMSnews.get_news(max_items=20)
        if news:
            st.markdown(
                OMSnews.news_marquee_html(news, speed=120, dark=_is_dark),
                unsafe_allow_html=True,
            )

    _render_bars()
    _lap("after _render_bars")


    curves = build_curve_codes()
    _lap("after build_curve_codes")
    curve_labels = {c.key: c.label for c in CURVES}

    # Navegación: pestañas
    # ── NAVEGACIÓN: radio en vez de st.tabs ──
    # Rationale: st.tabs ejecuta el código de TODOS los tabs en cada rerun,
    # aunque sólo uno sea visible. Con 14 tabs y fragments lazy que llaman
    # al API, cada rerun consume ~45s. Usando un radio con guard por tab
    # activo, sólo corre el tab visible → render en <1s.
    _TAB_LABELS = [
        "Curvas", "Mercado", "Cauciones", "Forwards", "Gráficos", "Futuros",
        "Total Return", "Análisis Yields", "Comparador Yields",
        "Breakeven Inflación", "Crédito Corp.", "Histórico",
        "Posiciones", "Matriz Tenencias",
    ]
    _active_tab = st.radio(
        "Sección",
        options=_TAB_LABELS,
        index=_TAB_LABELS.index(st.session_state.get("_active_tab", "Análisis Yields")),
        horizontal=True,
        key="_active_tab",
        label_visibility="collapsed",
    )
    st.divider()

    # Los "tabs" son ahora context managers trivales (st.container) para
    # mantener el indent y la estructura del código. El guard real es el `if`.
    class _TabGuard:
        def __init__(self, name):
            self.name = name
            self.active = (name == _active_tab)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __bool__(self):
            return self.active

    tab_curvas = _TabGuard("Curvas")
    tab_mercado = _TabGuard("Mercado")
    tab_cauciones = _TabGuard("Cauciones")
    tab_fwds = _TabGuard("Forwards")
    tab_graficos = _TabGuard("Gráficos")
    tab_futuros = _TabGuard("Futuros")
    tab_tr = _TabGuard("Total Return")
    tab_yas = _TabGuard("Análisis Yields")
    tab_comp = _TabGuard("Comparador Yields")
    tab_breakeven = _TabGuard("Breakeven Inflación")
    tab_credito = _TabGuard("Crédito Corp.")
    tab_historico = _TabGuard("Histórico")
    tab_posiciones = _TabGuard("Posiciones")
    tab_matriz = _TabGuard("Matriz Tenencias")
    _lap("after tabs setup (radio)")
    # ─────────────────────────
    # Curvas (todas juntas) — auto-refresh via st.fragment
    # ─────────────────────────
    if tab_curvas:
        compact = st.toggle("Modo compacto (usar expanders)", value=True)

        @st.fragment(run_every=refresh_interval)
        def _curvas_live():
            # Refrescar FX A3500 en cada ciclo live (>>> PATCH FX 04/2026)
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))

            st.caption(market_status_caption(plazo, auto_refresh=auto_refresh))
            if not is_market_open():
                st.info("⚪ Mercado cerrado — TIREA / TNA / Duration se calculan sobre el **Close** del último cierre. Bid/Offer TIREA usan sus precios si existen.")

            for c in CURVES:
                if c.key not in curves:
                    continue
                title = f"{c.label}"

                if compact:
                    with st.expander(title, expanded=(c.key in ("cer", "lecap"))):
                        df = load_curve_last_table(username, password, c.key, plazo)
                        if df is None or df.empty:
                            st.info("Sin datos (mercado cerrado o sin respuesta de marketdata).")
                        else:
                            st.dataframe(style_curvas(df), width="stretch", height=520)
                else:
                    st.subheader(title)
                    df = load_curve_last_table(username, password, c.key, plazo)
                    if df is None or df.empty:
                        st.info("Sin datos (mercado cerrado o sin respuesta de marketdata).")
                    else:
                        st.dataframe(style_curvas(df), width="stretch", height=520)

        _curvas_live()
        _lap("after curvas")

    # ─────────────────────────
    # Mercado — auto-refresh
    # ─────────────────────────
    if tab_mercado:
        curve_key_mkt = st.selectbox(
            "Curva",
            options=[c.key for c in CURVES if c.key in curves],
            format_func=lambda k: curve_labels.get(k, k),
            key="mkt_curve",
        )

        @st.fragment(run_every=refresh_interval)
        def _mercado_live():
            # Refrescar FX A3500 en cada ciclo live (>>> PATCH FX 04/2026)
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))

            col_metric, col_status = st.columns([1, 4])
            with col_metric:
                mkt_metric = st.radio(
                    "Métrica",
                    options=["TIREA", "TEM"],
                    horizontal=True,
                    key="mkt_metric",
                    label_visibility="collapsed",
                )
            with col_status:
                st.caption(market_status_caption(plazo, auto_refresh=auto_refresh))

            if not is_market_open():
                st.info("⚪ Mercado cerrado — métricas calculadas sobre **Close** del último cierre. Bid/Offer usan sus precios si hay book.")
            dfm = load_curve_market_table(username, password, curve_key_mkt, plazo)
            if dfm is None or dfm.empty:
                st.info("Sin datos (mercado cerrado o sin respuesta de marketdata).")
            else:
                if mkt_metric == "TEM":
                    dfm = dfm.copy()
                    rename_map = {}
                    for col in ("Bid TIREA", "TIREA", "Offer TIREA"):
                        if col in dfm.columns:
                            v = pd.to_numeric(dfm[col], errors="coerce")
                            dfm[col] = (1.0 + v) ** (30.0 / 360.0) - 1.0
                            rename_map[col] = col.replace("TIREA", "TEM")
                    if rename_map:
                        dfm.rename(columns=rename_map, inplace=True)
                st.dataframe(style_mercado(dfm), width="stretch", height=680)

        _mercado_live()
        _lap("after mercado")
    
    # ─────────────────────────
    # Cauciones
    # ─────────────────────────
    if tab_cauciones:
        st.subheader("Monitor de Cauciones — BYMA")
        st.caption("Tasas TNA por plazo. Datos en tiempo real. Sin cálculo de TIR (se negocia directo por TNA).")

        col_cfg1, col_cfg2 = st.columns([1, 1])
        with col_cfg1:
            caucion_plazos_mode = st.radio(
                "Plazos",
                options=["Principales (1-7, 14, 21, 28, 35, 60, 90, 120)", "Todos (1 a 30)"],
                horizontal=True,
                key="caucion_plazos_mode",
            )
        with col_cfg2:
            caucion_mostrar_usd = st.toggle("Mostrar Dólares", value=False, key="caucion_usd")

        if caucion_plazos_mode.startswith("Todos"):
            plazos_cauc = list(range(1, 31))
        else:
            plazos_cauc = None  # usa default del módulo (principales)

        @st.fragment(run_every=refresh_interval)
        def _cauciones_live():
            ts = datetime.now().strftime("%H:%M:%S")
            is_open = is_market_open()
            dot = "🔴 LIVE" if is_open else "⚪ CERRADO"
            prefix = f"{dot}  |  " if (auto_refresh or not is_open) else ""
            st.caption(f"{prefix}Actualizado: {ts}")

            session = get_session(username, password)

            # ── Pesos ──
            st.markdown("### Cauciones en Pesos (ARS)")
            df_pesos = OMScauciones.fetch_cauciones(session, moneda="PESOS", plazos=plazos_cauc)
            if df_pesos is None or df_pesos.empty:
                st.info("Sin datos de cauciones en pesos (mercado cerrado o sin respuesta).")
            else:
                st.dataframe(
                    OMScauciones.style_cauciones(df_pesos),
                    width="stretch",
                    height=min(520, 40 + 35 * len(df_pesos)),
                )

            # ── Dólares (toggle) ──
            if caucion_mostrar_usd:
                st.markdown("### Cauciones en Dólares (USD)")
                df_usd = OMScauciones.fetch_cauciones(session, moneda="DOLAR", plazos=plazos_cauc)
                if df_usd is None or df_usd.empty:
                    st.info("Sin datos de cauciones en dólares (poca liquidez o mercado cerrado).")
                else:
                    st.dataframe(
                        OMScauciones.style_cauciones(df_usd),
                        width="stretch",
                        height=min(520, 40 + 35 * len(df_usd)),
                    )

        _cauciones_live()
        _lap("after cauciones")

    # ─────────────────────────
    # Forwards
    # ─────────────────────────
    if tab_fwds:
        st.subheader("Forwards implícitos (TIR) — tiempo real")
        st.caption("Matriz aproximada: usa TIR como spot (no bootstrap de curva de descuento).")

        # Matrices apiladas verticalmente (apaisadas): CER → LECAP → Globales.
        # Fragment con auto-refresh: las TIR se mueven con cada tick → recomputa.
        @st.fragment(run_every=refresh_interval)
        def _fwds_matrices_live():
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))
            if not is_market_open():
                st.info("⚪ Mercado cerrado — forwards calculados sobre TIREA derivado del Close.")

            _FWD_BLOCKS = (
                ("cer",      "### CER",                          "No hay suficientes datos para forwards CER."),
                ("lecap",    "### LECAP / Tasa fija",            "No hay suficientes datos para forwards LECAP."),
                ("globales", "### Globales (Ley Extranjera)",    "No hay suficientes datos para forwards Globales."),
                ("bonares",  "### Bonares (Ley Argentina)",      "No hay suficientes datos para forwards Bonares."),
            )
            for curve_key, title_md, empty_msg in _FWD_BLOCKS:
                st.markdown(title_md)
                df_c = load_curve_last_table(username, password, curve_key, plazo)
                if df_c is None or df_c.empty or "Código" not in df_c.columns:
                    st.info(empty_msg)
                    st.markdown("")
                    continue

                all_codes = df_c["Código"].astype(str).tolist()
                selected = _fwd_bond_filter(curve_key, all_codes, plazo)

                if len(selected) < 2:
                    st.warning("Tildá al menos 2 bonos para ver la matriz.")
                    st.markdown("")
                    continue

                df_filt = df_c[df_c["Código"].astype(str).isin(selected)]
                fwd_c = forwards_matrix(df_filt)
                if fwd_c.empty:
                    st.info(empty_msg)
                else:
                    st.dataframe(style_forwards(fwd_c), width="stretch", height=520)
                st.markdown("")  # aire entre matrices

        _fwds_matrices_live()
        _lap("after fwds_matrices")

        # ── Forwards interactivos (what-if por precio editable) ──
        st.markdown("---")
        st.markdown("### Forwards interactivos — editá precios y recalculá")
        st.caption(
            "Modificá el **Precio** de cualquier instrumento en la tabla izquierda. "
            "Se recalculan **TIR** y **Duration** automáticamente, y la matriz de forwards "
            "de la derecha se actualiza con los nuevos valores."
        )

        _WI_CURVE_LABELS = {
            "cer": "CER",
            "lecap": "LECAP / Tasa fija",
            "globales": "Globales (Ley Extranjera)",
            "bonares": "Bonares (Ley Argentina)",
        }

        @st.fragment
        def _wi_forwards_live():
            """Aísla la edición de precios del what-if: cambios acá NO disparan
            re-ejecución de main() ni de las matrices de forwards de arriba."""
            wi_curve_key = st.radio(
                "Curva para what-if",
                options=list(_WI_CURVE_LABELS.keys()),
                format_func=lambda k: _WI_CURVE_LABELS.get(k, k),
                horizontal=True,
                key="wi_fwd_curve",
            )

            df_wi_base = load_curve_last_table(username, password, wi_curve_key, plazo)

            if df_wi_base is None or df_wi_base.empty:
                st.info(f"Sin datos para la curva {wi_curve_key}.")
                return

            # Precio base: Last si hay, si no Close
            px_base = _effective_price_series(df_wi_base, last_col="Last", close_col="Close")

            # Construir tabla editable
            wi_editor_df = pd.DataFrame({
                "Código": df_wi_base["Código"].astype(str).values,
                "Precio": pd.to_numeric(px_base, errors="coerce").astype("float64").values,
            })

            # Session state: persistir ediciones por curva
            wi_state_key = f"wi_fwd_prices::{wi_curve_key}::{plazo}"

            # Si el usuario ya editó, usamos esos valores como base; si no, los del mercado
            if wi_state_key in st.session_state:
                prev = st.session_state[wi_state_key]
                wi_editor_df["Precio"] = wi_editor_df["Código"].map(
                    lambda c: prev.get(c, np.nan)
                ).fillna(wi_editor_df["Precio"])

            col_edit, col_mat = st.columns([1, 2])

            with col_edit:
                st.markdown("#### Precios (editables)")
                wi_edited = st.data_editor(
                    wi_editor_df,
                    width="stretch",
                    height=520,
                    num_rows="fixed",
                    column_config={
                        "Código": st.column_config.TextColumn("Código", disabled=True),
                        "Precio": st.column_config.NumberColumn(
                            "Precio",
                            format="%.4f",
                            step=0.01,
                            min_value=0.0,
                        ),
                    },
                    key=f"wi_fwd_editor::{wi_curve_key}::{plazo}",
                )

                # Persist user edits for this curve/plazo combo
                st.session_state[wi_state_key] = dict(
                    zip(wi_edited["Código"].astype(str), wi_edited["Precio"].astype(float))
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("↩️ Restaurar precios de mercado", key=f"wi_reset::{wi_curve_key}"):
                        if wi_state_key in st.session_state:
                            del st.session_state[wi_state_key]
                        st.rerun()

            # Recalcular TIR y Duration con los precios editados (CACHEADO)
            bond_type_wi = next((c.bond_type for c in CURVES if c.key == wi_curve_key), "lecap")
            settle_wi = _settlement_date_str(plazo)

            codes_wi = wi_edited["Código"].astype(str).to_numpy()
            prices_wi = pd.to_numeric(wi_edited["Precio"], errors="coerce").to_numpy(dtype="float64")

            # Si la tupla (codes, prices, bond_type, settle) ya se vio en la
            # sesión, el resultado viene del cache (ej: volviste al precio original).
            mdf_wi = _wi_metrics_cached(
                tuple(codes_wi.tolist()),
                _to_tuple_safe(prices_wi),
                bond_type_wi,
                settle_wi,
            )

            # Armar DataFrame con Código + Precio + TIREA + Duration
            wi_full = pd.DataFrame({
                "Código": codes_wi,
                "Precio": prices_wi,
                "TIREA": mdf_wi["TIREA"].values,
                "Duration": mdf_wi["Duration"].values,
            })

            with col_edit:
                st.markdown("#### TIR y Duration recalculadas")
                display_df = _sort_duration_nan_last(wi_full.copy(), "Duration")
                st.dataframe(
                    display_df.style.format({
                        "Precio": "{:,.4f}",
                        "TIREA": "{:.2%}",
                        "Duration": "{:.4f}",
                    }, na_rep="—"),
                    width="stretch",
                    height=360,
                )

            with col_mat:
                st.markdown("#### Matriz de Forwards recalculada")
                wi_full_for_fwd = wi_full.dropna(subset=["TIREA", "Duration"])

                if len(wi_full_for_fwd) < 2:
                    st.info("Necesitás al menos 2 instrumentos con TIR/Duration válidos para calcular forwards.")
                    return

                # Filtro por bono (mismo patrón que las matrices live, namespace `wi`)
                wi_codes_all = wi_full_for_fwd["Código"].astype(str).tolist()
                wi_selected = _fwd_bond_filter(f"wi::{wi_curve_key}", wi_codes_all, plazo)

                if len(wi_selected) < 2:
                    st.warning("Tildá al menos 2 bonos para ver la matriz.")
                    return

                wi_full_for_fwd = wi_full_for_fwd[
                    wi_full_for_fwd["Código"].astype(str).isin(wi_selected)
                ]

                # Matriz de forwards cacheada por (codes, TIREA, Duration)
                fwd_wi = _wi_forwards_matrix_cached(
                    tuple(wi_full_for_fwd["Código"].astype(str).tolist()),
                    _to_tuple_safe(wi_full_for_fwd["TIREA"].to_numpy()),
                    _to_tuple_safe(wi_full_for_fwd["Duration"].to_numpy()),
                )

                if fwd_wi.empty:
                    st.info("No se pudo calcular la matriz.")
                    return

                st.dataframe(style_forwards(fwd_wi), width="stretch", height=620)

                # Comparativa Δ vs matriz original
                with st.expander("Δ vs forwards con precios de mercado", expanded=False):
                    # La matriz base NO depende de los precios editados → cacheada
                    # por (codes, TIREA base, Duration base). Si el usuario edita
                    # varios precios, esta matriz se computa UNA sola vez.
                    _base_codes = tuple(df_wi_base["Código"].astype(str).tolist())
                    _base_tirea = _to_tuple_safe(
                        pd.to_numeric(df_wi_base.get("TIREA"), errors="coerce").to_numpy()
                    )
                    _base_dur = _to_tuple_safe(
                        pd.to_numeric(df_wi_base.get("Duration"), errors="coerce").to_numpy()
                    )
                    fwd_orig = _wi_forwards_matrix_cached(_base_codes, _base_tirea, _base_dur)

                    if not fwd_orig.empty:
                        common_idx = fwd_orig.index.intersection(fwd_wi.index)
                        common_cols = fwd_orig.columns.intersection(fwd_wi.columns)
                        if len(common_idx) >= 2 and len(common_cols) >= 2:
                            diff_df = (fwd_wi.loc[common_idx, common_cols]
                                       - fwd_orig.loc[common_idx, common_cols])
                            st.caption("Diferencia en puntos porcentuales (what-if − mercado).")
                            st.dataframe(
                                diff_df.style.format("{:+.2f}", na_rep="").background_gradient(
                                    cmap="RdBu_r", axis=None, vmin=-5, vmax=5,
                                ),
                                width="stretch",
                                height=520,
                            )

        _wi_forwards_live()
        _lap("after wi_forwards")

    # ─────────────────────────
    # Gráficos
    # ─────────────────────────
    if tab_graficos:
        st.subheader("Curva — Duration vs Yield (bid / last / offer) + NSS")

        @st.fragment(run_every=refresh_interval)
        def _graficos_live():
            """Fragment con auto-refresh: TIR recomputa en vivo.
            Todos los widgets viven acá dentro para que cambios de curva/métrica
            re-disparen el render sin afectar main()."""
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))

            if not is_market_open():
                st.info("⚪ Mercado cerrado — los puntos **LAST** del gráfico reflejan TIREA calculado sobre Close del último cierre.")

            curve_key = st.selectbox(
                "Curva",
                options=[c.key for c in CURVES if c.key in curves],
                format_func=lambda k: curve_labels.get(k, k),
                key="chart_curve",
            )

            if go is None:
                st.error("Plotly no está instalado en este entorno. Instalá: pip install plotly")
                return

            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                which = st.selectbox("Métrica", options=["TIREA", "TEM"], index=0, key="chart_metric")
            with c2:
                show_nss = st.checkbox("Mostrar NSS", value=True, key="chart_show_nss")
            with c3:
                thr = st.slider(
                    "Filtro outliers (sigmas MAD)",
                    min_value=1.5, max_value=5.0, value=3.0, step=0.25,
                    key="chart_thr",
                    help="Umbral robusto (MAD escalado). 2.5 = estricto, 3.0 = estándar, 4.0 = permisivo.",
                )
            with c4:
                st.caption("TIP: si la curva tiene pocos puntos, NSS puede fallar.")

            df_last = load_curve_last_table(username, password, curve_key, plazo)
            df_mkt = load_curve_market_table(username, password, curve_key, plazo)

            if df_last is None or df_last.empty:
                st.info("Sin datos para graficar (mercado cerrado o sin marketdata).")
                return

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
            dur_in = st.number_input("Duration objetivo", min_value=0.0, value=1.0, step=0.05, key="chart_dur_in")

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

        _graficos_live()
        _lap("after graficos")

    # ─────────────────────────
    # Futuros
    # ─────────────────────────
    if tab_futuros:
        @st.fragment
        def _futuros_live():
            st.subheader("Futuros DLR (ROFEX) — implícitas vs A3500")
            st.caption(
                "Tablas apiladas: Minorista arriba (DLR/MMMYY), Mayorista abajo (sufijo 'M'). "
                "Símbolos generados dinámicamente."
            )

            FUTUROS_BASE = _generate_futures_symbols(n_months=18)
            FUTUROS_MAY = [f"{s}M" for s in FUTUROS_BASE]
            symbols_all = FUTUROS_BASE + FUTUROS_MAY

            # ── FX A3500: por default el del OMS; override opcional ─────────────
            fx_oms = float(get_fx_hoy(session=get_session(username, password)))
            fx_cols = st.columns([1, 1, 2])
            with fx_cols[0]:
                override_fx = st.toggle(
                    "🔓 Override FX A3500",
                    value=False,
                    key="fut_override_fx",
                    help="Si está apagado, usa el último A3500 que levantó el OMS.",
                )
            with fx_cols[1]:
                if override_fx:
                    a3500 = st.number_input(
                        "A3500 spot (mayorista)", value=fx_oms, step=0.5,
                        format="%.4f", key="fut_a3500_override",
                    )
                else:
                    a3500 = fx_oms
                    st.metric("A3500 spot (OMS)", f"{a3500:,.4f}")
            with fx_cols[2]:
                st.caption(fx_status_text())

            # ── Fetch único para todos los símbolos ─────────────────────────────
            # Usamos cfg.ENTRIES (incluye LA, BI, OF, OP, CL, SE, HI, LO, TV,
            # OI, EV, NV, ACP, IV) en vez de hardcodear — así si mañana sumás
            # un entry, no queda atrás.
            raw = fetch_marketdata(
                username, password, symbols_all,
                market_id=DEFAULT_MARKET_ID, entries=cfg.ENTRIES, depth=1,
            )

            if raw is None or raw.empty:
                st.info("Sin datos de futuros (puede ser horario o mercado cerrado).")
                return

            snap = OMSprices.market_snapshot(raw)
            snap = _ensure_codigo_col(snap, source="index")
            snap["Código"] = snap["Código"].astype(str)

            # Fallback de close: CL → SE
            # CL puede venir vacío con mercado recién abierto o vencimientos
            # poco operados; SE (settlement) suele tener dato igual.
            if "SE" in raw.columns:
                se = raw["SE"].map(OMSprices.extract_price)
                if "close" in snap.columns:
                    snap["close"] = snap["close"].fillna(se)
                else:
                    snap["close"] = se

            # ── FIX bug clasificación: el sufijo es 'M' (no 'A') ────────────────
            cod_upper = snap["Código"].str.upper()
            is_may = cod_upper.str.endswith("M")
            snap["Canal"] = np.where(is_may, "Mayorista", "Minorista")

            # ── Vencimientos y días al vto (vectorizado) ────────────────────────
            today = date.today()
            maturities = snap["Código"].map(_parsear_vencimiento_futuro)
            dias_vto = maturities.map(
                lambda d: (d - today).days if isinstance(d, date) else np.nan
            )

            # ── Cálculos de rendimiento (todo numpy, recalcula con FX en vivo) ──
            lp = pd.to_numeric(snap.get("last"), errors="coerce")
            cp = pd.to_numeric(snap.get("close"), errors="coerce")
            op = pd.to_numeric(snap.get("open"), errors="coerce")
            hi = pd.to_numeric(snap.get("high"), errors="coerce")
            lo = pd.to_numeric(snap.get("low"), errors="coerce")
            bid_p = pd.to_numeric(snap.get("bid_price"), errors="coerce")
            bid_s = pd.to_numeric(snap.get("bid_size"), errors="coerce")
            off_p = pd.to_numeric(snap.get("offer_price"), errors="coerce")
            off_s = pd.to_numeric(snap.get("offer_size"), errors="coerce")
            vol = pd.to_numeric(snap.get("volume"), errors="coerce")

            # OI (Open Interest): puede venir como list/dict o número crudo
            oi = pd.Series(np.nan, index=snap.index)
            if "OI" in raw.columns:
                oi = raw["OI"].map(OMSprices.extract_size).reindex(snap.index)

            fx = float(a3500) if a3500 and a3500 > 0 else np.nan
            dv = dias_vto.astype("float64")

            with np.errstate(divide="ignore", invalid="ignore"):
                # Variaciones del último vs cierre
                var_last_pct = lp / cp - 1.0
                var_last_close = lp - cp

                # Rendimientos sobre Last/Bid/Offer respecto del FX
                td_last = lp / fx - 1.0
                td_bid = bid_p / fx - 1.0
                td_off = off_p / fx - 1.0

                # Anualizaciones (TNA lineal · TEA compuesta · TEM mensual capitaliz.)
                tna_last = td_last * 365.0 / dv
                tna_bid = td_bid * 365.0 / dv
                tna_off = td_off * 365.0 / dv

                tea_last = (1.0 + td_last * 30.0 / dv) ** 12 - 1.0
                tea_bid = (1.0 + td_bid * 30.0 / dv) ** 12 - 1.0
                tea_off = (1.0 + td_off * 30.0 / dv) ** 12 - 1.0

                tem_last = (1.0 + tea_last) ** (1.0 / 12.0) - 1.0
                tem_bid = (1.0 + tea_bid) ** (1.0 / 12.0) - 1.0
                tem_off = (1.0 + tea_off) ** (1.0 / 12.0) - 1.0

            # ── DataFrames de salida ────────────────────────────────────────────
            base = pd.DataFrame({
                "Tipo": np.where(is_may, "May", "Min"),
                "Código": snap["Código"].values,
                "Dias Vto": dias_vto.values,
                "Fecha Vto": maturities.values,
                "Open": op.values,
                "Close": cp.values,
                "High": hi.values,
                "Low": lo.values,
                "Last": lp.values,
                "Variación %": var_last_pct.values,
                "Δ Last-Close": var_last_close.values,
                "Bid Size": bid_s.values,
                "Bid": bid_p.values,
                "Offer": off_p.values,
                "Offer Size": off_s.values,
                "Rdto Directo Bid": td_bid.values,
                "Rdto Directo Offer": td_off.values,
                "TEM Bid": tem_bid.values,
                "TEM Offer": tem_off.values,
                "TNA Bid": tna_bid.values,
                "TNA Offer": tna_off.values,
                "TEA Bid": tea_bid.values,
                "TEA Offer": tea_off.values,
                "OI": oi.values,
                "Volumen": vol.values,
            }).replace([np.inf, -np.inf], np.nan)

            # Tabla de tasas (Min/May separadas, simple — la que viste antes mejorada)
            tasas = pd.DataFrame({
                "Código": snap["Código"].values,
                "Canal": snap["Canal"].values,
                "Close Price": cp.values,
                "Last Price": lp.values,
                "Variación": var_last_pct.values,
                "Dias Vto": dias_vto.values,
                "Tasa Directa": td_last.values,
                "TNA": tna_last.values,
                "TEA": tea_last.values,
            }).replace([np.inf, -np.inf], np.nan)

            tasas = tasas.sort_values("Dias Vto", ascending=True, na_position="last").reset_index(drop=True)
            # Min antes que May (alfabéticamente "May" < "Min", forzamos orden lógico)
            base["Tipo"] = pd.Categorical(base["Tipo"], categories=["Min", "May"], ordered=True)
            base = base.sort_values(["Tipo", "Dias Vto"], ascending=[True, True], na_position="last").reset_index(drop=True)
            base["Tipo"] = base["Tipo"].astype(str)

            # ── Tablas Min/May apiladas (ex-columnas) ──────────────────────────
            st.markdown("### Minorista (DLR/MMMYY)")
            df_min = tasas[tasas["Canal"] == "Minorista"].drop(columns=["Canal"]).reset_index(drop=True)
            if df_min.empty:
                st.info("Sin datos minorista.")
            else:
                st.dataframe(style_futuros(df_min), width="stretch",
                             height=min(560, 40 + 35 * len(df_min)))

            st.markdown("### Mayorista (DLR/MMMYYM)")
            df_may = tasas[tasas["Canal"] == "Mayorista"].drop(columns=["Canal"]).reset_index(drop=True)
            if df_may.empty:
                st.info("Sin datos mayorista.")
            else:
                st.dataframe(style_futuros(df_may), width="stretch",
                             height=min(560, 40 + 35 * len(df_may)))

            # ── Tabla de mercado completa (lazy, en expander) ──────────────────
            with st.expander("📊 Mercado completo (book + OLH + tasas Bid/Offer)", expanded=False):
                st.caption(
                    f"Min ({(base['Tipo'] == 'Min').sum()}) + May ({(base['Tipo'] == 'May').sum()}) · "
                    f"Rdto/TEM/TNA/TEA calculados sobre A3500 = **{fx:,.4f}** "
                    f"({'OVERRIDE manual' if override_fx else 'OMS'})"
                )
                st.dataframe(_style_futuros_mercado(base), width="stretch", height=720)

        _futuros_live()
        _lap("after futuros")

    if tab_tr:
        @st.fragment
        def _tr_live():
            st.subheader("Total Return real (calcula_total_return)")
            if not is_market_open():
                st.info("⚪ Mercado cerrado — la curva **Actual** se arma con TIREA calculada sobre el Close del último cierre.")

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
                            dflt = _nss_defaults_level_slope_convex(df_last, threshold_factor=3.0, anchor=anchor0, which="TIREA")
                            if dflt is None:
                                level0 = _safe_median_pct(df_last.get("TIREA"), default=40.0)
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
                            dflt2 = _nss_defaults_level_slope_convex(df_last, threshold_factor=3.0, anchor=float(anchor), which="TIREA")
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
                        y0 = _safe_median_pct(df_last.get("TIREA"), default=40.0)

                        pts_default = pd.DataFrame({"Duration": [dmin, dmid, dmax], "TIREA %": [y0, y0, y0]})
                        pts_editor = st.data_editor(pts_default, num_rows="dynamic", width="stretch")
                        scenario_y = _scenario_curve_points(durations, pts_editor)

                cN1, cN2 = st.columns([1, 2])
                with cN1:
                    show_nss_tr = st.checkbox("Mostrar NSS (curva actual)", value=True, key="tr_show_nss")
                with cN2:
                    thr_tr = st.slider(
                        "Filtro outliers NSS (sigmas MAD)",
                        min_value=1.5,
                        max_value=5.0,
                        value=3.0,
                        step=0.25,
                        key="tr_thr",
                        help="Umbral robusto (MAD escalado). 2.5 = estricto, 3.0 = estándar, 4.0 = permisivo.",
                    )

                fig = go.Figure()

                fig.add_trace(
                    go.Scatter(
                        x=df_last["Duration"],
                        y=_yield_pct_points(df_last["TIREA"]),
                        mode="markers+text",
                        name="Actual (LAST)",
                        text=df_last["Código"],
                        texttemplate="%{text} %{y:.1f}%",
                        textposition="top center",
                        textfont=dict(size=9),
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
        _tr_live()
        _lap("after tr")

    if tab_yas:
        _lap("entering tab_yas")
        # _render_yas YA está decorada con @st.fragment.
        # Llamarla directamente (sin wrapper) asegura que los widgets
        # internos estén asociados al fragment correcto.
        _render_yas(username, password, plazo, curve_labels)
        _lap("after _render_yas() executed")

    if tab_comp:
        @st.fragment
        def _comp_live():
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

                # Cálculo automático con spinner y error handling robusto
                try:
                    with st.spinner("Comparando…"):
                        obj_a = _bond_obj(code_a)
                        obj_b = _bond_obj(code_b)
                except Exception as e:
                    st.error(f"Error al cargar bonos: {type(e).__name__}: {e}")
                    obj_a = obj_b = None

                if obj_a is None or obj_b is None:
                    st.info(f"Esperando selección válida de ambos bonos…")
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
                                # Cast columnas object-mixed a str para evitar ArrowTypeError
                                _comp_show = comp_df.copy()
                                for _col in _comp_show.columns:
                                    if _comp_show[_col].dtype == object:
                                        _comp_show[_col] = _comp_show[_col].astype(str)
                                st.dataframe(_comp_show, width="stretch")

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
                                                mode="markers+text",
                                                name=f"Curva {curve_labels.get(curve_use, curve_use)}",
                                                text=df_c["Código"],
                                                texttemplate="%{text} %{y:.1f}%",
                                                textposition="top center",
                                                textfont=dict(size=9),
                                                hovertemplate="%{text}<br>Dur=%{x:.3f}<br>TIREA=%{y:.2f}%<extra></extra>",
                                                marker=dict(size=7, opacity=0.5),
                                            ))
                                            try:
                                                tmp = df_c[["Código", "Duration", "TIREA", "TEM"]].copy()
                                                popt_c, xmin_c, xmax_c = plotter._fit_nss_cached(
                                                    tmp, which="TIREA", threshold_factor=3.0, use_cache=False)
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
        # Crédito Corporativo
        # ─────────────────────────

        _comp_live()

    if tab_credito:
        @st.fragment
        def _credito_live():
            st.subheader("Scoring Crediticio — Corporativos Argentina USD")
            st.caption(
                "Score interno (1-5) basado en ratios de solvencia y liquidez. "
                "Datos del último balance disponible. "
                "Fuente: equipo de Research RV — Delta Asset Management."
            )
 
            df_credit = OMScredit.get_all_issuers_df()
 
            if df_credit.empty:
                st.warning("No se encontró credit_scores.json. Corré export_credit_scores.py.")
            else:
                col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
                with col_f1:
                    sectors = sorted(df_credit["Sector"].dropna().unique())
                    sel_sector = st.multiselect("Sector", options=sectors, default=[], key="cred_sector")
                with col_f2:
                    score_min = st.slider("Score mínimo", 1.0, 5.0, 1.0, 0.5, key="cred_score_min")
                with col_f3:
                    solo_con_ons = st.toggle("Solo con ONs cargadas", value=False, key="cred_solo_ons")
 
                df_show = df_credit.copy()
                if sel_sector:
                    df_show = df_show[df_show["Sector"].isin(sel_sector)]
                df_show = df_show[pd.to_numeric(df_show["Score"], errors="coerce") >= score_min]
                if solo_con_ons:
                    df_show = df_show[df_show["ONs cargadas"] > 0]
 
                cols_main = [
                    "Emisor", "Ticker", "Sector", "Score",
                    # Solvencia (sub-scores)
                    "Net Debt/EBITDA", "EBITDA/Interest", "(EBITDA-CAPEX)/Int",
                    "Pasivo/PN", "Solvencia",
                    # Liquidez (sub-scores)
                    "Current Ratio", "Liq. Ratio", "% ST Debt", "Liquidez",
                    # Balance
                    "DFN (USD M)", "EBITDA (USD M)",
                    # Meta
                    "ONs cargadas", "Last Q", "Comentario",
                ]
            
                cols_main = [c for c in cols_main if c in df_show.columns]
 
                st.dataframe(
                    OMScredit.style_credit_table(df_show[cols_main]),
                    width="stretch",
                    height=min(680, 40 + 35 * len(df_show)),
                )
 
                # Detalle emisor
                st.markdown("### Detalle emisor")
                emisor_opts = df_show["Ticker"].tolist()
                if emisor_opts:
                    sel_emisor = st.selectbox("Emisor", options=emisor_opts, key="cred_emisor_detail")
                    credit_data = OMScredit.get_credit(sel_emisor)
                    if credit_data:
                        st.markdown(f"**{credit_data.get('compania', '')}** — {credit_data.get('sector', '')}")
 
                        _com = credit_data.get("comentario")
                        if _com:
                            st.info(f"💬 {_com}")
 
                        bonds = OMScredit.get_bonds_for_issuer(sel_emisor)
                        if bonds:
                            st.markdown(f"**ONs cargadas ({len(bonds)}):** {', '.join(bonds)}")
 
                            # Métricas live de cada ON
                            bond_rows = []
                            settle = _settlement_date_str(plazo)
                            snap = _global_snapshot(username, password, plazo)
                            if snap is not None and not snap.empty:
                                for bc in bonds:
                                    # Buscar en snapshot directo o con D (MEP)
                                    bs = snap[snap["Código"] == bc]
                                    if bs.empty:
                                        bs = snap[snap["Código"] == bc[:-1] + "D"]
                                    if not bs.empty:
                                        lp = pd.to_numeric(bs.iloc[0].get("last"), errors="coerce")
                                        if np.isfinite(lp):
                                            obj = _bond_obj(bc)
                                            bt = "hdmep"  # default para corp USD
                                            if obj:
                                                clas = getattr(obj, "clasificacion", "") or ""
                                                if "TAMAR" in clas:
                                                    bt = "tamar"
                                                elif "Tasa Fija" in clas:
                                                    bt = "lecap"
                                                elif "UVA" in clas:
                                                    bt = "cer"
                                            m = metrics_for_price(bc, lp, bt, settle)
                                            bond_rows.append({
                                                "Código": bc,
                                                "Last": lp,
                                                "TIREA": m.get("TIREA", np.nan),
                                                "TNA": m.get("TNA", np.nan),
                                                "Duration": m.get("Duration", np.nan),
                                                "Paridad": m.get("Paridad", np.nan),
                                            })
 
                            if bond_rows:
                                df_bonds = pd.DataFrame(bond_rows)
                                st.dataframe(
                                    df_bonds.style.format({
                                        "Last": "{:,.4f}", "TIREA": "{:.2%}",
                                        "TNA": "{:.2%}", "Duration": "{:.4f}",
                                        "Paridad": "{:.2%}",
                                    }, na_rep="—"),
                                    width="stretch",
                                    height=min(400, 40 + 35 * len(df_bonds)),
                                )
                            elif bonds:
                                st.caption("Sin datos de mercado para estas ONs.")
                        else:
                            st.caption("Sin ONs cargadas en especies.py para este emisor.")

        # ─────────────────────────
        # Breakeven Inflación
        # ─────────────────────────
        _credito_live()

    if tab_breakeven:
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

        @st.fragment(run_every=refresh_interval)
        def _breakeven_live():
            """Fragment real-time: precios cambian → BE recalcula."""
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))
            if not is_market_open():
                st.info("⚪ Mercado cerrado — el breakeven se calcula con TIREA de CER y LECAP sobre Close del último cierre.")
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
            col_m1, col_m2 = st.columns([1, 2])
            with col_m1:
                be_method = st.radio(
                    "Método de cálculo",
                    options=["fisher", "iter", "both"],
                    format_func=lambda k: {
                        "fisher": "Fisher (rápido)",
                        "iter": "Iteración (preciso para cortas)",
                        "both": "Ambos (Fisher + Iteración)",
                    }.get(k, k),
                    horizontal=True,
                    key="be_method",
                )
            with col_m2:
                st.caption(
                    "**Fisher** usa `(1+i_nom)/(1+i_real)−1` — rápido pero "
                    "distorsiona en bonos CER cortos (duration < 0.5). "
                    "**Iteración** resuelve la inflación mensual constante que iguala los flujos "
                    "nominales del bono CER con los del LECAP de misma duration — es el método "
                    "que coincide con PPI/Allaria/Invecq."
                )
            df_lecap_be = load_curve_last_table(username, password, be_nom_key, plazo)

            # ═══════════════════════════════════════════════════════════
            # 🔁 Bootstrap de curva de inflación implícita
            # ═══════════════════════════════════════════════════════════
            st.markdown("---")
            st.markdown("### 🔁 Bootstrap de curva de inflación implícita")
            st.caption(
                "Bootstrap secuencial: resuelve mes a mes la inflación MOM que iguala TIREA(CER proyectado) "
                "con la TIR del LECAP vecino. Si varios bonos comparten mes → **promedio ponderado por volumen**. "
                "Meses sin ancla → **interpolación lineal**. Bonos con CER fix a menos de "
                f"**{BOOTSTRAP_MIN_BDAYS_TO_CER_FIX} días hábiles** → Fisher directo (el mes ya está prácticamente fijado)."
            )

            col_bs1, col_bs2, col_bs3 = st.columns([1, 1, 2])
            with col_bs1:
                run_bootstrap = st.button(
                    "🔁 Ejecutar bootstrap",
                    type="primary",
                    key="be_run_bootstrap",
                )
            with col_bs2:
                if "_bootstrap_result" in st.session_state:
                    if st.button("🧹 Limpiar resultado", key="be_clear_bootstrap"):
                        del st.session_state["_bootstrap_result"]
                        st.rerun()

            if run_bootstrap:
                if df_cer_be is None or df_cer_be.empty or df_lecap_be is None or df_lecap_be.empty:
                    st.error("Curvas CER o LECAP vacías — no se puede ejecutar.")
                else:
                    with st.spinner("Ejecutando bootstrap (puede tardar 10-20 segundos)…"):
                        import indices as _idx_bs
                        result = compute_inflation_bootstrap(df_cer_be, df_lecap_be, plazo, _idx_bs)
                        st.session_state["_bootstrap_result"] = result

            bs_result = st.session_state.get("_bootstrap_result")
            if bs_result:
                infla_impl = bs_result.get("inflacion_implicita", {})
                per_bond = bs_result.get("per_bond", [])
                warns = bs_result.get("warnings", [])

                if warns:
                    with st.expander(f"⚠️ {len(warns)} avisos del bootstrap", expanded=False):
                        for w in warns:
                            st.caption(f"• {w}")

                # Tabla de detalle por bono
                if per_bond:
                    df_pb = pd.DataFrame(per_bond)
                    df_pb = df_pb.sort_values("Duration", ascending=True, na_position="last").reset_index(drop=True)
                    st.markdown("#### Resolución por bono")
                    st.dataframe(
                        df_pb.style.format({
                            "Duration": "{:.4f}",
                            "TIR target": "{:.2%}",
                            "TIREA real": "{:.2%}",
                            "BE TEM": "{:.2%}",
                            "bdays_to_fix": "{:.0f}",
                        }, na_rep="—"),
                        width="stretch",
                        height=min(480, 40 + 35 * len(df_pb)),
                    )

                # Curva de inflación implícita
                if infla_impl:
                    # Ordenar por fecha
                    rows_ci = []
                    for k, v in infla_impl.items():
                        try:
                            d = pd.to_datetime(k, format="%b-%y")
                            rows_ci.append({"Mes": k, "_orden": d, "Inflación MOM (%)": v * 100.0})
                        except Exception:
                            pass
                    df_ci = pd.DataFrame(rows_ci).sort_values("_orden").drop(columns=["_orden"]).reset_index(drop=True)

                    st.markdown("#### Curva de inflación implícita (MOM)")
                    col_ci_t, col_ci_g = st.columns([1, 2])
                    with col_ci_t:
                        st.dataframe(
                            df_ci.style.format({"Inflación MOM (%)": "{:.2f}%"}),
                            width="stretch",
                            height=min(480, 40 + 35 * len(df_ci)),
                        )
                    with col_ci_g:
                        if go is not None and not df_ci.empty:
                            fig_ci = go.Figure()
                            fig_ci.add_trace(go.Scatter(
                                x=df_ci["Mes"],
                                y=df_ci["Inflación MOM (%)"],
                                mode="lines+markers+text",
                                name="Inflación implícita",
                                text=[f"{v:.1f}%" for v in df_ci["Inflación MOM (%)"]],
                                textposition="top center",
                                textfont=dict(size=9),
                                line=dict(color="#2980b9", width=2),
                                marker=dict(size=8, color="#2980b9"),
                                hovertemplate="%{x}<br>%{y:.2f}%<extra></extra>",
                            ))

                            # Línea de inflación observada (último dato BCRA) como referencia
                            inp_b = rentafija.inputs
                            df_infl_obs = inp_b.get("inflamom")
                            if df_infl_obs is not None and not df_infl_obs.empty and "inflacionmom" in df_infl_obs.columns:
                                hoy = date.today()
                                primer_dia_mes = hoy.replace(day=1)
                                obs_df = df_infl_obs[df_infl_obs.index < primer_dia_mes]
                                if not obs_df.empty:
                                    v_obs = float(obs_df.iloc[-1]["inflacionmom"])
                                    fig_ci.add_hline(
                                        y=v_obs, line_dash="dash", line_color="#ff9800",
                                        annotation_text=f"Última MOM observada: {v_obs:.1f}%",
                                        annotation_position="top left",
                                    )

                            fig_ci.update_layout(
                                title="Inflación MOM implícita por mes",
                                xaxis_title="Mes",
                                yaxis_title="Inflación MOM (%)",
                                height=420,
                                hovermode="x unified",
                                margin=dict(l=10, r=10, t=50, b=10),
                            )
                            _st_plotly(fig_ci)

                    # Botón para aplicar el bootstrap como proyección de CER
                    st.markdown("---")
                    if st.button(
                        "📥 Aplicar curva implícita como proyección de CER",
                        key="be_apply_bootstrap",
                        help="Actualiza rentafija.inputs['cer_proyectado'] con esta curva. "
                             "Afecta a TODAS las tabs (Curvas CER Proy, TR, etc.).",
                    ):
                        new_proy = {k: float(v * 100.0) for k, v in infla_impl.items() if np.isfinite(v)}
                        st.session_state["_custom_inflation_proy"] = new_proy
                        import indices as _idx_apply
                        _recalculate_cer_proyectado(new_proy, _idx_apply)
                        st.cache_data.clear()
                        st.success(f"Aplicada proyección de {len(new_proy)} meses. Refrescando…")
                        st.rerun()

            st.markdown("---")
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
                be_df = compute_breakeven_table(df_cer_be, df_lecap_be, plazo, method=be_method)
                if be_df.empty:
                    st.warning("No se pudo calcular breakeven (pocos datos o NSS no ajustó).")
                else:
                    # Show key metrics
                    cols_show_be = [
                        "Código", "Vencimiento", "Duration",
                        "TIREA CER (real)", "TEM CER (real)",
                        "TIR Nom. (vecino)", "Bono ref.",
                        "TIREA Nominal (NSS)",
                        "BE TEM (Fisher NSS)",
                        "BE TEM (Fisher vecino)",
                        "BE TEM (Iter)",
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

                        # Breakeven — elegir columna según método seleccionado.
                        # En "both" priorizamos Iter (más preciso), sino Fisher NSS.
                        be_tirea_col_candidates = []
                        if be_method in ("iter", "both"):
                            if "BE TEM (Iter)" in be_df.columns:
                                _iter_tem = pd.to_numeric(be_df["BE TEM (Iter)"], errors="coerce")
                                _iter_tirea = (1.0 + _iter_tem) ** 12.0 - 1.0
                                be_df = be_df.assign(**{"BE TIREA (Iter)": _iter_tirea})
                                be_tirea_col_candidates.append(
                                    ("BE TIREA (Iter)", "BE Inflación (Iter)", "#8e44ad")
                                )
                        if be_method in ("fisher", "both"):
                            if "BE TIREA (Fisher NSS)" in be_df.columns:
                                be_tirea_col_candidates.append(
                                    ("BE TIREA (Fisher NSS)", "BE Inflación (Fisher NSS)", "#2980b9")
                                )

                        for col_name, trace_name, color in be_tirea_col_candidates:
                            fig_be.add_trace(go.Scatter(
                                x=be_df["Duration"],
                                y=_yield_pct_points(be_df[col_name]),
                                mode="markers+lines",
                                name=trace_name,
                                text=be_df["Código"],
                                hovertemplate="%{text}<br>Dur=%{x:.3f}<br>BE=%{y:.2f}%<extra></extra>",
                                marker=dict(size=10, color=color),
                                line=dict(dash="dot", width=2, color=color),
                            ))

                        # NSS fits as reference lines
                        try:
                            tmp_l = df_lecap_be[["Código", "Duration", "TIREA", "TEM"]].copy()
                            popt_l, xmin_l, xmax_l = plotter._fit_nss_cached(
                                tmp_l, which="TIREA", threshold_factor=3.0, use_cache=False)
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
                                tmp_c, which="TIREA", threshold_factor=3.0, use_cache=False)
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

                    # Breakeven TEM chart (más intuitivo para el mercado local)
                    if go is not None:
                        fig_be_tem = go.Figure()

                        # Columnas a graficar según método
                        be_tem_traces = []
                        if be_method in ("iter", "both") and "BE TEM (Iter)" in be_df.columns:
                            be_tem_traces.append(("BE TEM (Iter)", "BE TEM (Iter)", "#8e44ad"))
                        if be_method in ("fisher", "both"):
                            if "BE TEM (Fisher vecino)" in be_df.columns:
                                be_tem_traces.append(
                                    ("BE TEM (Fisher vecino)", "BE TEM (Fisher vecino)", "#2980b9")
                                )
                            if "BE TEM (Fisher NSS)" in be_df.columns and be_method == "fisher":
                                be_tem_traces.append(
                                    ("BE TEM (Fisher NSS)", "BE TEM (Fisher NSS)", "#3498db")
                                )

                        for col_name, trace_name, color in be_tem_traces:
                            _pct = _yield_pct_points(be_df[col_name])
                            fig_be_tem.add_trace(go.Bar(
                                x=be_df["Código"],
                                y=_pct,
                                name=trace_name,
                                marker_color=color,
                                text=[(f"{v:.2f}%" if pd.notna(v) else "") for v in _pct],
                                textposition="outside",
                                textfont=dict(size=11),
                                hovertemplate=f"%{{x}}<br>{trace_name}=%{{y:.2f}}%<extra></extra>",
                            ))

                        # Add inflación observada reference line
                        inp = rentafija.inputs
                        df_inflam = inp.get("inflamom")
                        obs_inf = None
                        if df_inflam is not None and not df_inflam.empty and "inflacionmom" in df_inflam.columns:
                            hoy = date.today()
                            primer_dia_mes = hoy.replace(day=1)
                            obs = df_inflam[df_inflam.index < primer_dia_mes]
                            if not obs.empty:
                                obs_inf = obs.iloc[-1]["inflacionmom"]
                                fig_be_tem.add_hline(
                                    y=obs_inf,
                                    line_dash="dash",
                                    line_color="#ff9800",
                                    annotation_text=f"Inflación MOM obs: {obs_inf:.1f}%",
                                    annotation_position="top left",
                                )

                        fig_be_tem.update_layout(
                            title="Breakeven Inflación MOM (TEM) por instrumento CER",
                            xaxis_title="Instrumento",
                            yaxis_title="BE TEM (%)",
                            height=420,
                            margin=dict(l=10, r=10, t=60, b=10),
                        )
                        _st_plotly(fig_be_tem)

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

            # ═══════════════════════════════════════════════════════════
            # 🔍 DEBUG: inspección paso a paso del método Iter
            # ═══════════════════════════════════════════════════════════
            with st.expander("🔍 DEBUG — inspeccionar método Iter para un bono", expanded=False):
                st.caption(
                    "Probá distintos valores de inflación mensual y fijate qué TIREA "
                    "devuelve el bono `j` (CER proyectado) a su precio de mercado. "
                    "El breakeven es la inflación donde esa TIREA iguala la del LECAP vecino."
                )

                debug_opts = df_cer_be["Código"].tolist() if (df_cer_be is not None and not df_cer_be.empty) else []
                if debug_opts:
                    dbg_code = st.selectbox(
                        "Bono CER (base, sin `j`)",
                        options=debug_opts,
                        key="be_debug_code",
                    )
                    if st.button("Ejecutar debug", key="be_debug_run"):
                        obj_base = _bond_obj(dbg_code)
                        j_code = f"{dbg_code}j"
                        obj_j = globals().get(j_code)

                        st.write(f"**Código base:** `{dbg_code}` → `_bond_obj()` devolvió: `{obj_base is not None}`")
                        st.write(f"**Buscando `{j_code}` en globals:** {'✅ ENCONTRADO' if obj_j is not None else '❌ NO ENCONTRADO'}")

                        if obj_j is None:
                            # Listar globals que terminan en 'j' para ver qué nombres hay
                            j_candidates = [k for k in globals().keys()
                                            if k.lower().endswith("j") and len(k) <= 10
                                            and k[0].isupper()][:30]
                            st.error(
                                f"El bono `{j_code}` no existe como variable global. "
                                f"Sin esto, el método iter no puede funcionar."
                            )
                            st.write(f"**Otros `*j` disponibles en globals:** {j_candidates}")
                        else:
                            # Precio de mercado
                            row_cer = df_cer_be[df_cer_be["Código"] == dbg_code].iloc[0]
                            px_last = pd.to_numeric(row_cer.get("Last"), errors="coerce")
                            px_close = pd.to_numeric(row_cer.get("Close"), errors="coerce")
                            px = float(px_last if np.isfinite(px_last) else px_close)

                            # Target LECAP
                            lecap_d = pd.to_numeric(df_lecap_be["Duration"], errors="coerce")
                            lecap_t = pd.to_numeric(df_lecap_be["TIREA"], errors="coerce")
                            ok = np.isfinite(lecap_d) & np.isfinite(lecap_t)
                            dur_cer = float(row_cer.get("Duration"))
                            near_idx = (lecap_d[ok] - dur_cer).abs().idxmin()
                            tir_target = float(lecap_t.loc[near_idx])
                            cod_target = str(df_lecap_be.loc[near_idx, "Código"])

                            st.write(f"**Precio mkt CER:** {px:.4f} | Duration: {dur_cer:.4f}")
                            st.write(f"**Target LECAP:** `{cod_target}` | TIREA: {tir_target:.4%}")

                            # Probar varios niveles de inflación
                            import indices as _idx_dbg
                            settle_dbg = _settlement_date_str(plazo)

                            # Backup
                            inp_b = rentafija.inputs
                            bkp_cer = inp_b.get("cer_proyectado")
                            bkp_uva = inp_b.get("uva_proyectado")
                            bkp_inf = inp_b.get("inflamom")
                            bkp_mod_proy = dict(getattr(_idx_dbg, "proyeccion_inflacion_mensual", {}))

                            rows_dbg = []
                            # Calcular mes de referencia del bono (lo que intentamos resolver)
                            cer_fix_dbg = _cer_effective_maturity_date(obj_base)
                            mes_ref_dbg = _inflation_month_for_cer_date(cer_fix_dbg) if cer_fix_dbg else None
                            # Formato que espera _recalculate_cer_proyectado
                            mes_ref_key = None
                            if mes_ref_dbg:
                                try:
                                    mes_ref_key = pd.to_datetime(mes_ref_dbg, format="%b-%Y").strftime("%b-%y")
                                except Exception:
                                    mes_ref_key = None

                            st.write(f"**Mes de referencia del bono:** `{mes_ref_dbg}` (key: `{mes_ref_key}`)")

                            # Leer proyección base (la que ya tiene indices.py)
                            import indices as _idx_dbg2
                            base_proy = dict(getattr(_idx_dbg2, "proyeccion_inflacion_mensual", {}))
                            if mes_ref_key:
                                st.write(f"**Valor actual de proyección en `{mes_ref_key}`:** {base_proy.get(mes_ref_key, 'NO PRESENTE')}%")

                            try:
                                for i_m in [0.005, 0.015, 0.023, 0.030, 0.050, 0.080, 0.120]:
                                    # Método A: inflación constante (como antes, para comparar)
                                    proy_const = {}
                                    today_d = date.today()
                                    d = today_d.replace(day=1) + relativedelta(months=1)
                                    for _ in range(36):
                                        proy_const[d.strftime("%b-%y")] = i_m * 100.0
                                        d = d + relativedelta(months=1)
                                    _recalculate_cer_proyectado(proy_const, _idx_dbg)
                                    try:
                                        tir_j_const = float(obj_j.calcula_tirea(px / 100.0, settle_dbg))
                                    except Exception:
                                        tir_j_const = float("nan")

                                    # Método B: cambiar SÓLO el mes de referencia del bono
                                    tir_j_ref = float("nan")
                                    if mes_ref_key:
                                        proy_ref = dict(base_proy)  # copia de la base
                                        proy_ref[mes_ref_key] = i_m * 100.0
                                        _recalculate_cer_proyectado(proy_ref, _idx_dbg)
                                        try:
                                            tir_j_ref = float(obj_j.calcula_tirea(px / 100.0, settle_dbg))
                                        except Exception:
                                            tir_j_ref = float("nan")

                                    rows_dbg.append({
                                        "i_TEM probada": f"{i_m:.2%}",
                                        "TIREA j (const)": f"{tir_j_const:.4%}" if np.isfinite(tir_j_const) else "—",
                                        "TIREA j (solo mes ref)": f"{tir_j_ref:.4%}" if np.isfinite(tir_j_ref) else "—",
                                        "Δ mes ref vs target": f"{(tir_j_ref - tir_target):+.4%}" if np.isfinite(tir_j_ref) else "—",
                                    })
                            finally:
                                if bkp_cer is not None: rentafija.inputs["cer_proyectado"] = bkp_cer
                                if bkp_uva is not None: rentafija.inputs["uva_proyectado"] = bkp_uva
                                if bkp_inf is not None: rentafija.inputs["inflamom"] = bkp_inf
                                if bkp_mod_proy: _idx_dbg.proyeccion_inflacion_mensual = bkp_mod_proy

                            st.dataframe(pd.DataFrame(rows_dbg), width="stretch")
                            st.caption(
                                f"El método Iter busca la `i_TEM` donde **TIREA {j_code} = {tir_target:.4%}**. "
                                "Si ves que todos los valores de la primera columna son similares (no cambian con i), "
                                "es que el bono `j` no está respondiendo a la inyección de CER proyectado. "
                                "Si f(i) nunca cambia de signo en el rango probado, el breakeven está fuera de `[-2%, 15%]`."
                            )


        _breakeven_live()

    # ─────────────────────────
    # Histórico (series macro + bonos BYMA)
    # ─────────────────────────
    if tab_historico:
        @st.fragment
        def _historico_live():
            st.subheader("Histórico de tasas, precios y series macro")

            sub_macro, sub_bonos = st.tabs(["📊 Series Macro (BCRA)", "📈 Histórico BYMA (bonos)"])

            # ── Sub-tab: Series Macro ──
            with sub_macro:
                st.caption(
                    "Series del BCRA ya cargadas en memoria (A3500, Badlar, Tamar, CER, UVA, Inflación MOM). "
                    "Cero costo de lectura — vienen de `rentafija.inputs`."
                )

                macro_sources = {
                    "A3500 (mayorista)": ("a3500", "tca3500"),
                    "Badlar": ("badlar", "BADLAR"),
                    "Tamar": ("tamar", "TAMAR"),
                    "CER": ("CER", "CER"),
                    "UVA": ("UVA", "UVA"),
                    "Inflación MOM (%)": ("inflamom", "inflacionmom"),
                }

                inp = rentafija.inputs
                available_macro = [k for k, (key, _) in macro_sources.items() if inp.get(key) is not None and not inp[key].empty]

                if not available_macro:
                    st.info("No hay series macro cargadas en `rentafija.inputs`.")
                else:
                    col_m1, col_m2 = st.columns([2, 1])
                    with col_m1:
                        macro_sel = st.multiselect(
                            "Series a visualizar",
                            options=available_macro,
                            default=available_macro[:2],
                            key="macro_series_sel",
                        )
                    with col_m2:
                        macro_norm = st.toggle("Normalizar base 100", value=False, key="macro_norm")
                        macro_range = st.radio(
                            "Rango",
                            options=["Todo", "1Y", "6M", "3M", "1M"],
                            horizontal=True,
                            key="macro_range",
                        )

                    if macro_sel and go is not None:
                        fig_macro = go.Figure()

                        # Filtro de rango
                        today = pd.Timestamp.today()
                        range_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "Todo": None}
                        days_back = range_map.get(macro_range)
                        cutoff = today - pd.Timedelta(days=days_back) if days_back else None

                        stats_rows = []
                        for label in macro_sel:
                            key, col = macro_sources[label]
                            df_m = inp[key].copy()
                            if col not in df_m.columns:
                                continue
                            s = pd.to_numeric(df_m[col], errors="coerce").dropna()
                            if s.empty:
                                continue
                            # Convert index a datetime
                            s.index = pd.to_datetime(s.index, errors="coerce")
                            s = s.dropna()
                            if cutoff is not None:
                                s = s[s.index >= cutoff]
                            if s.empty:
                                continue

                            y_plot = (s / s.iloc[0]) * 100.0 if macro_norm else s

                            fig_macro.add_trace(go.Scatter(
                                x=s.index, y=y_plot, mode="lines",
                                name=label,
                                hovertemplate=f"{label}<br>%{{x|%Y-%m-%d}}<br>%{{y:.4f}}<extra></extra>",
                            ))

                            stats_rows.append({
                                "Serie": label,
                                "Último": float(s.iloc[-1]),
                                "Fecha último": s.index[-1].date(),
                                "Mín": float(s.min()),
                                "Máx": float(s.max()),
                                "Promedio": float(s.mean()),
                                "Obs.": int(len(s)),
                            })

                        y_axis_title = "Base 100" if macro_norm else "Valor"
                        fig_macro.update_layout(
                            title=f"Series macro — {macro_range}",
                            xaxis_title="Fecha",
                            yaxis_title=y_axis_title,
                            height=500,
                            hovermode="x unified",
                            legend_orientation="h",
                            legend_yanchor="bottom", legend_y=1.02,
                            legend_xanchor="left", legend_x=0,
                            margin=dict(l=10, r=10, t=60, b=10),
                        )
                        _st_plotly(fig_macro)

                        if stats_rows:
                            st.markdown("#### Estadísticas del período")
                            st.dataframe(
                                pd.DataFrame(stats_rows).style.format({
                                    "Último": "{:,.4f}",
                                    "Mín": "{:,.4f}",
                                    "Máx": "{:,.4f}",
                                    "Promedio": "{:,.4f}",
                                    "Obs.": "{:,.0f}",
                                }),
                                width="stretch",
                                height=min(300, 40 + 35 * len(stats_rows)),
                            )

            # ── Sub-tab: Histórico BYMA ──
            with sub_bonos:
                df_hist = load_historico_byma()

                if df_hist.empty:
                    st.warning(
                        f"No se pudo cargar `{_HISTORICO_FILENAME}`.\n\n"
                        "Configurá en `secrets.txt`:\n"
                        "- `DELTA_HISTORICO_PATH` (ruta completa al archivo), o\n"
                        "- `DELTA_HISTORICO_DIR` (carpeta), o\n"
                        "- `DELTA_BASES_DIR` (si el histórico está junto a las carteras).\n\n"
                        "Podés usar `~` o `%USERPROFILE%` en las rutas — son independientes del usuario."
                    )
                else:
                    last_upd = _hist_last_update(df_hist)
                    st.caption(
                        f"Última fecha en el histórico: **{last_upd.date() if last_upd else '—'}**  |  "
                        f"{df_hist['Código'].nunique()} códigos  |  "
                        f"{df_hist['fecha_hoy'].nunique()} fechas  |  "
                        f"{len(df_hist):,} observaciones"
                    )

                    codigos_hist = _hist_codigos_disponibles(df_hist)

                    view_mode = st.radio(
                        "Vista",
                        options=["Un bono (precio + TIR)", "Curva completa (evolución histórica)", "Comparador TIR", "Spread entre bonos", "Tabla completa"],
                        horizontal=True,
                        key="hist_view_mode",
                    )

                    # Rango de fechas común
                    min_date = df_hist["fecha_hoy"].min().date()
                    max_date = df_hist["fecha_hoy"].max().date()
                    col_r1, col_r2, col_r3 = st.columns([1, 1, 1])
                    with col_r1:
                        date_from = st.date_input("Desde", value=max(min_date, (max_date - pd.Timedelta(days=365)).date() if hasattr(max_date - pd.Timedelta(days=365), "date") else min_date), min_value=min_date, max_value=max_date, key="hist_from")
                    with col_r2:
                        date_to = st.date_input("Hasta", value=max_date, min_value=min_date, max_value=max_date, key="hist_to")
                    with col_r3:
                        proy_filter = st.radio("Tipo", options=["Todos", "Base", "Proy (j)"], horizontal=True, key="hist_proy_filter")

                    # Aplicar filtros comunes
                    mask = (df_hist["fecha_hoy"].dt.date >= date_from) & (df_hist["fecha_hoy"].dt.date <= date_to)
                    if proy_filter == "Base":
                        mask &= df_hist["Proy"] == 0
                    elif proy_filter == "Proy (j)":
                        mask &= df_hist["Proy"] == 1
                    df_f = df_hist[mask].copy()

                    if df_f.empty:
                        st.info("No hay datos en el rango/filtro seleccionado.")
                    else:
                        codigos_f = sorted(df_f["Código"].unique().tolist())

                        # ── Vista 1: Un bono ──
                        if view_mode.startswith("Un bono"):
                            code_sel = st.selectbox("Bono", options=codigos_f, key="hist_single_code")
                            sub = df_f[df_f["Código"] == code_sel].sort_values("fecha_hoy")

                            if sub.empty or go is None:
                                st.info("Sin datos para este bono en el rango.")
                            else:
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=sub["fecha_hoy"], y=sub["Last Price"],
                                    mode="lines", name="Precio", yaxis="y",
                                    hovertemplate="%{x|%Y-%m-%d}<br>Px=%{y:,.4f}<extra></extra>",
                                    line=dict(color="#3498db"),
                                ))
                                fig.add_trace(go.Scatter(
                                    x=sub["fecha_hoy"], y=pd.to_numeric(sub["TIREA"]) * 100.0,
                                    mode="lines", name="TIREA (%)", yaxis="y2",
                                    hovertemplate="%{x|%Y-%m-%d}<br>TIREA=%{y:.2f}%<extra></extra>",
                                    line=dict(color="#e74c3c"),
                                ))
                                fig.update_layout(
                                    title=f"{code_sel} — Precio & TIREA",
                                    xaxis=dict(title="Fecha"),
                                    yaxis=dict(title="Precio", side="left"),
                                    yaxis2=dict(title="TIREA (%)", overlaying="y", side="right"),
                                    height=520,
                                    hovermode="x unified",
                                    legend_orientation="h",
                                    legend_yanchor="bottom", legend_y=1.02,
                                )
                                _st_plotly(fig)

                                # Stats
                                stats = {
                                    "Último precio": f"{sub['Last Price'].iloc[-1]:,.4f}",
                                    "Última TIREA": f"{sub['TIREA'].iloc[-1]:.2%}",
                                    "Última Duration": f"{sub['Duration'].iloc[-1]:.4f}",
                                    "Fecha última obs.": sub["fecha_hoy"].iloc[-1].strftime("%Y-%m-%d"),
                                    "Δ Precio (período)": f"{(sub['Last Price'].iloc[-1] / sub['Last Price'].iloc[0] - 1):.2%}",
                                    "Δ TIREA (bps)": f"{(sub['TIREA'].iloc[-1] - sub['TIREA'].iloc[0]) * 10000:+.0f}",
                                }
                                cols_stat = st.columns(len(stats))
                                for (k, v), c in zip(stats.items(), cols_stat):
                                    c.metric(k, v)

                        # ── Vista 2: Comparador TIR ──
                        # ── Vista 1b: Curva completa (evolución histórica de todas las TIR) ──
                        elif view_mode.startswith("Curva completa"):
                            st.caption(
                                "Cada línea es la TIREA histórica de un bono de la curva seleccionada. "
                                "Las líneas horizontales son el promedio y rango histórico del conjunto."
                            )

                            # Selector de "curva": usamos los mismos grupos de la app (CER/LECAP/TAMAR/etc.)
                            # pero los resolvemos al universo de códigos del histórico.
                            curve_groups = build_curve_codes()
                            curve_opts_hist = []
                            for curve_def in CURVES:
                                codes_in_curve = set(curve_groups.get(curve_def.key, []))
                                # Códigos del histórico que pertenecen a esa curva (sin sufijo j/v)
                                hist_base_codes = {_md_code_from_calc_code(c) for c in codigos_f}
                                calc_base_codes = {_md_code_from_calc_code(c) for c in codes_in_curve}
                                overlap = hist_base_codes & calc_base_codes
                                if overlap:
                                    curve_opts_hist.append(curve_def.key)

                            if not curve_opts_hist:
                                st.info("No hay curvas con datos históricos en este rango.")
                            else:
                                col_cv1, col_cv2, col_cv3 = st.columns([1, 1, 1])
                                with col_cv1:
                                    hist_curve_sel = st.selectbox(
                                        "Curva",
                                        options=curve_opts_hist,
                                        format_func=lambda k: curve_labels.get(k, k),
                                        key="hist_curve_sel",
                                    )
                                with col_cv2:
                                    hist_y_metric = st.selectbox(
                                        "Métrica",
                                        options=["TIREA", "TEM", "TNA", "Paridad"],
                                        index=0,
                                        key="hist_curve_metric",
                                    )
                                with col_cv3:
                                    hist_show_bands = st.toggle(
                                        "Mostrar promedio y rango",
                                        value=True,
                                        key="hist_curve_bands",
                                    )

                                # Códigos del histórico que pertenecen a esta curva
                                curve_codes_raw = curve_groups.get(hist_curve_sel, [])
                                curve_base_codes = {_md_code_from_calc_code(c) for c in curve_codes_raw}

                                # Respetar el filtro Proy del usuario:
                                # - si eligió "Base" → solo Proy=0
                                # - si eligió "Proy (j)" → solo Proy=1
                                # - si "Todos" → buscamos por base_code (stripping j/v) y mostramos ambos
                                df_curve_hist = df_f[
                                    df_f["Código"].map(_md_code_from_calc_code).isin(curve_base_codes)
                                ].copy()

                                if df_curve_hist.empty or go is None:
                                    st.info("Sin datos históricos para esta curva en el rango seleccionado.")
                                else:
                                    fig = go.Figure()

                                    codes_in_hist = sorted(df_curve_hist["Código"].unique())
                                    scale = 100.0 if hist_y_metric in ("TIREA", "TEM", "TNA", "Paridad") else 1.0

                                    # Un trace por código
                                    for c in codes_in_hist:
                                        sub = df_curve_hist[df_curve_hist["Código"] == c].sort_values("fecha_hoy")
                                        if sub.empty or hist_y_metric not in sub.columns:
                                            continue
                                        y = pd.to_numeric(sub[hist_y_metric], errors="coerce") * scale
                                        fig.add_trace(go.Scatter(
                                            x=sub["fecha_hoy"], y=y,
                                            mode="lines", name=c,
                                            hovertemplate=f"{c}<br>%{{x|%Y-%m-%d}}<br>{hist_y_metric}=%{{y:.2f}}%<extra></extra>",
                                        ))

                                    # Líneas de referencia: promedio y rango del agregado
                                    if hist_show_bands:
                                        all_vals = pd.to_numeric(df_curve_hist[hist_y_metric], errors="coerce").dropna() * scale
                                        if not all_vals.empty:
                                            mean_v = float(all_vals.mean())
                                            min_v = float(all_vals.min())
                                            max_v = float(all_vals.max())
                                            fig.add_hline(
                                                y=mean_v, line_dash="solid", line_color="#7f8c8d", line_width=1.2,
                                                annotation_text=f"Prom: {mean_v:.1f}%",
                                                annotation_position="right",
                                            )
                                            fig.add_hline(
                                                y=min_v, line_dash="dash", line_color="#95a5a6", line_width=0.8,
                                                annotation_text=f"Mín: {min_v:.1f}%",
                                                annotation_position="right",
                                            )
                                            fig.add_hline(
                                                y=max_v, line_dash="dash", line_color="#95a5a6", line_width=0.8,
                                                annotation_text=f"Máx: {max_v:.1f}%",
                                                annotation_position="right",
                                            )

                                    fig.update_layout(
                                        title=f"Evolución histórica — {curve_labels.get(hist_curve_sel, hist_curve_sel)} ({hist_y_metric})",
                                        xaxis_title="Fecha",
                                        yaxis_title=f"{hist_y_metric} (%)",
                                        height=560,
                                        hovermode="x unified",
                                        legend_orientation="h",
                                        legend_yanchor="bottom", legend_y=-0.25,
                                        legend_xanchor="left", legend_x=0,
                                        margin=dict(l=10, r=80, t=60, b=80),
                                    )
                                    _st_plotly(fig)

                                    # Stats agregadas
                                    all_vals = pd.to_numeric(df_curve_hist[hist_y_metric], errors="coerce").dropna() * scale
                                    if not all_vals.empty:
                                        s1, s2, s3, s4, s5 = st.columns(5)
                                        s1.metric("Bonos", len(codes_in_hist))
                                        s2.metric(f"Prom {hist_y_metric}", f"{all_vals.mean():.2f}%")
                                        s3.metric("Mín", f"{all_vals.min():.2f}%")
                                        s4.metric("Máx", f"{all_vals.max():.2f}%")
                                        s5.metric("Desvío", f"{all_vals.std():.2f}%")

                                    # Snapshot de la última fecha por bono (útil para comparar con la curva actual)
                                    with st.expander("Último valor por bono (snapshot más reciente)", expanded=False):
                                        last_by_code = (
                                            df_curve_hist
                                            .sort_values("fecha_hoy")
                                            .groupby("Código")
                                            .tail(1)
                                            [["Código", "fecha_hoy", "Last Price", "TIREA", "TEM", "Duration", "Paridad"]]
                                            .sort_values("Duration" if "Duration" in df_curve_hist.columns else "Código")
                                            .reset_index(drop=True)
                                        )
                                        st.dataframe(
                                            last_by_code.style.format({
                                                "Last Price": "{:,.4f}",
                                                "TIREA": "{:.2%}",
                                                "TEM": "{:.2%}",
                                                "Duration": "{:.4f}",
                                                "Paridad": "{:.2%}",
                                            }, na_rep="—"),
                                            width="stretch",
                                            height=min(400, 40 + 35 * len(last_by_code)),
                                        )
                        elif view_mode.startswith("Comparador"):
                            codes_multi = st.multiselect(
                                "Bonos a comparar",
                                options=codigos_f,
                                default=codigos_f[:3] if len(codigos_f) >= 3 else codigos_f,
                                key="hist_multi_codes",
                            )
                            if codes_multi and go is not None:
                                fig = go.Figure()
                                for c in codes_multi:
                                    sub = df_f[df_f["Código"] == c].sort_values("fecha_hoy")
                                    if sub.empty:
                                        continue
                                    fig.add_trace(go.Scatter(
                                        x=sub["fecha_hoy"],
                                        y=pd.to_numeric(sub["TIREA"]) * 100.0,
                                        mode="lines", name=c,
                                        hovertemplate=f"{c}<br>%{{x|%Y-%m-%d}}<br>TIREA=%{{y:.2f}}%<extra></extra>",
                                    ))
                                fig.update_layout(
                                    title="Evolución histórica de TIREA",
                                    xaxis_title="Fecha",
                                    yaxis_title="TIREA (%)",
                                    height=520,
                                    hovermode="x unified",
                                    legend_orientation="h",
                                    legend_yanchor="bottom", legend_y=1.02,
                                )
                                _st_plotly(fig)

                        # ── Vista 3: Spread entre bonos ──
                        elif view_mode.startswith("Spread"):
                            col_sp1, col_sp2 = st.columns(2)
                            with col_sp1:
                                code_a = st.selectbox("Bono A (largo)", options=codigos_f, key="hist_sp_a")
                            with col_sp2:
                                code_b = st.selectbox("Bono B (corto)", options=codigos_f,
                                                      index=min(1, len(codigos_f) - 1), key="hist_sp_b")

                            if code_a and code_b and go is not None:
                                sub_a = df_f[df_f["Código"] == code_a].set_index("fecha_hoy")["TIREA"]
                                sub_b = df_f[df_f["Código"] == code_b].set_index("fecha_hoy")["TIREA"]
                                spread = (sub_a - sub_b).dropna() * 10000  # bps

                                if spread.empty:
                                    st.info("No hay fechas en común entre los dos bonos en este rango.")
                                else:
                                    fig = go.Figure()
                                    fig.add_trace(go.Scatter(
                                        x=spread.index, y=spread.values,
                                        mode="lines", name=f"{code_a} − {code_b}",
                                        fill="tozeroy", line=dict(color="#9b59b6"),
                                        hovertemplate="%{x|%Y-%m-%d}<br>Spread=%{y:+.0f} bps<extra></extra>",
                                    ))
                                    fig.add_hline(y=spread.mean(), line_dash="dash", line_color="#7f8c8d",
                                                  annotation_text=f"Prom: {spread.mean():+.0f} bps",
                                                  annotation_position="top right")
                                    fig.update_layout(
                                        title=f"Spread histórico TIR: {code_a} − {code_b}",
                                        xaxis_title="Fecha",
                                        yaxis_title="Spread (bps)",
                                        height=520,
                                        hovermode="x unified",
                                    )
                                    _st_plotly(fig)

                                    # Stats del spread
                                    s1, s2, s3, s4, s5 = st.columns(5)
                                    s1.metric("Último", f"{spread.iloc[-1]:+.0f} bps")
                                    s2.metric("Promedio", f"{spread.mean():+.0f} bps")
                                    s3.metric("Mín", f"{spread.min():+.0f} bps")
                                    s4.metric("Máx", f"{spread.max():+.0f} bps")
                                    s5.metric("Desvío", f"{spread.std():.0f} bps")

                                    # Z-score del spread actual vs histórico
                                    z = (spread.iloc[-1] - spread.mean()) / spread.std() if spread.std() > 0 else 0
                                    if abs(z) >= 1.5:
                                        emoji = "🔴" if z > 0 else "🟢"
                                        st.caption(
                                            f"{emoji} Spread actual está a **{z:+.2f} σ** del promedio histórico — "
                                            f"{'wide' if z > 0 else 'tight'} vs la media."
                                        )

                        # ── Vista 4: Tabla completa ──
                        else:
                            code_opts = st.multiselect(
                                "Filtrar códigos (vacío = todos)",
                                options=codigos_f,
                                default=[],
                                key="hist_tbl_codes",
                            )
                            tbl = df_f.copy()
                            if code_opts:
                                tbl = tbl[tbl["Código"].isin(code_opts)]
                            tbl = tbl.sort_values(["fecha_hoy", "Código"], ascending=[False, True])

                            st.dataframe(
                                tbl.style.format({
                                    "Last Price": "{:,.4f}",
                                    "TIREA": "{:.2%}",
                                    "TNA": "{:.2%}",
                                    "TEM": "{:.2%}",
                                    "Paridad": "{:.2%}",
                                    "Duration": "{:.4f}",
                                    "tem_spread": "{:+.2%}",
                                }, na_rep="—"),
                                width="stretch",
                                height=600,
                            )

                            csv = tbl.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "📥 Descargar como CSV",
                                data=csv,
                                file_name=f"historico_{date_from}_{date_to}.csv",
                                mime="text/csv",
                            )

        # ─────────────────────────
        # Posiciones (un fondo: TIR/DUR/VN/%PN + futuros)
        # ─────────────────────────
        _historico_live()

    if tab_posiciones:
        st.subheader("Carteras — posiciones por fondo")
        st.caption(
            "Fuente: `Delta_Composicion.xlsx` + `Delta_PN.xlsx`. "
            "TIR / Duration / Precio se calculan en vivo para las especies con curva cargada "
            "(matcheo por `Cod_Delta` ↔ Código BYMA)."
        )

        # Pre-computar referencias para capturar en el closure del fragment.
        _bonds_set = set(BONDS.keys()) if isinstance(BONDS, dict) else set(BONDS)
        _settle = _settlement_date_str(plazo)

        @st.fragment
        def _posiciones_live():
            """Fragment: aísla cambios de widget (fondo/clase) para que NO
            disparen la re-ejecución de main() y el re-render de otros tabs."""
            def _snapshot_fn():
                return _global_snapshot(username, password, plazo)

            OMSposiciones.render_tab_posiciones(
                snapshot_fn=_snapshot_fn,
                parallel_metrics_fn=_parallel_metrics,
                effective_price_fn=_effective_price_series,
                settle=_settle,
                bonds_universe=_bonds_set,
            )

        _posiciones_live()

    # ─────────────────────────
    # Matriz de Tenencias (buscador + matriz especies × fondos)
    # ─────────────────────────
    if tab_matriz:
        st.subheader("Matriz de tenencias — especies × fondos")

        @st.fragment
        def _matriz_live():
            """Fragment: aísla el buscador y la matriz. Cambiar especie,
            toggle, unidad o top-N ya NO re-ejecuta main()."""
            OMSposiciones.render_tab_matriz()

        _matriz_live()

    # [PROFILING TEMPORAL]
    try:
        _main_end = _t_main.perf_counter()
        print(f"━━━ main() finished in {(_main_end-_main_start)*1000:.0f}ms ━━━\n", flush=True)
    except Exception:
        pass

if __name__ == "__main__":
    main()