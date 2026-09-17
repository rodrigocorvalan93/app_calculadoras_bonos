"""Copiar gráfico (⧉) como imagen — SVG estilados por CLASES CSS.

El price action y la distribución de Históricos (y Futuros) pintan con clases
(`.fut-chart .pa-band1 { fill: var(--accent); opacity: .14 }`): al copiar, la
imagen suelta no ve el CSS de la página y caía al default de SVG (relleno
negro, sin stroke, fuente serif) — salía una banda negra sin línea. copySvg
ahora clona el SVG con el estilo CALCULADO inline (harness con el JS real:
tests/chart_copy_harness.cjs). Sólo corre al click: nada de esto toca el
motor live ni un request."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_copy_svg_lleva_los_estilos_calculados_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "chart_copy_harness.cjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode in (0, 1), r.stderr
    out = json.loads(r.stdout)
    assert out["boton_inyectado"]
    assert out["banda_con_color_y_opacidad"], out["svg"]          # la banda ya no es negra
    assert out["linea_con_stroke_sin_fill"], out["svg"]            # la línea ya no desaparece
    assert out["tendencia_dasharray"], out["svg"]
    assert out["texto_con_fuente_y_color"], out["svg"]             # fuente del sistema, no serif
    assert out["etiqueta_apagada_sigue_oculta"], out["svg"]        # display:none se respeta
    assert out["var_resuelta_y_fallback"], out["svg"]              # var(--x, fb) → color
    assert out["fuente_en_la_raiz"], out["svg"]
    assert out["tamano_fijo"] and out["xmlns"] and out["titles_sin_estilo"]
    assert out["svg_vivo_intacto"]                                 # el DOM en pantalla no cambia
    assert out["una_lectura_por_nodo"], out["fallos"]              # una getComputedStyle por nodo
    assert out["ok"], out["fallos"]


def test_copy_svg_fragmentos_en_app_js() -> None:
    """Sin node: el bloque existe y clona con estilos calculados (no serializa
    el SVG vivo a secas)."""
    js = (ROOT / "backend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    bloque = js.split("// ── Copiar gráfico al portapapeles", 1)[1]
    for frag in ("function inlineComputed", "svg.cloneNode(true)", "getComputedStyle(el)",
                 "serializeToString(clone)", "clone.setAttribute('width'", "cs.display === 'none'"):
        assert frag in bloque, frag
    assert "serializeToString(svg)" not in bloque
