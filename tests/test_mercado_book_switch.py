"""Libro (Mercado / Órdenes): métrica por nivel elegible (?y=tirea|tem|tna|
margen) desde el MISMO dict de métricas cacheado que ya daba la TIREA, chips en
el título que se recuerdan en el navegador, Acum sin flash; y las dos causas
del reporte del desk — bid y offer apilados (el botón ⧉ ocupaba una celda de
la grilla) y el parpadeo a 1 Hz (dim del panel en cada request live)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.locale_ar import fmt_pct as ar_pct          # el filtro Jinja `ar_pct`
from backend.services import bond_universe, marketdata_store, pricing, symbols as syms

ROOT = Path(__file__).resolve().parents[1]


def _tamar_corp() -> str:
    from backend.services import curves
    bond_universe.ensure_loaded()
    cods = sorted(curves.build_curve_codes().get("corp_tamar") or [])
    if not cods:
        pytest.skip("sin ONs TAMAR en el universo")
    return cods[0]


def _sembrar(code: str) -> str:
    sym = syms.md_symbol(code, "24hs")
    marketdata_store.get_store().update_from_md(sym, {
        "LA": {"price": 100.0, "size": 1000}, "CL": {"price": 99.5},
        "BI": [{"price": 99.9, "size": 5000}, {"price": 99.8, "size": 12000}],
        "OF": [{"price": 100.1, "size": 7000}, {"price": 100.2, "size": 9000}],
    })
    return sym


@pytest.mark.asyncio
async def test_metrica_por_nivel_tem_tna_margen_y_fallback() -> None:
    code = _tamar_corp()
    _sembrar(code)
    settle = pricing.settlement_date_str("24hs")
    m = pricing.metrics_for_market_price(code, 99.9, settle) or {}
    assert m.get("tirea") is not None
    async with AsyncClient(transport=ASGITransport(app=__import__("backend.main", fromlist=["app"]).app),
                           base_url="http://t") as ac:
        r = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs", "y": "tem"})
        assert r.status_code == 200
        assert "<th>Bid TEM</th>" in r.text and "<th>Offer TEM</th>" in r.text
        assert ar_pct(m["tem"], 2) in r.text                      # el valor del nivel = el del dict cacheado
        assert 'data-book-y="tem"' in r.text and 'class="hc-preset active" data-book-y="tem"' in r.text
        assert 'data-noflash' in r.text                              # el Acum no flashea
        # el self-refresh del libro conserva la métrica elegida
        sr = re.search(r'hx-get="([^"]+)"\s+hx-trigger="md-update', r.text)
        assert sr and "y=tem" in sr.group(1).replace("&amp;", "&")
        # TNA con la convención del bono en la cabecera
        conv = pricing.tna_convention(bond_universe.get(code))[0]
        t = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs", "y": "tna"})
        assert f"<th>Bid TNA {conv}</th>" in t.text and ar_pct(m["tna"], 2) in t.text
        # Margen: sólo si el bono tiene benchmark (TAMAR/BADLAR); si no, cae a TIREA
        mg = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs", "y": "margen"})
        if m.get("margen_tna") is not None and m["margen_tna"] == m["margen_tna"]:
            assert "<th>Bid Margen</th>" in mg.text and ar_pct(m["margen_tna"], 2) in mg.text
        else:
            assert "<th>Bid TIREA</th>" in mg.text and 'data-book-y="margen"' not in mg.text
        # y inválido → TIREA (default) sin error
        z = await ac.get(f"/mercado/book/{code}", params={"plazo": "24hs", "y": "zzz"})
        assert z.status_code == 200 and "<th>Bid TIREA</th>" in z.text
        # el libro embebido en Órdenes deja pasar la métrica
        q = await ac.get("/ordenes/quote", params={"code": code, "plazo": "24hs", "y": "tem"})
        assert q.status_code == 200 and "<th>Bid TEM</th>" in q.text


def test_front_no_apila_ni_parpadea() -> None:
    """app.js: en un padre grid/flex el botón ⧉ y la tabla van en un wrapper
    (un solo ítem de grilla); el Acum se saltea en el diff de flashes; el
    switch se guarda en localStorage y viaja en cada pedido del libro. CSS:
    el dim al cargar no aplica a paneles que se refrescan con md-update."""
    js = (ROOT / "backend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "backend" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert "w.className = 'tbl-wrap'" in js and "getComputedStyle(parent).display" in js
    assert "hasAttribute('data-noflash')" in js
    assert "'book-y'" in js and "/mercado/book/" in js and "/ordenes/quote" in js and "htmx:configRequest" in js
    assert '[data-flash-scope]:not([hx-trigger*="md-update"]).htmx-request' in css
    assert "[data-flash-scope].htmx-request {" not in css
    assert ".tbl-wrap" in css
