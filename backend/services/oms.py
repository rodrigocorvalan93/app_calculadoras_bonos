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

import asyncio
import functools
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# El audit es el registro de trazabilidad de órdenes REALES: sus timestamps
# van en reloj de Buenos Aires (naive, mismo formato de siempre) para poder
# reconciliar contra la rueda/el broker aunque el server corra en UTC.
_TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")

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


def set_live(on: Optional[bool], user: str = "") -> bool:
    """on True/False ⇒ override; None ⇒ vuelve a seguir la config."""
    _live_override["v"] = None if on is None else bool(on)
    audit("oms_live_switch", {"on": is_live(), "user": user})
    return is_live()

# Tokens de confirmación: token → (payload, expira). Un solo uso.
_pending: Dict[str, tuple] = {}
_pending_lock = threading.Lock()
_TOKEN_TTL = 90.0


def kill_switch(on: Optional[bool] = None, user: str = "") -> bool:
    if on is not None:
        _kill["on"] = bool(on)
        audit("kill_switch", {"on": _kill["on"], "user": user})
    return _kill["on"]


def audit(event: str, data: Dict[str, Any]) -> None:
    rec = {"ts": datetime.now(_TZ_BA).replace(tzinfo=None).isoformat(timespec="seconds"),
           "event": event, "live": is_live(), **data}
    with _audit_lock:
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


async def audit_async(event: str, data: Dict[str, Any]) -> None:
    """audit() desde código async SIN bloquear el event loop: el write va al
    executor (el archivo vive en la carpeta OneDrive — un write puede clavarse
    decenas de ms — y encima el lock serializa: un handler esperando el lock
    frenaba a TODOS los usuarios). El await preserva el orden audit-antes-de-
    mandar que exige el diseño."""
    await asyncio.get_running_loop().run_in_executor(None, audit, event, data)


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

# Estado REAL en el broker (evento live_estado, del seguimiento post-envío) →
# etiqueta del blotter. El "OK" de newSingleOrder sólo significa "recibida":
# el risk puede rechazarla al instante (Saldo insuficiente) y el blotter
# quedaba en ENVIADA para siempre — había que abrir la Matriz para enterarse.
_ESTADO_LABEL = {
    "REJECTED": "RECHAZADA (broker)", "FILLED": "EJECUTADA",
    "PARTIALLY_FILLED": "PARCIAL", "CANCELLED": "CANCELADA",
    "NEW": "EN MERCADO", "PENDING_NEW": "EN MERCADO",
}


def blotter(n: int = 60) -> List[Dict[str, Any]]:
    """Estado de órdenes derivado del audit persistente (más nuevas primero).
    Funciona en paper y en live — es el registro de lo que pasó por el OMS."""
    rows: List[Dict[str, Any]] = []
    for a in audit_tail(400):                      # ya viene del más nuevo al más viejo
        if a.get("event") == "live_estado":        # estado real del broker (seguimiento)
            raw = str(a.get("estado") or "").upper()
            st = _ESTADO_LABEL.get(raw, raw or "?")
        else:
            st = _BLOTTER_STATUS.get(a.get("event"))
            if st is None:
                continue
        rows.append({
            "ts": a.get("ts"), "status": st,
            "code": a.get("code"), "side": a.get("side"),
            "qty": a.get("qty"), "price": a.get("price"),
            "account": a.get("account"), "ordtype": a.get("ordtype") or "limit",
            "cid": a.get("client_order_id"),
            "motivo": a.get("motivo") or a.get("texto") or a.get("error"),
        })
        if len(rows) >= n:
            break
    return rows


