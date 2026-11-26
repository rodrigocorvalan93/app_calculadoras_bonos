"""Un bono hard-dollar = UNA ficha en su dólar natural y hasta tres tickers en
BYMA (pesos, MEP …D, cable …C). Cualquier pantalla que reciba un TICKER tiene
que valuarlo con la ficha nativa y el precio llevado a su dólar:

    pesos           ÷ FX de la moneda de pago (CCL si la nativa es cable, MEP si es MEP)
    la otra pata    × MEP ÷ CCL  (o × CCL ÷ MEP): se le saca / suma el canje
    la nativa       tal cual

Con precios consistentes en las tres patas la TIR es la MISMA por cualquier
camino: la tabla / el libro de Mercado y Curvas, el libro de Órdenes por
ticker, el autofill de YAS, el add-in de Excel y las alertas. Hasta el 26/11
sólo cumplía la vista por pata de Mercado / Curvas: la pata cruzada no tenía
ficha (sin TIR en Órdenes, error en el add-in), la de pesos entraba cruda a la
ficha en dólares (add-in y alertas: −100 %), el autofill de YAS metía el precio
dirty en la ficha clean de un global, y el ticket de Órdenes medía el tope con
la moneda de la FICHA (una compra de AL30 en pesos de VN 10.000 «superaba» el
tope en dólares; una de GD30D por USD 17 millones pasaba como pesos).
"""
from __future__ import annotations

import re

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from backend.routes import curves as rc
from backend.services import alertas, bond_universe, curves, patas, pricing
from backend.services import fx as fx_svc
from backend.services import marketdata_store as mds
from backend.services import symbols as syms

CCL, MEP = 1500.0, 1450.0
PG, PA = 62.0, 60.0                      # GD30C (cable) y AL30D (MEP), dirty por 100 VN


def _seed(store, code: str, px: float, vol: float = 1e12) -> None:
    store.update_from_md(syms.md_symbol(code, "24hs"), {
        "LA": {"price": px, "size": 1000, "date": "1"}, "CL": {"price": px * 0.99, "date": "1"},
        "BI": [{"price": px * 0.999, "size": 5000}], "OF": [{"price": px * 1.001, "size": 5000}],
        "EV": vol, "NV": vol / px * 100})


@pytest.fixture()
def tres_patas(monkeypatch):
    """Store aislado con GD30 / GD30D / GD30C y AL30 / AL30D / AL30C a precios
    consistentes con CCL 1500 y MEP 1450 (canje 3,45 %)."""
    bond_universe.ensure_loaded()
    for c in ("GD30", "GD30C", "AL30", "AL30D"):
        if bond_universe.get(c) is None:
            pytest.skip(f"especies.py sin la ficha {c}")
    store = mds.MarketDataStore()
    monkeypatch.setattr(mds, "_store", store)
    _seed(store, "GD30C", PG)
    _seed(store, "GD30", PG * CCL)
    _seed(store, "GD30D", PG * CCL / MEP)
    _seed(store, "AL30D", PA)
    _seed(store, "AL30", PA * MEP)
    _seed(store, "AL30C", PA * MEP / CCL)
    fx_svc.invalidate()
    fx = fx_svc.get_fx("24hs")
    assert fx.ccl == pytest.approx(CCL) and fx.usb == pytest.approx(MEP)
    settle = pricing.settlement_date_str("24hs")
    ref = {"GD30": pricing.metrics_for_market_price("GD30C", PG, settle)["tirea"],
           "AL30": pricing.metrics_for_market_price("AL30D", PA, settle)["tirea"]}
    assert all(np.isfinite(v) for v in ref.values())
    yield {"store": store, "ref": ref, "settle": settle}
    fx_svc.invalidate()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _tir_last(html: str) -> float:
    m = re.search(r"TIR @ last.{0,120}?(-?[\d\.]+,\d+)\s*%", html, re.S)
    assert m, html[:400]
    return float(m.group(1).replace(".", "").replace(",", ".")) / 100.0


