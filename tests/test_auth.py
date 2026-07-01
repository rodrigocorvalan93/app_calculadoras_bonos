"""Auth — login wall, gating por rol, panel superuser y reset de contraseña.

El muro se prende por test (settings.auth_enabled = True) sobre un store temporal
con el superuser sembrado. El secret de sesión es fijo (conftest), así la cookie
firmada funciona con httpx (que persiste cookies entre requests)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    """Muro prendido + store temporal fresco con superuser bootstrapeado."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    b = auth.ensure_bootstrapped()
    assert b["created"] and b["user"] == "rodricor93"
    yield
    auth.refresh()   # limpia el cache global para los siguientes tests


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _login(ac: AsyncClient, user: str, pwd: str):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


# ── Muro ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_wall_redirige_sin_sesion(auth_on):
    async with _client() as ac:
        r = await ac.get("/yas")
        assert r.status_code == 302 and "/login" in r.headers["location"]


@pytest.mark.asyncio
async def test_wall_htmx_da_401_con_hx_redirect(auth_on):
    async with _client() as ac:
        r = await ac.get("/yas/market?code=AL30", headers={"hx-request": "true"})
        assert r.status_code == 401 and r.headers.get("hx-redirect") == "/login"


@pytest.mark.asyncio
async def test_login_ok_y_acceso(auth_on):
    async with _client() as ac:
        r = await _login(ac, "rodricor93", "Rc_874562")
        assert r.status_code == 303
        y = await ac.get("/yas")
        assert y.status_code == 200 and "Análisis de Yields" in y.text
        # superuser ve el panel y el chip
        assert "/admin" in y.text and "rodricor93" in y.text


@pytest.mark.asyncio
async def test_login_mal_falla(auth_on):
    async with _client() as ac:
        r = await _login(ac, "rodricor93", "malaclave")
        assert r.status_code == 401 and "incorrect" in r.text.lower()


@pytest.mark.asyncio
async def test_paginas_publicas_sin_sesion(auth_on):
    async with _client() as ac:
        assert (await ac.get("/login")).status_code == 200
        assert (await ac.get("/forgot")).status_code == 200
        assert (await ac.get("/healthz")).status_code == 200


# ── Gating por rol ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_basico_no_ve_ordenes(auth_on):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123",
                                                "role": "basico", "email": ""})
        assert r.status_code == 200 and "creado" in r.text
    async with _client() as ac:
        await _login(ac, "juan", "clave123")
        # /ordenes no está en el default de básico → 403
        assert (await ac.get("/ordenes")).status_code == 403
        # /yas sí
        y = await ac.get("/yas")
        assert y.status_code == 200
        # la nav NO muestra Órdenes ni el panel admin
        assert ">Órdenes<" not in y.text and "/admin" not in y.text


@pytest.mark.asyncio
async def test_admin_solo_superuser(auth_on):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "pepe", "password": "clave123", "role": "premium"})
    async with _client() as ac:
        await _login(ac, "pepe", "clave123")
        assert (await ac.get("/admin")).status_code == 403


@pytest.mark.asyncio
async def test_config_role_tabs(auth_on):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        # dejar a básico sólo YAS + Curvas
        r = await su.post("/admin/tabs", data={"tab_basico_yas": "on", "tab_basico_curves": "on",
                                               "tab_premium_yas": "on"})
        assert r.status_code == 200
    assert set(auth.allowed_tabs("basico")) == {"yas", "curves"}
    # ahora un básico no entra a /breakeven (antes estaba permitido)
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "ana", "password": "clave123", "role": "basico"})
    async with _client() as ac:
        await _login(ac, "ana", "clave123")
        assert (await ac.get("/breakeven")).status_code == 403
        assert (await ac.get("/curves")).status_code == 200


