"""Tasas (MAE money-market): cauciones + repo.

Lee del snapshot en memoria de `services.mae` (refrescado por el poller),
así que cada endpoint cumple el target sub-50 ms sin tocar la API.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import cauciones as cauc_svc, dolares as dx, mae as mae_svc

router = APIRouter(tags=["tasas"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _ctx() -> Dict[str, Any]:
    return {
        "cauciones": mae_svc.cauciones_rows(),       # MAE
        "byma_cauciones": cauc_svc.byma_rows("PESOS"),  # BYMA $ (store)
        "byma_cauciones_usd": cauc_svc.byma_rows("DOLAR"),  # BYMA US$ (store)
        "repo": mae_svc.repo_rows(),
        "oficial": dx.official_fx(),                 # ref. dólar oficial
        "status": mae_svc.status(),
    }


@router.get("/tasas", response_class=HTMLResponse)
async def tasas_page(request: Request) -> HTMLResponse:
    return _render(request, "tasas.html", **_ctx())


@router.get("/tasas/table", response_class=HTMLResponse)
async def tasas_table(request: Request) -> HTMLResponse:
    """Partial htmx (auto-refresh): cauciones + repo."""
    return _render(request, "partials/tasas_table.html", **_ctx())
