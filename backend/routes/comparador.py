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


def _is_num(x) -> bool:
    try:
        return x is not None and float(x) == float(x)  # descarta None y NaN
    except (TypeError, ValueError):
        return False


def _forward_implicit(ma: Dict[str, Any], mb: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Forward implícita en TIR entre los dos bonos (capitalización EA),
    usando Duration como eje temporal — misma convención que
    plotter.matriz_forwards_tir. Detecta el corto (t1) y el largo (t2):

        fwd = [ (1+y2)^t2 / (1+y1)^t1 ]^(1/(t2−t1)) − 1
    """
    ya, yb, ta, tb = ma.get("tirea"), mb.get("tirea"), ma.get("duration"), mb.get("duration")
    if not all(_is_num(v) for v in (ya, yb, ta, tb)):
        return None
    if ta <= 0 or tb <= 0 or ta == tb:
        return None
    if ta < tb:
        c1, y1, t1, c2, y2, t2 = ma["code"], ya, ta, mb["code"], yb, tb
    else:
        c1, y1, t1, c2, y2, t2 = mb["code"], yb, tb, ma["code"], ya, ta
    try:
        fwd = ((1.0 + y2) ** t2 / (1.0 + y1) ** t1) ** (1.0 / (t2 - t1)) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if fwd != fwd:
        return None
    return {"short": c1, "long": c2, "t1": t1, "t2": t2, "y1": y1, "y2": y2, "fwd": fwd}


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
    swap: Optional[Dict[str, Any]] = None
    fwd: Optional[Dict[str, Any]] = None
    if ma and mb and not ma.get("error") and not mb.get("error"):
        for k in _DELTA_KEYS:
            va, vb = ma.get(k), mb.get(k)
            try:
                if va is not None and vb is not None and va == va and vb == vb:
                    deltas[k] = float(va) - float(vb)
            except (TypeError, ValueError):
                pass

        # VN equivalente a mismo efectivo: monto_A = VN_A × precio_A;
        # VN_B equivalente = monto_A / precio_B (ej. 1mm de A ≈ 1,2mm de B).
        pa, pb = ma.get("precio"), mb.get("precio")
        if _is_num(pa) and _is_num(pb) and float(pb) != 0:
            try:
                monto_a = float(vn) * float(pa)
                swap = {
                    "vn_a": float(vn), "monto_a": monto_a,
                    "vn_b": monto_a / float(pb), "monto_b": monto_a,
                    "moneda_a": ma.get("moneda"), "moneda_b": mb.get("moneda"),
                }
            except (TypeError, ValueError, ZeroDivisionError):
                swap = None

        fwd = _forward_implicit(ma, mb)

    return _render(
        request,
        "partials/comparador_result.html",
        ma=ma, mb=mb, deltas=deltas, swap=swap, fwd=fwd,
        a=a, b=b, mode=mode, plazo=plazo, vn=vn,
    )


@router.get("/comparador/valfield", response_class=HTMLResponse)
async def comparador_valfield(
    request: Request,
    which: str = "a",
    a: str = "",
    b: str = "",
    mode: str = "precio",
    plazo: str = "24hs",
) -> HTMLResponse:
    """Re-renderiza el input de Valor A/B prellenado con el last del mercado
    (modo precio). Se dispara al cambiar el bono."""
    code = a if which == "a" else b
    val = ""
    if mode == "precio" and code:
        last = _market_last(code, plazo)
        if last is not None:
            val = repr(float(last))  # número plano para <input type=number>
    return _render(request, "partials/comparador_valfield.html", which=which, val=val)
