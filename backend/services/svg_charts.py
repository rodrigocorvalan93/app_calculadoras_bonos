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
    """Ticks 'lindos' (1/2/2.5/5 × 10^k) dentro de [lo, hi].

    Un rango degenerado (lo == hi, no finito, o tan angosto que es ruido de
    punto flotante frente al nivel — p. ej. una serie plana cuyo canal ±σ
    queda a 1e-14 del precio) devuelve un solo tick: si el paso cae por
    debajo del ULP del valor, `v += step` no avanza y el loop no termina
    (pasó en CI con numpy 2.5). El loop además está acotado por si acaso —
    esto corre dentro de un request y nunca puede colgar un worker."""
    lo, hi = float(lo), float(hi)
    span = hi - lo
    if span <= 0 or not math.isfinite(span) or span <= max(abs(lo), abs(hi)) * 1e-9:
        return [lo]
    raw = span / max(1, n)
    step = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if step * mult >= raw:
            step *= mult
            break
    out: List[float] = []
    v = math.ceil(lo / step) * step
    tope = hi + step * 1e-6
    for _ in range(max(1, n) * 4 + 8):
        if v > tope:
            break
        out.append(round(v, 10))
        nv = v + step
        if nv <= v:                      # el paso no mueve el float: cortar
            break
        v = nv
    return out or [lo]


def donut(items: List[Dict[str, Any]], *, size: int = 170, r_in: float = 50.0,
          r_out: float = 80.0, gap_deg: float = 0.8) -> Optional[Dict[str, Any]]:
    """Geometría de una dona (torta con agujero) para SVG server-side.

    `items`: [{"label": str, "val": float, ...extras}] — la porción es
    proporcional a `val` (los ≤ 0 o no finitos no se dibujan); los extras
    (pct, monto…) se conservan en cada porción para la leyenda / tooltip.
    Devuelve {size, cx, cy, slices: [{i, d, frac, ...item}]} o None sin datos.
    Una sola porción = anillo completo (dos arcos, SVG no dibuja 360° de un
    tirón). El color lo da la clase `comp-c{i}` (CSS, 8 tonos cíclicos)."""
    vals = [(it, float(it.get("val") or 0.0)) for it in items]
    vals = [(it, v) for it, v in vals if v > 0 and math.isfinite(v)]
    total = sum(v for _, v in vals)
    if not vals or total <= 0:
        return None
    cx = cy = size / 2.0
    gap = math.radians(gap_deg) if len(vals) > 1 else 0.0

    def P(r: float, a: float) -> str:
        return f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}"

    def sector(a0: float, a1: float) -> str:
        big = 1 if (a1 - a0) > math.pi else 0
        return (f"M{P(r_out, a0)} A{r_out:.1f},{r_out:.1f} 0 {big} 1 {P(r_out, a1)} "
                f"L{P(r_in, a1)} A{r_in:.1f},{r_in:.1f} 0 {big} 0 {P(r_in, a0)} Z")

    slices: List[Dict[str, Any]] = []
    a = -math.pi / 2.0
    for i, (it, v) in enumerate(vals):
        frac = v / total
        a1 = a + 2.0 * math.pi * frac
        if len(vals) == 1:
            mid = a + math.pi
            d = sector(a, mid) + " " + sector(mid, a1)
        else:
            d = sector(a + gap / 2.0, a1 - gap / 2.0)
        slices.append({**it, "i": i, "d": d, "frac": round(frac, 6)})
        a = a1
    return {"size": size, "cx": cx, "cy": cy, "slices": slices, "n": len(slices)}


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
