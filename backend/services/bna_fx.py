"""Dólar del Banco Nación (BNA) para el add-in de Excel — =OMS.FX("bna_…") (07/10).

Lo pidió el desk SÓLO para Excel: dólar BNA **divisa** (compra / venta) y
**billete** (compra / venta), con la fecha del dato, refrescado 1×/hora.

Fuente: las páginas públicas de cotizaciones del BNA — no hay API:
    https://www.bna.com.ar/Personas   → tabla "Billetes" (`id="billetes"`)
    https://www.bna.com.ar/Empresas   → tabla "Divisas"  (`id="divisas"`)
Cada tabla tiene la fila "Dolar U.S.A" con compra y venta (es-AR: "1.395,0000")
y la fecha del dato "DD/MM/AAAA" al lado. Se parsea con expresiones TOLERANTES
(`parsear`): el bloque desde el `id` hasta el cierre de su tabla, la fila del
dólar y la primera fecha del bloque (si no hay, la primera de la página).

Se baja en un THREAD DE FONDO cada hora (10 min si falló) — NUNCA en un
request — y el último dato queda en `data/bna_fx.json` (fuera de git): al
arrancar se sirve el de la última corrida hasta que el poller traiga uno nuevo,
y sin red se sigue mostrando con su fecha. El snapshot de Excel toma
`snapshot()` de memoria (µs).

    BNA_FX=0           apaga el poller (la suite corre así; snapshot() sigue leyendo el archivo)
    BNA_FX_URLS=a,b    páginas a parsear (default Personas + Empresas)
    BNA_FX_PATH=…      archivo local (default data/bna_fx.json)
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.bna_fx")

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = REPO_ROOT / "data" / "bna_fx.json"
_DEFAULT_URLS = ("https://www.bna.com.ar/Personas", "https://www.bna.com.ar/Empresas")
_REFRESH_OK_S = 60 * 60      # el desk pidió 1×/hora (BNA cambia un par de veces por día)
_REFRESH_FAIL_S = 10 * 60
_TIMEOUT = 20

SECCIONES = (("billetes", "billete"), ("divisas", "divisa"))   # (id en el HTML, clave nuestra)

_lock = threading.Lock()
_state: Dict[str, Any] = {"billete": None, "divisa": None, "actualizado": None,
                          "fuente": None, "error": None, "cargado": False}
_stop = threading.Event()
_thread: Optional[threading.Thread] = None

# Fila "Dolar U.S.A" (también "Dólar U.S.A." / "Dolar USA"): el resto de SU celda,
# y las dos celdas numéricas es-AR que la siguen de inmediato — nada de saltar a
# la fila siguiente (con "n/d" en el dólar tomaba los números del euro).
_NUM = r"([\d\.]*\d,\d+|\d+)"
_ROW = re.compile(r"D[oó]lar\s+U\.?\s*S\.?\s*A\.?[^<]*</td>\s*<td[^>]*>\s*" + _NUM + r"\s*</td>\s*<td[^>]*>\s*" + _NUM + r"\s*</td>",
                  re.S | re.I)
_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _path() -> Path:
    return Path(os.getenv("BNA_FX_PATH") or _DEFAULT_PATH)


def _urls() -> List[str]:
    raw = os.getenv("BNA_FX_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return list(_DEFAULT_URLS)


def habilitado() -> bool:
    return (os.getenv("BNA_FX") or "1").strip().lower() not in ("0", "false", "no", "off")


# ── parseo ───────────────────────────────────────────────────────────────────
def _num(s: str) -> float:
    """'1.395,0000' / '1395,5' / '1395' → float (es-AR: punto miles, coma decimal)."""
    return float(s.replace(".", "").replace(",", "."))


def _fecha_iso(seg: str, pagina: str) -> Optional[str]:
    for texto in (seg, pagina):
        for m in _FECHA.finditer(texto):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                continue
    return None


def parsear(html: str) -> Dict[str, Dict[str, Any]]:
    """{'billete': {compra, venta, fecha}, 'divisa': {...}} con lo que haya en
    la página (puede traer una sola sección). Valores no positivos o fila
    ausente → la sección se saltea; sin fecha parseable → fecha None."""
    out: Dict[str, Dict[str, Any]] = {}
    if not html:
        return out
    for id_html, clave in SECCIONES:
        i = html.find(f'id="{id_html}"')
        if i < 0:
            i = html.find(f"id='{id_html}'")
        if i < 0:
            continue
        j = html.find("</table>", i)
        seg = html[i:(j if j > 0 else len(html)) + 600]
        m = _ROW.search(seg)
        if not m:
            continue
        try:
            compra, venta = _num(m.group(1)), _num(m.group(2))
        except ValueError:
            continue
        if not (compra > 0 and venta > 0 and venta >= compra * 0.9):
            continue
        out[clave] = {"compra": compra, "venta": venta, "fecha": _fecha_iso(seg, html)}
    return out


# ── archivo local ────────────────────────────────────────────────────────────
def _sane(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    try:
        c, v = float(raw.get("compra")), float(raw.get("venta"))
    except (TypeError, ValueError):
        return None
    if not (c > 0 and v > 0):
        return None
    f = raw.get("fecha")
    try:
        f = date.fromisoformat(str(f)[:10]).isoformat() if f else None
    except ValueError:
        f = None
    return {"compra": c, "venta": v, "fecha": f}


def _leer_archivo() -> Dict[str, Any]:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[bna_fx] %s ilegible (%s); arranco sin dato", _path().name, exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {"billete": _sane(raw.get("billete")), "divisa": _sane(raw.get("divisa")),
            "actualizado": raw.get("actualizado")}


def _escribir_archivo() -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    with _lock:
        payload = {"billete": _state["billete"], "divisa": _state["divisa"], "actualizado": _state["actualizado"]}
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _ensure_cargado_locked() -> None:
    if _state["cargado"]:
        return
    d = _leer_archivo()
    _state["billete"], _state["divisa"] = d.get("billete"), d.get("divisa")
    _state["actualizado"] = d.get("actualizado")
    _state["cargado"] = True
    if _state["billete"] or _state["divisa"]:
        _state["fuente"] = "archivo"


# ── red ──────────────────────────────────────────────────────────────────────
def _ssl_ctx():
    try:
        import ssl

        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (app-calculadoras-bonos)",
                                               "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx()) as resp:
        return resp.read().decode("utf-8", "replace")


def refresh() -> bool:
    """UNA pasada (bloqueante, con red) por las páginas configuradas. True si
    alguna sección cambió. Nunca lanza: el error queda en el estado."""
    with _lock:
        _ensure_cargado_locked()
    nuevo: Dict[str, Dict[str, Any]] = {}
    errores: List[str] = []
    for url in _urls():
        try:
            for k, v in parsear(_fetch(url)).items():
                nuevo.setdefault(k, v)
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{url}: {exc.__class__.__name__}: {exc}")
    if not nuevo:
        with _lock:
            _state["error"] = "; ".join(errores) or "sin fila 'Dolar U.S.A' en las páginas"
        logger.warning("[bna_fx] sin dato: %s", _state["error"])
        return False
    with _lock:
        cambio = any(_state.get(k) != v for k, v in nuevo.items())
        for k, v in nuevo.items():
            _state[k] = v
        _state["actualizado"] = time.time()
        _state["fuente"] = "bna.com.ar"
        _state["error"] = "; ".join(errores) or None
    if cambio:
        try:
            _escribir_archivo()
        except OSError as exc:
            logger.warning("[bna_fx] no pude guardar %s: %s", _path(), exc)
        logger.info("[bna_fx] %s", " · ".join(f"{k} {v['compra']:.2f}/{v['venta']:.2f} ({v['fecha']})" for k, v in nuevo.items()))
    return cambio


def _loop() -> None:
    while not _stop.is_set():
        refresh()
        with _lock:
            ok = _state["error"] is None and (_state["billete"] or _state["divisa"])
        if _stop.wait(_REFRESH_OK_S if ok else _REFRESH_FAIL_S):
            break


def start() -> None:
    """Arranca el poller horario (idempotente). Thread daemon: nunca bloquea requests."""
    global _thread
    if not habilitado():
        logger.info("[bna_fx] deshabilitado (BNA_FX=0): se sirve el último dato guardado")
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="bna-fx", daemon=True)
        _thread.start()


def stop() -> None:
    _stop.set()


# ── lectura ──────────────────────────────────────────────────────────────────
def snapshot() -> Dict[str, Any]:
    """Sección `bna` del snapshot de Excel: compra / venta / fecha (ISO) de
    billete y divisa + metadatos. Lectura de memoria, nunca lanza."""
    with _lock:
        _ensure_cargado_locked()
        b, d = _state["billete"], _state["divisa"]
        out = {"billete_compra": None, "billete_venta": None, "billete_fecha": None,
               "divisa_compra": None, "divisa_venta": None, "divisa_fecha": None,
               "actualizado": _state["actualizado"], "fuente": _state["fuente"], "error": _state["error"]}
        if b:
            out.update(billete_compra=b["compra"], billete_venta=b["venta"], billete_fecha=b["fecha"])
        if d:
            out.update(divisa_compra=d["compra"], divisa_venta=d["venta"], divisa_fecha=d["fecha"])
        return out


def reset_para_tests() -> None:
    with _lock:
        _state.update(billete=None, divisa=None, actualizado=None, fuente=None, error=None, cargado=False)
