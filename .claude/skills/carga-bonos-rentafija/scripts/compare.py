#!/usr/bin/env python3
"""Compara una especie NUEVA contra su COMPARABLE — control de carga completo.

Uso (desde la raíz del repo):
    python3 .claude/skills/carga-bonos-rentafija/scripts/compare.py <NUEVO> <COMPARABLE>

Tres controles:
  1. SET DE HERMANAS: el comparable define qué fichas existen ('', 'j', 'v',
     'C', 'D'). El nuevo tiene que tener LAS MISMAS — una hermana faltante es
     el error de alta más común (p. ej. cargar el dual sin la pata 'v').
  2. ESTRUCTURA: por cada par (NUEVO+suf vs COMP+suf), los campos estructurales
     (clasificación, ajuste, tasa, convenciones, lags, quote) deben ser
     IDÉNTICOS — difieren ⇒ casi seguro error de carga. La `industria` se
     compara salvo el sufijo " Proyectado"-like ya implícito en el par.
  3. PROPIOS: código / ISIN / nombre / vencimiento deben DIFERIR — iguales ⇒
     copiaste de más.

Exit 0 si todo OK; 1 si hay algo que corregir.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_SUFFIXES = ("", "j", "v", "C", "D")

_STRUCT = [
    "clasificacion", "industria", "moneda", "ajuste_sobre_capital",
    "tipo_tasa_interes", "index", "convencion_base", "convencion_devengamiento",
    "tipo_amortizacion", "step_up", "factor_capitalizacion",
    "dias_lag_ajuste", "dias_lag_ajuste_base", "quote_price_cnv",
]
_OWN = ["codigo", "isin", "nombre_security", "vencimiento"]


def _g(o, a):
    return getattr(o, a, None)


def _siblings(get, base: str) -> dict:
    return {s: get(base + s) for s in _SUFFIXES if get(base + s) is not None}


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    new_code, cmp_code = argv
    try:
        from backend.services import bond_universe
    except Exception as exc:  # noqa: BLE001
        print(f"[X] No pude importar el backend (¿desde la raíz del repo?): {exc}")
        return 1
    bond_universe.ensure_loaded()
    get = bond_universe.get
    if get(cmp_code) is None:
        print(f"[X] comparable {cmp_code} no está en el universo.")
        return 1

    cmp_set = _siblings(get, cmp_code)
    new_set = _siblings(get, new_code)
    rc = 0

    print(f"\nSET DE HERMANAS   comparable {cmp_code}: {{{', '.join(repr(s) for s in cmp_set)}}}")
    for suf in cmp_set:
        present = suf in new_set
        rc += (not present)
        print(f"  [{'ok' if present else '!!'}] {new_code}{suf:<2} "
              f"{'presente' if present else 'FALTA — cargá esta ficha (las 3 ediciones)'}")
    extra = [s for s in new_set if s not in cmp_set]
    if extra:
        print(f"  [??] {new_code} tiene hermanas que el comparable no: {extra} — verificá que sea intencional.")

    for suf, cobj in cmp_set.items():
        nobj = new_set.get(suf)
        if nobj is None:
            continue
        bad = same = 0
        print(f"\nESTRUCTURA  {new_code}{suf}  vs  {cmp_code}{suf}   (deben COINCIDIR)")
        for f in _STRUCT:
            va, vb = _g(nobj, f), _g(cobj, f)
            ok = va == vb
            bad += (not ok)
            print(f"  [{'ok' if ok else '!!'}] {f:26} {str(va):30} {'==' if ok else '!='} {vb}")
        print(f"PROPIOS  {new_code}{suf}  vs  {cmp_code}{suf}   (deben DIFERIR)")
        for f in _OWN:
            va, vb = _g(nobj, f), _g(cobj, f)
            diff = va != vb
            same += (not diff)
            print(f"  [{'ok' if diff else '!!'}] {f:26} {str(va):30} {'!=' if diff else '=='} {vb}")
        rc += bad + same

    print()
    if rc:
        print(f"[X] {rc} problema(s): hermanas faltantes y/o campos que no cuadran → revisá la carga.")
        return 1
    print("[OK] Set de hermanas completo, estructura idéntica al comparable, propios distintos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
