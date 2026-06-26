"""Resumen semanal por segmento en Históricos: Δ Precio % + Δ TIR (pp) por
categoría (mismas que Escenario), sobre la serie histórica por bono."""
from __future__ import annotations

import pytest

from backend.services import bond_universe, curves
from backend.services import historico_byma as hb


def test_weekly_segments_calcula_deltas():
    bond_universe.ensure_loaded()
    cer = curves.build_curve_codes().get("cer", [])
    if not cer:
        pytest.skip("sin curva cer")
    code = cer[0]
    # by_code sintético: precio +1%, TIR −0,5pp, duration 0,3 (→ CER corto)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0],
                                    "TIREA": [0.50, 0.495], "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["loaded"] and res["start"] == "2026-06-18" and res["end"] == "2026-06-25"
    seg = next((s for s in res["segments"] if code in s["members"]), None)
    assert seg is not None and seg["key"] == "cer_corto"
    assert abs(seg["dprice"] - 0.01) < 1e-9        # +1 %
    assert abs(seg["dtir"] - (-0.005)) < 1e-9       # −0,5 pp (compresión)
    assert {"cer", "a3500", "tamar_ini", "tamar_fin", "tamar_delta"} <= set(res["indices"])


def test_weekly_segments_sin_data():
    prev = hb._cache
    hb._cache = {"loaded": False, "error": "x", "bounds": (None, None), "by_code": {}}
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["loaded"] is False and res["segments"] == []


@pytest.mark.asyncio
async def test_historicos_semanal_endpoint_no_crash():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for d in (7, 14, 30):
            r = await ac.get(f"/historicos/semanal?dias={d}")
            assert r.status_code == 200 and "Traceback" not in r.text
        pg = await ac.get("/historicos")
        assert pg.status_code == 200 and 'id="hist-semanal"' in pg.text and "Qué pasó" in pg.text
