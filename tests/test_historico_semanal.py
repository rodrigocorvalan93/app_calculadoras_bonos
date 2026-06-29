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
    # by_code sintético: precio +1%, TIR −0,5pp, TEM −0,1pp, duration 0,3 (→ CER
    # corto). El tem_spread está cargado pero NO debe mostrarse: CER no lleva margen.
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0],
                                    "TIREA": [0.50, 0.495], "TEM": [0.030, 0.029],
                                    "tem_spread": [0.020, 0.018], "Duration": [0.3, 0.3]}}},
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
    # detalle por bono: Δprecio / ΔTIR / ΔTEM
    row = next((r for r in seg["rows"] if r["code"] == code), None)
    assert row is not None
    assert abs(row["dprice"] - 0.01) < 1e-9
    assert abs(row["dtir"] - (-0.005)) < 1e-9
    assert abs(row["dtem"] - (-0.001)) < 1e-9        # 0,029 − 0,030
    # CER NO lleva margen aunque haya tem_spread en el Excel → gateado a None
    assert row["margen"] is None and row["dmargen"] is None
    assert seg["has_margen"] is False


def test_weekly_segments_margen_solo_variable():
    """El margen (tem_spread) SÍ aparece en un bono de tasa variable (TAMAR)."""
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TEM": [0.030, 0.029], "tem_spread": [0.040, 0.038],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    seg = next((s for s in res["segments"] if code in s["members"]), None)
    assert seg is not None and seg["has_margen"] is True
    row = next((r for r in seg["rows"] if r["code"] == code), None)
    assert row is not None
    assert abs(row["margen"] - 0.038) < 1e-9         # tem_spread al cierre (floater)
    assert abs(row["dmargen"] - (-0.002)) < 1e-9     # 0,038 − 0,040


def test_weekly_segments_sin_data():
    prev = hb._cache
    hb._cache = {"loaded": False, "error": "x", "bounds": (None, None), "by_code": {}}
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["loaded"] is False and res["segments"] == []


def test_index_at_robusto_a_indice_mixto():
    """Regresión A3500: el poller de FX inyectaba hoy con índice STRING → índice
    mixto (date + str) que rompía la comparación y dejaba la deva A3500 en None.
    `_index_at` ahora salta etiquetas no parseables y sigue dando el valor."""
    import rentafija
    from datetime import date, timedelta
    a3500 = rentafija.inputs.get("a3500")
    if a3500 is None or "tca3500" not in getattr(a3500, "columns", []):
        pytest.skip("sin serie a3500")
    # contaminar el índice con una etiqueta string (reproduce el bug viejo)
    rentafija.inputs["a3500"].loc["2026-06-26", "tca3500"] = 1480.0
    start = (date(2026, 6, 26) - timedelta(days=7)).isoformat()
    idx = hb._window_indices(start, "2026-06-25")
    assert idx["a3500"] is not None        # antes daba None por el TypeError str<=date
    assert hb._index_at("a3500", "tca3500", start) is not None


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


@pytest.mark.asyncio
async def test_historicos_semanal_detalle_render():
    """Con cache inyectada (bono TAMAR = floater), el partial renderiza el detalle
    por bono CON la columna Margen (Δ TEM, sub-tabla y código del bono)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TEM": [0.030, 0.029], "tem_spread": [0.040, 0.038],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/historicos/semanal?dias=7")
    finally:
        hb._cache = prev
    assert r.status_code == 200 and "Traceback" not in r.text
    assert "Δ TEM" in r.text and "Margen" in r.text       # encabezados del detalle
    assert 'class="sem-detail"' in r.text                  # sub-tabla anidada
    assert code in r.text                                  # fila por bono
