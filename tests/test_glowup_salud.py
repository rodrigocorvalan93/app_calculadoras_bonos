"""Glow-up C (06/11) — autonomía visible: /salud para todos los roles con
acciones filtradas por rol, el estado del feed de la topbar como link
(/salud, o /conexion con el feed caído), /novedades desde el git log y la
causa de OneDrive en Posiciones / Matriz."""
from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, novedades, salud


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


async def _login(ac: AsyncClient, user: str, clave: str) -> None:
    await ac.post("/login", data={"username": user, "password": clave, "next": "/inicio"})


def _feed_falso(**kw):
    base = {"feed_alive": False, "authenticated": False, "connected": False, "connecting": False,
            "stale_seconds": None, "feed_down": False, "en_rueda": False, "data_age_s": None,
            "md_stale": False, "data_stale": False, "warn": None}
    base.update(kw)
    return lambda: dict(base)


def test_resumen_feed_y_titular(monkeypatch) -> None:
    from backend.services import feed_health
    monkeypatch.setattr(feed_health, "snapshot", _feed_falso(authenticated=True, feed_down=True))
    items = salud.resumen()
    feed = next(i for i in items if i["key"] == "feed")
    assert feed["estado"] == "err" and feed["texto"] == "Feed caído"
    assert feed["accion"] == {"href": "/conexion", "label": "Reconectar"}
    assert salud.titular(items)["estado"] == "err"
    # autenticado y con ticks → ok, sin acción
    monkeypatch.setattr(feed_health, "snapshot",
                        _feed_falso(authenticated=True, connected=True, feed_alive=True, data_age_s=3.0))
    feed = next(i for i in salud.resumen() if i["key"] == "feed")
    assert feed["estado"] == "ok" and feed["accion"] is None and "hace 3 s" in feed["detalle"]
    # un lector que explota no voltea el resumen
    monkeypatch.setattr(salud, "_mae", lambda: 1 / 0)
    items = salud.resumen()
    mae = next(i for i in items if i["key"] == "mae")
    assert mae["estado"] == "err" and "ZeroDivisionError" in mae["detalle"]
    # errores de la última hora: cuenta sólo los recientes (el ring se parchea:
    # en la suite completa otros tests dejan warnings de la última hora)
    from backend.services import errores
    monkeypatch.setattr(errores, "ultimos", lambda n=120: [
        {"t": time.time() - 7200, "ts": "x", "level": "ERROR", "logger": "viejo", "msg": "m"},
        {"t": time.time() - 60, "ts": "x", "level": "WARNING", "logger": "test.salud", "msg": "m"}])
    err = next(i for i in salud.resumen() if i["key"] == "errores")
    assert err["estado"] == "warn" and err["texto"].startswith("1 aviso") and "test.salud" in err["detalle"]
    monkeypatch.setattr(errores, "ultimos", lambda n=120: [])
    assert next(i for i in salud.resumen() if i["key"] == "errores")["estado"] == "ok"


@pytest.mark.asyncio
async def test_salud_para_todos_con_acciones_por_rol(auth_on, monkeypatch) -> None:
    from backend.services import feed_health
    monkeypatch.setattr(feed_health, "snapshot", _feed_falso(authenticated=True, feed_down=True))
    async with _client() as su:
        await _login(su, "su_test", "clave-de-test-2026!")
        await su.post("/admin/users", data={"username": "nico", "password": "clave123", "role": "basico"})
        r = await su.get("/salud")
        assert r.status_code == 200 and "<title>Salud · ΔYieldVertex</title>" in r.text
        assert 'href="/admin"' in r.text                                     # acción de superuser
    async with _client() as ac:
        await _login(ac, "nico", "clave123")
        r = await ac.get("/salud")
        assert r.status_code == 200
        assert 'data-key="feed"' in r.text and "Feed caído" in r.text and 'href="/conexion"' in r.text
        assert "Cierre histórico" in r.text and "Avisos del proceso" in r.text
        assert "Ver el detalle" not in r.text                                # /admin no es para un básico
        b = await ac.get("/salud/body")
        assert b.status_code == 200 and 'class="salud-list"' in b.text and "<html" not in b.text
    async with _client() as anon:
        assert (await anon.get("/salud")).status_code in (302, 303, 401, 403)


