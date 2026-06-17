"""Órdenes — panel de trading del OMS.

Ticket (single) + multi-comitente, con tipo de orden Limit/Market, tenencia y
book embebidos (reusa el libro de Mercado), confirmación en dos pasos con token
de un solo uso, y blotter de estados desde el audit. Envío real detrás de
`oms_live` (default OFF → todo PAPER). Sin estado en el path caliente: el quote
y el blotter leen del store / del audit acotado.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.services import marketdata_store as mds, oms, pricing, symbols as syms

router = APIRouter(tags=["ordenes"])


def _render(request: Request, template: str, trigger: Optional[str] = None, **ctx) -> HTMLResponse:
    resp = request.app.state.templates.TemplateResponse(request, template, ctx)
    if trigger:                              # refresca el blotter tras una acción
        resp.headers["HX-Trigger"] = trigger
    return resp


# ── helpers ────────────────────────────────────────────────────────────────
def _last_ref(code: str, plazo: str) -> Optional[float]:
    snap = mds.get_store().get(syms.md_symbol(code, plazo))
    if snap is None:
        return None
    return snap.last if snap.last is not None else snap.close


def _moneda(code: str) -> str:
    return (pricing.bond_meta(code) or {}).get("moneda") or "ARS"


def _num_qty(s: Any) -> Optional[float]:
    """Cantidad (VN, entera): los puntos son separador de miles (es-AR)."""
    s = str(s or "").strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _num_px(s: Any) -> Optional[float]:
    """Precio: si hay coma es es-AR (1.234,56); si no, se toma tal cual."""
    s = str(s or "").strip().replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _base_ctx() -> Dict[str, Any]:
    return {"live": oms.is_live(), "kill": oms.kill_switch(),
            "max_notional": settings.oms_max_notional,
            "max_notional_usd": settings.oms_max_notional_usd,
            "band": settings.oms_price_band_pct}


# ── páginas / parciales ──────────────────────────────────────────────────────
@router.get("/ordenes", response_class=HTMLResponse)
async def ordenes_page(request: Request, code: str = "", side: str = "buy",
                       px: str = "", plazo: str = "24hs") -> HTMLResponse:
    return _render(request, "ordenes.html", code=code.upper(), side=side, px=px,
                   plazo=plazo, **_base_ctx())


@router.get("/ordenes/quote", response_class=HTMLResponse)
async def ordenes_quote(request: Request, code: str = "", plazo: str = "24hs") -> HTMLResponse:
    """Book + bid/offer + tenencia del bono — idéntico al de Mercado (reusa su
    render). Se dispara al tipear/elegir la especie."""
    code = code.strip().upper()
    if not code:
        return HTMLResponse("")
    from backend.routes.curves import mercado_book   # mismo libro que Mercado
    return await mercado_book(request, code, plazo)


@router.get("/ordenes/blotter", response_class=HTMLResponse)
async def ordenes_blotter(request: Request) -> HTMLResponse:
    return _render(request, "partials/ordenes_blotter.html", blotter=oms.blotter(60))


@router.get("/ordenes/panel", response_class=HTMLResponse)
async def ordenes_panel(request: Request, account: str = "") -> HTMLResponse:
    """Comitentes + órdenes vivas del broker (lectura). Degrada con mensaje
    claro si la sesión REST no está autenticada."""
    accs: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []
    err = None
    # Guard: si la sesión REST no está logueada, NO tocamos la red — si no, cada
    # poll (15 s) colgaría ~5 s en el connect timeout (paper/offline). Mostramos
    # el aviso y listo; cuando haya login, el panel se enciende solo.
    from backend.services.primary_client import get_client
    if not get_client().authenticated:
        err = "Sesión del broker sin login (paper/offline). Conectá en /conexion."
    else:
        try:
            accs = await oms.accounts()
            if account:
                orders = await oms.live_orders(account)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
    return _render(request, "partials/ordenes_panel.html",
                   accounts=accs, orders=orders, account=account, err=err, **_base_ctx())


# ── ticket single (2 pasos) ──────────────────────────────────────────────────
@router.post("/ordenes/ticket", response_class=HTMLResponse)
async def ordenes_ticket(request: Request, code: str = Form(""), side: str = Form("buy"),
                         ordtype: str = Form("limit"), qty: str = Form(""),
                         price: str = Form(""), account: str = Form(""),
                         plazo: str = Form("24hs")) -> HTMLResponse:
    code = code.strip().upper()
    fqty = _num_qty(qty)
    fpx = _num_px(price)
    if fqty is None or (ordtype != "market" and fpx is None):
        return _render(request, "partials/orden_confirm.html",
                       error="Cantidad/precio inválidos.", **_base_ctx())
    moneda = _moneda(code)
    ref = _last_ref(code, plazo)
    motivo = oms.validate(code, side, fqty, fpx, account, ref, moneda, ordtype)
    if motivo:
        oms.audit("rechazada_pretrade", {"code": code, "side": side, "qty": fqty,
                                         "price": fpx, "account": account,
                                         "ordtype": ordtype, "motivo": motivo})
        return _render(request, "partials/orden_confirm.html", error=motivo,
                       trigger="orden-done", **_base_ctx())
    est_px = fpx if ordtype != "market" else ref
    payload = {"code": code, "symbol": syms.md_symbol(code, plazo), "side": side,
               "ordtype": ordtype, "qty": fqty, "price": fpx, "account": account,
               "plazo": plazo, "moneda": moneda, "ref": ref,
               "notional": fqty * (est_px or 0) / 100.0}
    token = oms.new_token(payload)
    return _render(request, "partials/orden_confirm.html",
                   p=payload, token=token, **_base_ctx())


@router.post("/ordenes/confirmar", response_class=HTMLResponse)
async def ordenes_confirmar(request: Request, token: str = Form("")) -> HTMLResponse:
    payload = oms.pop_token(token)
    if payload is None or "batch" in payload:
        return _render(request, "partials/orden_confirm.html",
                       error="Token vencido o ya usado — volvé a armar el ticket.",
                       **_base_ctx())
    res = await oms.place(payload)
    return _render(request, "partials/orden_confirm.html", result=res,
                   trigger="orden-done", **_base_ctx())


# ── multi-comitente (mismo bono → N cuentas) ─────────────────────────────────
@router.post("/ordenes/multi", response_class=HTMLResponse)
async def ordenes_multi(request: Request, code: str = Form(""), side: str = Form("buy"),
                        ordtype: str = Form("limit"), price: str = Form(""),
                        plazo: str = Form("24hs"), lines: str = Form("")) -> HTMLResponse:
    """Una orden por línea 'comitente, cantidad' (misma especie/lado/precio)."""
    code = code.strip().upper()
    fpx = _num_px(price)
    if ordtype != "market" and fpx is None:
        return _render(request, "partials/orden_confirm.html",
                       error="Precio inválido (Limit).", **_base_ctx())
    moneda = _moneda(code)
    ref = _last_ref(code, plazo)
    est_px = fpx if ordtype != "market" else ref
    batch: List[Dict[str, Any]] = []
    errors: List[str] = []
    for i, raw in enumerate(lines.splitlines(), 1):
        ln = raw.strip()
        if not ln:
            continue
        parts = [p.strip() for p in ln.replace(";", ",").replace("\t", ",").split(",")]
        if len(parts) < 2:
            errors.append(f"Línea {i}: formato 'comitente, cantidad'.")
            continue
        acct, q = parts[0], _num_qty(parts[1])
        if not acct or q is None:
            errors.append(f"Línea {i}: comitente o cantidad inválidos.")
            continue
        motivo = oms.validate(code, side, q, fpx, acct, ref, moneda, ordtype)
        if motivo:
            errors.append(f"{acct}: {motivo}")
            continue
        batch.append({"code": code, "symbol": syms.md_symbol(code, plazo), "side": side,
                      "ordtype": ordtype, "qty": q, "price": fpx, "account": acct,
                      "plazo": plazo, "moneda": moneda, "ref": ref,
                      "notional": q * (est_px or 0) / 100.0})
    if not batch:
        return _render(request, "partials/orden_confirm.html",
                       error="Sin líneas válidas. " + " · ".join(errors), **_base_ctx())
    token = oms.new_token({"batch": batch})
    return _render(request, "partials/orden_confirm.html",
                   batch=batch, batch_total=sum(b["notional"] for b in batch),
                   batch_moneda=("USD" if (moneda or "ARS").upper() in ("USD", "USB") else "ARS"),
                   warnings=errors, token=token, **_base_ctx())


@router.post("/ordenes/multi/confirmar", response_class=HTMLResponse)
async def ordenes_multi_confirmar(request: Request, token: str = Form("")) -> HTMLResponse:
    payload = oms.pop_token(token)
    if payload is None or "batch" not in payload:
        return _render(request, "partials/orden_confirm.html",
                       error="Token vencido o ya usado — volvé a armar la multiorden.",
                       **_base_ctx())
    results = [await oms.place(p) for p in payload["batch"]]
    return _render(request, "partials/orden_confirm.html", results=results,
                   trigger="orden-done", **_base_ctx())


@router.post("/ordenes/kill", response_class=HTMLResponse)
async def ordenes_kill(request: Request, on: str = Form("1")) -> HTMLResponse:
    oms.kill_switch(on == "1")
    return _render(request, "partials/oms_status.html", trigger="orden-done", **_base_ctx())


@router.post("/ordenes/live", response_class=HTMLResponse)
async def ordenes_live(request: Request, arm: str = Form("0"),
                       confirm: str = Form("")) -> HTMLResponse:
    """Prende/apaga el modo LIVE en caliente. Armar exige escribir 'LIVE'
    (anti-click accidental); apagar es inmediato. No persiste (reboot→config)."""
    if arm == "1":
        if confirm.strip().upper() != "LIVE":
            return _render(request, "partials/oms_status.html",
                           live_msg="Para activar LIVE escribí exactamente LIVE y confirmá.",
                           **_base_ctx())
        oms.set_live(True)
    else:
        oms.set_live(False)
    return _render(request, "partials/oms_status.html", trigger="orden-done",
                   live_msg=("⚠️ MODO LIVE activado — las órdenes viajan al broker."
                             if oms.is_live() else "Modo PAPER — nada viaja al broker."),
                   **_base_ctx())
