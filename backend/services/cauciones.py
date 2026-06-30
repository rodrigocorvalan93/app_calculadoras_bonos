"""Cauciones BYMA — tasas (TNA) por plazo, leídas del store en memoria (mismo
WS que los bonos). Símbolos `MERV - XMEV - PESOS - {n}D` / `… - DOLAR - {n}D`.

La caución cotiza directo por TNA (no hay TIR que calcular). Complementa las
cauciones de MAE en la pestaña Tasas. Lee sólo de cache → sub-50 ms.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.services import marketdata_store

# Mismos plazos que el monitor legacy (OMScauciones.PLAZOS_DEFAULT).
PLAZOS: List[int] = [1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 35, 60, 90, 120]


def _moneda_tk(moneda: str) -> str:
    return "DOLAR" if str(moneda).upper().startswith("DOL") else "PESOS"


def symbols(moneda: str = "PESOS") -> List[str]:
    """Símbolos BYMA de caución para sembrar en el WS."""
    m = _moneda_tk(moneda)
    return [f"MERV - XMEV - {m} - {n}D" for n in PLAZOS]


def byma_rows(moneda: str = "PESOS") -> List[Dict[str, Any]]:
    """Filas de caución BYMA con datos en el store, ordenadas por plazo."""
    store = marketdata_store.get_store()
    m = _moneda_tk(moneda)
    rows: List[Dict[str, Any]] = []
    for n in PLAZOS:
        snap = store.get(f"MERV - XMEV - {m} - {n}D")
        if snap is None:
            continue
        last, bid, offer, close = snap.last, snap.bid, snap.offer, snap.close
        if last is None and bid is None and offer is None:
            continue
        var = None
        try:
            if last is not None and close not in (None, 0):
                var = last - close          # variación de TNA en puntos
        except (TypeError, ZeroDivisionError):
            var = None
        rows.append({
            "plazo": f"{n}D", "_n": n,
            "moneda": "ARS" if m == "PESOS" else "USD",
            "tasa": last, "bid": bid, "offer": offer, "close": close,
            "var": var, "volumen": snap.volume,
        })
    return rows


def best(moneda: str = "PESOS") -> Dict[str, Any] | None:
    """Caución de referencia: el plazo más corto con tasa (para un KPI)."""
    for r in byma_rows(moneda):
        if r["tasa"] is not None:
            return r
    return None


# Plazos overnight candidatos para el KPI del riel. La caución 1D es la de
# mayor volumen casi siempre; cuando hay feriado/finde por medio el overnight
# rueda al 2D/3D/4D, que es entonces el que concentra el volumen. Por eso
# elegimos por volumen entre estos plazos en vez de fijar 1D a mano.
_RAIL_PLAZOS = (1, 2, 3, 4)


def rail_pick(moneda: str = "PESOS") -> Dict[str, Any] | None:
    """Caución overnight de referencia para el riel: entre 1D y 4D, la de
    mayor volumen con tasa (1D salvo feriado/finde, donde rueda al 2-4D).
    Si ninguna de esas tiene volumen, cae a la más corta con tasa."""
    rows = [r for r in byma_rows(moneda) if r["tasa"] is not None]
    if not rows:
        return None
    short = [r for r in rows if r["_n"] in _RAIL_PLAZOS]
    with_vol = [r for r in short if r["volumen"] is not None]
    if with_vol:
        return max(with_vol, key=lambda r: r["volumen"] or 0.0)
    # Sin volumen reportado: la más corta entre las candidatas, o la más corta global.
    return (short or rows)[0]


def rail_picks() -> List[Dict[str, Any]]:
    """Cauciones overnight de referencia para el riel, en orden ARS → USD.
    Sólo incluye las monedas con dato en el store (lista vacía si no hay)."""
    out: List[Dict[str, Any]] = []
    for moneda in ("PESOS", "DOLAR"):
        pick = rail_pick(moneda)
        if pick is not None:
            out.append(pick)
    return out