# ── el resolver ──────────────────────────────────────────────────────────────
def test_leg_de_resuelve_ficha_y_moneda_de_cada_ticker():
    bond_universe.ensure_loaded()
    L = patas.leg_de
    # global: ficha base CLEAN (referencia tipo Bloomberg) + nativa cable …C
    assert L("GD30") == patas.Leg("GD30", "GD30C", "ARS", "USD", True)
    assert L("GD30C") == patas.Leg("GD30C", "GD30C", "USD", "USD", True)
    assert L("GD30D") == patas.Leg("GD30D", "GD30C", "USB", "USD", False)      # la MEP no tiene ficha
    # bonar: nativa MEP …D
    assert L("AL30") == patas.Leg("AL30", "AL30D", "ARS", "USB", True)
    assert L("AL30D") == patas.Leg("AL30D", "AL30D", "USB", "USB", True)
    assert L("AL30C") == patas.Leg("AL30C", "AL30D", "USD", "USB", False)      # la cable no tiene ficha
    assert L("gd30d") == L("GD30D") and L(" AL30C ") == L("AL30C")
    assert [L(c).convierte for c in ("GD30", "GD30D", "GD30C", "AL30", "AL30C", "AL30D")] == [True, True, False, True, True, False]
    # moneda en la que se OPERA cada ticker (tope de una orden)
    assert [patas.moneda_ticker(c) for c in ("GD30", "GD30D", "GD30C", "AL30", "AL30D", "AL30C")] == \
        ["ARS", "USB", "USD", "ARS", "USB", "USD"]
    # un bono en pesos no tiene patas; un código cualquiera no se inventa
    pesos = next(c for c in curves.build_curve_codes().get("cer") or [] if not c.endswith("j"))
    assert L(pesos) == patas.Leg(pesos, pesos, "", "", True) and not L(pesos).convierte
    assert patas.moneda_ticker(pesos) == (pricing.bond_meta(pesos).get("moneda") or "ARS")
    assert L("ZZZZ9") is None and L("ZZZZ9D") is None and L("") is None and patas.moneda_ticker("ZZZZ9") == "ARS"
    # textos del libro
    assert "÷ CCL" in patas.como_se_valua(L("GD30")) and "GD30C" in patas.como_se_valua(L("GD30"))
    assert "× MEP ÷ CCL" in patas.como_se_valua(L("GD30D")) and "÷ MEP" in patas.como_se_valua(L("AL30"))
    assert "× CCL ÷ MEP" in patas.como_se_valua(L("AL30C"))
    assert patas.como_se_valua(L("GD30C")) == "" and patas.como_se_valua(L(pesos)) == "" and patas.como_se_valua(None) == ""


def test_leg_de_on_con_solo_la_nativa_y_raiz_que_termina_en_d():
    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    # una ON MEP con sólo la nativa …D cargada: su ticker en pesos (…O) y su pata cable (…C) no tienen ficha
    nat = next((c for c in cc.get("corp_hdmep") or [] if c.endswith("D") and bond_universe.get(c[:-1] + "O") is None
                and bond_universe.get(c[:-1] + "C") is None and bond_universe.get(c[:-1]) is None), None)
    if nat is not None:
        base = nat[:-1]
        assert patas.leg_de(base + "O") == patas.Leg(base + "O", nat, "ARS", "USB", False)
        assert patas.leg_de(base + "C") == patas.Leg(base + "C", nat, "USD", "USB", False)
    # CO32D: la RAÍZ termina en D (su pata cable es CO32DC) → el ticker CO32D es el de pesos
    if bond_universe.get("CO32D") is not None and bond_universe.get("CO32DC") is not None:
        assert pricing.es_especie_pesos("CO32D") and not pricing.es_especie_pesos("CO32DC")
        assert pricing.native_dollar_code("CO32D") == "CO32DC" and pricing.pesos_sibling_code("CO32DC") == "CO32D"
        assert patas.leg_de("CO32D") == patas.Leg("CO32D", "CO32DC", "ARS", "USD", True)
        assert patas.leg_de("CO32DD") == patas.Leg("CO32DD", "CO32DC", "USB", "USD", False)
    assert pricing.es_especie_pesos("GD30") and pricing.es_especie_pesos("AL30")
    assert not pricing.es_especie_pesos("GD30C") and not pricing.es_especie_pesos("AL30D") and not pricing.es_especie_pesos("ZZZZ9")


