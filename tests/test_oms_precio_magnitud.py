"""El caso real VSCMO (28/08): precio "141.750" tipeado con punto decimal
(estilo Matriz/en-US) → el parser es-AR lo lee como 141.750,00 (×1000) → sin
dato en el store la banda no corría → con "confirmá manualmente" la orden viajó
al broker y el risk la rechazó por Saldo insuficiente (300.000 VN × 141.750 =
425 MM, abajo del tope de 1.000 MM).

Tres cierres, cada uno testeado acá:
1. `oms.market_ref_rest` — last/close por REST del broker cuando el store no
   tiene el símbolo → la banda casi siempre tiene referencia.
2. Hint de magnitud en el rechazo de banda: si price×1000 o ÷1000 encaja en la
   banda, el motivo sugiere el precio es-AR correcto (sin reinterpretar nada).
3. `place()` manda orderQty ENTERO (no "300000.0" en el query string).
"""
from __future__ import annotations

import asyncio
import re

import pytest

from backend.services import oms


def test_hint_magnitud_en_banda_mercado() -> None:
    # ×1000 (el caso VSCMO): fuera de banda + sugerencia del precio correcto
    m = oms.validate("VSCMO", "buy", 300_000, 141_750.0, "C1", 141.75)
    assert m and "banda" in m and "¿Quisiste decir 141,75?" in m
    # ÷1000 (el sub-precio clásico, PSSXO): también sugiere
    m2 = oms.validate("PSSXO", "sell", 1_000, 204.6, "C1", 204_600.0)
    assert m2 and "banda" in m2 and "204.600,00" in m2 and "Quisiste" in m2
    # fuera de banda SIN encaje ×/÷1000 → rechazo normal, sin hint confuso
    m3 = oms.validate("AL30", "buy", 100, 700.0, "C1", 941.0)
    assert m3 and "banda" in m3 and "Quisiste" not in m3
    # dentro de banda → pasa como siempre
    assert oms.validate("AL30", "buy", 100, 941.0, "C1", 940.0) is None


def test_hint_magnitud_en_banda_teorica() -> None:
    # sin mercado pero con valor técnico: misma sugerencia sobre la banda teórica
    m = oms.validate("VSCMO", "buy", 300_000, 141_750.0, "C1", None, theo_ref=141.75)
    assert m and "valor técnico" in m and "Quisiste" in m


class _FakeClient:
    def __init__(self, resp, authenticated: bool = True):
        self.resp = resp
        self.authenticated = authenticated
        self.calls: list = []

    async def get_json(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return self.resp


@pytest.mark.asyncio
async def test_market_ref_rest(monkeypatch) -> None:
    from backend.services import primary_ws

    # LA vacío → cae a CL; params correctos (marketId/symbol/entries)
    c = _FakeClient({"status": "OK", "marketData": {"LA": None, "CL": {"price": 141.75}}})
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c)
    assert await oms.market_ref_rest("MERV - XMEV - VSCMO - 24hs") == 141.75
    path, params = c.calls[0]
    assert path == "rest/marketdata/get" and params["symbol"].endswith("VSCMO - 24hs")
    # sin sesión → NI TOCA la red
    c2 = _FakeClient({"status": "OK"}, authenticated=False)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c2)
    assert await oms.market_ref_rest("X") is None and c2.calls == []
    # respuesta rara / error del broker → None (fail-open al flujo de siempre)
    c3 = _FakeClient({"status": "ERROR"})
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c3)
    assert await oms.market_ref_rest("X") is None
    c4 = _FakeClient(None)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c4)
    assert await oms.market_ref_rest("X") is None


