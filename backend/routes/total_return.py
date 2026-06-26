"""Total Return — pantalla on-demand (no live).

Dada una curva, una fecha terminal y una curva de salida (TIR target por bono
en 3 modos: paramétrica nivel/pendiente/convexidad, NSS completo, o puntos
interpolados, con override manual por fila), arma la tabla de total return con
la descomposición carry + compresión + ajuste, reusando
`services.total_return` (núcleo = rentafija.calcula_total_return). El cómputo es
pesado (regenera cashflows por bono) → corre en executor y se cachea.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.locale_ar import parse_ar_num
from backend.routes.curves import _rows_for, _row_pool
from backend.services import bond_universe, curves, total_return as tr_svc

router = APIRouter(tags=["total-return"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _num(s: Any) -> Optional[float]:
    return parse_ar_num(s)            # parser es-AR canónico (maneja miles + rechaza inf/nan)


def _default_terminal() -> str:
    return (date.today() + timedelta(days=120)).strftime("%d/%m/%Y")


async def _nss_defaults(curve: str, plazo: str) -> Optional[Dict[str, Any]]:
    """Params NSS de la curva (para autocompletar nivel/pendiente/convexidad)."""
    from backend.services import nss
    rows, _ = await _rows_for(curve, plazo)
    pts = [(r["duration"], r["tirea"] * 100.0) for r in rows
           if r.get("duration") and r["duration"] == r["duration"]
           and r.get("tirea") is not None and r["tirea"] == r["tirea"]]
    if len(pts) < 4:
        return None
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, nss.params, [a for a, _ in pts], [b for _, b in pts])


@router.get("/total-return", response_class=HTMLResponse)
async def total_return_page(request: Request, curve: str = "", plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    all_curves = curves.list_curves()
    table = curves.build_curve_codes()
    selected = curve if (curve and curve in table) else \
        next((c.key for c in all_curves if table.get(c.key)), None)
    nss = await _nss_defaults(selected, plazo) if selected else None
    return _render(request, "total_return.html", all_curves=all_curves, table=table,
                   selected_key=selected, plazo=plazo, terminal=_default_terminal(), nss=nss)


def _y1_by_code(rows: List[Dict[str, Any]], mode: str, p: Dict[str, Any],
                overrides: Dict[str, float]) -> Dict[str, float]:
    """TIR de salida (decimal) por código según el modo; los overrides manuales
    (y1__CODE) siempre ganan."""
    durs = np.array([(r.get("duration") or np.nan) for r in rows], dtype="float64")
    if mode == "nss" and p.get("popt"):
        y = tr_svc.scenario_nss(durs, p["popt"])
    elif mode == "points" and p.get("points"):
        y = tr_svc.scenario_points(durs, p["points"])
    else:  # params (default)
        y = tr_svc.scenario_params(durs, p.get("level", 0.0), p.get("slope", 0.0),
                                   p.get("convex", 0.0), p.get("anchor", 1.0))
    out: Dict[str, float] = {}
    for r, yi in zip(rows, y):
        code = r.get("code")
        if not code:
            continue
        if code in overrides:
            out[code] = overrides[code]
        elif yi == yi:                      # no NaN
            out[code] = float(yi)
    return out


@router.get("/total-return/table", response_class=HTMLResponse)
async def total_return_table(
    request: Request,
    curve: str = "", plazo: str = "24hs", terminal: str = "",
    mode: str = "params",
    level: str = "", slope: str = "", convex: str = "", anchor: str = "",
    b0: str = "", b1: str = "", b2: str = "", b3: str = "", t1: str = "", t2: str = "",
    points: str = "",
    use_manual: str = "",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    terminal = (terminal or "").strip() or _default_terminal()
    settle = tr_svc.settle_str(plazo)

    rows, _meta = await _rows_for(curve, plazo)
    rows = [r for r in rows if r.get("tirea") is not None and r["tirea"] == r["tirea"]
            and r.get("duration") and r["duration"] == r["duration"]]

    # Params del modo elegido.
    p: Dict[str, Any] = {
        "level": _num(level) or 0.0, "slope": _num(slope) or 0.0,
        "convex": _num(convex) or 0.0, "anchor": _num(anchor) or 1.0,
    }
    if mode == "nss":
        popt = [_num(x) for x in (b0, b1, b2, b3, t1, t2)]
        p["popt"] = popt if all(v is not None for v in popt) else None
    if mode == "points":
        pts = []
        for ln in (points or "").replace(";", "\n").splitlines():
            parts = [x.strip() for x in ln.replace("\t", ",").split(",")]
            if len(parts) >= 2 and _num(parts[0]) is not None and _num(parts[1]) is not None:
                pts.append((_num(parts[0]), _num(parts[1])))
        p["points"] = pts

    # Overrides manuales por fila (y1__CODE = TIR % editada en la tabla). Sólo se
    # toman si el usuario pidió recalcular con sus tasas (use_manual=1).
    overrides: Dict[str, float] = {}
    if use_manual == "1":
        for k, v in request.query_params.items():
            if k.startswith("y1__"):
                n = _num(v)
                if n is not None:
                    overrides[k[4:]] = n / 100.0

    y1_map = _y1_by_code(rows, mode, p, overrides)

    # Cómputo pesado en executor; cacheado por inputs.
    key = (curve, plazo, terminal, settle, mode,
           hashlib.md5(json.dumps({"p": {k: p.get(k) for k in ("level", "slope", "convex", "anchor", "popt", "points")},
                                   "ov": overrides, "codes": [r["code"] for r in rows]},
                                  default=str, sort_keys=True).encode()).hexdigest())

    def _compute():
        return tr_svc.compute_rows(rows, terminal, settle, y1_map)

    loop = asyncio.get_running_loop()
    tr_rows, dias = await loop.run_in_executor(
        _row_pool, lambda: _cached_or(key, _compute))

    chart = tr_svc.chart_from_tr_rows(tr_rows)
    ycurve = tr_svc.curve_chart(tr_rows)
    return _render(request, "partials/total_return_table.html",
                   rows=tr_rows, dias=dias, terminal=terminal, settle=settle,
                   curve=curve, mode=mode, chart=chart, ycurve=ycurve)


def _cached_or(key, fn):
    return tr_svc._cache.get_or_compute(key, fn)
