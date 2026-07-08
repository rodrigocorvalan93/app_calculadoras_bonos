"""Motor live: SSE de /market/events + persistencia del store entre reinicios."""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.services import marketdata_store as mds
from backend.services import store_persist


def _seed(sym: str, last: float = 101.5, close: float = 100.0) -> None:
    mds.get_store().update_from_md(sym, {
        "LA": {"price": last, "date": "1751833623000"},
        "CL": {"price": close},
    })


# ── store persist ──────────────────────────────────────────────────────────
def test_snapshot_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MARKET_SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    _seed("MERV - XMEV - TEST1 - 24hs", last=99.9, close=98.7)
    assert store_persist.save() is True

    store = mds.get_store()
    seq_before = store.seq()
    store._data.pop("MERV - XMEV - TEST1 - 24hs")      # simula un reinicio
    assert store_persist.load() >= 1
    snap = store.get("MERV - XMEV - TEST1 - 24hs")
    assert snap is not None and snap.last == 99.9 and snap.close == 98.7
    assert snap.last_ts == "1751833623000"
    # el restore NO es un tick: la seq no avanza (la UI no flashea).
    assert store.seq() == seq_before


def test_snapshot_restore_does_not_clobber_newer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MARKET_SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    sym = "MERV - XMEV - TEST2 - 24hs"
    _seed(sym, last=100.0)
    assert store_persist.save() is True
    _seed(sym, last=111.1)                              # el feed vivo llegó después
    assert store_persist.load() == 0 or mds.get_store().get(sym).last == 111.1
    assert mds.get_store().get(sym).last == 111.1


def test_snapshot_too_old_is_discarded(tmp_path, monkeypatch) -> None:
    p = tmp_path / "snap.json"
    monkeypatch.setenv("MARKET_SNAPSHOT_PATH", str(p))
    p.write_text(json.dumps({
        "saved_at": 1.0,                                # 1970 → viejísimo
        "symbols": {"MERV - XMEV - VIEJO - 24hs": {"symbol": "x", "last": 1.0}},
    }), encoding="utf-8")
    assert store_persist.load() == 0
    assert mds.get_store().get("MERV - XMEV - VIEJO - 24hs") is None


def test_snapshot_empty_store_never_overwrites(tmp_path, monkeypatch) -> None:
    p = tmp_path / "snap.json"
    monkeypatch.setenv("MARKET_SNAPSHOT_PATH", str(p))
    _seed("MERV - XMEV - TEST3 - 24hs")
    assert store_persist.save() is True
    good = p.read_text(encoding="utf-8")
    mds.get_store()._data.clear()                       # store vacío (boot sin feed)
    assert store_persist.save() is False                # no pisa el snapshot bueno
    assert p.read_text(encoding="utf-8") == good


# ── SSE ────────────────────────────────────────────────────────────────────
# El stream es infinito, así que NO se testea vía AsyncClient (cerrar el
# stream con ASGITransport espera a que el generador termine → cuelga).
# Iteramos el generador del endpoint directamente y lo cerramos nosotros.
@pytest.mark.asyncio
async def test_sse_emits_baseline_and_tick() -> None:
    from backend.routes.market import events

    resp = await events()
    assert resp.media_type == "text/event-stream"
    assert resp.headers.get("x-accel-buffering") == "no"

    gen = resp.body_iterator

    async def next_data() -> int:
        while True:
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
            for line in str(chunk).splitlines():
                if line.startswith("data: "):
                    return int(line[6:])

    try:
        base = await next_data()                        # baseline inmediato al conectar
        _seed("MERV - XMEV - SSE1 - 24hs")               # tick → evento en ≤ ~250 ms
        nxt = await next_data()
        assert nxt > base
    finally:
        await gen.aclose()


def test_sse_gzip_bypass_registered() -> None:
    # El wrapper anti-gzip del SSE tiene que estar en la cadena de middlewares
    # (si gzip envolviera el stream, los eventos quedarían buffereados).
    from backend.main import app

    names = [getattr(m.cls, "__name__", "") for m in app.user_middleware]
    assert "_SSESinGzip" in names
