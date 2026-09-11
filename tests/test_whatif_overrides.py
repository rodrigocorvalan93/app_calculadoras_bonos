"""What-if de Forwards: el parser de precios.

Los inputs del what-if son <input type="text" inputmode="decimal"> en es-AR
(value/placeholder con ar_num). Antes eran type=number, que Safari/Firefox
rechazan con la coma decimal (mandaban "" y el override se perdía). Se parsean
con parse_ar_num, el único parser de entrada de la app: "1.234" es mil
doscientos treinta y cuatro (una LECAP a 1.234 % VN existe; 1,234 no), "98.5"
y "98,5" son 98,5; float() queda de fallback.
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


def test_price_overrides_es_ar() -> None:
    ov = curves._price_overrides(_Req([
        ("price_S13N6", "1.234"),     # es-AR: mil-234 (LECAP), no uno-coma-234
        ("price_S31O6", "1.234,50"),  # miles + coma decimal
        ("price_GD30", "95,50"),      # coma decimal (lo que tipea el desk)
        ("price_AL30", "95.50"),      # punto con 2 decimales → decimal
        ("price_DICP", "50000.00"),   # CER viejo: decenas de miles (formato viejo del input)
        ("otra_cosa", "9"),           # no empieza con price_ → ignorado
    ]))
    assert ov["S13N6"] == 1234.0
    assert ov["S31O6"] == 1234.5
    assert ov["GD30"] == 95.5
    assert ov["AL30"] == 95.5
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
