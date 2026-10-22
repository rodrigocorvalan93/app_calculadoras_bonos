"""Mercado: el recuadro no cambia de tamaño al actualizarse (02/10).

Medido con Playwright sobre un server con ticks sintéticos (45 s, ~1 tick/s):
en el panel de acciones (swap completo en cada tick) la tabla saltaba 4 px por
un frame en CADA tick — el botón ⧉ de copiar vive adentro del swap, se
re-inyectaba recién en afterSettle y su margen negativo (-18 px) no compensaba
su alto real (14 px) —, el flash de cada celda traía una escala (tick-pop,
+4,5 % por 0,22 s) que agrandaba el recuadro de la celda, el contenedor se
atenuaba (opacity .93) en cada request y el scroll horizontal de la tabla
volvía a 0 con cada swap. Después: 0 cambios de alto del card, 0 frames sin
botón, 0 layout shifts de la tabla y scroll conservado. El flash de color
(tick-up / tick-down) y la cadencia por tick NO cambian: sólo deja de moverse
el recuadro."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "backend/static/css/style.css").read_text(encoding="utf-8")
JS = (ROOT / "backend/static/js/app.js").read_text(encoding="utf-8")
CSS_SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _bloques(selector: str) -> list[str]:
    """Cuerpos de las reglas cuyo selector es exactamente `selector` (al inicio de línea)."""
    return re.findall(r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS_SIN_COMENTARIOS)


def test_boton_copiar_tiene_alto_neto_cero() -> None:
    (b,) = _bloques(".tbl-copy")
    assert "height: 14px" in b and "box-sizing: border-box" in b
    assert "margin: 0 2px -14px auto" in b          # margen negativo = alto exacto → cero corrimiento
    assert "-18px" not in b


def test_boton_copiar_grafico_svg_no_corre_el_grafico() -> None:
    """Forwards · Histórico del forward (desk 22/10): el ⧉ de los SVG del
    server se inyectaba sólo en afterSettle (20 ms después del swap) y era un
    bloque con margin-bottom -22 px entre el margin-bottom de las tarjetas
    (.metrics-grid, 12 px) y el margin-top del svg (10 px): rompía el colapso de
    esos márgenes (12 + 18 − 22 + 10 = 18 en vez de 12) → en cada md-update el
    svg y el pie bajaban 6 px por un frame y el botón parpadeaba. Medido con
    Playwright sobre el server con ticks (8 s, ~1 tick/s): antes 10 frames sin
    botón, 16 cambios de posición (svg 1381 → 1387 → 1381, card 626 → 632);
    después 0 / 0 / 0 layout shifts. Ahora el botón es un float a la derecha con
    caja de margen de alto cero (fuera del flujo: esté o no, nada se mueve) y
    se inyecta en afterSwap, antes del primer paint, como el ⧉ de las tablas."""
    (b,) = _bloques(".chart-copy.chart-copy-inline")
    assert "float: right" in b and "position: relative" in b
    assert "height: 18px" in b and "box-sizing: border-box" in b
    assert "margin: 0 2px -18px 0" in b             # margen negativo = alto exacto → caja de margen de alto 0
    assert "-22px" not in b and "auto;" not in b.replace("top: auto", "").replace("right: auto", "")
    i = JS.index("function injectSvg(root)")
    bloque = JS[i:i + 2500]
    assert "document.body.addEventListener('htmx:afterSwap', function (evt) { injectSvg(" in bloque
    assert "document.body.addEventListener('htmx:afterSettle', function (evt) { injectSvg(" in bloque
    assert "if (prev && prev.classList && prev.classList.contains('chart-copy')) return;" in bloque   # idempotente
    # Y un tick que no cambia el HTML del histórico no lo swapea (cero teardown
    # del svg por tick): opt-in al skip de swaps idénticos de app.js.
    tpl = (ROOT / "backend/templates/partials/forwards_body.html").read_text(encoding="utf-8")
    assert re.search(r'<div id="fwd-hist"[^>]*\bdata-skip-same\b', tpl), tpl[tpl.index('id="fwd-hist"') - 20:][:200]
    assert "if (t.__lastHtml === html) { evt.detail.shouldSwap = false; return; }" in JS
    # Un .table-scroll SIN tabla adentro (Series diarias / Curva por fechas
    # envuelven el svg solo) no recibe el ⧉ de "copiar tabla": quedaba un
    # segundo ⧉ que no copiaba nada, encimado al del gráfico (revisión 22/10).
    j = JS.index("root.querySelectorAll('.table-scroll').forEach(function (ts) {")
    assert "if (!ts.querySelector('table')) return;" in JS[j:j + 600]


def test_flash_es_solo_color_sin_escala() -> None:
    assert "tick-pop" not in CSS_SIN_COMENTARIOS     # ni keyframes ni una segunda animación
    up, down = _bloques(".tick-up"), _bloques(".tick-down")
    assert up and down
    for b in up + down:
        assert "transform" not in b and "font-weight" not in b and "padding" not in b
    assert any("animation: tick-up" in b for b in up) and any("animation: tick-down" in b for b in down)


def test_paneles_por_delta_no_se_atenuan_en_el_swap() -> None:
    assert '[data-flash-scope]:not([hx-trigger*="md-update"]):not([data-delta-scope]).htmx-request' in CSS
    # Mercado es el panel por delta: su trigger no lleva md-update (entra por app.js)
    tpl = (ROOT / "backend/templates/mercado.html").read_text(encoding="utf-8")
    assert 'data-delta-scope' in tpl and 'hx-trigger="refresh, every 30s"' in tpl


def test_boton_copiar_se_inyecta_en_after_swap_y_el_scroll_se_conserva() -> None:
    assert "document.body.addEventListener('htmx:afterSwap', function (evt) { inject(" in JS
    assert "document.body.addEventListener('htmx:afterSettle', function (evt) { inject(" in JS
    i = JS.index("Scroll horizontal de las tablas a través de un swap completo")
    bloque = JS[i:i + 2500]
    assert "evt.detail.shouldSwap === false" in bloque           # un swap cancelado no guarda nada
    assert "ts[i].scrollLeft = sl[i]" in bloque and "htmx:afterSwap" in bloque


def test_anchos_de_columna_congelados_con_ratchet() -> None:
    # Medido: con table-layout auto el VWAP pasaba de 85 a 73 px y corría las 6
    # columnas de la derecha; app.js mide una vez, fija los th y sólo ensancha.
    assert "[data-cols-fijas] > table { table-layout: fixed; }" in CSS      # también las tablas del libro
    i = JS.index("Anchos de columna estables en las tablas live (ratchet)")
    bloque = JS[i:JS.index("Scroll horizontal de las tablas a través de un swap completo")]
    assert "p.setAttribute('data-cols-fijas', '')" in bloque          # fixed vía el padre (sobrevive al settle de htmx)
    assert "tbl.style.tableLayout" not in bloque                       # nunca inline en la <table id=…>
    assert "scrollWidth > cs[c].clientWidth" in bloque                 # desborde → ratchet
    assert "Math.max(a[i] || 0, b[i] || 0)" in bloque                  # los anchos sólo crecen
    assert "window.__anchosCol.chequear(tbl, aplicadas)" in JS         # el delta por filas también chequea


def test_metrica_del_feed_no_corre_la_topbar() -> None:
    # '14 t/min · 9 ms' cambia de largo con los dígitos: ancho mínimo fijo para
    # que el botón «más» de la navegación no se corra con cada actualización.
    (b,) = _bloques(".live-meta")
    assert re.search(r"min-width:\s*\d", b), b
