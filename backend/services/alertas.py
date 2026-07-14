"""Alertas de precio/TIR — sólo superuser.

Modelo simple de mesa: cada alerta es un umbral one-shot sobre un bono
(`precio` del mercado o `tirea` calculada) con operador ≥ / ≤. Un chequeo
en background (cada ~30 s, en el threadpool — nunca en el event loop)
compara contra el último dato del store; si cruza, la alerta se marca
DISPARADA (queda visible con valor y hora) y, si tiene mail, se envía por
`mailer.send`. No se re-arma sola: el rearme es manual desde la UI, así
un precio oscilando alrededor del umbral no spamea.

Persistencia: `data/alertas.json` (fuera de git, mismo patrón que
`escenario_prefs`). El archivo es chico (~KB) y se lee por chequeo — el
costo (~µs, en thread) no toca el hot path de requests; a cambio, editar
las alertas desde otra máquina (carpeta sincronizada) las levanta solo.

Unidades: `precio` en la misma unidad que la columna Last de Curvas (el
precio de mercado crudo del feed); `tirea` en % (12,5 = 12,5% TIREA), que
es como se muestra en toda la app.
"""
from __future__ import annotations

import json
import logging
import math
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("backend.alertas")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = REPO_ROOT / "data" / "alertas.json"
_lock = threading.Lock()
_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

METRICS = ("precio", "tirea")
OPS = (">=", "<=")
_MAX_ALERTAS = 50

CHECK_EVERY_SECONDS = 30.0


def _path() -> Path:
    return Path(os.getenv("ALERTAS_PATH") or _DEFAULT_PATH)


