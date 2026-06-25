"""Specs de instrumento (lámina mínima / tick / límites) — REST cacheado.

`rest/instruments/detail?marketId=ROFX&symbol=<symbol>` devuelve el
instrumento; sus specs son estáticas, así que se cachean por símbolo (para
toda la sesión). Usa el cliente REST autenticado del WS (cookies del login).
Failure-silent: si el broker no está logueado o el campo no viene, None.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.config import settings

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
        if result is not None:           # NO cachear el fallo transitorio (broker offline /
            _cache[symbol] = result      # pre-login): antes quedaba None fijo hasta reiniciar
    return result


# ── Universo de instrumentos del broker (validación de símbolo pre-trade) ──
# `rest/instruments/all` lista TODOS los instrumentos negociables del broker
# (símbolo + plazo + segmento). Lo usamos para no mandar una orden a un símbolo
# que el broker no tiene —p. ej. una ON que sólo cotiza SENEBI o en otro plazo—:
# así el "Invalid Instrument ... doesn't exist" se convierte en un aviso
# pre-trade accionable con los símbolos/plazos que SÍ existen para ese código.
# El universo es estático en la sesión ⇒ se cachea (por host, para invalidar
# solo con el hot-swap de broker de /conexion). Failure-OPEN: si no se puede
# traer la lista (sin login / error), `valid_symbols` da None y NADIE bloquea.
_sym_lock = threading.Lock()
_sym_cache: Optional[Set[str]] = None
_sym_cache_host: Optional[str] = None


def _instrument_symbol(inst: Any) -> Optional[str]:
    """Símbolo negociable de un instrumento crudo de `rest/instruments/all`
    (defensivo: el símbolo viene anidado en `instrumentId` o plano en `symbol`)."""
    if not isinstance(inst, dict):
        return None
    iid = inst.get("instrumentId")
    if isinstance(iid, dict) and iid.get("symbol"):
        return str(iid["symbol"]).strip()
    s = inst.get("symbol")
    return str(s).strip() if s else None


async def valid_symbols() -> Optional[Set[str]]:
    """Set de símbolos negociables del broker activo, cacheado por sesión/host.
    None si no se pudo traer (sin login / error / vacío) ⇒ el llamador NO debe
    bloquear (fail-open)."""
    global _sym_cache, _sym_cache_host
    host = settings.primary_base_url
    with _sym_lock:
        if _sym_cache is not None and _sym_cache_host == host:
            return _sym_cache
    from backend.services.primary_ws import get_ws_client

    try:
        data = await get_ws_client().get_json("rest/instruments/all")
    except Exception:  # noqa: BLE001 — fail-open: nunca rompas el envío por esto
        return None
    items = (data or {}).get("instruments") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return None                         # no cacheamos el fallo: reintenta al próximo login
    syms = {s for s in (_instrument_symbol(it) for it in items) if s}
    if not syms:
        return None
    with _sym_lock:
        _sym_cache, _sym_cache_host = syms, host
    return syms


def reset_symbols_cache() -> None:
    """Invalida el cache del universo (tests / reconexión manual)."""
    global _sym_cache, _sym_cache_host
    with _sym_lock:
        _sym_cache = _sym_cache_host = None


def match_candidates(symbols: Set[str], code: str, limit: int = 12) -> List[str]:
    """Símbolos del broker cuyo código coincide con `code` (o comparte raíz).
    El código BYMA es el 3er token de `MERV - XMEV - <cod> - <plazo>[ - <seg>]`.
    Primero match EXACTO del código; si no hay, por raíz (4 letras) para sugerir
    series/patas hermanas. Ordenado y acotado a `limit`."""
    from backend.services.symbols import calc_to_md_code

    base = calc_to_md_code(code).strip().upper()
    if not base:
        return []
    stem = base[:4]
    exact: List[str] = []
    prefix: List[str] = []
    for s in symbols:
        toks = [t.strip().upper() for t in s.split(" - ")]
        cod = toks[2] if len(toks) >= 3 and toks[0] == "MERV" else (toks[0] if toks else "")
        if cod == base:
            exact.append(s)
        elif stem and cod.startswith(stem):
            prefix.append(s)
    return sorted(set(exact or prefix))[:limit]


async def resolve(code: str, symbol: str) -> Dict[str, Any]:
    """¿El broker tiene `symbol` en su universo? Devuelve
    {checked, exists, symbol, candidates}. `checked=False` ⇒ no se pudo
    verificar (sin lista) ⇒ el llamador no debe bloquear (fail-open)."""
    syms = await valid_symbols()
    if syms is None:
        return {"checked": False, "exists": False, "symbol": symbol, "candidates": []}
    exists = symbol in syms
    cands = [] if exists else match_candidates(syms, code)
    return {"checked": True, "exists": exists, "symbol": symbol, "candidates": cands}
