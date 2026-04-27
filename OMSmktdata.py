#%%
"""Descarga masiva y normalización de datos de mercado.

OPTIMIZACIÓN (04/2026):
- Blacklist temporal de símbolos muertos (TTL 10 min) → evita reintentar
  símbolos que no operan ese día y estaban generando ~300 requests inútiles
  cada 15s. Speedup típico: latencia de ciclo baja de 5-8s a <1s.
- Distinción "body vacío" vs "error real": los primeros van silenciosos,
  los segundos siguen loggeándose.
- Log agregado al final del ciclo en vez de 1 línea por símbolo.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

import OMSapi
import OMSsettings as cfg


# ──────────────────────────────────────────────────────────────────────
# Blacklist de símbolos muertos (compartida entre threads/ciclos)
# ──────────────────────────────────────────────────────────────────────

# TTL en segundos para mantener un símbolo en la blacklist.
# 120s = 2min. Balance entre eficiencia (no reintentar cada 15s) y responsividad
# (si un corporativo empieza a operar, aparece en ~2min automáticamente).
# Si querés forzar refresh inmediato: botón "🔄 Recargar" del sidebar.
_DEAD_SYMBOL_TTL = 120

# dict: symbol → timestamp en el que fue marcado como muerto
_dead_symbols: Dict[str, float] = {}
_dead_lock = threading.Lock()

# Contador de calls a bulk_market_data (para grace period post-login).
# Las primeras N calls NO blacklistean — esto evita que un primer fetch
# post-login con sesión fría meta símbolos válidos a la blacklist.
_call_counter = 0
_counter_lock = threading.Lock()
_GRACE_CALLS = 3  # primeras 3 calls no blacklistean

# Si el ratio de vacíos en un ciclo supera este umbral, NO se blacklistea
# nada en ese ciclo. Indica problema de API, no de símbolos individuales.
_MAX_EMPTY_RATIO = 0.80


def _is_blacklisted(symbol: str) -> bool:
    """True si el símbolo está en blacklist y el TTL no expiró."""
    now = time.time()
    with _dead_lock:
        ts = _dead_symbols.get(symbol)
        if ts is None:
            return False
        if now - ts > _DEAD_SYMBOL_TTL:
            # Expiró: sacamos de blacklist para reintentar
            del _dead_symbols[symbol]
            return False
        return True


def _mark_dead(symbol: str) -> None:
    """Agrega el símbolo a la blacklist."""
    with _dead_lock:
        _dead_symbols[symbol] = time.time()


def clear_dead_symbols() -> int:
    """Limpia completamente la blacklist. Útil para botón 'Recargar'.
    También resetea el contador de grace period para que los próximos
    fetches no blacklisteen nada durante las primeras N calls.
    Retorna cuántos símbolos había."""
    global _call_counter
    with _dead_lock:
        n = len(_dead_symbols)
        _dead_symbols.clear()
    with _counter_lock:
        _call_counter = 0  # re-activar grace period
    return n


def dead_symbols_info() -> Tuple[int, List[str]]:
    """(count, lista) de símbolos actualmente en blacklist. Útil para diagnóstico."""
    now = time.time()
    with _dead_lock:
        alive = [s for s, ts in _dead_symbols.items()
                 if now - ts <= _DEAD_SYMBOL_TTL]
    return len(alive), sorted(alive)


# ──────────────────────────────────────────────────────────────────────
# Fetch tolerante de un símbolo
# ──────────────────────────────────────────────────────────────────────

class _SymbolEmpty(Exception):
    """El endpoint devolvió status ERROR, body vacío, o JSON sin marketData.
    No es un error real — es el comportamiento esperado para muchos
    corporativos que no operan cualquier día."""
    pass


def _fetch_one_tolerant(
    session,
    market_id: str,
    symbol: str,
    entries: str,
    depth: int,
) -> Optional[dict]:
    """Devuelve el dict con marketData o None si el símbolo no operó.
    Distingue 'sin datos' (esperado) de 'error real' (HTTP 5xx, timeout).

    Raises:
        _SymbolEmpty: si el símbolo no tiene datos (blacklist candidate)
        requests.HTTPError / requests.ConnectionError / requests.Timeout:
            errores reales de red (el caller los puede contar aparte)
    """
    try:
        r = session.get(
            f"{cfg.BASE_URL}rest/marketdata/get",
            params={
                "marketId": market_id,
                "symbol": symbol,
                "entries": entries,
                "depth": depth,
            },
            timeout=10,
        )
        r.raise_for_status()

        # Body vacío: el endpoint devolvió 200 pero sin contenido
        if not r.content or not r.content.strip():
            raise _SymbolEmpty("empty body")

        # Intento de parseo JSON
        try:
            raw = r.json()
        except ValueError:
            # JSON malformado / body no-JSON → tratar como símbolo muerto
            raise _SymbolEmpty("non-JSON body")

        if raw.get("status") == "ERROR":
            raise _SymbolEmpty("status=ERROR")

        md = raw.get("marketData")
        if md is None:
            raise _SymbolEmpty("no marketData key")

        md["symbol"] = symbol
        return md

    except _SymbolEmpty:
        raise
    except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
        # Errores de red reales: que el caller decida si los cuenta
        raise


# ──────────────────────────────────────────────────────────────────────
# Bulk fetch (paralelo con blacklist)
# ──────────────────────────────────────────────────────────────────────

def bulk_market_data(
    session,
    symbols: List[str],
    market_id: str = "ROFX",
    entries: str = cfg.ENTRIES,
    depth: int = cfg.DEPTH,
    max_threads: int = cfg.MAX_THREADS,
    use_blacklist: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch paralelo de marketdata para una lista de símbolos.

    NOTE: esto NO es bulk nativo (el endpoint BYMA no lo soporta), es paralelo
    con ThreadPool. La optimización real está en:
    1. Skippear símbolos en blacklist (no generan request HTTP).
    2. Marcar como muertos los que devuelven vacío → no se reintentan en ~10min.
    3. Log agregado al final en vez de 1 print por símbolo.

    Args:
        use_blacklist: si False, ignora la blacklist (útil para forzar refresh).
        verbose: si True, imprime el log resumen al final.
    """
    if not symbols:
        return pd.DataFrame()

    # ── 0. Incrementar contador de llamadas (para grace period) ──
    global _call_counter
    with _counter_lock:
        _call_counter += 1
        call_number = _call_counter

    in_grace_period = call_number <= _GRACE_CALLS

    # ── 1. Filtrar por blacklist ──
    if use_blacklist:
        to_fetch = [s for s in symbols if not _is_blacklisted(s)]
        n_skipped = len(symbols) - len(to_fetch)
    else:
        to_fetch = list(symbols)
        n_skipped = 0

    if not to_fetch:
        if verbose:
            print(f"[bulk_market_data] skip={n_skipped} (todos blacklisted)")
        return pd.DataFrame()

    # ── 2. Fetch paralelo ──
    results: List[dict] = []
    n_ok = 0
    n_empty = 0
    n_error = 0
    empty_symbols: List[str] = []  # candidatos a blacklist (decisión al final)
    errors_sample: List[str] = []  # muestra de errores reales para el log

    with ThreadPoolExecutor(max_threads) as ex:
        futs = {
            ex.submit(_fetch_one_tolerant, session, market_id, sym, entries, depth): sym
            for sym in to_fetch
        }
        for f in as_completed(futs):
            sym = futs[f]
            try:
                res = f.result()
            except _SymbolEmpty:
                # Símbolo no operó → candidato a blacklist (decidimos al final)
                n_empty += 1
                empty_symbols.append(sym)
                continue
            except Exception as e:
                # Error real de red → loggear pero NO blacklistear
                # (puede ser un blip transitorio; si persiste, cae por su cuenta)
                n_error += 1
                if len(errors_sample) < 5:
                    errors_sample.append(f"{sym}: {type(e).__name__}: {e}")
                continue

            if res:
                results.append(res)
                n_ok += 1
            else:
                # Defensivo por si _fetch_one_tolerant retornara None sin raise
                n_empty += 1
                empty_symbols.append(sym)

    # ── 3. Decisión de blacklist (al final, con visión global del ciclo) ──
    # Sólo blacklistear si:
    # (a) use_blacklist está activo,
    # (b) NO estamos en grace period (primeras N calls post-login / post-clear),
    # (c) el ratio de vacíos es razonable (no es "todo falló, probablemente API fría")
    n_attempted = len(to_fetch)
    empty_ratio = n_empty / n_attempted if n_attempted > 0 else 0.0
    should_blacklist = (
        use_blacklist
        and not in_grace_period
        and empty_ratio < _MAX_EMPTY_RATIO
    )
    if should_blacklist and empty_symbols:
        for sym in empty_symbols:
            _mark_dead(sym)

    # ── 4. Log resumen (1 línea en vez de N) ──
    if verbose or n_error > 0 or in_grace_period:
        reason = ""
        if in_grace_period:
            reason = f" [grace call {call_number}/{_GRACE_CALLS} → NO blacklist]"
        elif not should_blacklist and empty_symbols:
            reason = f" [ratio vacios {empty_ratio:.0%} >= {_MAX_EMPTY_RATIO:.0%} → NO blacklist]"
        msg = (f"[bulk_market_data] OK={n_ok}  vacios={n_empty}  errores={n_error}  "
               f"skip_blacklist={n_skipped}{reason}")
        if errors_sample:
            msg += "\n  muestra de errores: " + " | ".join(errors_sample)
        print(msg)

    # ── 5. Ensamblar DataFrame ──
    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).set_index("symbol")
