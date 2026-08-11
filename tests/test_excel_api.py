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


async def test_manifest_base_override(auth_on):
    """`?base=` fija el host del manifest (la tarjeta de /admin lo usa para el
    manifest universal con localhost — cada notebook corre su propia app). Una
    base que no es http(s) se ignora y cae al host del request."""
    async with _client() as ac:
        r = await ac.get("/excel/manifest.xml",
                         params={"base": "http://localhost:8000/"})
        assert r.status_code == 200
        assert "http://localhost:8000/static/excel/functions.js" in r.text
        assert "http://t/" not in r.text
        # base inválida (no-http) → fallback al host del request, sin colarse
        r2 = await ac.get("/excel/manifest.xml", params={"base": "javascript:alert(1)"})
        assert r2.status_code == 200
        assert "javascript:" not in r2.text
        assert "http://t/static/excel/taskpane.html" in r2.text


async def test_admin_tarjeta_instalacion_excel(auth_on):
    """/admin muestra la guía de instalación multi-máquina con el link al
    manifest universal (localhost)."""
    async with _client() as ac:
        await ac.post("/login", data={"username": "rodricor93", "password": "Rc_874562",
                                      "next": "/yas"})
        r = await ac.get("/admin")
    assert r.status_code == 200
    assert "instalar en otra máquina" in r.text
    assert "manifest universal" in r.text
    # urlencode de Jinja deja las barras sin escapar: http%3A//localhost…
    assert "/excel/manifest.xml?base=http%3A//localhost" in r.text


# ── Calculadora YAS en celdas (/excel/v1/calc) ───────────────────────────────
async def test_calc_batch_requiere_token_y_calcula(auth_on):
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    auth.create_user("mesa3", "clave123", "basico")
    tok = auth.set_excel_access("mesa3", True)
    body = {"items": [
        {"code": "GD30", "modo": "precio", "valor": 78.5},
        {"code": "GD30", "modo": "tir", "valor": 0.14},
        {"code": "GD30", "modo": "precio", "valor": 78.5, "nominales": 1_000_000},
        {"code": "NOEXISTE", "modo": "precio", "valor": 100.0},
    ]}
    async with _client() as ac:
        assert (await ac.post("/excel/v1/calc", json=body)).status_code == 401
        r = await ac.post("/excel/v1/calc", json=body, headers={"X-OMS-Token": tok})
    assert r.status_code == 200
    res = r.json()["results"]
    # item 0: precio → tirea, igual que el YAS web (mismo compute_metrics)
    esperado = pricing.compute_metrics("GD30", "precio", 78.5,
                                       settle=pricing.settlement_date_str("24hs"),
                                       include_cashflows=False)
    assert res[0]["tirea"] == pytest.approx(esperado["tirea"])
    assert res[0]["tna"] == pytest.approx(esperado["tna"])
    assert res[0]["tna_convention_label"] == esperado["tna_convention_label"]
    # item 1: tir → precio (ida y vuelta consistente con el item 0)
    assert res[1]["precio_clean_pct"] == pytest.approx(78.5, rel=0.02)
    # item 2: con nominales viaja el ticket
    assert res[2]["vn_ticket"] == 1_000_000
    assert res[2]["monto_total"] == pytest.approx(1_000_000 * esperado["precio"])
    assert res[2]["interes"] == pytest.approx(1_000_000 * esperado["intereses_corridos"])
    # item 3: error POR ITEM, sin voltear el batch
    assert "error" in res[3] and "NOEXISTE" in res[3]["error"]


async def test_calc_batch_valida_entrada(auth_on):
    auth.create_user("mesa4", "clave123", "basico")
    tok = auth.set_excel_access("mesa4", True)
    h = {"X-OMS-Token": tok}
    async with _client() as ac:
        assert (await ac.post("/excel/v1/calc", json={}, headers=h)).status_code == 400
        assert (await ac.post("/excel/v1/calc", json={"items": []}, headers=h)).status_code == 400
        demasiados = {"items": [{"code": "GD30", "modo": "precio", "valor": 70.0 + i}
                                for i in range(41)]}
        assert (await ac.post("/excel/v1/calc", json=demasiados, headers=h)).status_code == 400
        # modo inválido y valor no numérico: error por item, 200 igual
        r = await ac.post("/excel/v1/calc", headers=h, json={"items": [
            {"code": "GD30", "modo": "banana", "valor": 1},
            {"code": "GD30", "modo": "precio", "valor": "hola"},
        ]})
        assert r.status_code == 200
        res = r.json()["results"]
        assert "Modo inválido" in res[0]["error"] and "error" in res[1]


