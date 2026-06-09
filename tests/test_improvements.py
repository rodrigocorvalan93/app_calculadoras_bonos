"""Mejoras: delta B−A del comparador, posición con sufijo j/v, what-if de
forwards (precio editable → recálculo) y panel de datos del libro.

  - `positions.position_for` resuelve el sufijo (TTS26v → TTS26) como el
    path de precios (`symbols.calc_to_md_code`).
  - HTTP smoke de /comparador/result (header Δ (B−A)), /forwards/table con
    filtro de bonos, /forwards/whatif con precio override y /mercado/book.
"""
from __future__ import annotations

import pytest

from backend.services import bond_universe
from backend.services import positions


def test_position_for_strips_jv_suffix() -> None:
    """TTS26v / TTS26 caen en la misma tenencia que el Cod_Delta TTS26."""
    saved = positions._cache
    positions._cache = {
        "error": None, "paths": {}, "holdings": [], "loaded": True,
        "fondos": {18: "Crecimiento"}, "pn": {18: 1000.0},
        "by_code": {"TTS26": {
            "especie": "TTS26", "total_cantidad": 100.0, "total_valor": 80.0,
            "funds": [{"cod_fondo": 18, "cantidad": 100.0, "valor": 80.0}],
        }},
    }
    try:
        base = positions.position_for("TTS26")
        suff = positions.position_for("TTS26v")        # sufijo v
        assert base is not None and suff is not None
        assert suff["code"] == "TTS26"                 # normalizado
        assert suff["total_cantidad"] == 100.0
        assert suff["funds"][0]["pct_pn"] == pytest.approx(80.0 / 1000.0)
        assert positions.position_for("NOPE") is None
    finally:
        positions._cache = saved


def test_position_for_ignores_plazo_suffix() -> None:
    """'S31L6 CI' (mismo bono, plazo CI) cae en la tenencia de 'S31L6'."""
    saved = positions._cache
    positions._cache = {
        "error": None, "paths": {}, "holdings": [], "loaded": True,
        "fondos": {10: "Performance"}, "pn": {10: 1000.0},
        "by_code": {"S31L6": {
            "especie": "S31L6", "total_cantidad": 150.0, "total_valor": 1380.0,
            "funds": [{"cod_fondo": 10, "cantidad": 150.0, "valor": 1380.0}],
        }},
    }
    try:
        assert positions._norm_code("S31L6 CI") == "S31L6"
        assert positions._norm_code("S31L6 24HS") == "S31L6"
        assert positions._norm_code("TX26j") == "TX26J"          # NO toca el sufijo j/v
        p = positions.position_for("S31L6 CI")
        assert p is not None and p["code"] == "S31L6" and p["total_cantidad"] == 150.0
    finally:
        positions._cache = saved


def test_corporate_curves_are_seeded() -> None:
    """Los corporativos (RVS1O y la curva corp_tamar) se suscriben al WS."""
    from backend import main
    from backend.services import curves, symbols as syms

    bond_universe.ensure_loaded()
    seed = set(main._initial_symbols())
    assert syms.md_symbol("RVS1O", "24hs") in seed
    corp = curves.build_curve_codes().get("corp_tamar", [])
    if corp:
        assert all(syms.md_symbol(c, "24hs") in seed for c in corp)


