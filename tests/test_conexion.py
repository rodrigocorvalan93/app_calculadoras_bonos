"""Conexión — landing de broker: página, defaults y login fallido manejado."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_conexion_page() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/conexion")
    t = r.text
    assert r.status_code == 200
    for host in ("latinsecurities.matrizoms", "lbo.xoms", "cocos.xoms"):
        assert host in t, host                       # los 3 brokers ofrecidos
    assert 'type="password"' in t
    assert 'name="password" value=' not in t         # la clave NUNCA va al HTML
    assert "MAE" in t and "directo" in t             # nota MAE sin selector


@pytest.mark.asyncio
async def test_conexion_login_fallido_es_manejado() -> None:
    """Sin red al broker (sandbox) el POST devuelve 200 con mensaje claro,
    nunca un 500."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/conexion/login", data={
            "url": "https://api.lbo.xoms.com.ar/", "username": "u", "password": "p"})
    assert r.status_code == 200
    assert ("No pude conectar" in r.text) or ("rechazó" in r.text) or ("desconectado" in r.text)
