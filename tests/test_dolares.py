"""Tests for the Dólares monitor (backend/services/dolares.py + routes).

Covers:
  - `fx_rows` builds the implicit USD/USB table off the store with the
    bid/offer/last ratio convention (ARS leg ÷ cable/MEP leg).
  - `canje_rows` returns CCL/MEP − 1 with bid < last < offer ordering.
  - `official_fx` prefers a live `DLR/SPOT` (bidirectional) over the A3500
    crawl — so a spot trading below its close shows a NEGATIVE variation.
  - `puntas` + the FX operation math.
  - HTTP smoke for /dolares, /dolares/tables, /dolares/oficial,
    /dolares/rail, /dolares/calc.
"""
from __future__ import annotations

import pytest

from backend.services import bond_universe
from backend.services import dolares as dx
from backend.services import fx as fx_svc
from backend.services import marketdata_store as mds_
from backend.services import symbols as syms_


def _base() -> str:
    bond_universe.ensure_loaded()
    bases = fx_svc.fx_bases()
    if not bases:
        pytest.skip("no globales/bonares bases in especies.py")
    return bases[0]


def _seed(base: str, *, ars=74.55, c=0.0501, d=0.0506) -> None:
    store = mds_.get_store()
    store.update_from_md(syms_.md_symbol(base, "24hs"), {
        "BI": {"price": ars - 0.15}, "OF": {"price": ars + 0.25},
        "LA": {"price": ars}, "CL": {"price": ars - 0.35}})
    store.update_from_md(syms_.md_symbol(base + "C", "24hs"), {
        "BI": {"price": c - 0.0001}, "OF": {"price": c + 0.0001},
        "LA": {"price": c}, "CL": {"price": c}, "EV": {"size": 42_000_000}})
    store.update_from_md(syms_.md_symbol(base + "D", "24hs"), {
        "BI": {"price": d - 0.0001}, "OF": {"price": d + 0.0001},
        "LA": {"price": d}, "CL": {"price": d}, "EV": {"size": 12_000_000}})
    dx._cache.clear()


def test_fx_rows_ratio_convention() -> None:
    base = _base()
    _seed(base)
    rows = dx.fx_rows("USD", "24hs")
    row = next((r for r in rows if r["base"] == base), None)
    assert row is not None
    # last = ARS.last / cable.last ; bid = ARS.bid / cable.offer ; offer = ARS.offer / cable.bid
    assert row["last"] == pytest.approx(74.55 / 0.0501)
    assert row["bid"] == pytest.approx((74.55 - 0.15) / (0.0501 + 0.0001))
    assert row["offer"] == pytest.approx((74.55 + 0.25) / (0.0501 - 0.0001))
    assert row["bid"] < row["last"] < row["offer"]      # spread sane
    assert row["vol_usd_m"] == pytest.approx(42.0)      # cable-leg $ volume / 1e6


def test_canje_is_ccl_over_mep_with_bid_offer() -> None:
    base = _base()
    _seed(base)                       # d (MEP price) > c (cable price) → CCL > MEP → canje > 0
    rows = dx.canje_rows("24hs")
    row = next((r for r in rows if r["base"] == base), None)
    assert row is not None
    ccl, mep = 74.55 / 0.0501, 74.55 / 0.0506
    assert row["last"] == pytest.approx(ccl / mep - 1.0)
    assert row["last"] > 0                              # cable más caro que el MEP
    assert row["bid"] < row["last"] < row["offer"]      # canje tiene bid/offer, no sólo last


def test_official_spot_is_bidirectional() -> None:
    """DLR/SPOT por debajo de su close → variación NEGATIVA (la flecha baja).
    Esto arregla el A3500, que casi siempre marca para arriba."""
    store = mds_.get_store()
    store.update_from_md(dx.SPOT_SYMBOL, {"LA": {"price": 1405.0}, "CL": {"price": 1412.0}})
    dx._cache.clear()
    ofi = dx.official_fx()
    assert ofi["source"] == "DLR/SPOT"
    assert ofi["last"] == pytest.approx(1405.0)
    assert ofi["var_pct"] is not None and ofi["var_pct"] < 0


def test_puntas_and_operation_math() -> None:
    base = _base()
    _seed(base)
    p = dx.puntas(base, "USD", "24hs")
    assert p["last"] == pytest.approx(74.55 / 0.0501)
    # Comprar USD: pago bono ARS al offer, vendo pata cable al bid.
    px_a, px_u = p["ars_offer"], p["usd_bid"]
    usd_qty = 10_000.0
    vn = usd_qty * 100.0 / px_u
    ars = vn * px_a / 100.0
    assert ars > 0 and vn > 0
    # TC efectivo = ARS pagados / USD obtenidos = offer implícito.
    assert ars / usd_qty == pytest.approx(p["offer"])


def test_official_and_summary_are_robust() -> None:
    """El núcleo del monitor nunca debe tirar y siempre trae el set de claves
    completo (la página y el riel se cargan en todas las pestañas)."""
    ofi = dx.official_fx()
    for k in ("source", "last", "close", "var_pct", "bid", "offer", "volume", "date"):
        assert k in ofi, k
    s = dx.summary()
    for k in ("plazo", "usd", "usb", "canje", "brecha", "brecha_var_pp", "oficial"):
        assert k in s, k
    if s["canje"]:
        assert "var_pct" in s["canje"]        # el riel muestra la variación del canje


