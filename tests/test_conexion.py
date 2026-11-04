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
async def test_conexion_default_lbo_y_form_oob_tras_login_ok(monkeypatch) -> None:
    """04/11 (desk): LBO es el broker por defecto (settings y primera opción
    del selector) y, tras un login OK, la respuesta trae el form entero fuera
    de banda (`hx-swap-oob`) con el usuario precargado y la clave vacía — así
    el navegador ofrece guardar usuario y clave (con el campo de clave viejo
    en pantalla, Chrome no da por enviado el form). Un login fallido NO
    re-manda el form (lo tipeado se conserva)."""
    from httpx import ASGITransport, AsyncClient

    from backend.config import settings
    from backend.main import app
    from backend.routes import conexion
    from backend.services import primary_ws as pws

    assert settings.primary_base_url == "https://api.lbo.xoms.com.ar/"
    assert conexion.KNOWN_HOSTS[0][0] == "LBO"

    class _Fake(pws.PrimaryWS):
        acepta = True

        async def login(self, username, password):                      # sin red
            self._username, self._password = username, password
            if self.acepta:
                self._cookies = __import__("httpx").Cookies()
            return self.acepta

        async def start(self, symbols=()):
            self._connected = True

        async def stop(self):
            self._connected = False

    viejo = pws.get_ws_client()
    base, user, pwd = settings.primary_base_url, settings.primary_user, settings.primary_pass
    monkeypatch.setattr(conexion.primary_ws, "PrimaryWS", _Fake)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            page = await ac.get("/conexion")
            ok = await ac.post("/conexion/login", data={
                "url": "https://api.lbo.xoms.com.ar/", "username": "mesa", "password": "clave-x"})
            _Fake.acepta = False
            mal = await ac.post("/conexion/login", data={
                "url": "https://api.lbo.xoms.com.ar/", "username": "mesa", "password": "otra"})
    finally:
        pws.set_ws_client(viejo)
        settings.primary_base_url, settings.primary_user, settings.primary_pass = base, user, pwd
    # página: el selector arranca en LBO, el form tiene id y autocomplete para el gestor de claves
    t = page.text
    assert t.index('value="https://api.lbo.xoms.com.ar/"') < t.index('value="https://api.latinsecurities')
    assert 'id="conn-form"' in t and 'autocomplete="username"' in t and 'autocomplete="current-password"' in t
    assert "hx-swap-oob" not in t
    # login OK: estado + form fuera de banda, usuario precargado, clave nunca
    assert ok.status_code == 200 and "Conectado a https://api.lbo.xoms.com.ar/" in ok.text
    assert '<form id="conn-form" hx-swap-oob="outerHTML"' in ok.text
    assert 'value="mesa"' in ok.text and "clave-x" not in ok.text and 'name="password" value=' not in ok.text
    # login fallido: mensaje, sin form (lo tipeado queda en pantalla)
    assert mal.status_code == 200 and "rechazó usuario/clave" in mal.text and "hx-swap-oob" not in mal.text


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
