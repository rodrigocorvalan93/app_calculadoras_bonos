"""OMS.MACRO en el add-in de Excel: último dato macro del BCRA en una celda.

Item `tipo: "macro"` en el batch /excel/v1/calc (sin especie ni precio): la
fuente es services.historico — el mismo backup BCRA de OMS.HIST y del riel del
dólar — así la celda muestra lo que muestra la web. El add-in devuelve el
valor o, con VERDADERO, la fecha del dato como serial de Excel. `tamar5` /
`badlar5` = promedio de las últimas 5 ruedas, el benchmark de OMS.MARGEN."""
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


def test_metadata_js_y_docs_de_macro() -> None:
    fj = json.loads((ROOT / "backend/static/excel/functions.json").read_text(encoding="utf-8"))
    por_id = {f["id"]: f for f in fj["functions"]}
    assert por_id["MACRO"]["result"]["type"] == "any"
    assert [p["name"] for p in por_id["MACRO"]["parameters"]] == ["serie", "fecha"]
    assert por_id["MACRO"]["parameters"][1]["optional"] is True
    js = (ROOT / "backend/static/excel/functions.js").read_text(encoding="utf-8")
    assert 'CustomFunctions.associate("MACRO", guard(macroFn))' in js and "v23" in js
    assert 'it.tipo !== "macro"' in js                      # no es "a precio de mercado": se memoiza (TTL 5 min)
    assert "function isoToSerial" in js and "Date.UTC(1899, 11, 30)" in js
    assert "function wantsDate" in js and '"verdadero"' in js
    for doc in ("FORMULAS.md", "README.md", "taskpane.html"):
        t = (ROOT / "backend/static/excel" / doc).read_text(encoding="utf-8")
        assert "OMS.MACRO" in t, doc


def test_serial_de_excel_de_la_fecha_del_dato() -> None:
    """La fórmula del add-in (días desde el 30/12/1899) coincide con Excel:
    09/09/2026 → 46274."""
    assert (date(2026, 9, 9) - date(1899, 12, 30)).days == 46274
