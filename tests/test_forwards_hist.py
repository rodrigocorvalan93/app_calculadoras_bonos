"""Histórico de forwards par-a-par — fórmula, serie, stats/percentil y endpoint."""
from __future__ import annotations

import pytest

from backend.services import forwards_hist as fh


def test_fwd_rate_formula() -> None:
    # forward 0,5→1,0 años con 30% y 35%: f = (d1/d2)^(1/0,5) − 1
    y1, t1, y2, t2 = 0.30, 0.5, 0.35, 1.0
    d1, d2 = (1 + y1) ** -t1, (1 + y2) ** -t2
    esperado = (d1 / d2) ** (1.0 / (t2 - t1)) - 1.0
    assert fh.fwd_rate(y1, t1, y2, t2) == pytest.approx(esperado)
    assert fh.fwd_rate(y1, 1.0, y2, 0.5) is None       # t2 ≤ t1
    assert fh.fwd_rate(None, t1, y2, t2) is None
    assert fh.fwd_rate(-1.5, t1, y2, t2) is None       # (1+y) ≤ 0


def _base_sintetica(monkeypatch, n=100, ver="v-test"):
    """historico_byma falso: A (corto) y B (largo) con TIR/Duration por rueda."""
    from backend.services import historico_byma as hb

    dates = [f"2026-{4 + i // 30:02d}-{(i % 30) + 1:02d}" for i in range(n)]
    a = {"dates": dates, "vals": {"TIREA": [0.30 + 0.0005 * i for i in range(n)],
                                  "Duration": [0.5] * n}}
    b = {"dates": dates, "vals": {"TIREA": [0.35 + 0.0005 * i for i in range(n)],
                                  "Duration": [1.0] * n}}
    fake = {"loaded": True, "by_code": {"AAA": a, "BBB": b}, "last_update": ver}
    monkeypatch.setattr(hb, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(hb, "meta", lambda: {"last_update": ver})
    monkeypatch.setattr(hb, "available", lambda: True)
    return dates


def test_serie_y_stats_con_ventana(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=100, ver="v1")
    s = fh.serie("AAA", "BBB")
    assert len(s["dates"]) == 100 and len(s["fwds"]) == 100
    # la serie es creciente (TIRs suben en paralelo) → percentil alto para el último
    st = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=s["fwds"][-1])
    assert st["n"] == 60                                # ventana recorta
    assert st["media"] == pytest.approx(sum(s["fwds"][-60:]) / 60)
    assert st["desvio"] is not None and st["desvio"] > 0
    assert st["percentil"] is not None and st["percentil"] > 0.95
    assert st["z"] == pytest.approx((s["fwds"][-1] - st["media"]) / st["desvio"])
    assert st["aviso_n"] is False
    # toda la historia
    st_all = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=None)
    assert st_all["n"] == 100 and st_all["percentil"] is None
    # un fwd_hoy en la mediana → percentil ~50
    mid = sorted(s["fwds"][-60:])[30]
    st_mid = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=mid)
    assert 0.35 < st_mid["percentil"] < 0.65


def test_stats_muestra_chica_avisa(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=8, ver="v2")
    st = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=0.4)
    assert st["n"] == 8 and st["aviso_n"] is True


def test_par_sin_datos(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=10, ver="v3")
    assert fh.serie("AAA", "NOEXISTE")["fwds"] == []
    st = fh.stats("AAA", "NOEXISTE", ventana=60)
    assert st["n"] == 0 and st["media"] is None


def test_chart_geometria(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=50, ver="v4")
    s = fh.serie("AAA", "BBB")
    st = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=s["fwds"][-1])
    ch = fh.chart(st)
    assert ch is not None
    assert len(ch["poly"].split()) == 50                # un punto por rueda
    assert ch["media_y"] is not None and ch["banda"] is not None
    assert ch["hoy"] is not None and len(ch["xlabels"]) == 5
    assert all(ch["y0"] <= t["y"] <= ch["y1"] for t in ch["yticks"])


def test_chart_y_stats_con_what_if(monkeypatch) -> None:
    """El forward recalculado con los precios editados del what-if entra como
    SEGUNDO punto (`whatif`, misma x que hoy) con percentil / z propios y
    también manda en la escala vertical; sin what-if no hay punto ni stats."""
    _base_sintetica(monkeypatch, n=50, ver="v6")
    s = fh.serie("AAA", "BBB")
    hoy = s["fwds"][-1]
    st = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=hoy, fwd_whatif=hoy + 0.5)   # muy por encima del máximo
    assert st["fwd_wi"] == pytest.approx(hoy + 0.5)
    assert st["percentil_wi"] == 1.0 and st["z_wi"] > 0
    assert st["percentil"] == pytest.approx(fh.stats("AAA", "BBB", ventana=0, fwd_hoy=hoy)["percentil"])
    ch = fh.chart(st)
    assert ch["whatif"] is not None and ch["whatif"]["cx"] == ch["hoy"]["cx"]
    assert ch["y0"] <= ch["whatif"]["cy"] < ch["hoy"]["cy"]          # entra en la escala, arriba del de hoy
    st0 = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=hoy)
    assert st0["fwd_wi"] is None and st0["percentil_wi"] is None and st0["z_wi"] is None
    assert fh.chart(st0)["whatif"] is None


