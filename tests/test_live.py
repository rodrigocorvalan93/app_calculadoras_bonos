"""Motor live — /market/seq + triggers md-update en los paneles vivos.

El front sondea /market/seq cada 1 s (entero plano, ~µs) y dispara `md-update`
en <body> sólo cuando la secuencia avanzó; los paneles con
`hx-trigger="md-update from:body, …"` se re-renderizan recién ahí. Un tick
llega a pantalla en ~1 s y sin mercado no se re-renderiza nada.
"""
from __future__ import annotations

import pytest

from backend.services import marketdata_store as mds


def test_store_seq_monotona() -> None:
    store = mds.get_store()
    s0 = store.seq()
    store.update_from_md("TEST - SEQ - 24hs", {"LA": {"price": 100.0}})
    s1 = store.seq()
    assert s1 == s0 + 1
    store.update_from_md("TEST - SEQ - 24hs", {"LA": {"price": 100.5}})
    assert store.seq() == s1 + 1


@pytest.mark.asyncio
async def test_market_seq_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    store = mds.get_store()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r1 = await ac.get("/market/seq")
        assert r1.status_code == 200
        v1 = int(r1.text)                      # texto plano parseable
        store.update_from_md("TEST - SEQ2 - 24hs", {"LA": {"price": 1.0}})
        r2 = await ac.get("/market/seq")
        assert int(r2.text) == v1 + 1


@pytest.mark.asyncio
async def test_paneles_vivos_declaran_md_update() -> None:
    """Las páginas con data de mercado escuchan md-update (y mantienen un
    fallback lento), y marcan el contenedor para los flashes de tick."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for url in ("/mercado", "/curves", "/dolares", "/futuros", "/tasas", "/yas"):
            r = await ac.get(url)
            assert r.status_code == 200, url
            assert "md-update from:body" in r.text, url
            assert "data-flash-scope" in r.text, url
        # base.html: riel + dot de estado del feed en todas las páginas
        r = await ac.get("/yas")
        assert 'id="live-dot"' in r.text
