"""Futuros de dólar (DLR) — símbolos, parseo de vto, tasa implícita y endpoint."""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import futuros as fut


def test_symbols_and_vto() -> None:
    mn, my = fut.symbols("min"), fut.symbols("may")
    assert mn and mn[0].startswith("DLR/") and not mn[0].endswith("M")
    assert my and my[0].endswith("M")
    v = fut._parse_vto("DLR/FEB26")
    assert v == date(2026, 2, 28)
    assert fut._parse_vto("DLR/FEB26M") == date(2026, 2, 28)
    assert fut._parse_vto("basura") is None


def test_symbols_meses_en_espanol() -> None:
    """ROFEX/A3 abrevia el mes en ESPAÑOL. Regresión: la tira generada en
    inglés hacía que DLR/AUG26M no matcheara ningún símbolo real y agosto
    (también ENE/ABR/DIC) desaparecía de la tabla aunque estuviera operando."""
    joined = " ".join(fut.symbols("may"))          # 14 meses cubren los 12
    for mes in ("ENE", "ABR", "AGO", "DIC"):
        assert mes in joined
    for mes in ("JAN", "APR", "AUG", "DEC"):
        assert mes not in joined
    # ambos idiomas parsean al mismo vencimiento
    assert fut._parse_vto("DLR/AGO26M") == date(2026, 8, 31)
    assert fut._parse_vto("DLR/AUG26M") == date(2026, 8, 31)
    # alias sólo para los 4 meses que difieren, en ambas direcciones
    assert fut._alias("DLR/AGO26M") == "DLR/AUG26M"
    assert fut._alias("DLR/AUG26") == "DLR/AGO26"
    assert fut._alias("DLR/FEB26") is None
    # la siembra del WS incluye los dos códigos (el broker descarta el falso)
    alls = fut.all_symbols()
    ags = [s for s in alls if "AGO" in s]
    assert ags and all(s.replace("AGO", "AUG") in alls for s in ags)


def test_rows_lee_data_bajo_alias_ingles() -> None:
    """Data llegada (o persistida de versiones viejas) bajo el código inglés
    alimenta la fila del contrato canónico; `code` expone el símbolo real con
    data para que el click al book pegue en el store."""
    from backend.services import marketdata_store as mds

    sym = next(s for s in fut.symbols("may") if "AGO" in s)
    alias = fut._alias(sym)
    sp = fut.spot() or 1000.0
    mds.get_store().update_from_md(alias, {"LA": {"price": sp * 1.05},
                                           "OI": {"size": 4321.0}})
    r = next((x for x in fut.rows("may") if x["code"] == alias), None)
    assert r is not None and r["last"] == pytest.approx(sp * 1.05)
    assert r["oi"] == 4321.0 and r["label"].startswith("Ago")
    assert r["tna"] is not None


def test_rows_tea_y_volumen_fallback_nominal() -> None:
    """TEA = TIR efectiva anual directa del td; sin EV el volumen cae al
    nominal (NV, contratos) para no mostrar '—' con mercado operando."""
    from backend.services import marketdata_store as mds

    sym = fut.symbols("may")[2]
    sp = fut.spot() or 1000.0
    mds.get_store().update_from_md(sym, {"LA": {"price": sp * 1.06}, "NV": {"size": 7777.0}})
    r = next(x for x in fut.rows("may") if x["code"] == sym)
    assert r["tea"] == pytest.approx((1.0 + r["td"]) ** (365.0 / r["dias"]) - 1.0)
    assert r["volume"] == 7777.0


def test_deva_chart_promedio() -> None:
    """La línea 'prom' es la TEM constante que compone al mismo punto final."""
    rws = [{"label": "A", "dias": 30, "last": 1030.0},
           {"label": "B", "dias": 61, "last": 1060.0}]
    ch = fut.deva_path_chart(rws, 1000.0)
    assert ch and ch["avg"] is not None
    assert ch["avg"]["val"] == pytest.approx((1060.0 / 1000.0) ** (30.4375 / 61.0) - 1.0)


