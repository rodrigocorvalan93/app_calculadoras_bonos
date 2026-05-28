"""Curves routes — Phase 2 step 1.

For now the table is static metadata (Vto / Moneda / Cupón / TIPO TASA /
Index / Ajuste) for every bond in the chosen curve. Live prices and
the TIREA column land in step 2, once the broker session is in place.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, curves, pricing

router = APIRouter(prefix="/curves", tags=["curves"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _rows_for(curve_key: str) -> list[dict]:
    """One row per bond code in the curve — metadata only for now."""
    codes = curves.build_curve_codes().get(curve_key, [])
    out = []
    for code in codes:
        meta = pricing.bond_meta(code)
        if not meta:
            continue
        out.append(meta)
    return out


@router.get("", response_class=HTMLResponse)
async def curves_page(request: Request, curve: str | None = None) -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    default_key = next((c.key for c in all_curves if table.get(c.key)), None)
    selected_key = curve if (curve and curve in table) else default_key
    return _render(
        request,
        "curves.html",
        all_curves=all_curves,
        table=table,
        selected_key=selected_key,
        selected_def=curves.curve_def(selected_key) if selected_key else None,
        rows=_rows_for(selected_key) if selected_key else [],
    )


@router.get("/table", response_class=HTMLResponse)
async def curve_table_partial(request: Request, curve: str = "") -> HTMLResponse:
    """HTMX partial: table body only for the requested curve."""
    return _render(
        request,
        "partials/curve_table.html",
        selected_def=curves.curve_def(curve),
        rows=_rows_for(curve),
    )
