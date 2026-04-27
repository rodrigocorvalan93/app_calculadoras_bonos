#%% """Cálculo de métricas de bonos (sin eval)."""
from dataclasses import dataclass
from typing import Dict
import rentafija  # tu librería interna con fórmulas


@dataclass
class BondWrapper:
    def __init__(self, code: str, obj):
        self.code = code
        self.obj  = obj

    # --------- MÉTRICAS ----------------------------------------------
    def metrics(self, price_pct: float) -> dict[str, float]:
        """
        Calcula TIREA, TNA, TEM, Paridad y Duration a partir del precio
        en porcentaje (ej. 145.30 = 145,30 % del VN).
        """
        precio_sucio = price_pct / 100  # porcentaje → paridad (1 = 100 %)
        try:
            tirea = self.obj.calcula_tirea(precio=precio_sucio)   # ← fix
        except Exception:
            return {"TIREA": None, "TNA": None, "TEM": None,
                    "Paridad": None, "Duration": None}

        # resto igual
        import rentafija
        tna = rentafija.tir_a_tna(tirea, self.obj.dias_remanentes, 365)
        tem = (1 + tirea) ** (30 / 360) - 1
        duration = self.obj.calcula_duration(tirea)
        return {"TIREA": tirea, "TNA": tna, "TEM": tem,
                "Paridad": precio_sucio, "Duration": duration}