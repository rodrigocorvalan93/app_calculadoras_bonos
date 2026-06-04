"""Futuros de dólar (DLR) — tasas implícitas (mayorista/minorista) + un panel
de los Dólar Linked soberanos contra la implícita del futuro más cercano.

Lee todo de cache (store + official_fx + curva DLK) → sub-50 ms.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, futuros as fut

router = APIRouter(tags=["futuros"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


async def _ctx() -> Dict[str, Any]:
    bond_universe.ensure_loaded()
    near = fut.nearest("may") or fut.nearest("min")
    # Dólar Linked soberanos (TIR/duration de la curva) vs la implícita del futuro.
    try:
        from backend.routes.curves import _rows_for
        dlk_rows, _meta = await _rows_for("dolarlinked", "24hs", False, "native")
    except Exception:  # noqa: BLE001
        dlk_rows = []
    dlk = [{"code": r["code"], "tirea": r.get("tirea"), "duration": r.get("duration"), "last": r.get("last")}
           for r in dlk_rows if r.get("tirea") is not None]
    dlk.sort(key=lambda r: (r["duration"] if r["duration"] is not None else 9999.0))
    return {"may_rows": fut.rows("may"), "min_rows": fut.rows("min"),
            "spot": fut.spot(), "near": near, "dlk": dlk}


@router.get("/futuros", response_class=HTMLResponse)
async def futuros_page(request: Request) -> HTMLResponse:
    return _render(request, "futuros.html", **(await _ctx()))


@router.get("/futuros/table", response_class=HTMLResponse)
async def futuros_table(request: Request) -> HTMLResponse:
    return _render(request, "partials/futuros_table.html", **(await _ctx()))
