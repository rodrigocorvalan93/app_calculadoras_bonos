"""OMS — validaciones pre-trade, paper, token de un solo uso, kill-switch."""
from __future__ import annotations

import asyncio

import pytest

from backend.config import settings
from backend.services import oms


def test_validaciones_pretrade() -> None:
    assert settings.oms_live is False                       # SEGURIDAD: paper default
    assert oms.validate("", "buy", 1, 1, "C1", None)        # sin especie
    assert oms.validate("AL30", "buy", 0, 941.0, "C1", None)            # qty 0
    assert oms.validate("AL30", "buy", 100, 941.0, "", None)            # sin cuenta
    assert "banda" in oms.validate("AL30", "buy", 100, 941.0, "C1", 700.0)   # fat-finger
    assert "tope" in oms.validate("AL30", "buy", 1e12, 941.0, "C1", 941.0)   # notional
    assert oms.validate("AL30", "buy", 100_000, 941.0, "C1", 940.0) is None  # OK


def test_paper_y_token_un_solo_uso() -> None:
    payload = {"code": "AL30", "symbol": "X", "side": "buy", "qty": 100.0,
               "price": 941.0, "account": "C1", "plazo": "24hs", "notional": 941.0, "ref": 940.0}
    tok = oms.new_token(payload)
    assert oms.pop_token(tok) == payload
    assert oms.pop_token(tok) is None                       # segundo uso: rechazado
    res = asyncio.run(oms.place(payload))
    assert res["status"] == "PAPER" and "NO viajó" in res["motivo"]
    assert any(a["event"] == "paper_enviada" for a in oms.audit_tail(5))


def test_kill_switch_bloquea() -> None:
    oms.kill_switch(True)
    try:
        assert "KILL" in oms.validate("AL30", "buy", 100, 941.0, "C1", 941.0)
        res = asyncio.run(oms.place({"code": "AL30", "symbol": "X", "side": "buy",
                                     "qty": 1.0, "price": 941.0, "account": "C1"}))
        assert res["status"] == "RECHAZADA"
    finally:
        oms.kill_switch(False)


@pytest.mark.asyncio
async def test_ordenes_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    # Sembrar la referencia de mercado: otros tests dejan AL30 con last≈87 en
    # el store global y la banda fat-finger (±10%) rechazaría el ticket — que
    # es exactamente lo que debe hacer; acá fijamos la ref para el caso feliz.
    from backend.services import marketdata_store as mds, symbols as syms
    mds.get_store().update_from_md(syms.md_symbol("AL30", "24hs"), {"LA": {"price": 941.3}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        p = await ac.get("/ordenes")
        assert p.status_code == 200 and "PAPER" in p.text and "KILL" in p.text
        # ticket válido → confirmación con token; confirmar → PAPER
        t = await ac.post("/ordenes/ticket", data={"code": "AL30", "side": "buy",
            "qty": "100000", "price": "941,30", "account": "C1", "plazo": "24hs"})
        assert t.status_code == 200 and 'name="token"' in t.text
        import re
        tok = re.search(r'name="token" value="(\w+)"', t.text).group(1)
        c = await ac.post("/ordenes/confirmar", data={"token": tok})
        assert c.status_code == 200 and "PAPER" in c.text
        c2 = await ac.post("/ordenes/confirmar", data={"token": tok})
        assert "vencido o ya usado" in c2.text               # un solo uso
        # panel degrada sin auth (broker offline) con mensaje claro
        pa = await ac.get("/ordenes/panel")
        assert pa.status_code == 200


def test_validate_topes_por_moneda() -> None:
    """ARS → tope 1.000M ; hard-dollar (USD/USB) → tope 5M USD."""
    # notional = qty * price / 100. Con precio 100 → notional == qty.
    # ARS: 2.000M VN @ 100 = 2.000M ARS > 1.000M → rechaza ; 500M ok
    assert "ARS" in oms.validate("X", "buy", 2_000_000_000, 100.0, "C1", 100.0, "ARS")
    assert oms.validate("X", "buy", 500_000_000, 100.0, "C1", 100.0, "ARS") is None
    # USD: 6.000.000 VN @ 100 = 6.000.000 USD > 5M → rechaza ; 1M USD ok
    assert "USD" in oms.validate("GD", "buy", 6_000_000, 100.0, "C1", 100.0, "USD")
    assert oms.validate("GD", "buy", 1_000_000, 100.0, "C1", 100.0, "USB") is None


def test_validate_market_sin_precio() -> None:
    """Market: no exige precio ni respeta banda; estima notional con la ref."""
    assert oms.validate("AL30", "buy", 100, None, "C1", 941.0, "ARS", "market") is None
    # market sin precio pero con qty 0 → sigue fallando por cantidad
    assert oms.validate("AL30", "buy", 0, None, "C1", 941.0, "ARS", "market")


@pytest.mark.asyncio
async def test_quote_y_multi_y_blotter() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds, symbols as syms

    mds.get_store().update_from_md(syms.md_symbol("AL30", "24hs"),
                                   {"LA": {"price": 941.3}, "CL": {"price": 939.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # quote: book + tenencia (reusa el de Mercado)
        q = await ac.get("/ordenes/quote", params={"code": "AL30", "plazo": "24hs"})
        assert q.status_code == 200 and "Libro" in q.text
        # multiorden: 2 comitentes → confirmación batch con token
        m = await ac.post("/ordenes/multi", data={"code": "AL30", "side": "buy",
            "ordtype": "limit", "price": "941,30", "plazo": "24hs",
            "lines": "COMIT-1, 100000\nCOMIT-2, 50000"})
        assert m.status_code == 200 and "MULTIORDEN" in m.text
        import re
        tok = re.search(r'name="token" value="(\w+)"', m.text).group(1)
        c = await ac.post("/ordenes/multi/confirmar", data={"token": tok})
        assert c.status_code == 200 and c.text.count("PAPER") >= 2
        # blotter: refleja las 2 paper recién enviadas
        b = await ac.get("/ordenes/blotter")
        assert b.status_code == 200 and "AL30" in b.text and "Blotter" in b.text


def test_live_switch_runtime() -> None:
    """Override en memoria: prende/apaga LIVE sin tocar config; reset → paper."""
    assert oms.is_live() is False                 # default paper
    try:
        assert oms.set_live(True) is True and oms.is_live() is True
        oms.kill_switch(True)                     # evita tocar la red en el test
        res = asyncio.run(oms.place({"code": "AL30", "symbol": "X", "side": "buy",
                                     "qty": 1.0, "price": 100.0, "account": "C1",
                                     "ordtype": "limit"}))
        assert res["status"] == "RECHAZADA"       # live, pero kill bloquea
    finally:
        oms.kill_switch(False)
        oms.set_live(None)
    assert oms.is_live() is False                 # vuelve a seguir la config


@pytest.mark.asyncio
async def test_live_endpoint_requiere_confirmacion() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post("/ordenes/live", data={"arm": "1", "confirm": "nope"})
            assert r.status_code == 200 and oms.is_live() is False     # no se armó
            r2 = await ac.post("/ordenes/live", data={"arm": "1", "confirm": "LIVE"})
            assert r2.status_code == 200 and oms.is_live() is True      # armado
            assert "LIVE" in r2.text
            r3 = await ac.post("/ordenes/live", data={"arm": "0"})
            assert r3.status_code == 200 and oms.is_live() is False     # de vuelta paper
    finally:
        oms.set_live(None)
