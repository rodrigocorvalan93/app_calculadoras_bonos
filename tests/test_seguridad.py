"""Endurecimiento de seguridad — regresiones de la revisión.

Cubre: gating de subárbol de Posiciones/Matriz (data confidencial no cruza rol),
security headers + defensa CSRF por Origin, tope anti-DoS del parser ad-hoc,
allowlist de host del manifest de Excel, y el guard de arranque que impide
servir sin muro en un host expuesto.
"""
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


async def _login(ac: AsyncClient, user: str, pwd: str):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


# ── #1 · Posiciones / Matriz: los partials de datos se gatean por subárbol ──────
@pytest.mark.asyncio
async def test_posiciones_matriz_data_no_cruza_rol(auth_on):
    """Un básico (sin las pestañas Posiciones/Matriz) recibe 403 no sólo en la
    página sino también en los partials de datos, que antes quedaban abiertos y
    filtraban las tenencias reales de los fondos."""
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "nico", "password": "clave123",
                                             "role": "basico"})
        await su.post("/admin/users", data={"username": "prem", "password": "clave123",
                                             "role": "premium"})
    async with _client() as ac:
        await _login(ac, "nico", "clave123")
        for path in ("/posiciones", "/posiciones/table", "/posiciones/targets",
                     "/matriz", "/matriz/table"):
            assert (await ac.get(path)).status_code == 403, path
    # premium (tiene ambas pestañas por default) pasa el gate
    async with _client() as ac:
        await _login(ac, "prem", "clave123")
        assert (await ac.get("/posiciones/table")).status_code == 200
        assert (await ac.get("/matriz/table")).status_code == 200


# ── #5 · Security headers + defensa CSRF por Origin ─────────────────────────────
@pytest.mark.asyncio
async def test_security_headers_presentes():
    async with _client() as ac:
        r = await ac.get("/login")
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "strict-origin" in (r.headers.get("referrer-policy") or "")
    csp = r.headers.get("content-security-policy") or ""
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp


@pytest.mark.asyncio
async def test_csrf_origin_cruzado_bloqueado():
    async with _client() as ac:
        # POST con Origin de otro host → 403 (antes de tocar la ruta/auth)
        malo = await ac.post("/login", data={"username": "x", "password": "y"},
                             headers={"origin": "http://evil.example"})
        assert malo.status_code == 403
        # Origin del mismo host → pasa el chequeo (login corre; credencial mala)
        bueno = await ac.post("/login", data={"username": "x", "password": "y"},
                              headers={"origin": "http://t"})
        assert bueno.status_code != 403
        # sin Origin ni Referer (cliente no-browser) → pasa
        sin = await ac.post("/login", data={"username": "x", "password": "y"})
        assert sin.status_code != 403


@pytest.mark.asyncio
async def test_csrf_no_aplica_a_excel_token():
    """/excel/* se autentica por token (no cookie) → sin CSRF de credencial
    ambiente; el chequeo de Origin no debe bloquearlo (responde 401 por token)."""
    async with _client() as ac:
        r = await ac.post("/excel/v1/calc", headers={"origin": "http://evil.example"})
    assert r.status_code != 403


# ── #3 · Tope anti-DoS del parser de ficha ad-hoc ───────────────────────────────
def test_adhoc_rechaza_secuencia_gigante():
    from backend.services import adhoc
    with pytest.raises(ValueError):
        adhoc.parse_ficha('{"Código": "X", "z": [0]*900000000}')
    # la aritmética legítima de listas sigue funcionando
    _n, ficha = adhoc.parse_ficha('{"Código": "TX26", "amort": [0]*6 + [8]*12}')
    assert ficha["amort"] == [0] * 6 + [8] * 12


# ── #4 · Manifest de Excel: allowlist de host + sin inyección XML ───────────────
@pytest.mark.asyncio
async def test_manifest_base_allowlist():
    async with _client() as ac:
        # host arbitrario → se ignora, cae al host de descarga (no aparece)
        r = await ac.get("/excel/manifest.xml", params={"base": "http://evil.example.com:8000"})
        assert r.status_code == 200 and "evil.example.com" not in r.text
        # loopback está permitido → se respeta
        r2 = await ac.get("/excel/manifest.xml", params={"base": "http://127.0.0.1:9000"})
        assert r2.status_code == 200 and "127.0.0.1:9000" in r2.text
        # intento de inyección XML → no se refleja el markup
        r3 = await ac.get("/excel/manifest.xml", params={"base": 'https://x"/><Evil>'})
        assert r3.status_code == 200 and "<Evil>" not in r3.text


# ── #2 · Guard de arranque: sin muro + host expuesto = no arranca ───────────────
def test_arranque_rechaza_sin_muro_en_host_expuesto(monkeypatch):
    from backend import main as bmain
    monkeypatch.setattr(settings, "auth_enabled", False)
    # combo peligroso: sin muro + 0.0.0.0 → RuntimeError
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError):
        bmain.create_app()
    # sin muro pero en loopback (dev local) → arranca normal
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    app = bmain.create_app()
    assert app is not None


@pytest.mark.asyncio
async def test_paginas_del_addin_excel_sin_headers_restrictivos():
    """Las páginas del add-in viven en /static/excel/* y las FRAMEA Office +
    cargan office.js del CDN. X-Frame-Options: DENY y CSP script-src 'self' las
    rompían (runtime de funciones sin red → celdas en #N/D). Deben quedar EXENTAS,
    igual que /excel/*. El resto del front web SÍ conserva los headers."""
    async with _client() as ac:
        for p in ("/static/excel/functions.html", "/static/excel/taskpane.html",
                  "/static/excel/functions.js"):
            r = await ac.get(p)
            assert r.status_code == 200, p
            assert r.headers.get("x-frame-options") is None, p
            assert r.headers.get("content-security-policy") is None, p
        # el front web sigue protegido
        r = await ac.get("/static/css/style.css")
        assert r.headers.get("x-frame-options") == "DENY"
