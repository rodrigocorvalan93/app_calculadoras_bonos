"""OMS — cursado de órdenes (Etapa A lectura + Etapa B paper, C tras flag).

SEGURIDAD PRIMERO (acá hay plata real):
- `settings.oms_live` arranca en False: toda orden se valida, se confirma en
  dos pasos y se REGISTRA como PAPER — nunca viaja al broker. Para fuego real:
  OMS_LIVE=1 en secrets.txt + kill-switch visible + límites.
- Confirmación en dos pasos con token de un solo uso (TTL 90 s) → ni un
  double-click ni un retry de red pueden duplicar una orden.
- Audit log persistente (oms_audit.jsonl, gitignored): cada intento, envío,
  respuesta y cancelación queda escrito ANTES de tocar la red.
- Kill-switch en memoria: bloquea todo envío al instante.

Lectura (Etapa A): cuentas y órdenes vivas por REST del broker (mismos paths
de la API Primary/XOMS que usa la casa: rest/accounts, rest/order/actives,
rest/order/newSingleOrder, rest/order/cancelById). Si el deployment del broker
difiere, el error crudo se muestra en el panel para ajustar el path.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings

_AUDIT_PATH = Path(__file__).resolve().parents[2] / "oms_audit.jsonl"
_audit_lock = threading.Lock()

# Kill-switch (en memoria; arranca permitido pero el modo paper ya protege).
_kill = {"on": False}

# Tokens de confirmación: token → (payload, expira). Un solo uso.
_pending: Dict[str, tuple] = {}
_pending_lock = threading.Lock()
_TOKEN_TTL = 90.0


def kill_switch(on: Optional[bool] = None) -> bool:
    if on is not None:
        _kill["on"] = bool(on)
        audit("kill_switch", {"on": _kill["on"]})
    return _kill["on"]


def audit(event: str, data: Dict[str, Any]) -> None:
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event,
           "live": settings.oms_live, **data}
    with _audit_lock:
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def audit_tail(n: int = 30) -> List[Dict[str, Any]]:
    try:
        with open(_AUDIT_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(ln) for ln in reversed(lines)]
    except FileNotFoundError:
        return []
    except Exception:  # noqa: BLE001
        return []


def validate(code: str, side: str, qty: float, price: float,
             account: str, last_ref: Optional[float]) -> Optional[str]:
    """Validaciones pre-trade. Devuelve el motivo del rechazo o None si pasa."""
    if _kill["on"]:
        return "KILL-SWITCH activado: envíos bloqueados."
    if not account:
        return "Falta la comitente/cuenta."
    if not code:
        return "Falta la especie."
    if side not in ("buy", "sell"):
        return "Lado inválido."
    if not qty or qty <= 0:
        return "Cantidad (VN) debe ser > 0."
    if not price or price <= 0:
        return "Precio debe ser > 0."
    notional = qty * price / 100.0   # bonos cotizan por VN 100
    if notional > settings.oms_max_notional:
        return (f"Notional estimado {notional:,.0f} supera el tope "
                f"{settings.oms_max_notional:,.0f} (oms_max_notional).")
    if last_ref:
        band = settings.oms_price_band_pct / 100.0
        if abs(price / last_ref - 1.0) > band:
            return (f"Precio {price} fuera de la banda ±{settings.oms_price_band_pct:.0f}% "
                    f"vs referencia {last_ref} (fat-finger guard).")
    return None


def new_token(payload: Dict[str, Any]) -> str:
    tok = uuid.uuid4().hex[:16]
    with _pending_lock:
        # higiene: limpiar vencidos
        now = time.time()
        for k in [k for k, (_, exp) in _pending.items() if exp < now]:
            _pending.pop(k, None)
        _pending[tok] = (payload, now + _TOKEN_TTL)
    audit("ticket", {**payload, "token": tok})
    return tok


def pop_token(tok: str) -> Optional[Dict[str, Any]]:
    """Consume el token (un solo uso). None si no existe o venció."""
    with _pending_lock:
        item = _pending.pop(tok, None)
    if item is None:
        return None
    payload, exp = item
    if exp < time.time():
        return None
    return payload


# ── Broker REST (Etapa A: lectura · Etapa C: envío con OMS_LIVE=1) ─────────
async def accounts() -> List[Dict[str, Any]]:
    from backend.services.primary_client import get_client
    d = await get_client().get_json("rest/accounts")
    return d.get("accounts", []) if isinstance(d, dict) else []


async def live_orders(account: str) -> List[Dict[str, Any]]:
    from backend.services.primary_client import get_client
    d = await get_client().get_json("rest/order/actives", {"accountId": account})
    return d.get("orders", []) if isinstance(d, dict) else []


async def place(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía la orden (o la simula). El audit se escribe ANTES y DESPUÉS."""
    client_order_id = f"calc-{uuid.uuid4().hex[:12]}"
    rec = {**payload, "client_order_id": client_order_id}
    if _kill["on"]:
        audit("rechazada_kill", rec)
        return {"status": "RECHAZADA", "motivo": "kill-switch activado", **rec}
    if not settings.oms_live:
        audit("paper_enviada", rec)
        return {"status": "PAPER", "motivo": "modo paper (OMS_LIVE=0): NO viajó al broker", **rec}

    audit("live_enviando", rec)
    from backend.services.primary_client import get_client
    try:
        d = await get_client().get_json("rest/order/newSingleOrder", {
            "marketId": "ROFX",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "orderQty": payload["qty"],
            "price": payload["price"],
            "ordType": "limit",
            "timeInForce": "Day",
            "account": payload["account"],
        })
        audit("live_respuesta", {**rec, "broker": d})
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        audit("live_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}


async def cancel(client_order_id: str, proprietary: str = "api") -> Dict[str, Any]:
    rec = {"client_order_id": client_order_id, "proprietary": proprietary}
    if not settings.oms_live:
        audit("paper_cancelada", rec)
        return {"status": "PAPER", **rec}
    audit("live_cancelando", rec)
    from backend.services.primary_client import get_client
    try:
        d = await get_client().get_json("rest/order/cancelById", {
            "clientOrderId": client_order_id, "proprietary": proprietary})
        audit("live_cancel_respuesta", {**rec, "broker": d})
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        audit("live_cancel_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}
