"""Cuadro Target vs Actual por categoría (Posiciones). El estado (targets) vive
en localStorage del cliente; el server sólo sirve el % actual por categoría y la
caja Alpine. Acá: markup Alpine correcto + endpoint sin crash."""
from __future__ import annotations

import pytest


def test_targets_partial_alpine_markup():
    from backend.main import app
    env = app.state.templates.env
    html = env.get_template("partials/posiciones_targets.html").render(
        cat_actual=[{"cat": "Globales", "actual": 0.14}, {"cat": "DLK", "actual": 0.16}],
        fondo=99, nombre="G6")
    assert "posTargets(99" in html                 # Alpine con el fondo como clave
    assert "Globales" in html and "DLK" in html
    assert "tgt-tbl" in html and "tgt-copy" in html  # tabla + botón copiar
    assert "0.14" in html and "0.16" in html         # actuals embebidos (tojson)
    assert "Target" in html and "Actual" in html and "Desvío" in html


def _extract_xdata(html: str):
    """Valor del atributo x-data del card, parseado como lo haría el browser.
    Si el atributo está mal formado (el `"` del JSON cierra el atributo en
    comillas dobles), el parser devuelve el call TRUNCADO → el test lo caza."""
    from html.parser import HTMLParser

    grabbed = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            v = dict(attrs).get("x-data")
            if v and v.startswith("posTargets"):
                grabbed.append(v)

    P().feed(html)
    return grabbed[0] if grabbed else None


def test_targets_xdata_attribute_well_formed():
    # Regresión: `tojson` emite `"` sin escapar; en un atributo con comillas
    # dobles el primer `"` del JSON cerraba x-data y Alpine no arrancaba (caja
    # invisible por x-cloak). Debe ir en comillas simples → JSON intacto.
    from backend.main import app
    env = app.state.templates.env
    html = env.get_template("partials/posiciones_targets.html").render(
        cat_actual=[{"cat": "Globales", "actual": 0.14}, {"cat": "DLK", "actual": 0.16}],
        fondo=99, nombre="G6")
    xd = _extract_xdata(html)
    assert xd is not None, "no se encontró un x-data='posTargets(...)' bien formado"
    assert xd.startswith("posTargets(99,") and xd.endswith(")")   # call completo, no truncado
    assert '"cat"' in xd and '"actual"' in xd                     # el JSON entró entero


def test_targets_partial_empty_fondo_renders_nothing():
    from backend.main import app
    env = app.state.templates.env
    html = env.get_template("partials/posiciones_targets.html").render(
        cat_actual=[], fondo=None, nombre="")
    assert html.strip() == ""                       # sin fondo → caja vacía


@pytest.mark.asyncio
async def test_targets_endpoint_no_crash():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe
    bond_universe.ensure_loaded()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        assert (await ac.get("/posiciones/targets")).status_code == 200            # sin fondo
        assert (await ac.get("/posiciones/targets?fondo=1&plazo=24hs")).status_code == 200
        pg = await ac.get("/posiciones")
        assert pg.status_code == 200
        assert 'id="pos-targets"' in pg.text and "function posTargets" in pg.text
        # el contenedor NO lleva md-update (no se pisa la edición en cada tick)
        import re
        m = re.search(r'id="pos-targets"[^>]*hx-trigger="([^"]*)"', pg.text)
        assert m and "md-update" not in m.group(1) and "change from:select" in m.group(1)


@pytest.mark.asyncio
async def test_pos_fondo_es_estatica_con_boton_refresh():
    """La tabla de tenencias (con el Last editable) NO debe auto-refrescarse en cada
    tick BYMA — pisaba lo que el usuario tipeaba. Es estática + botón ↻ Precios BYMA."""
    import re

    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe
    bond_universe.ensure_loaded()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        pg = await ac.get("/posiciones")
    assert pg.status_code == 200
    # el contenedor de tenencias NO escucha md-update (no se refresca solo)
    m = re.search(r'id="pos-fondo"[^>]*>', pg.text)
    assert m and "md-update" not in m.group(0)
    # botón manual para traer precios BYMA, apuntando al panel
    assert "Precios BYMA" in pg.text
    assert re.search(r'hx-get="/posiciones/table"[^>]*hx-target="#pos-fondo"', pg.text)
