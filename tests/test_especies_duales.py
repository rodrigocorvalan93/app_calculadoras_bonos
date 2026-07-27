"""Duales CER/TAMAR — consistencia de fichas.

Regresión TXMJ8v: había DOS definiciones del dict en especies.py y la segunda
(un copy-paste de TXMJ9v) pisaba a la correcta con Cupón/Spread 0 en vez de 3,
Código "TXMJ8" en vez de "TXMJ8v", la emisión de TXMJ9 y la fecha de cupón
corrida un día. Efecto visible: margen TAMAR t+4 cuando el mercado (y la
cuenta bien hecha) daba t+6,82.
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path


def test_txmj8v_ficha_correcta() -> None:
    import especies

    b = especies.TXMJ8v
    assert b.codigo == "TXMJ8v"
    assert b.cupon_spread == 3.0            # margen de emisión TAMAR+3
    assert b.tipo_tasa_interes == "VARIABLE_CAP" and b.index == "TAMAR"
    assert b.emision == date(2026, 5, 15)
    assert b.vencimiento == date(2028, 6, 30)
    # el único cupón cae en el vencimiento (no un día antes)
    assert [f.date() if hasattr(f, "date") else f for f in [b.fechas_cupon[-1]]][0] \
        .strftime("%d/%m/%Y") == "30/06/2028"


def test_patas_tamar_duales_con_spread() -> None:
    """Todas las patas 'v' de los duales CER/TAMAR capitalizan TAMAR + 3."""
    import especies

    for name in ("TXMJ8v", "TXMJ9v", "TXMD8v", "TXMD9v", "TXMJ0v"):
        b = getattr(especies, name)
        assert b.tipo_tasa_interes == "VARIABLE_CAP" and b.index == "TAMAR", name
        assert b.cupon_spread == 3.0, f"{name}: spread {b.cupon_spread} != 3"


def test_especies_sin_dicts_duplicados() -> None:
    """Ninguna ficha definida dos veces a nivel módulo: la segunda pisa a la
    primera en silencio — exactamente cómo se rompió TXMJ8v."""
    import especies

    src = Path(especies.__file__).read_text(encoding="utf-8")
    seen: dict = {}
    dups = []
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Dict)):
            name = node.targets[0].id
            if name in seen:
                dups.append(f"{name} (líneas {seen[name]} y {node.lineno})")
            seen[name] = node.lineno
    assert not dups, f"Fichas duplicadas en especies.py: {dups}"
