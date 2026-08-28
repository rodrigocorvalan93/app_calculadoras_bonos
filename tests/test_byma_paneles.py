"""Paneles de equities VIVOS (BYMA Open Data) con fallback curado, y la
vista "Acciones · Todas" con badge Líder/General. Sin red: todo mockeado."""
from __future__ import annotations

import pytest

from backend.services import byma_paneles as bp, equities, marketdata_store as mds, symbols as syms


@pytest.fixture(autouse=True)
def _cache_limpio():
    with bp._lock:
        bp._cache.clear()
    yield
    with bp._lock:
        bp._cache.clear()


def _seed(code: str, px: float, close: float) -> None:
    mds.get_store().update_from_md(syms.md_symbol(code, "24hs"), {
        "LA": {"price": px}, "CL": {"price": close},
        "EV": {"size": 1_000_000}, "NV": {"size": 5_000}})


def test_extract_symbols_shapes() -> None:
    # shape {"data": [...]} con settlement en el símbolo → ticker limpio y único
    assert bp._extract_symbols({"data": [
        {"symbol": "GGAL - 0003-C-CT-ARS"}, {"symbol": "GGAL"}, {"symbol": "moli"},
        {"symbol": ""}, {"otra": 1}]}) == ["GGAL", "MOLI"]
    # lista plana también vale; basura → None (fallback)
    assert bp._extract_symbols([{"symbol": "BHIP"}]) == ["BHIP"]
    assert bp._extract_symbols({"error": "x"}) is None
    assert bp._extract_symbols("html de un proxy") is None


def test_refresh_parcial_no_pisa_lo_sabido(monkeypatch) -> None:
    respuestas = {"leading-equity": ["GGAL", "NUEVA"], "general-equity": ["MOLI"],
                  "cedears": None}
    monkeypatch.setattr(bp, "_fetch_panel", lambda s, ep: respuestas.get(ep))
    got = bp.refresh()
    assert got == {"lideres": 2, "general": 1}
    assert bp.tickers("lideres") == ["GGAL", "NUEVA"]
    assert bp.tickers("cedears") is None                    # ese endpoint falló → fallback
    # segunda pasada: sólo cede el que respondió; lo sabido no se borra
    respuestas.update({"leading-equity": None, "cedears": ["SPY"]})
    bp.refresh()
    assert bp.tickers("lideres") == ["GGAL", "NUEVA"]       # se conserva
    assert bp.tickers("cedears") == ["SPY"]


def test_panel_tickers_vivo_con_fallback() -> None:
    # sin dato vivo → lista curada
    assert equities.panel_tickers("general") == equities.GENERAL
    # con dato vivo → manda BYMA
    with bp._lock:
        bp._cache["general"] = ["MOLI", "XXNU"]
    assert equities.panel_tickers("general") == ["MOLI", "XXNU"]
    # y el seed del WS incluye la unión (curados + vivos)
    subs = equities.all_symbols()
    assert any("XXNU" in s for s in subs) and any("BHIP" in s for s in subs)


def test_panel_todas_con_badge() -> None:
    _seed("GGAL", 5400.0, 5300.0)
    _seed("MOLI", 300.0, 290.0)
    rows = equities.panel_rows("todas")
    por_code = {r["code"]: r for r in rows}
    assert por_code["GGAL"]["panel"] == "L"
    assert por_code["MOLI"]["panel"] == "G"
    # si BYMA moviera MOLI al panel líder, el badge sigue a la membresía viva
    with bp._lock:
        bp._cache["lideres"] = ["MOLI"]
        bp._cache["general"] = ["BHIP"]
    rows2 = equities.panel_rows("todas")
    assert {r["code"]: r["panel"] for r in rows2}["MOLI"] == "L"


@pytest.mark.asyncio
async def test_http_panel_todas() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _seed("GGAL", 5400.0, 5300.0)
    _seed("MOLI", 300.0, 290.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table?panel=todas&plazo=24hs")
        assert r.status_code == 200
        assert "Líder + General" in r.text and ">Panel<" in r.text
        assert ">L</span>" in r.text and ">G</span>" in r.text
        mp = await ac.get("/mercado")
        assert 'value="todas"' in mp.text
