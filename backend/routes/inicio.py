"""Inicio — página de aterrizaje de la app (07/10).

Resumen del mercado en una pantalla: tipos de cambio, tasas, Merval / riesgo
país / CEDEARs de referencia, soberanos por segmento (último · var · var % ·
TIR · Δ TIR · TEM · margen), panel líder y futuros de dólar. UNA request live
por tick (`/inicio/body`, `md-update` + respaldo 30 s) para toda la página,
cacheada por seq del store (`seq_cached`: N pestañas comparten el render) —
las filas de bonos salen del MISMO cache por curva y seq que Mercado / Curvas
(`routes.curves._rows_en_seq`), así que con Mercado abierto en otra pestaña el
costo marginal es el Jinja; el resto son lookups en memoria
(`services.inicio`). Nada de acá toca red ni disco.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.cache_seq import seq_cached
from backend.routes.curves import _row_for_code, _row_pool, _rows_en_seq, book_context
from backend.services import bond_universe, inicio as inicio_svc, marketdata_store, pizarra as piz_svc, pricing

logger = logging.getLogger("backend.inicio.routes")

router = APIRouter(tags=["inicio"])

_PLAZO = "24hs"


def _render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _user(request: Request) -> str:
    """Bucket del usuario para la pizarra: la sesión, o "_local" sin muro de
    login (mismo pseudo-usuario que escenario / órdenes)."""
    u = getattr(request.state, "user", None) or {}
    return str(u.get("username") or "_local")


async def _filas_curvas() -> Dict[str, List[dict]]:
    """Filas de cada curva de las tarjetas, del cache compartido con Mercado /
    Curvas (1 build por curva y seq; un tick re-arma sólo su fila). En serie a
    propósito: el build es GIL-bound y así no se ocupan los 8 workers del pool
    de una vez (el libro / Mercado de otro usuario sigue teniendo worker)."""
    out: Dict[str, List[dict]] = {}
    for key in inicio_svc.CURVAS_NECESARIAS:
        try:
            _seq, rows, _meta, _oh = await _rows_en_seq(key, _PLAZO, True, "native", "byma", "", 0)
        except Exception:  # noqa: BLE001 — una curva rota no tira la página
            logger.exception("[inicio] filas de la curva %s fallaron", key)
            rows = []
        out[key] = rows
    return out


async def _contexto() -> Dict[str, Any]:
    bond_universe.ensure_loaded()
    rows_by = await _filas_curvas()
    loop = asyncio.get_running_loop()
    ctx = await loop.run_in_executor(None, inicio_svc.resumen, _PLAZO)
    ctx["bonos"] = inicio_svc.tarjetas_bonos(rows_by)
    return ctx


@router.get("/inicio", response_class=HTMLResponse)
async def inicio_page(request: Request) -> HTMLResponse:
    ctx = await _contexto()
    prefs = await _prefs(request)
    piz = await _pizarra_ctx(request, prefs)
    return _render(request, "inicio.html", piz_codes=bond_universe.all_codes(), piz_y=prefs["y"],
                   piz_n=len(prefs["cuadros"]), **piz, **ctx)


@router.get("/inicio/body", response_class=HTMLResponse)
@seq_cached(ttl=2.0)
async def inicio_body(request: Request) -> HTMLResponse:
    """El resumen entero (todas las tarjetas) en un partial: lo que swapea el
    motor live en cada tick."""
    return _render(request, "partials/inicio_body.html", **(await _contexto()))


# ── Pizarra por usuario ──────────────────────────────────────────────────────
# Prefs en memoria por firma del archivo (mtime + tamaño, µs): el GET corre en
# cada tick y no tiene por qué leer el JSON; otra instancia que escriba el
# mismo archivo (carpeta compartida) se ve igual porque cambia la firma.
_PREFS_MEMO: Dict[str, Tuple[tuple, Dict[str, Any]]] = {}
# Render de la pizarra por usuario: (seq del store, firma de prefs) → HTML. Un
# tick o un cambio de cuadros lo invalidan; con la seq quieta (fuera de rueda)
# el GET de cada refresh es un lookup.
_PIZ_MEMO: Dict[str, Tuple[int, tuple, str]] = {}
piz_stats: Dict[str, int] = {"hit": 0, "miss": 0}


def _prefs_sig() -> tuple:
    try:
        st = os.stat(piz_svc._path())
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


async def _prefs(request: Request) -> Dict[str, Any]:
    user = _user(request)
    sig = _prefs_sig()
    ent = _PREFS_MEMO.get(user)
    if ent is not None and ent[0] == sig:
        return ent[1]
    prefs = await asyncio.get_running_loop().run_in_executor(None, piz_svc.load_user, user)
    _PREFS_MEMO[user] = (sig, prefs)
    return prefs


async def _pizarra_ctx(request: Request, prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Contexto de `partials/inicio_pizarra.html`: un item por cuadro. Las
    cotizaciones se arman todas en UNA tarea del pool; cada libro reusa
    `book_context` (el del libro de Mercado / Órdenes), que ya corre su parte
    GIL-bound en el pool."""
    y = prefs["y"]
    cuadros = prefs["cuadros"]
    loop = asyncio.get_running_loop()
    cots = [(i, c) for i, c in enumerate(cuadros) if c["tipo"] == "cotizacion"]

    def _build_cots() -> Dict[int, Optional[dict]]:
        out: Dict[int, Optional[dict]] = {}
        for i, c in cots:
            try:
                out[i] = _row_for_code(c["code"], c["plazo"], "native", None, book=True, fuente="byma",
                                       settle=pricing.settlement_date_str(c["plazo"]))
            except Exception:  # noqa: BLE001 — un cuadro roto no tira la pizarra
                logger.exception("[pizarra] cotización de %s falló", c["code"])
                out[i] = None
        return out

    filas = await loop.run_in_executor(_row_pool, _build_cots) if cots else {}
    items: List[Dict[str, Any]] = []
    for i, c in enumerate(cuadros):
        if c["tipo"] == "libro":
            try:
                ctx: Optional[Dict[str, Any]] = await book_context(request, c["code"], c["plazo"], "native", "byma", y)
            except Exception:  # noqa: BLE001
                logger.exception("[pizarra] libro de %s falló", c["code"])
                ctx = None
            items.append({"tipo": "libro", "cuadro": c, "ctx": ctx})
        else:
            meta = pricing.bond_meta(c["code"]) or {}
            items.append({"tipo": "cotizacion", "cuadro": c,
                          "ctx": {"row": filas.get(i), "code": c["code"],
                                  "nombre": meta.get("nombre") or c["code"], "plazo": c["plazo"]}})
    return {"cuadros": items, "y": y}