def test_conversiones_de_precio(tres_patas):
    L = patas.leg_de
    assert patas.precio_nativo(L("GD30"), PG * CCL) == pytest.approx(PG)                 # pesos ÷ CCL
    assert patas.precio_nativo(L("GD30D"), PG * CCL / MEP) == pytest.approx(PG)          # MEP × MEP ÷ CCL
    assert patas.precio_nativo(L("GD30C"), PG) == PG
    assert patas.precio_nativo(L("AL30"), PA * MEP) == pytest.approx(PA)                 # pesos ÷ MEP
    assert patas.precio_nativo(L("AL30C"), PA * MEP / CCL) == pytest.approx(PA)          # cable × CCL ÷ MEP
    assert patas.desde_nativo(L("AL30"), 100.0) == pytest.approx(100.0 * MEP)
    assert patas.desde_nativo(L("GD30D"), 100.0) == pytest.approx(100.0 * CCL / MEP)
    assert patas.precio_nativo(L("GD30"), None) is None and patas.precio_nativo(L("GD30"), -1) is None
    # sin FX vivo no hay precio convertido (nunca uno en otra moneda); la nativa no lo necesita
    vacio = fx_svc.FxSnapshot()
    assert patas.precio_nativo(L("GD30"), PG * CCL, fx=vacio) is None
    assert patas.precio_nativo(L("GD30D"), 63.0, fx=vacio) is None
    assert patas.precio_nativo(L("GD30C"), PG, fx=vacio) == PG


# ── Mercado / Curvas / Órdenes ───────────────────────────────────────────────
def test_la_misma_tir_por_la_fila_de_cualquier_ticker(tres_patas):
    ref, settle = tres_patas["ref"], tres_patas["settle"]
    for base, nat, cruz in (("GD30", "GD30C", "GD30D"), ("AL30", "AL30D", "AL30C")):
        # la vista por pata de Mercado / Curvas (nativa + leg)
        for leg in ("native", "ARS", "USD", "USB"):
            assert rc._row_for_code(nat, "24hs", leg, settle=settle)["tirea"] == pytest.approx(ref[base], abs=1e-9), (nat, leg)
        # por TICKER: la especie en pesos, la nativa y la pata cruzada (sin ficha)
        for tk in (base, nat, cruz):
            r = rc._row_for_code(tk, "24hs", "native", settle=settle, book=True)
            assert r is not None and r["code"] == tk and r["calc"] == nat, tk
            assert r["tirea"] == pytest.approx(ref[base], abs=1e-9), tk
            assert r["symbol"] == syms.md_symbol(tk, "24hs")                 # el libro es el de ESE ticker
            assert r["tirea_bid"] > r["tirea"] > r["tirea_offer"]            # puntas convertidas igual
    assert rc._row_for_code("ZZZZ9D", "24hs") is None


@pytest.mark.asyncio
async def test_http_libro_de_ordenes_y_mercado_por_ticker(tres_patas):
    ref = tres_patas["ref"]
    async with _client() as ac:
        for tk, base in (("GD30", "GD30"), ("GD30D", "GD30"), ("GD30C", "GD30"),
                         ("AL30", "AL30"), ("AL30D", "AL30"), ("AL30C", "AL30")):
            for url in (f"/mercado/book/{tk}", f"/ordenes/quote?code={tk}"):
                r = await ac.get(url)
                assert r.status_code == 200 and f"Libro · {tk}" in r.text, url
                assert _tir_last(r.text) == pytest.approx(ref[base], abs=6e-5), url
                # el refresh automático vuelve a pedir ESE ticker y lo resuelve de nuevo
                assert f'hx-get="/mercado/book/{tk}?plazo=24hs&amp;leg=native' in r.text, url
        gd = (await ac.get("/mercado/book/GD30D")).text
        assert "TIR con la ficha GD30C: precio × MEP ÷ CCL (se le saca el canje)" in gd and "CCL 1.500,00" in gd and "MEP 1.450,00" in gd
        assert "TIR con la ficha AL30D: precio ÷ MEP" in (await ac.get("/mercado/book/AL30")).text
        assert "TIR con la ficha AL30D: precio × CCL ÷ MEP (se le suma el canje)" in (await ac.get("/ordenes/quote?code=AL30C")).text
        assert "book-valua" not in (await ac.get("/mercado/book/GD30C")).text          # la nativa no lleva nota
        # la vista por pata sigue igual
        for leg in ("ARS", "USD", "USB"):
            assert _tir_last((await ac.get(f"/mercado/book/GD30C?leg={leg}")).text) == pytest.approx(ref["GD30"], abs=6e-5)


