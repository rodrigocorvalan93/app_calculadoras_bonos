# -*- coding: utf-8 -*-
# plotter.py
# ==========
# Graficadores + ajuste Nelson-Siegel-Svensson (NSS)
# + Matriz de forwards aproximados desde TIREA
#
# Optimizado:
# - evita iterrows
# - minimiza overhead pandas
# - reduce evaluaciones redundantes del modelo
# - permite limitar anotaciones con max_labels

from __future__ import annotations

from datetime import date as _date
from typing import Callable, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


# ──────────────────────────────────
# 1) Modelo Nelson-Siegel-Svensson
# ──────────────────────────────────
def nss_model(x, beta0, beta1, beta2, beta3, tau1, tau2):
    """
    NSS: y(x) = beta0 + beta1*f1 + beta2*f2 + beta3*f3
    """
    x = np.asarray(x, dtype=np.float64)
    tau1 = float(tau1)
    tau2 = float(tau2)

    if tau1 == 0.0:
        z1 = np.zeros_like(x)
        exp1 = np.ones_like(x)
    else:
        z1 = x / tau1
        exp1 = np.exp(-z1)

    if tau2 == 0.0:
        z2 = np.zeros_like(x)
        exp2 = np.ones_like(x)
    else:
        z2 = x / tau2
        exp2 = np.exp(-z2)

    f1 = np.where(x == 0.0, 1.0, (1.0 - exp1) / z1)
    f2 = np.where(x == 0.0, 0.0, f1 - exp1)
    f3 = np.where(x == 0.0, 0.0, (1.0 - exp2) / z2 - exp2)

    return beta0 + beta1 * f1 + beta2 * f2 + beta3 * f3