async def market_ref_rest(symbol: str) -> Optional[float]:
    """Last/close del broker por REST para un símbolo SIN dato en el store
    (ON ilíquido, especie fuera del universo WS). Cierra el agujero real del
    fat-finger: sin referencia la banda no corría, y un precio tipeado con
    punto decimal ("141.750", estilo Matriz) que el parser es-AR lee ×1000
    (141.750,00) viajaba al broker — caso VSCMO. Si el broker puede aceptar la
    orden, el broker TIENE el market data: con esto la banda casi siempre corre.
    Una llamada por armado de ticket (no es hot path), best-effort: sin sesión
    o sin dato → None y el flujo queda como siempre (valor técnico →
    confirmación manual)."""
    from backend.services.primary_ws import get_ws_client
    c = get_ws_client()
    if not c.authenticated:
        return None
    try:
        d = await c.get_json("rest/marketdata/get", {
            "marketId": "ROFX", "symbol": symbol, "entries": "LA,CL", "depth": 1})
        if not isinstance(d, dict) or d.get("status") != "OK":
            return None
        md = d.get("marketData") or {}
        for k in ("LA", "CL"):
            v = md.get(k)
            px = v.get("price") if isinstance(v, dict) else None
            if px:
                return float(px)
    except Exception:  # noqa: BLE001 — best-effort: cualquier problema → sin ref
        return None
    return None


def _hint_magnitud(price: float, ref: float, band: float) -> str:
    """Detector del clásico error de formato: '141.750' tipeado con punto
    decimal (estilo Matriz/en-US) se lee es-AR como 141.750,00 (×1000) — y al
    revés, '204,600' pensado en-US como 204.600 se lee 204,60 (÷1000). Si el
    precio rechazado ENCAJA en la banda al correrle la coma 3 lugares, el
    rechazo lo dice explícito: el operador corrige al toque en vez de pelearse
    con la banda. Sólo agrega texto al motivo — nunca reinterpreta el precio
    en silencio (acá hay plata real)."""
    from backend.locale_ar import fmt_num
    for factor in (0.001, 1000.0):
        alt = price * factor
        if ref and abs(alt / ref - 1.0) <= band:
            return (f" ¿Quisiste decir {fmt_num(alt, 2)}? Ojo con el formato es-AR: "
                    f"el PUNTO es separador de miles y el decimal va con COMA "
                    f"(el precio ingresado se leyó como {fmt_num(price, 2)}).")
    return ""


