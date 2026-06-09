"""Análisis de créditos — scoring crediticio corporativo + detalle por emisor
con las métricas live de sus ONs. Lee todo de cache (credit_scores.json + store).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from backend.services import credito, marketdata_store, pricing, symbols as syms

router = APIRouter(tags=["creditos"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _table_ctx(sector: List[str], score_min: float, solo_ons: bool) -> Dict[str, Any]:
    sec = [s for s in (sector or []) if s]
    return {
        "rows": credito.issuers(sec or None, score_min, solo_ons),
        "sectors": credito.sectors(),
        "status": credito.status(),
        "sector": sec, "score_min": score_min, "solo_ons": solo_ons,
    }


@router.get("/creditos", response_class=HTMLResponse)
async def creditos_page(
    request: Request,
    sector: List[str] = Query(default=[]),
    score_min: float = 1.0,
    solo_ons: bool = False,
) -> HTMLResponse:
    return _render(request, "creditos.html", **_table_ctx(sector, score_min, solo_ons))


@router.get("/creditos/table", response_class=HTMLResponse)
async def creditos_table(
    request: Request,
    sector: List[str] = Query(default=[]),
    score_min: float = 1.0,
    solo_ons: bool = False,
) -> HTMLResponse:
    return _render(request, "partials/creditos_table.html", **_table_ctx(sector, score_min, solo_ons))


@router.get("/creditos/detail", response_class=HTMLResponse)
async def creditos_detail(request: Request, ticker: str = "") -> HTMLResponse:
    """Ficha del emisor + sus ONs con métricas live (TIREA/TNA/Duration/Paridad)."""
    d = credito.detail(ticker)
    store = marketdata_store.get_store()
    bonds: List[Dict[str, Any]] = []
    for bc in d.get("bonds", []):
        snap = store.get(syms.md_symbol(bc, "24hs"))
        last = snap.last if snap else None
        m = pricing.metrics_for_market_price(bc, last) if last is not None else None
        bonds.append({
            "code": bc, "last": last,
            "tirea": (m or {}).get("tirea"), "tna": (m or {}).get("tna"),
            "duration": (m or {}).get("duration"), "paridad": (m or {}).get("paridad"),
            "nombre": (pricing.bond_meta(bc) or {}).get("nombre"),
        })
    return _render(request, "partials/creditos_detail.html",
                   ticker=ticker, credit=d.get("credit") or {}, bonds=bonds)
