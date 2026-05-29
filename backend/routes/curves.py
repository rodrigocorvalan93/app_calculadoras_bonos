"""Curves routes — Phase 2 step 1.

For now the table is static metadata (Vto / Moneda / Cupón / TIPO TASA /
Index / Ajuste) for every bond in the chosen curve. Live prices and
the TIREA column land in step 2, once the broker session is in place.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, curves, fx as fx_svc, marketdata_store, positions, pricing, symbols as syms

# Shared pool — the per-bond TIR compute is CPU-bound and the cache
# hits keep the work small, but the first poll after a price tick still
# benefits from fan-out across cores.
_row_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="curve-rows")

router = APIRouter(prefix="/curves", tags=["curves"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


# Leg → cable/MEP ticker suffix. ARS (pesos) is resolved separately because
# its ticker is base+"O" (corporates) or base (globales).
_LEG_SUFFIX = {"USD": "C", "USB": "D"}


def _leg_symbol(code: str, plazo: str, leg: str, store) -> tuple[str, str]:
    """(BYMA symbol, leg_basis) for the requested `leg` of a bond whose
    native ficha is `code` (`…C` cable / `…D` MEP).

    leg="native" (default) uses the code's own ticker — the FX-free path.
    "USD"/"USB" point at the cable/MEP ticker; "ARS" at the pesos ticker
    (base+"O" for corps, base for globales — whichever the store knows).
    """
    base = code[:-1] if code[-1:] in ("C", "D") else code
    if leg in _LEG_SUFFIX:
        return syms.md_symbol(base + _LEG_SUFFIX[leg], plazo), leg
    if leg == "ARS":
        sym_o = syms.md_symbol(base + "O", plazo)
        sym_b = syms.md_symbol(base, plazo)
        return (sym_o if store.get(sym_o) is not None else sym_b), "ARS"
    return syms.md_symbol(code, plazo), ""  # native


def _tirea_at(code: str, price_pct, settle=None):
    """TIREA at an arbitrary price (cached). None if no/invalid price."""
    if price_pct is None:
        return None
    m = pricing.metrics_for_market_price(code, price_pct, settle)
    return (m or {}).get("tirea") if m else None


def _px_cls(px, close) -> str:
    """Color de letra de un precio vs el cierre previo: verde si sube, rojo
    si baja, gris si el movimiento es < 2 bps (o no hay cierre)."""
    if px is None or close in (None, 0):
        return ""
    try:
        bps = (px / close - 1.0) * 10000.0
    except (TypeError, ZeroDivisionError):
        return ""
    if bps > 2:
        return "px-up"
    if bps < -2:
        return "px-down"
    return "px-flat"


def _dur_sort_key(r: dict):
    """Orden por duration ascendente; los sin duration (None/NaN) al final."""
    d = r.get("duration")
    bad = d is None or d != d
    return (bad, d if not bad else 0.0)


def _row_for_code(code: str, plazo: str, leg: str = "native", fx=None, book: bool = False) -> dict | None:
    meta = pricing.bond_meta(code)
    if not meta:
        return None
    store = marketdata_store.get_store()
    symbol, leg_basis = _leg_symbol(code, plazo, leg, store)
    snap = store.get(symbol)

    last = snap.last if snap else None
    bid = snap.bid if snap else None
    offer = snap.offer if snap else None
    close = snap.close if snap else None
    open_ = snap.open if snap else None
    high = snap.high if snap else None
    low = snap.low if snap else None
    volume = snap.volume if snap else None       # EV — $ efectivo operado
    nominal = snap.nominal if snap else None      # NV — nominales operados
    bid_size = snap.bid_size if snap else None
    offer_size = snap.offer_size if snap else None
    last_size = snap.last_size if snap else None
    last_ts = snap.last_ts if snap else None
    close_ts = snap.close_ts if snap else None

    # The ARS leg is the only one that needs the FX (pesos ÷ the bond's
    # native rate → its own basis). USD/USB/native price straight off the
    # ticker. `cp()` normalizes any price quoted on this leg before calc.
    native = (meta.get("moneda") or "USD")

    def cp(px):
        if px is None:
            return None
        if leg_basis == "ARS":
            return fx_svc.normalize_price(px, "ARS", native, fx)
        return px

    # Precio de referencia: last (LA) si operó hoy; si no, cierre previo (CL).
    if last is not None:
        ref_px, price_source, price_date = last, "LA", last_ts
    elif close is not None:
        ref_px, price_source, price_date = close, "CL", close_ts
    else:
        ref_px, price_source, price_date = None, None, None

    m = (pricing.metrics_for_market_price(code, cp(ref_px)) or {}) if ref_px is not None else {}

    # VWAP = efectivo / nominales * 100 (misma escala que el precio cotizado).
    vwap = None
    try:
        if volume and nominal:
            vwap = volume / nominal * 100.0
    except (TypeError, ZeroDivisionError):
        vwap = None

    # Variación vs cierre previo.
    var_pct = var_px = None
    try:
        if last is not None and close not in (None, 0):
            var_px = last - close
            var_pct = (last / close - 1.0) * 100.0
    except (TypeError, ZeroDivisionError):
        var_pct = var_px = None

    # Δ yield (bps) = TIREA(last) − TIREA(close).
    delta_yield_bps = None
    if last is not None and close is not None and last != close:
        ty_last = m.get("tirea") if price_source == "LA" else _tirea_at(code, cp(last))
        ty_close = _tirea_at(code, cp(close))
        if ty_last is not None and ty_close is not None and ty_last == ty_last and ty_close == ty_close:
            delta_yield_bps = (ty_last - ty_close) * 10000.0

    # Color por punta (vs cierre) + fondo de la celda de variación (heatmap
    # cuya intensidad escala con |var%|, tope ±2%).
    last_cls = _px_cls(last, close)
    bid_cls = _px_cls(bid, close)
    offer_cls = _px_cls(offer, close)
    var_bg = ""
    if var_pct is not None:
        alpha = min(abs(var_pct) / 2.0, 1.0) * 0.38
        rgb = "34,197,94" if var_pct >= 0 else "239,68,68"
        var_bg = f"background-color: rgba({rgb},{alpha:.2f})"

    row = dict(meta)
    row.update(
        {
            "code": code,                # ticker BYMA = nombre de variable
            "symbol": symbol,
            "leg": leg,
            "last": last, "bid": bid, "offer": offer,
            "close": close, "open": open_, "high": high, "low": low,
            "bid_size": bid_size, "offer_size": offer_size, "last_size": last_size,
            "volume": volume, "nominal": nominal, "vwap": vwap,
            "var_pct": var_pct, "var_px": var_px, "var_bg": var_bg,
            "last_cls": last_cls, "bid_cls": bid_cls, "offer_cls": offer_cls,
            "last_ts": last_ts, "close_ts": close_ts,
            "price_source": price_source, "price_date": price_date,
            "delta_yield_bps": delta_yield_bps,
            "tirea": m.get("tirea"),
            "tna": m.get("tna"),
            "tna_convention_label": m.get("tna_convention_label"),
            "tem": m.get("tem"),
            "duration": m.get("duration"),
            "paridad": m.get("paridad"),
            "margen_tna": m.get("margen_tna"),
        }
    )
    if book:
        row["tirea_bid"] = _tirea_at(code, cp(bid))
        row["tirea_offer"] = _tirea_at(code, cp(offer))
        row["tirea_last"] = m.get("tirea") if price_source == "LA" else _tirea_at(code, cp(last))
    return row


def _has_quote(row: dict) -> bool:
    """True if the store gave us any tradeable price for this row."""
    return any(row.get(k) is not None for k in ("last", "bid", "offer"))


async def _rows_for(
    curve_key: str,
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
    book: bool = False,
) -> tuple[list[dict], dict]:
    """One row per bond. Live columns come from the in-process store;
    TIREA / Duration are cached so a 5 s poll hits the cache nearly
    always. Parallelized across `_row_pool` so the cold path (cache
    miss on a wide curve) stays under the 50 ms p95 target.

    `only_quoting` replaces the legacy `has(code)` BONDS guard: when the
    store has live data, hide rows with no bid/last/offer (the same
    "only what actually trades" filter, sourced from the WS instead of
    a REST ticker set). If the store is completely empty (broker
    offline / dev), we DON'T filter — otherwise the table would be
    blank and useless. Returns (rows, meta) where meta carries counts
    for the UI badge.
    """
    codes = curves.build_curve_codes().get(curve_key, [])
    if not codes:
        return [], {"total": 0, "quoting": 0, "filtered": False, "store_empty": True}

    # Only the ARS leg needs the FX reference (pesos → native basis); the
    # native / USD / USB legs price straight off their own ticker.
    fx = fx_svc.get_fx(plazo) if leg == "ARS" else None
    loop = asyncio.get_running_loop()
    raw: list[dict | None] = await asyncio.gather(
        *(loop.run_in_executor(_row_pool, _row_for_code, code, plazo, leg, fx, book) for code in codes)
    )
    rows = [r for r in raw if r is not None]
    quoting = sum(1 for r in rows if _has_quote(r))
    store_empty = quoting == 0

    # Filter only when the user asked AND there's at least one live
    # quote to filter against (avoid blanking the table in dev).
    do_filter = only_quoting and not store_empty
    visible = [r for r in rows if _has_quote(r)] if do_filter else rows
    # Orden por defecto: por duration (los sin duration al final). La duration
    # ya se calcula sobre el precio de referencia (last si operó, si no cierre).
    visible.sort(key=_dur_sort_key)
    meta = {
        "total": len(rows),
        "quoting": quoting,
        "filtered": do_filter,
        "store_empty": store_empty,
    }
    return visible, meta


@router.get("", response_class=HTMLResponse)
async def curves_page(
    request: Request,
    curve: str | None = None,
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    default_key = next((c.key for c in all_curves if table.get(c.key)), None)
    selected_key = curve if (curve and curve in table) else default_key
    rows, row_meta = await _rows_for(selected_key, plazo, only_quoting, leg) if selected_key else ([], {})
    return _render(
        request,
        "curves.html",
        all_curves=all_curves,
        table=table,
        selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        rows=rows,
        row_meta=row_meta,
        plazo=plazo,
        only_quoting=only_quoting,
        leg=leg,
    )


@router.get("/table", response_class=HTMLResponse)
async def curve_table_partial(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    """HTMX partial: table body only for the requested curve."""
    rows, row_meta = await _rows_for(curve, plazo, only_quoting, leg)
    return _render(
        request,
        "partials/curve_table.html",
        selected_def=curves.curve_def(curve),
        rows=rows,
        row_meta=row_meta,
        plazo=plazo,
        only_quoting=only_quoting,
        leg=leg,
    )


# ── Mercado (monitor de book / blotter) ───────────────────────────────────
# Reusa la partición de curvas y el motor de filas, pero con columnas de
# mercado (book + sizes + VWAP + TIREA por punta + variación) y book=True
# para calcular las TIREA de bid/last/offer.
mercado_router = APIRouter(tags=["mercado"])


@mercado_router.get("/mercado", response_class=HTMLResponse)
async def mercado_page(
    request: Request,
    curve: str | None = None,
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    default_key = next((c.key for c in all_curves if table.get(c.key)), None)
    selected_key = curve if (curve and curve in table) else default_key
    rows, row_meta = (
        await _rows_for(selected_key, plazo, only_quoting, leg, book=True)
        if selected_key else ([], {})
    )
    return _render(
        request,
        "mercado.html",
        all_curves=all_curves,
        table=table,
        selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        rows=rows,
        row_meta=row_meta,
        plazo=plazo,
        only_quoting=only_quoting,
        leg=leg,
    )


@mercado_router.get("/mercado/table", response_class=HTMLResponse)
async def mercado_table_partial(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    """HTMX partial: blotter body for the requested curve."""
    rows, row_meta = await _rows_for(curve, plazo, only_quoting, leg, book=True)
    return _render(
        request,
        "partials/mercado_table.html",
        selected_def=curves.curve_def(curve),
        rows=rows,
        row_meta=row_meta,
        plazo=plazo,
        only_quoting=only_quoting,
        leg=leg,
    )


@mercado_router.get("/mercado/book/{code}", response_class=HTMLResponse)
async def mercado_book(
    request: Request,
    code: str,
    plazo: str = "24hs",
    leg: str = "native",
) -> HTMLResponse:
    """Libro (profundidad) de un instrumento — se carga al clickear su fila."""
    bond_universe.ensure_loaded()
    store = marketdata_store.get_store()
    symbol, leg_basis = _leg_symbol(code, plazo, leg, store)
    snap = store.get(symbol)
    meta = pricing.bond_meta(code) or {}
    native = meta.get("moneda") or "USD"
    fx = fx_svc.get_fx(plazo) if leg == "ARS" else None

    def cp(px):
        if px is None:
            return None
        return fx_svc.normalize_price(px, "ARS", native, fx) if leg_basis == "ARS" else px

    def with_yield(levels):
        out = []
        cum = 0.0
        for lvl in (levels or []):
            px, sz = lvl.get("price"), lvl.get("size")
            cum += (sz or 0.0)
            out.append({"price": px, "size": sz, "cum": cum, "tirea": _tirea_at(code, cp(px))})
        return out

    return _render(
        request,
        "partials/mercado_book.html",
        code=code,
        nombre=meta.get("nombre") or code,
        symbol=symbol,
        snap=snap,
        position=positions.position_for(code),                  # tenencia (desplegable)
        bids=with_yield(snap.bids if snap else None),
        offers=with_yield(snap.offers if snap else None),
    )


# ── Forwards implícitos (matriz triangular por curva) ─────────────────────
# Fila = bono corto (t1), columna = bono largo (t2). Celda = forward EA entre
# ambos usando Duration como eje temporal y TIREA como spot:
#   fwd = [(1+y2)^t2 / (1+y1)^t1]^(1/(t2−t1)) − 1   (igual que plotter).
forwards_router = APIRouter(tags=["forwards"])


def _forwards_matrix(rows: list[dict]) -> dict:
    pts = [
        (r["code"], r["tirea"], r["duration"])
        for r in rows
        if r.get("tirea") is not None and r["tirea"] == r["tirea"]
        and r.get("duration") is not None and r["duration"] == r["duration"] and r["duration"] > 0
    ]
    pts.sort(key=lambda p: p[2])  # por Duration ascendente
    n = len(pts)
    codes = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ts = [p[2] for p in pts]
    dfact = [(1.0 + ys[i]) ** (-ts[i]) for i in range(n)]

    raw: list[list[float | None]] = [[None] * n for _ in range(n)]
    finite: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            if ts[j] <= ts[i]:
                continue
            try:
                f = (dfact[i] / dfact[j]) ** (1.0 / (ts[j] - ts[i])) - 1.0
            except (ValueError, ZeroDivisionError, OverflowError):
                f = None
            if f is not None and f == f:
                raw[i][j] = f
                finite.append(f)
    vmin = min(finite) if finite else 0.0
    vmax = max(finite) if finite else 1.0

    out_rows = []
    for i in range(n):
        cells = []
        for j in range(n):
            f = raw[i][j]
            if f is None:
                cells.append({"fwd": None, "bg": ""})
            else:
                norm = (f - vmin) / (vmax - vmin) if vmax > vmin else 0.5
                norm = max(0.0, min(1.0, norm))
                alpha = 0.08 + norm * 0.42
                cells.append({"fwd": f, "bg": f"background-color: rgba(76,201,240,{alpha:.2f})"})
        out_rows.append({"code": codes[i], "t": ts[i], "tirea": ys[i], "cells": cells})
    return {"header": [{"code": codes[j], "t": ts[j]} for j in range(n)], "rows": out_rows, "n": n}


async def _forwards_for(curve_key: str, plazo: str, only_quoting: bool, leg: str) -> dict:
    rows, _meta = await _rows_for(curve_key, plazo, only_quoting, leg)
    return _forwards_matrix(rows)


@forwards_router.get("/forwards", response_class=HTMLResponse)
async def forwards_page(
    request: Request,
    curve: str | None = None,
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    default_key = next((c.key for c in all_curves if table.get(c.key)), None)
    selected_key = curve if (curve and curve in table) else default_key
    fwd = await _forwards_for(selected_key, plazo, only_quoting, leg) if selected_key else {"header": [], "rows": [], "n": 0}
    return _render(
        request, "forwards.html",
        all_curves=all_curves, table=table, selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        fwd=fwd, plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@forwards_router.get("/forwards/table", response_class=HTMLResponse)
async def forwards_table_partial(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    fwd = await _forwards_for(curve, plazo, only_quoting, leg)
    return _render(
        request, "partials/forwards_table.html",
        fwd=fwd, selected_def=curves.curve_def(curve),
        plazo=plazo, only_quoting=only_quoting, leg=leg,
    )
