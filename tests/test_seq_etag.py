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
async def test_paneles_periodicos_revalidan() -> None:
    """Todo panel COMPARTIDO con refresh periódico sale con ETag (la vía 304).
    Órdenes queda afuera a propósito: contenido sensible/por rol, no se
    cachea compartido (invariante de seguridad)."""
    bond_universe.ensure_loaded()
    async with _client() as ac:
        for url, params in [
            ("/tasas/table", {}),
            ("/yas/market", {"code": "GD30"}),
            ("/alertas/tabla", {}),
            ("/cafci/fondos", {}),
            ("/mercado/book/GD30", {}),
        ]:
            r = await ac.get(url, params=params)
            assert r.status_code == 200, url
            assert r.headers.get("etag"), f"sin ETag: {url}"
            assert r.headers.get("cache-control") == "private, no-cache", url
        # marquee: con el poller RSS frío el body es vacío y el decorador (bien)
        # no cachea vacíos → ETag sólo cuando hay titulares.
        r = await ac.get("/news/marquee")
        assert r.status_code == 200
        assert r.headers.get("etag") or not r.content


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
