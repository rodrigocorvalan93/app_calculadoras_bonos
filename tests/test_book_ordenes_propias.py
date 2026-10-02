"""Libro (Mercado / Órdenes): órdenes PROPIAS resaltadas y profundidad fija.

El nivel donde hay una orden nuestra viva va en negrita y en verde (compra) /
rojo (venta), con el VN propio en el tooltip. Fuentes, sin red en el hot path:
lo que esta app envió y el broker aceptó (`recordar_propia` en `oms.place`,
hasta un estado final / cancel / que el broker deje de listarla) y la última
lista de vivas del broker por comitente (`recordar_activas`, que cargan el
panel de Órdenes y `maybe_refresh_activas` en background). Las dos puntas se
rellenan hasta 5 filas para que el card no cambie de alto con cada nivel que
entra o sale."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, marketdata_store, oms, symbols as syms

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _limpio():
    oms._OWN.clear()
    oms._ACTIVES.clear()
    yield
    oms._OWN.clear()
    oms._ACTIVES.clear()


def _lecap() -> str:
    from backend.services import curves
    bond_universe.ensure_loaded()
    cods = sorted(curves.build_curve_codes().get("lecap") or [])
    if not cods:
        pytest.skip("sin lecaps en el universo")
    return cods[0]


def _sembrar(code: str) -> str:
    sym = syms.md_symbol(code, "24hs")
    marketdata_store.get_store().update_from_md(sym, {
        "LA": {"price": 100.0, "size": 1000}, "CL": {"price": 99.5},
        "BI": [{"price": 99.9, "size": 5000}, {"price": 99.8, "size": 12000}],
        "OF": [{"price": 100.1, "size": 7000}, {"price": 100.2, "size": 9000}],
    })
    return sym


def test_own_levels_junta_app_y_broker_sin_duplicar() -> None:
    sym = "MERV - XMEV - TMF27 - 24hs"
    # enviada desde la app: el broker devolvió clientId 529527480147778
    oms.recordar_propia({"symbol": sym, "side": "sell", "price": 124.5, "qty": 240_000_000,
                         "account": "27404", "client_order_id": "calc-abc"}, cid="529527480147778")
    # la lista de vivas del broker trae la misma (mismo id) y otra de compra, y una ejecutada que no cuenta
    oms.recordar_activas("27404", [
        {"clOrdId": "529527480147778", "instrumentId": {"symbol": sym}, "side": "SELL",
         "price": 124.5, "orderQty": 240_000_000, "leavesQty": 240_000_000, "status": "NEW",
         "accountId": {"id": "27404"}},
        {"clOrdId": "777", "instrumentId": {"symbol": "merv - xmev - tmf27 - 24hs"}, "side": "BUY",
         "price": 124.2, "orderQty": 10_000_000, "cumQty": 4_000_000, "status": "PARTIALLY_FILLED"},
        {"clOrdId": "888", "instrumentId": {"symbol": sym}, "side": "BUY", "price": 124.0,
         "orderQty": 5_000_000, "status": "FILLED"},
        {"clOrdId": "999", "instrumentId": {"symbol": "MERV - XMEV - AL30 - 24hs"}, "side": "BUY",
         "price": 70_000.0, "orderQty": 1000, "status": "NEW"},
    ])
    niv = oms.own_levels(sym)
    assert niv["sell"] == {124.5: 240_000_000.0}                  # una sola vez aunque esté en las dos fuentes
    assert niv["buy"] == {124.2: 6_000_000.0}                     # lo que queda de la parcial
    assert oms.own_levels("MERV - XMEV - AL30 - 24hs")["buy"] == {70000.0: 1000.0}
    assert oms.own_levels("MERV - XMEV - GD30 - 24hs") == {"buy": {}, "sell": {}}
    # market (sin precio) no marca nada; símbolo con espacios raros se normaliza
    oms.recordar_propia({"symbol": sym, "side": "buy", "price": None, "qty": 1000}, cid="m1")
    assert "m1" not in oms._OWN
    oms.recordar_propia({"symbol": "  merv - xmev -  tmf27 - 24hs ", "side": "B", "price": "124,2".replace(",", "."),
                         "qty": 1_000_000}, cid="b2")
    assert oms.own_levels(sym)["buy"][124.2] == 7_000_000.0


def test_propia_se_da_de_baja_con_estado_final_cancel_o_lista_del_broker() -> None:
    sym = "MERV - XMEV - TMF27 - 24hs"
    oms.recordar_propia({"symbol": sym, "side": "sell", "price": 124.5, "qty": 100}, cid="A")
    oms.recordar_propia({"symbol": sym, "side": "sell", "price": 124.6, "qty": 200}, cid="B")
    oms.recordar_propia({"symbol": sym, "side": "buy", "price": 124.0, "qty": 300, "account": "27404"}, cid="C")
    oms.actualizar_propia("A", 100, 40)                           # parcial: quedan 60
    assert oms.own_levels(sym)["sell"][124.5] == 60.0
    oms.actualizar_propia("A", 100, 100)                          # ejecutada entera
    oms.olvidar_propia("B")                                       # cancel aceptada
    assert oms.own_levels(sym)["sell"] == {}
    # la lista del broker para 27404 no trae a C: era vieja (> 20 s) → se da de baja
    oms._OWN["C"]["ts"] = time.time() - 60
    oms.recordar_activas("27404", [])
    assert oms.own_levels(sym) == {"buy": {}, "sell": {}}
    # una recién enviada (< 20 s) sobrevive a una lista que todavía no la trae
    oms.recordar_propia({"symbol": sym, "side": "buy", "price": 124.0, "qty": 300, "account": "27404"}, cid="D")
    oms.recordar_activas("27404", [])
    assert oms.own_levels(sym)["buy"] == {124.0: 300.0}


def test_lista_del_broker_vencida_no_afirma_nada() -> None:
    sym = "MERV - XMEV - TMF27 - 24hs"
    oms.recordar_activas("1", [{"clOrdId": "x", "instrumentId": {"symbol": sym}, "side": "SELL",
                                "price": 1.0, "orderQty": 10, "status": "NEW"}])
    assert oms.own_levels(sym)["sell"] == {1.0: 10.0}
    t, vivas = oms._ACTIVES["1"]
    oms._ACTIVES["1"] = (t - oms._ACTIVES_TTL - 1, vivas)
    assert oms.own_levels(sym)["sell"] == {}


def test_marcar_niveles_por_precio_redondeado() -> None:
    niveles = [{"price": 124.5, "size": 1000}, {"price": 124.55, "size": 50}, {"price": None}]
    oms.marcar_niveles(niveles, {124.5: 240.0})
    assert niveles[0]["own"] == 240.0 and "own" not in niveles[1] and "own" not in niveles[2]
    oms.marcar_niveles(niveles, {})                                # sin propias: no toca nada


def test_maybe_refresh_activas_sin_sesion_no_hace_nada(monkeypatch) -> None:
    oms._actives_next = 0.0
    from backend.services import primary_ws
    cli = primary_ws.get_ws_client()
    monkeypatch.setattr(type(cli), "authenticated", property(lambda self: False))
    oms.maybe_refresh_activas()                                     # sin sesión REST: ni toca la red
    assert oms._actives_next == 0.0
    # con sesión pero sin loop corriendo (llamada síncrona): tampoco rompe
    monkeypatch.setattr(type(cli), "authenticated", property(lambda self: True))
    oms.recordar_propia({"symbol": "X", "side": "buy", "price": 1.0, "qty": 1, "account": "9"}, cid="q")
    oms.maybe_refresh_activas()
    assert oms._actives_next == 0.0                                 # no quedó throttleado sin haber disparado


@pytest.mark.asyncio
async def test_libro_resalta_la_propia_y_rellena_la_profundidad() -> None:
    from backend.main import app
    code = _lecap()
    sym = _sembrar(code)
    # venta propia en el 1er offer (100,10) y compra en el 2º bid (99,80)
    oms.recordar_propia({"symbol": sym, "side": "sell", "price": 100.1, "qty": 2500, "account": "27404"}, cid="s1")
    oms.recordar_activas("27404", [{"clOrdId": "b1", "instrumentId": {"symbol": sym}, "side": "BUY",
                                    "price": 99.8, "orderQty": 4000, "status": "NEW"}])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs"})
        assert r.status_code == 200
        html = r.text
        assert 'class="depth-ask own-order own-sell"' in html
        assert "Orden propia de VENTA: 2.500 VN de los 7.000 de este nivel" in html
        assert 'class="depth-bid own-order own-buy"' in html
        assert "Orden propia de COMPRA: 4.000 VN de los 12.000 de este nivel" in html
        assert html.count("own-order") == 2                       # sólo esos dos niveles
        # profundidad fija: 2 niveles por punta → 3 filas de relleno en cada tabla
        assert html.count('class="depth-pad"') == 6
        # el libro embebido en Órdenes es el mismo render
        q = await ac.get("/ordenes/quote", params={"code": code, "plazo": "24hs"})
        assert q.status_code == 200 and q.text.count("own-order") == 2
    # sin propias: ninguna fila marcada, el relleno sigue (el libro se cachea por
    # seq del store: un tick nuevo para que no devuelva el HTML anterior)
    oms._OWN.clear(); oms._ACTIVES.clear()
    _sembrar(code)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs"})
        assert "own-order" not in r.text and r.text.count('class="depth-pad"') == 6


def test_css_y_js_del_libro() -> None:
    css = (ROOT / "backend/static/css/style.css").read_text(encoding="utf-8")
    assert ".cashflows tr.own-order td { font-weight: 700; }" in css
    assert ".cashflows tr.own-buy td  { color: var(--green); }" in css
    assert ".cashflows tr.own-sell td { color: var(--red); }" in css
    assert ".depth-pad td" in css
    js = (ROOT / "backend/static/js/app.js").read_text(encoding="utf-8")
    # swap outerHTML sobre sí mismo (el libro): el flash y el congelado de
    # columnas tienen que mirar el nodo NUEVO (evt.target), no el detail.target
    # desconectado — con htmx 2 el libro no flasheaba nunca.
    assert "if (t && !t.isConnected && evt.target && evt.target.hasAttribute) t = evt.target;" in js
    assert "return (t && t.isConnected) ? t : evt.target;" in js
    assert "[data-flash-scope] table.cashflows" in js
    assert "if (cs[i].colSpan > 1 || cs[i].rowSpan > 1) return [];" in js
    assert "[data-cols-fijas] > table { table-layout: fixed; }" in css
