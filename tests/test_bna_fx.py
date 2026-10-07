"""Dólar BNA para el add-in de Excel (=OMS.FX("bna_…"), 07/10): parser tolerante
del HTML de bna.com.ar, poller horario en thread de fondo (nunca en un
request), persistencia local y la sección `bna` del snapshot."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bna_fx

# Estructura de las páginas del BNA (Personas → Billetes, Empresas → Divisas):
# tabla con la fila "Dolar U.S.A", compra / venta es-AR y la fecha del dato.
_PERSONAS = """
<html><body>
<div class="cotizacion">
  <div id="billetes" class="tab-pane active">
    <table class="table cotizacion">
      <thead><tr><th>Monedas</th><th>Compra</th><th>Venta</th></tr></thead>
      <tbody>
        <tr><td class="tit">Dolar U.S.A</td><td>1.395,0000</td><td>1.445,0000</td></tr>
        <tr><td class="tit">Euro</td><td>1.620,0000</td><td>1.700,0000</td></tr>
        <tr><td class="tit">Real *</td><td>240,0000</td><td>270,0000</td></tr>
      </tbody>
    </table>
    <div class="fechaCot">7/10/2026</div>
  </div>
</div>
</body></html>
"""
_EMPRESAS = """
<html><body>
<div id="divisas" class="tab-pane">
  <table class="table cotizacion">
    <thead><tr><th>Monedas</th><th>Compra</th><th>Venta</th></tr></thead>
    <tbody>
      <tr><td class="tit">Dólar U.S.A.</td><td>1387,5000</td><td>1407,5000</td></tr>
    </tbody>
  </table>
  <div class="fechaCot">Fecha: 06/10/2026 16:30</div>
