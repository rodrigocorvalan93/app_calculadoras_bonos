"""Comparador · gráfico de barras de cashflows A vs B (services.comparador_cf +
partials/comparador_cashflow.html): geometría pura con filas sintéticas
(escala, eje de tiempo, VN por lado, conversión de moneda de B), y el HTTP
de /comparador/result con el SVG (y sin él cuando un bono falla)."""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import comparador_cf as cfc


def _rows(fechas, total, interes=1.0, amort=0.0):
    return [{"fecha_cpn": d, "fecha_pmt": d, "intereses": interes, "amortizacion": amort, "total": total}
            for d in fechas]


def test_geometria_pura_dos_bonos() -> None:
    settle = date(2026, 11, 4)
    a = _rows([date(2027, 1, 9), date(2027, 7, 9), date(2028, 1, 9)], 0.08)      # 8 % VN por pago
    b = _rows([date(2027, 3, 1), date(2028, 3, 1)], 0.5, amort=50.0)              # 50 % VN
    ch = cfc.chart_from_rows(a, b, vn_a=1_000_000, vn_b=400_000, settle=settle)
    assert ch is not None and ch["n_a"] == 3 and ch["n_b"] == 2
    assert ch["tot_a"] == pytest.approx(3 * 0.08 * 1_000_000) and ch["tot_b"] == pytest.approx(2 * 0.5 * 400_000)
    assert ch["desde"] == settle and ch["hasta"] == date(2028, 3, 1)
    # escala: la barra más alta (B: 200.000) es la que más sube; el tope lindo la cubre
    ymax = max(x["monto"] for x in ch["bars_a"] + ch["bars_b"])
    assert ymax == pytest.approx(200_000)
    assert ch["yticks"][0]["v"] == 0 and ch["yticks"][-1]["v"] >= ymax
    assert all(ch["y0"] <= bb["y"] <= ch["y1"] for bb in ch["bars_a"] + ch["bars_b"])
    # eje de tiempo: A y B en orden cronológico y adentro del plot; A a la izquierda de su fecha, B a la derecha
    xs_a = [bb["x"] for bb in ch["bars_a"]]
    assert xs_a == sorted(xs_a) and all(ch["x0"] <= x <= ch["x1"] for x in xs_a)
    assert ch["bars_a"][0]["x"] < ch["bars_b"][0]["x"]                             # 09/01/2027 < 01/03/2027
    # tramo < 2 años → ticks semestrales MM/AA; más largo → por año
    assert [t["label"] for t in ch["xticks"]] == ["01/27", "07/27", "01/28"]
    largo = cfc.chart_from_rows(a, _rows([date(2029, 6, 1)], 0.5), 1.0, 1.0, settle)
    assert [t["label"] for t in largo["xticks"]] == ["2027", "2028", "2029"]
    # la altura es proporcional al monto
    ba, bb = ch["bars_a"][0], ch["bars_b"][0]
    assert bb["h"] / ba["h"] == pytest.approx(200_000 / 80_000, rel=1e-6)


def test_conversion_de_moneda_y_bordes() -> None:
    settle = date(2026, 11, 4)
    a = _rows([date(2027, 6, 1)], 1.0)
    b = _rows([date(2027, 6, 1)], 1.0)
    sin = cfc.chart_from_rows(a, b, 100.0, 100.0, settle)
    con = cfc.chart_from_rows(a, b, 100.0, 100.0, settle, conv_b=1500.0)
    assert sin["tot_b"] == pytest.approx(100.0) and con["tot_b"] == pytest.approx(150_000.0)
    assert con["tot_a"] == pytest.approx(100.0)                                   # A no se toca
    # tramo corto → ticks semestrales MM/AA
    assert [t["label"] for t in sin["xticks"]] == ["01/27"]
    # sin flujos → None; filas con total NaN se saltan; settle como datetime también vale
    assert cfc.chart_from_rows([], [], 1.0, 1.0, settle) is None
    nan = _rows([date(2027, 1, 1)], float("nan"))
    assert cfc.chart_from_rows(nan, [], 1.0, 1.0, settle) is None
    from datetime import datetime
    ch = cfc.chart_from_rows(a, b, 1.0, 1.0, datetime(2026, 11, 4, 0, 0))
    assert ch["desde"] == settle


def test_nice_step() -> None:
    assert cfc._nice_step(200_000) in (50_000.0, 100_000.0)
    assert cfc._nice_step(0.9) == pytest.approx(0.25)
    assert cfc._nice_step(0) == 1.0


@pytest.mark.asyncio
async def test_http_comparador_dibuja_los_cashflows() -> None:
    """GD30 vs GD35 a precio (misma moneda): el partial trae el SVG con barras
    de A y B, el título con los dos códigos y el pie con el cash neutral. GD30
    vs AL30 (USD vs USB) sin FX vivo en la suite: se dibuja igual, cada uno
    en su moneda y el pie lo dice. Con un bono inexistente no hay gráfico (y
    la página sigue respondiendo)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe

    bond_universe.ensure_loaded()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        ok = await ac.get("/comparador/result", params={
            "a": "GD30", "b": "GD35", "mode": "precio", "val_a": "78,5", "val_b": "66", "vn": "1000000"})
        mixto = await ac.get("/comparador/result", params={
            "a": "GD30", "b": "AL30", "mode": "precio", "val_a": "78,5", "val_b": "76"})
        malo = await ac.get("/comparador/result", params={
            "a": "GD30", "b": "NOEXISTE", "mode": "precio", "val_a": "78,5", "val_b": "76"})
    assert ok.status_code == 200
    assert 'class="cfc-chart"' in ok.text and "cfc-bar-a" in ok.text and "cfc-bar-b" in ok.text
    assert "Cashflows · GD30 vs GD35" in ok.text and "VN cash neutral" in ok.text and "en USD" in ok.text
    assert ok.text.count("cfc-bar-a") >= 3 and ok.text.count("cfc-bar-b") >= 3   # varios pagos cada uno (+ leyenda)
    assert mixto.status_code == 200 and 'class="cfc-chart"' in mixto.text
    assert "monedas distintas (USD vs USB)" in mixto.text or "pasados a USD" in mixto.text
    assert malo.status_code == 200 and "cfc-chart" not in malo.text
