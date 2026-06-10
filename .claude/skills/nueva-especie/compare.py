#!/usr/bin/env python3
"""Compara una especie NUEVA contra su COMPARABLE (el bono espejado) — control de carga.

Uso (desde la raíz del repo):
    python .claude/skills/nueva-especie/compare.py <NUEVO> <COMPARABLE>

Idea: un bono nuevo se carga ESPEJANDO uno existente del mismo tipo. Entonces:
  • los campos ESTRUCTURALES (clasificación, tipo, ajuste, convenciones, lags)
    deben ser IDÉNTICOS al comparable — si difieren, casi seguro hay un error;
  • los campos PROPIOS del papel (código, ISIN, nombre, vencimiento) DEBEN diferir
    — si quedaron iguales, copiaste de más.

Exit code 0 si la estructura coincide y los propios difieren; 1 si algo no cuadra.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Campos que el papel nuevo COMPARTE con su comparable (deben coincidir):
_STRUCT = [
    "clasificacion", "industria", "moneda", "ajuste_sobre_capital",
    "tipo_tasa_interes", "index", "convencion_base", "convencion_devengamiento",
    "tipo_amortizacion", "step_up", "factor_capitalizacion",
    "dias_lag_ajuste", "dias_lag_ajuste_base", "quote_price_cnv",
]
# Campos PROPIOS del papel (deben diferir entre dos bonos distintos):
_OWN = ["codigo", "isin", "nombre_security", "vencimiento"]


def _g(o, a):
    return getattr(o, a, None)


def main(argv) -> int:
    if len(argv) != 2:
        print("uso: python .claude/skills/nueva-especie/compare.py <NUEVO> <COMPARABLE>")
        return 2
    new_code, cmp_code = argv
    try:
        from backend.services import bond_universe
    except Exception as exc:  # noqa: BLE001
        print(f"[X] No pude importar el backend (¿desde la raíz del repo?): {exc}")
        return 1
    bond_universe.ensure_loaded()
    a, b = bond_universe.get(new_code), bond_universe.get(cmp_code)
    if a is None:
        print(f"[X] {new_code} no está en el universo (¿faltó alguna de las 3 ediciones?).")
        return 1
    if b is None:
        print(f"[X] comparable {cmp_code} no está en el universo.")
        return 1

    bad = 0
    print(f"\nESTRUCTURA  {new_code}  vs  {cmp_code}   (deben COINCIDIR)")
    for f in _STRUCT:
        va, vb = _g(a, f), _g(b, f)
        ok = va == vb
        bad += (not ok)
        print(f"  [{'ok' if ok else '!!'}] {f:26} {str(va):28} {'==' if ok else '!='} {vb}")

    same = 0
    print(f"\nPROPIOS DEL PAPEL  {new_code}  vs  {cmp_code}   (deben DIFERIR)")
    for f in _OWN:
        va, vb = _g(a, f), _g(b, f)
        diff = va != vb
        same += (not diff)
        print(f"  [{'ok' if diff else '!!'}] {f:26} {str(va):28} {'!=' if diff else '=='} {vb}")

    print()
    if bad:
        print(f"[X] {bad} campo(s) estructural(es) DIFIEREN del comparable → revisá la carga.")
        return 1
    if same:
        print(f"[X] {same} campo(s) propios quedaron IGUALES al comparable → ¿copiaste de más?")
        return 1
    print("[OK] Estructura idéntica al comparable y campos propios distintos. Carga consistente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
