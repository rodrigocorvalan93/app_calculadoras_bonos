"""Dólares — monitor FX (SIOPEL oficial + USD/USB implícito por bono +
canje + calculadora de operación) y el riel lateral en vivo.

Todo lee de caches en memoria (`services.dolares` → store + historico +
snapshot MAE del poller), así que cada endpoint cumple el target
sub-50 ms p95 sin tocar el broker en el path de request.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from backend.services import dolares as dx, fx as fx_svc

router = APIRouter(tags=["dolares"])

_PLAZOS = ("24hs", "CI")
_LEGS = (("USD", "USD · Cable"), ("USB", "USB · MEP"))


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _norm_plazos(plazo: str) -> List[str]:
    p = (plazo or "24hs").lower()
    if p in ("ambos", "both", "todos"):
        return ["24hs", "CI"]
    return ["CI"] if p.startswith("ci") else ["24hs"]


def _tables_ctx(plazo: str) -> Dict[str, Any]:
    plazos = _norm_plazos(plazo)
    blocks = []
    for pz in plazos:
        blocks.append({
            "plazo": pz,
            "usd": dx.fx_rows("USD", pz),
            "usb": dx.fx_rows("USB", pz),
            "canje": dx.canje_rows(pz),
        })
    return {"blocks": blocks, "plazo_sel": plazo, "legs": _LEGS}


@router.get("/dolares", response_class=HTMLResponse)
async def dolares_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bases = fx_svc.fx_bases()
    ctx = _tables_ctx(plazo)
    return _render(
        request,
        "dolares.html",
        bases=bases,
        siopel=dx.siopel_rows(),
        oficial=dx.official_fx(),
        summary=dx.summary("24hs"),
        plazos_opt=[("24hs", "24 hs"), ("CI", "Contado Inmediato"), ("ambos", "Ambos")],
        **ctx,
    )


@router.get("/dolares/tables", response_class=HTMLResponse)
async def dolares_tables(request: Request, plazo: str = "24hs") -> HTMLResponse:
    """Partial htmx: tablas FX implícito + canje (auto-refresh)."""
    return _render(request, "partials/dolares_tables.html", **_tables_ctx(plazo))


@router.get("/dolares/oficial", response_class=HTMLResponse)
async def dolares_oficial(request: Request) -> HTMLResponse:
    """Partial htmx: SIOPEL oficial + A3500 (auto-refresh)."""
    return _render(
        request, "partials/dolares_oficial.html",
        siopel=dx.siopel_rows(), oficial=dx.official_fx(),
    )


@router.get("/dolares/rail", response_class=HTMLResponse)
async def dolares_rail(request: Request, plazo: str = "24hs") -> HTMLResponse:
    """Partial htmx del riel lateral (se carga en todas las pestañas)."""
    pz = "CI" if (plazo or "").lower().startswith("ci") else "24hs"
    return _render(request, "partials/fx_rail.html", summary=dx.summary(pz))


@router.get("/dolares/calc", response_class=HTMLResponse)
async def dolares_calc(
    request: Request,
    base: str = Query("GD30"),
    leg: str = Query("USD"),
    plazo: str = Query("24hs"),
    side: str = Query("comprar"),     # comprar | vender (USD)
    modo: str = Query("usd"),         # usd | ars  (en qué moneda fijo la cantidad)
    cantidad: float = Query(10000.0),
) -> HTMLResponse:
    leg = leg.upper() if leg.upper() in ("USD", "USB") else "USD"
    pz = "CI" if (plazo or "").lower().startswith("ci") else "24hs"
    p = dx.puntas(base, leg, pz)

    res: Dict[str, Any] = {
        "ok": False, "base": base, "leg": leg, "plazo": pz, "side": side,
        "modo": modo, "cantidad": cantidad, "puntas": p,
    }

    # Comprar USD: pago bono en ARS al offer, vendo la pata USD al bid → TC = offer implícito.
    # Vender USD : compro la pata USD al offer, vendo bono ARS al bid   → TC = bid implícito.
    if side == "comprar":
        px_a, px_u, fx_eff = p["ars_offer"], p["usd_bid"], p["offer"]
        lbl_a, lbl_u = "compra bono ARS", "venta pata USD"
    else:
        px_a, px_u, fx_eff = p["ars_bid"], p["usd_offer"], p["bid"]
        lbl_a, lbl_u = "venta bono ARS", "compra pata USD"

    if px_a and px_u and fx_eff:
        if (modo or "usd").startswith("usd"):
            usd_qty = float(cantidad)
            vn = usd_qty * 100.0 / px_u
            ars_amt = vn * px_a / 100.0
        else:
            ars_amt = float(cantidad)
            vn = ars_amt * 100.0 / px_a
            usd_qty = vn * px_u / 100.0
        res.update({
            "ok": True, "vn": vn, "ars": ars_amt, "usd": usd_qty,
            "fx_eff": fx_eff, "px_a": px_a, "px_u": px_u,
            "lbl_a": lbl_a, "lbl_u": lbl_u,
        })
    return _render(request, "partials/dolares_calc.html", r=res)
