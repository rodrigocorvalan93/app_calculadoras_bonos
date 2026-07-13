"""Total return REALIZADO entre dos fechas de la base histórica.

En Argentina se opera DIRTY: comparar precios de dos fechas muerde una caída
discreta cada corte de cupón. El TR realizado correcto es el mismo de
`rentafija.calcula_total_return` pero con precios OBSERVADOS:

    TR = (P2 − P1 + cupones cobrados en (d1, d2]) / P1

donde los cupones (renta + amortización, columna Total del cashflow de la
ficha) se toman de la ficha real del bono, escalados ×100 — la misma
convención precio-de-mercado / precio-de-cálculo (px/100) de toda la app.

Eficiencia: los precios salen del índice en memoria del histórico (µs); el
cashflow requiere una copia de ficha por bono (~ms). Todo corre on-demand en
executor y se cachea por (curva, fechas) con TTL largo — el pasado no cambia.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from backend.cache import LockedTTLCache

logger = logging.getLogger("backend.tr_realizado")

_cache = LockedTTLCache(maxsize=64, ttl=900)


def _cupones_entre(code: str, d1: date, d2: date) -> Optional[float]:
    """Cobros (renta + amortización) por 100 VN en (d1, d2], de la ficha real.
    Mismo criterio de ventana que calcula_total_return. None si la ficha no
    puede generar cashflows a ese settle (bono raro) — el caller lo excluye."""
    from backend.services import pricing
    obj = pricing._bond_obj_copy(code)
    if obj is None or not hasattr(obj, "generate_cashflows"):
        return None
    try:
        obj.generate_cashflows(d1.strftime("%d/%m/%Y"))
        cf = obj.cashflow_cpn_full
        mask = (cf["Fechas"] > d1) & (cf["Fechas"] <= d2)
        return float(cf.loc[mask, "Total"].sum()) * 100.0   # convención px mercado = 100×px calc
    except Exception:  # noqa: BLE001
        logger.debug("[tr_realizado] cashflows de %s fallaron", code, exc_info=True)
        return None


def _compute(curve_key: str, d1_iso: str, d2_iso: str, proy: str) -> Dict[str, Any]:
    from backend.services import curves, historico_byma, symbols as syms

    c = historico_byma.ensure_loaded()
    out: Dict[str, Any] = {"loaded": c["loaded"], "rows": [], "d1": d1_iso, "d2": d2_iso,
                           "curve_label": curve_key, "summary": None}
    if not c["loaded"]:
        return out
    out["curve_label"] = next((cv.label for cv in curves.list_curves() if cv.key == curve_key),
                              curve_key)
    base_set = {syms.calc_to_md_code(x) for x in curves.build_curve_codes().get(curve_key, [])}
    rows: List[Dict[str, Any]] = []
    for code, e in c["by_code"].items():
        if e["base"] not in base_set:
            continue
        if proy == "base" and e["proy"] != 0:
            continue
        if proy == "proy" and e["proy"] != 1:
            continue
        p1, f1 = historico_byma._value_and_date_at(e, "Last Price", d1_iso)
        p2, f2 = historico_byma._value_and_date_at(e, "Last Price", d2_iso)
        y1, _ = historico_byma._value_and_date_at(e, "TIREA", d1_iso)
        y2, _ = historico_byma._value_and_date_at(e, "TIREA", d2_iso)
        if p1 is None or p2 is None or not p1 or f1 is None or f2 is None or f1 >= f2:
            continue
        # Cupones sobre la ventana REAL de precios de este bono (f1, f2]: si el
        # corte cayó entre la fecha pedida y la observada, no se pierde ni duplica.
        cup = _cupones_entre(code, date.fromisoformat(f1), date.fromisoformat(f2))
        if cup is None:
            continue
        px_var = p2 / p1 - 1.0
        cup_pct = cup / p1
        rows.append({
            "code": code, "f1": f1, "f2": f2, "p1": p1, "p2": p2,
            "px_var": px_var, "cupones": cup, "cup_pct": cup_pct,
            "tr": px_var + cup_pct,                     # (P2 − P1 + cupones) / P1
            "y1": y1, "y2": y2,
            "dy_bps": ((y2 - y1) * 10000.0) if (y1 is not None and y2 is not None) else None,
        })
    rows.sort(key=lambda r: r["tr"], reverse=True)
    out["rows"] = rows
    if rows:
        n = len(rows)
        out["summary"] = {
            "n": n,
            "px_var": sum(r["px_var"] for r in rows) / n,
            "cup_pct": sum(r["cup_pct"] for r in rows) / n,
            "tr": sum(r["tr"] for r in rows) / n,
        }
    return out


def tabla(curve_key: str, d1_iso: str, d2_iso: str, proy: str = "todos") -> Dict[str, Any]:
    """TR realizado por bono de la curva entre d1 y d2 (cacheado: el pasado no
    cambia; TTL 15 min por si la base se re-guarda hoy)."""
    key = (curve_key, d1_iso, d2_iso, proy)
    return _cache.get_or_compute(key, lambda: _compute(curve_key, d1_iso, d2_iso, proy))
