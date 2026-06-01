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
