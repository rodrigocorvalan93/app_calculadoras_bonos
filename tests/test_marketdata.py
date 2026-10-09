"""Offline tests for the live market-data plumbing.

The actual broker connection can't be exercised here (no creds, no
network to Primary). What we test:

  - MarketDataStore correctly decodes Primary's `marketData` envelopes
    (mixed dict / list-of-dict / scalar fields).
  - BYMA symbol helpers format the right ticker.
  - PrimaryWS boots gracefully when credentials are missing.
  - /market/diag and /market/snapshot/* return well-formed JSON when
    the store is empty.
"""
from __future__ import annotations

import pytest

from backend.services import marketdata_store as mds
from backend.services import primary_ws as pws
from backend.services import symbols as syms


# ── Store / decoder ──────────────────────────────────────────────────


def test_md_value_handles_dict_list_scalar() -> None:
    assert mds._md_value(None) is None
    assert mds._md_value({"price": 87.3, "size": 1000}, "price") == 87.3
    assert mds._md_value({"price": 87.3, "size": 1000}, "size") == 1000
    assert mds._md_value([{"price": 87.3}], "price") == 87.3
    assert mds._md_value([], "price") is None
    assert mds._md_value(150.5) == 150.5  # scalar
    assert mds._md_value("not a number") is None


def test_update_from_md_merges_book_and_trade() -> None:
    store = mds.MarketDataStore()
    snap = store.update_from_md(
        "MERV - XMEV - GD30 - 24hs",
        {
            "BI": [{"price": 69.95, "size": 5000}],
            "OF": [{"price": 70.05, "size": 3000}],
            "LA": {"price": 70.00, "size": 1500, "date": "2026-05-28T15:30:00"},
            "OP": 69.80,
            "HI": 70.20,
            "LO": 69.50,
            "CL": 70.10,
            "EV": 50_000_000,
            "TV": 142,
            "NV": 715_000,
        },
    )
    assert snap.bid == 69.95
    assert snap.offer == 70.05
    assert snap.last == 70.00
    assert snap.high == 70.20
    assert snap.volume == 50_000_000
    assert snap.trade_count == 142
    assert snap.last_ts == "2026-05-28T15:30:00"
    assert snap.vwap() == 50_000_000 / 715_000


def test_close_ts_from_list_form() -> None:
    """Regresión #38: CL como lista-de-dicts también debe actualizar close_ts
    (antes sólo se leía la fecha del caso dict → fecha de cierre vieja/blanca)."""
    store = mds.MarketDataStore()
    # forma dict (ya andaba)
    s1 = store.update_from_md("A", {"CL": {"price": 70.1, "date": "2026-05-27T17:00:00"}})
    assert s1.close == 70.1 and s1.close_ts == "2026-05-27T17:00:00"
    # forma lista-de-dicts (el bug)
    s2 = store.update_from_md("B", {"CL": [{"price": 99.5, "date": "2026-05-28T17:00:00"}]})
    assert s2.close == 99.5 and s2.close_ts == "2026-05-28T17:00:00"


def test_update_from_md_keeps_sticky_fields() -> None:
    """A second push that only carries a new LA shouldn't blow away BI/OF."""
    store = mds.MarketDataStore()
    store.update_from_md("S", {"BI": [{"price": 100, "size": 10}], "OF": [{"price": 101, "size": 5}]})
    store.update_from_md("S", {"LA": {"price": 100.5, "size": 1}})
    s = store.get("S")
    assert s.bid == 100
    assert s.offer == 101
    assert s.last == 100.5


def test_subscribe_payload_shape() -> None:
    import json

    raw = pws._subscribe_payload(["MERV - XMEV - GD30 - 24hs"])
    parsed = json.loads(raw)
    assert parsed["type"] == "smd"
    assert parsed["level"] == 1
    assert "BI" in parsed["entries"]
    # IV (Index Value): sin pedirlo, los índices (I.MERVAL) no mandan NADA.
    assert "IV" in parsed["entries"]
    # OI sólo va en los lotes de futuros (entries explícitos), no en el default.
    assert "OI" not in parsed["entries"]
    assert parsed["products"] == [{"symbol": "MERV - XMEV - GD30 - 24hs", "marketId": "ROFX"}]
    fut_raw = json.loads(pws._subscribe_payload(["DLR/AGO26M"], entries=pws.ENTRIES_FUT))
    assert "OI" in fut_raw["entries"] and "BI" in fut_raw["entries"]
    assert pws._is_futuro("DLR/AGO26M") and not pws._is_futuro("DLR/SPOT")


