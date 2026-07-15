"""YAS routes — Análisis de Yields.

Layout:
- GET  /yas                      → full page (selectbox + form + result panel)
- POST /yas/recompute            → HTML partial with metrics + ticket + cashflows
- GET  /yas/cashflows/{code}     → expander body for the cashflows accordion
"""
from __future__ import annotations

import asyncio
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
    # compute_metrics + ticket_rows son GIL-bound (el calc legacy no libera el
    # GIL); un CER pesado llega a ~64-76 ms. En el handler async bloquearían el
    # event loop y con él /market/seq y los paneles live de todos. Al pool.
    def _calc():
        m = pricing.compute_metrics(
            code=code,
            mode=mode,
            value=parsed_value,
            settle=settle,
            fx_override=parsed_fx,
            freq_override=int(parsed_freq) if parsed_freq else None,
            base_override=int(parsed_base) if parsed_base else None,
        )
        return m, pricing.ticket_rows(m, nominales=parsed_nom)

    metrics, ticket = await asyncio.get_running_loop().run_in_executor(None, _calc)
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


# ── Mini-histórico de la ficha (precio + TIR desde la base BYMA) ────────────
def _spark(pairs, scale=1.0, w=300, h=64):
    """Sparkline SVG de una serie [(iso_date, val)] ya filtrada de Nones.
    Devuelve dict para el template (path + último punto + rango) o None."""
    if len(pairs) < 2:
        return None
    vals = [v * scale for _, v in pairs]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or (abs(vmax) * 0.01 or 1.0)
    pad = span * 0.08
    lo, hi = vmin - pad, vmax + pad
    n = len(vals)
    pts = [(round(4 + i * (w - 8) / (n - 1), 1),
            round(4 + (1 - (v - lo) / (hi - lo)) * (h - 8), 1)) for i, v in enumerate(vals)]
    return {
        "w": w, "h": h,
        "path": "M " + " L ".join(f"{x},{y}" for x, y in pts),
        "x1": pts[-1][0], "y1": pts[-1][1],
        "vmin": vmin, "vmax": vmax,
        "first": vals[0], "last": vals[-1],
        "d0": pairs[0][0], "d1": pairs[-1][0], "n": n,
    }


def _hist_ctx(code: str, dias: int) -> dict:
    """Series del bono desde la base histórica (cacheada en memoria): lookup
    O(1) por código + slicing de ≤250 puntos + armado de 2 SVGs (~µs). Si el
    código exacto no está (p. ej. ficha hermana), matchea por base md."""
    from backend.services import historico_byma

    c = historico_byma.ensure_loaded()
    entry = c["by_code"].get(code) if c["loaded"] else None
    if entry is None and c["loaded"] and code:
        base = syms.calc_to_md_code(code)
        cands = sorted((e for e in c["by_code"].values() if e.get("base") == base),
                       key=lambda e: e.get("proy", 0))
        entry = cands[0] if cands else None
    charts = []
    if entry is not None:
        for metric, label, scale, unit in (("Last Price", "Precio", 1.0, ""),
                                           ("TIREA", "TIREA", 100.0, "%")):
            vals = (entry.get("vals") or {}).get(metric)
            if not vals:
                continue
            pairs = [(d, v) for d, v in zip(entry["dates"], vals) if v is not None][-dias:]
            sp = _spark(pairs, scale)
            if sp is None:
                continue
            if metric == "Last Price":
                delta = (sp["last"] / sp["first"] - 1.0) * 100.0 if sp["first"] else None
                delta_unit, good_when_up = "%", True
            else:
                delta = sp["last"] - sp["first"]           # ya en puntos de TIR
                delta_unit, good_when_up = " pp", False    # TIR abajo = rally = verde
            def _fmt(iso: str) -> str:
                return f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}" if len(iso) >= 10 else iso
            charts.append({**sp, "label": label, "unit": unit,
                           "d0_fmt": _fmt(sp["d0"]), "d1_fmt": _fmt(sp["d1"]),
                           "delta": delta, "delta_unit": delta_unit,
                           "delta_up": (delta is not None and
                                        ((delta >= 0) == good_when_up))})
    return {"code": code, "dias": dias, "charts": charts,
            "hist_loaded": c["loaded"]}


@router.get("/hist", response_class=HTMLResponse)
async def yas_hist(request: Request, code: str = "", dias: int = 90) -> HTMLResponse:
    """Mini-histórico de la ficha (carga LAZY: la ficha nunca lo espera).
    Datos de la base en memoria; el executor sólo cubre la carga fría del
    Excel en el primer hit tras un boot sin warm."""
    dias = max(10, min(int(dias or 90), 250))
    ctx = await asyncio.get_running_loop().run_in_executor(None, _hist_ctx, code, dias)
    return _render(request, "partials/yas_hist.html", **ctx)