def test_implied_rate_math() -> None:
    td, tna, tem = fut._impl(110.0, 100.0, 365)      # +10% en 1 año
    assert td == pytest.approx(0.10)
    assert tna == pytest.approx(0.10)                # lineal: 0.10·365/365
    assert tem is not None and tem > 0
    assert fut._impl(None, 100.0, 30) == (None, None, None)
    assert fut._impl(110.0, None, 30) == (None, None, None)


def test_rows_from_store() -> None:
    from backend.services import marketdata_store as mds
    # [1], no [0]: el último día del mes el contrato front vence HOY (días=0,
    # sin tasa implícita) y el test fallaba sólo ese día del calendario.
    sym = fut.symbols("may")[1]
    sp = fut.spot() or 1000.0
    mds.get_store().update_from_md(sym, {"LA": {"price": sp * 1.03}, "CL": {"price": sp * 1.02}})
    r = next((x for x in fut.rows("may") if x["code"] == sym), None)
    assert r is not None and r["dias"] is not None
    assert r["tna"] is not None and r["last"] == pytest.approx(sp * 1.03)


@pytest.mark.asyncio
async def test_futuros_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p = await ac.get("/futuros")
        t = await ac.get("/futuros/table")
    assert p.status_code == 200 and "Spot A3500" in p.text and "Mayorista" in p.text
    # futuros arriba del panel DLK; columna Código presente
    assert t.status_code == 200 and "Código" in t.text
    if "Dólar Linked soberanos" in t.text:
        assert t.text.find("Mayorista") < t.text.find("Dólar Linked soberanos")


@pytest.mark.asyncio
async def test_futuros_override_and_book() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds

    sym = fut.symbols("may")[0]
    sp = fut.spot() or 1410.0
    mds.get_store().update_from_md(sym, {
        "LA": {"price": sp * 1.03},
        "BI": [{"price": sp * 1.02, "size": 100}],
        "OF": [{"price": sp * 1.04, "size": 50}]})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ov = await ac.get("/futuros/table?spot_override=1500")
        bk = await ac.get("/futuros/book", params={"code": sym})
    assert ov.status_code == 200 and "1.500,00" in ov.text       # usó el override
    assert bk.status_code == 200 and "Profundidad" in bk.text and "Compras" in bk.text


@pytest.mark.asyncio
async def test_futuros_tabla_puntas_oi_y_graficos() -> None:
    """La tabla muestra puntas × size, Vol y OI con la Σ al pie, y con ≥2
    contratos con precio se dibujan la curva de TNA y el sendero de deva."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds

    sp = 1400.0
    # [1] y [2]: el front puede tener días=0 a fin de mes (sin TNA → sin curva)
    s1, s2 = fut.symbols("may")[1], fut.symbols("may")[2]
    st = mds.get_store()
    st.update_from_md(s1, {"LA": {"price": sp * 1.02},
                           "BI": [{"price": sp * 1.015, "size": 120}],
                           "OF": [{"price": sp * 1.025, "size": 80}],
                           "EV": 50_000.0, "OI": {"size": 1_000.0}})
    st.update_from_md(s2, {"LA": {"price": sp * 1.04}, "OI": {"size": 2_500.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        t = await ac.get("/futuros/table?spot_override=1400")
    assert t.status_code == 200
    assert "Bid × size" in t.text and "OI" in t.text and "TEA" in t.text
    assert "×120" in t.text                                       # size de la punta
    assert "Σ volumen / interés abierto" in t.text                # footer con la suma
    assert "Σ OI" in t.text                                       # strip: OI total
    assert "Curva de tasas implícitas" in t.text                  # línea (SVG)
    assert "Sendero de devaluación mensual" in t.text             # barras (SVG)
    assert "fc-bar" in t.text and "fc-line" in t.text
    assert "TEM promedio" in t.text and "fc-avg" in t.text        # sendero promedio
    assert 'class="fut-tables"' in t.text                         # tiras apiladas
