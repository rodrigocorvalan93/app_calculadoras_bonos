"""YAS routes — Análisis de Yields.

Layout:
- GET  /yas                      → full page (selectbox + form + result panel)
- POST /yas/recompute            → HTML partial with metrics + ticket + cashflows
- GET  /yas/ficha                → ficha estática del instrumento (sin precio)
- GET  /yas/market               → panel de mercado (bid / last / offer / OHLC)

Estados del resultado (rediseño 30/10): `vacio` (sin valor: ficha y mercado
visibles, zona de resultados neutra, sin rojos), `invalido` (aviso pegado al
campo vía OOB, resultados neutros: nunca quedan números de un valor anterior)
y `ok`. El valor crudo del autofill viaja en `value_raw` (precisión completa
del mercado) mientras el input muestra 4 decimales; en cuanto el usuario
edita, Alpine lo vacía y vale lo tipeado.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.cache import AsyncSingleFlight
from backend.config import settings
from backend.locale_ar import parse_ar_num
from backend.services import auth as auth_svc, bond_universe, curves as curves_svc, delta_especies, marketdata_store, positions, pricing, symbols as syms
from backend.cache_seq import seq_cached

router = APIRouter(prefix="/yas", tags=["yas"])


def _parse_ar_number(raw: Optional[str]) -> Optional[float]:
    """Parser es-AR canónico (puntos = miles, coma = decimal). Antes era una copia
    propia que sólo sacaba los puntos si había coma → un VN/precio con miles
    ('2.000.000', '500.000') daba None y caía al default 1.000.000 sin avisar."""
    return parse_ar_num(raw)


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template, ctx)


# Single-flight de recálculos IDÉNTICOS en vuelo (auditoría R10): N usuarios
# pidiendo el mismo bono / modo / valor / settle / VN al mismo tiempo → UN
# cálculo en el pool; los demás esperan ese mismo Future (cache.AsyncSingleFlight,
# el mismo helper de Escenario / Total Return). Sólo se comparte el cálculo
# (métricas + ticket, de sólo lectura en el template); la tenencia por fondos
# visibles y el render siguen por request. Costo: un lookup de dict.
_INFLIGHT = AsyncSingleFlight()


def _single_flight(key: tuple, fn) -> "asyncio.Future":
    return _INFLIGHT.run(key, None, fn)


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
    # Autofill por defecto: último precio del activo seleccionado (modo precio),
    # convertido al basis de la ficha (una especie pesos de hard-dollar — GD30,
    # AL30, …O — divide por el FX de pago; antes el last ARS crudo entraba a la
    # ficha en dólares y el autofill precargaba un precio 1500×). El input
    # muestra 4 decimales; el crudo viaja en `value_raw` (precisión completa).
    last = pricing.market_last_native(selected, settings.default_plazo)
    default_value = "" if last is None else _fmt_input(last)
    default_raw = "" if last is None else repr(float(last))
    return _render(
        request,
        "yas.html",
        codes=codes,
        selected=selected,
        meta=pricing.bond_meta(selected),
        plazo=settings.default_plazo,
        settle=pricing.settlement_date_str(settings.default_plazo),
        default_value=default_value,
        default_raw=default_raw,
    )


def _fmt_input(v: float) -> str:
    """Valor para MOSTRAR en el input: es-AR, hasta 4 decimales sin ceros de
    más (70.633307 → '70,6333'; 100.0 → '100'; 0.14 → '0,14')."""
    txt = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return txt.replace(".", ",")


def _valor_efectivo(value: str, value_raw: str) -> tuple[Optional[float], str]:
    """(valor numérico, estado) del form: `value_raw` (crudo del autofill, lo
    vacía Alpine al editar) gana sobre `value` si ambos parsean y coinciden a
    4 decimales — así el cálculo conserva la precisión del mercado sin mostrar
    un número de 6-8 decimales. Estados: 'vacio' | 'invalido' | 'ok'."""
    v = _parse_ar_number(value)
    if v is None:
        return None, ("vacio" if not (value or "").strip() else "invalido")
    raw = _parse_ar_number(value_raw) if (value_raw or "").strip() else None
    if raw is not None and abs(round(raw, 4) - round(v, 4)) < 1e-9:
        return raw, "ok"
    return v, "ok"


@router.get("/ficha", response_class=HTMLResponse)
async def yas_ficha(request: Request, code: str = "", plazo: str = "24hs") -> HTMLResponse:
    """Ficha estática del instrumento (identificación, convenciones, rescate
    anticipado). Sólo `bond_meta` (memoizado) + la fecha de liquidación del
    plazo: no depende del precio, así que se ve aunque no haya valor ni
    cotización. La pide el form al cambiar de bono o de plazo (no en cada
    tecleo: el recompute ya no la re-renderiza por OOB como el strip viejo)."""
    code = bond_universe.resolve(code) or code
    return _render(request, "partials/yas_ficha.html",
                   meta=pricing.bond_meta(code), plazo=plazo,
                   settle=pricing.settlement_date_str(plazo))


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
    bench_override: str = Form(""),
    value_raw: str = Form(""),
) -> HTMLResponse:
    parsed_value, estado = _valor_efectivo(value, value_raw)
    parsed_nom = _parse_ar_number(nominales) or 1_000_000.0
    parsed_fx = _parse_ar_number(fx_override)
    parsed_freq = _parse_ar_number(freq_override)
    parsed_base = _parse_ar_number(base_override)
    parsed_bench = _parse_ar_number(bench_override)        # TAMAR/BADLAR custom (TNA %)

    if parsed_value is None:
        # Sin valor / inválido: zona de resultados neutra (sin rojos ni tarjetas
        # vacías) + aviso pegado al campo (OOB). Sin cálculo ni ticket.
        return _render(
            request,
            "partials/yas_result.html",
            estado=estado,
            metrics={},
            ticket={},
            meta=pricing.bond_meta(code),
            mode=mode,
            hint=_hint(mode, estado, None, value_raw),
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
            bench_override=parsed_bench,
        )
        return m, pricing.ticket_rows(m, nominales=parsed_nom)

    key = (code, mode, parsed_value, settle, parsed_nom, parsed_fx, parsed_freq, parsed_base, parsed_bench)
    metrics, ticket = await _single_flight(key, _calc)
    return _render(
        request,
        "partials/yas_result.html",
        estado="ok",
        metrics=metrics,
        curve_key=curves_svc.curve_key_for(code),
        curve_label=(curves_svc.curve_def(curves_svc.curve_key_for(code) or "") or None) and curves_svc.curve_def(curves_svc.curve_key_for(code)).label,
        ticket=ticket,
        meta=pricing.bond_meta(code),
        mode=mode,
        hint=_hint(mode, "ok", parsed_value, value_raw, metrics),
        # tenencia filtrada por los fondos visibles del usuario (None = todos)
        position=positions.position_for(code, auth_svc.visible_fondos_for(request)),
        especie=delta_especies.info(code),
    )


def _hint(mode: str, estado: str, value: Optional[float], value_raw: str,
          metrics: Optional[dict] = None) -> dict:
    """Línea de ayuda bajo el campo editable (OOB en cada recompute): qué
    valor entró y de dónde. `cls` = '' | 'is-invalid' | 'is-empty'."""
    if estado == "invalido":
        return {"cls": "is-invalid", "text": "No es un número · usá coma decimal, ej. 87,30"}
    if estado == "vacio":
        return {"cls": "is-empty", "text": "sin valor · ingresá uno a mano o elegí un bono con cotización"}
    raw = (value_raw or "").strip()
    if mode == "precio":
        if raw and value is not None and abs(value - round(value, 4)) > 1e-9:
            return {"cls": "", "text": f"del mercado · precisión interna {str(value).replace('.', ',')}"}
        return {"cls": "", "text": "del mercado" if raw else "manual"}
    if value is None:
        return {"cls": "", "text": ""}
    from backend.locale_ar import fmt_pct
    if mode == "tir":
        return {"cls": "", "text": f"= {fmt_pct(value, 2)} efectiva anual"}
    if mode == "tna":
        return {"cls": "", "text": f"= {fmt_pct(value, 2)} nominal anual"}
    if mode == "margen":
        return {"cls": "", "text": f"= {fmt_pct(value, 2)} sobre el benchmark"}
    return {"cls": "", "text": ""}


@router.post("/tr", response_class=HTMLResponse)
async def yas_tr(
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
    bench_override: str = Form(""),
    tasa_salida: str = Form(""),
    fecha_salida: str = Form(""),
    value_raw: str = Form(""),
) -> HTMLResponse:
    """Total return puntual de la ficha: entrada al estado actual del form YAS
    (hx-include), salida a `tasa_salida` (TIREA decimal; vacío = flat) en
    `fecha_salida` (DD/MM/AAAA; vacío = settle + 90 días). GIL-bound → pool."""
    parsed_value, estado = _valor_efectivo(value, value_raw)
    parsed_nom = _parse_ar_number(nominales) or 1_000_000.0
    parsed_fx = _parse_ar_number(fx_override)
    parsed_freq = _parse_ar_number(freq_override)
    parsed_base = _parse_ar_number(base_override)
    parsed_bench = _parse_ar_number(bench_override)
    parsed_salida = _parse_ar_number(tasa_salida)

    if parsed_value is None:
        # Sin valor en la ficha: estado neutro (no es un error del TR).
        return _render(request, "partials/yas_tr.html",
                       tr={"vacio": True, "estado": estado},
                       tasa_salida=tasa_salida, fecha_salida=fecha_salida)

    settle = settle_custom.strip() or pricing.settlement_date_str(plazo)

    def _calc():
        return pricing.tr_puntual(
            code=code, mode=mode, value=parsed_value, settle=settle,
            tir_salida=parsed_salida, fecha_salida=fecha_salida.strip() or None,
            nominales=parsed_nom, fx_override=parsed_fx,
            freq_override=int(parsed_freq) if parsed_freq else None,
            base_override=int(parsed_base) if parsed_base else None,
            bench_override=parsed_bench,
        )

    tr = await asyncio.get_running_loop().run_in_executor(None, _calc)
    return _render(request, "partials/yas_tr.html", tr=tr,
                   tasa_salida=tasa_salida, fecha_salida=fecha_salida)


@router.get("/market", response_class=HTMLResponse)
@seq_cached(ttl=2.0)
async def yas_market_card(
    request: Request,
    code: str = "",
    plazo: str = "24hs",
    mode: str = "precio",
    value: str = "",
    value_raw: str = "",
) -> HTMLResponse:
    """HTMX partial — bid / offer / last / OHLC for a bond from the store.

    El `code` viene por query (hx-include del form), no en la URL — así el
    panel sigue al bono seleccionado en vez de quedar fijo al inicial. `mode`
    / `value` sólo deciden el tag «en uso» del Last (modo precio y el valor de
    la ficha = el último convertido al basis de la ficha).
    """
    store = marketdata_store.get_store()
    symbol = syms.md_symbol(code, plazo) if code else ""
    snap = store.get(symbol) if symbol else None
    en_uso = False
    if snap is not None and mode == "precio" and getattr(snap, "last", None) is not None:
        v, _ = _valor_efectivo(value, value_raw)
        nat = pricing.market_last_native(code, plazo) if v is not None else None
        en_uso = nat is not None and abs(round(nat, 4) - round(v, 4)) < 1e-9
    return _render(
        request,
        "partials/yas_market_card.html",
        snap=snap.to_dict() if snap else None,
        symbol=symbol,
        code=code,
        plazo=plazo,
        en_uso=en_uso,
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
