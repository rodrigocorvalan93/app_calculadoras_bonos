"""Books de caución BYMA (pestaña Tasas) y de futuros (paridad Mercado), y el
VWAP de caución: acumulador de trades en el store + guardado diario junto al
histórico FX (plazo o/n real del día → viernes 3D / pre-feriado 4D, sin
huecos en la serie)."""
from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import cauciones as cauc_svc
from backend.services import marketdata_store as mds


@pytest.fixture()
def store_limpio(monkeypatch):
    """Store propio por test: los símbolos de caución son fijos (PESOS - 1D)
    y el singleton compartido contaminaría los picks por volumen."""
    st = mds.MarketDataStore()
    monkeypatch.setattr(mds, "_store", st)
    return st


def test_vwap_caucion_acumula_dedup_y_guard(store_limpio) -> None:
    """El feed no publica VWAP de tasa: lo acumula el store con los trades
    (Σ tasa×monto / Σ monto), dedup del LA sticky, y el guard de sesión
    parcial devuelve None antes que un promedio mentiroso."""
    sym = "MERV - XMEV - PESOS - 7D"
    st = store_limpio
    st.update_from_md(sym, {"LA": {"price": 30.0, "size": 1_000_000.0, "date": "1"}})
    st.update_from_md(sym, {"LA": {"price": 32.0, "size": 3_000_000.0, "date": "2"}})
    acc = st.get(sym).vwap_acc
    assert acc["den"] == 4_000_000.0
    assert acc["num"] == pytest.approx(30.0 * 1e6 + 32.0 * 3e6)
    # el mismo LA reenviado (snapshot inicial sticky) NO se double-cuenta
    st.update_from_md(sym, {"LA": {"price": 32.0, "size": 3_000_000.0, "date": "2"}})
    assert st.get(sym).vwap_acc["den"] == 4_000_000.0
    # EV cubierto por lo acumulado → VWAP ponderado real
    st.update_from_md(sym, {"EV": 4_000_000.0})
    assert cauc_svc.vwap_sesion(st.get(sym)) == pytest.approx(31.5)
    # EV mucho mayor que lo visto (app arrancada a mitad de rueda) → None
    st.update_from_md(sym, {"EV": 40_000_000.0})
    assert cauc_svc.vwap_sesion(st.get(sym)) is None
    # un bono cualquiera no acumula (el costo queda scoped a caución)
    st.update_from_md("MERV - XMEV - AL30D - 24hs", {"LA": {"price": 58.0, "size": 100.0}})
    assert st.get("MERV - XMEV - AL30D - 24hs").vwap_acc is None


def test_caucion_book_completo_y_stale(store_limpio) -> None:
    st = store_limpio
    st.update_from_md("MERV - XMEV - PESOS - 1D", {
        "LA": {"price": 31.0, "size": 2e6, "date": "10"},
        "CL": 30.0, "OP": 32.0, "HI": 33.0, "LO": 29.5,
        "EV": 2e6, "TV": 12.0,
        "BI": [{"price": 30.9, "size": 5e6}, {"price": 30.5, "size": 3e6}],
        "OF": [{"price": 31.2, "size": 4e6}],
    })
    b = cauc_svc.book("PESOS", 1)
    assert b["tasa"] == 31.0 and b["close"] == 30.0
    assert b["var"] == pytest.approx(1.0)               # puntos de TNA
    assert b["monto"] == 2e6 and b["ops"] == 12.0 and b["es_hoy"] is True
    assert [lv["cum"] for lv in b["bids"]] == [5e6, 8e6]
    assert b["bids"][1]["frac"] == pytest.approx(1.0)   # degradé de profundidad
    assert b["vwap"] == pytest.approx(31.0)
    assert b["vencimiento"]                             # hoy + 1 corrido

    # Snapshot restaurado de OTRA rueda (persistencia): ni puntas ni stats del
    # día — la última tasa conocida queda como cierre de referencia.
    st.restore({"MERV - XMEV - DOLAR - 1D": {
        "symbol": "MERV - XMEV - DOLAR - 1D",
        "last": 5.0, "close": 4.8, "bids": [{"price": 4.9, "size": 1e6}],
        "volume": 1e6, "updated_at": time.time() - 3 * 86400}})
    b2 = cauc_svc.book("DOLAR", 1)
    assert b2["es_hoy"] is False and b2["tasa"] is None
    assert b2["bids"] == [] and b2["monto"] is None
    assert b2["close"] == 4.8

    assert cauc_svc.book("PESOS", 120) is None          # plazo sin datos


