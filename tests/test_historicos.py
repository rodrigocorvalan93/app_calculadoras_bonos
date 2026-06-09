"""Históricos — rango personalizado (macro) + histórico de tasas por curva (BYMA).

El Excel histórico no está en CI: se inyecta una estructura sintética en el
cache de `historico_byma` para ejercitar la vista de curvas y el SVG, y se
verifica la degradación cuando no hay Excel.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services import bond_universe, curves, historico_byma, symbols as syms


def _inject_synthetic():
    """Inyecta historia sintética para la primera curva con ≥3 códigos."""
    bond_universe.ensure_loaded()
    ck = next((k for k, v in curves.build_curve_codes().items() if len(v) >= 3), None)
    assert ck, "sin curvas para el test"
    codes = curves.build_curve_codes()[ck][:4]
    days = [(date(2025, 9, 1) + timedelta(days=7 * i)).isoformat() for i in range(20)]
    by_code = {}
    for j, c in enumerate(codes):
        ser = [0.40 + 0.02 * j + 0.01 * ((i % 5) - 2) for i in range(20)]
        by_code[c] = {"base": syms.calc_to_md_code(c), "proy": 0, "dates": days,
                      "vals": {"TIREA": ser, "TNA": ser, "TEM": [s / 12 for s in ser],
                               "Paridad": [0.85] * 20}}
    historico_byma._cache = {
        "loaded": True, "error": None, "path": "synthetic", "by_code": by_code,
        "bounds": (days[0], days[-1]), "n_codes": len(by_code), "n_dates": len(days),
        "n_obs": len(days) * len(codes), "last_update": days[-1]}
    return ck, codes, days


def _clear():
    historico_byma._cache = None


@pytest.mark.asyncio
async def test_macro_custom_range() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import historico

    series = historico.series_list()
    key = series[0]["key"] if series else "a3500"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        page = await ac.get("/historicos")
        data = await ac.get(f"/historicos/data?serie={key}&desde=2025-01-01&hasta=2025-06-01")
    assert page.status_code == 200 and 'id="hist-macro-uplot"' in page.text
    assert data.status_code == 200
    j = data.json()
    assert "x" in j and "y" in j and len(j["x"]) == len(j["y"])


@pytest.mark.asyncio
async def test_curva_history_view() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    ck, codes, days = _inject_synthetic()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # partial: controles + contenedor uPlot (el chart se dibuja client-side)
            r = await ac.get(f"/historicos/curva?curve={ck}&metric=TIREA")
            # data: JSON multilínea para uPlot
            jd = await ac.get(f"/historicos/curva/data?curve={ck}&metric=TIREA")
            jp = await ac.get(f"/historicos/curva/data?curve={ck}&metric=Paridad&desde={days[5]}&hasta={days[15]}")
        assert r.status_code == 200
        assert 'id="hist-curva-uplot"' in r.text and 'id="hc-ctrls"' in r.text
        j = jd.json()
        assert j["loaded"] and len(j["series"]) == len(codes)        # una serie por bono
        assert len(j["x"]) and j["bands"] and j["bands"]["mean"] is not None
        assert all(len(s["y"]) == len(j["x"]) for s in j["series"])  # alineadas a la unión de fechas
        assert jp.status_code == 200 and jp.json()["loaded"]
        cs = historico_byma.curve_series(ck, "TIREA")
        assert cs["loaded"] and len(cs["lines"]) == len(codes)
    finally:
        _clear()


@pytest.mark.asyncio
async def test_curva_degrades_without_excel() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    historico_byma._cache = {"loaded": False, "error": "no Excel", "by_code": {},
                             "bounds": (None, None), "n_codes": 0, "n_dates": 0,
                             "n_obs": 0, "last_update": None}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/historicos/curva?curve=cer")
            page = await ac.get("/historicos")
        assert r.status_code == 200 and "no disponible" in r.text.lower()
        assert page.status_code == 200          # la página (macro) no se entera
    finally:
        _clear()
