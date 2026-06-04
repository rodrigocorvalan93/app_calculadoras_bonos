"""Futuros de dólar (DLR) — tasas implícitas (mayorista/minorista) + un panel
de los Dólar Linked soberanos con su tasa SINTÉTICA contra el futuro más cercano
a la duration de cada bono.

Lee todo de cache (store + official_fx + curva DLK) → sub-50 ms.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, futuros as fut, marketdata_store

router = APIRouter(tags=["futuros"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _parse_num(s: Optional[str]) -> Optional[float]:
    """Parsea el override de spot (acepta '1.435,50' es-AR o '1435.5')."""
    if not s:
        return None
    t = str(s).strip()
    if "," in t:                      # formato es-AR: . miles, , decimal
        t = t.replace(".", "").replace(",", ".")
    try:
        v = float(t)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _bond_tna(tirea: float, freq: float = 90.0, base: float = 365.0) -> float:
    """TNA del DLK desde su TIREA (convención 90/365)."""
    return ((1.0 + tirea) ** (freq / base) - 1.0) * (base / freq)


async def _ctx(spot_override: str = "") -> Dict[str, Any]:
    bond_universe.ensure_loaded()
    sp_over = _parse_num(spot_override)
    may_rows = fut.rows("may", sp_over)
    min_rows = fut.rows("min", sp_over)
    spot = sp_over if sp_over else fut.spot()
    near = next((r for r in may_rows if r["dias"] and r["dias"] > 0 and r["tna"] is not None), None) \
        or next((r for r in min_rows if r["dias"] and r["dias"] > 0 and r["tna"] is not None), None)

    # Curvas DLK + Todos ARS en paralelo (cada una usa el threadpool por dentro).
    try:
        from backend.routes.curves import _rows_for
        dlk_rows, ars_rows = await asyncio.gather(
            _rows_for("dolarlinked", "24hs", False, "native"),
            _rows_for("todos_ars_proyectado", "24hs", False, "native"),
        )
        dlk_rows, ars_rows = dlk_rows[0], ars_rows[0]
    except Exception:  # noqa: BLE001
        dlk_rows, ars_rows = [], []

    matchable = [r for r in may_rows if r["dias"] and r["dias"] > 0 and r.get("td") is not None]

    def _match(dur: Optional[float]):
        if not matchable or not dur:
            return None
        m = min(matchable, key=lambda f: abs(f["dias"] - dur * 365.0))
        return m, (1.0 + m["td"]) ** (365.0 / m["dias"]) - 1.0   # (futuro, TEA implícita)

    # 1) DLK soberanos → sintético PESO: (1+TIR_bono)·(1+TEA_fut)−1 ; TNA_bono + TNA_fut.
    dlk: List[Dict[str, Any]] = []
    for r in dlk_rows:
        tirea, dur = r.get("tirea"), r.get("duration")
        if tirea is None:
            continue
        b: Dict[str, Any] = {"code": r["code"], "tirea": tirea, "duration": dur, "last": r.get("last")}
        mm = _match(dur)
        if mm:
            m, tea_fut = mm
            b.update({"fut_label": m["label"], "fut_code": m["code"], "fut_tna": m["tna"], "fut_tea": tea_fut,
                      "tir_sint": (1.0 + tirea) * (1.0 + tea_fut) - 1.0,
                      "tna_sint": (_bond_tna(tirea) + m["tna"]) if m["tna"] is not None else None})
        dlk.append(b)
    dlk.sort(key=lambda x: (x["duration"] if x["duration"] is not None else 9999.0))

    # 2) Curva ARS (≤1.5y dur) → sintético DÓLAR LINKED (al revés): le sacamos la
    #    deval del futuro. TIR sint = (1+TIR_ars)/(1+TEA_fut)−1 ; TNA sint = TNA_ars − TNA_fut.
    ars: List[Dict[str, Any]] = []
    for r in ars_rows:
        tirea, dur, tna = r.get("tirea"), r.get("duration"), r.get("tna")
        if tirea is None or dur is None or dur > 1.5:
            continue
        a: Dict[str, Any] = {"code": r["code"], "tirea": tirea, "tna": tna, "duration": dur, "last": r.get("last")}
        mm = _match(dur)
        if mm:
            m, tea_fut = mm
            a.update({"fut_label": m["label"], "fut_tna": m["tna"], "fut_tea": tea_fut,
                      "tir_sint": (1.0 + tirea) / (1.0 + tea_fut) - 1.0,
                      "tna_sint": (tna - m["tna"]) if (tna is not None and m["tna"] is not None) else None})
        ars.append(a)
    ars.sort(key=lambda x: x["duration"])

    return {"may_rows": may_rows, "min_rows": min_rows, "spot": spot, "near": near,
            "dlk": dlk, "ars": ars, "spot_override": spot_override or ""}


@router.get("/futuros", response_class=HTMLResponse)
async def futuros_page(request: Request, spot_override: str = "") -> HTMLResponse:
    return _render(request, "futuros.html", **(await _ctx(spot_override)))


@router.get("/futuros/table", response_class=HTMLResponse)
async def futuros_table(request: Request, spot_override: str = "") -> HTMLResponse:
    return _render(request, "partials/futuros_table.html", **(await _ctx(spot_override)))


@router.get("/futuros/book", response_class=HTMLResponse)
async def futuros_book(request: Request, code: str = "", spot_override: str = "") -> HTMLResponse:
    """Profundidad (book) de un contrato + su tasa implícita por punta."""
    store = marketdata_store.get_store()
    snap = store.get(code)
    sp = _parse_num(spot_override) or fut.spot()
    vto = fut._parse_vto(code)
    dias = (vto - date.today()).days if vto else None

    def impl(px):
        return fut._impl(px, sp, dias)[1]   # TNA implícita

    bids, offers = [], []
    if snap is not None:
        for lvl in (snap.bids or []):
            bids.append({"price": lvl.get("price"), "size": lvl.get("size"), "tna": impl(lvl.get("price"))})
        for lvl in (snap.offers or []):
            offers.append({"price": lvl.get("price"), "size": lvl.get("size"), "tna": impl(lvl.get("price"))})
    return _render(request, "partials/futuros_book.html",
                   code=code, label=fut._label(code), snap=snap, dias=dias, spot=sp,
                   bids=bids, offers=offers,
                   tna_last=(impl(snap.last) if snap else None))
