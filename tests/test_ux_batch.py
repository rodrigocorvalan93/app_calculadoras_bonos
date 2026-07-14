"""Batch UX: PWA (manifest + íconos + metas), Ctrl+K (/market/codes + palette)
y heatmap de variaciones (macro fx.heat)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── PWA ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_manifest_e_iconos_servidos() -> None:
    async with _client() as ac:
        m = await ac.get("/static/manifest.webmanifest")
        assert m.status_code == 200
        assert "manifest" in m.headers["content-type"] or "json" in m.headers["content-type"]
        data = m.json()
        assert data["display"] == "standalone" and data["short_name"] == "Bonos"
        assert {i["sizes"] for i in data["icons"]} >= {"192x192", "512x512"}
        for path in ("/static/icons/icon-180.png", "/static/icons/icon-192.png",
                     "/static/icons/icon-512.png"):
            r = await ac.get(path)
            assert r.status_code == 200 and r.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_head_tiene_metas_pwa() -> None:
    async with _client() as ac:
        r = await ac.get("/yas")
    assert r.status_code == 200
    assert 'rel="manifest"' in r.text
    assert 'name="theme-color"' in r.text
    assert 'rel="apple-touch-icon"' in r.text
    assert 'apple-mobile-web-app-capable' in r.text


# ── Ctrl+K ───────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_market_codes_para_ctrl_k() -> None:
    async with _client() as ac:
        r = await ac.get("/market/codes")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 100
        al30 = next(i for i in items if i["c"] == "AL30")
        assert al30["v"].startswith("20")                     # vencimiento ISO
        # 2ª llamada: cache por proceso → misma cantidad, sin recomputar
        r2 = await ac.get("/market/codes")
        assert len(r2.json()["items"]) == len(items)


@pytest.mark.asyncio
async def test_palette_en_app_js() -> None:
    async with _client() as ac:
        js = await ac.get("/static/js/app.js")
        css = await ac.get("/static/css/style.css")
    assert "ck-overlay" in js.text and "/market/codes" in js.text
    assert "#ck-panel" in css.text
    # pase mobile: sólo bajo media query (desktop intacto)
    assert "max-width: 980px" in css.text


# ── Heatmap de variaciones ───────────────────────────────────────────────────
def test_macro_heat_intensidad_y_signo() -> None:
    from jinja2 import Environment, FileSystemLoader
    from backend.main import TEMPLATES_DIR

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    tpl = env.from_string(
        '{% import "partials/_fx_macros.html" as fx %}'
        "[{{ fx.heat(v, cap=cap) }}]")
    up = tpl.render(v=0.01, cap=0.02)          # +1% con cap 2% → verde a media intensidad
    assert "34,197,94" in up and "0.19" in up
    dn = tpl.render(v=-0.05, cap=0.02)         # −5% → rojo saturado al máximo (0.38)
    assert "239,68,68" in dn and "0.38" in dn
    assert tpl.render(v=None, cap=0.02) == "[]"          # sin dato → sin estilo
    nan = float("nan")
    assert tpl.render(v=nan, cap=0.02) == "[]"           # NaN → sin estilo
