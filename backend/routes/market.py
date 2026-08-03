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

import asyncio
import time
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from backend.services import fx as fx_svc, marketdata_store as mds, primary_ws, symbols as syms

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/seq", response_class=PlainTextResponse)
async def seq() -> PlainTextResponse:
    """Secuencia global del store (texto plano, ~µs). Fallback del front
    cuando EventSource no está disponible (ver /market/events): la sondea
    cada 1 s y dispara `md-update` sólo cuando avanza."""
    return PlainTextResponse(str(mds.get_store().seq()))


# Cadencia del chequeo interno de la seq por conexión SSE. Es un int bajo
# mutex (~µs): 4 chequeos/s por cliente no mueven la aguja, y la latencia
# tick→pantalla queda en ≤250 ms + render (vs ~1 s del polling HTTP).
_SSE_TICK_SECONDS = 0.25
_SSE_HEARTBEAT_SECONDS = 15.0


@router.get("/events")
async def events() -> StreamingResponse:
    """SSE: pushea la secuencia del store cuando avanza (+ heartbeat como
    comentario cada 15 s para que proxies/keep-alives no corten la conexión).

    Reemplaza el polling 1/s de /market/seq: cero requests de sondeo, latencia
    de tick casi instantánea y — clave en el celular — la radio del teléfono
    no se despierta una vez por segundo. El primer evento manda la seq actual
    como baseline. El cliente cae solo al polling si EventSource falla
    (static/js/app.js)."""
    async def gen() -> AsyncIterator[str]:
        store = mds.get_store()
        last = None
        beat = time.monotonic()
        # retry: cuánto espera EventSource antes de reconectar solo.
        yield "retry: 2000\n\n"
        while True:
            cur = store.seq()
            now = time.monotonic()
            if cur != last:
                last = cur
                beat = now
                yield f"data: {cur}\n\n"
            elif now - beat >= _SSE_HEARTBEAT_SECONDS:
                beat = now
                yield ": hb\n\n"
            await asyncio.sleep(_SSE_TICK_SECONDS)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",   # nginx/proxies: no bufferear el stream
    })


_codes_cache: Dict[str, Any] = {}


@router.get("/codes")
async def codes() -> Dict[str, Any]:
    """Universo de códigos para el buscador Ctrl+K: [{c, v}] (código +
    vencimiento). El universo es estático por proceso → se arma UNA vez y
    después es un dict lookup (~ns). ~554 bonos ≈ 15 KB gzipeados una vez
    por sesión de navegador (el cliente lo cachea en memoria)."""
    if not _codes_cache:
        from backend.services import bond_universe
        bond_universe.ensure_loaded()
        items = []
        for code in bond_universe.all_codes():
            o = bond_universe.get(code)
            v = getattr(o, "vencimiento", None)
            try:
                v_iso = (v.date() if hasattr(v, "date") else v).isoformat() if v else ""
            except Exception:  # noqa: BLE001
                v_iso = ""
            items.append({"c": code, "v": v_iso})
        _codes_cache["items"] = items
    return {"items": _codes_cache["items"]}


@router.get("/diag")
async def diag() -> Dict[str, Any]:
    ws = primary_ws.get_ws_client()
    store = mds.get_store()
    return {
        "ws": ws.stats(),
        "store": store.stats(),
        "authenticated": ws.authenticated,
    }


@router.get("/health")
async def market_health() -> Dict[str, Any]:
    """Estado del feed para el dot de la topbar (liviano; el front lo sondea cada
    ~15 s). Dos alarmas distintas:

    - `feed_down`: sesión del broker abierta PERO el WS desconectado.
    - `warn` (md_stale/data_stale): el caso silencioso — WS CONECTADO pero sin
      market data (broker que autentica y no streamea): el seq sigue avanzando
      por MAE/pollers y los precios que se ven son los persistidos de la última
      rueda buena. Sólo alarma en rueda y con sesión — sin falsos positivos de
      noche ni en paper/dev. Ver services.feed_health."""
    from backend.services import feed_health

    return feed_health.snapshot()


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