@pytest.mark.asyncio
async def test_ticket_de_ordenes_usa_la_moneda_del_ticker(tres_patas, monkeypatch):
    from backend.config import settings
    from backend.routes import ordenes
    monkeypatch.setattr(settings, "oms_max_notional", 1_000_000_000.0)
    monkeypatch.setattr(settings, "oms_max_notional_usd", 5_000_000.0)

    async def ticket(ac, code, px, qty):
        r = await ac.post("/ordenes/ticket", data={"code": code, "side": "buy", "ordtype": "limit", "qty": str(qty),
                                                   "price": f"{px:.2f}".replace(".", ","), "account": "C1", "plazo": "24hs"})
        assert r.status_code == 200
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))

    async with _client() as ac:
        # pesos: VN 10.000 de AL30 a 87.000 = 8,7 millones de PESOS (antes: «8.700.000 USD supera el tope»)
        for code, px in (("AL30", PA * MEP), ("GD30", PG * CCL)):
            t = await ticket(ac, code, px, 10_000)
            assert "supera el tope" not in t and "notional ≈" in t and " ARS" in t, t[:300]
        # y el tope en pesos sigue valiendo: VN 2.000.000 × 87.000 / 100 = 1.740 millones > 1.000 millones
        assert "ARS supera el tope 1,000,000,000 ARS" in await ticket(ac, "AL30", PA * MEP, 2_000_000)
        # dólares: la pata cruzada sin ficha (GD30D MEP, AL30C cable) lleva el tope en USD, como la nativa
        for code, px in (("GD30D", PG * CCL / MEP), ("AL30C", PA * MEP / CCL), ("GD30C", PG), ("AL30D", PA)):
            assert "USD supera el tope 5,000,000 USD" in await ticket(ac, code, px, 20_000_000), code
            ok = await ticket(ac, code, px, 100_000)
            assert "supera el tope" not in ok and " USD" in ok, (code, ok[:300])
    # valor técnico de referencia (sin mercado): en la moneda en que cotiza el ticker
    vt = pricing.compute_metrics("AL30D", "tir", 10.0)["valor_tecnico"]
    assert ordenes._theo_ref("AL30D") == pytest.approx(vt)
    assert ordenes._theo_ref("AL30") == pytest.approx(vt * MEP)                 # pesos
    assert ordenes._theo_ref("AL30C") == pytest.approx(vt * MEP / CCL)          # cable
    vg = pricing.compute_metrics("GD30C", "tir", 10.0)["valor_tecnico"]
    assert ordenes._theo_ref("GD30") == pytest.approx(vg * CCL) and ordenes._theo_ref("GD30D") == pytest.approx(vg * CCL / MEP)
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": fx_svc.FxSnapshot())
    assert ordenes._theo_ref("AL30") is None and ordenes._theo_ref("AL30D") == pytest.approx(vt)   # sin FX: sin referencia


