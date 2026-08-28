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


def test_extract_symbols_orden_volumen() -> None:
    filas = [
        {"symbol": "PEPE", "volume": 10},
        {"symbol": "TSLA", "volume": 500},
        {"symbol": "KO", "volumeAmount": "500"},      # string y otro campo: vale igual
        {"symbol": "ZZZZ"},                           # sin volumen → 0, al final
        {"symbol": "MSFT", "montoOperado": 1000},
    ]
    # orden_volumen: desc por volumen, empates (TSLA/KO) en el orden de BYMA
    assert bp._extract_symbols(filas, orden_volumen=True) == \
        ["MSFT", "TSLA", "KO", "PEPE", "ZZZZ"]
    # default: alfabético (paneles de acciones), completo
    assert bp._extract_symbols(filas) == ["KO", "MSFT", "PEPE", "TSLA", "ZZZZ"]


def test_fetch_panel_cedears_completo_en_orden_volumen() -> None:
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
    assert len(vivos) == 1300 and vivos[0] == "C1300"   # completo, mayor volumen 1º
    # panel de acciones: completo alfabético
    gen = bp._fetch_panel(_Sess(), bp._EPS["general"])
    assert len(gen) == 1300 and gen[0] == "C0001"


def test_cedears_cap_en_equities_y_union_curados() -> None:
    # lista viva grande (orden de volumen desc): el panel default corta en
    # CEDEARS_VIVOS_MAX y suma SIEMPRE los curados, sin duplicar
    vivos = [f"C{i:04d}" for i in range(1300, 0, -1)]
    with bp._lock:
        bp._cache["cedears"] = list(vivos)
    got = equities.panel_tickers("cedears")
    assert "C1300" in got and "C1001" in got and "C1000" not in got   # top 300
    assert "SPY" in got and "EWZ" in got and len(got) == len(set(got))
    # lista viva chica: entra entera + curados (un finde sin volumen no borra nada)
    with bp._lock:
        bp._cache["cedears"] = ["NUEV1", "SPY"]
    got2 = equities.panel_tickers("cedears")
    assert "NUEV1" in got2 and "SPY" in got2 and "EWZ" in got2
    # Líder/General siguen REEMPLAZANDO (la rotación de BYMA debe mover la acción)
    with bp._lock:
        bp._cache["general"] = ["MOLI"]
    assert equities.panel_tickers("general") == ["MOLI"]


def test_cedears_universo_y_view() -> None:
    vivos = [f"C{i:04d}" for i in range(1300, 0, -1)]     # C1300 = más operado
    with bp._lock:
        bp._cache["cedears"] = list(vivos)
    univ = equities.cedears_universo()
    assert univ[:2] == ["C1300", "C1299"] and "SPY" in univ
    assert len(univ) == 1300 + len(equities.CEDEARS)      # sin solapamiento acá
    # búsqueda global: matchea fuera del top-300 y lo reporta como "nuevo"
    codes, nuevos = equities.cedears_view(q="c0250")
    assert codes == ["C0250"] and nuevos == ["C0250"]
    # un curado del panel base NO es nuevo
    codes2, nuevos2 = equities.cedears_view(q="SPY")
    assert "SPY" in codes2 and "SPY" not in nuevos2
    # "ver 150 más": la siguiente tanda POR VOLUMEN después del panel base
    base = equities.panel_tickers("cedears")
    codes3, nuevos3 = equities.cedears_view(mas=150)
    assert len(codes3) == len(base) + 150 and len(nuevos3) == 150
    assert nuevos3[0] == "C1000"                          # el que sigue al top 300
    # sin q ni mas → el panel base tal cual, nada para suscribir
    codes4, nuevos4 = equities.cedears_view()
    assert codes4 == base and nuevos4 == []


@pytest.mark.asyncio
async def test_http_cedears_buscador_y_mas(monkeypatch) -> None:
    """El buscador y el +150 suscriben on-demand y muestran filas stub que se
    llenan cuando el feed contesta (acá: guiones, sin datos sembrados)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import primary_ws

    class _WS:
        def __init__(self):
            self.subs: list = []

        async def subscribe(self, symbols):
            self.subs.extend(symbols)
    ws = _WS()
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: ws)
    with bp._lock:
        bp._cache["cedears"] = [f"C{i:04d}" for i in range(1300, 0, -1)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table?panel=cedears&plazo=24hs&q=C0123")
        assert r.status_code == 200 and "C0123" in r.text          # fila stub
        assert any("C0123" in s for s in ws.subs)                  # suscripto al vuelo
        assert any("CI" in s for s in ws.subs)                     # ambos plazos
        r2 = await ac.get("/mercado/table?panel=cedears&plazo=24hs&mas=150")
        assert r2.status_code == 200 and "C1000" in r2.text        # 1º de la tanda extra
        assert "de 14" in r2.text                                  # "N de 14xx conocidos"
        # sin q/mas: el panel default no suscribe nada nuevo
        n_subs = len(ws.subs)
        r3 = await ac.get("/mercado/table?panel=cedears&plazo=24hs")
        assert r3.status_code == 200 and len(ws.subs) == n_subs
