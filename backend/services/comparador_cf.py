"""Comparador · gráfico de barras de cashflows A vs B (03/11).

Pedido del desk: ver los dos cronogramas uno contra otro. SVG server-side
(geometría acá, dibujo en `partials/comparador_cashflow.html`), mismo patrón
que `_bar_chart` / `futuros_charts`: sin JS, copiable con el ⧉.

Qué se compara: **la plata que entra por el mismo efectivo invertido**. A va
con el VN de la pantalla; B con el VN *cash neutral* del comparador (mismo
monto al precio de cada uno) cuando hay precio de los dos, si no con el mismo
VN. Si las monedas difieren, los flujos de B se pasan a la moneda de A con el
FX implícito de hoy (CCL / MEP, el mismo del cash neutral) y el pie lo dice.
Cada barra = un pago (fecha hábil de pago, `Total` × VN de la ficha: interés
+ amortización con ajuste, igual que el Cashflows del YAS / OMS.CASHFLOW),
sobre un eje de tiempo real desde la liquidación — así se ve CUÁNDO cobra
cada uno, no sólo cuánto. Los flujos salen del memo de `_flujos_de` (µs).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

W, H = 760, 250
X0, X1 = 70, W - 14
Y0, Y1 = 14, H - 44
BAR_W = 6.0            # ancho de cada barra (A y B pegadas, centradas en la fecha)
MAX_FLOWS = 400        # tope por bono: 100 años de cupón mensual, nunca pasa


def _as_date(d: Any) -> Optional[date]:
    if d is None:
        return None
    if hasattr(d, "date") and callable(d.date):
        try:
            return d.date()
        except Exception:  # noqa: BLE001
            return None
    return d if isinstance(d, date) else None


def _nice_step(span: float, n: int = 4) -> float:
    """Paso 'lindo' (1 · 2 · 2,5 · 5 × 10^k) para ~n ticks."""
    if span <= 0:
        return 1.0
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _xticks(d0: date, d1: date) -> List[Dict[str, Any]]:
    """Ticks del eje de tiempo: cada año si el tramo pasa los 2 años, si no
    cada 6 meses; etiqueta AAAA o MM/AA."""
    span_d = max(1, (d1 - d0).days)
    out: List[Dict[str, Any]] = []
    if span_d > 730:
        y = d0.year + 1
        while date(y, 1, 1) <= d1:
            out.append({"d": date(y, 1, 1), "label": str(y)})
            y += 1
    else:
        y, m = d0.year, d0.month
        # primer semestre entero después de d0
        m = 7 if m < 7 else 1
        y = y if m == 7 else y + 1
        while date(y, m, 1) <= d1:
            out.append({"d": date(y, m, 1), "label": f"{m:02d}/{y % 100:02d}"})
            m += 6
            if m > 12:
                m, y = 1, y + 1
    return out


def chart_from_rows(rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]],
                    vn_a: float, vn_b: float, settle: Any,
                    conv_b: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Geometría del gráfico a partir de las filas de `pricing.cashflow_table`
    (`fecha_pmt`, `intereses`, `amortizacion`, `total`) de cada bono.
    `conv_b` = factor que pasa los montos de B a la moneda de A (None = sin
    conversión). Pura: sin pricing ni mercado. None si no hay ningún flujo."""
    d0 = _as_date(settle)
    pts: List[Dict[str, Any]] = []
    for lado, rows, vn in (("a", rows_a, vn_a), ("b", rows_b, vn_b)):
        for r in list(rows)[:MAX_FLOWS]:
            d = _as_date(r.get("fecha_pmt")) or _as_date(r.get("fecha_cpn"))
            tot = r.get("total")
            if d is None or tot is None or not math.isfinite(float(tot)):
                continue
            monto = float(tot) * float(vn)
            if lado == "b" and conv_b is not None:
                monto *= conv_b
            pts.append({"lado": lado, "d": d, "monto": monto,
                        "int": float(r.get("intereses") or 0.0),
                        "amort": float(r.get("amortizacion") or 0.0),
                        "total": float(tot)})
    if not pts:
        return None
    if d0 is None:
        d0 = min(p["d"] for p in pts)
    d1 = max(p["d"] for p in pts)
    d0 = min(d0, min(p["d"] for p in pts))
    span = max(30, (d1 - d0).days)
    pad = max(10, int(span * 0.03))
    d1p = d1 + timedelta(days=pad)
    span_p = max(1, (d1p - d0).days)

    ymax = max(p["monto"] for p in pts)
    if ymax <= 0:
        return None
    step = _nice_step(ymax)
    top = step * math.ceil(ymax / step + 0.05)

    def X(d: date) -> float:
        return X0 + (d - d0).days / span_p * (X1 - X0)

    def Y(v: float) -> float:
        return Y1 - (v / top) * (Y1 - Y0)

    bars: Dict[str, List[Dict[str, Any]]] = {"a": [], "b": []}
    tot: Dict[str, float] = {"a": 0.0, "b": 0.0}
    for p in pts:
        cx = X(p["d"])
        x = cx - BAR_W if p["lado"] == "a" else cx
        y = Y(p["monto"])
        bars[p["lado"]].append({"x": round(x, 2), "y": round(y, 2), "w": BAR_W,
                                "h": round(max(0.0, Y1 - y), 2), "fecha": p["d"],
                                "monto": p["monto"], "int": p["int"], "amort": p["amort"],
                                "total": p["total"]})
        tot[p["lado"]] += p["monto"]

    yticks = []
    v = 0.0
    while v <= top + 1e-9:
        yticks.append({"y": round(Y(v), 2), "v": v})
        v += step
    xticks = [{"x": round(X(t["d"]), 2), "label": t["label"]} for t in _xticks(d0, d1p)]
    return {"w": W, "h": H, "x0": X0, "x1": X1, "y0": Y0, "y1": Y1,
            "xlabel_y": Y1 + 16, "legend_y": H - 8,
            "yticks": yticks, "xticks": xticks,
            "bars_a": bars["a"], "bars_b": bars["b"],
            "tot_a": tot["a"], "tot_b": tot["b"],
            "n_a": len(bars["a"]), "n_b": len(bars["b"]),
            "desde": d0, "hasta": d1, "vn_a": float(vn_a), "vn_b": float(vn_b)}