# ── YAS (autofill), add-in de Excel y alertas ────────────────────────────────
def test_autofill_de_yas_en_la_convencion_de_la_ficha(tres_patas):
    ref, settle = tres_patas["ref"], tres_patas["settle"]
    assert str(pricing.bond_meta("GD30")["quote_price_cnv"]).upper() == "CLEAN"
    # GD30 es la referencia CLEAN (% del residual, sin corridos): el autofill NO es el dirty 62
    px = pricing.market_last_native("GD30", "24hs")
    nat = pricing.metrics_for_market_price("GD30C", PG, settle)
    assert px == pytest.approx(nat["precio_clean_pct"], rel=1e-9) and abs(px - PG) > 1.0
    assert pricing.compute_metrics("GD30", "precio", px, settle=settle, include_cashflows=False)["tirea"] == pytest.approx(ref["GD30"], abs=1e-9)
    # AL30 (ficha DIRTY en dólares): pesos ÷ MEP; las nativas, el último tal cual
    assert pricing.market_last_native("AL30", "24hs") == pytest.approx(PA)
    assert pricing.market_last_native("AL30D", "24hs") == PA and pricing.market_last_native("GD30C", "24hs") == PG
    assert pricing.dirty_a_cotizacion("GD30C", 62.0, settle) == 62.0 and pricing.dirty_a_cotizacion("GD30", None, settle) is None
    # sin último: None, salvo que se pida el cierre (add-in / alertas)
    st = tres_patas["store"]
    st.update_from_md(syms.md_symbol("AL35", "24hs"), {"CL": {"price": 70.0 * MEP, "date": "1"}})
    if bond_universe.get("AL35") is not None:
        assert pricing.market_last_native("AL35", "24hs") is None
        assert pricing.market_last_native("AL35", "24hs", usar_cierre=True) == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_http_snapshot_y_excel_por_ticker(tres_patas):
    ref, settle = tres_patas["ref"], tres_patas["settle"]
    tks = [("GD30", "GD30"), ("GD30D", "GD30"), ("GD30C", "GD30"), ("AL30", "AL30"), ("AL30D", "AL30"), ("AL30C", "AL30")]
    async with _client() as ac:
        j = (await ac.get("/market/snapshot/GD30")).json()
        assert j["last_native"] == pytest.approx(pricing.metrics_for_market_price("GD30C", PG, settle)["precio_clean_pct"])
        # sin precio: el add-in valúa al mercado — la misma TIR para los tres tickers
        r = await ac.post("/excel/v1/calc", json={"items": [{"tipo": "tir", "code": tk, "modo": "precio"} for tk, _ in tks]})
        assert r.status_code == 200
        res = r.json()["results"]
        for (tk, base), x in zip(tks, res):
            assert "error" not in x and x["tirea"] == pytest.approx(ref[base], abs=1e-9), (tk, x)
        assert [x["codigo"] for x in res] == ["GD30", "GD30C", "GD30C", "AL30", "AL30D", "AL30D"]
        # con precio: la pata sin ficha lleva el precio en SU moneda (se le saca / suma el canje);
        # un código con ficha conserva el basis de su ficha (GD30 = clean, como en YAS)
        r = await ac.post("/excel/v1/calc", json={"items": [
            {"tipo": "tir", "code": "GD30D", "modo": "precio", "valor": PG * CCL / MEP},
            {"tipo": "tir", "code": "AL30C", "modo": "precio", "valor": PA * MEP / CCL},
            {"tipo": "tir", "code": "GD30", "modo": "precio", "valor": 96.5},
            {"tipo": "meta", "code": "GD30D"}, {"tipo": "cashflow", "code": "AL30C"},
            {"tipo": "tir", "code": "ZZZZ9D", "modo": "precio", "valor": 50}]})
        a, b, c, meta, cf, malo = r.json()["results"]
        assert a["tirea"] == pytest.approx(ref["GD30"], abs=1e-9) and b["tirea"] == pytest.approx(ref["AL30"], abs=1e-9)
        assert c["tirea"] == pytest.approx(pricing.compute_metrics("GD30", "precio", 96.5, settle=settle, include_cashflows=False)["tirea"])
        assert meta["codigo"] == "GD30C" and meta["vencimiento"].startswith("2030")
        assert cf["codigo"] == "AL30D" and cf["n"] == len(cf["filas"]) > 0
        assert "error" in malo


def test_alertas_tir_por_ticker(tres_patas, tmp_path, monkeypatch):
    monkeypatch.setenv("ALERTAS_PATH", str(tmp_path / "alertas.json"))
    ref = tres_patas["ref"]
    for tk, base in (("GD30", "GD30"), ("GD30D", "GD30"), ("GD30C", "GD30"), ("AL30", "AL30"), ("AL30D", "AL30"), ("AL30C", "AL30")):
        assert alertas.current_value(tk, "tirea") == pytest.approx(ref[base] * 100, abs=1e-7), tk
    # el precio de la alerta es el de pantalla del ticker, sin convertir
    assert alertas.current_value("GD30", "precio") == pytest.approx(PG * CCL)
    assert alertas.current_value("GD30D", "precio") == pytest.approx(PG * CCL / MEP)
    assert alertas.current_value("ZZZZ9", "tirea") is None
    # se puede crear una alerta sobre la pata cruzada; un código inventado no
    assert alertas.add("GD30D", "tirea", ">=", 12.0) is None
    assert "desconocido" in (alertas.add("ZZZZ9D", "tirea", ">=", 12.0) or "")


