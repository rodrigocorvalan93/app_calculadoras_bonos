"""Cauciones BYMA — tasas (TNA) por plazo, leídas del store en memoria (mismo
WS que los bonos). Símbolos `MERV - XMEV - PESOS - {n}D` / `… - DOLAR - {n}D`.

La caución cotiza directo por TNA (no hay TIR que calcular). Complementa las
cauciones de MAE en la pestaña Tasas. Lee sólo de cache → sub-50 ms.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.locale_ar import hoy_ba
from backend.services import marketdata_store

# Mismos plazos que el monitor legacy (OMScauciones.PLAZOS_DEFAULT).
PLAZOS: List[int] = [1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 35, 60, 90, 120]


def _dia_ba(epoch: float):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(epoch, ZoneInfo("America/Argentina/Buenos_Aires")).date()


def _last_es_de_hoy(snap: Any) -> bool:
    """¿El last del snapshot es DE HOY (fecha BA)? El store es sticky y se
    persiste entre reinicios: un viernes la caución 1D no opera (liquidaría
    sábado) pero el last del jueves seguía contando como tasa viva y el riel
    la mostraba operando. Manda el last_ts del trade; sin last_ts (feeds que
    no mandan date), el updated_at del snapshot."""
    ts = getattr(snap, "last_ts", None)
    if ts:
        from backend.services.historico_writer import _fecha_dato  # lazy
        d = _fecha_dato(ts)
        if d is not None:
            return d >= hoy_ba()
    ua = getattr(snap, "updated_at", 0.0) or 0.0
    return bool(ua) and _dia_ba(ua) >= hoy_ba()


def _snap_tocado_hoy(snap: Any) -> bool:
    """¿Hubo ALGÚN tick de este snapshot hoy (fecha BA)? Para el book: unas
    puntas restauradas de la rueda anterior no son puntas de hoy."""
    ua = getattr(snap, "updated_at", 0.0) or 0.0
    return bool(ua) and _dia_ba(ua) >= hoy_ba()


def _moneda_tk(moneda: str) -> str:
    return "DOLAR" if str(moneda).upper().startswith("DOL") else "PESOS"


def symbols(moneda: str = "PESOS") -> List[str]:
    """Símbolos BYMA de caución para sembrar en el WS."""
    m = _moneda_tk(moneda)
    return [f"MERV - XMEV - {m} - {n}D" for n in PLAZOS]


def byma_rows(moneda: str = "PESOS", *, include_close_only: bool = False) -> List[Dict[str, Any]]:
    """Filas de caución BYMA con datos en el store, ordenadas por plazo.

    Por defecto sólo filas con cotización viva (last/bid/offer) — lo que
    muestra la pestaña Tasas. Con `include_close_only` entran también las que
    sólo tienen cierre previo (pre-apertura, mercado cerrado, reinicio del
    server): el feed manda el CL en el snapshot inicial aunque no haya
    operaciones, y el riel lo usa de fallback."""
    store = marketdata_store.get_store()
    m = _moneda_tk(moneda)
    rows: List[Dict[str, Any]] = []
    for n in PLAZOS:
        snap = store.get(f"MERV - XMEV - {m} - {n}D")
        if snap is None:
            continue
        last, bid, offer, close = snap.last, snap.bid, snap.offer, snap.close
        # Un last que NO es de hoy no es tasa viva — es el cierre de la última
        # rueda (viernes: la 1D no opera y el last sticky del jueves la mostraba
        # operando en el riel). Se degrada a cierre; un book sin ticks de hoy
        # (restaurado de la persistencia) tampoco cuenta como puntas vivas.
        if last is not None and not _last_es_de_hoy(snap):
            if close is None:
                close = last
            last = None
        if (bid is not None or offer is not None) and not _snap_tocado_hoy(snap):
            bid = offer = None
        if last is None and bid is None and offer is None:
            if not (include_close_only and close is not None):
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


def _pick_short(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Entre los plazos overnight (1D–4D), el de mayor volumen; sin volumen
    reportado, el más corto entre las candidatas, o el más corto global."""
    short = [r for r in rows if r["_n"] in _RAIL_PLAZOS]
    with_vol = [r for r in short if r["volumen"] is not None]
    if with_vol:
        return max(with_vol, key=lambda r: r["volumen"] or 0.0)
    return (short or rows)[0]


def rail_pick(moneda: str = "PESOS") -> Dict[str, Any] | None:
    """Caución overnight de referencia para el riel: entre 1D y 4D, la de
    mayor volumen con tasa (1D salvo feriado/finde, donde rueda al 2-4D).
    Si ninguna de esas tiene volumen, cae a la más corta con tasa.

    Sin operaciones todavía (pre-apertura, mercado cerrado, server recién
    reiniciado) cae al CIERRE PREVIO, marcado `es_cierre=True` — así el riel
    no pierde el KPI de la tasa del día fuera del horario de rueda."""
    all_rows = byma_rows(moneda, include_close_only=True)
    rows = [r for r in all_rows if r["tasa"] is not None]
    if rows:
        return _pick_short(rows)
    closed = [r for r in all_rows if r["close"] is not None]
    if not closed:
        return None
    pick = dict(_pick_short(closed))
    pick.update(tasa=pick["close"], var=None, es_cierre=True)
    return pick


def rail_picks() -> List[Dict[str, Any]]:
    """Cauciones overnight de referencia para el riel, en orden ARS → USD.
    Sólo incluye las monedas con dato en el store (lista vacía si no hay)."""
    out: List[Dict[str, Any]] = []
    for moneda in ("PESOS", "DOLAR"):
        pick = rail_pick(moneda)
        if pick is not None:
            out.append(pick)
    return out
