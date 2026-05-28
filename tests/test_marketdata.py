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
    assert parsed["products"] == [{"symbol": "MERV - XMEV - GD30 - 24hs", "marketId": "ROFX"}]


# ── Symbol helpers ───────────────────────────────────────────────────


def test_symbol_strips_calc_suffix() -> None:
    assert syms.calc_to_md_code("TX26j") == "TX26"
    assert syms.calc_to_md_code("TXMJ9v") == "TXMJ9"
    assert syms.calc_to_md_code("GD30") == "GD30"


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