def chart_for(a: str, b: str, settle: Optional[str], vn: float,
              swap: Optional[Dict[str, Any]], plazo: str,
              moneda_a: Optional[str], moneda_b: Optional[str]) -> Optional[Dict[str, Any]]:
    """Gráfico para el comparador: flujos pendientes de A y B a la misma
    liquidación. VN de B = cash neutral si hay `swap`, si no el de A; B a la
    moneda de A con el FX implícito del plazo si difieren (sin FX → sin
    convertir, y el pie lo aclara). None si a alguno le faltan flujos."""
    from backend.services import fx as fx_svc, pricing

    if not a or not b:
        return None
    ta = pricing.cashflow_table(a, settle=settle)
    tb = pricing.cashflow_table(b, settle=settle)
    if ta.get("error") or tb.get("error") or not ta["rows"] or not tb["rows"]:
        return None
    vn_a = float(vn)
    vn_b = float(swap["vn_b"]) if swap and swap.get("vn_b") else vn_a
    conv_b: Optional[float] = None
    nota: List[str] = []
    nota.append("B con VN cash neutral (el mismo efectivo que A, a los precios de la comparación)"
                if swap and swap.get("vn_b")
                else "mismo VN para los dos (sin precio de ambos no hay cash neutral)")
    mon_a, mon_b = (moneda_a or ""), (moneda_b or "")
    if mon_a != mon_b:
        try:
            uno = fx_svc.normalize_price(1.0, mon_b, mon_a, fx_svc.get_fx(plazo))
        except Exception:  # noqa: BLE001
            uno = None
        if uno is not None and math.isfinite(float(uno)) and float(uno) > 0:
            conv_b = float(uno)
            nota.append(f"flujos de B pasados a {mon_a or 'la moneda de A'} con el FX implícito de hoy")
        else:
            nota.append(f"monedas distintas ({mon_a or '?'} vs {mon_b or '?'}) sin FX para convertir: cada uno en la suya")
    ch = chart_from_rows(ta["rows"], tb["rows"], vn_a, vn_b, ta.get("settle"), conv_b)
    if ch is None:
        return None
    ch["moneda"] = mon_a or mon_b or ""
    ch["nota"] = " · ".join(nota)
    ch["a"], ch["b"] = a, b
    return ch
