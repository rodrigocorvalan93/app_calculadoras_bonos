"""Barra de activos (tape) — strip superior con lo esencial del día.

3 tasa fija + 3 CER + 3 globales (top por volumen del store) · A3500 · MEP ·
CCL · Merval en USD · EWZ y SPY "vistos en cable". Todo sale de caches en
memoria (store WS + fx + dólar oficial): el render warm es ~1 ms y se
refresca por md-update (sólo con ticks reales), así que no agrega carga.

Variación cable (CEDEARs / Merval USD):
    var_cable = (1 + var_ars) / (1 + var_ccl) − 1
con var_ccl = variación del CCL implícito vs cierre (de dx.summary).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import curves, dolares as dx, equities, fx as fx_svc, marketdata_store as mds, symbols as syms

router = APIRouter(tags=["tape"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _var(last: Optional[float], close: Optional[float]) -> Optional[float]:
    if last is None or close in (None, 0):
        return None
    return last / close - 1.0


def _top_bonds(curve_key: str, plazo: str, n: int = 3, strip_c: bool = False) -> List[Dict[str, Any]]:
    """Top-N por volumen nominal del store (puro lookup, sin pricing)."""
    store = mds.get_store()
    cands = []
    for code in curves.build_curve_codes().get(curve_key, []):
        base = code[:-1] if (strip_c and code.endswith("C")) else code   # globales: GD30C → GD30 (pata ARS)
        snap = store.get(syms.md_symbol(base, plazo))
        if snap is None or snap.last is None:
            continue
        cands.append((snap.nominal or 0.0, base, snap.last, _var(snap.last, snap.close)))
    cands.sort(reverse=True)
    return [{"code": c, "px": px, "var": v, "kind": "ars"} for _, c, px, v in cands[:n]]


def _items(plazo: str = "24hs") -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    items += _top_bonds("lecap", plazo)
    items += _top_bonds("cer", plazo)
    items += _top_bonds("globales", plazo, strip_c=True)

    # FX: oficial + MEP + CCL (var en pp ya calculada por dolares/fx).
    of = dx.official_fx()
    if of.get("last") is not None:
        items.append({"code": "A3500", "px": of["last"], "var": of.get("var_pct"), "kind": "fx"})
    summ = dx.summary(plazo)
    ccl_var = None
    for key, label in (("usb", "MEP"), ("usd", "CCL")):
        leg = summ.get(key) or {}
        if leg.get("last") is not None:
            # summary.var_pct viene en FRACCIÓN (0.004 = 0,4%), igual que en el
            # riel (que la renderiza con ar_pct ×100). No convertir.
            v = leg.get("var_pct")
            v = v if isinstance(v, (int, float)) else None
            items.append({"code": label, "px": leg["last"], "var": v, "kind": "fx"})
            if key == "usd":
                ccl_var = v
    fxq = fx_svc.get_fx(plazo)
    ccl = (summ.get("usd") or {}).get("last") or (getattr(fxq, "ccl", None) if fxq else None)

    def _cable(var_ars: Optional[float]) -> Optional[float]:
        if var_ars is None or ccl_var is None:
            return None
        return (1.0 + var_ars) / (1.0 + ccl_var) - 1.0

    # Merval: nivel en US$ (último / CCL) + variación en $ Y en US$.
    msnap = equities.merval_snapshot()
    if msnap is not None and msnap.last is not None and ccl:
        var_ars = _var(msnap.last, msnap.close)
        items.append({"code": "MERVAL US$", "px": msnap.last / ccl,
                      "var": _cable(var_ars), "var_ars": var_ars, "kind": "usd"})
    # EWZ / SPY vistos en cable (precio ARS/CCL; var ajustada por CCL).
    for code in ("EWZ", "SPY"):
        r = equities.row_for(code, plazo)
        if r and r.get("last") is not None and ccl:
            var_ars = (r["var_pct"] / 100.0) if r.get("var_pct") is not None else None
            items.append({"code": f"{code} US$", "px": r["last"] / ccl,
                          "var": _cable(var_ars), "kind": "usd"})
    return items


@router.get("/tape", response_class=HTMLResponse)
async def tape(request: Request, plazo: str = "24hs") -> HTMLResponse:
    return _render(request, "partials/tape.html", items=_items(plazo))


@router.get("/news/marquee", response_class=HTMLResponse)
async def news_marquee(request: Request) -> HTMLResponse:
    """Marquesina de titulares (lee el cache del poller; costo ~0)."""
    from backend.services import news
    return _render(request, "partials/news_marquee.html", items=news.items())
