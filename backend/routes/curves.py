"""Curves routes — Phase 2 step 1.

For now the table is static metadata (Vto / Moneda / Cupón / TIPO TASA /
Index / Ajuste) for every bond in the chosen curve. Live prices and
the TIREA column land in step 2, once the broker session is in place.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backend.locale_ar import fmt_pct
from backend.services import bond_universe, curves, fx as fx_svc, instruments, mae as mae_svc, marketdata_store, positions, pricing, symbols as syms

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


def _row_for_code(code: str, plazo: str, leg: str = "native", fx=None, book: bool = False,
                  fuente: str = "byma") -> dict | None:
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
    # Estreno: emitido hace ≤5 días (o liquida en estos días). Exime del filtro
    # "solo con cotización" — un bono nuevo no operó todavía y desaparecía de
    # Curvas/Mercado hasta su primer trade. Costo: una resta de fechas.
    emis = meta.get("emision")
    estreno = False
    try:
        estreno = emis is not None and (date.today() - emis).days <= 5
    except TypeError:
        pass
    # Posición del Last dentro del rango del día (0=Low, 1=High) para la
    # barrita de rango — usa datos que ya están en la fila, costo ~ns.
    range_pos = None
    try:
        if last is not None and low is not None and high is not None and high > low:
            range_pos = max(0.0, min(1.0, (last - low) / (high - low)))
    except TypeError:
        pass
    row.update(
        {
            "estreno": estreno,
            "range_pos": range_pos,
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
            "px_calc": cp(ref_px) if ref_px is not None else None,
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
        # tirea_low/high/close son sólo para el panel del libro (un bono), NO
        # para cada fila de la tabla — se calculan en la route /mercado/book.
        # Cross-venue MAE (OTC): último/volumen del mismo bono en MAE (cache).
        mae_q = mae_svc.match(code, leg)
        row["mae"] = mae_q
        # Volumen total nominal = BYMA (NV) + MAE (volumenAcumulado VN).
        vols = [v for v in (nominal, (mae_q or {}).get("volumen")) if v is not None]
        row["vol_total"] = sum(vols) if vols else None

    # Switch de fuente: en modo MAE los precios pasan a los de MAE (último/
    # cierre/var/mín/máx/volumen) con TIR recalculada; sin libro (MAE no informa
    # puntas). Si el bono no tiene dato MAE, cae a BYMA (marca "BYMA*").
    if fuente == "mae":
        mq = row.get("mae") if book else mae_svc.match(code, leg)
        if mq and mq.get("last") is not None:
            mlast, mclose = mq["last"], mq.get("close")
            try:
                mvar = (mlast / mclose - 1.0) * 100.0 if mclose else mq.get("var_pct")
            except (TypeError, ZeroDivisionError):
                mvar = mq.get("var_pct")
            row.update({
                "last": mlast, "close": mclose, "var_pct": mvar, "var_px": None, "var_bg": "",
                "low": mq.get("min"), "high": mq.get("max"),
                "bid": None, "offer": None, "bid_size": None, "offer_size": None,
                "nominal": mq.get("volumen"), "volume": mq.get("monto"), "vwap": None,
                "price_source": "MAE", "src": "MAE", "last_cls": _px_cls(mlast, mclose),
            })
            if book:
                row["tirea_last"] = _tirea_at(code, cp(mlast))
                row["tirea_bid"] = row["tirea_offer"] = None
        else:
            row["src"] = "BYMA*"        # sin dato MAE → se muestra BYMA
    else:
        row["src"] = "BYMA"
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
    fuente: str = "byma",
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

    # Construimos las filas en chunks (round-robin) en vez de 1 tarea por bono:
    # para curvas anchas (corp_hdmep ~131) eso evitaba ~130 dispatches al pool en
    # cada request (warm p95 ~120 ms). Con N_WORKERS chunks secuenciales se
    # mantiene el paralelismo del path frío con una fracción del overhead.
    n_workers = max(1, getattr(_row_pool, "_max_workers", 8))

    def _build_chunk(chunk: list[str]) -> list[dict | None]:
        return [_row_for_code(c, plazo, leg, fx, book, fuente) for c in chunk]

    chunks = [codes[i::n_workers] for i in range(n_workers)]
    parts: list[list[dict | None]] = await asyncio.gather(
        *(loop.run_in_executor(_row_pool, _build_chunk, ch) for ch in chunks if ch)
    )
    rows = [r for part in parts for r in part if r is not None]
    # Fracción de volumen vs el máximo de la tabla → barrita de fondo en la
    # celda (degradé). O(n) sobre filas ya construidas, costo ~µs.
    vmax = max((r.get("volume") or 0.0) for r in rows) if rows else 0.0
    nmax = max((r.get("nominal") or 0.0) for r in rows) if rows else 0.0
    for r in rows:
        r["volume_frac"] = (r.get("volume") or 0.0) / vmax if vmax > 0 else 0.0
        r["nominal_frac"] = (r.get("nominal") or 0.0) / nmax if nmax > 0 else 0.0
    quoting = sum(1 for r in rows if _has_quote(r))
    store_empty = quoting == 0

    # Filter only when the user asked AND there's at least one live
    # quote to filter against (avoid blanking the table in dev).
    do_filter = only_quoting and not store_empty
    visible = [r for r in rows if _has_quote(r) or r.get("estreno")] if do_filter else rows
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
    fuente: str = "byma",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    default_key = next((c.key for c in all_curves if table.get(c.key)), None)
    selected_key = curve if (curve and curve in table) else default_key
    rows, row_meta = (
        await _rows_for(selected_key, plazo, only_quoting, leg, book=True, fuente=fuente)
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
        fuente=fuente,
    )


@mercado_router.get("/mercado/table", response_class=HTMLResponse)
async def mercado_table_partial(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
    fuente: str = "byma",
    panel: str = "rf",
) -> HTMLResponse:
    """HTMX partial: blotter body for the requested curve."""
    # Panel Acciones / CEDEARs: precio puro desde el store (sin TIR ni
    # calculadora) — cada fila es un lookup en memoria, sin pasar por pricing.
    if panel in ("lideres", "cedears"):
        from backend.services import equities
        eq_rows = equities.panel_rows(panel, plazo)
        return _render(request, "partials/equities_table.html",
                       rows=eq_rows, panel=panel, plazo=plazo)
    rows, row_meta = await _rows_for(curve, plazo, only_quoting, leg, book=True, fuente=fuente)
    return _render(
        request,
        "partials/mercado_table.html",
        selected_def=curves.curve_def(curve),
        rows=rows,
        row_meta=row_meta,
        plazo=plazo,
        only_quoting=only_quoting,
        leg=leg,
        fuente=fuente,
    )


@mercado_router.get("/mercado/book/{code}", response_class=HTMLResponse)
async def mercado_book(
    request: Request,
    code: str,
    plazo: str = "24hs",
    leg: str = "native",
    fuente: str = "byma",
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

    row = _row_for_code(code, plazo, leg, fx, book=True, fuente=fuente)   # fila (BYMA o MAE)
    if row:  # TIR de mín/máx/cierre — sólo para este bono; sobre la fuente activa
        row["tirea_low"] = _tirea_at(code, cp(row.get("low")))
        row["tirea_high"] = _tirea_at(code, cp(row.get("high")))
        row["tirea_close"] = _tirea_at(code, cp(row.get("close")))
    return _render(
        request,
        "partials/mercado_book.html",
        code=code,
        nombre=meta.get("nombre") or code,
        symbol=symbol,
        snap=snap,
        row=row,
        position=positions.position_for(code),                  # tenencia (desplegable)
        instr=await instruments.detail(symbol),                 # lámina mínima / tick / límites
        bids=with_yield(snap.bids if snap else None),
        offers=with_yield(snap.offers if snap else None),
        fuente=fuente,
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

    span = (vmax - vmin) or 1.0
    out_rows = []
    for i in range(n):
        cells = []
        for j in range(n):
            f = raw[i][j]
            if f is None:
                cells.append({"txt": "·", "bg": ""})
            else:
                norm = min(1.0, max(0.0, (f - vmin) / span))
                alpha = 0.08 + norm * 0.42
                # Texto pre-formateado en Python (evita N² dispatch del filtro
                # Jinja `ar_pct` al renderizar la matriz — clave en curvas anchas).
                cells.append({"txt": fmt_pct(f, 2),
                              "bg": f"background-color: rgba(76,201,240,{alpha:.2f})"})
        out_rows.append({"code": codes[i], "t": ts[i], "tirea": ys[i], "cells": cells})
    return {"header": [{"code": codes[j], "t": ts[j]} for j in range(n)], "rows": out_rows, "n": n}


def _is_fwd_point(r: dict) -> bool:
    """El bono entra a la matriz si tiene TIREA y Duration finita y > 0."""
    t, d = r.get("tirea"), r.get("duration")
    return t is not None and t == t and d is not None and d == d and d > 0


# Tope de bonos en la matriz: una matriz triangular es O(N²) en cómputo Y en
# render (una corp curve tiene >130 bonos → 16k celdas, ilegible y lenta). Se
# muestran los MAX_FWD de mayor volumen; los checkboxes siguen permitiendo
# elegir cuáles. Mantiene el target sub-50 ms y la legibilidad.
MAX_FWD = 50


def _fwd_points(rows: list[dict]) -> tuple[list[dict], bool, int]:
    """Bonos válidos para la matriz, capados a los MAX_FWD de mayor volumen.
    Devuelve (rows_capados, truncado, total_válidos)."""
    pts = [r for r in rows if _is_fwd_point(r)]
    total = len(pts)
    if total > MAX_FWD:
        pts = sorted(pts, key=lambda r: -(r.get("volume") or 0.0))[:MAX_FWD]
    return pts, total > MAX_FWD, total


# Helpers PUROS sobre `rows` ya construidas — así la página y el body arman
# filtro + matriz + what-if con UNA sola pasada de `_rows_for` (no tres).
def _candidates_from_rows(rows: list[dict]) -> list[str]:
    pts = [(r["code"], r["duration"]) for r in rows if _is_fwd_point(r)]
    pts.sort(key=lambda p: p[1])
    return [c for c, _ in pts]


def _matrix_from_rows(rows: list[dict], include: set[str] | None = None) -> dict:
    if include is not None:
        rows = [r for r in rows if r["code"] in include]
    capped, trunc, total = _fwd_points(rows)
    m = _forwards_matrix(capped)
    m["truncated"], m["total"] = trunc, total
    return m


def _whatif_from_rows(rows: list[dict], include: set[str] | None,
                      overrides: dict[str, float]):
    """(filas editables, matriz). Un bono SIN editar reusa la TIR/Duration ya
    calculada en su fila (cero pricing extra); sólo los editados recalculan."""
    if include is not None:
        rows = [r for r in rows if r["code"] in include]
    capped, trunc, total = _fwd_points(rows)   # mismo tope/criterio que la matriz
    out = []
    for r in capped:
        code = r["code"]
        mkt = r.get("px_calc")            # precio nativo de mercado (el que valuó la fila)
        ov = overrides.get(code)
        if ov is not None:
            m = pricing.metrics_for_market_price(code, ov) or {}
            tirea, duration, price = m.get("tirea"), m.get("duration"), ov
        else:                              # reusa lo ya calculado en la fila
            tirea, duration, price = r.get("tirea"), r.get("duration"), mkt
        out.append({"code": code, "market": mkt, "price": price,
                    "tirea": tirea, "duration": duration, "edited": ov is not None})
    matrix = _forwards_matrix(out)
    matrix["truncated"], matrix["total"] = trunc, total
    return out, matrix


async def _forwards_for(curve_key: str, plazo: str, only_quoting: bool, leg: str,
                        include: set[str] | None = None) -> dict:
    rows, _meta = await _rows_for(curve_key, plazo, only_quoting, leg)
    return _matrix_from_rows(rows, include)


def _price_overrides(request: Request) -> dict[str, float]:
    """Lee los `price_<CODE>` del query (what-if): precio nativo % VN > 0."""
    out: dict[str, float] = {}
    for k, v in request.query_params.multi_items():
        if not k.startswith("price_"):
            continue
        try:
            f = float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if f == f and f > 0:
            out[k[len("price_"):]] = f
    return out


async def _whatif_rows(curve_key: str, plazo: str, only_quoting: bool, leg: str,
                       include: set[str] | None, overrides: dict[str, float]):
    rows, _meta = await _rows_for(curve_key, plazo, only_quoting, leg)
    return _whatif_from_rows(rows, include, overrides)


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
    if selected_key:
        rows, _meta = await _rows_for(selected_key, plazo, only_quoting, leg)   # 1 sola pasada
        candidates = _candidates_from_rows(rows)
        fwd = _matrix_from_rows(rows)
        wi_rows, wi_fwd = _whatif_from_rows(rows, None, {})
    else:
        candidates, fwd, wi_rows, wi_fwd = [], {"header": [], "rows": [], "n": 0}, [], {"header": [], "rows": [], "n": 0}
    return _render(
        request, "forwards.html",
        all_curves=all_curves, table=table, selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        candidates=candidates, selected_codes=set(candidates),
        fwd=fwd, wi_rows=wi_rows, wi_fwd=wi_fwd,
        curve=selected_key, plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@forwards_router.get("/forwards/body", response_class=HTMLResponse)
async def forwards_body(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    """Curva/plazo/leg cambió → reconstruye filtro + matriz + what-if (estado
    fresco: todos los bonos tildados, precios a mercado)."""
    rows, _meta = await _rows_for(curve, plazo, only_quoting, leg)   # 1 sola pasada
    candidates = _candidates_from_rows(rows)
    fwd = _matrix_from_rows(rows)
    wi_rows, wi_fwd = _whatif_from_rows(rows, None, {})
    return _render(
        request, "partials/forwards_body.html",
        selected_def=curves.curve_def(curve),
        candidates=candidates, selected_codes=set(candidates),
        fwd=fwd, wi_rows=wi_rows, wi_fwd=wi_fwd,
        curve=curve, plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@forwards_router.get("/forwards/table", response_class=HTMLResponse)
async def forwards_table_partial(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
    code: list[str] = Query(default=None),
    filtered: int = 0,
) -> HTMLResponse:
    include = set(code or []) if filtered else None
    fwd = await _forwards_for(curve, plazo, only_quoting, leg, include=include)
    return _render(
        request, "partials/forwards_table.html",
        fwd=fwd, selected_def=curves.curve_def(curve),
        plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@forwards_router.get("/forwards/whatif", response_class=HTMLResponse)
async def forwards_whatif(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
    code: list[str] = Query(default=None),
    filtered: int = 0,
) -> HTMLResponse:
    include = set(code or []) if filtered else None
    overrides = _price_overrides(request)
    wi_rows, wi_fwd = await _whatif_rows(curve, plazo, only_quoting, leg, include, overrides)
    return _render(
        request, "partials/forwards_whatif.html",
        wi_rows=wi_rows, wi_fwd=wi_fwd, selected_def=curves.curve_def(curve),
        curve=curve, plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


# ── Gráficos (scatter TIREA vs Duration, SVG server-side) ──────────────────
graficos_router = APIRouter(tags=["graficos"])


def _chart_data(rows: list[dict], width: int = 940, height: int = 480) -> dict:
    pts = [
        (r["code"], r["duration"], r["tirea"] * 100.0, (r.get("moneda") or ""))
        for r in rows
        if r.get("duration") is not None and r["duration"] == r["duration"]
        and r.get("tirea") is not None and r["tirea"] == r["tirea"]
    ]
    if not pts:
        return {"points": [], "n": 0}
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0
    padx, pady = (xmax - xmin) * 0.08, (ymax - ymin) * 0.10
    xmin -= padx; xmax += padx; ymin -= pady; ymax += pady
    ml, mr, mt, mb = 56, 16, 14, 42
    pw, ph = width - ml - mr, height - mt - mb

    def sx(x): return round(ml + (x - xmin) / (xmax - xmin) * pw, 1)
    def sy(y): return round(mt + (1 - (y - ymin) / (ymax - ymin)) * ph, 1)

    points = []
    for code, d, t, mon in pts:
        color = "var(--cyan)" if mon.upper() in ("USD", "USB") else "var(--accent)"
        points.append({"code": code, "cx": sx(d), "cy": sy(t), "dur": d, "tirea": t, "color": color})
    points.sort(key=lambda p: p["cx"])

    # Overlay de la regresión Nelson-Siegel-Svensson (Duration → TIREA), si hay
    # puntos suficientes. Se mapea con el mismo sx/sy que el scatter.
    nss_path = None
    try:
        from backend.services import nss as nss_svc
        sm = nss_svc.sample(xs, ys)
        if sm:
            nss_path = "M " + " L ".join(f"{sx(x)},{sy(y)}" for x, y in sm)
    except Exception:  # noqa: BLE001
        nss_path = None

    def ticks(lo, hi, n=5):
        return [lo + (hi - lo) / n * i for i in range(n + 1)]

    xticks = [{"x": sx(v), "v": round(v, 1)} for v in ticks(xmin, xmax)]
    yticks = [{"y": sy(v), "v": round(v, 1)} for v in ticks(ymin, ymax)]
    return {
        "points": points, "xticks": xticks, "yticks": yticks, "nss_path": nss_path,
        "width": width, "height": height, "ml": ml, "mt": mt, "pw": pw, "ph": ph,
        "x0": ml, "x1": ml + pw, "y0": mt, "y1": mt + ph, "n": len(pts),
    }


async def _chart_for(curve_key: str, plazo: str, only_quoting: bool, leg: str) -> dict:
    rows, _meta = await _rows_for(curve_key, plazo, only_quoting, leg)
    return _chart_data(rows)


@graficos_router.get("/graficos", response_class=HTMLResponse)
async def graficos_page(
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
    chart = await _chart_for(selected_key, plazo, only_quoting, leg) if selected_key else {"points": [], "n": 0}
    return _render(
        request, "graficos.html",
        all_curves=all_curves, table=table, selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        chart=chart, plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@graficos_router.get("/graficos/svg", response_class=HTMLResponse)
async def graficos_svg(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> HTMLResponse:
    chart = await _chart_for(curve, plazo, only_quoting, leg)
    return _render(
        request, "partials/graficos_svg.html",
        chart=chart, selected_def=curves.curve_def(curve),
        plazo=plazo, only_quoting=only_quoting, leg=leg,
    )


@graficos_router.get("/graficos/estimate", response_class=HTMLResponse)
async def graficos_estimate(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
    duration: str = "",
) -> HTMLResponse:
    """Estima TIR / TEM / TNAs a una `duration` dada con la regresión NSS de la
    curva (Duration → TIREA). El fit corre en threadpool (CPU, scipy)."""
    from backend.services import nss as nss_svc

    try:
        d = float(str(duration).strip().replace(",", "."))
    except (TypeError, ValueError):
        d = None
    est = None
    if d is not None:
        rows, _meta = await _rows_for(curve, plazo, only_quoting, leg)
        pts = [(r["duration"], r["tirea"] * 100.0) for r in rows
               if r.get("duration") is not None and r["duration"] == r["duration"]
               and r.get("tirea") is not None and r["tirea"] == r["tirea"]]
        if len(pts) >= 4:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            loop = asyncio.get_running_loop()
            est = await loop.run_in_executor(None, nss_svc.estimate, d, xs, ys)
    return _render(request, "partials/graficos_estimate.html",
                   est=est, duration=duration, n=len(rows) if d is not None else 0)


@graficos_router.get("/graficos/data")
async def graficos_data(
    request: Request,
    curve: str = "",
    plazo: str = "24hs",
    only_quoting: bool = True,
    leg: str = "native",
) -> JSONResponse:
    """Datos JSON para el chart de Gráficos (uPlot): scatter ARS/USD por leg +
    la curva NSS evaluada en un grid fino. Eje x = Duration (años)."""
    import numpy as np

    from backend.services import nss as nss_svc

    rows, _meta = await _rows_for(curve, plazo, only_quoting, leg, book=True)

    def _pp(v):                       # fracción → %, NaN/None → None
        return float(v) * 100.0 if (v is not None and v == v) else None

    pts = [(r["code"], float(r["duration"]), float(r["tirea"]) * 100.0, (r.get("moneda") or "").upper(),
            _pp(r.get("tirea_bid")), _pp(r.get("tirea_offer")))
           for r in rows
           if r.get("duration") is not None and r["duration"] == r["duration"]
           and r.get("tirea") is not None and r["tirea"] == r["tirea"]]
    if not pts:
        return JSONResponse({"n": 0, "xs": [], "ars": [], "usd": [], "nss": [], "codes": [], "bid": [], "off": []})

    bond_x = sorted({p[1] for p in pts})
    bid_at: Dict[float, float] = {}
    off_at: Dict[float, float] = {}
    xs_set = set(bond_x)
    if len(pts) >= 4 and bond_x[-1] > bond_x[0]:
        xs_set |= set(float(v) for v in np.linspace(bond_x[0], bond_x[-1], 80))
    xs = sorted(xs_set)
    ars_at: Dict[float, float] = {}
    usd_at: Dict[float, float] = {}
    code_at: Dict[float, str] = {}
    for code, d, t, mon, tb, to in pts:
        (usd_at if mon in ("USD", "USB") else ars_at)[d] = t
        code_at[d] = code
        if tb is not None:
            bid_at[d] = tb
        if to is not None:
            off_at[d] = to
    # La regresión NSS se ajusta SIEMPRE sobre el last (los bid/offer son
    # series visuales extra, como en OMSweb_app).
    nss_y = nss_svc.eval_at([p[1] for p in pts], [p[2] for p in pts], xs) if len(pts) >= 4 else None
    return JSONResponse({
        "n": len(pts), "xs": xs,
        "ars": [ars_at.get(x) for x in xs],
        "usd": [usd_at.get(x) for x in xs],
        "bid": [bid_at.get(x) for x in xs],
        "off": [off_at.get(x) for x in xs],
        "codes": [code_at.get(x) for x in xs],
        "nss": nss_y or [],
    })