def test_oi_decodifica_interes_abierto() -> None:
    """OI (interés abierto, futuros): {'size': contratos}, escalar pelado, o
    {'price': …} según el gateway — las tres formas cargan open_interest."""
    store = mds.MarketDataStore()
    s = store.update_from_md("DLR/AGO26M", {"OI": {"size": 123_456.0}})
    assert s.open_interest == 123_456.0
    s = store.update_from_md("DLR/AGO26M", {"OI": 130_000.0})
    assert s.open_interest == 130_000.0
    s = store.update_from_md("DLR/AGO26M", {"OI": {"price": 140_000.0}})
    assert s.open_interest == 140_000.0
    # sticky: un tick sin OI no lo pisa
    s = store.update_from_md("DLR/AGO26M", {"LA": {"price": 1500.0}})
    assert s.open_interest == 140_000.0
    # el EV con forma {"price": …} (visto en ROFEX) también carga volume
    s = store.update_from_md("DLR/AGO26M", {"EV": {"price": 999.0}})
    assert s.volume == 999.0


@pytest.mark.asyncio
async def test_rechazo_con_oi_reintenta_sin_oi_antes_de_descartar() -> None:
    """Un ERROR single-symbol de un 'smd' con OI puede ser por el ENTRY y no
    por el símbolo: primero se reintenta con ENTRIES estándar; recién si vuelve
    a fallar sin OI se descarta. Un lote rechazado se reintenta de a uno con
    los MISMOS entries (los futuros conservan el OI)."""
    import asyncio
    import json

    client = pws.PrimaryWS("https://example.invalid/", store=mds.MarketDataStore())
    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    client._ws = FakeWS()
    # 1) single con OI rechazado → reintento sin OI, sin descartar
    client._recover_from_error(pws._subscribe_payload(["DLR/AGO26M"], entries=pws.ENTRIES_FUT))
    await asyncio.sleep(0.05)
    assert sent and sent[0]["entries"] == pws.ENTRIES
    assert "DLR/AGO26M" not in client._rejected
    # 2) vuelve a fallar ya sin OI → ahora sí es el símbolo: descartado
    client._recover_from_error(pws._subscribe_payload(["DLR/AGO26M"]))
    assert "DLR/AGO26M" in client._rejected
    # 3) lote de futuros rechazado → individual conservando ENTRIES_FUT
    sent.clear()
    client._recover_from_error(pws._subscribe_payload(["DLR/DIC26M", "DLR/ENE27M"],
                                                      entries=pws.ENTRIES_FUT))
    await asyncio.sleep(0.05)
    assert len(sent) == 2 and all(p["entries"] == pws.ENTRIES_FUT for p in sent)


def test_iv_de_indice_mapea_a_last() -> None:
    """Los índices publican IV (no LA): el store lo mapea a `last` — el shape
    real del feed, que era por qué el Merval no aparecía en el tape."""
    from backend.services.marketdata_store import MarketDataStore

    store = MarketDataStore()
    # dict con fecha (shape típico)
    s = store.update_from_md("MERV - XMEV - I.MERVAL",
                             {"IV": {"price": 2_501_234.5, "date": 1752585600000}})
    assert s.last == 2_501_234.5 and s.last_ts == "1752585600000"
    # escalar pelado (Primary es inconsistente entre entries)
    s = store.update_from_md("MERV - XMEV - I.MERVAL", {"IV": 2_502_000.0})
    assert s.last == 2_502_000.0
    # sin IV → no toca el last existente (sticky)
    s = store.update_from_md("MERV - XMEV - I.MERVAL", {"CL": {"price": 2_450_000.0}})
    assert s.last == 2_502_000.0 and s.close == 2_450_000.0


# ── Symbol helpers ───────────────────────────────────────────────────


def test_symbol_strips_calc_suffix() -> None:
    # Sufijos de calc (minúscula) → se strippean
    assert syms.calc_to_md_code("TX26j") == "TX26"
    assert syms.calc_to_md_code("TXMJ9v") == "TXMJ9"
    assert syms.calc_to_md_code("GD30") == "GD30"
    # Regresión #12: un ticker REAL terminado en V/J MAYÚSCULA no debe mutilarse.
    # SUPV (Grupo Supervielle) se convertía en "SUP" con el strip case-insensitive
    # y nunca levantaba precio.
    assert syms.calc_to_md_code("SUPV") == "SUPV"
    assert syms.md_symbol("SUPV", "24hs") == "MERV - XMEV - SUPV - 24hs"


