"""Comparador de bonos — A vs B por precio o TNA, métricas lado a lado.

Reutiliza el motor de YAS (`pricing.compute_metrics`): cada bono se valúa al
precio (o TNA) dado y se muestran Precio / TIREA / TNA / TEM / Duration /
Paridad / Margen, con la diferencia A−B para las métricas comparables. Si no
se pasa precio y el modo es "precio", se autocompleta con el last del store
(igual que el autofill del comparador legacy de OMSweb_app).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, marketdata_store, pricing, symbols as syms

router = APIRouter(tags=["comparador"])

# modo del comparador → modo de compute_metrics
_MODE = {"precio": "precio", "tna": "tna"}
# métricas (decimales) con diferencia A−B comparable
_DELTA_KEYS = ("tirea", "tna", "tem", "duration", "paridad")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _market_last(code: str, plazo: str) -> Optional[float]:
    snap = marketdata_store.get_store().get(syms.md_symbol(code, plazo))
    return snap.last if snap else None


@router.get("/comparador", response_class=HTMLResponse)
async def comparador_page(
    request: Request,
    a: str = "",
    b: str = "",
    mode: str = "precio",
    plazo: str = "24hs",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(
        request,
        "comparador.html",
        codes=bond_universe.all_codes(),
        a=a, b=b, mode=mode, plazo=plazo,
    )


@router.get("/comparador/result", response_class=HTMLResponse)
async def comparador_result(
    request: Request,
    a: str = "",
    b: str = "",
    mode: str = "precio",
    val_a: str = "",
    val_b: str = "",
    vn: float = 1_000_000.0,
    plazo: str = "24hs",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    settle = pricing.settlement_date_str(plazo)
    cm_mode = _MODE.get(mode, "precio")

    def metrics(code: str, val: str) -> Optional[Dict[str, Any]]:
        if not code:
            return None
        v = _to_float(val)
        if v is None and cm_mode == "precio":
            v = _market_last(code, plazo)   # autofill desde el mercado
        if v is None:
            return None
        m = pricing.compute_metrics(code, cm_mode, v, settle=settle, include_cashflows=False)
        meta = pricing.bond_meta(code) or {}
        m["code"] = code
        m["nombre"] = meta.get("nombre")
        m["moneda"] = meta.get("moneda")
        m["vencimiento"] = meta.get("vencimiento")
        m["input_value"] = v
        return m

    ma = metrics(a, val_a)
    mb = metrics(b, val_b)

    deltas: Dict[str, float] = {}
    if ma and mb and not ma.get("error") and not mb.get("error"):
        for k in _DELTA_KEYS:
            va, vb = ma.get(k), mb.get(k)
            try:
                if va is not None and vb is not None and va == va and vb == vb:
                    deltas[k] = float(va) - float(vb)
            except (TypeError, ValueError):
                pass

    return _render(
        request,
        "partials/comparador_result.html",
        ma=ma, mb=mb, deltas=deltas, a=a, b=b, mode=mode, plazo=plazo, vn=vn,
    )
