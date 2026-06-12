"""Órdenes — UI del OMS (lectura + ticket con confirmación en dos pasos)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.services import marketdata_store as mds, oms, symbols as syms

router = APIRouter(tags=["ordenes"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _last_ref(code: str, plazo: str) -> Optional[float]:
    snap = mds.get_store().get(syms.md_symbol(code, plazo))
    if snap is None:
        return None
    return snap.last if snap.last is not None else snap.close


def _base_ctx() -> Dict[str, Any]:
    return {"live": settings.oms_live, "kill": oms.kill_switch(),
            "max_notional": settings.oms_max_notional,
            "band": settings.oms_price_band_pct, "audit": oms.audit_tail(25)}


@router.get("/ordenes", response_class=HTMLResponse)
async def ordenes_page(request: Request, code: str = "", side: str = "buy",
                       px: str = "", plazo: str = "24hs") -> HTMLResponse:
    return _render(request, "ordenes.html", code=code, side=side, px=px,
                   plazo=plazo, **_base_ctx())


@router.get("/ordenes/panel", response_class=HTMLResponse)
async def ordenes_panel(request: Request, account: str = "") -> HTMLResponse:
    """Cuentas + órdenes vivas del broker (Etapa A, lectura). Degrada con
    mensaje claro si la sesión REST no está autenticada."""
    accs, orders, err = [], [], None
    try:
        accs = await oms.accounts()
        if account:
            orders = await oms.live_orders(account)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    return _render(request, "partials/ordenes_panel.html",
                   accounts=accs, orders=orders, account=account, err=err, **_base_ctx())


@router.post("/ordenes/ticket", response_class=HTMLResponse)
async def ordenes_ticket(request: Request, code: str = Form(""), side: str = Form("buy"),
                         qty: str = Form(""), price: str = Form(""),
                         account: str = Form(""), plazo: str = Form("24hs")) -> HTMLResponse:
    """Paso 1: validar y mostrar la confirmación (token de un solo uso)."""
    code = code.strip().upper()
    try:
        fqty = float(str(qty).replace(".", "").replace(",", "."))
        fpx = float(str(price).replace(",", "."))
    except ValueError:
        return _render(request, "partials/orden_confirm.html",
                       error="Cantidad/precio inválidos.", **_base_ctx())
    ref = _last_ref(code, plazo)
    motivo = oms.validate(code, side, fqty, fpx, account, ref)
    if motivo:
        oms.audit("rechazada_pretrade", {"code": code, "side": side, "qty": fqty,
                                         "price": fpx, "account": account, "motivo": motivo})
        return _render(request, "partials/orden_confirm.html", error=motivo, **_base_ctx())
    payload = {"code": code, "symbol": syms.md_symbol(code, plazo), "side": side,
               "qty": fqty, "price": fpx, "account": account, "plazo": plazo,
               "notional": fqty * fpx / 100.0, "ref": ref}
    token = oms.new_token(payload)
    return _render(request, "partials/orden_confirm.html",
                   p=payload, token=token, error=None, **_base_ctx())


@router.post("/ordenes/confirmar", response_class=HTMLResponse)
async def ordenes_confirmar(request: Request, token: str = Form("")) -> HTMLResponse:
    """Paso 2: consumir el token (un solo uso) y enviar (o simular)."""
    payload = oms.pop_token(token)
    if payload is None:
        return _render(request, "partials/orden_confirm.html",
                       error="Token vencido o ya usado — volvé a armar el ticket.", **_base_ctx())
    res = await oms.place(payload)
    return _render(request, "partials/orden_confirm.html",
                   result=res, error=None, **_base_ctx())


@router.post("/ordenes/kill", response_class=HTMLResponse)
async def ordenes_kill(request: Request, on: str = Form("1")) -> HTMLResponse:
    oms.kill_switch(on == "1")
    return _render(request, "partials/orden_confirm.html", error=None, **_base_ctx())
