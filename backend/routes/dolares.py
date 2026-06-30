"""Dólares — monitor FX (SIOPEL oficial + USD/USB implícito por bono +
canje + calculadora de operación) y el riel lateral en vivo.

Todo lee de caches en memoria (`services.dolares` → store + historico +
snapshot MAE del poller), así que cada endpoint cumple el target
sub-50 ms p95 sin tocar el broker en el path de request.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from backend.services import cauciones as cauc_svc, dolares as dx, fx as fx_svc, historico

logger = logging.getLogger("backend.dolares.routes")

router = APIRouter(tags=["dolares"])

_PLAZOS = ("24hs", "CI")
_LEGS = (("USD", "USD · Cable"), ("USB", "USB · MEP"))


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _safe(label: str, fn: Callable[[], Any], default: Any) -> Any:
    """Corre `fn` y, si lanza, loguea el traceback y degrada a `default` — el
    monitor de dólar no debe tirar 500 (se carga en todas las pestañas)."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        logger.exception("[dolares] %s falló; degradado", label)
        return default


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
            "usd": _safe(f"fx_rows USD {pz}", lambda pz=pz: dx.fx_rows("USD", pz), []),
            "usb": _safe(f"fx_rows USB {pz}", lambda pz=pz: dx.fx_rows("USB", pz), []),
            "canje": _safe(f"canje_rows {pz}", lambda pz=pz: dx.canje_rows(pz), []),
        })
    return {"blocks": blocks, "plazo_sel": plazo, "legs": _LEGS}


@router.get("/dolares", response_class=HTMLResponse)
async def dolares_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    ctx = _safe("tables_ctx", lambda: _tables_ctx(plazo),
                {"blocks": [], "plazo_sel": plazo, "legs": _LEGS})
    return _render(
        request,
        "dolares.html",
        bases=_safe("fx_bases", fx_svc.fx_bases, []),
        siopel=_safe("siopel_rows", dx.siopel_rows, []),
        oficial=dx.official_fx(),          # self-guarded (nunca lanza)
        summary=dx.summary("24hs"),        # self-guarded (nunca lanza)
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
        siopel=_safe("siopel_rows", dx.siopel_rows, []), oficial=dx.official_fx(),
    )


@router.get("/dolares/rail", response_class=HTMLResponse)
async def dolares_rail(request: Request, plazo: str = "24hs") -> HTMLResponse:
    """Partial htmx del riel lateral (se carga en todas las pestañas)."""
    pz = "CI" if (plazo or "").lower().startswith("ci") else "24hs"
    _safe("macro_refresh", historico.macro_maybe_refresh, None)   # re-lee sólo 11:00 / 15:30
    return _render(request, "partials/fx_rail.html", summary=dx.summary(pz),
                   caucion=_safe("caucion_rail", lambda: cauc_svc.rail_pick("PESOS"), None),
                   macro=_safe("macro_snapshot", historico.macro_snapshot, []))


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
    p = _safe("puntas", lambda: dx.puntas(base, leg, pz), {
        "base": base, "leg": leg, "plazo": pz, "ars_bid": None, "ars_offer": None,
        "ars_last": None, "usd_bid": None, "usd_offer": None, "usd_last": None,
        "bid": None, "last": None, "offer": None})

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