def test_dlk_tir_reacts_to_a3500() -> None:
    """La TIR de un DLK reacciona al cambio del A3500 (la key del cache incluye el
    índice). Antes quedaba vieja hasta el TTL de 20 s. LECAP no mete índice."""
    import numpy as np
    import rentafija

    from backend.services import curves, pricing

    bond_universe.ensure_loaded()
    g = curves.build_curve_codes()
    cer = (g.get("cer") or [None])[0]
    if cer:
        assert pricing._bond_index_kind(cer) == "cer"
    lec = (g.get("lecap") or [None])[0]
    if lec:
        assert pricing._bond_index_kind(lec) == ""              # nominal → sin índice en la key
    dlk = (g.get("dolarlinked") or g.get("corp_dlk") or [None])[0]
    if not dlk:
        pytest.skip("sin bonos dólar-linked")
    assert pricing._bond_index_kind(dlk) == "a3500"
    df = rentafija.inputs.get("a3500")
    if df is None or not len(df):
        pytest.skip("sin serie A3500")
    col = df.columns.get_loc("tca3500")
    orig = float(df.iloc[-1, col])
    price = None
    for p in (100.0, 1000.0, 5000.0, 500.0, 50.0, 10000.0):
        m = pricing.metrics_for_market_price(dlk, p)
        if m and np.isfinite(m.get("tirea", float("nan"))):
            price = p
            break
    if price is None:
        pytest.skip("el DLK no pricea en este entorno")
    try:
        t1 = pricing.metrics_for_market_price(dlk, price)["tirea"]
        df.iloc[-1, col] = orig * 1.10                          # +10% A3500
        pricing._index_val_cache.clear()                       # fingerprint lo toma ya
        t2 = pricing.metrics_for_market_price(dlk, price)["tirea"]
        assert abs(t1 - t2) > 1e-9                              # la TIR reaccionó
    finally:
        df.iloc[-1, col] = orig
        pricing._index_val_cache.clear()
        pricing._curve_metrics_cache.clear()


@pytest.mark.asyncio
async def test_posiciones_shows_asof() -> None:
    """Posiciones muestra la fecha de la última cartera (mtime del archivo)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    assert positions._file_asof(None) is None
    saved = positions._cache
    positions._cache = {
        "loaded": True, "error": None, "holdings": [], "pn": {10: 1000.0},
        "fondos": {10: "Performance"}, "paths": {}, "by_code": {}, "asof": "01/06/2026 09:30",
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/posiciones")
        assert r.status_code == 200
        assert "Última cartera: 01/06/2026 09:30" in r.text
    finally:
        positions._cache = saved


@pytest.mark.asyncio
async def test_matriz_has_copyable_detail() -> None:
    """La Matriz trae el detalle vertical copiable (JS) y los datos para armarlo."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    saved = positions._cache
    positions._cache = {
        "loaded": True, "error": None, "paths": {}, "asof": None, "by_code": {},
        "pn": {10: 1_000_000.0, 20: 500_000.0}, "fondos": {10: "RENTA", 20: "Multimercado"},
        "holdings": [
            {"cod_delta": "TX26", "cod_fondo": 10, "cantidad": 200000.0, "valor": 200000.0, "especie": "TX26", "clase": None},
            {"cod_delta": "TX26", "cod_fondo": 20, "cantidad": 100000.0, "valor": 100000.0, "especie": "TX26", "clase": None},
        ],
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/matriz")
        assert r.status_code == 200
        assert 'id="matriz-detail"' in r.text and "buildMatrizDetail" in r.text
        assert "RENTA" in r.text and "200.000" in r.text and "100.000" in r.text
    finally:
        positions._cache = saved


def test_todos_ars_aggregate_includes_duals() -> None:
    """'Todos ARS (Proyectado)' = TAMAR + CER Proy + Tasa Fija + duales, y los
    códigos CER Proyectado resuelven (con una sola 'j', no 'jj')."""
    from backend.services import curves, pricing

    bond_universe.ensure_loaded()
    g = curves.build_curve_codes()
    agg = set(g.get("todos_ars_proyectado", []))
    for sub in ("tamar", "cerproy", "lecap", "dualfija", "dualtamar", "dualcer"):
        assert set(g.get(sub, [])) <= agg, f"falta {sub} en el agregado"
    cp = g.get("cerproy", [])
    assert cp and all(pricing.bond_meta(c) for c in cp), "cerproy con códigos que no resuelven (¿jj?)"
    assert all(not c.endswith("jj") for c in cp)


def _first_codes(n: int = 2) -> list[str]:
    bond_universe.ensure_loaded()
    codes = bond_universe.all_codes()
    if len(codes) < n:
        pytest.skip("universo de bonos insuficiente")
    return codes[:n]


@pytest.mark.asyncio
async def test_comparador_delta_is_b_minus_a() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    a, b = _first_codes(2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/comparador/result", params={
            "a": a, "b": b, "mode": "precio", "val_a": "70", "val_b": "72", "plazo": "24hs"})
    assert r.status_code == 200
    assert "Δ (B−A)" in r.text          # header en la dirección nueva