@pytest.mark.asyncio
async def test_topbar_estado_del_feed_es_un_link(auth_on) -> None:
    async with _client() as ac:
        await _login(ac, "su_test", "clave-de-test-2026!")
        r = await ac.get("/inicio")
        js = await ac.get("/static/js/app.js")
    assert 'id="live-link"' in r.text and 'href="/salud"' in r.text
    assert 'id="live-dot"' in r.text and 'id="live-meta"' in r.text         # ids intactos para app.js
    assert 'class="footer-ver" href="/novedades"' in r.text
    assert "liveLink('/conexion'" in js.text and "liveLink('/salud'" in js.text


@pytest.mark.asyncio
async def test_novedades_desde_el_git_log(auth_on, monkeypatch) -> None:
    lineas = ["abc1234\x1f2026-11-06\x1fYAS: layout compacto (#260)",
              "def5678\x1f2026-11-06\x1fTests sin PR",
              "0123abc\x1f2026-11-04\x1fExcel =OMS.CASHFLOW (#261)"]
    # estado del módulo restaurado al salir (los commits falsos no se quedan)
    monkeypatch.setattr(novedades, "_items", [])
    monkeypatch.setattr(novedades, "_version", "")
    monkeypatch.setattr(novedades, "_estado", dict(novedades._estado))
    monkeypatch.setattr(novedades, "_leer_git", lambda n=60: list(lineas))
    novedades.cargar()
    assert novedades.estado()["cargado"] and novedades.estado()["n"] == 3
    it = novedades.items()[0]
    assert it["sha"] == "abc1234" and it["titulo"] == "YAS: layout compacto" and it["pr"] == 260
    assert it["fecha_fmt"] == "06/11/2026"
    async with _client() as ac:
        await _login(ac, "su_test", "clave-de-test-2026!")
        r = await ac.get("/novedades")
        assert r.status_code == 200 and "<title>Qué hay de nuevo · ΔYieldVertex</title>" in r.text
        assert r.text.count('class="nv-fecha"') == 2 and "YAS: layout compacto" in r.text
        assert "/pull/260" in r.text and "/pull/261" in r.text and "Tests sin PR" in r.text
        # sin git: la página lo dice y linkea a GitHub (un fallo con historial
        # ya leído no lo borra: se vacía a mano para simular el primer arranque)
        monkeypatch.setattr(novedades, "_leer_git", lambda n=60: (_ for _ in ()).throw(OSError("git no disponible")))
        novedades.cargar()
        assert novedades.estado()["cargado"] and novedades.estado()["n"] == 3
        monkeypatch.setattr(novedades, "_items", [])
        novedades.cargar()
        assert not novedades.estado()["cargado"] and novedades.items() == []
        r = await ac.get("/novedades")
        assert r.status_code == 200 and 'class="empty-state' in r.text and "git no disponible" in r.text


@pytest.mark.asyncio
async def test_posiciones_marcador_onedrive_dice_el_remedio(tmp_path, monkeypatch) -> None:
    from backend.services import nube, positions
    comp = tmp_path / "Delta_Composicion.xlsx"
    comp.write_bytes(b"no es un xlsx")
    monkeypatch.setenv("DELTA_COMPOSICION_PATH", str(comp))
    monkeypatch.delenv("DELTA_PN_PATH", raising=False)
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda path, exc=None: True)
    positions.refresh()
    try:
        err = positions.status()["error"]
        assert "sólo en la nube" in err and "Delta_Composicion.xlsx" in err and "Errno" not in err
        async with _client() as ac:
            r = await ac.get("/posiciones")
            m = await ac.get("/matriz/table")
        assert "sólo en la nube" in r.text and "Mantener siempre en este dispositivo" in r.text
        assert m.status_code == 200 and "sólo en la nube" in m.text
        # sin marcador: el error de siempre (con la excepción)
        monkeypatch.setattr(nube, "ilegible_por_nube", lambda path, exc=None: False)
        positions.refresh()
        assert positions.status()["error"].startswith("Error leyendo composición")
    finally:
        with positions._lock:
            positions._cache = None
