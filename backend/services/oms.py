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

import math
import asyncio

import httpx
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


# Tail parseado cacheado por (mtime_ns, size, n): el blotter pollea cada 8 s
# POR usuario y re-leía ~77 KB + 400 json.loads del archivo (en OneDrive) aunque
# no hubiera cambiado. Carrera de asignación benigna (se recomputa, no corrompe).
_tail_cache: Optional[tuple] = None


def audit_tail(n: int = 30) -> List[Dict[str, Any]]:
    global _tail_cache
    import os

    try:
        st = os.stat(_AUDIT_PATH)
        sig = (st.st_mtime_ns, st.st_size, n)
    except OSError:
        sig = None
    c = _tail_cache
    if sig is not None and c is not None and c[0] == sig:
        return c[1]
    out = []
    for ln in reversed(_tail_lines(n)):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    if sig is not None:
        _tail_cache = (sig, out)
    return out


# Eventos del audit que representan el desenlace de un intento de orden →
# alimentan el blotter (estado por intento).
_BLOTTER_STATUS = {
    "paper_enviada": "PAPER", "live_respuesta": "ENVIADA", "live_error": "ERROR",
    "rechazada_kill": "RECHAZADA", "rechazada_pretrade": "RECHAZADA",
    "rechazada_contexto": "RECHAZADA",
    "live_rechazo_broker": "RECHAZADA (broker)",     # HTTP 200 con JSON de rechazo
    "live_desconocida": "DESCONOCIDA",               # respuesta perdida: pudo entrar
    "live_desconocida_posible": "DESCONOCIDA",       # hay una orden igual sin hora: ¿anterior?
    "live_desconocida_no_verificable": "DESCONOCIDA",  # el broker no respondió la lista completa
    "live_desconocida_sin_rastro": "NO ENTRÓ",       # verificada la lista completa del día: no está
    "paper_cancelada": "CANCELADA",
    "live_cancel_respuesta": "CANCEL ACEPTADA",      # el broker aceptó el pedido (estado final: seguimiento)
    "live_cancel_rechazo": "CANCEL RECHAZADA",       # la orden sigue viva
    "live_cancel_error": "CANCEL ERROR",
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
            px = _ref_ok(v.get("price")) if isinstance(v, dict) else None
            if px:
                return px
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
    causas = (
        # ×/÷1000: formato ("141.750" con punto decimal se lee 141.750,00)
        (0.001, "Ojo con el formato es-AR: el PUNTO es separador de miles y el decimal va con COMA"),
        (1000.0, "Ojo con el formato es-AR: el PUNTO es separador de miles y el decimal va con COMA"),
        # ×/÷100: precio por 1 VN en vez de por 100 VN (caso GN39O 1.448,50 vs 144.850)
        (100.0, "Ojo: los bonos/ONs cotizan POR 100 VN, no por 1 VN"),
        (0.01, "Ojo: los bonos/ONs cotizan POR 100 VN, no por 1 VN"),
    )
    for factor, causa in causas:
        alt = price * factor
        if ref and abs(alt / ref - 1.0) <= band:
            return (f" ¿Quisiste decir {fmt_num(alt, 2)}? {causa} "
                    f"(el precio ingresado se leyó como {fmt_num(price, 2)}).")
    return ""


def _finito(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _ref_ok(x: Any) -> Optional[float]:
    """Referencia de precio usable (float finito > 0) o None."""
    if x is None or not _finito(x):
        return None
    f = float(x)
    return f if f > 0 else None


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
    if not qty or not _finito(qty) or qty <= 0:
        return "Cantidad (VN) debe ser > 0."
    is_market = ordtype == "market"
    if not is_market and (not price or not _finito(price) or price <= 0):
        return "Precio debe ser > 0 (orden Limit)."
    # Referencias del feed / valor técnico: NaN, inf o ≤ 0 NO son una referencia
    # (NaN es verdadero y toda comparación con él da False: antes anulaba la
    # banda de precio y, en Market, también el tope de notional). Se tratan
    # exactamente como "sin referencia" (política explícita de abajo).
    last_ref = _ref_ok(last_ref)
    theo_ref = _ref_ok(theo_ref)
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
    from backend.services import primary_ws
    # El ticket queda atado al contexto de broker con el que se armó: si
    # alguien reconecta (otro host / otra sesión) antes de confirmarlo, `place`
    # lo rechaza en vez de mandarlo al broker nuevo. En una multiorden la
    # versión va en CADA hija (place recibe las hijas sueltas, no el batch).
    ctx = primary_ws.context_version()
    payload["ctx_version"] = ctx
    for hija in (payload.get("batch") or []):
        if isinstance(hija, dict):
            hija["ctx_version"] = ctx
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

# Comitentes cacheados 60 s por host del broker: el panel de Órdenes pollea
# cada 15 s POR usuario y la lista es estática dentro de la sesión — cada poll
# era un round-trip REST al broker (decenas-cientos de ms) sin necesidad. El
# host en la key invalida solo con el hot-swap de /conexion.
_accounts_cache: Optional[tuple] = None
_ACCOUNTS_TTL = 60.0


async def accounts() -> List[Dict[str, Any]]:
    """Comitentes para el panel: MERGE de las configuradas (secret, por broker)
    con las que el broker expone por REST, deduplicadas por número. Si el broker
    falla pero hay configuradas, se muestran igual (no rompe el panel); sin
    configuradas, el error del broker se propaga como hasta ahora."""
    global _accounts_cache
    from backend.services import primary_ws
    # host + versión de contexto: re-login en el mismo host con otras
    # credenciales = otras cuentas; antes la lista vieja sobrevivía 60 s.
    host = (settings.primary_base_url, primary_ws.context_version())
    c = _accounts_cache
    if c is not None and c[0] == host and (time.monotonic() - c[1]) < _ACCOUNTS_TTL:
        return c[2]
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
    out = _merge_comitentes(cfg, broker)
    _accounts_cache = (host, time.monotonic(), out)
    return out


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
    ctx = payload.get("ctx_version")
    if ctx is not None:
        from backend.services import primary_ws
        if int(ctx) != primary_ws.context_version():
            await audit_async("rechazada_contexto", rec)
            return {"status": "RECHAZADA",
                    "motivo": "el broker / la sesión cambió después de armar el ticket — volvé a armarlo",
                    **rec}
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
    # Re-chequeo del kill-switch y del modo JUSTO antes de transmitir: entre el
    # chequeo de entrada y acá hubo esperas (audit, resolve del instrumento —
    # segundos la primera vez) y el freno pudo activarse en el medio; antes la
    # orden salía igual. Sin ningún await entre esta lectura y el envío.
    if _kill["on"]:
        await audit_async("rechazada_kill", {**rec, "etapa": "pre_envio"})
        return {"status": "RECHAZADA", "motivo": "kill-switch activado antes del envío", **rec}
    if not is_live():
        await audit_async("paper_enviada", {**rec, "etapa": "pre_envio"})
        return {"status": "PAPER", "motivo": "modo paper (cambió antes del envío): NO viajó al broker", **rec}
    if ctx is not None:
        # El contexto también se re-chequea acá: un swap de broker durante el
        # audit / resolve (auditoría R02) mandaba el ticket por la conexión
        # nueva. El cliente se toma en la MISMA sentencia que el envío.
        from backend.services import primary_ws as _pws
        if int(ctx) != _pws.context_version():
            await audit_async("rechazada_contexto", {**rec, "etapa": "pre_envio"})
            return {"status": "RECHAZADA",
                    "motivo": "el broker / la sesión cambió mientras se preparaba el envío — volvé a armar el ticket",
                    **rec}
    rec["enviada_ts"] = time.time()          # para la reconciliación: sólo órdenes de después de esto
    try:
        d = await get_ws_client().get_json_checked("rest/order/newSingleOrder", params)
    except Exception as exc:  # noqa: BLE001
        if _resultado_desconocido(exc):
            # El request PUDO llegar al broker (timeout esperando la respuesta,
            # conexión cortada a mitad, HTTP 5xx al serializar la respuesta):
            # no es un error limpio sino un estado DESCONOCIDO — el operador
            # no debe reenviar a ciegas. Se reconcilia en background contra
            # las órdenes del día en el broker.
            await audit_async("live_desconocida", {**rec, "error": str(exc)})
            _spawn(_reconciliar_desconocida(rec))
            return {"status": "DESCONOCIDA",
                    "motivo": (f"sin respuesta válida del broker ({str(exc)[:120]}): la orden PUDO haber "
                               "entrado — verificá en la Matriz / activas antes de reenviar"),
                    **rec}
        await audit_async("live_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}
    o = d.get("order") if isinstance(d, dict) else None
    aceptada = (isinstance(d, dict) and str(d.get("status") or "").upper() == "OK"
                and isinstance(o, dict) and bool(o.get("clientId")))
    if not aceptada:
        # HTTP 200 con JSON de rechazo ({"status":"ERROR","message":…}): antes
        # se auditaba como live_respuesta y el blotter lo dejaba ENVIADA.
        msg = _broker_msg(d)
        await audit_async("live_rechazo_broker", {**rec, "broker": d, "motivo": msg})
        return {"status": "RECHAZADA", "motivo": f"el broker rechazó la orden: {msg}", "broker": d, **rec}
    await audit_async("live_respuesta", {**rec, "broker": d})
    _spawn(_order_followup(str(o["clientId"]), str(o.get("proprietary") or "api"), rec))
    return {"status": "OK", "broker": d, **rec}


def _spawn(coro) -> None:
    t = asyncio.get_running_loop().create_task(coro)
    _followups.add(t)
    t.add_done_callback(_followups.discard)


def _resultado_desconocido(exc: BaseException) -> bool:
    """True si el fallo ocurrió DESPUÉS de que el request pudo salir (el broker
    quizá lo procesó): timeouts de lectura/escritura, conexión cortada,
    protocolo roto, HTTP 5xx, cuerpo vacío o no-JSON. Un ConnectError /
    ConnectTimeout nunca llegó al broker; un 4xx es un rechazo antes de
    procesar (sin sesión, mal formado)."""
    from backend.services.primary_ws import BrokerHTTPError, BrokerRespuestaInvalida
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return False
    if isinstance(exc, BrokerHTTPError):
        return exc.status_code >= 500
    if isinstance(exc, BrokerRespuestaInvalida):
        return True
    return isinstance(exc, (httpx.TimeoutException, httpx.RemoteProtocolError,
                            httpx.ReadError, httpx.WriteError, httpx.CloseError))


def _broker_msg(d: Any) -> str:
    if isinstance(d, dict):
        for k in ("message", "description", "detail", "error", "status"):
            v = d.get(k)
            if v:
                return str(v)[:200]
    return str(d)[:200]


_RECONCILE_DELAYS = (2.0, 6.0)
_RECONCILE_MARGEN_S = 5.0        # tolerancia de reloj entre el server y el broker


def _misma_orden(o: Dict[str, Any], rec: Dict[str, Any]) -> bool:
    """Mismos términos económicos (símbolo, lado, VN, precio si es Limit)."""
    try:
        iid = o.get("instrumentId") if isinstance(o.get("instrumentId"), dict) else {}
        if str(iid.get("symbol") or o.get("symbol") or "") != str(rec.get("symbol") or ""):
            return False
        if str(o.get("side") or "").lower() != str(rec.get("side") or "").lower():
            return False
        if float(o.get("orderQty") or 0) != float(rec.get("qty") or 0):
            return False
        if str(rec.get("ordtype") or "limit") != "market" and rec.get("price") is not None:
            if abs(float(o.get("price") or 0) - float(rec["price"])) > 1e-9:
                return False
        return True
    except (TypeError, ValueError):
        return False


def _ts_orden(o: Dict[str, Any]) -> Optional[float]:
    """Epoch del alta de la orden en el broker (`transactTime`, formato Primary
    'AAAAMMDD-HH:MM:SS.mmm-0300', o ISO). None si no viene / no parsea."""
    raw = o.get("transactTime") or o.get("transactionTime") or o.get("timestamp")
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y%m%d-%H:%M:%S.%f%z", "%Y%m%d-%H:%M:%S%z", "%Y%m%d-%H:%M:%S.%f", "%Y%m%d-%H:%M:%S"):
        try:
            d = datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=_TZ_BA)
            return d.timestamp()
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=_TZ_BA)
        return d.timestamp()
    except ValueError:
        try:
            n = float(s)
            return n / 1000.0 if n > 1e11 else n
        except ValueError:
            return None


def _es_nuestra(o: Dict[str, Any], rec: Dict[str, Any]) -> Optional[bool]:
    """¿La orden del broker es ESTE intento? True si además de los términos su
    alta es posterior al envío (con margen); False si es de antes (una orden
    anterior idéntica, auditoría R01/B04); None si el broker no informa la hora
    — ambiguo, no se atribuye."""
    if not _misma_orden(o, rec):
        return False
    t0 = rec.get("enviada_ts")
    ts = _ts_orden(o)
    if not t0 or ts is None:
        return None
    return ts >= float(t0) - _RECONCILE_MARGEN_S


async def _reconciliar_desconocida(rec: Dict[str, Any]) -> None:
    """Tras una respuesta perdida, busca el intento en el broker y audita SÓLO
    lo que la evidencia permite (auditoría R01):
      · aparece una orden con los mismos términos dada de alta DESPUÉS del
        envío → `live_estado` con su estado real (EN MERCADO / EJECUTADA / …);
      · aparece una con los mismos términos pero sin hora o de antes → sigue
        DESCONOCIDA (`live_desconocida_posible`, con su clientId para mirarla);
      · la lista COMPLETA del día (`rest/order/all`: activas + ejecutadas +
        canceladas + rechazadas) respondió y no está → `live_desconocida_sin_rastro`
        ("NO ENTRÓ (verificado)");
      · sólo respondió `actives` (o ninguna) → no hay prueba: sigue
        DESCONOCIDA (`live_desconocida_no_verificable`) — una orden ejecutada
        al instante no es una activa, y una consulta fallida no es evidencia.
    Best-effort, en background; ante cualquier duda queda DESCONOCIDA."""
    from backend.services.primary_ws import get_ws_client
    cuenta = rec.get("account")
    verificado_todo = False
    for delay in _RECONCILE_DELAYS:
        await asyncio.sleep(delay)
        ambigua: Optional[Dict[str, Any]] = None
        for path in ("rest/order/all", "rest/order/actives"):
            try:
                d = await get_ws_client().get_json_checked(path, {"accountId": cuenta})
            except Exception:  # noqa: BLE001 — sin respuesta no hay evidencia
                continue
            ordenes = d.get("orders", []) if isinstance(d, dict) else None
            if not isinstance(ordenes, list):
                continue
            if path == "rest/order/all":
                verificado_todo = True
            for o in ordenes:
                if not isinstance(o, dict):
                    continue
                v = _es_nuestra(o, rec)
                if v is True:
                    await audit_async("live_estado", {**rec, "estado": str(o.get("status") or "NEW"),
                                                      "texto": "encontrada en el broker tras la respuesta perdida",
                                                      "broker_order_id": o.get("clientId")})
                    return
                if v is None and ambigua is None:
                    ambigua = o
            if path == "rest/order/all":
                break                       # la lista completa alcanza; actives es subconjunto
        if ambigua is not None:
            await audit_async("live_desconocida_posible",
                              {**rec, "texto": ("hay una orden con los mismos términos pero sin hora de alta "
                                                "(¿anterior?): verificá antes de reenviar"),
                               "broker_order_id": ambigua.get("clientId")})
            return
    if verificado_todo:
        await audit_async("live_desconocida_sin_rastro",
                          {**rec, "texto": "no está en la lista completa de órdenes del día del broker "
                                           f"({len(_RECONCILE_DELAYS)} consultas): no entró"})
    else:
        await audit_async("live_desconocida_no_verificable",
                          {**rec, "texto": "no se pudo consultar la lista completa del día en el broker: "
                                           "sigue DESCONOCIDA — verificá en la Matriz antes de reenviar"})


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
    except Exception as exc:  # noqa: BLE001
        await audit_async("live_cancel_error", {**rec, "error": str(exc)})
        return {"status": "ERROR", "motivo": str(exc), **rec}
    if isinstance(d, dict) and str(d.get("status") or "").upper() == "OK":
        # OK = el broker ACEPTÓ el pedido de cancelar; el estado final lo
        # confirma el seguimiento / la Matriz (CANCELLED), no esta respuesta.
        await audit_async("live_cancel_respuesta", {**rec, "broker": d})
        return {"status": "OK", "broker": d, **rec}
    # HTTP 200 con JSON de rechazo: la orden SIGUE VIVA. Antes se auditaba
    # como live_cancel_respuesta y el blotter la mostraba CANCELADA (R03).
    msg = _broker_msg(d)
    await audit_async("live_cancel_rechazo", {**rec, "broker": d, "motivo": msg})
    return {"status": "ERROR", "motivo": f"el broker rechazó la cancelación: {msg}", "broker": d, **rec}