</div>
</body></html>
"""


@pytest.fixture()
def bna_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("BNA_FX_PATH", str(tmp_path / "bna.json"))
    monkeypatch.setenv("BNA_FX", "0")
    bna_fx.reset_para_tests()
    yield tmp_path / "bna.json"
    bna_fx.reset_para_tests()


def test_parsear_billetes_y_divisas_es_ar_con_fecha() -> None:
    b = bna_fx.parsear(_PERSONAS)
    assert b == {"billete": {"compra": 1395.0, "venta": 1445.0, "fecha": "2026-10-07"}}
    d = bna_fx.parsear(_EMPRESAS)
    assert d == {"divisa": {"compra": 1387.5, "venta": 1407.5, "fecha": "2026-10-06"}}
    # una página con las dos tablas (o sin fecha, o con basura) también se tolera
    ambas = _PERSONAS.replace("</body>", _EMPRESAS.split("<body>")[1])
    assert set(bna_fx.parsear(ambas)) == {"billete", "divisa"}
    sin_fecha = _PERSONAS.replace("7/10/2026", "")
    assert bna_fx.parsear(sin_fecha)["billete"]["fecha"] is None
    assert bna_fx.parsear("<html>nada</html>") == {} and bna_fx.parsear("") == {}
    roto = _PERSONAS.replace("1.395,0000", "n/d")
    assert bna_fx.parsear(roto) == {}                      # fila sin números → sección salteada
    assert bna_fx.parsear(_PERSONAS.replace("1.445,0000", "0,0000")) == {}   # venta 0 no es dato


def test_refresh_persiste_y_snapshot(bna_tmp, monkeypatch) -> None:
    assert bna_fx.snapshot()["billete_venta"] is None
    paginas = {"https://www.bna.com.ar/Personas": _PERSONAS, "https://www.bna.com.ar/Empresas": _EMPRESAS}
    llamadas: list = []

    def fetch(url):
        llamadas.append(url)
        return paginas[url]

    monkeypatch.setattr(bna_fx, "_fetch", fetch)
    assert bna_fx.refresh() is True
    assert llamadas == list(bna_fx._DEFAULT_URLS)
    s = bna_fx.snapshot()
    assert (s["billete_compra"], s["billete_venta"], s["billete_fecha"]) == (1395.0, 1445.0, "2026-10-07")
    assert (s["divisa_compra"], s["divisa_venta"], s["divisa_fecha"]) == (1387.5, 1407.5, "2026-10-06")
    assert s["fuente"] == "bna.com.ar" and s["error"] is None and s["actualizado"] is not None
    assert bna_fx.refresh() is False                        # mismo dato: sin cambio (y sin reescribir)
    raw = json.loads(bna_tmp.read_text(encoding="utf-8"))
    assert raw["billete"]["venta"] == 1445.0 and raw["divisa"]["fecha"] == "2026-10-06"
    # reinicio del proceso: arranca con el último dato guardado
    bna_fx.reset_para_tests()
    s = bna_fx.snapshot()
    assert s["billete_venta"] == 1445.0 and s["fuente"] == "archivo"
    # una página caída no borra la otra ni el último dato; el error queda visible
    def fetch2(url):
        if url.endswith("Empresas"):
            raise OSError("sin red")
        return _PERSONAS.replace("1.445,0000", "1.450,0000")
    monkeypatch.setattr(bna_fx, "_fetch", fetch2)
    assert bna_fx.refresh() is True
    s = bna_fx.snapshot()
    assert s["billete_venta"] == 1450.0 and s["divisa_venta"] == 1407.5 and "sin red" in s["error"]
    # todo caído: False, último dato intacto
    monkeypatch.setattr(bna_fx, "_fetch", lambda url: (_ for _ in ()).throw(OSError("sin red")))
    assert bna_fx.refresh() is False and bna_fx.snapshot()["billete_venta"] == 1450.0
    # apagado por env: start() no levanta thread
    bna_fx.start()
    assert bna_fx._thread is None or not bna_fx._thread.is_alive()


def test_urls_y_path_por_env(monkeypatch) -> None:
    monkeypatch.setenv("BNA_FX_URLS", "http://a/x, http://b/y")
    assert bna_fx._urls() == ["http://a/x", "http://b/y"]
    monkeypatch.delenv("BNA_FX_URLS")
    assert bna_fx._urls() == list(bna_fx._DEFAULT_URLS)
    assert bna_fx.habilitado() is False                      # la suite corre con BNA_FX=0


def test_snapshot_de_excel_lleva_la_seccion_bna(bna_tmp, monkeypatch) -> None:
    from backend.routes import excel as excel_route
    monkeypatch.setattr(bna_fx, "_fetch", lambda url: _PERSONAS if url.endswith("Personas") else _EMPRESAS)
    bna_fx.refresh()
    snap = excel_route._build(None)
    assert snap["bna"]["billete_venta"] == 1445.0 and snap["bna"]["divisa_compra"] == 1387.5
    assert snap["bna"]["billete_fecha"] == "2026-10-07"
    json.dumps(snap, default=str)
    # failure-silent como las demás secciones
    monkeypatch.setattr(excel_route.bna_fx_svc, "snapshot", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = excel_route._build(None)
    assert snap["bna"] == {} and "quotes" in snap


@pytest.mark.asyncio
async def test_endpoint_snapshot_incluye_bna(bna_tmp, monkeypatch) -> None:
    from backend.main import app
    monkeypatch.setattr(bna_fx, "_fetch", lambda url: _PERSONAS if url.endswith("Personas") else _EMPRESAS)
    bna_fx.refresh()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/excel/v1/snapshot?codes=TX26,GD30C,AL30D")   # key propia: no pisa el cache de otro test
        assert r.status_code == 200
        b = r.json()["bna"]
        assert b["divisa_venta"] == 1407.5 and b["billete_compra"] == 1395.0 and b["divisa_fecha"] == "2026-10-06"


def test_docs_del_add_in_mencionan_bna() -> None:
    from pathlib import Path
    ex = Path(__file__).resolve().parents[1] / "backend/static/excel"
    fj = json.loads((ex / "functions.json").read_text(encoding="utf-8"))
    fx = next(f for f in fj["functions"] if f["id"] == "FX")
    assert "bna_divisa_venta" in fx["parameters"][0]["description"] and "bna_billete_compra" in fx["description"]
    assert "bna_billete_venta" in (ex / "taskpane.html").read_text(encoding="utf-8")
    assert "bna_divisa_compra" in (ex / "FORMULAS.md").read_text(encoding="utf-8")
