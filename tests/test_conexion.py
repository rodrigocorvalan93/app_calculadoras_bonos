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


@pytest.mark.asyncio
async def test_conexion_status_se_refresca_y_espera_el_handshake() -> None:
    """09/10: tras un login OK la tarjeta mostraba "⚠ Feed caído" (start()
    vuelve antes del handshake y el partial no se refrescaba) y el desk volvía
    a apretar Reconectar. Ahora: GET /conexion/status (lo sondea la tarjeta
    cada 10 s) y el POST espera acotado a que el WS conecte."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.routes import conexion

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/conexion")
        st = await ac.get("/conexion/status")
    assert 'hx-get="/conexion/status"' in page.text and 'hx-trigger="every 10s"' in page.text
    assert st.status_code == 200 and "Estado del feed" in st.text and "Reprobar símbolos rechazados" in st.text

    class _WS:
        _connected = False

    ws = _WS()

    async def conecta():
        await asyncio.sleep(0.15)
        ws._connected = True

    asyncio.get_running_loop().create_task(conecta())
    assert await conexion._esperar_conexion(ws, 2.0, paso_s=0.05) is True       # conectó dentro del plazo
    ws2 = _WS()
    assert await conexion._esperar_conexion(ws2, 0.2, paso_s=0.05) is False     # no conectó: no cuelga
    assert await conexion._esperar_conexion(object(), 5.0) is False             # fake sin _connected: no espera


@pytest.mark.asyncio
async def test_conexion_reprobar_olvida_rechazados(monkeypatch) -> None:
    """09/10: una cuenta quedó con 2717 de 2903 símbolos en el cache de
    rechazados → cada reconexión suscribía 186 y el feed mostraba precios
    viejos. El botón «Reprobar» olvida memoria + cache del host y vuelve a
    pedir todo; la página avisa la tormenta."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import primary_ws as pws

    ws = pws.get_ws_client()
    ws._subscriptions.update(f"MERV - XMEV - S{i} - 24hs" for i in range(1000))
    ws._rejected.update(f"MERV - XMEV - S{i} - 24hs" for i in range(700))
    ws._rejected_fecha.update({s: "2026-10-06" for s in ws._rejected})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            page = await ac.get("/conexion")
            assert page.status_code == 200
            assert "rechazó 700 de 1.000 símbolos" in page.text and 'hx-post="/conexion/reprobar"' in page.text
            r = await ac.post("/conexion/reprobar")
        assert r.status_code == 200
        assert "Olvidé 700 símbolos rechazados" in r.text and "Reprobar símbolos rechazados (0)" in r.text
        assert not ws._rejected and not ws._rejected_fecha and ws.stats()["rejected"] == 0
    finally:
        ws._subscriptions.clear()
        ws._rejected.clear()
        ws._rejected_fecha.clear()