async def test_calc_settle_custom_fx_y_tr(auth_on):
    """El 3er arg acepta fecha de liquidación custom (settle del YAS), `fx`
    viaja como fx_override, y tipo=tr devuelve el total return puntual."""
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    auth.create_user("mesa5", "clave123", "basico")
    tok = auth.set_excel_access("mesa5", True)
    h = {"X-OMS-Token": tok}
    fecha = "15/09/2026"
    async with _client() as ac:
        r = await ac.post("/excel/v1/calc", headers=h, json={"items": [
            {"code": "GD30", "modo": "precio", "valor": 78.5, "settle": fecha},
            {"code": "GD30", "modo": "precio", "valor": 78.5, "fx": 1500.0},
            {"code": "GD30", "modo": "precio", "valor": 78.5, "tipo": "tr",
             "tir_salida": 0.12, "fecha_salida": "30/12/2026", "nominales": 1_000_000},
            {"code": "GD30", "modo": "precio", "valor": 78.5, "tipo": "tr",
             "fecha_salida": "01/01/2020"},          # salida anterior al settle
        ]})
    assert r.status_code == 200
    res = r.json()["results"]
    # settle custom = mismo resultado que compute_metrics con esa fecha
    esp = pricing.compute_metrics("GD30", "precio", 78.5, settle=fecha,
                                  include_cashflows=False)
    assert res[0]["settle"] == fecha
    assert res[0]["tirea"] == pytest.approx(esp["tirea"])
    # fx pasa como override (passthrough exacto contra el motor)
    esp_fx = pricing.compute_metrics("GD30", "precio", 78.5,
                                     settle=pricing.settlement_date_str("24hs"),
                                     fx_override=1500.0, include_cashflows=False)
    assert res[1]["tirea"] == pytest.approx(esp_fx["tirea"])
    # TR: mismo desglose que tr_puntual
    esp_tr = pricing.tr_puntual("GD30", "precio", 78.5,
                                settle=pricing.settlement_date_str("24hs"),
                                tir_salida=0.12, fecha_salida="30/12/2026",
                                nominales=1_000_000)
    assert res[2]["tr"] == pytest.approx(esp_tr["tr"])
    assert res[2]["tea"] == pytest.approx(esp_tr["tea"])
    assert res[2]["pnl_total_m"] == pytest.approx(esp_tr["pnl_total_m"])
    assert res[2]["fecha_salida"] == "30/12/2026" and res[2]["dias"] == esp_tr["dias"]
    # TR con fecha imposible → error por item, batch vivo
    assert "error" in res[3] and "posterior" in res[3]["error"]


async def test_calc_sin_precio_usa_last_del_mercado(auth_on):
    """Precio omitido en modo precio → el server resuelve el last del store
    (reemplaza anidar OMS.QUOTE, que como streaming da #¡VALOR! en Office)."""
    from backend.services import bond_universe, marketdata_store as mds, pricing

    bond_universe.ensure_loaded()
    mds.get_store().update_from_md("MERV - XMEV - GD30 - 24hs", {"LA": {"price": 78.5}})
    auth.create_user("mesa6", "clave123", "basico")
    tok = auth.set_excel_access("mesa6", True)
    h = {"X-OMS-Token": tok}
    async with _client() as ac:
        r = await ac.post("/excel/v1/calc", headers=h, json={"items": [
            {"code": "GD30", "modo": "precio"},                       # sin valor → last
            {"code": "GD30", "modo": "precio", "nominales": 500_000},  # ticket al last
            {"code": "GD30", "modo": "tir"},                          # tir sin valor → error
            {"code": "ZZZZZ", "modo": "precio"},                      # sin especie con precio
        ]})
    assert r.status_code == 200
    res = r.json()["results"]
    esp = pricing.compute_metrics("GD30", "precio", 78.5,
                                  settle=pricing.settlement_date_str("24hs"),
                                  include_cashflows=False)
    assert res[0]["tirea"] == pytest.approx(esp["tirea"])
    assert res[1]["vn_ticket"] == 500_000
    assert res[1]["monto_total"] == pytest.approx(500_000 * esp["precio"])
    assert "error" in res[2]                       # tir necesita valor explícito
    assert "error" in res[3] and "Sin precio de mercado" in res[3]["error"]


@pytest.mark.asyncio
async def test_manifest_token_en_url_y_saneado() -> None:
    """Runtime CLÁSICO: el runtime de funciones es SEPARADO del panel y no
    siempre comparte OfficeRuntime.storage → el token va embebido en la URL de
    functions.html/taskpane.html. El valor se valida (alfabeto de token_urlsafe)
    para que no se pueda inyectar XML."""
    import xml.dom.minidom as MD

    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        ok = await ac.get("/excel/manifest.xml", params={"token": "AbC-123_xyzAbC123xyz"})
        bad = await ac.get("/excel/manifest.xml", params={"token": 'x"/><Evil>&'})
        none = await ac.get("/excel/manifest.xml")
    for r in (ok, bad, none):
        assert r.status_code == 200
        MD.parseString(r.text)                      # XML siempre bien formado
    assert "functions.html?token=AbC-123_xyzAbC123xyz" in ok.text
    assert "taskpane.html?token=AbC-123_xyzAbC123xyz" in ok.text
    assert "<Evil>" not in bad.text and "token=" not in bad.text   # inválido → se descarta
    assert "token=" not in none.text                               # sin token: compat
    assert "SharedRuntime" not in none.text                        # modelo clásico
