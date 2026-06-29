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
    # by_code sintético: precio +1%, TIR −0,5pp, TEM −0,1pp, duration 0,3 (→ CER corto)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0],
                                    "TIREA": [0.50, 0.495], "TEM": [0.030, 0.029],
                                    "Duration": [0.3, 0.3]}}},
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
    # CER no es tasa variable → sin margen TNA
    assert row["margen"] is None and row["dmargen"] is None
    assert seg["has_margen"] is False


def test_margen_tna_formula():
    """Margen = TNA30(TIR) − bench/100; None si falta benchmark o TIR.
    TNA_30 = ((1+TIREA)^(30/365) − 1) × (365/30)."""
    entry = {"dates": ["2026-06-25"], "vals": {"TIREA": [0.50]}}
    tna30 = ((1.0 + 0.50) ** (30.0 / 365.0) - 1.0) * (365.0 / 30.0)
    assert abs(hb._margen_tna(entry, 30.0, "2026-06-25") - (tna30 - 0.30)) < 1e-9
    assert hb._margen_tna(entry, None, "2026-06-25") is None
    assert hb._margen_tna({"dates": ["2026-06-25"], "vals": {}}, 30.0, "2026-06-25") is None


def test_weekly_segments_margen_solo_variable(monkeypatch):
    """El margen TNA SÍ aparece en un bono de tasa variable (TAMAR). Se fija el
    benchmark TAMAR a 30 % para no depender de la serie BCRA del entorno."""
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TNA": [0.45, 0.46], "TEM": [0.030, 0.029],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    seg = next((s for s in res["segments"] if code in s["members"]), None)
    assert seg is not None and seg["has_margen"] is True
    row = next((r for r in seg["rows"] if r["code"] == code), None)
    assert row is not None and row["margen"] is not None and row["dmargen"] is not None


def test_weekly_segments_duales_separados(monkeypatch):
    """Los duales aparecen como segmentos separados: la pata TAMAR ('…v', que en el
    Excel cae bajo el ticker base) trae margen; la base fija/CER no."""
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes()
    fija, tamar_fija = codes.get("dualfija", []), codes.get("dualtamar_fija", [])
    if not fija or not tamar_fija:
        pytest.skip("sin duales fija/tamar en el universo")
    base = sorted(fija)[0]            # p.ej. TTD26 (ficha FIJA = ticker traded del Excel)
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {base: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TEM": [0.030, 0.029], "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    segs = {s["key"]: s for s in res["segments"]}
    # base Fija/TAMAR: aparece, SIN margen (no es floater)
    assert "dual_fija" in segs and segs["dual_fija"]["has_margen"] is False
    # pata TAMAR/Fija: aparece (vía fallback '…v' → ticker base) y CON margen
    assert "dual_tamar_fija" in segs and segs["dual_tamar_fija"]["has_margen"] is True
    assert segs["dual_tamar_fija"]["rows"][0]["margen"] is not None


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
async def test_historicos_semanal_detalle_render(monkeypatch):
    """Con cache inyectada (bono TAMAR = floater) y benchmark fijo, el partial
    renderiza el detalle por bono CON la columna Margen (Δ TEM, sub-tabla, código)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TNA": [0.45, 0.46], "TEM": [0.030, 0.029],
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
