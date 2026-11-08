"""Preferencias de interfaz por usuario: GET /prefs (JSON) y POST /prefs
(JSON con las claves que cambiaron; `null` borra). Las sincroniza `app.js`
con el localStorage del navegador. Sólo login; el bucket es el username (o
`_local` sin muro, como la pizarra)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.services import prefs as prefs_svc

router = APIRouter(tags=["prefs"])


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None) or {}
    return str(u.get("username") or "_local") if isinstance(u, dict) else str(getattr(u, "username", "") or "_local")


@router.get("/prefs")
async def prefs_get(request: Request) -> JSONResponse:
    user = _user(request)
    data = await asyncio.get_running_loop().run_in_executor(None, prefs_svc.load_user, user)
    return JSONResponse({"user": user, "prefs": data}, headers={"Cache-Control": "no-store"})


@router.post("/prefs")
async def prefs_post(request: Request) -> JSONResponse:
    try:
        body: Dict[str, Any] = await request.json()
    except ValueError:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)
    if not isinstance(body, dict) or len(body) > 64:
        return JSONResponse({"error": "se espera un objeto chico {clave: valor}"}, status_code=400)
    user = _user(request)
    try:
        data = await asyncio.get_running_loop().run_in_executor(None, prefs_svc.set_user, user, body)
    except OSError as exc:
        return JSONResponse({"error": f"no se pudo guardar: {exc}"}, status_code=503)
    return JSONResponse({"user": user, "prefs": data}, headers={"Cache-Control": "no-store"})