async def _pizarra_response(request: Request, error: Optional[str] = None) -> HTMLResponse:
    user = _user(request)
    prefs = await _prefs(request)
    sig = _PREFS_MEMO[user][0]
    seq = marketdata_store.get_store().seq()
    hdr = {"Cache-Control": "no-store"}
    if error is None:
        ent = _PIZ_MEMO.get(user)
        if ent is not None and ent[0] == seq and ent[1] == sig:
            piz_stats["hit"] += 1
            return HTMLResponse(ent[2], headers=hdr)
    piz_stats["miss"] += 1
    ctx = await _pizarra_ctx(request, prefs)
    resp = _render(request, "partials/inicio_pizarra.html", error=error, **ctx)
    if error is None:
        if len(_PIZ_MEMO) > 256:            # fusible (usuarios reales: decenas)
            _PIZ_MEMO.clear()
        _PIZ_MEMO[user] = (seq, sig, resp.body.decode("utf-8"))
    for k, v in hdr.items():
        resp.headers[k] = v
    return resp


@router.get("/inicio/pizarra", response_class=HTMLResponse)
async def inicio_pizarra(request: Request) -> HTMLResponse:
    """La pizarra del usuario entera (todos sus cuadros) — lo que swapea el
    motor live en cada tick."""
    return await _pizarra_response(request)


async def _mutar(request: Request, fn, *args: Any) -> HTMLResponse:
    """Aplica una mutación de la pizarra (I/O del JSON en el executor) y
    devuelve la pizarra re-renderizada; un error de negocio va como aviso."""
    user = _user(request)
    error: Optional[str] = None
    try:
        await asyncio.get_running_loop().run_in_executor(None, fn, user, *args)
    except piz_svc.PizarraError as exc:
        error = str(exc)
    except OSError as exc:
        logger.exception("[pizarra] no pude guardar")
        error = f"No pude guardar la pizarra: {exc}"
    return await _pizarra_response(request, error=error)


@router.post("/inicio/pizarra/agregar", response_class=HTMLResponse)
async def pizarra_agregar(request: Request, code: str = Form(""), tipo: str = Form("libro"),
                          plazo: str = Form("24hs")) -> HTMLResponse:
    return await _mutar(request, piz_svc.agregar, code, tipo, plazo)


@router.post("/inicio/pizarra/quitar", response_class=HTMLResponse)
async def pizarra_quitar(request: Request, idx: int = Form(...)) -> HTMLResponse:
    return await _mutar(request, piz_svc.quitar, idx)


@router.post("/inicio/pizarra/mover", response_class=HTMLResponse)
async def pizarra_mover(request: Request, idx: int = Form(...), delta: int = Form(1)) -> HTMLResponse:
    return await _mutar(request, piz_svc.mover, idx, delta)


@router.post("/inicio/pizarra/metrica", response_class=HTMLResponse)
async def pizarra_metrica(request: Request, y: str = Form("tirea")) -> HTMLResponse:
    return await _mutar(request, piz_svc.set_metrica, y)


@router.post("/inicio/pizarra/limpiar", response_class=HTMLResponse)
async def pizarra_limpiar(request: Request) -> HTMLResponse:
    return await _mutar(request, piz_svc.limpiar)
