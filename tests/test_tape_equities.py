"""Barra de activos + panel Acciones/CEDEARs + noticias — smoke CI-safe."""
from __future__ import annotations

import pytest

from backend.services import equities, marketdata_store as mds, symbols as syms


def _seed(code: str, px: float, close: float) -> None:
    mds.get_store().update_from_md(syms.md_symbol(code, "24hs"), {
        "BI": {"price": px * 0.999}, "OF": {"price": px * 1.001},
        "LA": {"price": px}, "CL": {"price": close},
        "OP": {"price": close}, "EV": {"size": 1_000_000}, "NV": {"size": 5_000}})


def test_equities_rows() -> None:
    _seed("GGAL", 5400.0, 5300.0)
    r = equities.row_for("GGAL")
    assert r and r["last"] == 5400.0
    assert abs(r["var_pct"] - (5400.0 / 5300.0 - 1) * 100) < 1e-9
    rows = equities.panel_rows("lideres")
    assert any(x["code"] == "GGAL" for x in rows)
    assert "tirea" not in rows[0]                  # sin calculadora


def test_merval_snapshot_robusto_a_simbolo() -> None:
    """El índice Merval llega con un string que puede diferir del que suscribimos
    (echo del broker). merval_snapshot escanea el store por 'MERVAL' → lo encuentra
    aunque no matchee ninguna variante exacta, así el 'MERVAL US$' del tape aparece."""
    mds.get_store().update_from_md("MERV - XMEV - I.MERVAL - spot",
                                   {"LA": {"price": 2_500_000.0}, "CL": {"price": 2_450_000.0}})
    ms = equities.merval_snapshot()
    assert ms is not None and ms.last == 2_500_000.0


@pytest.mark.asyncio
async def test_tape_merval_usd_aparece() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    store = mds.get_store()
    # CCL computable: pata ARS (base) + cable (…C) de los globales
    for c in curves.build_curve_codes().get("globales", []):
        base = c[:-1] if c.endswith("C") else c
        store.update_from_md(syms.md_symbol(base, "24hs"), {"LA": {"price": 70000.0}})
        store.update_from_md(syms.md_symbol(base + "C", "24hs"), {"LA": {"price": 70.0}})
    # El índice llega por IV (Index Value), NO por LA — el shape real del feed.
    store.update_from_md("MERV - XMEV - I.MERVAL - spot",
                         {"IV": {"price": 2_500_000.0}, "CL": {"price": 2_450_000.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        tp = await ac.get("/tape")
    assert tp.status_code == 200
    # DOS entradas: nivel en $ (índice crudo, 0 decimales) y en US$ (por CCL)
    assert ">MERVAL<" in tp.text and "MERVAL US$" in tp.text
    assert "2.500.000" in tp.text                                # nivel ARS sin decimales


@pytest.mark.asyncio
async def test_equities_tape_news_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _seed("SPY", 42000.0, 41000.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        eq = await ac.get("/mercado/table?panel=lideres&plazo=24hs")
        tp = await ac.get("/tape")
        nm = await ac.get("/news/marquee")
        mp = await ac.get("/mercado")
    assert eq.status_code == 200 and "GGAL" in eq.text and "TIREA" not in eq.text
    assert tp.status_code == 200                    # con o sin items, nunca rompe
    assert nm.status_code == 200                    # sin red → vacío, no error
    assert mp.status_code == 200 and 'value="cedears"' in mp.text   # selector de panel


def test_panel_general_y_cedears_ampliados() -> None:
    """El panel General existe (antes sólo había Líder) y las listas curadas
    no se pisan entre sí; un ticker sin cotización simplemente no aparece."""
    assert len(equities.GENERAL) >= 30 and len(equities.CEDEARS) >= 60
    assert not (set(equities.GENERAL) & set(equities.LIDERES))
    assert len(set(equities.CEDEARS)) == len(equities.CEDEARS)   # sin duplicados
    _seed("MOLI", 300.0, 290.0)
    rows = equities.panel_rows("general")
    assert any(x["code"] == "MOLI" for x in rows)
    assert not any(x["code"] == "GGAL" for x in rows)            # líder no se mezcla
    # el seed del WS suscribe los TRES paneles (24hs + CI)
    subs = equities.all_symbols()
    assert any("MOLI" in s for s in subs) and any("NFLX" in s for s in subs)


@pytest.mark.asyncio
async def test_panel_lideres_encabeza_con_el_merval_y_oclh_ocultable() -> None:
    """(1) El índice Merval encabeza el panel Líderes (y Líder + General con
    badge I): nivel por IV, OCLH del feed, var vs cierre, sin puntas / VWAP /
    volumen, fijado arriba (`data-pin`) y sin libro; no cuenta como especie ni
    aparece en General / CEDEARs. (2) Las columnas OCLH de la tabla de acciones
    llevan `col-oclh`: el toggle de la página (CSS puro) no las ocultaba."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _seed("GGAL", 5400.0, 5300.0)
    mds.get_store().update_from_md("MERV - XMEV - I.MERVAL - spot",
                                   {"IV": {"price": 2_500_000.0}, "CL": {"price": 2_450_000.0},
                                    "OP": {"price": 2_460_000.0}, "HI": {"price": 2_510_000.0},
                                    "LO": {"price": 2_440_000.0}})
    equities._merval_sym = None
    rows = equities.panel_rows("lideres")
    assert rows[0]["code"] == "MERVAL" and rows[0]["indice"] is True
    assert rows[0]["last"] == 2_500_000.0 and rows[0]["open"] == 2_460_000.0
    assert abs(rows[0]["var_pct"] - (2_500_000.0 / 2_450_000.0 - 1) * 100) < 1e-9
    assert rows[0]["bid"] is None and rows[0]["vwap"] is None and rows[0]["volume"] is None
    assert rows[0]["volume_frac"] == 0.0 and rows[0]["range_pos"] is not None
    assert sum(1 for r in rows if r.get("indice")) == 1 and any(r["code"] == "GGAL" for r in rows)
    todas = equities.panel_rows("todas")
    assert todas[0]["code"] == "MERVAL" and todas[0]["panel"] == "I"
    assert not any(r["code"] == "MERVAL" for r in equities.panel_rows("general"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table?panel=lideres&plazo=24hs")
        g = await ac.get("/mercado/table?panel=general&plazo=24hs")
    assert r.status_code == 200
    html = r.text
    i_merval = html.index("MERVAL")
    assert i_merval < html.index(">GGAL<")                             # encabeza la tabla
    fila = html[html.rfind("<tr", 0, i_merval):html.index("</tr>", i_merval)]
    assert 'data-pin' in fila and 'row-indice' in fila and "2.500.000,00" in fila
    assert "/mercado/book/MERVAL" not in html                           # sin libro
    assert 'class="col-oclh grp">Open</th>' in html and html.count('class="col-oclh"') >= 4
    n = len([x for x in rows if not x.get("indice")])
    assert f"{n} especies" in html                                      # el índice no cuenta
    assert "MERVAL" not in g.text


@pytest.mark.asyncio
async def test_http_panel_general() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _seed("MOLI", 300.0, 290.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table?panel=general&plazo=24hs")
        assert r.status_code == 200
        assert "Panel general" in r.text and "MOLI" in r.text
        mp = await ac.get("/mercado")
        assert 'value="general"' in mp.text                      # opción en el selector
