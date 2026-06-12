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
