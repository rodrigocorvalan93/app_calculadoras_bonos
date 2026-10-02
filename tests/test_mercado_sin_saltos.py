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
    assert "[data-cols-fijas] > table.mercado-table, [data-cols-fijas] > table.curve-table { table-layout: fixed; }" in CSS
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