def test_hist_row_plazo_por_volumen(store_limpio) -> None:
    """Viernes ficticio: la 1D casi no opera y el volumen se concentra en la
    3D → la serie histórica guarda la 3D sin que nadie configure nada."""
    st = store_limpio
    st.update_from_md("MERV - XMEV - PESOS - 1D",
                      {"LA": {"price": 29.0, "size": 1e5, "date": "1"}, "EV": 1e5})
    st.update_from_md("MERV - XMEV - PESOS - 3D",
                      {"LA": {"price": 30.5, "size": 9e6, "date": "2"}, "EV": 9e6})
    r = cauc_svc.hist_row("PESOS")
    assert r["plazo_d"] == 3 and r["tna"] == 30.5
    assert r["vwap"] == pytest.approx(30.5) and r["monto"] == 9e6


def test_hist_row_none_con_datos_de_otra_rueda(store_limpio) -> None:
    """El cierre sticky de la rueda anterior JAMÁS entra al histórico como
    tasa de hoy (duplicaría el dato del día previo)."""
    store_limpio.restore({"MERV - XMEV - PESOS - 1D": {
        "symbol": "MERV - XMEV - PESOS - 1D",
        "last": 30.0, "close": 29.0, "volume": 5e6,
        "updated_at": time.time() - 3 * 86400}})
    assert cauc_svc.hist_row("PESOS") is None


def test_build_fx_row_incluye_caucion(monkeypatch, store_limpio) -> None:
    from types import SimpleNamespace

    from backend.services import dolares
    from backend.services import fx as fx_svc
    from backend.services import historico_writer as hw

    snap = SimpleNamespace(ccl=1480.0, usb=1465.0, canje=1480.0 / 1465.0 - 1.0,
                           ccl_base="GD30")
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": snap)
    monkeypatch.setattr(dolares, "official_fx", lambda: {"last": 1350.0})
    store_limpio.update_from_md("MERV - XMEV - PESOS - 2D",
                                {"LA": {"price": 31.0, "size": 4e6, "date": "9"}, "EV": 4e6})
    row = hw.build_fx_row()
    assert row["caucion_plazo_d"] == 2 and row["caucion_tna"] == 31.0
    assert row["caucion_tna_vwap"] == pytest.approx(31.0)
    assert row["caucion_monto"] == 4e6

    # sin caución el FX se guarda igual: las claves van en None (columnas estables)
    monkeypatch.setattr(mds, "_store", mds.MarketDataStore())
    row2 = hw.build_fx_row()
    assert row2 is not None and row2["caucion_tna"] is None and row2["ccl"] == 1480.0


@pytest.mark.asyncio
async def test_http_tasas_caucion_book_y_wiring(store_limpio) -> None:
    from backend.main import app

    store_limpio.update_from_md("MERV - XMEV - PESOS - 1D", {
        "LA": {"price": 31.0, "size": 2e6, "date": "10"}, "CL": 30.0, "EV": 2e6,
        "BI": [{"price": 30.9, "size": 5e6}], "OF": [{"price": 31.2, "size": 4e6}],
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/tasas/caucion/book", params={"moneda": "PESOS", "dias": 1})
        assert r.status_code == 200
        assert "Libro · Caución ARS 1D" in r.text
        assert "VWAP sesión" in r.text and "md-update" in r.text
        assert "depth-bid" in r.text and "31,00" in r.text
        # la página tiene el target del libro FUERA del área auto-refrescada…
        page = await ac.get("/tasas")
        assert 'id="cauc-book"' in page.text
        # …y las filas BYMA son clickeables hacia el endpoint (con col. VWAP)
        tbl = await ac.get("/tasas/table")
        assert "/tasas/caucion/book?moneda=PESOS" in tbl.text
        assert "<th>VWAP</th>" in tbl.text


@pytest.mark.asyncio
async def test_http_futuros_book_paridad_mercado(store_limpio) -> None:
    """El libro de futuros muestra el cuadro completo estilo Mercado: stats
    del día + profundidad con acumulado y TNA implícita por nivel, vivo."""
    from backend.main import app

    code = "DLR/JUN27M"          # ~10 meses: robusto al drift del reloj del CI
    store_limpio.update_from_md(code, {
        "LA": {"price": 1650.0, "size": 10.0}, "CL": 1640.0,
        "OP": 1642.0, "HI": 1655.0, "LO": 1638.0,
        "EV": 120000.0, "TV": 34.0, "OI": {"size": 5.2e6},
        "BI": [{"price": 1649.0, "size": 20.0}, {"price": 1648.0, "size": 15.0}],
        "OF": [{"price": 1651.0, "size": 12.0}],
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/futuros/book", params={"code": code, "spot_override": "1400"})
    assert r.status_code == 200
    assert "TNA impl @ last" in r.text                 # donde en bonos va la TIR
    assert "Var vs ajuste" in r.text and "0,61" in r.text   # 1650/1640−1
    assert "depth-bid" in r.text and "depth-ask" in r.text  # DOM con degradé
    assert "md-update" in r.text                       # card vivo (auto-refresh)
    assert "spot_override=1400" in r.text              # el refresh conserva el override
