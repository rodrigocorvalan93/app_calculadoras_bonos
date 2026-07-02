"""What-if de Forwards: el parser de precios (regresión de la auditoría).

Los inputs del what-if son <input type="number">, que serializan en formato
inglés (punto = decimal). Parsearlos con parse_ar_num (heurística es-AR) leía
'1.234' como 1234 → precio 1000×. Ahora se parsean con float().
"""
from __future__ import annotations

from backend.routes import curves


class _Req:
    class _QP:
        def __init__(self, items):
            self._items = items

        def multi_items(self):
            return self._items

    def __init__(self, items):
        self.query_params = self._QP(items)


def test_price_overrides_type_number_no_1000x() -> None:
    ov = curves._price_overrides(_Req([
        ("price_AL30", "1.234"),      # type=number: uno-coma-234, NO mil-234
        ("price_GD30", "95.50"),
        ("price_DICP", "50000.00"),   # CER viejo: decenas de miles
        ("otra_cosa", "9"),           # no empieza con price_ → ignorado
    ]))
    assert ov["AL30"] == 1.234        # antes parse_ar_num → 1234.0 (1000×)
    assert ov["GD30"] == 95.5
    assert ov["DICP"] == 50000.0
    assert "otra_cosa" not in ov


def test_price_overrides_descarta_invalidos() -> None:
    ov = curves._price_overrides(_Req([
        ("price_A", ""),              # vacío
        ("price_B", "inf"),           # no finito
        ("price_C", "-5"),            # no positivo
        ("price_D", "xyz"),           # no numérico
        ("price_E", "0"),             # cero → no > 0
    ]))
    assert ov == {}
