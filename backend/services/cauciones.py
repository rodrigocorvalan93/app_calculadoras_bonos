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


def vwap_evnv(snap: Any, dias: int) -> float | None:
    """Tasa promedio ponderada del día SI viene codificada en los acumuladores
    EV/NV del feed — dato del server en cada snapshot, NO una grabación local
    (mismo espíritu que el VWAP de bonos = EV/NV×100 que ya usa Mercado). Si
    para caución un acumulador es el contado y el otro el monto a vencimiento,
    entonces (mayor/menor − 1) · 365/n es el VWAP de tasa.

    AUTOVALIDADO contra el propio rango del día que publica la API: sólo se
    devuelve si cae entre el mínimo y el máximo operados (±0,5 pp). Si el
    broker manda EV = NV (una sola plata), da 0% fuera de rango → None: jamás
    un número inventado. No hay endpoint alternativo: `rest/data/getTrades`
    responde `{trades: []}` para caución (ver
    proyecto_cauciones_ml/diagnostico_endpoints.py)."""
    try:
        ev, nv = getattr(snap, "volume", None), getattr(snap, "nominal", None)
        lo, hi = getattr(snap, "low", None), getattr(snap, "high", None)
        if not ev or not nv or ev <= 0 or nv <= 0 or dias <= 0:
            return None
        if lo is None or hi is None:
            return None                      # sin rango del día no hay validación
        r = float(ev) / float(nv)
        if r < 1.0:                          # orientación desconocida: probar ambas
            r = 1.0 / r
        tasa = (r - 1.0) * 365.0 / float(dias) * 100.0
        if not (float(lo) - 0.5 <= tasa <= float(hi) + 0.5):
            return None
        return tasa
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def book(moneda: str = "PESOS", dias: int = 1) -> Dict[str, Any] | None:
    """Detalle completo de UNA caución para el card del libro en Tasas:
    stats del día + profundidad con acumulado (tasa por nivel, monto en $)
    + VWAP del día si el feed lo codifica (vwap_evnv). Todo del store en
    memoria (sub-ms). Las puntas y stats restauradas de otra rueda no cuentan
    (mismos guards que byma_rows); None si el store no conoce el símbolo."""
    from datetime import timedelta

    m = _moneda_tk(moneda)
    n = int(dias)
    snap = marketdata_store.get_store().get(f"MERV - XMEV - {m} - {n}D")
    if snap is None:
        return None
    hoy = _snap_tocado_hoy(snap)
    last_hoy = snap.last is not None and _last_es_de_hoy(snap)

    def levels(raw):
        out: List[Dict[str, Any]] = []
        cum = 0.0
        for lvl in (raw if hoy else None) or []:
            tasa, monto = lvl.get("price"), lvl.get("size")
            cum += (monto or 0.0)
            out.append({"tasa": tasa, "monto": monto, "cum": cum})
        for lvl in out:                    # fracción → degradé de profundidad
            lvl["frac"] = lvl["cum"] / cum if cum > 0 else 0.0
        return out

    last = snap.last if last_hoy else None
    close = snap.close if snap.close is not None else (None if last_hoy else snap.last)
    var = (last - close) if (last is not None and close is not None) else None
    return {
        "plazo": f"{n}D", "dias": n,
        "moneda": "ARS" if m == "PESOS" else "USD",
        "tasa": last, "close": close, "var": var,
        "open": snap.open if hoy else None,
        "high": snap.high if hoy else None,
        "low": snap.low if hoy else None,
        "monto": snap.volume if hoy else None,      # EV — $ operado en el día
        "ops": snap.trade_count if hoy else None,
        "vwap": vwap_evnv(snap, n) if hoy else None,
        "vencimiento": (hoy_ba() + timedelta(days=n)).isoformat(),
        "bids": levels(snap.bids), "offers": levels(snap.offers),
        "es_hoy": hoy,
    }


def hist_row(moneda: str = "PESOS") -> Dict[str, Any] | None:
    """Dato de caución overnight para el HISTÓRICO diario: el plazo o/n real
    del día (rail_pick: mayor volumen entre 1D-4D → un viernes cae solo al 3D
    y pre-feriado al 4D, así la serie no tiene huecos), con la tasa operada
    HOY (jamás el cierre de otra rueda) y el VWAP del día si el feed lo
    codifica en EV/NV (ver vwap_evnv — todo dato de API, nada grabado)."""
    pick = rail_pick(moneda)
    if not pick or pick.get("es_cierre") or pick.get("tasa") is None:
        return None
    snap = marketdata_store.get_store().get(
        f"MERV - XMEV - {_moneda_tk(moneda)} - {pick['_n']}D")
    return {"plazo_d": pick["_n"], "tna": pick["tasa"],
            "vwap": vwap_evnv(snap, pick["_n"]) if snap is not None else None,
            "monto": pick.get("volumen")}
