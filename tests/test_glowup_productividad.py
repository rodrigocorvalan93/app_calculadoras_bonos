"""Glow-up D / E (06/11) — productividad: prefs por usuario en el server
(/prefs), Ctrl+K con acciones / recientes / "+BONO a la pizarra", atajos con
leyenda, CSS de impresión y topbar compacta; y la línea «hoy» de Inicio."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, hoy as hoy_svc, prefs

_BA = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


@pytest.fixture()
def prefs_tmp(tmp_path, monkeypatch):
    p = tmp_path / "prefs.json"
    monkeypatch.setenv("PREFS_PATH", str(p))
    return p


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _login(ac: AsyncClient, user: str, clave: str) -> None:
    await ac.post("/login", data={"username": user, "password": clave, "next": "/inicio"})


# ── prefs ───────────────────────────────────────────────────────────────────
def test_prefs_servicio_allowlist_y_persistencia(prefs_tmp) -> None:
    assert prefs.load_user("ana") == {}
    out = prefs.set_user("ana", {"yas_theme": "light", "fx_rail": "0", "zzz": "no", "ck_recent": [{"href": "/yas"}],
                                 "book-y": "x" * 5000})
    assert out == {"yas_theme": "light", "fx_rail": "0", "ck_recent": '[{"href": "/yas"}]'}   # lista → JSON; largo afuera
    assert prefs.load_user("ana") == out and prefs.load_user("juan") == {}
    out = prefs.set_user("ana", {"fx_rail": None, "pos_fondo": "4"})                              # None borra
    assert out == {"yas_theme": "light", "ck_recent": '[{"href": "/yas"}]', "pos_fondo": "4"}
    assert prefs_tmp.is_file() and "ana" in prefs_tmp.read_text(encoding="utf-8")
    # archivo corrupto: se aparta y se arranca vacío sin tirar
    prefs_tmp.write_text("{no json", encoding="utf-8")
    assert prefs.load_user("ana") == {}


@pytest.mark.asyncio
async def test_prefs_http_por_usuario(auth_on, prefs_tmp) -> None:
    async with _client() as su:
        await _login(su, "su_test", "clave-de-test-2026!")
        await su.post("/admin/users", data={"username": "nico", "password": "clave123", "role": "basico"})
        r = await su.post("/prefs", json={"yas_theme": "delta", "nada": "x"})
        assert r.status_code == 200 and r.json()["prefs"] == {"yas_theme": "delta"} and r.json()["user"] == "su_test"
        assert (await su.post("/prefs", content=b"[1,2", headers={"Content-Type": "application/json"})).status_code == 400
    async with _client() as ac:
        await _login(ac, "nico", "clave123")
        g = await ac.get("/prefs")
        assert g.status_code == 200 and g.json() == {"user": "nico", "prefs": {}}            # las de otro no se ven
        await ac.post("/prefs", json={"fx_rail": "0"})
        assert (await ac.get("/prefs")).json()["prefs"] == {"fx_rail": "0"}
    async with _client() as anon:
        assert (await anon.get("/prefs")).status_code in (302, 303, 401, 403)


# ── Ctrl+K · atajos · CSS ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ctrlk_atajos_prefs_y_css() -> None:
    async with _client() as ac:
        js = (await ac.get("/static/js/app.js")).text
        css = (await ac.get("/static/css/style.css")).text
    for tok in ("ck_recent", 'kind: "piz"', "/inicio/pizarra/agregar", "Salud de la app", "Qué hay de nuevo",
                "window.yvShortcuts", 'CHORD = { i: "/inicio"', "window.ckIsOpen", 'fetch("/prefs"', "sendBeacon",
                "#i-' + name"):
        assert tok in js, tok
    assert "📈" not in js.split("Ctrl+K: búsqueda global", 1)[1].split("Atajos de teclado con leyenda", 1)[0]
    for tok in ("@media print", "#kb-overlay", ".ck-hdr", ".ini-hoy", ".mkt-clocks { display: none; }"):
        assert tok in css, tok


# ── Inicio · línea «hoy» ────────────────────────────────────────────────────
def test_linea_hoy_calendario() -> None:
    cierre = {"estado": "ok", "texto": "✓ cierre 05/11"}
    # viernes 06/11/2026 = Día del bancario (feriado cargado a mano) a las 12:00
    h = hoy_svc.linea_hoy(datetime(2026, 11, 6, 12, 0, tzinfo=_BA), cierre=cierre)
    assert h["feriado_hoy"] == "Día del bancario" and not h["es_habil"] and h["rueda_estado"] == "off"
    assert h["dia_txt"] == "viernes 6 de noviembre" and h["fecha_fmt"] == "06/11/2026"
    # 09/11 también es feriado; desde un día sin rueda CI y 24 hs liquidan el
    # primer hábil (misma convención que pricing.settlement_date_str)
    assert h["liq_ci"] == "10/11/2026" and h["liq_24"] == "10/11/2026"
    assert h["prox_feriado"]["fecha_fmt"] == "09/11/2026" and h["prox_feriado"]["en_dias"] == 3
    assert h["cierre_cls"] == "ok" and h["cierre_txt"] == "Cierre 05/11"
    # jueves 05/11 a las 11:00: rueda abierta, liquida CI hoy, próximo feriado mañana
    h = hoy_svc.linea_hoy(datetime(2026, 11, 5, 11, 0, tzinfo=_BA), cierre={"estado": "falta", "texto": "falta cierre 04/11"})
    assert h["es_habil"] and h["rueda_estado"] == "ok" and "abierta hasta" in h["rueda_txt"]
    assert h["liq_ci"] == "05/11/2026" and h["prox_feriado"]["nombre"] == "Día del bancario"
    assert h["cierre_cls"] == "err"
    # sábado: sin rueda; domingo 20:00 también
    assert "fin de semana" in hoy_svc.linea_hoy(datetime(2026, 11, 7, 12, 0, tzinfo=_BA), cierre=cierre)["rueda_txt"]
    h = hoy_svc.linea_hoy(datetime(2026, 11, 10, 18, 30, tzinfo=_BA), cierre={})
    assert h["rueda_estado"] == "off" and "cerró" in h["rueda_txt"] and h["cierre_cls"] == "off"
    # Día de la Soberanía (20/11) trasladado al lunes 23/11 por el calendario oficial
    assert hoy_svc.proximo_feriado(date(2026, 11, 10))["fecha_fmt"] == "23/11/2026"


@pytest.mark.asyncio
async def test_inicio_trae_la_linea_hoy() -> None:
    async with _client() as ac:
        r = await ac.get("/inicio")
        p = await ac.get("/inicio/hoy")
    assert r.status_code == 200 and 'id="inicio-hoy"' in r.text and 'class="ini-hoy"' in r.text
    assert "Liquida CI" in r.text and "Cierre histórico:" in r.text and 'href="/salud"' in r.text
    assert p.status_code == 200 and 'class="ini-hoy"' in p.text and "<html" not in p.text
