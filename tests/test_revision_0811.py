"""Revisión adversarial del glow-up (08/11) — lo que no vuelve:
- `empty()` escapa la causa; el error de una pestaña de Históricos no inyecta
  HTML del request (era un XSS reflejado por `| safe`);
- las páginas de error escapan título/detalle y llevan los headers de
  seguridad aunque las arme el handler de Exception (corre fuera del stack
  de middlewares); el detalle del 500 sólo lo ve el superuser;
- /salud no muestra rutas absolutas a un no-superuser;
- la pizarra avisa por header cuando el alta falló (Ctrl+K «+BONO»);
- app.js: `g` ignora el auto-repeat, las flechas de Ctrl+K saltan los
  encabezados y las prefs se reintentan si el POST falló."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

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


def _req(path: str = "/x", hx: bool = False, su: bool = False, accept: str = "") -> Request:
    headers = [(b"host", b"t")]
    if hx:
        headers.append((b"hx-request", b"true"))
    if accept:
        headers.append((b"accept", accept.encode()))
    r = Request({"type": "http", "method": "GET", "path": path, "query_string": b"", "scheme": "http",
                 "server": ("t", 80), "headers": headers, "app": None})
    r.state.is_superuser = su
    r.state.user = {"username": "su_test", "role": "superuser"} if su else {"username": "nico", "role": "basico"}
    return r


@pytest.mark.asyncio
async def test_pestana_de_historicos_con_fecha_maliciosa_no_inyecta_html() -> None:
    payload = "<img src=x onerror=alert(1)>"
    async with _client() as ac:
        r = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "f1": payload, "f2": "2026-01-02"})
    assert r.status_code == 200 and payload not in r.text
    if "hist-tab-error" in r.text:                     # cayó en el estado de error: el texto va escapado
        assert "&lt;img src=x onerror=alert(1)&gt;" in r.text


def test_empty_escapa_la_causa_y_deja_las_acciones() -> None:
    from backend.main import app
    tpl = app.state.templates.env.from_string(
        '{% from "partials/_estados.html" import empty %}{{ empty("t", causa, \'<a class="btn" href="/x">ir</a>\') }}')
    out = tpl.render(causa="<b>x</b> & y")
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in out and '<a class="btn" href="/x">ir</a>' in out


@pytest.mark.asyncio
async def test_pagina_error_escapa_y_lleva_headers_de_seguridad() -> None:
    from backend.main import app
    pe = app.state.pagina_error
    hx = pe(_req(hx=True), 500, "Algo falló", 'Err: <script>alert("x")</script>')
    assert hx.status_code == 500 and b"<script>" not in hx.body and b"&lt;script&gt;" in hx.body
    for h in ("x-frame-options", "content-security-policy", "x-content-type-options", "referrer-policy"):
        assert h in hx.headers, h
    js = pe(_req(path="/excel/v1/x"), 500, "Algo falló", "detalle")
    assert js.headers["content-type"].startswith("application/json") and "x-frame-options" in js.headers
    # el handler de Exception: detalle sólo para el superuser
    handler = app.exception_handlers[Exception]
    r_su = await handler(_req(hx=True, su=True), RuntimeError("C:\\Users\\pablo\\OneDrive\\Delta Bases\\x.xlsx"))
    r_no = await handler(_req(hx=True, su=False), RuntimeError("C:\\Users\\pablo\\OneDrive\\Delta Bases\\x.xlsx"))
    assert b"RuntimeError" in r_su.body and b"pablo" in r_su.body
    assert b"pablo" not in r_no.body and b"Error interno" in r_no.body and r_no.status_code == 500


@pytest.mark.asyncio
async def test_salud_oculta_rutas_absolutas_a_un_basico(auth_on, monkeypatch) -> None:
    from backend.services import positions, salud
    monkeypatch.setattr(positions, "status", lambda: {
        "loaded": False, "error": "Error leyendo composición: [Errno 13] 'C:\\Users\\pablo\\OneDrive - Delta\\Delta Bases\\Delta_Composicion.xlsx' "
                                  "y /home/desk/Delta Bases/Delta_PN.xlsx"})
    items = salud.resumen()
    assert "pablo" in next(i for i in items if i["key"] == "carteras")["detalle"]        # el servicio no filtra
    async with _client() as su:
        await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/salud"})
        await su.post("/admin/users", data={"username": "nico", "password": "clave123", "role": "basico"})
        assert "pablo" in (await su.get("/salud/body")).text                               # el superuser sí lo ve
    async with _client() as ac:
        await ac.post("/login", data={"username": "nico", "password": "clave123", "next": "/salud"})
        t = (await ac.get("/salud/body")).text
    assert "pablo" not in t and "/home/desk" not in t and "Delta_Composicion.xlsx" in t and "Delta_PN.xlsx" in t


@pytest.mark.asyncio
async def test_pizarra_avisa_por_header_cuando_no_agrego(tmp_path, monkeypatch) -> None:
    from backend.services import pizarra
    monkeypatch.setenv("PIZARRA_PATH", str(tmp_path / "p.json"))
    pizarra._version.clear()
    async with _client() as ac:
        r = await ac.post("/inicio/pizarra/agregar", data={"code": "NOEXISTE", "tipo": "cotizacion", "plazo": "24hs"})
        assert r.status_code == 200 and r.headers.get("X-Pizarra-Error") == "1" and "no es un bono" in r.text
        ok = await ac.post("/inicio/pizarra/agregar", data={"code": "TX28", "tipo": "cotizacion", "plazo": "24hs"})
        assert ok.status_code == 200 and "X-Pizarra-Error" not in ok.headers


@pytest.mark.asyncio
async def test_app_js_acorde_flechas_y_reintento_de_prefs() -> None:
    async with _client() as ac:
        js = (await ac.get("/static/js/app.js")).text
    assert "e.repeat" in js and "function mover(d)" in js and 'items[i].kind === "hdr"' in js
    assert "X-Pizarra-Error" in js and "window.yvToast" in js
    assert "function ok() { Object.keys(d).forEach" in js                      # visto[k] recién con el POST ok
