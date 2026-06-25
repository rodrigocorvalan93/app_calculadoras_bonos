"""Escenario multi-activo — comparador de retorno esperado EN PESOS por categoría.

Pantalla on-demand (no live). Para un horizonte y un escenario de salida (Exit
YTM por categoría + pendiente opcional por duration, override por bono) arma, por
cada categoría (Tasa fija / larga, CER corto/medio/largo, DLK, TAMAR, Globales,
Bonares), el total return en pesos descompuesto en Carry + Ganancia de capital,
con overlay de deva CCL/MEP para los hard-dollar. Núcleo en `services.escenario`
(→ `services.total_return._bond_tr` → `rentafija.calcula_total_return`). El cómputo
pesado corre en executor y se cachea por inputs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.cache import LockedTTLCache
from backend.routes.curves import _rows_for, _row_pool
from backend.services import bond_universe, escenario as esc, total_return as tr_svc

router = APIRouter(tags=["escenario"])

_cache = LockedTTLCache(maxsize=32, ttl=20)


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _num(s: Any) -> Optional[float]:
    s = str(s or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None   # rechaza "inf"/"nan"/"1e999"


def _default_terminal() -> str:
    return (date.today() + timedelta(days=120)).strftime("%d/%m/%Y")


def _parse_d(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def _a3500_drift(settle: str, terminal: str) -> float:
    """Deva oficial implícita (A3500 proyectado, futuros ROFEX) entre settle y
    terminal — semilla editable para la deva CCL/MEP del escenario."""
    sd, td = _parse_d(settle), _parse_d(terminal)
    if not sd or not td:
        return 0.0

    class _O:
        ajuste_sobre_capital = "A3500"
        dias_lag_ajuste_base = -10

    try:
        return float(tr_svc._index_drift(_O(), sd, td))
    except Exception:  # noqa: BLE001
        return 0.0


def _cauc_al_plazo(tna: float, dias: int) -> float:
    """Caución 'al plazo' por capitalización diaria de la TNA (roll 1 día)."""
    if dias <= 0:
        return 0.0
    return (1.0 + tna / 365.0) ** dias - 1.0


async def _cat_rows(cat: esc.Cat, plazo: str) -> List[Dict[str, Any]]:
    """Filas de la curva de la categoría filtradas al bucket de duration y a
    bonos con TIREA + duration válidas."""
    rows, _meta = await _rows_for(cat.curve, plazo)
    return [r for r in rows
            if r.get("tirea") is not None and r["tirea"] == r["tirea"]
            and esc.in_bucket(cat, r.get("duration"))]


@router.get("/escenario", response_class=HTMLResponse)
async def escenario_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    terminal = _default_terminal()
    settle = tr_svc.settle_str(plazo)
    dias = ((_parse_d(terminal) - _parse_d(settle)).days
            if (_parse_d(terminal) and _parse_d(settle)) else 0)
    deva = _a3500_drift(settle, terminal)
    cauc_tna = 0.20
    cats: List[Dict[str, Any]] = []
    for cat in esc.CATEGORIES:
        rows = await _cat_rows(cat, plazo)
        ytm = esc._avg([r.get("tirea") for r in rows])
        cats.append({"key": cat.key, "label": cat.label, "fx": cat.fx,
                     "n": len(rows), "ytm": ytm})
    return _render(request, "escenario.html", cats=cats, terminal=terminal, plazo=plazo,
                   settle=settle, dias=dias, deva_pct=deva * 100.0,
                   cauc_tna_pct=cauc_tna * 100.0, anchor=1.0)


def _per_cat_params(request: Request) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Lee ytm_<key> (TIREA %) y slope_<key> (bps/año) por categoría del query."""
    ytm: Dict[str, float] = {}
    slope: Dict[str, float] = {}
    for k, v in request.query_params.items():
        if k.startswith("ytm_"):
            n = _num(v)
            if n is not None:
                ytm[k[4:]] = n / 100.0
        elif k.startswith("slope_"):
            n = _num(v)
            if n is not None:
                slope[k[6:]] = n
    return ytm, slope


