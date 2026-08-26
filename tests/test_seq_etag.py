"""Revalidación HTTP de los paneles live (seq_cached + ETag / 304).

El costo de datos del refresh por tick: si el HTML no cambió, el server
contesta 304 SIN body — incluso cuando la seq global avanzó por un tick de
OTRO símbolo y el panel se re-renderizó idéntico (rama miss-304). Cuando el
contenido sí cambió, viaja completo al instante (frescura intacta)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, marketdata_store


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_etag_hit_y_304() -> None:
    bond_universe.ensure_loaded()
    params = {"curve": "dolarlinked", "only_quoting": "false"}
    async with _client() as ac:
        r1 = await ac.get("/forwards/table", params=params)
        assert r1.status_code == 200 and r1.content
        etag = r1.headers.get("etag")
        assert etag and etag.startswith('"')
        assert r1.headers.get("cache-control") == "private, no-cache"
        # el cliente ya tiene ese HTML → 304 sin body (rama hit-304)
        r2 = await ac.get("/forwards/table", params=params,
                          headers={"If-None-Match": etag})
        assert r2.status_code == 304 and not r2.content
        assert r2.headers.get("x-seq-cache") == "hit-304"
        assert r2.headers.get("etag") == etag
        # etag distinto (contenido viejo) → HTML completo
        r3 = await ac.get("/forwards/table", params=params,
                          headers={"If-None-Match": '"otro"'})
        assert r3.status_code == 200 and r3.content


@pytest.mark.asyncio
async def test_miss_304_cuando_la_seq_avanza_sin_cambios() -> None:
    """Tick de otro símbolo (la seq global avanza) → el panel se re-renderiza;
    si quedó idéntico, el cliente recibe 304 igual (no re-baja el HTML)."""
    bond_universe.ensure_loaded()
    params = {"curve": "dolarlinked", "only_quoting": "false"}
    store = marketdata_store.get_store()
    async with _client() as ac:
        r1 = await ac.get("/forwards/hist", params=params)
        assert r1.status_code == 200
        etag = r1.headers.get("etag")
        assert etag
        with store._lock:                       # simular tick ajeno al panel
            store._updates += 1
        r2 = await ac.get("/forwards/hist", params=params,
                          headers={"If-None-Match": etag})
        assert r2.status_code == 304 and not r2.content
        assert r2.headers.get("x-seq-cache") == "miss-304"
