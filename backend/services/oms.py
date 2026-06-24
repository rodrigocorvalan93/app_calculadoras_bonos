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

import functools
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings

logger = logging.getLogger("oms")

_AUDIT_PATH = Path(__file__).resolve().parents[2] / "oms_audit.jsonl"
_audit_lock = threading.Lock()

# Kill-switch (en memoria; arranca permitido pero el modo paper ya protege).
_kill = {"on": False}

# Override de LIVE en runtime. None ⇒ usa settings.oms_live (secrets.txt). Se
# puede prender/apagar desde la UI SIN reiniciar; NO persiste: al reiniciar
# vuelve al default de config (paper, salvo OMS_LIVE=1) — un reboot nunca te
# deja operando en serio por accidente.
_live_override: Dict[str, Optional[bool]] = {"v": None}


def is_live() -> bool:
    return settings.oms_live if _live_override["v"] is None else _live_override["v"]


def set_live(on: Optional[bool]) -> bool:
    """on True/False ⇒ override; None ⇒ vuelve a seguir la config."""
    _live_override["v"] = None if on is None else bool(on)
    audit("oms_live_switch", {"on": is_live()})
    return is_live()

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
           "live": is_live(), **data}
    with _audit_lock:
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _tail_lines(n: int) -> List[str]:
    """Últimas n líneas leyendo SÓLO el final del archivo (el audit crece sin
    límite; no queremos releer todo en cada blotter/refresh)."""
    try:
        with open(_AUDIT_PATH, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(8192, size)
                size -= step
                f.seek(size)
                data = f.read(step) + data
        return data.decode("utf-8", "replace").splitlines()[-n:]
    except FileNotFoundError:
        return []
    except Exception:  # noqa: BLE001
        return []


def audit_tail(n: int = 30) -> List[Dict[str, Any]]:
    out = []
    for ln in reversed(_tail_lines(n)):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


# Eventos del audit que representan el desenlace de un intento de orden →
# alimentan el blotter (estado por intento).
_BLOTTER_STATUS = {
    "paper_enviada": "PAPER", "live_respuesta": "ENVIADA", "live_error": "ERROR",
    "rechazada_kill": "RECHAZADA", "rechazada_pretrade": "RECHAZADA",
    "paper_cancelada": "CANCELADA", "live_cancel_respuesta": "CANCELADA",
}


def blotter(n: int = 60) -> List[Dict[str, Any]]:
    """Estado de órdenes derivado del audit persistente (más nuevas primero).
    Funciona en paper y en live — es el registro de lo que pasó por el OMS."""
    rows: List[Dict[str, Any]] = []
    for a in audit_tail(400):                      # ya viene del más nuevo al más viejo
        st = _BLOTTER_STATUS.get(a.get("event"))
        if st is None:
            continue
        rows.append({
            "ts": a.get("ts"), "status": st,
            "code": a.get("code"), "side": a.get("side"),
            "qty": a.get("qty"), "price": a.get("price"),
            "account": a.get("account"), "ordtype": a.get("ordtype") or "limit",
            "cid": a.get("client_order_id"),
            "motivo": a.get("motivo") or a.get("error"),
        })
        if len(rows) >= n:
            break
    return rows


def validate(code: str, side: str, qty: float, price: Optional[float],
             account: str, last_ref: Optional[float], moneda: str = "ARS",
             ordtype: str = "limit") -> Optional[str]:
    """Validaciones pre-trade. Devuelve el motivo del rechazo o None si pasa.

    - Tope de notional EN LA MONEDA DEL BONO: ARS (oms_max_notional) para pesos,
      USD (oms_max_notional_usd) para hard-dollar (moneda USD/USB).
    - Banda de precio (fat-finger) sólo para Limit; Market toma lo que haya.
    """
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
    is_market = ordtype == "market"
    if not is_market and (not price or price <= 0):
        return "Precio debe ser > 0 (orden Limit)."
    is_usd = (moneda or "ARS").upper() in ("USD", "USB")
    cap = settings.oms_max_notional_usd if is_usd else settings.oms_max_notional
    unit = "USD" if is_usd else "ARS"
    ref_px = price if not is_market else last_ref   # market estima con la referencia
    if ref_px:
        notional = qty * ref_px / 100.0             # bonos cotizan por VN 100
        if notional > cap:
            return (f"Notional estimado {notional:,.0f} {unit} supera el tope "
                    f"{cap:,.0f} {unit}.")
    if not is_market and last_ref:
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


# ── Comitentes (cuentas) configurables por broker ─────────────────────────
# El broker suele exponer sólo una comitente genérica por REST, pero el
# operador maneja muchos fondos cuyos números son SENSIBLES. Se cargan por el
# secret OMS_COMITENTES (env var / .env / secrets.txt) — NUNCA se commitean —
# como JSON {broker: {etiqueta: nro}}, ej:
#   {"lbo": {"PYMES": "54437", ...}, "cocos": {"PERSO": "27404"}}
# El broker activo se deduce del host (settings.primary_base_url, que /conexion
# repunta en caliente). `accounts()` hace MERGE de estas con las del broker.
@functools.lru_cache(maxsize=1)
def _comitentes_all() -> Dict[str, Dict[str, str]]:
    """Parsea OMS_COMITENTES una sola vez (el secret no cambia en runtime, sólo
    el broker activo). {} si está vacío o el JSON no es válido."""
    raw = (settings.oms_comitentes or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("OMS_COMITENTES no es JSON válido — se ignora (el panel cae al genérico del broker)")
        return {}
    if not isinstance(data, dict):
        logger.warning("OMS_COMITENTES debe ser un objeto {broker: {etiqueta: nro}} — se ignora")
        return {}
    return data


def _active_broker_key() -> str:
    """Clave del broker activo deducida del host (api.LBO/COCOS/LATIN.xoms…)."""
    host = (settings.primary_base_url or "").lower()
    for key in ("lbo", "cocos", "latin"):
        if key in host:
            return key
    return "default"


def configured_comitentes() -> List[Dict[str, str]]:
    """Comitentes del secret para el broker activo, en el orden cargado. Sin
    red → disponibles aunque no haya sesión. [] si no hay nada configurado."""
    broker_map = _comitentes_all().get(_active_broker_key()) or {}
    out: List[Dict[str, str]] = []
    for label, num in broker_map.items():
        num = str(num).strip()
        if num:
            out.append({"id": num, "label": str(label).strip() or num, "source": "config"})
    return out


def _normalize_account(a: Any) -> Dict[str, str]:
    """Cuenta cruda del broker REST → {id, label, source}. Defensivo con el
    shape (la API Primary/XOMS varía: id / accountName / name / brokerId)."""
    if not isinstance(a, dict):
        return {"id": str(a).strip(), "label": str(a).strip(), "source": "broker"}
    num = str(a.get("id") or a.get("accountName") or a.get("name") or a.get("brokerId") or "").strip()
    label = str(a.get("name") or a.get("accountName") or num or "?").strip()
    return {"id": num, "label": label, "source": "broker"}


def _merge_comitentes(cfg: List[Dict[str, str]], broker: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Unión cfg + broker, deduplicada por número de comitente: primero las
    configuradas (en su orden, con su etiqueta de fondo), después las que sólo
    expone el broker. Si un número está en ambas, gana la etiqueta de cfg."""
    seen = {c["id"] for c in cfg if c.get("id")}
    out = list(cfg)
    for b in broker:
        bid = b.get("id", "")
        if bid and bid not in seen:
            out.append(b)
            seen.add(bid)
    return out


# ── Broker REST (Etapa A: lectura · Etapa C: envío con OMS_LIVE=1) ─────────
async def accounts() -> List[Dict[str, Any]]:
    """Comitentes para el panel: MERGE de las configuradas (secret, por broker)
    con las que el broker expone por REST, deduplicadas por número. Si el broker
    falla pero hay configuradas, se muestran igual (no rompe el panel); sin
    configuradas, el error del broker se propaga como hasta ahora."""
    cfg = configured_comitentes()
    broker: List[Dict[str, str]] = []
    try:
        from backend.services.primary_ws import get_ws_client
        d = await get_ws_client().get_json_checked("rest/accounts")
        raw = d.get("accounts", []) if isinstance(d, dict) else []
        broker = [_normalize_account(a) for a in raw]
    except Exception:  # noqa: BLE001 — best-effort: con cfg seguimos; sin cfg, propaga
        if not cfg:
            raise
    return _merge_comitentes(cfg, broker)


async def live_orders(account: str) -> List[Dict[str, Any]]:
    from backend.services.primary_ws import get_ws_client
    d = await get_ws_client().get_json_checked("rest/order/actives", {"accountId": account})
    return d.get("orders", []) if isinstance(d, dict) else []


async def place(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía la orden (o la simula). El audit se escribe ANTES y DESPUÉS."""
    client_order_id = f"calc-{uuid.uuid4().hex[:12]}"
    rec = {**payload, "client_order_id": client_order_id}
    if _kill["on"]:
        audit("rechazada_kill", rec)
        return {"status": "RECHAZADA", "motivo": "kill-switch activado", **rec}
    if not is_live():
        audit("paper_enviada", rec)
        return {"status": "PAPER", "motivo": "modo paper (OMS_LIVE=0): NO viajó al broker", **rec}

    audit("live_enviando", rec)
    from backend.services.primary_ws import get_ws_client
    ordtype = payload.get("ordtype", "limit")
    params = {
        "marketId": "ROFX",
        "symbol": payload["symbol"],
        "side": payload["side"],
        "orderQty": payload["qty"],
        "ordType": ordtype,
        "timeInForce": "Day",
        "account": payload["account"],
    }
    if ordtype != "market":
        params["price"] = payload["price"]
    try:
        d = await get_ws_client().get_json_checked("rest/order/newSingleOrder", params)
        audit("live_respuesta", {**rec, "broker": d})
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        audit("live_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}


async def cancel(client_order_id: str, proprietary: str = "api") -> Dict[str, Any]:
    rec = {"client_order_id": client_order_id, "proprietary": proprietary}
    if not is_live():
        audit("paper_cancelada", rec)
        return {"status": "PAPER", **rec}
    audit("live_cancelando", rec)
    from backend.services.primary_ws import get_ws_client
    try:
        d = await get_ws_client().get_json_checked("rest/order/cancelById", {
            "clientOrderId": client_order_id, "proprietary": proprietary})
        audit("live_cancel_respuesta", {**rec, "broker": d})
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        audit("live_cancel_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}
