"""Histórico de tasas forward entre pares de bonos — media, desvío y percentil.

Reconstruye la serie del forward par-a-par desde la base histórica diaria
(historico_byma: TIREA + Duration por bono y rueda, ya cacheada en memoria
desde el parquet) con LA MISMA fórmula que la matriz de Forwards en vivo:

    f = ((1+y1)^-t1 / (1+y2)^-t2) ^ (1/(t2-t1)) − 1

Advertencia metodológica (el "ojo" del pedido): el forward entre DOS BONOS
FIJOS no es estacionario — las durations se acortan rueda a rueda y el tramo
se corre por la curva, así que el percentil contra toda la historia compara
momentos distintos de la curva. Mitigación: ventana acotada (default 60
ruedas ≈ 3 meses), z-score además del percentil, y n visible con aviso si la
muestra es chica. La alternativa limpia (forwards de PLAZO CONSTANTE
interpolando la curva con NSS) es comparable en el tiempo pero no es
directamente tradeable — puede sumarse después.

Costo: O(ruedas del par) de aritmética sobre arrays ya en memoria (µs) +
memo por (versión de la base, par, ventana). Cero I/O en el request.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.cache import LockedTTLCache

_memo = LockedTTLCache(maxsize=512, ttl=300)

VENTANAS = (30, 60, 90, 0)          # ruedas; 0 = toda la historia
VENTANA_DEFAULT = 60
_N_MIN_AVISO = 20                   # con menos ruedas el percentil es humo
# Gap mínimo de duration (años ≈ 11 días): con t2−t1 → 0 la anualización del
# forward explota (miles de %) y UNA rueda así envenena media/desvío/percentil.
_MIN_GAP = 0.03


def fwd_rate(y1: float, t1: float, y2: float, t2: float) -> Optional[float]:
    """Forward implícito entre (y1,t1) y (y2,t2), t en años. None si no aplica."""
    if None in (y1, t1, y2, t2) or t2 <= t1 or t1 <= 0 or (1 + y1) <= 0 or (1 + y2) <= 0:
        return None
    try:
        d1 = (1.0 + y1) ** (-t1)
        d2 = (1.0 + y2) ** (-t2)
        f = (d1 / d2) ** (1.0 / (t2 - t1)) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return f if f == f else None


def serie(corto: str, largo: str) -> Dict[str, Any]:
    """Serie histórica del forward corto→largo: fechas ISO + tasas (decimal).
    Sólo ruedas donde AMBOS bonos tienen TIREA y Duration y dur_largo > dur_corto."""
    from backend.services import historico_byma as hb

    base = hb.ensure_loaded()
    a = (base.get("by_code") or {}).get(corto)
    b = (base.get("by_code") or {}).get(largo)
    if not a or not b:
        return {"dates": [], "fwds": []}

    def _map(entry) -> Dict[str, Any]:
        tir = (entry.get("vals") or {}).get("TIREA") or []
        dur = (entry.get("vals") or {}).get("Duration") or []
        out = {}
        for i, d in enumerate(entry.get("dates") or []):
            y = tir[i] if i < len(tir) else None
            t = dur[i] if i < len(dur) else None
            if y is not None and t is not None:
                out[d] = (y, t)
        return out

    ma, mb = _map(a), _map(b)
    dates, fwds = [], []
    for d in sorted(set(ma) & set(mb)):
        y1, t1 = ma[d]
        y2, t2 = mb[d]
        if t2 - t1 < _MIN_GAP:              # gap ínfimo → forward absurdo
            continue
        f = fwd_rate(y1, t1, y2, t2)
        if f is not None:
            dates.append(d)
            fwds.append(f)
    return {"dates": dates, "fwds": fwds}


def stats(corto: str, largo: str, ventana: int = VENTANA_DEFAULT,
          fwd_hoy: Optional[float] = None) -> Dict[str, Any]:
    """Media / desvío / min / max de la serie (ventana en ruedas; 0 = toda) y
    la posición del forward de HOY: percentil empírico y z-score."""
    from backend.services import historico_byma as hb

    ver = (hb.meta() or {}).get("last_update") or ""
    key = ("stats", ver, corto, largo, int(ventana))
    s = _memo.get_or_compute(key, lambda: _stats_base(corto, largo, int(ventana)))
    out = dict(s)
    out["fwd_hoy"] = fwd_hoy
    out["percentil"] = out["z"] = None
    fw = s.get("fwds") or []
    if fwd_hoy is not None and fw:
        menores = sum(1 for v in fw if v < fwd_hoy)
        iguales = sum(1 for v in fw if v == fwd_hoy)
        out["percentil"] = (menores + 0.5 * iguales) / len(fw)
        if s["desvio"]:
            out["z"] = (fwd_hoy - s["media"]) / s["desvio"]
    out["aviso_n"] = 0 < len(fw) < _N_MIN_AVISO
    return out


def _stats_base(corto: str, largo: str, ventana: int) -> Dict[str, Any]:
    import statistics

    s = serie(corto, largo)
    dates, fwds = s["dates"], s["fwds"]
    if ventana and ventana > 0:
        dates, fwds = dates[-ventana:], fwds[-ventana:]
    if not fwds:
        return {"n": 0, "dates": [], "fwds": [], "media": None, "desvio": None,
                "vmin": None, "vmax": None, "desde": None, "hasta": None}
    media = statistics.fmean(fwds)
    desvio = statistics.stdev(fwds) if len(fwds) > 1 else 0.0
    return {"n": len(fwds), "dates": dates, "fwds": fwds,
            "media": media, "desvio": desvio,
            "vmin": min(fwds), "vmax": max(fwds),
            "desde": dates[0], "hasta": dates[-1]}


def chart(st: Dict[str, Any], *, width: int = 880, height: int = 210) -> Optional[Dict[str, Any]]:
    """Geometría SVG de la serie: línea del forward + media punteada + banda
    ±1σ + punto del valor de HOY. Estilo fc-* (mismo look que el resto)."""
    fwds: List[float] = st.get("fwds") or []
    if len(fwds) < 2:
        return None
    from backend.services.svg_charts import _nice_ticks

    hoy = st.get("fwd_hoy")
    lo = min(fwds + ([hoy] if hoy is not None else []))
    hi = max(fwds + ([hoy] if hoy is not None else []))
    span = (hi - lo) or 0.01
    lo -= span * 0.08
    hi += span * 0.08
    pad_l, pad_r, pad_t, pad_b = 62, 16, 10, 26
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(fwds)

    def X(i: int) -> float:
        return round(pad_l + (i / (n - 1)) * pw, 2)

    def Y(v: float) -> float:
        return round(pad_t + (hi - v) / (hi - lo) * ph, 2)

    poly = " ".join(f"{X(i)},{Y(v)}" for i, v in enumerate(fwds))
    media, desvio = st.get("media"), st.get("desvio")
    dates = st.get("dates") or []
    # ~5 labels de fecha equiespaciados (DD/MM)
    xlabels = []
    for k in range(5):
        i = round(k * (n - 1) / 4)
        d = dates[i]
        xlabels.append({"x": X(i), "txt": f"{d[8:10]}/{d[5:7]}"})
    return {
        "w": width, "h": height, "x0": pad_l, "x1": width - pad_r,
        "y0": pad_t, "y1": height - pad_b, "poly": poly,
        "yticks": [{"v": v, "y": Y(v)} for v in _nice_ticks(lo, hi, 4)],
        "media_y": Y(media) if media is not None else None,
        "banda": ({"y": Y(media + desvio),
                   "h": round(abs(Y(media - desvio) - Y(media + desvio)), 2)}
                  if media is not None and desvio else None),
        "hoy": ({"cx": X(n - 1), "cy": Y(hoy)} if hoy is not None else None),
        "xlabels": xlabels, "xlabel_y": height - 8,
    }
