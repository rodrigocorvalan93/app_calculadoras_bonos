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


def test_extract_symbols_top_por_volumen() -> None:
    filas = [
        {"symbol": "PEPE", "volume": 10},
        {"symbol": "TSLA", "volume": 500},
        {"symbol": "KO", "volumeAmount": "500"},      # string y otro campo: vale igual
        {"symbol": "ZZZZ"},                           # sin volumen → 0
        {"symbol": "MSFT", "montoOperado": 1000},
    ]
    # top=3 → MSFT (1000) + TSLA/KO (500 c/u; empate = orden BYMA); salida ordenada
    assert bp._extract_symbols(filas, top=3) == ["KO", "MSFT", "TSLA"]
    # sin top (default) o con top holgado no se recorta nada
    assert len(bp._extract_symbols(filas)) == 5
    assert len(bp._extract_symbols(filas, top=99)) == 5


def test_fetch_panel_capea_solo_cedears() -> None:
    filas = [{"symbol": f"C{i:04d}", "volume": i} for i in range(1, 1301)]

    class _Resp:
        def raise_for_status(self) -> None:  # noqa: D102
            pass

        def json(self):  # noqa: D102
            return {"data": filas}

    class _Sess:
        def post(self, *a, **k):  # noqa: D102
            return _Resp()

    vivos = bp._fetch_panel(_Sess(), bp._EPS["cedears"])
    assert len(vivos) == bp.CEDEARS_VIVOS_MAX
    assert "C1300" in vivos and "C0001" not in vivos    # quedan los de mayor volumen
    # el mismo shape en un panel de acciones NO se capea
    assert len(bp._fetch_panel(_Sess(), bp._EPS["general"])) == 1300


def test_cedears_vivos_union_curados() -> None:
    # el cap por volumen puede dejar afuera un curado líquido (p. ej. finde sin
    # volumen): la vista cedears suma SIEMPRE los curados, sin duplicar
    with bp._lock:
        bp._cache["cedears"] = ["NUEV1", "NUEV2", "SPY"]
    got = equities.panel_tickers("cedears")
    assert "NUEV1" in got and "SPY" in got and "EWZ" in got
    assert len(got) == len(set(got))
    # Líder/General siguen REEMPLAZANDO (la rotación de BYMA debe mover la acción)
    with bp._lock:
        bp._cache["general"] = ["MOLI"]
    assert equities.panel_tickers("general") == ["MOLI"]