# ──────────────────────────────────
# 2) Utilidad: convierte columna a %
# ──────────────────────────────────
def pct_series(s: pd.Series, ratio_threshold: float = 0.20) -> pd.Series:
    """
    Convierte una serie a float en porcentaje (100 = 100%).

    Reglas robustas (clave para tu caso CER):

    - Strings con '%': se interpretan como %.
        "0.72%" -> 0.72
        "41.69%" -> 41.69

    - Numéricos:
        * abs(x) <= ratio_threshold  -> ratio (0.033 = 3.3%) => x*100
        * ratio_threshold < abs(x) <= 2.0 -> % chico (0.72 = 0.72%) => x
        * abs(x) > 2.0 -> % normal (41.69 = 41.69%) => x
    """
    if s is None:
        return pd.Series(dtype="float64")

    rt = float(ratio_threshold)

    if pd.api.types.is_numeric_dtype(s):
        out = pd.to_numeric(s, errors="coerce").astype("float64")
        m_ratio = out.abs() <= rt
        out = out.where(~m_ratio, out * 100.0)
        return out

    # strings
    s_str = s.astype(str)
    has_pct = s_str.str.contains("%", regex=False, na=False)

    cleaned = (
        s_str
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    out = pd.to_numeric(cleaned, errors="coerce").astype("float64")

    # si NO tenía % y parece ratio -> *100
    m_ratio = (~has_pct) & (out.abs() <= rt)
    out = out.where(~m_ratio, out * 100.0)
    return out


# ──────────────────────────────────
# 3) Helpers internos (performance)
# ──────────────────────────────────
_REQ = ("Duration", "TEM", "TIREA", "Código")


def _prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpieza mínima y conversiones.
    Devuelve columnas: Duration(float), TEM_(%), TIREA_(%), Código(str)
    """
    tmp = df.dropna(subset=_REQ).copy()
    tmp["Duration"] = pd.to_numeric(tmp["Duration"], errors="coerce")
    tmp["TEM_"] = pct_series(tmp["TEM"])
    tmp["TIREA_"] = pct_series(tmp["TIREA"])
    tmp["Código"] = tmp["Código"].astype(str)
    tmp = tmp.dropna(subset=["Duration", "TEM_", "TIREA_"])
    return tmp


def _fit_nss_with_outliers(
    X: np.ndarray,
    y: np.ndarray,
    threshold_factor: float = 2.0,
    maxfev: int = 10000,
):
    if X.size < 4:
        raise ValueError("No hay suficientes puntos para ajustar NSS (mínimo 4).")

    p0 = np.array([float(np.mean(y)), 0.0, 0.0, 0.0, 1.0, 1.0], dtype=np.float64)
    popt, _ = curve_fit(nss_model, X, y, p0=p0, maxfev=maxfev)

    yhat = nss_model(X, *popt)
    resid = y - yhat
    s = float(np.std(resid, ddof=0))

    if (not np.isfinite(s)) or s == 0.0:
        mask = np.ones_like(y, dtype=bool)
        return popt, mask

    mask = np.abs(resid) <= (float(threshold_factor) * s)

    if np.count_nonzero(mask) < 4:
        mask = np.ones_like(y, dtype=bool)
        return popt, mask

    popt2, _ = curve_fit(nss_model, X[mask], y[mask], p0=popt, maxfev=maxfev)
    return popt2, mask


def _pick_label_indices(n: int, max_labels: int | None) -> np.ndarray:
    if max_labels is None or n <= max_labels:
        return np.arange(n, dtype=int)
    return np.linspace(0, n - 1, int(max_labels), dtype=int)


def _annotate(ax, X, y, codes, tir, tem, max_labels: int | None = None, fontsize: int = 7):
    idx = _pick_label_indices(X.size, max_labels)
    for i in idx:
        ax.annotate(
            f"{codes[i]}\nTIR: {tir[i]:.2f}%\nTEM: {tem[i]:.2f}%",
            (X[i], y[i]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=fontsize,
        )


def _plot_nss(
    X: np.ndarray,
    y: np.ndarray,
    mask: np.ndarray,
    popt: np.ndarray,
    xlabel: str,
    ylabel: str,
    title: str,
    codes: np.ndarray,
    tir: np.ndarray,
    tem: np.ndarray,
    max_labels: int | None = None,
):
    xx = np.linspace(float(np.min(X)), float(np.max(X)), 140, dtype=np.float64)
    yy = nss_model(xx, *popt)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(X[mask], y[mask], label="Datos usados")
    if np.any(~mask):
        ax.scatter(X[~mask], y[~mask], marker="x", s=80, label="Outliers")
    ax.plot(xx, yy, label="Ajuste NSS")

    _annotate(ax, X[mask], y[mask], codes[mask], tir[mask], tem[mask], max_labels=max_labels)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    fig.tight_layout()
    plt.show()


# ──────────────────────────────────
# 4) Duration vs TEM (NSS)
# ──────────────────────────────────
def graficar_duration_tem_nss(df: pd.DataFrame, threshold_factor: float = 2.0, max_labels: int | None = None):
    missing = set(_REQ) - set(df.columns)
    if missing:
        print("Faltan columnas:", missing)
        return

    tmp = _prep_df(df)
    if len(tmp) < 4:
        print("No hay suficientes puntos válidos para ajustar NSS.")
        return

    X = tmp["Duration"].to_numpy(dtype=np.float64)
    y = tmp["TEM_"].to_numpy(dtype=np.float64)
    tir = tmp["TIREA_"].to_numpy(dtype=np.float64)
    tem = y
    codes = tmp["Código"].to_numpy(dtype=object)

    try:
        popt2, mask = _fit_nss_with_outliers(X, y, threshold_factor=float(threshold_factor))
    except Exception as e:
        print("Ajuste falló:", e)
        return

    _plot_nss(
        X=X, y=y, mask=mask, popt=popt2,
        xlabel="Duration (años)", ylabel="TEM (%)",
        title="Nelson-Siegel-Svensson — Duration vs TEM",
        codes=codes, tir=tir, tem=tem,
        max_labels=max_labels,
    )


# ──────────────────────────────────
# 5) Duration vs TIR (NSS)
# ──────────────────────────────────
def graficar_duration_tir_nss(df: pd.DataFrame, threshold_factor: float = 2.0, max_labels: int | None = None):
    missing = set(_REQ) - set(df.columns)
    if missing:
        print("Faltan columnas:", missing)
        return

    tmp = _prep_df(df)
    if len(tmp) < 4:
        print("No hay suficientes puntos válidos para ajustar NSS.")
        return

    X = tmp["Duration"].to_numpy(dtype=np.float64)
    y = tmp["TIREA_"].to_numpy(dtype=np.float64)
    tir = y
    tem = tmp["TEM_"].to_numpy(dtype=np.float64)
    codes = tmp["Código"].to_numpy(dtype=object)

    try:
        popt2, mask = _fit_nss_with_outliers(X, y, threshold_factor=float(threshold_factor))
    except Exception as e:
        print("Ajuste falló:", e)
        return

    _plot_nss(
        X=X, y=y, mask=mask, popt=popt2,
        xlabel="Duration (años)", ylabel="TIR (%)",
        title="Nelson-Siegel-Svensson — Duration vs TIR",
        codes=codes, tir=tir, tem=tem,
        max_labels=max_labels,
    )


# ──────────────────────────────────
# 6) Matriz de forwards aproximados desde TIREA
# ──────────────────────────────────
def _to_date(x) -> Optional[_date]:
    if x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None


def _yearfrac_365(d0: _date, d1: _date) -> float:
    return (pd.to_datetime(d1) - pd.to_datetime(d0)).days / 365.0


def _default_bond_lookup(code: str):
    return globals().get(code)


def matriz_forwards_tir(
    df: pd.DataFrame,
    settle_date=None,
    bond_lookup: Optional[Callable[[str], object]] = None,
    maturity_map: Optional[dict] = None,
    y_col: str = "TIREA",
    code_col: str = "Código",
    comp: str = "ea",      # default TEA (más alineado a “TIR”)
    min_years: float = 1e-6,
) -> pd.DataFrame:
    """
    Matriz triangular de forwards implícitos ENTRE BONOS (como tu Excel).

    - Fila = bono corto (t1)
    - Columna = bono largo (t2)
    - Celda = forward anualizado entre t1 y t2 (en % 0-100)

    Maturities:
      - prioridad: maturity_map[codigo]
      - sino: bond_lookup(codigo).vencimiento
      - sino: globals()[codigo].vencimiento (si bond_lookup es None)

    NOTA: Aproximado (usa TIR como spot), no DF curve bootstrapped.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if settle_date is None:
        settle_date = pd.Timestamp.today().date()
    else:
        settle_date = _to_date(settle_date)

    if bond_lookup is None:
        bond_lookup = _default_bond_lookup
    if maturity_map is None:
        maturity_map = {}

    tmp = df[[code_col, y_col]].copy()
    tmp = tmp.dropna(subset=[code_col, y_col])

    codes = tmp[code_col].astype(str).to_numpy()

    # TIR en decimal (pct_series retorna 0-100)
    tir_pct = pct_series(tmp[y_col])
    y = (tir_pct.to_numpy(dtype="float64") / 100.0)

    # t (años) por vencimiento
    t = np.full(len(tmp), np.nan, dtype="float64")

    # FAST PATH: si maturity_map está completo, evitamos buscar objetos (loop simple y barato)
    # (igual hay loop porque dict lookup por elemento, pero no hay objetos ni pandas heavy)
    for i, c in enumerate(codes):
        d = maturity_map.get(c)
        if d is None:
            obj = bond_lookup(c)
            if obj is not None and hasattr(obj, "vencimiento"):
                d = getattr(obj, "vencimiento")
        d = _to_date(d)
        if d is not None:
            t[i] = _yearfrac_365(settle_date, d)

    ok = np.isfinite(t) & np.isfinite(y)
    codes = codes[ok]
    t = t[ok]
    y = y[ok]

    if len(t) < 2:
        return pd.DataFrame(index=codes, columns=codes)

    t = np.maximum(t, float(min_years))

    order = np.argsort(t)
    t = t[order]
    y = y[order]
    codes = codes[order]

    comp = (comp or "ea").lower()
    if comp == "cont":
        dfact = np.exp(-y * t)
    elif comp in ("ea", "tea", "annual"):
        dfact = (1.0 + y) ** (-t)
    else:
        raise ValueError("comp debe ser 'cont' o 'ea'")

    DF1 = dfact.reshape(-1, 1)
    DF2 = dfact.reshape(1, -1)
    ratio = DF1 / DF2

    dt = t.reshape(1, -1) - t.reshape(-1, 1)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        fwd = ratio ** (1.0 / dt) - 1.0

    n = len(t)
    fwd[np.tril_indices(n, k=0)] = np.nan

    out = pd.DataFrame(fwd * 100.0, index=codes, columns=codes)
    out.index.name = "Forwards en TIR"
    return out
