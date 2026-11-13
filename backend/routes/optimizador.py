"""Optimizador de cartera — subí series históricas y obtené la cartera óptima.

Flujo:
  GET  /optimizador      → página (form de upload + parámetros)
  POST /optimizador/run  → parsea el archivo, corre prior MV / EP-Shannon /
                           q-Tsallis-EP y devuelve el partial de resultado.

El cálculo completo (parseo + pricing de fichas + optimización) es CPU-bound
(decenas de ms a algunos segundos según el panel): corre SIEMPRE en el
threadpool, disparado por el usuario — nunca en un panel live (CLAUDE.md,
target p95 < 50 ms del camino warm; el GET de la página es estático).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from backend.locale_ar import parse_ar_num
from backend.services import cartera_opt

router = APIRouter(prefix="/optimizador", tags=["optimizador"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _error(request: Request, mensaje: str) -> HTMLResponse:
    return _render(request, "partials/optimizador_result.html", error=mensaje)


@router.get("", response_class=HTMLResponse)
async def optimizador_page(request: Request) -> HTMLResponse:
    return _render(request, "optimizador.html")


@router.post("/run", response_class=HTMLResponse)
async def optimizador_run(
    request: Request,
    archivo: UploadFile = File(...),
    invariante: str = Form("tir"),
    ranking: str = Form(""),
    q: str = Form("2"),
    confianza: str = Form("100"),
    max_peso: str = Form("35"),
    delta: str = Form("2,5"),
) -> HTMLResponse:
    data = await archivo.read()
    if len(data) > cartera_opt.MAX_BYTES:
        return _error(request, "El archivo supera el máximo de 5 MB.")

    q_val = parse_ar_num(q)
    conf_val = parse_ar_num(confianza)
    peso_val = parse_ar_num(max_peso)
    delta_val = parse_ar_num(delta)
    if None in (q_val, conf_val, peso_val, delta_val):
        return _error(request, "Revisá los parámetros numéricos (q, confianza, peso máximo, aversión).")

    loop = asyncio.get_running_loop()
    try:
        # CPU-bound (pandas + fichas + SLSQP/L-BFGS-B) → threadpool, como
        # /nueva/parse: en el event loop congelaría los paneles live.
        ctx = await loop.run_in_executor(None, lambda: cartera_opt.run(
            archivo.filename or "",
            data,
            invariante=invariante,
            q=float(q_val),
            confianza=float(conf_val) / 100.0,
            max_peso=float(peso_val) / 100.0,
            delta=float(delta_val),
            ranking_texto=ranking,
        ))
    except ValueError as exc:
        return _error(request, str(exc))
    except Exception:
        import logging
        logging.getLogger("optimizador").exception("optimización falló")
        return _error(request, "La optimización falló por un error interno; está logueado.")
    return _render(request, "partials/optimizador_result.html", **ctx)
