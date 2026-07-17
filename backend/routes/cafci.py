"""CAFCI — vector de precios de la Cámara Argentina de FCI (búsqueda server-side).

El vector tiene ~6k filas: nunca se renderiza entero. La primera lectura del
Excel (~1-2 s) corre en threadpool para no bloquear el event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import cafci

router = APIRouter(tags=["cafci"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


async def _ctx(q: str) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    rows, total = await loop.run_in_executor(None, cafci.search, q, 200)
    return {"rows": rows, "total": total, "q": q, "status": cafci.status()}


@router.get("/cafci", response_class=HTMLResponse)
async def cafci_page(request: Request, q: str = "") -> HTMLResponse:
    # Shell instantáneo: NO toca ensure_loaded (la 1ª carga del Excel, o el
    # descubrimiento de carpeta en OneDrive, puede tardar). El vector se carga
    # lazy vía htmx (#cafci-body hx-trigger=load) → la pestaña abre al toque y
    # muestra "Cargando…" mientras tanto, nunca se congela.
    return _render(request, "cafci.html", q=q)


@router.get("/cafci/table", response_class=HTMLResponse)
async def cafci_table(request: Request, q: str = "", refresh: bool = False) -> HTMLResponse:
    if refresh:                                  # botón "Actualizar" → relee el Excel
        await asyncio.get_running_loop().run_in_executor(None, cafci.refresh)
        # Si hay token, refresca también el snapshot de la API (VCP fondos).
        from backend.services import cafci_api
        if cafci_api.enabled():
            await asyncio.get_running_loop().run_in_executor(None, cafci_api.refresh)
    return _render(request, "partials/cafci_table.html", **(await _ctx(q)))


@router.get("/cafci/fondos", response_class=HTMLResponse)
async def cafci_fondos(request: Request) -> HTMLResponse:
    """Panel VCP de fondos propios (API CAFCI) — SOLO SUPERUSER: la ruta está
    en _SUPERUSER_ONLY (main) y el div lazy sólo se renderiza para ese rol.
    Lectura de cache pura (~µs), sin executor."""
    from backend.services import cafci_api
    fondos, fecha, error = cafci_api.funds()
    return _render(request, "partials/cafci_fondos.html",
                   fondos=fondos, fecha=fecha, error=error,
                   enabled=cafci_api.enabled())
