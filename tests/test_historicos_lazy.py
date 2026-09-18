"""Pestañas lazy de Históricos (hx-get al abrir el tab).

Antes, una excepción del handler daba 500: htmx no swapea en error, el tab
quedaba en "Cargando…" para siempre y el flag de Alpine no volvía a pedirlo
(así quedó Acciones en una Mac). Ahora: 200 con el error a la vista y botón
Reintentar (server), timeout de request en los 4 contenedores y handler JS
para error de red / timeout con el mismo botón."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_excepcion_en_acciones_muestra_error_y_reintentar(monkeypatch) -> None:
    from backend.main import app
    from backend.routes import historico as hr

    def boom():
        raise RuntimeError("parquet ilegible de prueba")

    monkeypatch.setattr(hr, "_grupos_especies", boom)
    hr._AC_CACHE.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/acciones", params={"ticker": "GGAL"})
    hr._AC_CACHE.clear()
    assert r.status_code == 200                                   # no 500: htmx sí swapea
    assert "No se pudo armar el price action" in r.text
    assert "RuntimeError: parquet ilegible de prueba" in r.text   # QUÉ falló, a la vista
    assert "Reintentar" in r.text and "htmx.trigger(this.closest('[hx-trigger]'), 'reveal')" in r.text


@pytest.mark.asyncio
async def test_excepcion_en_curva_fechas_tambien(monkeypatch) -> None:
    from backend.main import app
    from backend.services import historico_byma

    def boom(*a, **k):
        raise ValueError("base rota de prueba")

    monkeypatch.setattr(historico_byma, "curves_with_history", boom)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/curva-fechas")
    assert r.status_code == 200
    assert "No se pudo armar la curva por fecha" in r.text and "ValueError: base rota de prueba" in r.text


@pytest.mark.asyncio
async def test_contenedores_lazy_con_timeout_y_js_de_reintento() -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/historicos")
        assert page.status_code == 200
        for tab in ("hist-curva", "hist-fechas", "hist-series", "hist-acciones"):
            i = page.text.index(f'id="{tab}"')
            frag = page.text[i:i + 400]
            assert 'hx-trigger="reveal"' in frag and 'hx-request=\'{"timeout":90000}\'' in frag, tab
        js = await ac.get("/static/js/app.js")
    for frag in ("function lazyFail", "htmx:timeout", "getAttribute('hx-trigger') !== 'reveal'", "Reintentar"):
        assert frag in js.text, frag