@pytest.mark.asyncio
async def test_ticket_sin_store_usa_ref_del_broker(monkeypatch) -> None:
    """Regresión del caso completo: VSCMO sin dato en el store → el ticket trae
    la ref por REST y la banda RECHAZA el ×1000 con el hint (antes viajaba)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async def fake_ref(symbol: str):
        assert "VSCMO" in symbol
        return 141.75
    monkeypatch.setattr(oms, "market_ref_rest", fake_ref)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        t = await ac.post("/ordenes/ticket", data={
            "code": "VSCMO", "side": "buy", "ordtype": "limit", "qty": "300.000",
            "price": "141.750", "account": "61123", "plazo": "24hs"})
        assert t.status_code == 200
        assert "banda" in t.text and "Quisiste decir 141,75" in t.text
        assert 'name="token"' not in t.text          # NO se armó ticket
    assert any(a["event"] == "rechazada_pretrade" and "Quisiste" in (a.get("motivo") or "")
               for a in oms.audit_tail(5))
    # y con el precio bien escrito (coma decimal) el ticket se arma normal
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        t2 = await ac.post("/ordenes/ticket", data={
            "code": "VSCMO", "side": "buy", "ordtype": "limit", "qty": "300.000",
            "price": "141,75", "account": "61123", "plazo": "24hs"})
        assert t2.status_code == 200 and 'name="token"' in t2.text
        assert re.search(r"141,75", t2.text)


@pytest.mark.asyncio
async def test_place_manda_order_qty_entero(monkeypatch) -> None:
    """El VN viaja como entero (300000, no '300000.0') — campo entero en xOMS."""
    from backend.services import instruments, primary_ws

    async def fake_resolve(code, symbol):
        return {"checked": False, "exists": False, "symbol": symbol, "candidates": []}
    monkeypatch.setattr(instruments, "resolve", fake_resolve)
    c = _FakeClient(None)

    async def fake_checked(path, params=None):
        c.calls.append((path, dict(params or {})))
        return {"status": "OK", "order": {"clientId": "1", "proprietary": "ISV"}}
    c.get_json_checked = fake_checked
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c)
    monkeypatch.setattr(oms, "_FOLLOWUP_DELAYS", (0.0,))

    try:
        oms.kill_switch(False)
        oms.set_live(True)
        res = await oms.place({"code": "VSCMO", "symbol": "MERV - XMEV - VSCMO - 24hs",
                               "side": "buy", "qty": 300000.0, "price": 141.75,
                               "account": "61123", "ordtype": "limit"})
        assert res["status"] == "OK"
        params = next(p for pa, p in c.calls if pa == "rest/order/newSingleOrder")
        assert params["orderQty"] == 300000 and isinstance(params["orderQty"], int)
        assert params["price"] == 141.75
        await asyncio.sleep(0.05)                  # deja correr el seguimiento
        assert any(pa == "rest/order/id" for pa, _ in c.calls)   # se disparó
    finally:
        oms.set_live(None)


@pytest.mark.asyncio
async def test_seguimiento_estado_broker(monkeypatch) -> None:
    """Tras un envío aceptado, el seguimiento trae el estado REAL del broker y
    el blotter lo muestra — el caso GN39O: 'OK' al enviar pero REJECTED (Saldo
    insuficiente) al toque; antes el blotter quedaba en ENVIADA para siempre y
    había que abrir la Matriz para enterarse."""
    from backend.services import primary_ws

    class _C:
        authenticated = True

        def __init__(self):
            self.calls: list = []

        async def get_json(self, path, params=None):
            self.calls.append((path, dict(params or {})))
            return {"status": "OK", "order": {"clientId": params["clientOrderId"],
                                              "status": "Rejected",
                                              "text": "Saldo insuficiente",
                                              "cumQty": 0}}
    c = _C()
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: c)
    monkeypatch.setattr(oms, "_FOLLOWUP_DELAYS", (0.0, 0.0))
    rec = {"code": "GN39O", "side": "buy", "qty": 180_077.0, "price": 144_850.0,
           "account": "72813", "client_order_id": "calc-test-seg"}
    await oms._order_followup("526502342000080", "ISV_PBCP", rec)
    assert len(c.calls) == 1                       # estado final → corta en el 1º intento
    assert c.calls[0][1] == {"clientOrderId": "526502342000080", "proprietary": "ISV_PBCP"}
    est = next(a for a in oms.audit_tail(5) if a.get("event") == "live_estado")
    assert est["estado"] == "REJECTED" and "Saldo" in est["texto"]   # normaliza a upper
    r = next(x for x in oms.blotter(10) if x["cid"] == "calc-test-seg")
    assert r["status"] == "RECHAZADA (broker)" and "Saldo insuficiente" in r["motivo"]
