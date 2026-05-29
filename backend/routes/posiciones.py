"""Posiciones / matriz de tenencias.

Sirve desde el cache de `services.positions` (cargado una vez al inicio;
`?refresh=1` fuerza relectura). Enriquece cada tenencia con métricas vivas
(TIREA / TNA / Duration / last) reutilizando el motor de curvas, matcheando
Cod_Delta ↔ ticker del universo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.routes.curves import _row_for_code
from backend.services import bond_universe, positions

router = APIRouter(tags=["posiciones"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _enrich(hs: List[Dict[str, Any]], pn: Optional[float], plazo: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for h in hs:
        code = h.get("cod_delta")
        m = _row_for_code(code, plazo) if code else None  # None si no está en el universo
        valor = h.get("valor")
        rows.append({
            **h,
            "in_universe": m is not None,
            "pct_pn": (valor / pn) if (valor is not None and pn and pn > 0) else None,
            "tirea": (m or {}).get("tirea"),
            "tna": (m or {}).get("tna"),
            "tna_convention_label": (m or {}).get("tna_convention_label"),
            "duration": (m or {}).get("duration"),
            "last": (m or {}).get("last"),
            "price_source": (m or {}).get("price_source"),
            "moneda": (m or {}).get("moneda"),
        })
    rows.sort(key=lambda r: (r.get("valor") or 0.0), reverse=True)
    return rows


@router.get("/posiciones", response_class=HTMLResponse)
async def posiciones_page(
    request: Request,
    fondo: Optional[int] = None,
    plazo: str = "24hs",
    refresh: bool = False,
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    if refresh:
        positions.refresh()
    fs = positions.fondos()
    st = positions.status()
    selected = fondo if (fondo is not None and any(f["cod"] == fondo for f in fs)) \
        else (fs[0]["cod"] if fs else None)
    pn = positions.pn_of(selected) if selected is not None else None
    rows = _enrich(positions.holdings(selected), pn, plazo) if selected is not None else []
    total_valor = sum((r.get("valor") or 0.0) for r in rows)
    return _render(
        request, "posiciones.html",
        fondos=fs, selected=selected, rows=rows, pn=pn, total_valor=total_valor,
        plazo=plazo, status=st,
        nombre=positions.fondo_label(selected) if selected is not None else "",
    )


@router.get("/posiciones/table", response_class=HTMLResponse)
async def posiciones_table(request: Request, fondo: int, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    pn = positions.pn_of(fondo)
    rows = _enrich(positions.holdings(fondo), pn, plazo)
    total_valor = sum((r.get("valor") or 0.0) for r in rows)
    return _render(
        request, "partials/posiciones_table.html",
        rows=rows, pn=pn, total_valor=total_valor, fondo=fondo, plazo=plazo,
        nombre=positions.fondo_label(fondo),
    )


@router.get("/posiciones/matriz", response_class=HTMLResponse)
async def posiciones_matriz(request: Request) -> HTMLResponse:
    bond_universe.ensure_loaded()
    c = positions.ensure_loaded()
    fs = positions.fondos()
    esps: Dict[str, Dict[int, float]] = {}
    for h in c["holdings"]:
        e = h.get("cod_delta") or h.get("especie")
        if not e:
            continue
        d = esps.setdefault(e, {})
        d[h["cod_fondo"]] = (d.get(h["cod_fondo"]) or 0.0) + (h.get("valor") or 0.0)
    rows = []
    for e, byf in sorted(esps.items(), key=lambda kv: -sum(kv[1].values())):
        cells = [{
            "valor": byf.get(f["cod"]),
            "pct": (byf.get(f["cod"]) / f["pn"]) if (byf.get(f["cod"]) and f.get("pn")) else None,
        } for f in fs]
        rows.append({"especie": e, "cells": cells, "total": sum(byf.values())})
    return _render(request, "partials/posiciones_matriz.html", fondos=fs, rows=rows)
