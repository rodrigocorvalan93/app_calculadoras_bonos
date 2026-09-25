"""Gráficos · tabla de los bonos graficados (cajón abajo del chart).

- `/graficos/data` lleva en `meta[code]` la ficha estática (vto DD/MM/AAAA,
  calificación, industria) también con fuente CAFCI.
- La página trae el cajón colapsado con la tabla vacía (la arma charts.js).
- Las funciones puras de charts.js (filas + HTML) corren en Node contra un
  payload de muestra (tests/graficos_tabla_harness.cjs).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _seed_cer():
    from backend.services import bond_universe, curves, marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])
    if len(codes) < 4:
        pytest.skip("curva CER insuficiente")
    store = mds.get_store()
    for i, c in enumerate(codes):
        store.update_from_md(syms.md_symbol(c, "24hs"),
                             {"LA": {"price": 95.0 + i * 0.7}, "CL": {"price": 94.9 + i * 0.7},
                              "EV": 2e7, "NV": 2e5})
    return codes


def test_bond_meta_trae_industria_y_clasificacion() -> None:
    from backend.services import bond_universe, pricing
    bond_universe.ensure_loaded()
    m = pricing.bond_meta("TX26")
    assert m.get("industria") and m.get("clasificacion") == "Soberano"
    assert pricing.bond_meta("NO_EXISTE_XYZ") == {}


def test_graf_ficha() -> None:
    from backend.routes import curves as rc
    from backend.services import bond_universe
    bond_universe.ensure_loaded()
    f = rc._graf_ficha("TX26")
    assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", f["vto"]) and f["cal"] and f["ind"]
    assert rc._graf_ficha("NO_EXISTE_XYZ") == {"vto": None, "cal": None, "ind": None}


@pytest.mark.asyncio
async def test_graficos_data_meta_lleva_la_ficha() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed_cer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        j = (await ac.get("/graficos/data?curve=cer&only_quoting=false")).json()
    codes = [c for c in j["codes"] if c]
    assert codes and j["n"] > 0
    for c in codes:
        m = j["meta"][c]
        assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", m["vto"]), c
        assert m["cal"] and m["ind"] and m["mon"]
        assert m["dur"] is not None and m["tir"] is not None


def test_graf_pts_cafci_lleva_la_ficha(monkeypatch) -> None:
    from backend.routes import curves as rc
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    codes = (curves.build_curve_codes().get("cer") or [])[:4]
    if len(codes) < 4:
        pytest.skip("curva CER insuficiente")
    fake = {c: {"byma": c, "tir": 12.5 + i, "mod_dur": 1.0 + i, "moneda": "ARS"} for i, c in enumerate(codes)}
    monkeypatch.setattr(rc, "_cafci_idx", lambda: fake)
    pts = rc._graf_pts_cafci("cer", "tirea", None, None, set())
    assert [p[0] for p in pts] == codes
    for p in pts:
        meta = p[6]
        assert meta["src"] == "CAFCI" and meta["p"] is None
        assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", meta["vto"]) and meta["cal"] and meta["ind"]


@pytest.mark.asyncio
async def test_pagina_graficos_trae_el_cajon() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/graficos")
    assert r.status_code == 200
    assert 'id="graf-tabla"' in r.text and 'id="graf-tabla-toggle"' in r.text
    assert "Bonos del gráfico" in r.text and 'id="graf-tabla-body" hidden' in r.text
    # abajo de todo: después del cajón de emisiones
    assert r.text.index('id="graf-tabla-card"') > r.text.index('id="graf-emis-card"')


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_tabla_funciones_puras_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "graficos_tabla_harness.cjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode in (0, 1), r.stderr
    out = json.loads(r.stdout)
    assert out["ok"], out["fallos"]
    assert out["n"] == 4


def test_charts_js_arma_la_tabla_en_cada_render() -> None:
    """Sin node: el render del chart llama a la tabla y el cajón recuerda su estado."""
    js = (ROOT / "backend" / "static" / "js" / "charts.js").read_text(encoding="utf-8")
    assert "function grafTablaRows(j)" in js and "function grafTablaHTML(rows, metric, conCurva)" in js
    assert js.count("renderTabla(j)") >= 2                       # sin datos y con datos
    assert "graf_tabla_open" in js and "tablaDirty" in js
