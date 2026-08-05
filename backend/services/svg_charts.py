"""Geometría compartida de los gráficos SVG server-side (sin JS).

Una sola fuente de layout para los gráficos de barras porcentuales — el
sendero de deva de Futuros y el break-even CER usan EXACTAMENTE esta función,
así las capturas de pantalla quedan con el mismo estilo (mismas proporciones,
mismos ticks, misma línea de promedio; el color/tipografía lo dan las clases
`fc-*` de style.css, también compartidas).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _nice_ticks(lo: float, hi: float, n: int = 5) -> List[float]:
    """Ticks 'lindos' (1/2/2.5/5 × 10^k) dentro de [lo, hi]."""
    span = hi - lo
    if span <= 0 or not math.isfinite(span):
        return [lo]
    raw = span / max(1, n)
    step = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if step * mult >= raw:
            step *= mult
            break
    out: List[float] = []
    v = math.ceil(lo / step) * step
    while v <= hi + step * 1e-6:
        out.append(round(v, 10))
        v += step
    return out


def barras_pct(segs: List[Dict[str, Any]], avg_val: Optional[float], *,
               width: int = 880, height: int = 250,
               ticks: int = 4, pad_l: int = 54,
               pad_b: int = 46) -> Optional[Dict[str, Any]]:
    """Layout de un gráfico de barras de porcentajes con línea de promedio.

    `segs`: [{"label": str, "val": float decimal, ...extras}] — los extras se
    conservan en cada barra (tooltips). Devuelve el dict de geometría que
    dibujan los templates (w/h, x0/x1, zero_y, xlabel_y, yticks, bars, avg).
    `pad_l`/`pad_b`: márgenes izquierdo/inferior — subirlos cuando los labels
    rotados del eje X son largos (BE usa "CÓDIGO · mes"): un label rotado a
    -32° baja ~0,53×ancho por debajo de xlabel_y y el viewBox lo recorta.
    """
    if not segs:
        return None
    vals = [s["val"] for s in segs]
    ymin, ymax = min(0.0, min(vals)), max(0.0, max(vals))
    span = (ymax - ymin) or 0.01
    ymax += span * 0.16                      # aire para el label sobre la barra
    if ymin < 0:
        ymin -= span * 0.10
    pad_r, pad_t = 14, 10
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    def Y(v: float) -> float:
        return round(pad_t + (ymax - v) / (ymax - ymin) * plot_h, 2)

    slot = plot_w / len(segs)
    bw = min(44.0, slot * 0.62)
    bars: List[Dict[str, Any]] = []
    for i, s in enumerate(segs):
        cx = round(pad_l + slot * (i + 0.5), 2)
        y_top, y_bot = Y(max(s["val"], 0.0)), Y(min(s["val"], 0.0))
        bars.append({**s, "cx": cx, "x": round(cx - bw / 2.0, 2),
                     "w": round(bw, 2), "y": y_top,
                     "h": round(max(y_bot - y_top, 0.75), 2),
                     "label_y": (y_top - 5) if s["val"] >= 0 else (y_bot + 12)})
    return {"w": width, "h": height, "x0": pad_l, "x1": width - pad_r, "y0": pad_t,
            "zero_y": Y(0.0), "xlabel_y": height - pad_b + 15, "bars": bars,
            "avg": ({"val": avg_val, "y": Y(avg_val)} if avg_val is not None else None),
            "yticks": [{"v": v, "y": Y(v)} for v in _nice_ticks(ymin, ymax, ticks)]}
