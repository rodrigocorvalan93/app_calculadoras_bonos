#!/usr/bin/env python3
"""Preview de clasificación de una especie — verificación post-alta.

Uso (desde la raíz del repo):
    python .claude/skills/carga-bonos-rentafija/scripts/preview.py <TICKER> [<TICKER> ...]

Carga el universo (especies.py) y, por cada ticker, muestra los campos
discriminantes + a qué Curva(s) y a qué Categoría/Tasa/Calificación de
Posiciones cae. Sirve para:
  • elegir/inspeccionar un bono COMPARABLE antes de cargar uno nuevo, y
  • VERIFICAR que un alta quedó bien (carga y cae donde esperabas).

Exit code 0 si todos los tickers cargan; 1 si alguno no está en el universo.
"""
from __future__ import annotations

import os
import sys

# Al correr un script por ruta, Python pone en sys.path la carpeta del script
# (.claude/skills/nueva-especie), no la raíz del repo. Agregamos la raíz (3
# niveles arriba) para poder importar `backend` y `especies` sin importar el cwd.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _fmt(o, attr):
    return getattr(o, attr, None)


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    try:
        from backend.routes.posiciones import _calif, _categoria, _tasa
        from backend.services import bond_universe, curves
    except Exception as exc:  # noqa: BLE001
        print(f"[X] No pude importar el backend (¿corrés desde la raíz del repo?): {exc}")
        return 1

    bond_universe.ensure_loaded()
    groups = curves.build_curve_codes()

    # Expandir cada ticker a sus fichas hermanas presentes ('', j, v, C, D):
    # el olvido de una hermana es el error de alta más común.
    expanded = []
    for code in argv:
        sibs = [code + s for s in ("", "j", "v", "C", "D")
                if bond_universe.get(code + s) is not None]
        expanded.extend(sibs or [code])
        if len(sibs) > 1:
            print(f"[i] {code}: {len(sibs)} fichas hermanas → {', '.join(sibs)}")

    rc = 0
    for code in expanded:
        o = bond_universe.get(code)
        if o is None:
            rc = 1
            print(f"\n[X] {code}: NO está en el universo.")
            print("    Para que cargue, en especies.py tienen que estar las 3 cosas:")
            print(f"      1) el dict        {code} = {{ ... }}")
            print(f"      2) la conversión  {code} = rentafija.Bono({code})")
            print(f"      3) {code} en la lista  todos_los_bonos")
            continue
        in_curves = sorted(k for k, codes in groups.items() if code in codes)
        print(f"\n[OK] {code}  ({_fmt(o, 'nombre_security') or ''})")
        print(f"     Clasificación : {_fmt(o, 'clasificacion')}")
        print(f"     Industria     : {_fmt(o, 'industria')}")
        print(f"     Moneda/Ajuste : {_fmt(o, 'moneda')} / {_fmt(o, 'ajuste_sobre_capital')}")
        print(f"     Tasa/Index    : {_fmt(o, 'tipo_tasa_interes')} / {_fmt(o, 'index')}")
        print(f"     Base/Step-up  : {_fmt(o, 'convencion_base')} / {_fmt(o, 'step_up')}")
        print(f"     Vencimiento   : {_fmt(o, 'vencimiento')}")
        print(f"     -> Curva(s)   : {', '.join(in_curves) if in_curves else '(ninguna)'}")
        print(f"     -> Posiciones : Categoría={_categoria(o)} · Tasa={_tasa(o)} · Calif={_calif(o)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
