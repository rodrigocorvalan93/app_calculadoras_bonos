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
    assert "2026-05-28T15:30:00" in r.text


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
