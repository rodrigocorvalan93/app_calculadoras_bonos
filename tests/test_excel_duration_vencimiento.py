"""OMS.DURATION y OMS.VENCIMIENTO en el add-in de Excel.

DURATION = el campo `duration` del mismo batch /excel/v1/calc que usan TIREA /
TNA (modified duration del YAS). VENCIMIENTO = ficha estática vía un item
`tipo: "meta"` (sin precio ni mercado: un bono que no operó hoy también tiene
vencimiento); el add-in lo muestra DD/MM/AAAA o como fecha de Excel."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_duration_y_vencimiento_en_excel_calc(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.routes.excel import _calc_meta
    from backend.services import auth, bond_universe, pricing

    bond_universe.ensure_loaded()
    settle = pricing.settlement_date_str("24hs")
    esperado = pricing.compute_metrics("GD30", "precio", 78.5, settle=settle, include_cashflows=False)
    assert not esperado.get("error") and esperado["duration"] > 0
    venc = pricing.bond_meta("GD30")["vencimiento"]
    venc_iso = (venc.date() if hasattr(venc, "date") else venc).isoformat()[:10]
    # ficha estática directa: ISO, sin tocar el mercado; desconocida → error por item
    m = _calc_meta("GD30")
    assert m["codigo"] == "GD30" and m["vencimiento"] == venc_iso and "callable" in m
    assert date.fromisoformat(m["vencimiento"]) > date(2026, 1, 1)
    assert "error" in _calc_meta("NOEXISTE") and "error" in _calc_meta("")

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_dur", "clave123", "basico")
        tok = auth.set_excel_access("mesa_dur", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post("/excel/v1/calc", headers={"X-OMS-Token": tok}, json={"items": [
                {"code": "GD30", "modo": "precio", "valor": 78.5},   # OMS.DURATION
                {"code": "gd30", "tipo": "meta"},                     # OMS.VENCIMIENTO (sin precio)
                {"code": "NOEXISTE", "tipo": "meta"},
            ]})
        assert r.status_code == 200
        res = r.json()["results"]
        assert res[0]["duration"] == pytest.approx(esperado["duration"])
        assert res[1]["vencimiento"] == venc_iso and res[1]["codigo"] == "GD30"
        assert "duration" not in res[1] and "error" in res[2]
    finally:
        auth.refresh()

    # el add-in registra las dos funciones, la metadata las publica y la ficha se memoiza
    fj = json.loads((ROOT / "backend/static/excel/functions.json").read_text(encoding="utf-8"))
    por_id = {f["id"]: f for f in fj["functions"]}
    assert por_id["DURATION"]["result"]["type"] == "number"
    assert [p["name"] for p in por_id["DURATION"]["parameters"]] == ["especie", "precio", "plazo", "fx"]
    assert [p["name"] for p in por_id["VENCIMIENTO"]["parameters"]] == ["especie", "formato"]
    js = (ROOT / "backend/static/excel/functions.js").read_text(encoding="utf-8")
    assert 'CustomFunctions.associate("DURATION", guard(durationFn))' in js
    assert 'CustomFunctions.associate("VENCIMIENTO", guard(vencimientoFn))' in js and "v20" in js
    assert 'it.tipo !== "meta"' in js                       # la ficha no es "a precio de mercado": se memoiza
    assert "Date.UTC(1899, 11, 30)" in js                   # serial de Excel (sistema 1900)
    for doc in ("FORMULAS.md", "README.md", "taskpane.html"):
        t = (ROOT / "backend/static/excel" / doc).read_text(encoding="utf-8")
        assert "OMS.DURATION" in t and "OMS.VENCIMIENTO" in t, doc


def test_serial_de_excel_del_vencimiento() -> None:
    """La fórmula del add-in (días desde el 30/12/1899) coincide con Excel:
    09/07/2030 → 47673."""
    assert (date(2030, 7, 9) - date(1899, 12, 30)).days == 47673
