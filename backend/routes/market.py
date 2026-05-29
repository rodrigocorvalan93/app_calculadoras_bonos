"""Market data diagnostics + snapshot lookup endpoints.

For now this is enough to verify the WS pipeline:

  GET /market/diag                 → JSON: WS stats + store stats
  GET /market/snapshot/{code}      → JSON: latest snapshot for a code
                                     (resolves to a BYMA ticker on both
                                     24hs and CI)

The proper Mercado tab (curve table + book detail UI) lands once the
WS pipeline has been validated against a live broker.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query

from backend.services import fx as fx_svc, marketdata_store as mds, primary_ws, symbols as syms

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/diag")
async def diag() -> Dict[str, Any]:
    ws = primary_ws.get_ws_client()
    store = mds.get_store()
    return {
        "ws": ws.stats(),
        "store": store.stats(),
        "authenticated": ws.authenticated,
    }


@router.get("/fx")
async def fx(plazo: str = Query("24hs")) -> Dict[str, Any]:
    """Implicit FX reference: CCL (USD/cable) + USB (MEP) from the
    top-volume liquid sovereign, computed off the in-process store."""
    return fx_svc.get_fx(plazo).to_dict()


@router.get("/snapshot/{code}")
async def snapshot(code: str, plazo: str = Query("24hs")) -> Dict[str, Any]:
    """Latest known market data for a calc code."""
    store = mds.get_store()
    sym_24hs = syms.md_symbol(code, "24hs")
    sym_ci = syms.md_symbol(code, "CI")
    pref = sym_24hs if plazo.lower().startswith("24") else sym_ci
    main = store.get(pref)
    return {
        "code": code,
        "symbol": pref,
        "snapshot": main.to_dict() if main else None,
        "also_known": {
            sym_24hs: store.get(sym_24hs).to_dict() if store.get(sym_24hs) else None,
            sym_ci: store.get(sym_ci).to_dict() if store.get(sym_ci) else None,
        },
    }
