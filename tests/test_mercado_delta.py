"""Mercado en vivo por FILAS: seq por símbolo en el store, /mercado/rows (sólo
las filas cambiadas desde `since`, X-Seq / X-Rows / X-Full), la tabla completa
con data-delta / data-seq / data-order y filas data-code (misma macro), y el
módulo delta de app.js."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, marketdata_store, symbols as syms

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def test_store_seq_por_simbolo() -> None:
    store = marketdata_store.get_store()
    s0 = store.seq()
    a = store.update_from_md("MERV - XMEV - ZZ01 - 24hs", {"LA": {"price": 100.0}})
    b = store.update_from_md("MERV - XMEV - ZZ02 - 24hs", {"LA": {"price": 100.0}})
    assert a.seq == s0 + 1 and b.seq == s0 + 2 and store.seq() == s0 + 2
    store.update_from_md("MERV - XMEV - ZZ01 - 24hs", {"LA": {"price": 101.0}})
    assert store.get("MERV - XMEV - ZZ01 - 24hs").seq == s0 + 3
    assert store.get("MERV - XMEV - ZZ02 - 24hs").seq == s0 + 2          # el otro no se movió
    # el snapshot persistido/restaurado no bumpea la seq
    store.restore({"MERV - XMEV - ZZ03 - 24hs": {"symbol": "MERV - XMEV - ZZ03 - 24hs", "last": 5.0}})
    assert store.seq() == s0 + 3 and store.get("MERV - XMEV - ZZ03 - 24hs").seq == 0


def _seed(codes, k: float = 1.0):
    store = marketdata_store.get_store()
    ts = str(int(datetime.now(_TZ).timestamp() * 1000))
    for c in codes:
        px = (95.0 + (sum(map(ord, c)) * 7 % 900) / 10) * k
        store.update_from_md(syms.md_symbol(c, "24hs"), {
            "LA": {"price": px, "size": 1000, "date": ts}, "CL": {"price": px * 0.995},
            "BI": [{"price": px * 0.999, "size": 5000}], "OF": [{"price": px * 1.001, "size": 7000}],
            "EV": 2e7, "NV": 2e5})
    return ts


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.asyncio
async def test_http_tabla_y_delta_por_filas() -> None:
    from backend.main import app
    from backend.routes import curves as rc

    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    curve = "cer" if "cer" in cc else next(iter(cc))
    ts = _seed(cc[curve])
    rc._ROWS_CACHE.clear()
    store = marketdata_store.get_store()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        t = await ac.get("/mercado/table", params={"curve": curve})
        assert t.status_code == 200
        assert 'data-delta="/mercado/rows?curve=' in t.text and 'data-seq="' in t.text and 'data-order="' in t.text
        codes_tabla = re.findall(r'<tr data-code="([^"]+)"', t.text)
        assert len(codes_tabla) >= 3
        seq = int(re.search(r'data-seq="(\d+)"', t.text).group(1))
        order = re.search(r'data-order="([0-9a-f]+)"', t.text).group(1)
        assert seq <= store.seq() and len(order) == 12
        # sin cambios desde esa seq → cuerpo vacío, X-Rows 0, misma seq
        r0 = await ac.get("/mercado/rows", params={"curve": curve, "since": seq, "order": order})
        assert r0.status_code == 200 and r0.text.strip() == "" and r0.headers["x-rows"] == "0"
        assert int(r0.headers["x-seq"]) == seq and "x-full" not in r0.headers
        # un tick en UN bono → sólo las filas de ese símbolo (base + variante 'j')
        code = codes_tabla[0]
        sym = syms.md_symbol(code, "24hs")
        esperadas = [c for c in codes_tabla if syms.md_symbol(c, "24hs") == sym]
        snap = store.get(sym)
        store.update_from_md(sym, {"LA": {"price": snap.last * 1.01, "size": 5, "date": ts}})
        r1 = await ac.get("/mercado/rows", params={"curve": curve, "since": seq, "order": order})
        assert r1.status_code == 200 and "x-full" not in r1.headers
        assert int(r1.headers["x-rows"]) == len(esperadas) and r1.text.count("<tr ") == len(esperadas)
        for c in esperadas:
            assert f'data-code="{c}"' in r1.text
        assert "hx-get=\"/mercado/book/" in r1.text
        seq2 = int(r1.headers["x-seq"])
        assert seq2 > seq
        # con since = seq2 → nada más
        r2 = await ac.get("/mercado/rows", params={"curve": curve, "since": seq2, "order": order})
        assert r2.headers["x-rows"] == "0" and r2.text.strip() == ""
        # la fila del delta es IDÉNTICA a la de la tabla completa (misma macro)
        t2 = await ac.get("/mercado/table", params={"curve": curve})
        fila_tabla = re.search(rf'<tr data-code="{re.escape(code)}".*?</tr>', t2.text, re.S).group(0)
        fila_delta = re.search(rf'<tr data-code="{re.escape(code)}".*?</tr>', r1.text, re.S).group(0)
        assert _norm(fila_tabla) == _norm(fila_delta)
        # orden/conjunto distinto → X-Full con cuerpo vacío (el cliente hace el swap)
        rf = await ac.get("/mercado/rows", params={"curve": curve, "since": seq2, "order": "nope"})
        assert rf.headers.get("x-full") == "1" and rf.text == ""
        # paneles de acciones y fuente MAE → siempre swap completo
        for extra in ({"panel": "lideres"}, {"fuente": "mae"}):
            rx = await ac.get("/mercado/rows", params={"curve": curve, **extra})
            assert rx.headers.get("x-full") == "1"
        # leg no nativa (precio ÷ FX): manda todas las filas aunque no haya tick
        tl = await ac.get("/mercado/table", params={"curve": curve, "leg": "ARS"})
        ol = re.search(r'data-order="([0-9a-f]+)"', tl.text).group(1)
        sl = int(re.search(r'data-seq="(\d+)"', tl.text).group(1))
        rl = await ac.get("/mercado/rows", params={"curve": curve, "leg": "ARS", "since": sl, "order": ol})
        assert int(rl.headers["x-rows"]) == tl.text.count('<tr data-code="') and rl.text.count("<tr ") >= 3
        # fuente MAE: la tabla no ofrece delta (sin data-delta) → el contenedor swapea completo
        tm = await ac.get("/mercado/table", params={"curve": curve, "fuente": "mae"})
        assert tm.status_code == 200 and "data-delta=" not in tm.text
        # página: contenedor con data-delta-scope, sin md-update en el trigger de htmx
        page = await ac.get("/mercado")
        assert 'data-delta-scope' in page.text and 'hx-trigger="refresh, every 30s"' in page.text
        assert 'id="mercado-table"' in page.text
        js = await ac.get("/static/js/app.js")
        for frag in ("data-delta-scope", "table[data-delta]", "X-Full", "X-Seq", "__mercadoDelta", "replaceWith"):
            assert frag in js.text, frag


@pytest.mark.asyncio
async def test_rows_en_seq_single_flight_y_cache() -> None:
    """Un build por (params, seq): dos pedidos concurrentes con la misma seq
    comparten las filas; un tick invalida."""
    import asyncio

    from backend.routes import curves as rc

    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    curve = "cer" if "cer" in cc else next(iter(cc))
    _seed(cc[curve])
    rc._ROWS_CACHE.clear()
    llamadas = []
    orig = rc._rows_for

    async def espia(*a, **k):
        llamadas.append(1)
        return await orig(*a, **k)

    rc._rows_for = espia
    try:
        a, b = await asyncio.gather(rc._rows_en_seq(curve, "24hs", True, "native", "byma", "", 0),
                                    rc._rows_en_seq(curve, "24hs", True, "native", "byma", "", 0))
        assert a is b and len(llamadas) == 1 and a[0] == marketdata_store.get_store().seq()
        c = await rc._rows_en_seq(curve, "24hs", True, "native", "byma", "", 0)
        assert c is a and len(llamadas) == 1                                # cache por seq
        _seed(cc[curve][:1], 1.02)                                            # tick → seq nueva
        d = await rc._rows_en_seq(curve, "24hs", True, "native", "byma", "", 0)
        assert d is not a and len(llamadas) == 2 and d[3] == a[3]            # mismo orden → mismo hash
    finally:
        rc._rows_for = orig


@pytest.mark.asyncio
async def test_memo_de_filas_solo_rearma_el_simbolo_que_tickeo() -> None:
    """Un tick en UN bono re-arma sólo su fila (las demás salen del memo por
    seq del símbolo) y las filas devueltas son copias (mutarlas no contamina)."""
    from backend.routes import curves as rc

    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    curve = "cer" if "cer" in cc else next(iter(cc))
    _seed(cc[curve])
    rc._ROW_MEMO.clear()
    rc._ROWS_CACHE.clear()
    llamadas = []
    orig = rc._row_for_code

    def espia(code, *a, **k):
        llamadas.append(code)
        return orig(code, *a, **k)

    rc._row_for_code = espia
    try:
        rows1, _ = await rc._rows_for(curve, "24hs", True, "native", book=True)
        n_total = len(llamadas)
        assert n_total >= len(rows1) >= 3
        llamadas.clear()
        rows2, _ = await rc._rows_for(curve, "24hs", True, "native", book=True)   # nada cambió → 0 builds
        assert llamadas == [] and [r["code"] for r in rows2] == [r["code"] for r in rows1]
        assert rows2[0] is not rows1[0] and rows2[0] == {**rows1[0], **rows2[0]}   # copias iguales
        rows2[0]["last"] = -1.0                                                   # mutar no contamina
        code = rows1[0]["code"]
        _seed([code], 1.03)                                                       # tick en uno
        rows3, _ = await rc._rows_for(curve, "24hs", True, "native", book=True)
        assert set(llamadas) == {c for c in cc[curve] if syms.md_symbol(c, "24hs") == syms.md_symbol(code, "24hs")}
        r3 = next(r for r in rows3 if r["code"] == code)
        assert r3["last"] == pytest.approx(rows1[0]["last"] * 1.03) and r3["last"] != -1.0
        # leg no nativa: sin memo (todas las filas se arman siempre)
        llamadas.clear()
        await rc._rows_for(curve, "24hs", True, "ARS", book=True)
        assert len(llamadas) >= len(rows1)
    finally:
        rc._row_for_code = orig
