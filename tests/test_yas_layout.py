"""YAS · rediseño de layout (30/10).

- La ficha del instrumento (`GET /yas/ficha`) se ve sin precio ni cotización:
  datos estáticos de `bond_meta` + liquidación del plazo; callable → cronograma
  tal como está cargado (sin derivar fechas, sin asumir 100); putable con
  texto y fecha → "No disponible"; no callable → "No", sin bloque.
- Estados del recompute: vacío (panel neutro, sin rojos), inválido (aviso
  pegado al campo por OOB + panel neutro, nunca números viejos), ok.
- Énfasis: lo ingresado sólo cambia de color (`is-input`), el resultado lleva
  fondo (`is-result`): modo precio resalta TIREA y TNA; modo TIREA / TNA /
  margen resalta el precio.
- `value_raw`: el crudo del autofill (precisión completa) gana sobre el input
  de 4 decimales mientras coincidan; si el usuario editó, vale lo tipeado.
- Total return sin valor → neutro. Snapshot con `last_native` para el
  autofill. Costo: la ficha es un lookup memoizado (< 2 ms), el recompute no
  cambia de camino.
"""
from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from backend.locale_ar import fmt_pct
from backend.services import bond_universe, pricing


def _client():
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _code(curva: str) -> str:
    from backend.services import curves
    bond_universe.ensure_loaded()
    return (curves.build_curve_codes().get(curva) or [])[0]


@pytest.mark.asyncio
async def test_ficha_visible_sin_precio_y_con_call() -> None:
    bond_universe.ensure_loaded()
    async with _client() as ac:
        # bullet sin call
        r = await ac.get("/yas/ficha", params={"code": _code("lecap"), "plazo": "24hs"})
        assert r.status_code == 200 and "Ficha del instrumento" in r.text
        assert "Rescate anticipado" in r.text and "call-box" not in r.text
        assert "Liquidación" in r.text and "t+1" in r.text
        # callable con cronograma (TSC4C: dict de ventanas en meses)
        r = await ac.get("/yas/ficha", params={"code": "TSC4C", "plazo": "CI"})
        assert "call-box" in r.text and "opción del emisor" in r.text
        assert "m84 a m95" in r.text and "103,875 %" in r.text          # 1.03875 → % VN
        assert "prima compensatoria" in r.text                           # texto tal cual
        assert "2030" not in r.text and "2032" not in r.text             # NO se derivan fechas
        assert "chip-call" in r.text and "t+1" not in r.text             # CI: sin t+1
        # putable con texto + fecha, sin precio → No disponible
        r = await ac.get("/yas/ficha", params={"code": "TY30P"})
        assert "del tenedor (put)" in r.text and "27/05/2027" in r.text
        assert "No disponible en la ficha" in r.text
        # código en minúscula (add-in / URL a mano) resuelve igual
        r = await ac.get("/yas/ficha", params={"code": "tsc4c"})
        assert "TSC4C" in r.text and "call-box" in r.text


def test_bond_meta_call_rows_y_cupon() -> None:
    bond_universe.ensure_loaded()
    m = pricing.bond_meta("TSC4C")
    assert m["callable"] and [r["precio"] for r in m["call_rows"]][1:] == pytest.approx([103.875, 101.938, 100.969, 100.0])
    assert m["call_rows"][0]["texto"].startswith("rescate con prima")
    assert m["cupon_label"] == "7,75 %" and m["amort_cuotas"] == 1
    ae = pricing.bond_meta("AE38")
    assert ae["cupon_label"].endswith("step-up") and ae["amort_cuotas"] == 22 and not ae["call_rows"]
    assert pricing._call_rows(None) == [] and pricing._call_rows(1.0) == [{"ventana": "", "precio": 100.0, "texto": ""}]
    assert pricing._call_rows({"x": "texto"}) == [{"ventana": "x", "precio": None, "texto": "texto"}]


