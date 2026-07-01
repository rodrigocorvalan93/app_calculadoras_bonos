"""Nueva especie (ad-hoc) — armá o pegá una ficha y calculá en vivo.

Flujo:
  GET  /nueva            → página (formulario guiado + textarea de pegado)
  POST /nueva/parse      → construye la ficha (form o pegado), la registra en el
                           store en memoria y devuelve el panel (header + form de
                           cálculo + primer resultado)
  POST /nueva/recompute  → recalcula sobre la ficha del token (precio/tir/tna/margen)
  POST /nueva/guardar    → agrega la ficha a especies.py (acción deliberada)

Cero impacto en el arranque: la ficha NO entra al universo; se arma en el
request sobre una copia y se descarta. Reusa `pricing.compute_metrics` vía
`obj_override` y los partials de métricas/cashflow de YAS.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.locale_ar import parse_ar_num
from backend.services import adhoc, pricing

router = APIRouter(prefix="/nueva", tags=["nueva"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


@router.get("", response_class=HTMLResponse)
async def nueva_page(request: Request) -> HTMLResponse:
    return _render(request, "nueva.html")


def _panel(request: Request, token: str, ficha: dict, *, mode: str = "precio",
           value: float = 100.0, settle: str = "") -> HTMLResponse:
    """Panel completo: encabezado + form de cálculo + primer resultado."""
    metrics = adhoc.compute(token, mode, value, settle=settle or None)
    ticket = pricing.ticket_rows(metrics) if not metrics.get("error") else {}
    return _render(
        request, "partials/nueva_panel.html",
        token=token, meta=adhoc.meta_from_ficha(ficha), metrics=metrics, ticket=ticket,
        mode=mode, default_value=str(value).replace(".", ","),
        n_cupones=len(ficha.get("Fechas de cupón") or []),
        existe=adhoc.especie_existe(str(ficha.get("Código") or "")),
    )


@router.post("/parse", response_class=HTMLResponse)
async def nueva_parse(
    request: Request,
    entrada: str = Form("form"),
    # pegado
    ficha_text: str = Form(""),
    # form guiado
    codigo: str = Form(""),
    nombre: str = Form(""),
    moneda: str = Form("ARS"),
    clasificacion: str = Form(""),
    emision: str = Form(""),
    vencimiento: str = Form(""),
    primer_cupon: str = Form(""),
    frecuencia: str = Form("2"),
    convencion_base: str = Form("365"),
    convencion_devengamiento: str = Form("Actual"),
    tipo_tasa: str = Form("FIJA"),
    cupon: str = Form("0"),
    index: str = Form(""),
    ajuste: str = Form(""),
    tipo_amortizacion: str = Form("BULLET"),
    cuotas_finales: str = Form("1"),
    amortizacion_custom: str = Form(""),
    valor_nominal: str = Form("100"),
    quote_price_cnv: str = Form("DIRTY"),
) -> HTMLResponse:
    try:
        if entrada == "pegar":
            _name, ficha = adhoc.parse_ficha(ficha_text)
        else:
            ficha = adhoc.build_ficha_from_form({
                "codigo": codigo, "nombre": nombre, "moneda": moneda,
                "clasificacion": clasificacion, "emision": emision,
                "vencimiento": vencimiento, "primer_cupon": primer_cupon,
                "frecuencia": frecuencia, "convencion_base": convencion_base,
                "convencion_devengamiento": convencion_devengamiento,
                "tipo_tasa": tipo_tasa, "cupon": cupon, "index": index, "ajuste": ajuste,
                "tipo_amortizacion": tipo_amortizacion, "cuotas_finales": cuotas_finales,
                "amortizacion_custom": amortizacion_custom, "valor_nominal": valor_nominal,
                "quote_price_cnv": quote_price_cnv,
            })
        token, _code = adhoc.register(ficha)
    except ValueError as exc:
        return _render(request, "partials/nueva_error.html", error=str(exc))
    return _panel(request, token, ficha)


@router.post("/recompute", response_class=HTMLResponse)
async def nueva_recompute(
    request: Request,
    token: str = Form(...),
    mode: str = Form("precio"),
    value: str = Form(""),
    settle_custom: str = Form(""),
) -> HTMLResponse:
    ficha = adhoc.get_ficha(token)
    if ficha is None:
        return _render(request, "partials/nueva_error.html",
                       error="La ficha expiró. Volvé a generarla o pegarla.")
    parsed = parse_ar_num(value)
    if parsed is None:
        return _render(request, "partials/nueva_result.html",
                       metrics={"error": "Ingresá un valor numérico."}, ticket={}, token=token,
                       existe=adhoc.especie_existe(str(ficha.get("Código") or "")))
    metrics = adhoc.compute(token, mode, parsed, settle=settle_custom.strip() or None)
    ticket = pricing.ticket_rows(metrics) if not metrics.get("error") else {}
    return _render(request, "partials/nueva_result.html",
                   metrics=metrics, ticket=ticket, token=token,
                   meta=adhoc.meta_from_ficha(ficha),
                   existe=adhoc.especie_existe(str(ficha.get("Código") or "")))


@router.post("/guardar", response_class=HTMLResponse)
async def nueva_guardar(request: Request, token: str = Form(...)) -> HTMLResponse:
    res = adhoc.guardar(token)
    return _render(request, "partials/nueva_guardar.html", res=res)