def validate(code: str, side: str, qty: float, price: Optional[float],
             account: str, last_ref: Optional[float], moneda: str = "ARS",
             ordtype: str = "limit", theo_ref: Optional[float] = None,
             confirmed: bool = False) -> Optional[str]:
    """Validaciones pre-trade. Devuelve el motivo del rechazo o None si pasa.

    - Tope de notional EN LA MONEDA DEL BONO: ARS (oms_max_notional) para pesos,
      USD (oms_max_notional_usd) para hard-dollar (moneda USD/USB).
    - Banda de precio (fat-finger) sólo para Limit; Market toma lo que haya. La
      referencia es, en orden: mercado (last/close) → valor técnico `theo_ref`
      (banda más ancha) → si no hay ninguna, se exige `confirmed` (config
      `oms_require_ref_confirm`). Esto cierra el agujero del ON ilíquido sin
      cotización, donde antes NO se chequeaba banda y un precio mal tipeado
      (p.ej. sub-precio 1000×) pasaba directo.
    - Market SIN ninguna referencia (ni mercado ni valor técnico): también exige
      `confirmed` y aplica el tope de notional sobre el VN a la par (precio=100).
      Antes este caso se colaba sin tope ni confirmación (ambos guards vivían bajo
      ramas que Market o el `ref_px` nulo salteaban) — el agujero real del hallazgo.
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
    ref_px = price if not is_market else (last_ref or theo_ref)  # market estima con la referencia
    if ref_px:
        notional = qty * ref_px / 100.0             # bonos cotizan por VN 100
        if notional > cap:
            return (f"Notional estimado {notional:,.0f} {unit} supera el tope "
                    f"{cap:,.0f} {unit}.")
    if not is_market:                               # banda fat-finger sólo para Limit
        if last_ref:
            band = settings.oms_price_band_pct / 100.0
            if abs(price / last_ref - 1.0) > band:
                return (f"Precio {price} fuera de la banda ±{settings.oms_price_band_pct:.0f}% "
                        f"vs mercado {last_ref} (fat-finger guard)."
                        + _hint_magnitud(price, last_ref, band))
        elif theo_ref and theo_ref > 0:
            band = settings.oms_theo_band_pct / 100.0
            if abs(price / theo_ref - 1.0) > band:
                return (f"Precio {price} fuera de la banda ±{settings.oms_theo_band_pct:.0f}% "
                        f"vs valor técnico {theo_ref:,.2f} (sin cotización de mercado; "
                        f"revisalo o confirmá manualmente)."
                        + _hint_magnitud(price, theo_ref, band))
        elif settings.oms_require_ref_confirm and not confirmed:
            return ("Sin referencia de mercado ni valor técnico para validar el precio. "
                    "Confirmá manualmente (o usá Market) para enviar.")
    elif ref_px is None:
        # Market SIN ninguna referencia (ni last/close ni valor técnico): antes se
        # colaba sin tope de notional (el `if ref_px:` de arriba no corre) y sin la
        # confirmación de sin-referencia (vivía bajo `if not is_market`). Eximir a
        # Market de la BANDA de precio es intencional ("toma lo que haya"), pero un
        # VN arbitrario no puede viajar al broker sin ningún guard. Exigimos
        # confirmación explícita y aplicamos un tope conservador sobre el VN
        # valuado a la par (precio=100 ⇒ notional ≈ qty).
        if settings.oms_require_ref_confirm and not confirmed:
            return ("Market sin referencia de mercado ni valor técnico: no se puede "
                    "estimar el notional. Confirmá manualmente para enviar (o usá "
                    "Limit con precio).")
        notional_par = qty                          # qty * 100 / 100 — VN a la par
        if notional_par > cap:
            return (f"VN {qty:,.0f} (≈{notional_par:,.0f} {unit} a la par) supera el tope "
                    f"{cap:,.0f} {unit}. Sin cotización no se puede validar mejor; "
                    f"bajá la cantidad o usá Limit.")
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


def peek_token(tok: str) -> Optional[Dict[str, Any]]:
    """Payload del token SIN consumirlo — para validar la confirmación LIVE
    antes de quemarlo (un error de tipeo no obliga a rearmar el ticket)."""
    with _pending_lock:
        item = _pending.get(tok)
    if item is None:
        return None
    payload, exp = item
    return None if exp < time.time() else payload


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


# Seguimiento post-envío: cuándo re-consultar el estado (seg tras el envío);
# el 2º intento sólo corre si el 1º no encontró un estado final.
_FOLLOWUP_DELAYS = (1.5, 4.0)
_ESTADO_FINAL = {"REJECTED", "FILLED", "CANCELLED", "EXPIRED"}
_followups: set = set()                 # refs vivas (create_task guarda débil)


async def _order_followup(client_id: str, proprietary: str, rec: Dict[str, Any]) -> None:
    """Persigue el estado REAL de la orden tras un envío aceptado: consulta
    rest/order/id un par de veces y audita cada estado nuevo como `live_estado`
    (el blotter lo muestra: "RECHAZADA (broker) · Saldo insuficiente",
    EJECUTADA, EN MERCADO…). Best-effort en background — no demora la
    respuesta del envío ni toca el hot path; cualquier error corta en
    silencio (el estado siempre está en la Matriz como último recurso)."""
    from backend.services.primary_ws import get_ws_client
    ultimo = ""
    for delay in _FOLLOWUP_DELAYS:
        await asyncio.sleep(delay)
        try:
            d = await get_ws_client().get_json("rest/order/id", {
                "clientOrderId": client_id, "proprietary": proprietary})
        except Exception:  # noqa: BLE001 — best-effort
            return
        o = d.get("order") if isinstance(d, dict) else None
        if not isinstance(o, dict):
            continue
        st = str(o.get("status") or "").upper()
        if st and st != ultimo:
            ultimo = st
            await audit_async("live_estado", {**rec, "estado": st,
                                              "texto": o.get("text") or "",
                                              "cum_qty": o.get("cumQty")})
        if st in _ESTADO_FINAL:
            return


async def place(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía la orden (o la simula). El audit se escribe ANTES y DESPUÉS."""
    client_order_id = f"calc-{uuid.uuid4().hex[:12]}"
    rec = {**payload, "client_order_id": client_order_id}
    if _kill["on"]:
        await audit_async("rechazada_kill", rec)
        return {"status": "RECHAZADA", "motivo": "kill-switch activado", **rec}
    if not is_live():
        await audit_async("paper_enviada", rec)
        return {"status": "PAPER", "motivo": "modo paper (OMS_LIVE=0): NO viajó al broker", **rec}

    await audit_async("live_enviando", rec)
    from backend.services.primary_ws import get_ws_client

    # Guard pre-trade: no mandes a un símbolo que el broker NO tiene en su
    # universo (ON que sólo opera SENEBI, plazo inexistente, ticker mal…). En vez
    # del críptico "Invalid Instrument ... doesn't exist" del broker DESPUÉS de
    # cursar, avisamos ANTES con los símbolos/plazos que SÍ existen para ese
    # código. Fail-open: si no se puede traer el universo, sigue como antes.
    from backend.services import instruments
    symbol = payload.get("symbol", "")
    if symbol:
        chk = await instruments.resolve(payload.get("code", ""), symbol)
        if chk["checked"] and not chk["exists"]:
            cands = chk["candidates"]
            motivo = (f"El broker no tiene el instrumento «{symbol}». "
                      + (f"Símbolos que SÍ existen para {payload.get('code', '')}: "
                         + ", ".join(cands) + "." if cands else
                         "No hay símbolos parecidos en el universo del broker "
                         "(¿ticker mal o ON que no opera en este broker?)."))
            await audit_async("live_instrumento_inexistente", {**rec, "candidatos": cands})
            return {"status": "ERROR", "motivo": motivo, "candidatos": cands, **rec}

    ordtype = payload.get("ordtype", "limit")
    qty = payload["qty"]
    try:
        # VN entero cuando lo es: un "300000.0" flotante en el query string es
        # buscarse un parseo raro del lado del broker (campo entero en xOMS)
        if float(qty).is_integer():
            qty = int(qty)
    except (TypeError, ValueError):
        pass
    params = {
        "marketId": "ROFX",
        "symbol": payload["symbol"],
        "side": payload["side"],
        "orderQty": qty,
        "ordType": ordtype,
        "timeInForce": "Day",
        "account": payload["account"],
    }
    if ordtype != "market":
        params["price"] = payload["price"]
    try:
        d = await get_ws_client().get_json_checked("rest/order/newSingleOrder", params)
        await audit_async("live_respuesta", {**rec, "broker": d})
        o = d.get("order") if isinstance(d, dict) else None
        if isinstance(o, dict) and o.get("clientId"):
            t = asyncio.get_running_loop().create_task(_order_followup(
                str(o["clientId"]), str(o.get("proprietary") or "api"), rec))
            _followups.add(t)
            t.add_done_callback(_followups.discard)
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        await audit_async("live_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}


async def cancel(client_order_id: str, proprietary: str = "api") -> Dict[str, Any]:
    rec = {"client_order_id": client_order_id, "proprietary": proprietary}
    if not is_live():
        await audit_async("paper_cancelada", rec)
        return {"status": "PAPER", **rec}
    await audit_async("live_cancelando", rec)
    from backend.services.primary_ws import get_ws_client
    try:
        d = await get_ws_client().get_json_checked("rest/order/cancelById", {
            "clientOrderId": client_order_id, "proprietary": proprietary})
        await audit_async("live_cancel_respuesta", {**rec, "broker": d})
        return {"status": d.get("status", "?"), "broker": d, **rec}
    except Exception as exc:  # noqa: BLE001
        await audit_async("live_cancel_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}
