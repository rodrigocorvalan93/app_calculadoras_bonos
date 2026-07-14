"""Alertas de precio/TIR — página + CRUD (sólo superuser).

El gating fuerte está en el middleware de `main` (`/alertas` entero en
`_SUPERUSER_ONLY`); la pestaña además no aparece en la nav de los otros
roles. La tabla es un partial live (md-update + fallback 30 s) que muestra
el valor vigente de cada alerta al lado del umbral — todo lecturas de
store + cache de métricas, sin cómputo nuevo en el request.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.locale_ar import parse_ar_num
from backend.services import alertas as alertas_svc, mailer

router = APIRouter(prefix="/alertas", tags=["alertas"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _disparada_fmt(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except ValueError:
        return iso


def _tabla_ctx(error: Optional[str] = None) -> dict:
    """Sync (correr en executor): current_value puede computar métricas en un
    cache miss (~ms) y no debe bloquear el event loop."""
    rows = []
    for a in alertas_svc.list_alertas():
        cur = None
        try:
            cur = alertas_svc.current_value(a["code"], a["metric"])
        except Exception:  # noqa: BLE001
            cur = None
        rows.append({**a, "actual": cur, "disparada_fmt": _disparada_fmt(a.get("disparada_at"))})
    return {"alertas": rows, "error": error, "smtp_ok": mailer.is_configured()}


@router.get("", response_class=HTMLResponse)
async def alertas_page(request: Request) -> HTMLResponse:
    user = getattr(request.state, "user", None) or {}
    email_default = ""
    if user.get("username"):
        from backend.services import auth
        email_default = (auth.get_user(user["username"]) or {}).get("email", "")
    ctx = await asyncio.get_running_loop().run_in_executor(None, _tabla_ctx)
    return _render(request, "alertas.html", email_default=email_default, **ctx)


@router.get("/tabla", response_class=HTMLResponse)
async def alertas_tabla(request: Request) -> HTMLResponse:
    ctx = await asyncio.get_running_loop().run_in_executor(None, _tabla_ctx)
    return _render(request, "partials/alertas_table.html", **ctx)


@router.post("/crear", response_class=HTMLResponse)
async def alertas_crear(request: Request,
                        code: str = Form(""),
                        metric: str = Form("precio"),
                        op: str = Form(">="),
                        valor: str = Form(""),
                        email: str = Form("")) -> HTMLResponse:
    v = parse_ar_num(valor)
    err = "Valor inválido." if v is None else alertas_svc.add(code, metric, op, v, email)
    ctx = await asyncio.get_running_loop().run_in_executor(None, _tabla_ctx, err)
    return _render(request, "partials/alertas_table.html", **ctx)


@router.post("/borrar", response_class=HTMLResponse)
async def alertas_borrar(request: Request, id: str = Form("")) -> HTMLResponse:
    alertas_svc.delete(id)
    ctx = await asyncio.get_running_loop().run_in_executor(None, _tabla_ctx)
    return _render(request, "partials/alertas_table.html", **ctx)


@router.post("/rearmar", response_class=HTMLResponse)
async def alertas_rearmar(request: Request, id: str = Form("")) -> HTMLResponse:
    alertas_svc.rearm(id)
    ctx = await asyncio.get_running_loop().run_in_executor(None, _tabla_ctx)
    return _render(request, "partials/alertas_table.html", **ctx)