# ── persistencia ────────────────────────────────────────────────────────────
def _sane(a: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(a, dict):
        return None
    try:
        code = str(a["code"]).strip().upper()
        metric = str(a["metric"])
        op = str(a["op"])
        valor = float(a["valor"])
    except (KeyError, TypeError, ValueError):
        return None
    if not code or metric not in METRICS or op not in OPS or not math.isfinite(valor):
        return None
    return {
        "id": str(a.get("id") or secrets.token_hex(4)),
        "code": code, "metric": metric, "op": op, "valor": valor,
        "email": str(a.get("email") or "").strip(),
        "activa": bool(a.get("activa", True)),
        "disparada_at": a.get("disparada_at") or None,
        "disparada_valor": a.get("disparada_valor"),
        "creada": a.get("creada") or "",
    }


def _load() -> List[Dict[str, Any]]:
    p = _path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("[alertas] archivo ilegible; arranco vacío")
        return []
    raw = data.get("alertas") if isinstance(data, dict) else None
    return [s for a in (raw or []) if (s := _sane(a)) is not None]


def _write(alertas: List[Dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"alertas": alertas}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def list_alertas() -> List[Dict[str, Any]]:
    with _lock:
        return _load()


# ── CRUD ────────────────────────────────────────────────────────────────────
def add(code: str, metric: str, op: str, valor: float, email: str = "") -> Optional[str]:
    """Alta. Devuelve None si OK o el motivo del rechazo (es-AR, para la UI)."""
    code = (code or "").strip().upper()
    if not code:
        return "Falta el código del bono."
    from backend.services import bond_universe
    bond_universe.ensure_loaded()
    if bond_universe.get(code) is None:
        return f"Código desconocido: {code}."
    if metric not in METRICS:
        return "Métrica inválida."
    if op not in OPS:
        return "Operador inválido."
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = float("nan")
    if not math.isfinite(v):
        return "Valor inválido."
    with _lock:
        alertas = _load()
        if len(alertas) >= _MAX_ALERTAS:
            return f"Máximo {_MAX_ALERTAS} alertas."
        alertas.append({
            "id": secrets.token_hex(4),
            "code": code, "metric": metric, "op": op, "valor": v,
            "email": (email or "").strip(),
            "activa": True, "disparada_at": None, "disparada_valor": None,
            "creada": datetime.now(_TZ).isoformat(timespec="seconds"),
        })
        _write(alertas)
    return None


def delete(alert_id: str) -> bool:
    with _lock:
        alertas = _load()
        keep = [a for a in alertas if a["id"] != alert_id]
        if len(keep) == len(alertas):
            return False
        _write(keep)
        return True


def rearm(alert_id: str) -> bool:
    """Re-arma una alerta disparada (vuelve a vigilar el mismo umbral)."""
    with _lock:
        alertas = _load()
        for a in alertas:
            if a["id"] == alert_id:
                a["activa"] = True
                a["disparada_at"] = None
                a["disparada_valor"] = None
                _write(alertas)
                return True
        return False


# ── valores actuales + chequeo ──────────────────────────────────────────────
def current_value(code: str, metric: str) -> Optional[float]:
    """Valor vigente de la métrica para un código, desde el store (last, si no
    cierre). TIR vía `metrics_for_market_price` (cacheada — el warmup la
    mantiene caliente para las curvas, acá casi siempre es un hit). None si no
    hay dato usable."""
    from backend.services import marketdata_store as mds, pricing
    from backend.services import symbols as syms

    snap = mds.get_store().get(syms.md_symbol(code, "24hs"))
    px = None
    if snap is not None:
        px = snap.last if snap.last is not None else snap.close
    if px is None:
        return None
    if metric == "precio":
        return float(px)
    m = pricing.metrics_for_market_price(code, px)
    t = (m or {}).get("tirea")
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    return t * 100.0 if math.isfinite(t) else None


def _cruza(cur: float, op: str, umbral: float) -> bool:
    return cur >= umbral if op == ">=" else cur <= umbral


def _notificar(a: Dict[str, Any], cur: float) -> None:
    if not a.get("email"):
        return
    from backend.locale_ar import JINJA_FILTERS
    from backend.services import mailer
    if not mailer.is_configured():
        logger.warning("[alertas] %s disparada pero SMTP no configurado (sin mail)", a["code"])
        return
    num = lambda v: JINJA_FILTERS["ar_num"](v, 2)  # noqa: E731
    met = "precio" if a["metric"] == "precio" else "TIREA"
    suf = "" if a["metric"] == "precio" else "%"
    subject = f"Alerta {a['code']}: {met} {num(cur)}{suf} ({a['op']} {num(a['valor'])}{suf})"
    body = (f"Alerta de bono disparada.\n\n"
            f"Bono: {a['code']}\n"
            f"Condición: {met} {a['op']} {num(a['valor'])}{suf}\n"
            f"Valor actual: {num(cur)}{suf}\n"
            f"Hora: {datetime.now(_TZ).strftime('%d/%m/%Y %H:%M')} (BA)\n\n"
            f"La alerta quedó desactivada; se re-arma desde la pestaña Alertas.")
    ok, detail = mailer.send(a["email"], subject, body)
    if not ok:
        logger.warning("[alertas] mail de %s falló: %s", a["code"], detail)


def check_once() -> int:
    """Un pase de chequeo (sync — correr en executor). Evalúa las alertas
    ACTIVAS contra el store, dispara las que cruzan y persiste. Devuelve
    cuántas disparó. Sin alertas activas sale al toque (~µs + un stat)."""
    with _lock:
        alertas = _load()
    activas = [a for a in alertas if a["activa"]]
    if not activas:
        return 0
    fired: Dict[str, float] = {}
    for a in activas:
        try:
            cur = current_value(a["code"], a["metric"])
        except Exception:  # noqa: BLE001
            logger.exception("[alertas] chequeo de %s falló", a["code"])
            continue
        if cur is not None and _cruza(cur, a["op"], a["valor"]):
            fired[a["id"]] = cur
    if not fired:
        return 0
    now = datetime.now(_TZ).isoformat(timespec="seconds")
    with _lock:
        alertas = _load()                      # releer: pudo haber CRUD en el medio
        tocadas = []
        for a in alertas:
            if a["id"] in fired and a["activa"]:
                a["activa"] = False
                a["disparada_at"] = now
                a["disparada_valor"] = fired[a["id"]]
                tocadas.append(a)
        if tocadas:
            _write(alertas)
    for a in tocadas:
        logger.info("[alertas] DISPARADA %s %s %s %s (actual %s)",
                    a["code"], a["metric"], a["op"], a["valor"], a["disparada_valor"])
        _notificar(a, a["disparada_valor"])
    return len(tocadas)
