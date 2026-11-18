"""Add-in de Excel: las funciones de cálculo no pueden quedar "ocupadas" (18/11).

Desk: "el add-in anda medio medio … OMS.TIREA se queda ocupado mucho tiempo,
a veces anda, a veces no", con 1 a 4 celdas. El server calcula cada celda en
milisegundos; lo que faltaba era el plazo: `OMSCalc.sendChunk` hacía un
`fetch` sin timeout ni reintento, y un pedido colgado entre Excel y el puente
https dejaba la celda en #¡OCUPADO! y `pending[k]` vivo para siempre (cada F9
de la MISMA fórmula se colgaba del pedido muerto hasta recargar el add-in).

- JS real en Node (`tests/excel_calc_harness.cjs`): plazo + UN reintento,
  error legible si tampoco responde, la misma fórmula se puede re-pedir,
  5xx / red / cuerpo cortado reintentan, 401 / 4xx no, dedup y memo intactos.
- Server: un batch lento deja una línea con dónde se fue el tiempo (espera
  del pool vs cálculo, item más lento).
- Puente TLS: un request de /excel/* lento, cortado o con 502 deja una línea
  (ruta sin query: el manifest per-usuario lleva ?token=).
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import ssl
import subprocess
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.routes import excel as excel_route
from backend.services import auth, tls_bridge

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_calc_js_plazo_y_reintento_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "excel_calc_harness.cjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert len(out) >= 13
    malos = {k: v for k, v in out.items() if v is not True}
    assert not malos, malos


def test_sello_de_build_y_plazos_en_el_js() -> None:
    js = (ROOT / "backend" / "static" / "excel" / "functions.js").read_text(encoding="utf-8")
    assert int(js.split('OMS_BUILD = "v')[1].split(" ")[0]) >= 27
    assert "CALC_TIMEOUTS_MS = [10000, 20000]" in js
    # el POST del cálculo ya no es un fetch pelado
    cuerpo = js[js.index("function postCalc("):js.index("function flush()")]
    assert "ctrl.abort()" in cuerpo and "Promise.race([work, guard])" in cuerpo


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


@pytest.mark.asyncio
async def test_calc_lento_deja_una_linea_con_el_motivo(auth_on, monkeypatch, caplog) -> None:
    from backend.main import app
    from backend.services import bond_universe

    bond_universe.ensure_loaded()
    auth.create_user("mesa_lenta", "clave123", "basico")
    tok = auth.set_excel_access("mesa_lenta", True)
    body = {"items": [{"code": "GD30", "modo": "precio", "valor": 78.5},
                      {"code": "AL30D", "modo": "precio", "valor": 70.0}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        with caplog.at_level(logging.WARNING, logger="backend.excel.addin"):
            r = await ac.post("/excel/v1/calc", json=body, headers={"X-OMS-Token": tok})
            assert r.status_code == 200 and len(r.json()["results"]) == 2
            assert all("tirea" in x for x in r.json()["results"])
            assert not [x for x in caplog.records if "[excel calc] lento" in x.getMessage()]   # sano: silencio
            monkeypatch.setattr(excel_route, "_CALC_LENTO_S", 0.0)
            r = await ac.post("/excel/v1/calc", json=body, headers={"X-OMS-Token": tok})
            assert r.status_code == 200 and all("tirea" in x for x in r.json()["results"])
    lineas = [x.getMessage() for x in caplog.records if "[excel calc] lento" in x.getMessage()]
    assert len(lineas) == 1
    assert "2 item(s)" in lineas[0] and "espera del pool" in lineas[0] and "más lento: precio " in lineas[0]


def test_calc_batch_medido_devuelve_lo_mismo_que_el_batch() -> None:
    import time

    from backend.services import bond_universe

    bond_universe.ensure_loaded()
    items = [{"code": "GD30", "modo": "precio", "valor": 78.5}, "basura",
             {"code": "NOEXISTE", "modo": "precio", "valor": 100.0}, {"code": "GD30", "tipo": "meta"}]
    res, espera, calculo, peor = excel_route._calc_batch_medido(items, time.perf_counter())
    assert res == excel_route._calc_batch(items)
    assert len(res) == len(items) and espera >= 0 and calculo >= 0 and peor


def test_ruta_del_puente_sin_query_ni_caracteres_raros() -> None:
    assert tls_bridge._ruta(b"POST /excel/v1/calc HTTP/1.1\r\nHost: x\r\n\r\n") == "POST /excel/v1/calc"
    assert tls_bridge._ruta(b"GET /static/excel/functions.html?token=SECRETO&x=1 HTTP/1.1\r\n\r\n") == (
        "GET /static/excel/functions.html")
    assert "\n" not in tls_bridge._ruta(b"GET /excel/a\x0bb\x07 HTTP/1.1\r\n\r\n")
    assert tls_bridge._ruta(b"") == " "


def test_avisos_del_puente_solo_del_addin_y_con_throttle(monkeypatch, caplog) -> None:
    monkeypatch.setattr(tls_bridge, "_avisos", {})
    with caplog.at_level(logging.WARNING, logger="backend.tls"):
        tls_bridge._avisar("lento", "GET /market/events", "120 s")          # la web por https: no es el add-in
        tls_bridge._avisar("lento", "POST /excel/v1/calc", "7.2 s entre el pedido y el fin de la respuesta")
        tls_bridge._avisar("lento", "POST /excel/v1/calc", "8.0 s")          # dentro del throttle
        tls_bridge._avisar("corte", "POST /excel/v1/calc", "la conexión superó 120 s y se cerró")
    msgs = [x.getMessage() for x in caplog.records]
    assert msgs == ["[tls] lento: POST /excel/v1/calc — 7.2 s entre el pedido y el fin de la respuesta",
                    "[tls] corte: POST /excel/v1/calc — la conexión superó 120 s y se cerró"]


@pytest.mark.asyncio
async def test_puente_avisa_request_lento_y_502(tmp_path, monkeypatch, caplog) -> None:
    """Puente real sobre un backend que tarda: con el umbral en 0 queda la
    línea `lento` con la ruta sin el token; con el backend caído, `502`."""
    from backend.tools import https_local

    certs = https_local.generate(tmp_path, ["localhost", "127.0.0.1"])
    leaf_cert, leaf_key, ca = certs["leaf_cert"], certs["leaf_key"], certs["ca_cert"]

    async def app(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        await asyncio.sleep(0.05)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    back = await asyncio.start_server(app, "127.0.0.1", 0)
    puerto = back.sockets[0].getsockname()[1]
    monkeypatch.setattr(tls_bridge, "_avisos", {})
    monkeypatch.setattr(tls_bridge, "_LENTO_S", 0.0)
    bridge = tls_bridge.TlsBridge(leaf_cert, leaf_key, "127.0.0.1", 0, "127.0.0.1", puerto)
    await bridge.start()
    bport = bridge._server.sockets[0].getsockname()[1]
    ctx = ssl.create_default_context(cafile=str(ca))
    try:
        with caplog.at_level(logging.WARNING, logger="backend.tls"):
            async with httpx.AsyncClient(verify=ctx) as c:
                r = await c.post(f"https://127.0.0.1:{bport}/excel/v1/calc?token=SECRETO", content=b"{}")
                assert r.status_code == 200 and r.text == "ok"
                back.close()
                await back.wait_closed()
                r = await c.get(f"https://127.0.0.1:{bport}/excel/v1/seq")
                assert r.status_code == 502
            await asyncio.sleep(0.05)
    finally:
        await bridge.stop()
    msgs = [x.getMessage() for x in caplog.records]
    assert any(m.startswith("[tls] lento: POST /excel/v1/calc — ") for m in msgs), msgs
    assert any(m.startswith("[tls] 502: GET /excel/v1/seq — ") for m in msgs), msgs
    assert not any("SECRETO" in m for m in msgs)
