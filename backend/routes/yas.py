"""YAS routes — Análisis de Yields.

Layout:
- GET  /yas                      → full page (selectbox + form + result panel)
- POST /yas/recompute            → HTML partial with metrics + ticket + cashflows
- GET  /yas/cashflows/{code}     → expander body for the cashflows accordion
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.locale_ar import parse_ar_num
from backend.services import bond_universe, curves as curves_svc, delta_especies, marketdata_store, positions, pricing, symbols as syms

router = APIRouter(prefix="/yas", tags=["yas"])


def _parse_ar_number(raw: Optional[str]) -> Optional[float]:
    """Parser es-AR canónico (puntos = miles, coma = decimal). Antes era una copia
    propia que sólo sacaba los puntos si había coma → un VN/precio con miles
    ('2.000.000', '500.000') daba None y caía al default 1.000.000 sin avisar."""
    return parse_ar_num(raw)


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template, ctx)


@router.get("", response_class=HTMLResponse)
async def yas_page(request: Request, code: Optional[str] = None) -> HTMLResponse:
    codes = bond_universe.all_codes()
    if not codes:
        return _render(
            request,
            "yas.html",
            codes=[],
            selected=None,
            meta={},
            plazo=settings.default_plazo,
            default_value="",
        )

    selected = code if code in codes else codes[0]
    # Autofill por defecto: último precio del activo seleccionado (modo precio).
    snap = marketdata_store.get_store().get(syms.md_symbol(selected, settings.default_plazo))
    last = snap.last if snap else None
    default_value = "" if last is None else str(last).replace(".", ",")
    return _render(
        request,
        "yas.html",
        codes=codes,
        selected=selected,
        meta=pricing.bond_meta(selected),
        plazo=settings.default_plazo,
        default_value=default_value,
    )


@router.post("/recompute", response_class=HTMLResponse)
async def yas_recompute(
    request: Request,
    code: str = Form(...),
    mode: str = Form("precio"),
    value: str = Form(""),
    nominales: str = Form("1000000"),
    plazo: str = Form("24hs"),
    settle_custom: str = Form(""),
    fx_override: str = Form(""),
    freq_override: str = Form(""),
    base_override: str = Form(""),
) -> HTMLResponse:
    parsed_value = _parse_ar_number(value)
    parsed_nom = _parse_ar_number(nominales) or 1_000_000.0
    parsed_fx = _parse_ar_number(fx_override)
    parsed_freq = _parse_ar_number(freq_override)
    parsed_base = _parse_ar_number(base_override)

    if parsed_value is None:
        return _render(
            request,
            "partials/yas_result.html",
            metrics={"error": "Ingresá un valor numérico."},
            ticket={},
            meta=pricing.bond_meta(code),
            mode=mode,
        )

    settle = settle_custom.strip() or pricing.settlement_date_str(plazo)
    metrics = pricing.compute_metrics(
        code=code,
        mode=mode,
        value=parsed_value,
        settle=settle,
        fx_override=parsed_fx,
        freq_override=int(parsed_freq) if parsed_freq else None,
        base_override=int(parsed_base) if parsed_base else None,
    )
    ticket = pricing.ticket_rows(metrics, nominales=parsed_nom)
    return _render(
        request,
        "partials/yas_result.html",
        metrics=metrics,
        curve_key=curves_svc.curve_key_for(code),
        curve_label=(curves_svc.curve_def(curves_svc.curve_key_for(code) or "") or None) and curves_svc.curve_def(curves_svc.curve_key_for(code)).label,
        ticket=ticket,
        meta=pricing.bond_meta(code),
        mode=mode,
        position=positions.position_for(code),
        especie=delta_especies.info(code),
    )


@router.get("/meta/{code}", response_class=HTMLResponse)
async def yas_meta(request: Request, code: str) -> HTMLResponse:
    """Used by the dropdown to refresh the header strip when the bond changes."""
    return _render(
        request,
        "partials/yas_header.html",
        meta=pricing.bond_meta(code),
    )


@router.get("/market", response_class=HTMLResponse)
async def yas_market_card(
    request: Request,
    code: str = "",
    plazo: str = "24hs",
) -> HTMLResponse:
    """HTMX partial — bid / offer / last / OHLC for a bond from the store.

    El `code` viene por query (hx-include del form), no en la URL — así el
    panel sigue al bono seleccionado en vez de quedar fijo al inicial.
    """
    store = marketdata_store.get_store()
    symbol = syms.md_symbol(code, plazo) if code else ""
    snap = store.get(symbol) if symbol else None
    return _render(
        request,
        "partials/yas_market_card.html",
        snap=snap.to_dict() if snap else None,
        symbol=symbol,
        code=code,
        plazo=plazo,
    )