@pytest.mark.asyncio
async def test_estados_vacio_invalido_ok_y_enfasis() -> None:
    code = _code("lecap")
    base = {"code": code, "nominales": "1000000", "plazo": "24hs"}
    async with _client() as ac:
        # vacío: panel neutro, sin alert-error, hint neutro por OOB
        r = await ac.post("/yas/recompute", data={**base, "mode": "precio", "value": ""})
        assert r.status_code == 200 and "empty-state" in r.text and "alert-error" not in r.text
        assert 'id="yas-value-hint" class="field-hint is-empty"' in r.text
        assert "metrics-primary" not in r.text and "<table class=\"ticket\"" not in r.text
        # inválido: aviso pegado al campo, sin resultados
        r = await ac.post("/yas/recompute", data={**base, "mode": "precio", "value": "87.30abc"})
        assert "Corregí el valor" in r.text and 'class="field-hint is-invalid"' in r.text
        assert "No es un número" in r.text and "metrics-primary" not in r.text and "alert-error" not in r.text
        # ok en modo precio: precio = ingresado (letra), TIREA y TNA = resultado (fondo)
        r = await ac.post("/yas/recompute", data={**base, "mode": "precio", "value": "95,5"})
        t = r.text
        assert "metrics-primary" in t and "empty-state" not in t
        assert '<div class="metric is-input">\n    <span class="metric-label">Precio' in t
        assert t.count('class="metric is-result"') == 2                     # TIREA y TNA
        assert t.count("tag-res") >= 2 and 'tag-in">ingresado' in t
        assert 'class="field-hint "' in t and "manual" in t                 # tipeado a mano
        # ok en modo TIREA: el precio es el resultado, la TIREA sólo cambia de letra
        r = await ac.post("/yas/recompute", data={**base, "mode": "tir", "value": "0,35"})
        t = r.text
        assert t.count('class="metric is-result"') == 1                     # sólo el precio
        assert 'TIREA <span class="tag tag-in">ingresado' in t
        assert "= 35,00% efectiva anual" in t                              # hint del modo
        assert '<tr class="res"><th>Precio usado' in t                      # ticket: fila resaltada
        # el ticket completo de siempre sigue (nada se pierde)
        assert "Ticket completo" in t and "Convenciones" in t


@pytest.mark.asyncio
async def test_value_raw_conserva_la_precision_del_mercado() -> None:
    code = _code("lecap")
    settle = pricing.settlement_date_str("24hs")
    exacto = pricing.compute_metrics(code, "precio", 95.123456, settle=settle, include_cashflows=False)["tirea"]
    redondo = pricing.compute_metrics(code, "precio", 95.1235, settle=settle, include_cashflows=False)["tirea"]
    assert exacto != redondo
    base = {"code": code, "mode": "precio", "nominales": "1000000", "plazo": "24hs"}
    async with _client() as ac:
        # input a 4 decimales + crudo coincidente → se usa el crudo
        r = await ac.post("/yas/recompute", data={**base, "value": "95,1235", "value_raw": "95.123456"})
        assert fmt_pct(exacto, 4) in r.text
        assert "precisión interna 95,123456" in r.text
        # el usuario editó el input (crudo viejo, ya no coincide) → vale lo tipeado
        r = await ac.post("/yas/recompute", data={**base, "value": "95,1235", "value_raw": "96.0"})
        assert fmt_pct(redondo, 4) in r.text and fmt_pct(exacto, 4) not in r.text
        # TR sin valor → neutro, no rojo
        r = await ac.post("/yas/tr", data={**base, "value": ""})
        assert "Se calcula con el valor de la ficha" in r.text and "var(--red" not in r.text


@pytest.mark.asyncio
async def test_pagina_market_card_y_snapshot_native() -> None:
    from backend.services import marketdata_store as mds, symbols as syms
    code = _code("lecap")
    mds.get_store().update_from_md(syms.md_symbol(code, "24hs"), {"LA": {"price": 96.123456, "size": 10}, "CL": {"price": 96.0}})
    async with _client() as ac:
        pg = await ac.get(f"/yas?code={code}")
        assert pg.status_code == 200
        assert 'id="yas-ficha"' in pg.text and "Ficha del instrumento" in pg.text   # inline al cargar
        assert 'name="value_raw"' in pg.text and "yas-header-strip" not in pg.text
        assert 'value: "96,1235"' in pg.text and 'valueRaw: "96.123456"' in pg.text  # 4 decimales + crudo
        snap = (await ac.get(f"/market/snapshot/{code}")).json()
        assert snap["last_native"] == pytest.approx(96.123456)
        # «en uso» sólo cuando la ficha valúa al last (modo precio y mismo valor)
        r = await ac.get("/yas/market", params={"code": code, "plazo": "24hs", "mode": "precio", "value": "96,1235", "value_raw": "96.123456"})
        assert "en uso" in r.text
        r = await ac.get("/yas/market", params={"code": code, "plazo": "24hs", "mode": "tir", "value": "0,3"})
        assert "en uso" not in r.text
        r = await ac.get("/yas/market", params={"code": code, "plazo": "24hs", "mode": "precio", "value": "90"})
        assert "en uso" not in r.text


@pytest.mark.asyncio
async def test_ficha_y_recompute_siguen_rapidos() -> None:
    """La ficha es un lookup memoizado; el recompute no cambió de camino."""
    code = _code("lecap")
    async with _client() as ac:
        await ac.get("/yas/ficha", params={"code": code})
        t0 = time.perf_counter()
        for _ in range(30):
            await ac.get("/yas/ficha", params={"code": code})
        ms = (time.perf_counter() - t0) * 1000 / 30
        assert ms < 25, ms
        data = {"code": code, "mode": "precio", "value": "95,5", "nominales": "1000000", "plazo": "24hs"}
        await ac.post("/yas/recompute", data=data)
        t0 = time.perf_counter()
        for _ in range(30):
            await ac.post("/yas/recompute", data=data)
        ms = (time.perf_counter() - t0) * 1000 / 30
        assert ms < 50, ms
