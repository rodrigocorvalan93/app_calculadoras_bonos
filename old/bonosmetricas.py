"""
bonos.py
========

- `Bono`: envoltorio con utilidades de métricas.
- `catalogo_desde_especies`: crea un diccionario {código: Bono}.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

import rentafija as rf


@dataclass(slots=True)
class Bono:
    """Wrapper sobre las clases definidas en `especies.py`."""

    código: str
    objeto: Any  # instancia proveniente de `especies`

    # --------------------------------------------------------------------- #
    # Métricas
    # --------------------------------------------------------------------- #

    def metricas(self, precio: float, hoy: date | None = None) -> Mapping[str, float]:
        """
        Calcula TIREA, TNA, TEM, Paridad y Duration para un precio dado.
        """
        tirea = (
            self.objeto.calcula_tirea(precio, hoy.strftime("%d/%m/%Y"))
            if hoy
            else self.objeto.calcula_tirea(precio)
        )

        días = getattr(self.objeto, "dias_remanentes", 180)
        tna = rf.tir_a_tna(tirea, días, 365)
        tem = (1 + tirea) ** (30 / 360) - 1

        duration = (
            self.objeto.calcula_duration(tirea, hoy.strftime("%d/%m/%Y"))
            if hoy
            else self.objeto.calcula_duration(tirea)
        )

        return {
            "TIREA": tirea,
            "TNA": tna,
            "TEM": tem,
            "Paridad": self.objeto.paridad,
            "Duration": duration,
        }


# --------------------------------------------------------------------------- #
# Catálogo automático
# --------------------------------------------------------------------------- #


def catalogo_desde_especies(mod) -> dict[str, Bono]:
    """
    Devuelve un diccionario {código: Bono} a partir del módulo `especies`.
    """
    return {
        nombre: Bono(nombre, getattr(mod, nombre))
        for nombre in dir(mod)
        if nombre.isupper()
    }
