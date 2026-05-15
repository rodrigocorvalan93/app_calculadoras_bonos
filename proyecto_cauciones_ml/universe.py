# -*- coding: utf-8 -*-
"""universe.py

Lógica de selección de símbolos de caución BYMA según el calendario.

En BYMA la caución de un día opera con plazo = días corridos hasta el
próximo día hábil. Ejemplos típicos:
  - Lunes a jueves laborables    → 1D
  - Viernes laborables           → 3D
  - Lunes con feriado el martes  → 2D
  - Viernes con feriado el lunes → 4D
  - Viernes con feriado lunes y martes → 5D

Sólo opera con volumen real el símbolo "del día". El resto está
listado pero sin trades — capturarlos sería ruido.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Reusamos el calendario de feriados del repo principal
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dias_habiles  # noqa: E402


def plazo_caucion(d: date) -> int:
    """Días corridos entre `d` y el siguiente día hábil argentino.

    Si `d` es no-hábil (sábado, domingo, feriado), igual devuelve la
    distancia al próximo hábil — útil para previsualizar el lunes
    desde un domingo.
    """
    sig = dias_habiles.siguiente_dia_habil_ar(d + timedelta(days=1))
    return (sig - d).days


def simbolo_caucion(d: date, moneda: str = "PESOS") -> str:
    """Devuelve el símbolo de caución que opera el día `d`."""
    n = plazo_caucion(d)
    return f"MERV - XMEV - {moneda.upper()} - {n}D"


def es_dia_habil_ar(d: date) -> bool:
    dias_habiles._ensure_holidays()
    return d.weekday() < 5 and d not in dias_habiles._ar_holidays


if __name__ == "__main__":
    # Sanity check rápido
    hoy = date.today()
    for i in range(-3, 8):
        d = hoy + timedelta(days=i)
        marker = "" if es_dia_habil_ar(d) else " (no hábil)"
        print(f"  {d:%a %Y-%m-%d}{marker:14s} → {simbolo_caucion(d)}")