@router.get("/escenario/table", response_class=HTMLResponse)
async def escenario_table(
    request: Request,
    plazo: str = "24hs", terminal: str = "",
    cauc_tna: str = "", cauc_plazo: str = "",
    ccl_deva: str = "", mep_deva: str = "",
    anchor: str = "", use_manual: str = "",
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    terminal = (terminal or "").strip() or _default_terminal()
    settle = tr_svc.settle_str(plazo)
    sd, td = _parse_d(settle), _parse_d(terminal)
    dias = (td - sd).days if (sd and td) else 0

    deva_default = _a3500_drift(settle, terminal)
    ccl_proy = (_num(ccl_deva) / 100.0) if _num(ccl_deva) is not None else deva_default
    mep_proy = (_num(mep_deva) / 100.0) if _num(mep_deva) is not None else deva_default
    # Caución 'al plazo': directa si la editan, si no derivada de la TNA.
    tna = (_num(cauc_tna) / 100.0) if _num(cauc_tna) is not None else 0.20
    cauc = (_num(cauc_plazo) / 100.0) if _num(cauc_plazo) is not None \
        else _cauc_al_plazo(tna, dias)
    anchor_f = _num(anchor) if _num(anchor) is not None else 1.0

    ytm_by_cat, slope_by_cat = _per_cat_params(request)
    overrides: Dict[str, float] = {}
    if use_manual == "1":
        for k, v in request.query_params.items():
            if k.startswith("y1__"):
                n = _num(v)
                if n is not None:
                    overrides[k[4:]] = n / 100.0

    # Reúno filas + TIR de salida por categoría (async, fuera del executor).
    prepared: List[Tuple[esc.Cat, List[Dict[str, Any]], Dict[str, float], float]] = []
    for cat in esc.CATEGORIES:
        rows = await _cat_rows(cat, plazo)
        level = ytm_by_cat.get(cat.key)
        if level is None:                      # sin input → mantiene la TIR actual (carry puro)
            level = esc._avg([r.get("tirea") for r in rows]) or 0.0
        slope = slope_by_cat.get(cat.key, 0.0)
        y1_map: Dict[str, float] = {}
        for r in rows:
            code, dur = r.get("code"), r.get("duration")
            if not code:
                continue
            if code in overrides:
                y1_map[code] = overrides[code]
            elif dur is not None and dur == dur:
                y1_map[code] = esc.exit_ytm(level, slope, dur, anchor_f)
        prepared.append((cat, rows, y1_map, esc.fx_of(cat, ccl_proy, mep_proy)))

    sig = {c.key: {r["code"]: [round(r.get("tirea") or 0, 6), round(y1m.get(r["code"], 0), 6)]
                   for r in rows if r.get("code")}
           for (c, rows, y1m, _fx) in prepared}
    key = (plazo, terminal, settle, round(ccl_proy, 6), round(mep_proy, 6), round(cauc, 6),
           hashlib.md5(json.dumps(sig, sort_keys=True).encode()).hexdigest())

    def _compute() -> List[Dict[str, Any]]:
        return [esc.compute_category(cat, rows, y1m, fx, ccl_proy, cauc, terminal, settle)
                for (cat, rows, y1m, fx) in prepared]

    loop = asyncio.get_running_loop()
    cats = await loop.run_in_executor(_row_pool, lambda: _cache.get_or_compute(key, _compute))
    chart = esc.chart_from_categories(cats)

    tea = (1.0 + tna / 365.0) ** 365 - 1.0
    return _render(request, "partials/escenario_table.html",
                   cats=cats, chart=chart, terminal=terminal, settle=settle, dias=dias,
                   ccl_proy=ccl_proy, mep_proy=mep_proy, cauc=cauc, tna=tna, tea=tea)