# ── Switch: TIR de la pata cruzada reconvertida (default) o al precio que entra ──
def test_leg_modo_y_tir_directa_de_la_pata_cruzada(tres_patas):
    """`leg=USB.dir` / `USD.dir`: el precio de la pata dólar cruzada entra TAL CUAL
    a la ficha (pedido del desk, 26/11). Default = reconvertido por el canje."""
    ref, settle = tres_patas["ref"], tres_patas["settle"]
    assert rc._leg_modo("USB.dir") == ("USB", True) and rc._leg_modo("USD.dir") == ("USD", True)
    assert rc._leg_modo("USB") == ("USB", False) and rc._leg_modo("native") == ("native", False)
    assert rc._leg_modo("ARS.dir") == ("ARS", False) and rc._leg_modo("native.dir") == ("native", False)
    assert rc._leg_modo("") == ("native", False) and rc._leg_modo(".dir") == ("native", False)
    # global (ficha cable) visto en su pata MEP
    px_d = PG * CCL / MEP
    directa = pricing.metrics_for_market_price("GD30C", px_d, settle)["tirea"]
    conv = rc._row_for_code("GD30C", "24hs", "USB", settle=settle, book=True)
    dire = rc._row_for_code("GD30C", "24hs", "USB.dir", settle=settle, book=True)
    assert conv["symbol"] == dire["symbol"] == syms.md_symbol("GD30D", "24hs") and conv["last"] == dire["last"]
    assert conv["tirea"] == pytest.approx(ref["GD30"], abs=1e-9) and not conv["tir_directa"]
    assert dire["tirea"] == pytest.approx(directa, abs=1e-12) and dire["tir_directa"]
    assert dire["px_calc"] == pytest.approx(px_d) and conv["px_calc"] == pytest.approx(PG)
    assert dire["tirea"] < conv["tirea"] - 0.005            # la MEP es más cara en dólares: rinde menos (≈ canje / duration)
    assert dire["tirea_bid"] == pytest.approx(pricing.metrics_for_market_price("GD30C", px_d * 0.999, settle)["tirea"])
    # bonar (ficha MEP) visto en su pata cable: al revés, la cable es más barata
    al = rc._row_for_code("AL30D", "24hs", "USD.dir", settle=settle)
    assert al["tir_directa"] and al["tirea"] == pytest.approx(
        pricing.metrics_for_market_price("AL30D", PA * MEP / CCL, settle)["tirea"], abs=1e-12)
    assert al["tirea"] > ref["AL30"] + 0.005
    # lo que NO cambia: la pata propia (USD de un global, USB de un bonar), la nativa y la de pesos
    for code, leg, base in (("GD30C", "USD.dir", "GD30"), ("AL30D", "USB.dir", "AL30"), ("GD30C", "native", "GD30"),
                            ("GD30C", "ARS", "GD30"), ("AL30D", "ARS", "AL30"), ("GD30C", "ARS.dir", "GD30")):
        r = rc._row_for_code(code, "24hs", leg, settle=settle)
        assert r["tirea"] == pytest.approx(ref[base], abs=1e-9) and not r["tir_directa"], (code, leg)
    # what-if de Curvas: misma regla que la fila
    assert rc._whatif_uno("GD30C", "24hs", "USB.dir", px_d, settle)["t"] == pytest.approx(directa * 100, abs=1e-9)
    assert rc._whatif_uno("GD30C", "24hs", "USB", px_d, settle)["t"] == pytest.approx(ref["GD30"] * 100, abs=1e-7)
    # el modo directo no necesita FX; el reconvertido sí
    vacio = fx_svc.FxSnapshot()
    assert rc._row_for_code("GD30C", "24hs", "USB.dir", fx=vacio, settle=settle)["tirea"] == pytest.approx(directa, abs=1e-12)
    assert rc._row_for_code("GD30C", "24hs", "USB", fx=vacio, settle=settle)["tirea"] is None


