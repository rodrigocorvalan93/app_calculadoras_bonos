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

from backend.services import bond_universe, curves, fx as fx_svc, marketdata_store, pricing, symbols as syms

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


def _row_for_code(code: str, plazo: str, leg: str = "native", fx=None) -> dict | None:
    meta = pricing.bond_meta(code)
    if not meta:
        return None
    store = marketdata_store.get_store()
    symbol, leg_basis = _leg_symbol(code, plazo, leg, store)
    snap = store.get(symbol)
    last_pct = snap.last if snap else None
    bid_pct = snap.bid if snap else None
    offer_pct = snap.offer if snap else None
    last_ts = snap.last_ts if snap else None

    # Price the bond off this leg. USD / USB feed the native ficha directly
    # (fx-free → that venue's cable / MEP yield). ARS is the only leg that
    # needs the FX: pesos ÷ the bond's native rate (CCL for cable-native,
    # MEP for MEP-native) → the bond's own basis.
    price_for_calc = last_pct
    if last_pct is not None and leg_basis == "ARS":
        native = (meta.get("moneda") or "USD")
        price_for_calc = fx_svc.normalize_price(last_pct, "ARS", native, fx)

    metrics = pricing.metrics_for_market_price(code, price_for_calc)
    row = dict(meta)
    row.update(
        {
            "symbol": symbol,
            "leg": leg,
            "last": last_pct,
            "bid": bid_pct,
            "offer": offer_pct,
            "last_ts": last_ts,
            "tirea": (metrics or {}).get("tirea") if metrics else None,
            "tna": (metrics or {}).get("tna") if metrics else None,
            "tna_convention_label": (metrics or {}).get("tna_convention_label") if metrics else None,
            "duration": (metrics or {}).get("duration") if metrics else None,
            "paridad": (metrics or {}).get("paridad") if metrics else None,
            "margen_tna": (metrics or {}).get("margen_tna") if metrics else None,
        }
    )
    return row


def _has_quote(row: dict) -> bool:
    """True if the store gave us any tradeable price for this row."""
    return any(row.get(k) is not None for k in ("last", "bid", "offer"))


async def _rows_for(
    curve_key: str,
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
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
        *(loop.run_in_executor(_row_pool, _row_for_code, code, plazo, leg, fx) for code in codes)
    )
    rows = [r for r in raw if r is not None]
    quoting = sum(1 for r in rows if _has_quote(r))
    store_empty = quoting == 0

    # Filter only when the user asked AND there's at least one live
    # quote to filter against (avoid blanking the table in dev).
    do_filter = only_quoting and not store_empty
    visible = [r for r in rows if _has_quote(r)] if do_filter else rows
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
