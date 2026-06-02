"""Nelson-Siegel-Svensson — ajuste de curva (Duration → yield) y estimación de
TIR / TEM / TNA a una duration dada.

Portado *lean* de `plotter.estimar_dur_tirtem_nss` (numpy + scipy, **sin
matplotlib** ni el resto del plotter legacy, que es pesado de importar). Sólo lo
usa la pestaña Gráficos. El ajuste se cachea por fingerprint de los puntos para
no re-fitear en cada refresh de 5 s.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[tuple, Optional[Tuple[np.ndarray, float, float]]] = {}
_CACHE_MAX = 64


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
    """Ajuste NSS cacheado por fingerprint de los puntos. (popt, x_min, x_max) o None."""
    key = (round(float(threshold), 2),
           tuple(round(float(x), 4) for x in xs),
           tuple(round(float(y), 4) for y in ys))
    with _lock:
        if key in _cache:
            return _cache[key]
    res = _fit_raw(xs, ys, threshold)
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = res
    return res


def _tna(tirea: float, freq: float, base: float) -> Optional[float]:
    """TNA bajo convención (freq días/período, base días/año) desde la TIREA."""
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
             threshold: float = 3.0, clip: bool = True) -> Optional[Dict[str, Any]]:
    """TIR / TEM / TNAs a una duration dada, vía NSS. y de entrada en %."""
    f = fit(xs, ys, threshold)
    if f is None:
        return None
    popt, x_min, x_max = f
    d = float(duration)
    d_used = float(np.clip(d, x_min, x_max)) if clip else d
    tirea = float(model(d_used, *popt)) / 100.0
    tem = (1.0 + tirea) ** (30.0 / 360.0) - 1.0
    # TNA del plazo: rendimiento total sobre D años anualizado lineal (días/365).
    tna_plazo = (((1.0 + tirea) ** d_used - 1.0) / d_used) if d_used > 0 else None
    return {
        "duration_in": d, "duration_used": d_used, "clamped": (d != d_used),
        "x_min": x_min, "x_max": x_max,
        "tirea": tirea, "tem": tem, "tna_plazo": tna_plazo,
        "tnas": {"30": _tna(tirea, 30, 365), "90": _tna(tirea, 90, 365),
                 "180": _tna(tirea, 180, 365), "365": _tna(tirea, 365, 365)},
    }