@pytest.mark.asyncio
async def test_forwards_hist_punto_what_if_solo_con_precio_editado(monkeypatch) -> None:
    """Con un precio editado en el what-if (`price_<CODE>`, lo que el panel
    manda con `#wi-prices`) para uno de los dos bonos del par, el histórico
    muestra el anillo celeste (`fc-dot-wi`) y la línea "what-if" con la Δ en
    bps; sin precio, con el input vacío o con un precio de OTRO bono, nada."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.routes import curves as rc
    from backend.services import bond_universe, curves, historico_byma as hb, marketdata_store as mds
    from backend.services import symbols as syms

    bond_universe.ensure_loaded()
    codes = (curves.build_curve_codes().get("cer") or [])[:6]
    px = {c: 1150.0 + i * 40 for i, c in enumerate(codes)}
    for c in codes:
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": px[c]}})
    rows, _ = await rc._rows_for("cer", "24hs", True, "native")
    cand = rc._candidates_from_rows([r for r in rows if r["code"] in codes])
    if len(cand) < 2:
        pytest.skip("sin dos bonos CER valuables con precio sintético")
    corto, largo = cand[0], cand[1]
    dates = [f"2026-{4 + i // 30:02d}-{(i % 30) + 1:02d}" for i in range(40)]
    by = {corto: {"dates": dates, "vals": {"TIREA": [0.30] * 40, "Duration": [0.5] * 40}},
          largo: {"dates": dates, "vals": {"TIREA": [0.35] * 40, "Duration": [1.0] * 40}}}
    fake = {"loaded": True, "by_code": by, "last_update": "v-wi"}
    monkeypatch.setattr(hb, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(hb, "meta", lambda: {"last_update": "v-wi"})
    monkeypatch.setattr(hb, "available", lambda: True)
    base = {"curve": "cer", "fw-corto": corto, "fw-largo": largo, "fw-ventana": "0"}
    ar = lambda v: f"{v:.2f}".replace(".", ",")                       # es-AR, como lo manda el input  # noqa: E731
    editado = ar(px[corto] * 0.99)
    # el input viene pre-cargado con el precio de mercado a 2 decimales: eso NO es edición
    pre = {f"price_{corto}": ar(px[corto]), f"price_{largo}": ar(px[largo]),
           f"mkt_{corto}": ar(px[corto]), f"mkt_{largo}": ar(px[largo])}
    # el panel se dibujó con otro precio (el mercado se movió después) y el
    # usuario no tocó nada: el input sigue igual a lo que mostraba → tampoco
    viejo = {f"price_{corto}": ar(px[corto] * 1.02), f"price_{largo}": ar(px[largo]),
             f"mkt_{corto}": ar(px[corto] * 1.02), f"mkt_{largo}": ar(px[largo])}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        sin = await ac.get("/forwards/hist", params=base)
        vacio = await ac.get("/forwards/hist", params={**base, f"price_{corto}": ""})
        otro = await ac.get("/forwards/hist", params={**base, "price_ZZZZ": "100"})
        igual = await ac.get("/forwards/hist", params={**base, **pre})
        stale = await ac.get("/forwards/hist", params={**base, **viejo})
        con = await ac.get("/forwards/hist", params={**base, **pre, f"price_{corto}": editado})
    for r in (sin, vacio, otro, igual, stale, con):
        assert r.status_code == 200
    assert 'class="fc-dot"' in sin.text                                  # el de hoy, siempre
    for r in (sin, vacio, otro, igual, stale):
        assert "fc-dot-wi" not in r.text and "what-if" not in r.text
    assert "fc-dot-wi" in con.text and 'class="fc-dot"' in con.text      # los dos puntos
    assert "◯ what-if" in con.text and " bps" in con.text
    assert "el anillo celeste, el del what-if" in con.text


def test_precio_editado_es_distinto_del_que_mostraba_el_input() -> None:
    """El what-if pre-carga cada input con el precio de mercado a 2 decimales
    (`ar_num(2)`) y a partir del primer cambio TODOS viajan con valor: sólo un
    precio distinto del que MOSTRABA el input (hidden `mkt_<CODE>` del mismo
    render; sin él, el mercado vivo) cuenta como edición — para el resaltado y
    la re-valuación del what-if y para el anillo del histórico. Antes una sola
    edición dejaba las 22 filas como `wi-edited`, re-valuadas al precio
    redondeado, y las seguía mostrando así después de borrarla; y contra el
    mercado VIVO un input sin tocar parecía editado apenas el bono operaba."""
    from backend.routes import curves as rc

    assert rc._precio_editado(None, 175.8437) is False
    assert rc._precio_editado(175.84, 175.8437) is False        # lo que muestra el input (sin hidden)
    assert rc._precio_editado(175.85, 175.8437) is True
    assert rc._precio_editado(150.0, 175.8437) is True
    assert rc._precio_editado(150.0, None) is True              # sin precio de mercado: lo que tipeó manda
    assert rc._precio_editado(175.84, 176.90, mostrado=175.84) is False   # el mercado se movió, el input no
    assert rc._precio_editado(175.84, 175.84, mostrado=176.90) is True    # tipeó justo el mercado nuevo: editó
    rows = [{"code": "A", "px_calc": 175.8437, "calc": "A", "tirea": 0.30, "duration": 0.5, "volume": 1.0},
            {"code": "B", "px_calc": 90.0, "calc": "B", "tirea": 0.35, "duration": 1.0, "volume": 1.0}]
    wi, _m = rc._whatif_from_rows(rows, None, {"A": 175.84, "B": 90.0}, None)
    assert [r["edited"] for r in wi] == [False, False]
    assert wi[0]["tirea"] == 0.30 and wi[0]["price"] == 175.8437   # reusa la fila, no re-valúa al redondeado
    wi2, _m = rc._whatif_from_rows(rows, None, {"A": 170.0, "B": 90.0}, None, {"A": 170.0, "B": 90.0})
    assert [r["edited"] for r in wi2] == [False, False]           # mostraba 170 y sigue en 170: sin tocar
    assert rc._fwd_whatif(rows[0], rows[1], {"A": 170.0, "B": 90.0}, None, {"A": 170.0, "B": 90.0}) is None


@pytest.mark.asyncio
async def test_forwards_hist_endpoint(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _base_sintetica(monkeypatch, n=40, ver="v5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # par sintético: sin fwd de hoy (no está en la curva viva) pero con serie
        r = await ac.get("/forwards/hist", params={
            "curve": "cer", "fw-corto": "AAA", "fw-largo": "BBB", "fw-ventana": "30"})
        vacio = await ac.get("/forwards/hist", params={"curve": "cer"})
        page = await ac.get("/forwards", params={"only_quoting": "false"})
    assert r.status_code == 200
    assert "Media (30 ruedas)" in r.text and "Percentil hoy" in r.text
    assert "fc-band" in r.text and "fc-avg" in r.text     # banda ±1σ + media
    assert "Ojo con el percentil" in r.text               # la advertencia SIEMPRE visible
    assert vacio.status_code == 200                       # sin par → estado vacío, no 500
    assert page.status_code == 200
    if "Histórico del forward" in page.text:              # con ≥2 candidatos
        assert 'name="fw-corto"' in page.text and 'name="fw-ventana"' in page.text


def test_serie_saltea_gaps_infimos(monkeypatch) -> None:
    """t2−t1 → 0 anualiza a miles de %: esas ruedas quedan FUERA de la serie
    para no envenenar media/desvío/percentil con un solo outlier."""
    from backend.services import historico_byma as hb

    dates = [f"2026-05-{i+1:02d}" for i in range(10)]
    a = {"dates": dates, "vals": {"TIREA": [0.30] * 10, "Duration": [0.50] * 10}}
    # el largo cruza al corto en las últimas 5 ruedas (gap < _MIN_GAP)
    b = {"dates": dates, "vals": {"TIREA": [0.35] * 10,
                                  "Duration": [1.0] * 5 + [0.51] * 5}}
    fake = {"loaded": True, "by_code": {"C": a, "L": b}, "last_update": "v-gap"}
    monkeypatch.setattr(hb, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(hb, "meta", lambda: {"last_update": "v-gap"})
    s = fh.serie("C", "L")
    assert len(s["fwds"]) == 5                      # sólo las ruedas con gap sano


@pytest.mark.asyncio
async def test_matriz_celdas_clickeables_para_hist() -> None:
    """Las celdas con forward llevan data-fwc/data-fwl (fila=corto, col=largo):
    app.js las usa para cargar ese par en el panel de histórico."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds
    from backend.services import symbols as syms

    bond_universe.ensure_loaded()
    for i, c in enumerate((curves.build_curve_codes().get("cer") or [])[:5]):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 1150.0 + i * 40}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/forwards/table", params={"curve": "cer"})
    assert r.status_code == 200
    if 'data-fwc="' in r.text:                      # con ≥2 bonos válidos
        assert 'data-fwl="' in r.text
