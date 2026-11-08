"""Salud para todos (`/salud`, partial `/salud/body`) y «Qué hay de nuevo»
(`/novedades`). Sólo login (no son pestañas: `auth.can_access_path` deja
pasar a cualquier rol logueado). Las ACCIONES de cada ítem se filtran por lo
que el rol puede abrir (un básico sin Posiciones no ve "Releer carteras")."""
from __future__ import annotations

import asyncio
from datetime import datetime
from itertools import groupby
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import auth, novedades, salud

router = APIRouter(tags=["salud"])
_TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")
REPO_URL = "https://github.com/rodrigocorvalan93/app_calculadoras_bonos"


def _rol(request: Request) -> Optional[str]:
    if getattr(request.state, "is_superuser", False):
        return "superuser"
    u = getattr(request.state, "user", None)
    if u is None:
        return None
    return u.get("role") if isinstance(u, dict) else getattr(u, "role", None)


def _filtrar_acciones(request: Request, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rol = _rol(request)
    for it in items:
        acc, tab = it.get("accion"), it.get("tab")
        if not acc or not tab:
            continue
        if tab == "admin":
            ok = rol == "superuser"
        else:
            ok = auth.can_access_path(rol, acc["href"].split("?", 1)[0])
        if not ok:
            it["accion"] = None
    return items


def _ctx(request: Request) -> Dict[str, Any]:
    items = _filtrar_acciones(request, salud.resumen())
    return {"items": items, "titular": salud.titular(items),
            "hora": datetime.now(_TZ_BA).strftime("%H:%M:%S")}


@router.get("/salud", response_class=HTMLResponse)
async def salud_page(request: Request) -> HTMLResponse:
    ctx = await asyncio.get_running_loop().run_in_executor(None, _ctx, request)
    return request.app.state.templates.TemplateResponse(request, "salud.html", ctx)


@router.get("/salud/body", response_class=HTMLResponse)
async def salud_body(request: Request) -> HTMLResponse:
    ctx = await asyncio.get_running_loop().run_in_executor(None, _ctx, request)
    return request.app.state.templates.TemplateResponse(request, "partials/salud_body.html", ctx)


@router.get("/novedades", response_class=HTMLResponse)
async def novedades_page(request: Request) -> HTMLResponse:
    items = novedades.items()
    grupos = [(fecha, list(g)) for fecha, g in groupby(items, key=lambda it: it["fecha_fmt"])]
    return request.app.state.templates.TemplateResponse(
        request, "novedades.html",
        {"grupos": grupos, "n": len(items), "estado": novedades.estado(),
         "version": novedades.version(), "repo_url": REPO_URL})
