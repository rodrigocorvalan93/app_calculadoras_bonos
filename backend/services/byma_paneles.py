"""Membresía VIVA de los paneles de equities — BYMA Open Data (pública).

Qué acción está en el panel Líder y cuál en el General (y el universo de
CEDEARs) lo define BYMA, no el broker — y lo rota ~1 vez por año. Este
servicio consulta los endpoints "free" de open.bymadata.com.ar (los mismos
que usa la web de BYMA, sin auth ni credenciales) y cachea la membresía en
memoria; `equities` la usa con FALLBACK TOTAL a sus listas curadas: sin red
(tests/CI, proxy caído, BYMA en mantenimiento) la app queda exactamente
como antes.

El refresh corre 1×/día desde un task del lifespan (en el threadpool — acá
todo es sync/requests) y, si aparecieron tickers nuevos, el task suscribe la
diferencia al WS del broker en caliente (ws.subscribe es incremental).

Nota TLS: la cadena del sitio de BYMA viene incompleta desde hace años (le
falta el intermedio); se intenta primero con verificación normal (certifi) y
sólo ante un error de SSL se reintenta sin verificar ESTE request — es data
pública de solo lectura, no viaja ninguna credencial, y el peor caso de un
MITM es una lista de tickers falsa que igual pasa por el fallback curado.
"""
from __future__ import annotations

import logging
import threading
import warnings
from typing import Dict, List, Optional

logger = logging.getLogger("backend.byma_paneles")

_BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
# panel → endpoint free de BYMA Open Data
_EPS = {"lideres": "leading-equity", "general": "general-equity", "cedears": "cedears"}
_TIMEOUT = 8.0

_lock = threading.Lock()
_cache: Dict[str, List[str]] = {}          # panel → tickers (ausente = sin dato aún)


def _extract_symbols(data) -> Optional[List[str]]:
    """Los endpoints devuelven una lista de dicts (o {"data": [...]}) con el
    ticker en `symbol`. Cambios de shape → None (fallback curado, sin drama)."""
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None
    out = set()
    for row in rows:
        if isinstance(row, dict):
            sym = str(row.get("symbol") or "").strip().upper()
            # los endpoints de equity a veces listan también el plazo/settlement
            # en el símbolo ("GGAL - 0003-C-CT-ARS"): nos quedamos con el ticker
            if sym:
                out.add(sym.split(" ")[0].split("-")[0].strip())
    out.discard("")
    return sorted(out) or None


def _fetch_panel(session, ep: str) -> Optional[List[str]]:
    body = {"excludeZeroPxAndQty": False, "T2": False, "T1": True, "T0": False}
    try:
        r = session.post(_BASE + ep, json=body, timeout=_TIMEOUT)
        r.raise_for_status()
        return _extract_symbols(r.json())
    except Exception as exc:  # noqa: BLE001
        import requests
        if isinstance(exc, requests.exceptions.SSLError):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")     # InsecureRequestWarning
                    r = session.post(_BASE + ep, json=body, timeout=_TIMEOUT, verify=False)
                r.raise_for_status()
                return _extract_symbols(r.json())
            except Exception as exc2:  # noqa: BLE001
                logger.warning("[byma_paneles] %s falló (aún sin verify): %s", ep, exc2)
                return None
        logger.warning("[byma_paneles] %s falló: %s", ep, exc)
        return None


def refresh() -> Dict[str, int]:
    """Consulta los 3 paneles y actualiza el cache con los que respondieron
    (parcial es válido: un endpoint caído no borra lo que ya se sabía).
    Devuelve {panel: n} de lo actualizado — {} = quedó todo en fallback."""
    import requests
    s = requests.Session()
    got: Dict[str, List[str]] = {}
    for panel, ep in _EPS.items():
        rows = _fetch_panel(s, ep)
        if rows:
            got[panel] = rows
    if got:
        with _lock:
            _cache.update(got)
        logger.info("[byma_paneles] membresía actualizada: %s",
                    {k: len(v) for k, v in got.items()})
    return {k: len(v) for k, v in got.items()}


def tickers(panel: str) -> Optional[List[str]]:
    """Membresía viva del panel, o None si todavía no hay dato (→ fallback)."""
    with _lock:
        v = _cache.get(panel)
        return list(v) if v else None
