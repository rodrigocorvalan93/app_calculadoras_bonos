#%% """Descarga masiva y normalización de datos de mercado."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
import pandas as pd

import OMSapi
import OMSsettings as cfg


def _one_symbol(session, market_id: str, symbol: str, entries: str, depth: int):
    raw = OMSapi.fetch_json(
        session,
        "rest/marketdata/get",
        marketId=market_id,
        symbol=symbol,
        entries=entries,
        depth=depth,
    )
    if raw.get("status") == "ERROR":
        return {}
    md = raw["marketData"]
    md["symbol"] = symbol
    return md


def bulk_market_data(
    session,
    symbols: List[str],
    market_id: str = "ROFX",
    entries: str = cfg.ENTRIES,
    depth: int = cfg.DEPTH,
    max_threads: int = cfg.MAX_THREADS,
) -> pd.DataFrame:
    results = []
    with ThreadPoolExecutor(max_threads) as ex:
        futs = {
            ex.submit(_one_symbol, session, market_id, sym, entries, depth): sym
            for sym in symbols
        }
        for f in as_completed(futs):
            sym = futs[f]
            try:
                res = f.result()
            except Exception as e:
                # Loguea y sigue con el resto (timeouts, errores HTTP, etc.)
                print(f"[bulk_market_data] Error al traer {sym}: {e}")
                continue
            if res:
                results.append(res)

    if not results:
        # Devolvemos DF vacío para que el caller lo maneje sin romper
        return pd.DataFrame()

    return pd.DataFrame(results).set_index("symbol")
