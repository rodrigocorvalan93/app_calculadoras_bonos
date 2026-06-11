#!/usr/bin/env python3
"""
Validador de coherencia para los dicts de bonos de la calculadora de renta fija.

Uso:
    python3 validar_bono.py <archivo.py>

Lee un .py con uno o más dicts de bono (asignaciones NOMBRE = {...}), los valida y reporta
ERRORES (incoherencias que romperían el cálculo) y AVISOS (cosas a revisar). Devuelve código de
salida 1 si hay errores.
"""
import sys
import re
from datetime import datetime

ADJ_BASE = {"CER", "UVA", "A3500"}
ADJ_ALL = ADJ_BASE | {"CER PROYECTADO", "UVA PROYECTADO", "A3500 PROYECTADO"}
INDEX_VALS = {"TAMAR", "BADLAR", "A3500"}

REQUIRED = [
    "Nombre Security", "Código", "Moneda", "Emisión", "Vencimiento",
    "Cupón / Spread", "Step-up", "Frecuencia de pago de cupón anual",
    "Tipo de Amortización", "Tipo Tasa Interés", "Index", "Ajuste sobre Capital",
    "Fechas de cupón", "Callable",
]


def parse_date(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def load_bonds(path):
    """Ejecuta el archivo y devuelve los dicts top-level que parecen bonos (tienen 'Código')."""
    src = open(path, encoding="utf-8").read()
    ns = {}
    try:
        exec(src, ns)
    except Exception as e:
        print(f"ERROR: no pude ejecutar el archivo ({e})")
        sys.exit(1)
    # orden de aparición
    names = [m.group(1) for m in re.finditer(r'^([A-Za-z0-9_]+)\s*=\s*\{', src, re.M)]
    bonds = {}
    for n in names:
        v = ns.get(n)
        if isinstance(v, dict) and "Código" in v:
            bonds[n] = v
    return bonds


def validate_one(name, b, errors, warns):
    def err(m): errors.append(f"[{name}] {m}")
    def wrn(m): warns.append(f"[{name}] {m}")

    for k in REQUIRED:
        if k not in b:
            err(f"falta el campo obligatorio '{k}'")

    # --- Nombre Security debe terminar en "Vto dd mm yyyy" (= vencimiento) ---
    nombre = b.get("Nombre Security", "") or ""
    vto_str = b.get("Vencimiento", "")
    vto = parse_date(vto_str)
    mm = re.search(r"Vto\s+(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s*$", nombre)
    if not mm:
        wrn("'Nombre Security' no termina en 'Vto dd mm yyyy'")
    elif vto:
        d, mo, y = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
        if (d, mo, y) != (vto.day, vto.month, vto.year):
            wrn(f"la fecha del 'Vto ...' en el nombre no coincide con el Vencimiento ({vto_str})")

    # --- Fechas ---
    fechas = b.get("Fechas de cupón") or []
    parsed = [parse_date(f) for f in fechas]
    if any(p is None for p in parsed):
        err("hay fechas de cupón que no parsean como dd/mm/aaaa")
    else:
        if parsed != sorted(parsed):
            err("las fechas de cupón no están en orden ascendente")
        vto = parse_date(b.get("Vencimiento", ""))
        if vto and parsed and parsed[-1] != vto:
            wrn(f"el último cupón ({fechas[-1]}) no coincide con el vencimiento "
                f"({b.get('Vencimiento')})")

    # --- Amortización ---
    tipo_amort = b.get("Tipo de Amortización")
    amort = b.get("Amortización")
    if tipo_amort == "BULLET":
        if amort not in (None, []):
            wrn("es BULLET pero 'Amortización' no es None")
    elif tipo_amort == "AMORTIZABLE":
        if not isinstance(amort, list):
            err("es AMORTIZABLE pero 'Amortización' no es una lista")
        else:
            if fechas and len(amort) != len(fechas):
                err(f"longitud de Amortización ({len(amort)}) != cantidad de fechas "
                    f"({len(fechas)})")
            tot = sum(amort)
            if abs(tot - 100) > 0.5:
                err(f"la amortización suma {tot}, debería sumar 100")

    # --- Acople tasa / índice / ajuste ---
    tipo_tasa = b.get("Tipo Tasa Interés")
    index = b.get("Index")
    ajuste = b.get("Ajuste sobre Capital")
    ilag_d = b.get("Días Lag índice desde inc")
    ilag_h = b.get("Días Lag índice hasta inc")
    alag_b = b.get("Días lag Ajuste base")
    alag = b.get("Días lag Ajuste")

    if tipo_tasa == "VARIABLE":
        if index not in INDEX_VALS:
            err(f"es VARIABLE pero Index='{index}' (esperaba TAMAR/BADLAR)")
        if not (isinstance(ilag_d, (int, float)) and ilag_d < 0):
            wrn("es VARIABLE pero el lag de índice no es negativo")
        if ajuste is not None:
            wrn(f"es VARIABLE y además tiene Ajuste sobre Capital='{ajuste}' (raro, revisar)")
    elif tipo_tasa == "FIJA":
        if index is not None:
            wrn(f"es FIJA pero Index='{index}' no es None")

    if ajuste in ADJ_ALL:
        if tipo_tasa != "FIJA":
            wrn(f"tiene ajuste de capital '{ajuste}' pero Tipo Tasa no es FIJA")
        if not (isinstance(alag_b, (int, float)) and alag_b < 0):
            wrn(f"ajusta por '{ajuste}' pero 'Días lag Ajuste base' no es negativo")
        if not (isinstance(alag, (int, float)) and alag < 0):
            wrn(f"ajusta por '{ajuste}' pero 'Días lag Ajuste' no es negativo")
    elif ajuste is None:
        if isinstance(alag_b, (int, float)) and alag_b < 0:
            wrn("no tiene ajuste de capital pero 'Días lag Ajuste base' es negativo")

    # --- Step-up ---
    cupon = b.get("Cupón / Spread")
    if b.get("Step-up") is True and not isinstance(cupon, list):
        err("Step-up=True pero 'Cupón / Spread' no es una lista de cupones")
    if b.get("Step-up") is False and isinstance(cupon, list):
        wrn("'Cupón / Spread' es lista pero Step-up=False (¿debería ser True?)")

    # --- Call ---
    if b.get("Callable") is True:
        if b.get("Fecha Call") is None:
            err("Callable=True pero 'Fecha Call' es None")
        if b.get("Precio Call") is None:
            err("Callable=True pero 'Precio Call' es None")
    else:
        if b.get("Fecha Call") is not None:
            wrn("Callable no es True pero hay 'Fecha Call' cargada")

    return index, ajuste


def validate_twins(bonds, errors, warns):
    """Chequea la pata proyectada 'j' para CER/UVA y que A3500 no la tenga."""
    for name, b in bonds.items():
        if name.endswith("j"):
            continue
        ajuste = b.get("Ajuste sobre Capital")
        jname = name + "j"
        if ajuste in {"CER", "UVA"}:
            if jname not in bonds:
                warns.append(f"[{name}] es {ajuste}: falta la pata proyectada '{jname}'")
            else:
                jb = bonds[jname]
                exp = ajuste + " PROYECTADO"
                if jb.get("Ajuste sobre Capital") != exp:
                    errors.append(f"[{jname}] 'Ajuste sobre Capital' debería ser '{exp}'")
                # debe ser idéntico salvo Industria y Ajuste sobre Capital
                for k in b:
                    if k in ("Industria", "Ajuste sobre Capital"):
                        continue
                    if jb.get(k) != b.get(k):
                        warns.append(f"[{jname}] difiere de {name} en '{k}' "
                                     f"(la pata 'j' solo debería cambiar Industria y Ajuste)")
        if ajuste == "A3500" and jname in bonds:
            warns.append(f"[{name}] es A3500 (Dollar Linked) y NO debería tener pata "
                         f"proyectada, pero existe '{jname}'")


def main():
    if len(sys.argv) != 2:
        print("Uso: python3 validar_bono.py <archivo.py>")
        sys.exit(2)
    bonds = load_bonds(sys.argv[1])
    if not bonds:
        print("No encontré ningún dict de bono (con clave 'Código') en el archivo.")
        sys.exit(1)

    errors, warns = [], []
    for name, b in bonds.items():
        validate_one(name, b, errors, warns)
    validate_twins(bonds, errors, warns)

    print(f"Bonos analizados: {', '.join(bonds.keys())}\n")
    if errors:
        print("ERRORES:")
        for e in errors:
            print("  ✗", e)
    if warns:
        print("AVISOS:")
        for w in warns:
            print("  ⚠", w)
    if not errors and not warns:
        print("✓ Todo coherente.")
    elif not errors:
        print("\n✓ Sin errores (revisá los avisos).")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
