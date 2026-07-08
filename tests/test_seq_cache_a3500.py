"""Cache de render por seq + A3500 oficial visible con fecha.

- seq_cached: N clientes del mismo panel comparten UN render por tick; un
  tick real (seq avanza) invalida al instante, el TTL acota las fuentes que
  no pasan por el store.
- A3500: el riel y la ficha Oficial muestran el último A3500 PUBLICADO con
  su fecha (aunque el intradía venga de SIOPEL), y el warmup decide cuándo
  reintentar el refresh vespertino (ventana 16-19 h BA, días hábiles).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import marketdata_store as mds
from backend.services.warmup import a3500_refresh_due

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _tick(sym: str = "MERV - XMEV - CACHE1 - 24hs") -> None:
    mds.get_store().update_from_md(sym, {"LA": {"price": 100.0}})


# ── seq_cached ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seq_cache_comparte_render_e_invalida_por_tick() -> None:
    async with _client() as ac:
        _tick()                                          # seq propia para este test
        r1 = await ac.get("/dolares/rail")
        assert r1.status_code == 200
        assert r1.headers.get("x-seq-cache") is None     # primer render: miss
        r2 = await ac.get("/dolares/rail")
        assert r2.status_code == 200
        assert r2.headers.get("x-seq-cache") == "hit"    # mismo seq+ttl: compartido
        assert r2.text == r1.text                        # byte a byte el mismo HTML

        _tick()                                          # tick real → seq avanza
        r3 = await ac.get("/dolares/rail")
        assert r3.headers.get("x-seq-cache") is None     # invalidado al instante


@pytest.mark.asyncio
async def test_seq_cache_distingue_query() -> None:
    async with _client() as ac:
        _tick()
        await ac.get("/dolares/rail?plazo=24hs")
        r = await ac.get("/dolares/rail?plazo=CI")       # otra query: no comparte
        assert r.headers.get("x-seq-cache") is None
        r = await ac.get("/dolares/rail?plazo=CI")
        assert r.headers.get("x-seq-cache") == "hit"


# ── A3500 visible ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_rail_muestra_a3500_con_fecha() -> None:
    async with _client() as ac:
        _tick()
        r = await ac.get("/dolares/rail")
    assert r.status_code == 200
    assert "A3500 · BCRA" in r.text
    # la serie del repo está cargada → valor + "al <fecha>"
    assert "al 20" in r.text or "—" in r.text


@pytest.mark.asyncio
async def test_ficha_oficial_muestra_a3500() -> None:
    async with _client() as ac:
        _tick()
        r = await ac.get("/dolares/oficial")
    assert r.status_code == 200
    assert "A3500 · BCRA" in r.text


# ── ventana vespertina del refresh ─────────────────────────────────────────
def _ba(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


def test_a3500_refresh_due_ventana_y_calendario() -> None:
    # miércoles 16:30, último publicado ayer → due
    assert a3500_refresh_due(_ba(2026, 7, 8, 16, 30), "2026-07-07") is True
    # ya publicado hoy → no
    assert a3500_refresh_due(_ba(2026, 7, 8, 16, 30), "2026-07-08") is False
    # antes de la ventana / después de la ventana → no
    assert a3500_refresh_due(_ba(2026, 7, 8, 15, 59), "2026-07-07") is False
    assert a3500_refresh_due(_ba(2026, 7, 8, 19, 0), "2026-07-07") is False
    # sábado → no
    assert a3500_refresh_due(_ba(2026, 7, 11, 16, 30), "2026-07-10") is False
    # sin serie cargada (None) dentro de la ventana → due (intenta traerla)
    assert a3500_refresh_due(_ba(2026, 7, 8, 17, 0), None) is True
