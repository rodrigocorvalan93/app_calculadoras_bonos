"""Nelson-Siegel-Svensson — ajuste de curva (Duration → yield) y estimación de
TIR / TEM / TNA a una duration dada.

Portado *lean* de `plotter.estimar_dur_tirtem_nss` (numpy + scipy, **sin
matplotlib** ni el resto del plotter legacy, que es pesado de importar). Sólo lo
usa la pestaña Gráficos. El ajuste se cachea por fingerprint de los puntos para
no re-fitear en cada refresh de 5 s.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from backend.cache import LockedTTLCache

logger = logging.getLogger(__name__)

# `curve_fit` (scipy, multi-pasada robusta) es la op más cara de la app. El cache
# da compute-once por fingerprint (un solo fit aunque /data, /nss y /estimate
# pidan la MISMA curva en paralelo) y evicta LRU en vez de vaciarse entero al
# llenarse (antes un clear() forzaba decenas de refits fríos). TTL holgado: el
# fingerprint ya rota cuando se mueven los precios.
_cache = LockedTTLCache(maxsize=256, ttl=120)
_NO_FIT = object()   # sentinel: "no fitea" cacheado (LockedTTLCache no cachea None)


def model(x, b0, b1, b2, b3, t1, t2):
    """NSS: y(x) = b0 + b1·f1 + b2·f2 + b3·f3. x en años (Duration), y en % (pp)."""
    x = np.asarray(x, dtype=np.float64)
    t1 = max(float(t1), 1e-8)
    t2 = max(float(t2), 1e-8)
    z1 = x / t1
    e1 = np.exp(-z1)
    z2 = x / t2
    e2 = np.exp(-z2)
    f1 = np.where(x == 0.0, 1.0, (1.0 - e1) / z1)
    f2 = np.where(x == 0.0, 0.0, f1 - e1)
    f3 = np.where(x == 0.0, 0.0, (1.0 - e2) / z2 - e2)
    return b0 + b1 * f1 + b2 * f2 + b3 * f3


def _mad_mask(resid: np.ndarray, k: float = 3.0) -> np.ndarray:
    """Máscara de inliers por MAD robusto (1.4826·MAD), como el legacy."""
    r = np.asarray(resid, dtype=np.float64)
    med = float(np.median(r))
    mad = float(np.median(np.abs(r - med)))
    sigma = (1.4826 * mad) if mad > 0 else (float(np.std(r)) or 1.0)
    return np.abs(r - med) <= (float(k) * sigma)


def _fit_raw(xs, ys, threshold: float, maxfev: int = 10000):
    import warnings

    from scipy.optimize import curve_fit

    X = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    m = np.isfinite(X) & np.isfinite(y)
    X, y = X[m], y[m]
    n = int(X.size)
    if n < 4:
        return None
    try:
        warnings.simplefilter("ignore")          # OptimizeWarning (covarianza) — inocuo
        if n >= 6:
            p0 = np.array([float(np.mean(y)), 0.0, 0.0, 0.0, 1.0, 1.0])
            popt, _ = curve_fit(model, X, y, p0=p0, maxfev=maxfev)
            mask = np.ones(n, dtype=bool)
            for _ in range(3):                       # refit robusto (máx 3 pasadas)
                nm = _mad_mask(y - model(X, *popt), threshold)
                if int(nm.sum()) < 6 or np.array_equal(nm, mask):
                    break
                mask = nm
                popt, _ = curve_fit(model, X[mask], y[mask], p0=popt, maxfev=maxfev)
        else:                                        # 4-5 pts: NS (4 params) → NSS equiv.
            def _ns(x, b0, b1, b2, t1):
                return model(x, b0, b1, b2, 0.0, t1, 2.0 * max(t1, 1e-8))
            p0 = np.array([float(np.mean(y)), 0.0, 0.0, 1.0])
            b0, b1, b2, t1 = (float(v) for v in curve_fit(_ns, X, y, p0=p0, maxfev=maxfev)[0])
            popt = np.array([b0, b1, b2, 0.0, t1, 2.0 * t1])
    except Exception as exc:  # noqa: BLE001
        logger.debug("[nss] fit falló (%d pts): %s", n, exc)
        return None
    return popt, float(np.min(X)), float(np.max(X))


def fit(xs: List[float], ys: List[float], threshold: float = 3.0):
    """Ajuste NSS cacheado por fingerprint de los puntos. (popt, x_min, x_max) o None.

    El cómputo se serializa por clave (compute-once): si varios requests piden la
    misma curva fría a la vez, sólo uno corre `curve_fit` y el resto lee el fit.
    """
    key = (round(float(threshold), 2),
           tuple(round(float(x), 4) for x in xs),
           tuple(round(float(y), 4) for y in ys))
    res = _cache.get_or_compute(key, lambda: _fit_raw(xs, ys, threshold) or _NO_FIT)
    return None if res is _NO_FIT else res


def _tna(tirea: float, freq: float, base: float) -> Optional[float]:
    """TNA bajo convención (freq días/período, base días/año) desde la TIREA."""
    if not (1.0 + tirea > 0.0):      # TIR ≤ −100% (o NaN) → base negativa = nº complejo, no float
        return None
    try:
        return ((1.0 + tirea) ** (freq / base) - 1.0) * (base / freq)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def sample(xs: List[float], ys: List[float], threshold: float = 3.0, n: int = 80):
    """Puntos (x, y%) de la curva NSS sobre el rango de datos → overlay del scatter."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    if not (x_max > x_min):
        return None
    xx = np.linspace(x_min, x_max, n)
    yy = model(xx, *popt)
    return [(float(a), float(b)) for a, b in zip(xx, yy)]


