"""API del add-in de Excel — snapshot, gating por token por usuario y manifest.

El store de mercado se puebla a mano (update_from_md) así el test no depende
del feed. El auth store va a un tmp por test, igual que en test_alertas.
"""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.routes import excel as excel_route
from backend.services import auth, marketdata_store as mds


@pytest.fixture()
def store_con_datos():
    st = mds.get_store()
    st.update_from_md("MERV - XMEV - GD30 - 24hs", {
        "BI": [{"price": 1000.0, "size": 5000}],
        "OF": [{"price": 1002.0, "size": 3000}],
        "LA": {"price": 1001.0, "size": 100, "date": "2026-07-22T14:00:00"},
        "CL": {"price": 990.0, "date": "2026-07-21"},
        "EV": 123456789.0, "NV": 120000.0, "TV": 42,
    })
    st.update_from_md("MERV - XMEV - GD30 - CI", {"LA": {"price": 999.5}})
    st.update_from_md("MERV - XMEV - PESOS - 7D", {"LA": {"price": 35.5}, "CL": 34.0})
    st.update_from_md("DLR/DEC26M", {"LA": {"price": 1600.0}, "CL": 1590.0})
    excel_route._cache.clear()          # los tests no comparten builds viejos
    yield st
    excel_route._cache.clear()


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── Servicio: tokens por usuario ─────────────────────────────────────────────
def test_excel_access_lifecycle(auth_on):
    auth.create_user("mesa1", "clave123", "basico")
    assert auth.excel_info("mesa1") == {"enabled": False, "token": None}
    tok = auth.set_excel_access("mesa1", True)
    assert tok and auth.user_for_excel_token(tok) == "mesa1"
    # cortar invalida al instante pero conserva el token
    auth.set_excel_access("mesa1", False)
    assert auth.user_for_excel_token(tok) is None
    assert auth.excel_info("mesa1")["token"] == tok
    # re-habilitar: mismo token vuelve a valer
    assert auth.set_excel_access("mesa1", True) == tok
    assert auth.user_for_excel_token(tok) == "mesa1"
    # regenerar rota; el viejo muere
    nuevo = auth.regen_excel_token("mesa1")
    assert nuevo != tok
    assert auth.user_for_excel_token(tok) is None
    assert auth.user_for_excel_token(nuevo) == "mesa1"
    # reset de contraseña NO corta el acceso
    auth.set_password("mesa1", "otraclave9")
    assert auth.user_for_excel_token(nuevo) == "mesa1"
    # borrar al usuario mata el token
    auth.delete_user("mesa1")
    assert auth.user_for_excel_token(nuevo) is None


# ── HTTP: gating + shape ─────────────────────────────────────────────────────
async def test_snapshot_requiere_token(auth_on, store_con_datos):
    async with _client() as ac:
        assert (await ac.get("/excel/v1/snapshot")).status_code == 401
        assert (await ac.get("/excel/v1/seq")).status_code == 401
        r = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": "trucho"})
        assert r.status_code == 401


async def test_snapshot_shape_y_token_ok(auth_on, store_con_datos):
    auth.create_user("mesa2", "clave123", "basico")
    tok = auth.set_excel_access("mesa2", True)
    async with _client() as ac:
        r = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})
        assert r.status_code == 200
        data = r.json()
        q = data["quotes"]["GD30"]["24hs"]
        assert q["last"] == 1001.0 and q["bid"] == 1000.0 and q["ask"] == 1002.0
        assert q["close"] == 990.0 and q["close_date"] == "2026-07-21"
        assert q["var"] == pytest.approx(1001.0 / 990.0 - 1.0)
        assert data["quotes"]["GD30"]["CI"]["last"] == 999.5
        # cauciones y futuros van en secciones propias, no en quotes
        assert "PESOS" not in data["quotes"]
        assert not any(k.startswith("DLR/") for k in data["quotes"])
        assert {"fx", "mayorista", "futuros", "cauciones", "seq"} <= set(data)
        # ?token= en query también vale (el webview a veces no puede meter headers)
        r2 = await ac.get(f"/excel/v1/seq?token={tok}")
        assert r2.status_code == 200 and r2.text.isdigit()
        # ping identifica al usuario
        r3 = await ac.get("/excel/v1/ping", headers={"X-OMS-Token": tok})
        assert r3.json()["user"] == "mesa2"
        # cortar el acceso desde el servicio → 401 inmediato
        auth.set_excel_access("mesa2", False)
        excel_route._cache.clear()
        assert (await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})).status_code == 401


async def test_snapshot_cache_comparte_bytes(auth_on, store_con_datos):
    auth.create_user("mesa3", "clave123", "basico")
    tok = auth.set_excel_access("mesa3", True)
    async with _client() as ac:
        r1 = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})
        r2 = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})
        # mismo build dentro de la ventana de 1 s (bytes idénticos, mismo ts)
        assert r1.content == r2.content
        # filtro por especie
        r3 = await ac.get("/excel/v1/snapshot?codes=gd30", headers={"X-OMS-Token": tok})
        d3 = r3.json()
        assert set(d3["quotes"]) == {"GD30"} and d3["extras"] == {}


async def test_manifest_publico_y_hist(auth_on):
    async with _client() as ac:
        r = await ac.get("/excel/manifest.xml")
        assert r.status_code == 200 and "OfficeApp" in r.text
        assert "http://t/static/excel/taskpane.html" in r.text
        # hist requiere token
        assert (await ac.get("/excel/v1/hist/a3500")).status_code == 401


def test_snapshot_json_compacto(store_con_datos):
    body = excel_route._snapshot_bytes("")
    data = json.loads(body)
    # sin None: los campos ausentes no viajan
    q = data["quotes"]["GD30"]["CI"]
    assert "bid" not in q and q["last"] == 999.5
