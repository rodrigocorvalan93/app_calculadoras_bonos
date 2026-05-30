"""Specs de instrumento (lámina mínima / tick / límites) — REST cacheado.

`rest/instruments/detail?marketId=ROFX&symbol=<symbol>` devuelve el
instrumento; sus specs son estáticas, así que se cachean por símbolo (para
toda la sesión). Usa el cliente REST autenticado del WS (cookies del login).
Failure-silent: si el broker no está logueado o el campo no viene, None.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple

_lock = threading.Lock()
_cache: Dict[str, Optional[Dict[str, Any]]] = {}

# Nombres posibles en Primary (defensivo: varían entre versiones).
_LAMINA_KEYS: Tuple[str, ...] = ("minTradeVol", "roundLot", "minLot", "lotSize", "minSize")
_TICK_KEYS: Tuple[str, ...] = ("minPriceIncrement", "tickSize", "priceIncrement")


def _num(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _extract(inst: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lamina": _num(inst, _LAMINA_KEYS),
        "tick": _num(inst, _TICK_KEYS),
        "low_limit": _num(inst, ("lowLimitPrice",)),
        "high_limit": _num(inst, ("highLimitPrice",)),
        "currency": inst.get("currency"),
    }


async def detail(symbol: str) -> Optional[Dict[str, Any]]:
    if not symbol:
        return None
    with _lock:
        if symbol in _cache:
            return _cache[symbol]
    from backend.services.primary_ws import get_ws_client

    data = await get_ws_client().get_json(
        "rest/instruments/detail", {"marketId": "ROFX", "symbol": symbol}
    )
    inst = (data or {}).get("instrument") if isinstance(data, dict) else None
    result = _extract(inst) if isinstance(inst, dict) else None
    with _lock:
        _cache[symbol] = result
    return result
