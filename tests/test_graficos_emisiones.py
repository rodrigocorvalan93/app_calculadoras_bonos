"""Gráficos · "Nuevas emisiones": el cuadro donde el desk tipea los cortes de la
licitación (ticker; tasa; duration) y charts.js los dibuja como ★ sobre la
curva. Todo vive en el navegador: la página trae el cuadro y el JS, y NINGÚN
request del gráfico lleva el textarea (no tiene `name`)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_graficos_trae_cuadro_de_emisiones_client_side() -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/graficos")
        assert page.status_code == 200
        assert 'id="graf-emis"' in page.text and "Nuevas emisiones" in page.text
        assert 'id="graf-emis-clear"' in page.text
        # el textarea no forma parte de los controles serializados
        cuadro = page.text.split('id="graf-emis"', 1)[1].split(">", 1)[0]
        assert "name=" not in cuadro
        js = await ac.get("/static/js/charts.js")
        assert js.status_code == 200
        for frag in ("Licitación ★", "function parseEmis", "graf_emis", "vs curva NSS"):
            assert frag in js.text