def eval_at(xs: List[float], ys: List[float], xq: List[float], threshold: float = 3.0):
    """Ajusta NSS a (xs, ys) y evalúa en cada x de `xq` (% pp). None fuera del
    rango fiteado, para que la línea no extrapole. Devuelve None si no fitea."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    yq = model(np.asarray(xq, dtype=np.float64), *popt)
    return [float(v) if (x_min <= float(x) <= x_max) else None for x, v in zip(xq, yq)]


def estimate(duration: float, xs: List[float], ys: List[float],
             threshold: float = 3.0, clip: bool = True,
             metric: str = "tirea") -> Optional[Dict[str, Any]]:
    """TIR / TEM / TNAs a una duration dada, vía NSS. y de entrada en %.

    `metric` indica en qué espacio vienen los `ys` (y por tanto el fit): "tirea"
    (TIREA %) o "tem" (TEM %). En modo TEM el valor de la curva ES la TEM; se
    recupera la TIREA anual ((1+TEM)^12 − 1) para derivar TNAs y mostrar ambas.
    """
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    d = float(duration)
    d_used = float(np.clip(d, x_min, x_max)) if clip else d
    val = float(model(d_used, *popt)) / 100.0     # valor de la curva en la métrica fiteada
    if metric == "tem":
        base = 1.0 + val
        tirea = (base ** (360.0 / 30.0) - 1.0) if base > 0.0 else None   # TEM → TIREA anual
    else:
        tirea = val
    # Sobre-extrapolación NSS: TIR ≤ −100% daría potencia COMPLEJA y TIR absurda
    # (p.ej. miles de %) daría OVERFLOW en (1+t)^d → ambas 500-ean json.dumps.
    if tirea is None or not (1.0 + tirea > 0.0):
        return {
            "duration_in": d, "duration_used": d_used, "clamped": (d != d_used),
            "x_min": x_min, "x_max": x_max,
            "tirea": None, "tem": None, "tna_plazo": None,
            "tnas": {"30": None, "90": None, "180": None, "365": None},
        }
    sane = tirea < 5.0                  # exp pequeño en `tem` no desborda; el de `d` sí
    tem = (1.0 + tirea) ** (30.0 / 360.0) - 1.0
    # TNA del plazo: rendimiento total sobre D años anualizado lineal (días/365).
    tna_plazo = (((1.0 + tirea) ** d_used - 1.0) / d_used) if (sane and d_used > 0) else None
    return {
        "duration_in": d, "duration_used": d_used, "clamped": (d != d_used),
        "x_min": x_min, "x_max": x_max,
        "tirea": tirea, "tem": tem, "tna_plazo": tna_plazo,
        "tnas": {"30": _tna(tirea, 30, 365), "90": _tna(tirea, 90, 365),
                 "180": _tna(tirea, 180, 365), "365": _tna(tirea, 365, 365)},
    }


def eval_clamped(duration: float, xs: List[float], ys: List[float],
                 threshold: float = 3.0) -> Optional[Dict[str, Any]]:
    """Valor de la curva NSS en `duration` (clamp al rango fiteado). Para métricas
    que NO son un yield (p.ej. margen sobre TAMAR/BADLAR), donde no aplican
    TEM/TNAs: devuelve sólo el valor interpolado (en las unidades de `ys`)."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    d = float(duration)
    d_used = float(np.clip(d, x_min, x_max))
    return {"duration_in": d, "duration_used": d_used, "clamped": (d != d_used),
            "x_min": x_min, "x_max": x_max, "value": float(model(d_used, *popt))}


def level_slope_convex(xs: List[float], ys: List[float], anchor: float,
                       threshold: float = 3.0) -> Optional[tuple]:
    """(level_pct, slope_bps, convex_bps) por Taylor 2º orden de la NSS alrededor
    de `anchor` (en años de duration). Sirve para autocompletar la 'curva
    imaginada' del Total Return (nivel/pendiente/convexidad). Réplica del legacy
    `OMSweb_app._nss_defaults_level_slope_convex`. None si no fitea."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt = f[0]
    a, h = float(anchor), 0.02
    g = lambda x: float(model(np.array([x], dtype=np.float64), *popt)[0])  # noqa: E731
    y0, yp, ym = g(a), g(a + h), g(a - h)
    slope_bps = (yp - ym) / (2.0 * h) * 100.0
    convex_bps = (yp - 2.0 * y0 + ym) / (h * h) * 100.0
    return float(y0), float(slope_bps), float(convex_bps)


def params(xs: List[float], ys: List[float], anchor: Optional[float] = None,
           threshold: float = 3.0) -> Optional[Dict[str, Any]]:
    """Parámetros NSS fiteados (β0..β3, τ1, τ2) + lecturas legibles + el
    nivel/pendiente/convexidad en `anchor`. None si no fitea. y de entrada en %."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    b0, b1, b2, b3, t1, t2 = (float(v) for v in popt)
    if anchor is None:
        anchor = round((x_min + x_max) / 2.0, 2)
    lsc = level_slope_convex(xs, ys, anchor, threshold)
    return {
        "b0": b0, "b1": b1, "b2": b2, "b3": b3, "t1": t1, "t2": t2,
        "x_min": x_min, "x_max": x_max, "n": len(xs),
        "y_corto": float(model(np.array([0.0]), *popt)[0]),   # TIREA @ duration→0
        "y_largo": b0,                                         # asintótica (β0)
        "anchor": float(anchor),
        "level_pct": lsc[0] if lsc else None,
        "slope_bps": lsc[1] if lsc else None,
        "convex_bps": lsc[2] if lsc else None,
    }