def test_symbol_builds_byma_ticker() -> None:
    assert syms.md_symbol("GD30", "24hs") == "MERV - XMEV - GD30 - 24hs"
    assert syms.md_symbol("TXMJ9v", "CI") == "MERV - XMEV - TXMJ9 - CI"


# ── WS client offline behaviour ──────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_login_returns_false_without_creds() -> None:
    client = pws.PrimaryWS("https://example.invalid/", store=mds.MarketDataStore())
    ok = await client.login("", "")
    assert ok is False
    assert not client.authenticated


@pytest.mark.asyncio
async def test_ws_start_without_creds_is_inert() -> None:
    """Reader loop should idle (waiting for cookies) without crashing."""
    import asyncio

    store = mds.MarketDataStore()
    client = pws.PrimaryWS("https://example.invalid/", store=store)
    await client.start()
    # Give the loop a tick to enter the "no creds" branch.
    await asyncio.sleep(0.05)
    stats = client.stats()
    assert stats["connected"] is False
    assert stats["messages"] == 0
    await client.stop()


def test_feed_alive_distingue_caido_de_quieto() -> None:
    """`feed_alive` = conectado Y con un Md reciente. Es la señal honesta que el
    dot/healthz deben usar en vez de `authenticated` (cookies), que sigue True con
    el feed muerto."""
    import time

    client = pws.PrimaryWS("https://example.invalid/", store=mds.MarketDataStore())
    # sin conexión ni mensajes → feed muerto
    assert client.feed_alive is False
    s = client.stats()
    assert s["feed_alive"] is False and s["stale_seconds"] is None
    # conectado y con un Md recién llegado → vivo
    client._connected = True
    client._stats["last_message_at"] = time.time()
    assert client.feed_alive is True
    assert client.stats()["stale_seconds"] is not None
    # conectado pero sin datos hace rato (> STALE_AFTER) → stale, no "vivo"
    client._stats["last_message_at"] = time.time() - (pws.PrimaryWS.STALE_AFTER + 10)
    assert client.feed_alive is False
    # tener cookies (authenticated) NO implica que el feed esté vivo
    client._cookies = object()
    assert client.authenticated is True and client.feed_alive is False


# ── /market endpoints ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_market_diag_returns_stats() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/market/diag")
    assert r.status_code == 200
    payload = r.json()
    assert "ws" in payload
    assert "store" in payload
    assert "authenticated" in payload


@pytest.mark.asyncio
async def test_market_snapshot_handles_empty_store() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/market/snapshot/GD30")
    assert r.status_code == 200
    payload = r.json()
    assert payload["code"] == "GD30"
    assert payload["symbol"] == "MERV - XMEV - GD30 - 24hs"
    # No live data in the test process — snapshot is None and that's fine.
    assert payload["snapshot"] is None or isinstance(payload["snapshot"], dict)