@pytest.mark.asyncio
async def test_sub_endpoints_compartidos_no_se_gatean(auth_on):
    """Regresión: los endpoints GLOBALES/compartidos sólo piden sesión, NO permiso
    de tab. Un básico sin 'dolares'/'historicos' NO debe recibir 403 en el riel
    (/dolares/rail, que sondea toda página) ni en /historicos/semanal (que usa la
    pestaña Qué pasó). La PÁGINA exacta sí se gatea."""
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        # básico ve sólo YAS + Qué pasó (ni dólares ni históricos)
        await su.post("/admin/tabs", data={"tab_basico_yas": "on", "tab_basico_quepaso": "on",
                                           "tab_premium_yas": "on"})
        await su.post("/admin/users", data={"username": "beto", "password": "clave123", "role": "basico"})
    async with _client() as ac:
        await _login(ac, "beto", "clave123")
        # sub-endpoints globales/compartidos → NO 403 (sólo requieren sesión)
        assert (await ac.get("/dolares/rail")).status_code != 403
        assert (await ac.get("/historicos/semanal")).status_code == 200
        assert (await ac.get("/que-paso")).status_code == 200      # su pestaña
        # la PÁGINA exacta que no tiene sí se gatea
        assert (await ac.get("/dolares")).status_code == 403
        assert (await ac.get("/historicos")).status_code == 403


@pytest.mark.asyncio
async def test_guardar_especie_solo_superuser(auth_on):
    """Persistir en especies.py es sólo del superuser: el botón no se renderiza
    para premium y el endpoint /nueva/guardar lo bloquea aunque conozca la URL."""
    form = {"entrada": "form", "codigo": "NPX", "emision": "01/07/2025",
            "vencimiento": "01/07/2027", "frecuencia": "2", "tipo_tasa": "FIJA",
            "cupon": "5", "tipo_amortizacion": "BULLET"}
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
    async with _client() as ac:
        await _login(ac, "prem", "clave123")
        r = await ac.post("/nueva/parse", data=form)
        assert r.status_code == 200 and "Guardar especie" not in r.text   # botón oculto
        g = await ac.post("/nueva/guardar", data={"token": "loquesea"})
        assert "superuser" in g.text.lower()                              # endpoint bloqueado
    async with _client() as ac:
        await _login(ac, "rodricor93", "Rc_874562")
        r = await ac.post("/nueva/parse", data=form)
        assert "Guardar especie" in r.text                                # superuser sí lo ve


@pytest.mark.asyncio
async def test_logout(auth_on):
    async with _client() as ac:
        await _login(ac, "rodricor93", "Rc_874562")
        assert (await ac.get("/yas")).status_code == 200
        lo = await ac.get("/logout")
        assert lo.status_code == 303
        assert (await ac.get("/yas")).status_code == 302   # de nuevo al muro


# ── Reset de contraseña ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reset_token_flow(auth_on):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "lucia", "password": "vieja123", "role": "premium"})
    token = auth.make_reset_token("lucia", ttl_seconds=3600)
    async with _client() as ac:
        pg = await ac.get(f"/reset?token={token}")
        assert pg.status_code == 200 and "Nueva contraseña" in pg.text
        r = await ac.post("/reset", data={"token": token, "password": "nueva123", "password2": "nueva123"})
        assert r.status_code == 200 and "actualizada" in r.text.lower()
    assert auth.verify_password("lucia", "nueva123") and not auth.verify_password("lucia", "vieja123")
    # token inválido
    async with _client() as ac:
        bad = await ac.get("/reset?token=basura.xx")
        assert "no es válido" in bad.text or "expiró" in bad.text


def test_seed_users_script(tmp_path, monkeypatch):
    """El script de seed crea los usuarios con el rol pedido, sólo guarda el hash
    y es idempotente (2da corrida no duplica ni rompe)."""
    import importlib
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "seed.json"))
    auth.refresh()
    seed = importlib.import_module("scripts.seed_users")
    seed.main(["jpaolicchi:premium", "jrivasrivas:basico"])
    assert auth.role_of("jpaolicchi") == "premium"
    assert auth.role_of("jrivasrivas") == "basico"
    # el store no guarda la clave en claro, sólo hash+salt
    import json
    raw = json.loads((tmp_path / "seed.json").read_text(encoding="utf-8"))
    assert "hash" in raw["users"]["jpaolicchi"] and "password" not in raw["users"]["jpaolicchi"]
    # idempotente
    seed.main(["jpaolicchi:premium"])
    assert sum(1 for u in auth.list_users() if u["username"] == "jpaolicchi") == 1
    auth.refresh()


@pytest.mark.asyncio
async def test_no_borrar_ultimo_superuser(auth_on):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        r = await su.post("/admin/users/delete", data={"username": "rodricor93"})
        # es el usuario logueado → bloqueado
        assert "propio usuario" in r.text or "último superuser" in r.text