@pytest.mark.asyncio
async def test_siopel_official_variation_from_variacion_field() -> None:
    """La variación del oficial SIOPEL sale del campo 'variacion' de MAE (en %,
    0,28 = 0,28%), y el cierre se deriva (last/(1+var)). NO de precioCierreAnterior,
    que para el spot no es el cierre real (caso real: 1410,29 → daba 1,40%)."""
    import time as _t

    row = {"ticker": "UST$T", "segmento": "Mayorista", "plazo": "000",
           "precioUltimo": 1430.0, "variacion": 0.28,
           "precioCierreAnterior": 1410.29, "volumenOperado": 1.22e8}
    ust = dx._extract_ust([row])
    with dx._mae_lock:
        dx._mae_snap.update({"rows": [row], "ts": _t.time(), "ust": ust})
    dx._cache.clear()
    try:
        o = dx.official_fx()
        assert o["source"] == "SIOPEL"
        assert o["var_pct"] == pytest.approx(0.0028)                  # 0,28% = 28 bps
        assert o["close"] == pytest.approx(1430.0 / 1.0028, rel=1e-4)  # ~1426
        assert o["close"] != pytest.approx(1410.29)                   # NO precioCierreAnterior
    finally:
        with dx._mae_lock:
            dx._mae_snap.update({"rows": [], "ts": 0.0, "ust": None})
        dx._cache.clear()


def test_locale_filters_are_undefined_safe() -> None:
    """Un `{{ obj.campo_inexistente | ar_num }}` da Jinja Undefined; los filtros
    deben devolver '—' y NO lanzar UndefinedError (causó el 500 de /dolares)."""
    from jinja2 import Undefined

    from backend import locale_ar as L
    u = Undefined(name="precioCompra")
    for fn in (L.fmt_num, L.fmt_pct, L.fmt_pct_pp, L.fmt_int, L.fmt_money, L.fmt_hum, L.fmt_ts, L.fmt_date):
        assert fn(u) == L.DASH, fn.__name__


@pytest.mark.asyncio
async def test_dolares_survives_siopel_without_compra_venta() -> None:
    """Las filas reales de MAE no traen precioCompra/precioVenta → la pestaña
    Dólares no debe romper (regresión del 500 en dolares_oficial.html)."""
    import time as _t

    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    rows = [{"ticker": "UST$T", "segmento": "Mayorista", "plazo": "000",
             "precioUltimo": 1405.0, "variacion": -0.0049}]   # sin compra/venta/mín/máx
    with dx._mae_lock:
        dx._mae_snap.update({"rows": rows, "ts": _t.time(), "ust": dx._extract_ust(rows)})
    dx._cache.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            assert (await ac.get("/dolares")).status_code == 200
            assert (await ac.get("/dolares/oficial")).status_code == 200
    finally:
        with dx._mae_lock:
            dx._mae_snap.update({"rows": [], "ts": 0.0, "ust": None})
        dx._cache.clear()


@pytest.mark.asyncio
async def test_dolares_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    base = _base()
    _seed(base)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for url in ("/dolares", "/dolares/tables?plazo=ambos", "/dolares/oficial",
                    "/dolares/rail", f"/dolares/calc?base={base}&leg=USD&plazo=24hs&side=comprar&modo=usd&cantidad=10000"):
            r = await ac.get(url)
            assert r.status_code == 200, url
            assert r.text  # non-empty HTML


# ── Macro en el riel (TAMAR/BADLAR/CER/UVA/inflación, reusando el cache) ──────
_FAKE_HIST = {
    "loaded": True, "error": None, "path": "x",
    "series": {
        # TAMAR: aplicable = promedio de los últimos 5 = (30+30+30+30+35)/5 = 31,0
        "tamar": {"label": "TAMAR (%)", "points": [("2026-06-01", 30.0), ("2026-06-02", 30.0),
                                                    ("2026-06-03", 30.0), ("2026-06-04", 30.0), ("2026-06-05", 35.0)]},
        "badlar": {"label": "BADLAR (%)", "points": [("2026-06-05", 28.0)]},
        "CER": {"label": "CER", "points": [("2026-06-09", 787.02)]},
        "UVA": {"label": "UVA", "points": [("2026-06-09", 1985.84)]},
        "inflamom": {"label": "infl", "points": [("2026-04-30", 2.6)]},
    },
}


def test_macro_snapshot_reuses_cache() -> None:
    from backend.services import historico
    saved = historico._cache
    historico._cache = _FAKE_HIST
    try:
        by = {m["key"]: m for m in historico.macro_snapshot()}
        assert by["tamar"]["value"] == 35.0 and by["tamar"]["date"] == "05/06/2026"
        assert abs(by["tamar"]["aplicable"] - 31.0) < 1e-9 and by["tamar"]["fmt"] == "pct"
        assert by["cer"]["fmt"] == "num" and by["cer"]["value"] == 787.02
        assert "aplicable" not in by["cer"]                 # sólo TAMAR/BADLAR
        assert set(by) == {"tamar", "badlar", "cer", "uva", "inflamom"}
    finally:
        historico._cache = saved


@pytest.mark.asyncio
async def test_rail_renders_macro() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import historico

    saved = historico._cache
    historico._cache = _FAKE_HIST
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/dolares/rail")
        assert r.status_code == 200
        for tok in ("📈 Macro", "TAMAR", "BADLAR", "CER", "UVA",
                    "aplicable", "35,00%", "31,00%"):     # último y aplicable de TAMAR
            assert tok in r.text, tok
    finally:
        historico._cache = saved
