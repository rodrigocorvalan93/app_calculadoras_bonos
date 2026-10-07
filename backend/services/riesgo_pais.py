"""Riesgo país (EMBI+ Argentina, JP Morgan) para la tarjeta Mercado de Inicio.

Fuente: ArgentinaDatos (api.argentinadatos.com — la misma API pública que usa
`tools/backfill_fx.py`):

    /v1/finanzas/indices/riesgo-pais/ultimo  → {"fecha": "AAAA-MM-DD", "valor": n}
    /v1/finanzas/indices/riesgo-pais         → [{"fecha": …, "valor": …}, …] (serie)

El dato es DIARIO (JP Morgan lo publica al cierre de Nueva York; la API lo
refleja con horas de demora), así que se baja en un THREAD DE FONDO cada 30
minutos — NUNCA en un request — y la historia reciente queda en
`data/riesgo_pais.json` (fuera de git, como `escenario_prefs.json`): la
variación contra la observación anterior sobrevive al reinicio y sin red se
muestra el último valor guardado con su fecha. En el primer arranque (menos
de dos puntos locales) se baja la serie completa UNA vez para tener el previo;
después sólo `/ultimo`.

    RIESGO_PAIS=0          apaga el poller (la suite corre así; snapshot() sigue
                           leyendo el archivo local)
    RIESGO_PAIS_URL=…      base de la API (default ArgentinaDatos)
    RIESGO_PAIS_PATH=…     archivo local (default data/riesgo_pais.json)

`snapshot()` es lectura de memoria (µs) y nunca lanza.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("backend.riesgo_pais")

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = REPO_ROOT / "data" / "riesgo_pais.json"
_DEFAULT_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
_KEEP = 60                   # observaciones que se guardan (≈ 3 meses de ruedas)
_REFRESH_OK_S = 30 * 60      # dato diario: cada 30 min sobra
_REFRESH_FAIL_S = 10 * 60    # sin red: reintento suave
_TIMEOUT = 20

Punto = Tuple[str, float]    # (fecha ISO, valor en puntos básicos)

_lock = threading.Lock()
_state: Dict[str, Any] = {"puntos": [], "fuente": None, "actualizado": None,
                          "error": None, "cargado": False}
_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def _path() -> Path:
    return Path(os.getenv("RIESGO_PAIS_PATH") or _DEFAULT_PATH)


def _url() -> str:
    return (os.getenv("RIESGO_PAIS_URL") or _DEFAULT_URL).rstrip("/")


def habilitado() -> bool:
    return (os.getenv("RIESGO_PAIS") or "1").strip().lower() not in ("0", "false", "no", "off")


# ── parseo ───────────────────────────────────────────────────────────────────
def _parse_punto(obj: Any) -> Optional[Punto]:
    if not isinstance(obj, dict):
        return None
    f = str(obj.get("fecha") or "")[:10]
    try:
        date.fromisoformat(f)
    except ValueError:
        return None
    try:
        v = float(obj.get("valor"))
    except (TypeError, ValueError):
        return None
    if v != v or v <= 0:                         # NaN / cero / negativo: basura
        return None
    return f, v


def parsear(payload: Any) -> List[Punto]:
    """Serie (lista de {fecha, valor}) o un solo punto → puntos ordenados por
    fecha, sin duplicados (la última entrada de una fecha gana). Ítems raros
    se saltean."""
    items = payload if isinstance(payload, list) else [payload]
    por_fecha: Dict[str, float] = {}
    for it in items:
        p = _parse_punto(it)
        if p is not None:
            por_fecha[p[0]] = p[1]
    return sorted(por_fecha.items())


# ── archivo local ────────────────────────────────────────────────────────────
def _leer_archivo() -> List[Punto]:
    p = _path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001 — ilegible/corrupto: arrancamos sin historia
        logger.warning("[riesgo_pais] %s ilegible (%s); arranco sin historia local", p.name, exc)
        return []
    return parsear(raw.get("puntos") if isinstance(raw, dict) else raw)


def _escribir_archivo(puntos: List[Punto]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"puntos": [{"fecha": f, "valor": v} for f, v in puntos]},
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _ensure_cargado_locked() -> None:
    if _state["cargado"]:
        return
    _state["puntos"] = _leer_archivo()[-_KEEP:]
    _state["cargado"] = True
    if _state["puntos"]:
        _state["fuente"] = "archivo"


def _merge(nuevos: List[Punto], fuente: Optional[str]) -> bool:
    """Incorpora puntos (por fecha, los nuevos ganan) y persiste si cambió algo.
    True si la serie cambió."""
    with _lock:
        _ensure_cargado_locked()
        d = dict(_state["puntos"])
        d.update(dict(nuevos))
        pts = sorted(d.items())[-_KEEP:]
        cambio = pts != _state["puntos"]
        _state["puntos"] = pts
        if fuente:
            _state["fuente"] = fuente
            _state["actualizado"] = time.time()
            _state["error"] = None
    if cambio:
        try:
            _escribir_archivo(pts)
        except OSError as exc:
            logger.warning("[riesgo_pais] no pude guardar %s: %s", _path(), exc)
    return cambio


# ── red ──────────────────────────────────────────────────────────────────────
def _ssl_ctx():
    """Bundle de certifi si está (el Python de python.org en macOS trae el
    store de CAs vacío — mismo patrón que services/ust.py)."""
    try:
        import ssl

        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None


def _fetch(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (app-calculadoras-bonos)",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx()) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def refresh() -> bool:
    """UNA pasada (bloqueante, con red): la serie completa si todavía no hay
    dos puntos locales (hace falta el previo para la variación), si no sólo el
    último. True si hubo dato nuevo. Nunca lanza: el error queda en el estado."""
    with _lock:
        _ensure_cargado_locked()
        n = len(_state["puntos"])
    base = _url()
    try:
        if n < 2:
            pts = parsear(_fetch(base))[-_KEEP:]
        else:
            pts = parsear(_fetch(base + "/ultimo"))
        if not pts:
            raise ValueError("respuesta sin puntos")
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state["error"] = f"{exc.__class__.__name__}: {exc}"
        logger.warning("[riesgo_pais] fetch falló: %s", exc)
        return False
    cambio = _merge(pts, "argentinadatos")
    if cambio:
        f, v = pts[-1]
        logger.info("[riesgo_pais] %s: %.0f pb", f, v)
    return cambio


def _loop() -> None:
    while not _stop.is_set():
        ok = refresh()
        if _stop.wait(_REFRESH_OK_S if ok or _state.get("error") is None else _REFRESH_FAIL_S):
            break


def start() -> None:
    """Arranca el poller (idempotente). Thread daemon: nunca bloquea requests."""
    global _thread
    if not habilitado():
        logger.info("[riesgo_pais] deshabilitado (RIESGO_PAIS=0): se muestra el último dato guardado")
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="riesgo-pais", daemon=True)
        _thread.start()


def stop() -> None:
    _stop.set()


# ── lectura ──────────────────────────────────────────────────────────────────
def _ar(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if len(iso) >= 10 else iso


def snapshot() -> Dict[str, Any]:
    """Último valor con su fecha y la variación contra la observación anterior
    (puntos y %). Todo None si nunca hubo dato. Lectura de memoria, nunca lanza."""
    with _lock:
        _ensure_cargado_locked()
        pts = list(_state["puntos"])
        fuente, error, act = _state["fuente"], _state["error"], _state["actualizado"]
    out: Dict[str, Any] = {"valor": None, "fecha": None, "fecha_iso": None, "previo": None,
                           "fecha_previa": None, "var": None, "var_pct": None,
                           "fuente": fuente, "error": error, "actualizado": act}
    if not pts:
        return out
    f, v = pts[-1]
    out.update(valor=v, fecha=_ar(f), fecha_iso=f)
    if len(pts) >= 2:
        f0, v0 = pts[-2]
        out.update(previo=v0, fecha_previa=_ar(f0), var=v - v0,
                   var_pct=(v / v0 - 1.0) if v0 else None)
    return out


def reset_para_tests() -> None:
    with _lock:
        _state.update(puntos=[], fuente=None, actualizado=None, error=None, cargado=False)
