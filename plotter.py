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
#
# 02/2026 — Fix:
# - pct_series: mejor heurística para TIR/TEM en formato decimal (0.40 -> 40%)
#   evitando el bug de NSS/forwards en tasa fija.

from __future__ import annotations

from datetime import date as _date
from typing import (  # <- Dict/Any para el helper de estimación
    Any,
    Callable,
    Dict,
    Optional,
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


# ──────────────────────────────────
# 1) Modelo Nelson-Siegel-Svensson
# ──────────────────────────────────
def nss_model(x, beta0, beta1, beta2, beta3, tau1, tau2):
    """
    NSS: y(x) = beta0 + beta1*f1 + beta2*f2 + beta3*f3

    Importante:
      - x se interpreta en "años" (en la app se usa Duration).
      - y devuelve "yield en % (puntos porcentuales)".
        Ej: 42.50 significa 42.50%.
    """
    x = np.asarray(x, dtype=np.float64)
    tau1 = max(float(tau1), 1e-8)
    tau2 = max(float(tau2), 1e-8)

    z1 = x / tau1
    exp1 = np.exp(-z1)

    z2 = x / tau2
    exp2 = np.exp(-z2)

    f1 = np.where(x == 0.0, 1.0, (1.0 - exp1) / z1)
    f2 = np.where(x == 0.0, 0.0, f1 - exp1)
    f3 = np.where(x == 0.0, 0.0, (1.0 - exp2) / z2 - exp2)

    return beta0 + beta1 * f1 + beta2 * f2 + beta3 * f3

def ns_model(x, beta0, beta1, beta2, tau1):
    """
    Nelson–Siegel (NS) — 4 params.
    Convención: devuelve yield en % puntos, igual que nss_model.
    """
    x = np.asarray(x, dtype=np.float64)
    tau1 = max(float(tau1), 1e-8)

    z1 = x / tau1
    exp1 = np.exp(-z1)

    f1 = np.where(x == 0.0, 1.0, (1.0 - exp1) / z1)
    f2 = np.where(x == 0.0, 0.0, f1 - exp1)

    return beta0 + beta1 * f1 + beta2 * f2


def _robust_outlier_mask(resid: np.ndarray, threshold_factor: float = 3.0) -> np.ndarray:
    """
    Máscara de NO-outliers usando MAD (Median Absolute Deviation) escalado.

    A diferencia de un filtro clásico ±k·std, MAD no se infla con los propios
    outliers — un único punto fuera de curva no ‘arrastra’ el umbral. Es el
    estimador robusto estándar (Huber, Hampel).

    sigma_robusto = 1.4826 * median(|r - median(r)|)
    Punto i es válido si |r_i - median(r)| <= threshold_factor * sigma_robusto.

    `threshold_factor` está en unidades de "sigmas robustos":
      - 2.5 → bastante estricto
      - 3.0 → estándar (recomendado)
      - 4.0 → permisivo
    """
    r = np.asarray(resid, dtype=np.float64)
    if r.size == 0:
        return np.ones(0, dtype=bool)

    med = float(np.nanmedian(r))
    abs_dev = np.abs(r - med)
    mad = float(np.nanmedian(abs_dev))
    sigma = 1.4826 * mad

    # Fallback si MAD es ~0 (curva casi exacta o muchos puntos repetidos)
    if (not np.isfinite(sigma)) or sigma <= 1e-12:
        sigma = float(np.nanstd(r, ddof=0))
        if (not np.isfinite(sigma)) or sigma <= 1e-12:
            return np.ones_like(r, dtype=bool)

    return abs_dev <= (float(threshold_factor) * sigma)


def _fit_ns_grid_ols(
    X: np.ndarray,
    y: np.ndarray,
    threshold_factor: float = 3.0,
    tau_bounds: tuple[float, float] = (0.05, 10.0),
    tau_grid: int = 80,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Fit NS robusto para pocos puntos:
    - grid logspace en tau1
    - OLS para (beta0,beta1,beta2) dado tau1
    - filtra outliers con el mismo esquema que NSS: residuales vs std

    Devuelve:
      popt_ns (beta0,beta1,beta2,tau1), mask usados
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if X.size < 4:
        raise ValueError("No hay suficientes puntos para ajustar NS (mínimo 4).")

    # grid logspace para estabilidad
    tmin, tmax = float(tau_bounds[0]), float(tau_bounds[1])
    taus = np.exp(np.linspace(np.log(tmin), np.log(tmax), int(tau_grid)))

    best = None
    best_sse = np.inf

    for tau1 in taus:
        z = X / tau1
        exp1 = np.exp(-z)
        f1 = np.where(X == 0.0, 1.0, (1.0 - exp1) / z)
        f2 = np.where(X == 0.0, 0.0, f1 - exp1)

        A = np.column_stack([np.ones_like(X), f1, f2])  # beta0,beta1,beta2
        try:
            beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        except Exception:
            continue

        yhat = A @ beta
        resid = y - yhat
        sse = float(np.nansum(resid ** 2))
        if np.isfinite(sse) and sse < best_sse:
            best_sse = sse
            best = (float(beta[0]), float(beta[1]), float(beta[2]), float(tau1))

    if best is None:
        raise ValueError("No se pudo ajustar NS (grid/OLS).")

    popt = np.array(best, dtype=np.float64)

    # outliers pass — MAD robusto (mismo criterio que NSS)
    yhat = ns_model(X, *popt)
    mask = _robust_outlier_mask(y - yhat, threshold_factor=float(threshold_factor))
    if np.count_nonzero(mask) < 4:
        mask = np.ones_like(y, dtype=bool)
        return popt, mask

    # refit OLS con tau1 fijo usando puntos usados
    tau1 = float(popt[3])
    z = X[mask] / tau1
    exp1 = np.exp(-z)
    f1 = np.where(X[mask] == 0.0, 1.0, (1.0 - exp1) / z)
    f2 = np.where(X[mask] == 0.0, 0.0, f1 - exp1)
    A = np.column_stack([np.ones_like(X[mask]), f1, f2])

    beta2, *_ = np.linalg.lstsq(A, y[mask], rcond=None)
    popt2 = np.array([float(beta2[0]), float(beta2[1]), float(beta2[2]), tau1], dtype=np.float64)

    return popt2, mask


# ──────────────────────────────────
# 2) Utilidad: convierte columna a %
# ──────────────────────────────────
def pct_series(s: pd.Series, ratio_threshold: float = 2.0) -> pd.Series:
    """
    Convierte una serie a float en porcentaje (100 = 100%).

    Heurística pensada para yields (TIREA/TEM) que pueden venir:
      - como decimales: 0.40 = 40%, 0.033 = 3.3%
      - como % "humanos": 40 = 40%, 3.3 = 3.3%
      - como strings con %: "41.69%" -> 41.69

    Reglas:
      - Strings con '%': se interpretan como porcentaje directo (se quita el '%').
      - Numéricos:
          * abs(x) <= ratio_threshold  -> se asume decimal (ratio) y se multiplica por 100.
          * abs(x) > ratio_threshold   -> se asume que ya está en % y se deja igual.

    Nota:
      - Por default ratio_threshold=2.0 (cubre yields hasta 200% en formato decimal).
      - Si tenés una serie numérica donde 0.72 significa "0.72%" (y NO 72%),
        podés llamar pct_series(s, ratio_threshold=0.20) para mantener el comportamiento anterior.
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
    threshold_factor: float = 3.0,
    maxfev: int = 10000,
):
    """
    Ajuste robusto:
      - Si hay >= 6 puntos: intenta NSS (6 params)
      - Si hay 4 o 5 puntos: fallback NS (4 params) y lo convierte a NSS equivalente:
            beta3 = 0
            tau2  = 2*tau1

    Filtro de outliers: MAD escalado (1.4826·MAD) en vez de std clásica
    — el std se infla con outliers y a veces ‘deja pasar’ el bono raro;
    el MAD es robusto. Se hacen hasta 2 pasadas de refit + remask para
    converger a un fit estable.

    Devuelve: popt (siempre 6 params NSS), mask
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    n = int(np.sum(np.isfinite(X) & np.isfinite(y)))
    if n < 4:
        raise ValueError("No hay suficientes puntos para ajustar curva (mínimo 4).")

    # ---------- Caso NSS full ----------
    if n >= 6:
        # Filtrar NaN antes de calcular mean y pasar a curve_fit:
        # np.mean sobre array con NaN devuelve NaN silenciosamente y
        # contamina p0, haciendo que curve_fit falle o converja mal.
        finite_mask = np.isfinite(X) & np.isfinite(y)
        X_fit = X[finite_mask]
        y_fit = y[finite_mask]

        y_mean = float(np.nanmean(y_fit)) if y_fit.size > 0 and np.isfinite(y_fit).any() else 0.0
        p0 = np.array([y_mean, 0.0, 0.0, 0.0, 1.0, 1.0], dtype=np.float64)
        popt, _ = curve_fit(nss_model, X_fit, y_fit, p0=p0, maxfev=maxfev)

        # Iteración robusta: refit + remask hasta converger (máx. 3 pasadas)
        mask = np.ones_like(y, dtype=bool)
        for _ in range(3):
            yhat = nss_model(X, *popt)
            new_mask = _robust_outlier_mask(y - yhat, threshold_factor=float(threshold_factor))
            # Mantener al menos 6 puntos para no perder grados de libertad
            if np.count_nonzero(new_mask) < 6:
                break
            if np.array_equal(new_mask, mask):
                break
            mask = new_mask
            try:
                popt, _ = curve_fit(nss_model, X[mask], y[mask], p0=popt, maxfev=maxfev)
            except Exception:
                # si el refit falla, mantenemos el último popt válido y cortamos
                break

        return popt, mask

    # ---------- Caso fallback NS (4-5 puntos) ----------
    popt_ns, mask = _fit_ns_grid_ols(
        X, y,
        threshold_factor=float(threshold_factor),
        tau_bounds=(0.05, 10.0),
        tau_grid=90,
    )

    b0, b1, b2, t1 = [float(v) for v in popt_ns]

    # convertimos NS -> NSS equivalente
    # (sirve para TODO el pipeline actual que grafica con nss_model)
    popt_nss = np.array([b0, b1, b2, 0.0, t1, 2.0 * t1], dtype=np.float64)

    return popt_nss, mask


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
    xlim: tuple[float, float] | None = None,   # ← zoom opcional
):
    # rango para la curva (si hay zoom válido, generamos xx en ese rango)
    if xlim is not None:
        x0, x1 = float(xlim[0]), float(xlim[1])
        if np.isfinite(x0) and np.isfinite(x1) and (x1 > x0):
            xx = np.linspace(x0, x1, 140, dtype=np.float64)
        else:
            x_lo = float(np.nanmin(X)) if np.isfinite(X).any() else 0.0
            x_hi = float(np.nanmax(X)) if np.isfinite(X).any() else 1.0
            xx = np.linspace(x_lo, x_hi, 140, dtype=np.float64)
            xlim = None
    else:
        x_lo = float(np.nanmin(X)) if np.isfinite(X).any() else 0.0
        x_hi = float(np.nanmax(X)) if np.isfinite(X).any() else 1.0
        xx = np.linspace(x_lo, x_hi, 140, dtype=np.float64)

    yy = nss_model(xx, *popt)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(X[mask], y[mask], label="Datos usados")
    if np.any(~mask):
        ax.scatter(X[~mask], y[~mask], marker="x", s=80, label="Outliers")
    ax.plot(xx, yy, label="Ajuste NSS")

    _annotate(ax, X[mask], y[mask], codes[mask], tir[mask], tem[mask], max_labels=max_labels)

    if xlim is not None:
        ax.set_xlim(float(xlim[0]), float(xlim[1]))

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
def graficar_duration_tem_nss(
    df: pd.DataFrame,
    threshold_factor: float = 3.0,
    max_labels: int | None = None,
    rango_x_min_plot: float | None = None,
    rango_x_max_plot: float | None = None,
):
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

    xlim = None
    if rango_x_min_plot is not None and rango_x_max_plot is not None:
        xlim = (float(rango_x_min_plot), float(rango_x_max_plot))

    _plot_nss(
        X=X, y=y, mask=mask, popt=popt2,
        xlabel="Duration (años)", ylabel="TEM (%)",
        title="Nelson-Siegel-Svensson — Duration vs TEM",
        codes=codes, tir=tir, tem=tem,
        max_labels=max_labels,
        xlim=xlim,
    )


# ──────────────────────────────────
# 5) Duration vs TIR (NSS)
# ──────────────────────────────────
def graficar_duration_tir_nss(
    df: pd.DataFrame,
    threshold_factor: float = 3.0,
    max_labels: int | None = None,
    rango_x_min_plot: float | None = None,
    rango_x_max_plot: float | None = None,
):
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

    xlim = None
    if rango_x_min_plot is not None and rango_x_max_plot is not None:
        xlim = (float(rango_x_min_plot), float(rango_x_max_plot))

    _plot_nss(
        X=X, y=y, mask=mask, popt=popt2,
        xlabel="Duration (años)", ylabel="TIR (%)",
        title="Nelson-Siegel-Svensson — Duration vs TIR",
        codes=codes, tir=tir, tem=tem,
        max_labels=max_labels,
        xlim=xlim,
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
    comp: str = "ea",      # default TEA (alineado a “TIR”)
    min_years: float = 1e-6,
    t_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Matriz triangular de forwards implícitos ENTRE BONOS.

    - Fila = bono corto (t1)
    - Columna = bono largo (t2)
    - Celda = forward anualizado entre t1 y t2 (en % 0-100)

    Eje temporal (t):
      - Si t_col está definido (ej "Duration"): usa esa columna del df directamente
        como t (en años). Más correcto para bonos amortizables o con cashflows
        intermedios significativos.
      - Si t_col es None (default, backwards-compatible):
          * prioridad: maturity_map[codigo]
          * sino: bond_lookup(codigo).vencimiento
          * sino: globals()[codigo].vencimiento (si bond_lookup es None)

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

    # Columnas requeridas
    req_cols = [code_col, y_col]
    if t_col is not None:
        req_cols.append(t_col)

    tmp = df[req_cols].copy()
    tmp = tmp.dropna(subset=[code_col, y_col])

    codes = tmp[code_col].astype(str).to_numpy()

    # TIR en decimal (pct_series retorna 0-100)
    tir_pct = pct_series(tmp[y_col])
    y = (tir_pct.to_numpy(dtype="float64") / 100.0)

    # t (años): desde t_col (Duration) o desde vencimiento
    if t_col is not None:
        t = pd.to_numeric(tmp[t_col], errors="coerce").to_numpy(dtype="float64")
    else:
        t = np.full(len(tmp), np.nan, dtype="float64")

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
    out.index.name = "Forwards (Duration)" if t_col is not None else "Forwards en TIR"
    return out


# ──────────────────────────────────
# 7) Estimar TIR/TEM desde Duration con NSS (sin plot)
# ──────────────────────────────────

# cache simple para no refitear si llamás mil veces con la misma curva
# key: (id(df), threshold_factor, which) -> (popt, x_min, x_max)
_NSS_FIT_CACHE: dict[tuple[int, float, str], tuple[np.ndarray, float, float]] = {}


def _fit_nss_cached(
    df: pd.DataFrame,
    which: str = "TIREA",              # "TIREA" o "TEM"
    threshold_factor: float = 3.0,
    use_cache: bool = True,
) -> tuple[np.ndarray, float, float]:
    """
    Ajusta NSS sobre (Duration -> which) y devuelve:
      popt, x_min, x_max
    con cache por identidad del df (id(df)).
    """
    which = (which or "TIREA").upper()
    if which not in ("TIREA", "TEM"):
        raise ValueError("which debe ser 'TIREA' o 'TEM'")

    key = (id(df), float(threshold_factor), which)
    if use_cache and key in _NSS_FIT_CACHE:
        return _NSS_FIT_CACHE[key]

    tmp = _prep_df(df)
    if len(tmp) < 4:
        raise ValueError("No hay suficientes puntos válidos para ajustar NSS (mínimo 4).")

    X = tmp["Duration"].to_numpy(dtype=np.float64)
    y = tmp["TIREA_"].to_numpy(dtype=np.float64) if which == "TIREA" else tmp["TEM_"].to_numpy(dtype=np.float64)

    popt, mask = _fit_nss_with_outliers(X, y, threshold_factor=float(threshold_factor))

    # rango observado (post outliers) para poder clippear
    X_used = X[mask] if mask is not None and np.any(mask) else X
    if X_used.size == 0 or not np.isfinite(X_used).any():
        raise ValueError("No hay valores finitos de Duration tras filtrar outliers.")
    x_min = float(np.nanmin(X_used))
    x_max = float(np.nanmax(X_used))

    out = (popt, x_min, x_max)
    if use_cache:
        _NSS_FIT_CACHE[key] = out
    return out


def estimar_dur_tirtem_nss(
    duration: float,
    curva: pd.DataFrame,
    threshold_factor: float = 3.0,
    clip: bool = True,
    use_cache: bool = True,
    tem_from_tir: bool = True,
) -> Dict[str, Any]:
    """
    Estima TIREA y TEM para una duration dada usando NSS (Duration -> yield).

    Returns dict con:
      - duration_in / duration_used
      - x_min / x_max
      - TIREA / TEM (decimal)
      - TIREA_pct / TEM_pct (en %)
    """
    dur_in = float(duration)

    # 1) Fit NSS para TIR
    popt_tir, x_min, x_max = _fit_nss_cached(
        curva, which="TIREA", threshold_factor=threshold_factor, use_cache=use_cache
    )

    dur_used = dur_in
    if clip:
        dur_used = float(np.clip(dur_used, x_min, x_max))

    tirea_pct = float(nss_model(dur_used, *popt_tir))
    tirea = tirea_pct / 100.0  # decimal

    # 2) TEM
    if tem_from_tir:
        # conversión simple TEA->TEM (aprox 30/360)
        tem = (1.0 + tirea) ** (30.0 / 360.0) - 1.0
        tem_pct = tem * 100.0
    else:
        popt_tem, x_min2, x_max2 = _fit_nss_cached(
            curva, which="TEM", threshold_factor=threshold_factor, use_cache=use_cache
        )
        if clip:
            dur_used2 = float(np.clip(dur_in, x_min2, x_max2))
        else:
            dur_used2 = dur_in
        tem_pct = float(nss_model(dur_used2, *popt_tem))
        tem = tem_pct / 100.0

    return {
        "duration_in": dur_in,
        "duration_used": dur_used,
        "x_min": x_min,
        "x_max": x_max,
        "TIREA": tirea,
        "TEM": tem,
        "TIREA_pct": tirea_pct,
        "TEM_pct": float(tem_pct),
    }