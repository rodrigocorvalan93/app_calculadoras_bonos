"""OMS.FX("a3500") = A3500 OFICIAL del BCRA (con fecha), no el cierre del feed.

Antes "a3500" mapeaba a `mayorista.close` (cierre anterior de SIOPEL / DLR
SPOT), que no cambia cuando el BCRA publica el A3500 del día (~15:30): la
celda quedaba en el dato de ayer toda la rueda. Ahora el snapshot lleva la
sección `a3500` (serie oficial en memoria, releída por el warmup al
publicarse) y el add-in expone valor, fecha (serial de Excel), anterior y
variación; "cierre" conserva el cierre del feed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings

ROOT = Path(__file__).resolve().parents[1]


def _pts():
    from backend.services import historico

    pts = historico.series_points("a3500").get("points") or []
    if len(pts) < 2:
        pytest.skip("sin serie A3500 en este entorno")
    return pts


def test_snapshot_lleva_el_a3500_oficial_con_fecha() -> None:
    from backend.routes import excel as excel_route

    pts = _pts()
    for codes in (None, frozenset({"GD30"})):          # con y sin filtro ?codes=
        snap = excel_route._build(codes)
        a = snap["a3500"]
        assert a["source"] == "A3500" and a["last"] == pts[-1][1] and a["date"] == str(pts[-1][0])[:10]
        assert a["close"] == pts[-2][1] and "var_pct" in a
        assert isinstance(snap.get("mayorista"), dict)   # la sección del feed sigue
        json.dumps(snap, default=str)                     # serializable


@pytest.mark.asyncio
async def test_endpoint_snapshot_incluye_a3500(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.routes import excel as excel_route
    from backend.services import auth

    pts = _pts()
    excel_route._cache.clear()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_a3500", "clave123", "basico")
        tok = auth.set_excel_access("mesa_a3500", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/excel/v1/snapshot", headers={"X-OMS-Token": tok})
        assert r.status_code == 200
        a = r.json()["a3500"]
        assert a["last"] == pts[-1][1] and a["date"] == str(pts[-1][0])[:10]
    finally:
        excel_route._cache.clear()
        auth.refresh()


def test_addin_mapea_a3500_oficial_y_docs() -> None:
    js = (ROOT / "backend/static/excel/functions.js").read_text(encoding="utf-8")
    assert 'if (t === "a3500") { return a35.last != null ? a35.last' in js
    assert '"a3500_fecha"' in js and "isoToSerial(a35.date)" in js
    assert '"a3500_ant"' in js and '"a3500_var"' in js
    assert 'if (t === "cierre") { return may.close' in js         # el cierre del feed sigue disponible
    assert '["A3500 fecha"' in js
    assert int(js.split('OMS_BUILD = "v')[1].split(" ")[0]) >= 22     # el sello subió con la función
    fj = json.loads((ROOT / "backend/static/excel/functions.json").read_text(encoding="utf-8"))
    fx = next(f for f in fj["functions"] if f["id"] == "FX")
    assert "a3500_fecha" in fx["parameters"][0]["description"] and "OFICIAL" in fx["description"]
    doc = (ROOT / "backend/static/excel/FORMULAS.md").read_text(encoding="utf-8")
    assert "a3500_fecha" in doc and "a3500_ant" in doc
    # el refresh por rollover de fecha también relee el backup (riel / HIST / MACRO / add-in)
    wu = (ROOT / "backend/services/warmup.py").read_text(encoding="utf-8")
    assert wu.count("historico.refresh)") >= 2
