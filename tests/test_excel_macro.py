"""OMS.MACRO en el add-in de Excel: último dato macro del BCRA en una celda.

La fuente es services.historico — el mismo backup BCRA de OMS.HIST y del riel
del dólar — así la celda muestra lo que muestra la web. El add-in devuelve el
valor o, con VERDADERO, la fecha del dato como serial de Excel. `tamar5` /
`badlar5` = promedio de las últimas 5 ruedas, el benchmark de OMS.MARGEN.

Desde la build v25 la función STREAMEA como OMS.FX: las 8 series viajan en la
sección `macro` de /excel/v1/snapshot (`_macro_section`, la misma
`_calc_macro`) y la celda se actualiza sola cuando la app refresca el dato —
antes era una async clásica con memo de 5 min y había que tocar la celda o
Ctrl+Alt+F9. El item `tipo: "macro"` del batch /excel/v1/calc queda para los
add-ins con el functions.js viejo cacheado."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings

ROOT = Path(__file__).resolve().parents[1]


def _series() -> dict:
    from backend.services import historico

    s = historico.ensure_loaded()["series"]
    if not s.get("tamar") or not s.get("a3500"):
        pytest.skip("sin backup BCRA en este entorno")
    return s


def test_calc_macro_ultimo_dato_alias_y_promedio_5_ruedas() -> None:
    from backend.routes.excel import _calc_macro
    from backend.services import pricing

    series = _series()
    tam = series["tamar"]["points"]
    m = _calc_macro("tamar")
    assert m["serie"] == "tamar" and m["valor"] == float(tam[-1][1]) and m["fecha"] == str(tam[-1][0])[:10]
    assert date.fromisoformat(m["fecha"]) >= date(2024, 1, 1) and m["n"] == len(tam) and m["label"]
    # case-insensitive, con espacios, alias, y las keys en mayúscula del backup (CER / UVA)
    assert _calc_macro(" TAMAR ")["valor"] == m["valor"]
    assert _calc_macro("cer")["serie"] == "cer" and _calc_macro("UVA")["serie"] == "uva"
    a35 = series["a3500"]["points"][-1]
    assert _calc_macro("mayorista")["valor"] == _calc_macro("a3500")["valor"] == float(a35[1])
    assert _calc_macro("inflacion")["serie"] == "inflamom"
    # promedio de 5 ruedas = el benchmark de OMS.MARGEN (pricing._bench_pct, misma data)
    p5 = _calc_macro("tamar5")
    vals = [float(v) for _, v in tam[-5:]]
    assert p5["valor"] == pytest.approx(sum(vals) / len(vals))
    assert p5["fecha"] == m["fecha"] and p5["serie"] == "tamar5"
    bench = pricing._bench_pct("TAMAR")
    if math.isfinite(bench):
        assert p5["valor"] == pytest.approx(bench)
    assert _calc_macro("badlar 5")["serie"] == "badlar5" == _calc_macro("BADLAR_aplicable")["serie"]
    # errores POR ITEM (nunca una excepción que voltee el batch)
    for malo in ("", "nada", "cer5", "tamar10"):
        assert "error" in _calc_macro(malo), malo
    assert "a3500 | badlar | tamar" in _calc_macro("nada")["error"]


@pytest.mark.asyncio
async def test_macro_en_el_batch_de_excel(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.routes.excel import _calc_macro
    from backend.services import auth, bond_universe

    _series()
    bond_universe.ensure_loaded()
    esperado = _calc_macro("tamar")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_macro", "clave123", "basico")
        tok = auth.set_excel_access("mesa_macro", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post("/excel/v1/calc", headers={"X-OMS-Token": tok}, json={"items": [
                {"tipo": "macro", "serie": "tamar"},                 # =OMS.MACRO("tamar")
                {"tipo": "macro", "code": "A3500"},                  # el add-in manda la serie también como code (key del memo)
                {"tipo": "macro", "serie": "tamar5"},                # =OMS.MACRO("tamar5")
                {"tipo": "macro", "serie": "nada"},
                {"code": "GD30", "modo": "precio", "valor": 78.5},   # convive con la calculadora YAS en el mismo batch
            ]})
        assert r.status_code == 200
        res = r.json()["results"]
        assert res[0] == esperado
        assert res[1]["serie"] == "a3500" and date.fromisoformat(res[1]["fecha"]) and res[1]["valor"] > 0
        assert res[2]["serie"] == "tamar5" and "error" in res[3] and res[4]["tirea"] > 0
    finally:
        auth.refresh()


def test_snapshot_lleva_la_seccion_macro_para_la_celda_en_vivo(monkeypatch) -> None:
    """La sección `macro` del snapshot = `_calc_macro` de las 8 series (los
    mismos números que el batch), con y sin filtro ?codes=; y es failure-silent
    como las demás secciones (un hiccup no deja sin cotizaciones al libro)."""
    from backend.routes import excel as excel_route
    from backend.routes.excel import _MACRO_SNAPSHOT_SERIES, _calc_macro

    series = _series()
    for codes in (None, frozenset({"GD30"})):
        snap = excel_route._build(codes)
        m = snap["macro"]
        assert set(m) == set(_MACRO_SNAPSHOT_SERIES) == {
            "a3500", "badlar", "tamar", "cer", "uva", "inflamom", "tamar5", "badlar5"}
        assert m["tamar"] == _calc_macro("tamar") and m["a3500"] == _calc_macro("a3500")
        tam = series["tamar"]["points"]
        assert m["tamar"]["valor"] == float(tam[-1][1]) and m["tamar"]["fecha"] == str(tam[-1][0])[:10]
        vals = [float(v) for _, v in tam[-5:]]
        assert m["tamar5"]["valor"] == pytest.approx(sum(vals) / len(vals)) and m["tamar5"]["serie"] == "tamar5"
        for k, v in m.items():                       # valor+fecha o un error legible por serie, nunca una excepción
            assert ("error" in v) or (v["valor"] is not None and date.fromisoformat(v["fecha"])), k
        json.dumps(snap, default=str)
    # una sección rota no voltea el snapshot
    monkeypatch.setattr(excel_route, "_macro_section", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = excel_route._build(None)
    assert snap["macro"] == {} and "quotes" in snap and isinstance(snap.get("a3500"), dict)


@pytest.mark.asyncio
async def test_endpoint_snapshot_incluye_macro(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.routes import excel as excel_route
    from backend.routes.excel import _calc_macro
    from backend.services import auth

    _series()
    esperado = _calc_macro("tamar")
    excel_route._cache.clear()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_macro_snap", "clave123", "basico")
        tok = auth.set_excel_access("mesa_macro_snap", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})
        assert r.status_code == 200
        m = r.json()["macro"]
        assert m["tamar"] == esperado and m["a3500"]["valor"] > 0 and "tamar5" in m
    finally:
        excel_route._cache.clear()
        auth.refresh()


def test_metadata_js_y_docs_de_macro() -> None:
    fj = json.loads((ROOT / "backend/static/excel/functions.json").read_text(encoding="utf-8"))
    por_id = {f["id"]: f for f in fj["functions"]}
    assert por_id["MACRO"]["result"]["type"] == "any"
    assert [p["name"] for p in por_id["MACRO"]["parameters"]] == ["serie", "fecha"]
    assert por_id["MACRO"]["parameters"][1]["optional"] is True
    # streaming como FX: Office lo necesita en la metadata para aceptar setResult repetidos
    assert por_id["MACRO"]["options"] == {"stream": True, "cancelable": True}
    js = (ROOT / "backend/static/excel/functions.js").read_text(encoding="utf-8")
    assert 'CustomFunctions.associate("MACRO", makeStreaming("MACRO", macroGet))' in js
    assert "guard(macroFn)" not in js and "function macroFn" not in js      # la async clásica se fue
    assert "function macroGet(s, serie, fecha)" in js and "s.macro" in js   # lee la sección del snapshot
    assert int(js.split('OMS_BUILD = "v')[1].split(" ")[0]) >= 25     # el sello subió con el cambio
    assert "function isoToSerial" in js and "Date.UTC(1899, 11, 30)" in js
    assert "function wantsDate" in js and '"verdadero"' in js
    # el modo cruda también la escribe (VLOOKUP en Excel perpetuo)
    tp_js = (ROOT / "backend/static/excel/taskpane.js").read_text(encoding="utf-8")
    assert '"MACRO|" + mks[i].toUpperCase()' in tp_js
    for doc in ("FORMULAS.md", "README.md", "taskpane.html"):
        t = (ROOT / "backend/static/excel" / doc).read_text(encoding="utf-8")
        assert "OMS.MACRO" in t, doc
    assert "MACRO\\|TAMAR" in (ROOT / "backend/static/excel/FORMULAS.md").read_text(encoding="utf-8")


def test_serial_de_excel_de_la_fecha_del_dato() -> None:
    """La fórmula del add-in (días desde el 30/12/1899) coincide con Excel:
    09/09/2026 → 46274."""
    assert (date(2026, 9, 9) - date(1899, 12, 30)).days == 46274