@pytest.mark.asyncio
async def test_http_switch_de_tir_en_curvas_mercado_y_libro(tres_patas):
    ref, settle = tres_patas["ref"], tres_patas["settle"]
    directa = pricing.metrics_for_market_price("GD30C", PG * CCL / MEP, settle)["tirea"]

    def tir_de(html: str, code: str) -> str:
        fila = re.search(r'<tr[^>]*data-code="%s".*?</tr>' % code, html, re.S)
        assert fila, code
        return fila.group(0)

    async with _client() as ac:
        # páginas: el switch existe, default reconvertido, y `leg=USB.dir` lo deja prendido
        for pag in ("/curves", "/mercado"):
            h = (await ac.get(f"{pag}?curve=globales")).text
            assert "data-leg-dir" in h and '<option value="USB" data-leg="USB"' in h
            assert re.search(r'<option value="1"\s*>Al precio que entra', h)
            h = (await ac.get(f"{pag}?curve=globales&leg=USB.dir")).text
            assert re.search(r'<option value="USB\.dir" data-leg="USB" selected', h)
            assert re.search(r'<option value="1" selected>Al precio que entra', h)
        # tablas
        for url in ("/curves/table?curve=globales&only_quoting=true", "/mercado/table?curve=globales&only_quoting=true"):
            conv = (await ac.get(url + "&leg=USB")).text
            dire = (await ac.get(url + "&leg=USB.dir")).text
            assert "leg USB" in conv and "TIR reconvertida (canje)" in conv and "tir-dir" not in conv
            assert "leg USB" in dire and "TIR al precio de la pata (sin reconvertir)" in dire
            f_conv, f_dire = tir_de(conv, "GD30C"), tir_de(dire, "GD30C")
            assert f"{ref['GD30'] * 100:.2f}".replace(".", ",") in f_conv
            assert f"{directa * 100:.2f}".replace(".", ",") in f_dire and "tir-dir" in f_dire
        # el libro que abre la fila lleva el modo en el link y lo conserva en su refresh
        dire = (await ac.get("/mercado/table?curve=globales&only_quoting=true&leg=USB.dir")).text
        assert "/mercado/book/GD30C?plazo=24hs&amp;leg=USB.dir" in dire or "/mercado/book/GD30C?plazo=24hs&leg=USB.dir" in dire
        b = (await ac.get("/mercado/book/GD30C?plazo=24hs&leg=USB.dir")).text
        assert _tir_last(b) == pytest.approx(directa, abs=6e-5)
        assert "al precio de la pata, sin reconvertir por el canje (TIR directa)" in b and "leg=USB.dir" in b
        assert _tir_last((await ac.get("/mercado/book/GD30C?plazo=24hs&leg=USB")).text) == pytest.approx(ref["GD30"], abs=6e-5)
        # delta por filas, what-if y datos del gráfico: el mismo modo
        r = await ac.get("/mercado/rows?curve=globales&only_quoting=true&leg=USB.dir&since=0&order=x")
        assert r.status_code == 200
        j = (await ac.get(f"/curves/whatif?curve=globales&leg=USB.dir&price_GD30C={PG * CCL / MEP:.6f}")).json()
        assert j["rows"]["GD30C"]["t"] == pytest.approx(directa * 100, abs=1e-6)
        g_conv = (await ac.get("/graficos/data?curve=globales&leg=USB&nss=0")).json()
        g_dire = (await ac.get("/graficos/data?curve=globales&leg=USB.dir&nss=0")).json()
        i = g_conv["codes"].index("GD30C")
        y_conv = next(v for v in (g_conv["usd"][i], g_conv["ars"][i]) if v is not None)
        i = g_dire["codes"].index("GD30C")
        y_dire = next(v for v in (g_dire["usd"][i], g_dire["ars"][i]) if v is not None)
        assert y_conv == pytest.approx(ref["GD30"] * 100, abs=1e-3) and y_dire == pytest.approx(directa * 100, abs=1e-3)
