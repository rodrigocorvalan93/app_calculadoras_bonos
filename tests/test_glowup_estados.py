"""Glow-up 06/11 — sistema visual y estados: páginas de error con la
plantilla de la app (403 / 404 / htmx), estados vacíos con causa y acción,
iconos SVG en la topbar, pestañas secundarias como componente, marca única."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_403_con_la_plantilla_de_la_app_y_alert_corto_para_htmx(auth_on) -> None:
    """Antes un `<h1>403</h1>` pelado; ahora error.html (topbar, acciones) y,
    para un request de htmx, un alert que el panel puede swapear."""
    async with _client() as su:
        await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/yas"})
        await su.post("/admin/users", data={"username": "nico", "password": "clave123", "role": "basico"})
    async with _client() as ac:
        await ac.post("/login", data={"username": "nico", "password": "clave123", "next": "/yas"})
        r = await ac.get("/admin")
        assert r.status_code == 403
        assert 'class="error-page"' in r.text and "Sin acceso" in r.text and "reservada al superuser" in r.text
        assert 'href="/inicio"' in r.text and "<title>403 · ΔYieldVertex</title>" in r.text
        hx = await ac.get("/admin", headers={"HX-Request": "true"})
        assert hx.status_code == 403 and 'class="alert alert-error"' in hx.text and "error-page" not in hx.text
        js = await ac.get("/admin", headers={"Accept": "application/json"})
        assert js.status_code == 403 and js.json()["error"].startswith("403")


@pytest.mark.asyncio
async def test_404_con_la_plantilla_de_la_app() -> None:
    async with _client() as ac:
        r = await ac.get("/esta-pagina-no-existe")
        assert r.status_code == 404
        assert 'class="error-page"' in r.text and "No existe" in r.text and 'class="error-code">404<' in r.text
        # los estáticos y el add-in siguen con el 404 corto de siempre
        s = await ac.get("/static/no-existe.css")
        assert s.status_code == 404 and "error-page" not in s.text


@pytest.mark.asyncio
async def test_topbar_iconos_svg_marca_y_sprite() -> None:
    async with _client() as ac:
        r = await ac.get("/inicio")
        js = await ac.get("/static/js/app.js")
    t = r.text
    assert "<title>Inicio · ΔYieldVertex</title>" in t
    assert '<symbol id="i-search"' in t and '<use href="#i-search"/>' in t      # sprite + uso
    assert 'aria-label="Buscar (Ctrl+K)"' in t and 'aria-label="Conexión del feed"' in t
    for emoji in ("🔔", "🔍", "👤", "🔌", "⎋", "💵"):
        assert emoji not in t.split("<main", 1)[0], emoji                        # topbar sin emojis
    assert "FastAPI rewrite" not in t and "sub-50 ms" not in t                  # pie sin texto de desarrollo
    assert "hx-progress" in js.text and "deUsuario" in js.text                  # barra de progreso global


@pytest.mark.asyncio
async def test_historicos_sub_tabs_componente() -> None:
    async with _client() as ac:
        r = await ac.get("/historicos")
    t = r.text
    assert 'class="sub-tabs" role="tablist"' in t and t.count('class="sub-tab"') == 7
    assert "📊 Macro" not in t and '{{ icon' not in t                         # macro renderizado, sin emoji
    assert "htmx.trigger('#hist-fechas','reveal')" in t                         # la carga lazy sigue igual


@pytest.mark.asyncio
async def test_posiciones_sin_carteras_dice_la_causa(tmp_path, monkeypatch) -> None:
    from backend.services import positions
    monkeypatch.setenv("DELTA_BASES_DIR", str(tmp_path))
    for env in ("DELTA_COMPOSICION_PATH", "DELTA_PN_PATH", "GALILEO_COMPOSICION_PATH", "GALILEO_PN_PATH"):
        monkeypatch.delenv(env, raising=False)
    positions.refresh()
    try:
        async with _client() as ac:
            r = await ac.get("/posiciones")
            p = await ac.get("/posiciones/table", params={"fondo": "", "plazo": "24hs"})
        assert r.status_code == 200 and p.status_code == 200
        assert r.text.count('class="empty-state es-error"') == 1               # una sola vez (no página + partial)
        assert "No se cargaron las posiciones" in r.text and "Delta_Composicion.xlsx" in r.text
        assert 'href="/posiciones?refresh=1"' in r.text                        # acción
        assert 'class="empty-state es-error"' in p.text
    finally:
        with positions._lock:
            positions._cache = None


@pytest.mark.asyncio
async def test_login_marca_unica() -> None:
    async with _client() as ac:
        r = await ac.get("/login")
    assert "ΔYieldVertex" in r.text and "Calculadora de bonos" in r.text
    assert "Calculadora · Bonos" not in r.text and "<title>Ingresar · ΔYieldVertex</title>" in r.text