# ── YAS market card ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_yas_market_card_empty_store() -> None:
    """With no store data the card renders dashes but doesn't crash."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/yas/market?code=GD30&plazo=24hs")
    assert r.status_code == 200
    assert "MERV - XMEV - GD30 - 24hs" in r.text
    assert "sin data en el store" in r.text


@pytest.mark.asyncio
async def test_yas_market_card_with_injected_snapshot() -> None:
    """Inject a snapshot into the singleton store and verify the partial picks it up."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds_

    store = mds_.get_store()
    store.update_from_md(
        "MERV - XMEV - GD30 - 24hs",
        {
            "BI": [{"price": 69.95, "size": 5000}],
            "OF": [{"price": 70.05, "size": 3000}],
            "LA": {"price": 70.00, "size": 1500, "date": "2026-05-28T15:30:00"},
            "HI": 70.20,
            "LO": 69.50,
        },
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/yas/market?code=GD30&plazo=24hs")
    assert r.status_code == 200
    # es-AR formatting: comma decimal, period thousands.
    assert "69,9500" in r.text  # bid
    assert "70,0500" in r.text  # offer
    assert "70,0000" in r.text  # last
    # el timestamp del feed se muestra legible (ar_hora: no es de hoy → DD/MM
    # HH:MM) y el valor completo queda en el title — antes era el ISO/epoch crudo
    assert "last @ 28/05 15:30" in r.text and 'title="28/05 15:30:00"' in r.text


@pytest.mark.asyncio
async def test_yas_market_card_follows_selected_bond() -> None:
    """Regresión: el card de market data debe seguir al bono seleccionado, no
    quedar fijo al inicial (la URL no debe traer el code hardcodeado)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds_

    store = mds_.get_store()
    store.update_from_md("MERV - XMEV - GD30 - 24hs", {"LA": {"price": 70.00}})
    store.update_from_md("MERV - XMEV - AL30 - 24hs", {"LA": {"price": 71.50}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        page = await ac.get("/yas")
        rg = await ac.get("/yas/market?code=GD30&plazo=24hs")
        ra = await ac.get("/yas/market?code=AL30&plazo=24hs")
    assert page.status_code == 200
    assert 'hx-get="/yas/market"' in page.text                       # URL sin code fijo
    assert 'hx-include="[name=code], [name=plazo]"' in page.text     # lo toma del form
    assert "MERV - XMEV - GD30 - 24hs" in rg.text and "70,0000" in rg.text
    assert "MERV - XMEV - AL30 - 24hs" in ra.text and "71,5000" in ra.text
    assert "AL30" not in rg.text                                     # cada card, su bono


# ── Curves table with live store ─────────────────────────────────────


@pytest.mark.asyncio
async def test_curves_table_with_live_store() -> None:
    """A code with a snapshot must show its last + a computed TIREA in the row."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds_, symbols as syms_

    bond_universe.ensure_loaded()
    # Pick a non-empty curve, then pick its first code with a known price ceiling.
    table = curves.build_curve_codes()
    chosen_curve = None
    chosen_code = None
    for c in curves.list_curves():
        codes = table.get(c.key) or []
        if codes:
            chosen_curve = c.key
            chosen_code = codes[0]
            break
    assert chosen_curve and chosen_code

    store = mds_.get_store()
    symbol = syms_.md_symbol(chosen_code, "24hs")
    store.update_from_md(symbol, {"LA": {"price": 87.30, "size": 1000}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # only_quoting defaults True → table filters to the bond we fed.
        r = await ac.get(f"/curves/table?curve={chosen_curve}&plazo=24hs")
    assert r.status_code == 200
    # Badge reports the cotización count and the live price renders.
    assert "con cotización" in r.text
    assert "87,30" in r.text          # precio last se muestra con 2 decimales (es-AR)


@pytest.mark.asyncio
async def test_curves_only_quoting_toggle_off_shows_universe() -> None:
    """With only_quoting=false the full static universe renders, even
    rows with no live quote."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves

    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    # Use a curve that's unlikely to have any injected snapshot.
    target = None
    for c in curves.list_curves():
        if len(table.get(c.key) or []) >= 5:
            target = c.key
            break
    assert target

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        on = await ac.get(f"/curves/table?curve={target}&plazo=CI&only_quoting=true")
        off = await ac.get(f"/curves/table?curve={target}&plazo=CI&only_quoting=false")
    assert on.status_code == 200 and off.status_code == 200
    # With the toggle off we render the full universe → more <tr> rows
    # (or equal, if the store happens to quote everything — never fewer).
    assert off.text.count("/yas?code=") >= on.text.count("/yas?code=")


def test_metrics_for_market_price_cached() -> None:
    """Second call with same bucket must hit the cache (object identity)."""
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    if "TXMJ9v" not in bond_universe.all_codes():
        pytest.skip("TXMJ9v missing")

    a = pricing.metrics_for_market_price("TXMJ9v", 87.30)
    b = pricing.metrics_for_market_price("TXMJ9v", 87.30)
    assert a is b, "TTL cache should return the same dict identity for the same bucket"


def test_metrics_for_market_price_handles_garbage() -> None:
    from backend.services import pricing

    assert pricing.metrics_for_market_price("TXMJ9v", None) is None
    assert pricing.metrics_for_market_price("TXMJ9v", "foo") is None
    assert pricing.metrics_for_market_price("TXMJ9v", -5) is None


# ── Performance gate: a curve with many live prices must stay sub-50ms ──


@pytest.mark.asyncio
async def test_curve_table_latency_with_live_prices() -> None:
    """Inject prices for every code in the widest curve and verify the
    HTTP /curves/table call (with TIREA computed per row) clears the
    50 ms p95 target on the warm path.
    """
    import statistics
    import time

    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds_, symbols as syms_

    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    chosen = max(table.items(), key=lambda kv: len(kv[1]))
    curve_key, codes = chosen
    if len(codes) < 20:
        pytest.skip("No wide curve to stress the row pipeline")

    store = mds_.get_store()
    # Plausible price per bond — same number is fine, we just need the
    # store entries to exist so the row picks the metrics path.
    for code in codes:
        store.update_from_md(
            syms_.md_symbol(code, "24hs"),
            {"LA": {"price": 90.0, "size": 100}},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Two warm-up calls so the TTL cache + error-bucket entries are
        # fully populated (matured bonds throw on first touch; we want
        # those cached too before measuring).
        await ac.get(f"/curves/table?curve={curve_key}&plazo=24hs")
        await ac.get(f"/curves/table?curve={curve_key}&plazo=24hs")

        times = []
        for _ in range(30):
            t0 = time.perf_counter()
            r = await ac.get(f"/curves/table?curve={curve_key}&plazo=24hs")
            times.append(time.perf_counter() - t0)
            assert r.status_code == 200

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    # CLAUDE.md target: < 50 ms p95 on the warm-cache path.
    assert p95 < 0.050, f"{curve_key} ({len(codes)} bonds) p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms"


def test_orden_anormal_en_book() -> None:
    """Detector de mano oficial: la señal es el TAMAÑO ABSOLUTO por punta
    (bids más sensibles que offers) + de-ruidador de liquidez (≥ratio del NV
    del día; sin NV alcanza el piso). El ratio solo NO dispara."""
    store = mds.MarketDataStore()
    BID, OFF, RATIO = 5e9, 15e9, 0.10

    # caso real: 25.000M VN en el 3er nivel con 35.000M operados → dispara
    s = store.update_from_md("LETRA", {
        "BI": [{"price": 124.62, "size": 16e6}, {"price": 124.58, "size": 360e3},
               {"price": 124.573, "size": 25e9}],
        "NV": {"size": 35e9},
    })
    a = mds.orden_anormal(s, BID, OFF, RATIO)
    assert a is not None and a["lado"] == "compra" and a["size"] == 25e9
    assert a["price"] == 124.573 and abs(a["pct_vol"] - 25 / 35) < 1e-9

    # el caso RUIDOSO reportado: 1.000M sobre 125M operados (ratio 8×) pero la
    # orden es chica en absoluto → NO dispara
    s2 = store.update_from_md("ILIQUIDA", {"BI": [{"price": 100.0, "size": 1e9}],
                                           "NV": {"size": 125e6}})
    assert mds.orden_anormal(s2, BID, OFF, RATIO) is None

    # asimetría: 10.000M en la VENTA no alcanza (piso 15.000M) — el mismo
    # tamaño en la COMPRA sí (piso 5.000M)
    s3 = store.update_from_md("ASIM", {"OF": [{"price": 101.0, "size": 10e9}],
                                       "NV": {"size": 30e9}})
    assert mds.orden_anormal(s3, BID, OFF, RATIO) is None
    s3 = store.update_from_md("ASIM", {"BI": [{"price": 99.0, "size": 10e9}]})
    a3 = mds.orden_anormal(s3, BID, OFF, RATIO)
    assert a3 is not None and a3["lado"] == "compra"

    # mega-líquido: 6.000M de bid con 200.000M operados (3%) → NO (ratio)
    s4 = store.update_from_md("MEGA", {"BI": [{"price": 98.0, "size": 6e9}],
                                       "NV": {"size": 200e9}})
    assert mds.orden_anormal(s4, BID, OFF, RATIO) is None

    # pre-apertura (sin NV): alcanza el piso de la punta
    s5 = store.update_from_md("PREAPERTURA", {"OF": [{"price": 99.0, "size": 16e9}]})
    a5 = mds.orden_anormal(s5, BID, OFF, RATIO)
    assert a5 is not None and a5["lado"] == "venta" and a5["pct_vol"] is None
    assert mds.orden_anormal(None, BID, OFF, RATIO) is None


@pytest.mark.asyncio
async def test_anom_badge_en_curvas() -> None:
    """El ⚠ aparece al lado del ticker cuando hay una orden anormal en el book."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves

    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    curve_key, codes = next((k, v) for k, v in table.items() if v)
    code = codes[0]
    store = mds.get_store()
    store.update_from_md(syms.md_symbol(code, "24hs"), {
        "LA": {"price": 90.0, "size": 100},
        "BI": [{"price": 89.9, "size": 1e6}, {"price": 89.5, "size": 30e9}],
        "NV": {"size": 40e9},
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/curves/table?curve={curve_key}&plazo=24hs")
        m = await ac.get(f"/mercado?book={code}&plazo=24hs")
    assert r.status_code == 200
    assert "anom-badge" in r.text and "Orden ANORMAL" in r.text
    # el ⚠ es un link al libro de la especie en Mercado…
    assert f"/mercado?book={code}" in r.text
    # …y /mercado?book=X auto-carga el libro al abrir (hx-trigger load)
    assert m.status_code == 200 and f"/mercado/book/{code}" in m.text and 'hx-trigger="load"' in m.text


# ── Cache local de símbolos rechazados (por host, con TTL) ───────────


@pytest.mark.asyncio
async def test_rechazados_persisten_por_host_con_ttl(tmp_path, monkeypatch) -> None:
    """Un símbolo que el broker rechazó queda en un JSON local: el próximo
    cliente del MISMO host arranca sin pedirlo (el primer subscribe sale sin la
    tormenta de lotes rechazados + reintentos de a uno), otro host no lo hereda
    (y al guardar no le pisa lo suyo), una entrada vencida (> REJECTED_TTL_DAYS)
    se vuelve a probar y PRIMARY_REJECTED_CACHE=0 apaga todo."""
    import json
    from datetime import date, timedelta

    path = tmp_path / "rechazados.json"
    monkeypatch.setenv("PRIMARY_REJECTED_CACHE", str(path))
    z1, z2 = "MERV - XMEV - ZZZ1 - CI", "MERV - XMEV - ZZZ2 - 24hs"
    client = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert not client._rejected
    client._recover_from_error(pws._subscribe_payload([z1]))
    client._recover_from_error(pws._subscribe_payload([z2]))
    assert client._rejected == {z1, z2}
    assert not path.exists()                       # escritura diferida (una por tormenta)
    await client.stop()                            # el stop la fuerza
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["broker-a.invalid"]) == {z1, z2}
    assert all(f == date.today().isoformat() for f in data["broker-a.invalid"].values())

    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    # mismo host → arranca con el cache y el subscribe los saltea
    c2 = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert c2._rejected == {z1, z2} and c2.stats()["rejected"] == 2
    await c2._send_in_chunks(FakeWS(), ["MERV - XMEV - GD30 - 24hs", z1, z2])
    assert [p["symbol"] for m in sent for p in m["products"]] == ["MERV - XMEV - GD30 - 24hs"]
    # otro host no hereda, y al guardar conserva lo del primero
    c3 = pws.PrimaryWS("https://broker-b.invalid/", store=mds.MarketDataStore())
    assert not c3._rejected
    c3._recover_from_error(pws._subscribe_payload(["MERV - XMEV - QQQ - CI"]))
    await c3.stop()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["broker-a.invalid"]) == {z1, z2}
    assert set(data["broker-b.invalid"]) == {"MERV - XMEV - QQQ - CI"}
    # vencida → se vuelve a probar
    data["broker-a.invalid"][z1] = (date.today() - timedelta(days=pws.REJECTED_TTL_DAYS + 1)).isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")
    c4 = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert c4._rejected == {z2}
    # archivo roto → arranca vacío, sin tirar
    path.write_text("{no es json", encoding="utf-8")
    assert not pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())._rejected
    # apagado
    monkeypatch.setenv("PRIMARY_REJECTED_CACHE", "0")
    path.write_text(json.dumps(data), encoding="utf-8")
    c5 = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert not c5._rejected
    c5._recover_from_error(pws._subscribe_payload([z1]))
    await c5.stop()
    assert json.loads(path.read_text(encoding="utf-8")) == data


@pytest.mark.asyncio
async def test_plazos_de_caucion_rechazados_se_reprueban_y_no_van_al_cache(tmp_path, monkeypatch) -> None:
    """09/10/2026 (viernes, lunes feriado): la tira de Tasas mostraba 1D–7D
    "hoy no hay" y sólo 14D/21D vivos mientras otra plataforma veía el 4D
    operando 912.000 M. Los plazos de caución existen POR DÍA (el 4D sólo
    cuando hoy+4 es hábil): el broker rechazó el 4D el martes, el rechazo fue
    al cache local por 7 días y el viernes — su día — nunca se suscribió.
    Exactamente los plazos que fueron inválidos algún día de la semana (1D–7D,
    el 7D por caer en el feriado) quedaban mudos; 14D/21D nunca lo son.
    Ahora: un plazo de caución rechazado no va al cache ni a `_rejected`, se
    suscribe de a uno, tiene un cooldown y se reprueba; al cambiar el día se
    piden todos de nuevo; un rechazo persistente vencido también se reprueba
    con el proceso arriba."""
    import json
    from datetime import date, datetime, timedelta

    from backend.locale_ar import TZ_BA

    path = tmp_path / "rechazados.json"
    monkeypatch.setenv("PRIMARY_REJECTED_CACHE", str(path))
    c4d, c1d = "MERV - XMEV - PESOS - 4D", "MERV - XMEV - DOLAR - 1D"
    bono, zzz = "MERV - XMEV - GD30 - 24hs", "MERV - XMEV - ZZZ - CI"
    hoy = date.today().isoformat()
    # un cache viejo con plazos de caución adentro NO los muda
    path.write_text(json.dumps({"broker-a.invalid": {c4d: hoy, zzz: hoy}}), encoding="utf-8")
    client = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert c4d not in client._rejected and zzz in client._rejected

    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append([p["symbol"] for p in json.loads(raw)["products"]])

    fixed = datetime(2026, 10, 9, 11, 0, tzinfo=TZ_BA)
    client._dia_diario = fixed.date()
    client._subscriptions.update([c4d, c1d, bono, zzz])
    client._connected, client._ws = True, FakeWS()
    await client._send_in_chunks(client._ws, [c4d, c1d, bono, zzz])
    assert sent == [[bono], [c1d], [c4d]]            # bono en lote, cauciones de a uno, zzz rechazado
    # el broker rechaza el 4D (hoy no hay rueda de ese plazo): cooldown, nada al cache
    client._recover_from_error(pws._subscribe_payload([c4d]))
    assert c4d not in client._rejected and c4d in client._rechazo_diario
    assert client.stats()["rechazados_hoy"] == [c4d] and client.stats()["rejected"] == 1
    sent.clear()
    await client._send_in_chunks(client._ws, [c4d, c1d])
    assert sent == [[c1d]]                            # en cooldown no se vuelve a pedir
    # reprobar: todavía en cooldown → nada; pasado el cooldown → se pide de nuevo
    assert await client.reprobar_pendientes(now_fn=lambda: fixed) == []
    client._rechazo_diario[c4d] -= pws.REPROBAR_DIARIO_S
    sent.clear()
    assert await client.reprobar_pendientes(now_fn=lambda: fixed) == [c4d]
    assert sent == [[c4d]] and c4d not in client._rechazo_diario
    # de noche no se reprueba (se vuelve a probar al conectar o a las 7)
    client._recover_from_error(pws._subscribe_payload([c4d]))
    client._rechazo_diario[c4d] -= pws.REPROBAR_DIARIO_S
    sent.clear()
    assert await client.reprobar_pendientes(now_fn=lambda: fixed.replace(hour=2)) == []
    assert sent == []
    # cambió el día: TODOS los plazos se piden de nuevo en la primera pasada en ventana
    manana = fixed + timedelta(days=1)
    assert sorted(await client.reprobar_pendientes(now_fn=lambda: manana)) == [c1d, c4d]
    assert sorted(sent) == [[c1d], [c4d]] and not client._rechazo_diario
    assert await client.reprobar_pendientes(now_fn=lambda: manana) == []        # una sola vez
    # desconectado: sólo contabilidad, no manda nada
    client._connected = False
    client._recover_from_error(pws._subscribe_payload([c4d]))
    client._rechazo_diario[c4d] -= pws.REPROBAR_DIARIO_S
    assert await client.reprobar_pendientes(now_fn=lambda: manana) == []
    client._connected = True
    # un rechazo persistente VENCIDO se reprueba con el proceso arriba (antes: sólo al
    # reiniciar); el 4D que quedó pendiente mientras estaba desconectado sale en la misma pasada
    client._rejected_fecha[zzz] = (date.today() - timedelta(days=pws.REJECTED_TTL_DAYS + 1)).isoformat()
    sent.clear()
    assert sorted(await client.reprobar_pendientes(now_fn=lambda: manana)) == [c4d, zzz]
    assert sorted(sent) == [[c4d], [zzz]]
    assert zzz not in client._rejected and zzz not in client._rejected_fecha
    # el cache en disco nunca lleva plazos de caución
    client._recover_from_error(pws._subscribe_payload([c4d]))
    client._recover_from_error(pws._subscribe_payload(["MERV - XMEV - QQQ - CI"]))
    await client.stop()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["broker-a.invalid"]) == {"MERV - XMEV - QQQ - CI"}
    assert pws._es_diario(c4d) and pws._es_diario("MERV - XMEV - DOLAR - 120D")
    assert not pws._es_diario(bono) and not pws._es_diario("MERV - XMEV - PESOS - 4D - CI")


@pytest.mark.asyncio
async def test_tormenta_de_rechazos_no_se_persiste_y_se_reprueba(tmp_path, monkeypatch) -> None:
    """09/10/2026: una cuenta en LBO quedó con 2717 de 2903 símbolos en el
    cache de rechazados (una tormenta: sesión / permisos de market data, no
    símbolos inválidos) → cada reconexión suscribía 186 y el feed mostraba
    precios viejos durante una semana. Ahora: más de la mitad del universo
    rechazado = tormenta → se corta la recuperación de a uno, el cache del host
    NO se guarda (queda vacío), un cache que ya viene así se descarta al
    conectar, el cambio de día vuelve a pedir todo y `olvidar_rechazados`
    (botón Reprobar de /conexion) lo hace al toque."""
    import json
    from datetime import date, datetime, timedelta

    from backend.locale_ar import TZ_BA

    path = tmp_path / "rechazados.json"
    monkeypatch.setenv("PRIMARY_REJECTED_CACHE", str(path))
    universo = [f"MERV - XMEV - S{i} - 24hs" for i in range(1000)]
    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append([p["symbol"] for p in json.loads(raw)["products"]])

    client = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    client._subscriptions.update(universo)
    client._connected, client._ws = True, FakeWS()
    # 400 rechazos de a uno (> 300 pero < 50 %): todavía símbolos inválidos normales
    for s in universo[:400]:
        client._recover_from_error(pws._subscribe_payload([s]))
    assert not client._tormenta and len(client._rejected) == 400
    # pasa la mitad del universo → tormenta: la recuperación de a uno se corta
    for s in universo[400:600]:
        client._recover_from_error(pws._subscribe_payload([s]))
    assert client._tormenta and client.stats()["tormenta"] is True
    sent.clear()
    await client._resubscribe_individually(universo[600:610], None)
    assert sent == []
    # el cache del host queda VACÍO (nada de persistir media universo)
    await client._flush_rechazados()
    assert json.loads(path.read_text(encoding="utf-8"))["broker-a.invalid"] == {}
    # día nuevo en ventana: se olvida todo y se pide el universo entero
    manana = datetime.now(TZ_BA).replace(hour=11, minute=0) + timedelta(days=1)
    client._dia_diario = date.today()
    sent.clear()
    assert len(await client.reprobar_pendientes(now_fn=lambda: manana)) == 1000
    assert not client._tormenta and not client._rejected and sum(len(m) for m in sent) == 1000
    # un cache que YA viene con tormenta de otra sesión se descarta al conectar
    path.write_text(json.dumps({"broker-a.invalid": {s: date.today().isoformat() for s in universo[:800]}}),
                    encoding="utf-8")
    c2 = pws.PrimaryWS("https://broker-a.invalid/", store=mds.MarketDataStore())
    assert len(c2._rejected) == 800
    c2._subscriptions.update(universo)
    assert c2._cache_es_tormenta()
    c2._subscriptions.clear()
    c2._subscriptions.update(universo[:1200])               # con 500 de 1000 → no (<= 50 %)
    c2._rejected = set(universo[:500]); c2._rejected_fecha = {s: "2026-10-06" for s in c2._rejected}
    assert not c2._cache_es_tormenta()
    # Reprobar: olvida memoria + disco y resuscribe todo por el WS vivo
    c2._rejected = set(universo[:800]); c2._rejected_fecha = {s: "2026-10-06" for s in c2._rejected}
    c2._connected, c2._ws = True, FakeWS()
    sent.clear()
    assert await c2.olvidar_rechazados() == 800
    assert not c2._rejected and sum(len(m) for m in sent) == 1000
    assert json.loads(path.read_text(encoding="utf-8"))["broker-a.invalid"] == {}
    await c2.stop()