@pytest.mark.asyncio
async def test_comparador_modes_tir_and_margen() -> None:
    """El comparador acepta los 4 modos; en margen, un bono de tasa fija
    muestra 'no aplica' en vez de un número engañoso."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    var = fija = None
    for c in bond_universe.all_codes():
        m = pricing.bond_meta(c) or {}
        t = (m.get("tipo_tasa_interes") or "").upper()
        idx = (m.get("index") or "").upper()
        if not var and t in ("VARIABLE", "VARIABLE_CAP") and idx in ("TAMAR", "BADLAR"):
            var = c
        if not fija and t not in ("VARIABLE", "VARIABLE_CAP"):
            fija = c
        if var and fija:
            break
    if not (var and fija):
        pytest.skip("falta un bono variable o uno de tasa fija")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        rt = await ac.get("/comparador/result", params={
            "a": var, "b": fija, "mode": "tir", "val_a": "0.40", "val_b": "0.45", "plazo": "24hs"})
        rm = await ac.get("/comparador/result", params={
            "a": var, "b": fija, "mode": "margen", "val_a": "0.02", "val_b": "0.03", "plazo": "24hs"})
    assert rt.status_code == 200 and "por TIREA" in rt.text
    assert rm.status_code == 200 and "por Margen" in rm.text
    assert "no aplica" in rm.text          # la fija no tiene margen


@pytest.mark.asyncio
async def test_forwards_filter_and_whatif() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import curves

    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    key = next((k for k, v in table.items() if v), None)
    if not key:
        pytest.skip("sin curvas")
    codes = table[key][:3]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # filtro: matriz sólo con un subconjunto tildado
        params = [("curve", key), ("plazo", "24hs"), ("leg", "native"), ("filtered", "1")]
        params += [("code", c) for c in codes]
        r1 = await ac.get("/forwards/table", params=params)
        assert r1.status_code == 200
        # what-if: mismo set + un precio editado → 200 y tabla editable
        r2 = await ac.get("/forwards/whatif", params=params + [(f"price_{codes[0]}", "70.5")])
        assert r2.status_code == 200
        assert 'id="wi-prices"' in r2.text or "Sin bonos" in r2.text
        # cuerpo completo (filtro + matriz + what-if)
        r3 = await ac.get("/forwards/body", params=[("curve", key), ("plazo", "24hs"), ("leg", "native")])
        assert r3.status_code == 200
        assert 'id="forwards-filter"' in r3.text


def test_forwards_matrix_caps_width() -> None:
    """Curvas anchas: la matriz se capa a MAX_FWD por volumen (perf + legible).
    El what-if comparte el tope y reusa la TIR de la fila si no se editó."""
    from backend.routes import curves as rc

    n = rc.MAX_FWD + 30
    rows = [{"code": f"B{i}", "tirea": 0.10 + i * 0.001, "duration": 1.0 + i * 0.1,
             "px_calc": 90.0, "volume": float(i)} for i in range(n)]
    m = rc._matrix_from_rows(rows)
    assert m["truncated"] is True and m["total"] == n and m["n"] == rc.MAX_FWD
    kept = {r["code"] for r in m["rows"]}
    assert f"B{n - 1}" in kept and f"B0" not in kept       # se quedan los de mayor volumen

    wi_rows, wi_m = rc._whatif_from_rows(rows, None, {})
    assert len(wi_rows) == rc.MAX_FWD and wi_m["n"] == rc.MAX_FWD
    assert all(not r["edited"] for r in wi_rows)            # sin overrides → nada editado


@pytest.mark.asyncio
async def test_mercado_book_shows_row_stats() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    code = _first_codes(1)[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs", "leg": "native"})
    assert r.status_code == 200
    assert "book-stats" in r.text       # panel con toda la fila
    assert "TIR @ last" in r.text and "Mín op." in r.text
