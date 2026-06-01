"""Comparador de bonos — A vs B por precio, TIREA, TNA o margen, métricas lado
a lado.

Reutiliza el motor de YAS (`pricing.compute_metrics`): cada bono se valúa al
precio / TIREA / TNA / margen dado y se muestran Precio / TIREA / TNA / TEM /
Duration / Paridad / Margen, con la diferencia B−A para las métricas
comparables. Si no se pasa precio y el modo es "precio", se autocompleta con el
last del store (igual que el autofill del comparador legacy de OMSweb_app). El
margen sólo aplica a tasa variable benchmarkeada (TAMAR/BADLAR); en los demás
bonos cae a valuar por el last y se marca "no aplica".
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import bond_universe, delta_especies, marketdata_store, positions, pricing, symbols as syms

router = APIRouter(tags=["comparador"])

# modo del comparador → modo de compute_metrics (mismos 4 que YAS)
_MODE = {"precio": "precio", "tir": "tir", "tna": "tna", "margen": "margen"}
# métricas (decimales) con diferencia B−A comparable
_DELTA_KEYS = ("tirea", "tna", "tem", "duration", "paridad", "margen_tna")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _margen_aplica(meta: Dict[str, Any]) -> bool:
    """El margen TNA sólo tiene sentido en tasa variable con benchmark
    (TAMAR/BADLAR) — mismo criterio que pricing.index_applied / margen_tna."""
    return (
        (meta.get("tipo_tasa_interes") or "").upper() in ("VARIABLE", "VARIABLE_CAP")
        and (meta.get("index") or "").upper() in ("TAMAR", "BADLAR")
    )


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
        meta = pricing.bond_meta(code) or {}
        v = _to_float(val)
        eff_mode = cm_mode
        margen_na = False
        if cm_mode == "margen" and not _margen_aplica(meta):
            # tasa fija/CER/HD: el margen no aplica → valúo al last para igual
            # mostrar las métricas, y marco "no aplica".
            margen_na = True
            eff_mode = "precio"
            v = _market_last(code, plazo)
        elif v is None and cm_mode == "precio":
            v = _market_last(code, plazo)   # autofill desde el mercado
        if v is None:
            return {
                "code": code, "nombre": meta.get("nombre"), "moneda": meta.get("moneda"),
                "vencimiento": meta.get("vencimiento"), "margen_na": margen_na,
                "error": "margen no aplica y sin last de mercado" if margen_na
                else ("sin last de mercado" if cm_mode == "precio" else "ingresá un valor"),
            }
        m = pricing.compute_metrics(code, eff_mode, v, settle=settle, include_cashflows=False)
        m["code"] = code
        m["nombre"] = meta.get("nombre")
        m["moneda"] = meta.get("moneda")
        m["vencimiento"] = meta.get("vencimiento")
        m["input_value"] = v
        m["margen_na"] = margen_na
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
                    deltas[k] = float(vb) - float(va)
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
        pos_a=positions.position_for(a), pos_b=positions.position_for(b),
        esp_a=delta_especies.info(a), esp_b=delta_especies.info(b),
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
