"""Patas BYMA de los soberanos hard-dollar para el histórico (13/10).

Un bonar paga MEP y su ficha nativa es la `…D` (AO27D); un global paga cable
y su nativa es la `…C` (GD30C). En BYMA los tres tickers cotizan: la pata en
pesos (AO27), la MEP (AO27D) y la cable (AO27C). Hasta acá la base px/tasas
guardaba sólo la nativa. El desk quiere, para los 15 soberanos (globales +
bonares, NO corporativos), también:

- la pata CRUZADA (AO27C de un bonar, GD30D de un global) con TIR **directa**:
  el precio crudo de esa pata contra el flujo de la ficha nativa, tal cual
  cotiza (es la TIR "por ticker" que publica el mercado; difiere de la vista
  por pata de Curvas, que convierte con CCL/MEP, en ≈ canje / duration);
- la pata en PESOS (AO27, GD30) con TIR = precio ÷ FX de referencia del día
  (MEP para un bonar, CCL para un global), la misma rama que ya usaba el
  writer para las especies en pesos de las ON hard-dollar; el FX usado queda
  en la fila (`FX`) para que sea reproducible.

El mapeo va por SUFIJO desde las listas de curva (nativa sin la última letra
= base), no por hermanas de ISIN: AO29 / AO29D traen ISIN placeholder en
especies.py y `dollar_siblings` no las enlaza. Un solo resolver para el
writer (`build_rows`), la reconstrucción (`_fila_rc` / `_filas_desde_feed`)
y los lectores (`price_action.serie_de`, selector de Históricos): la fila
lleva `Código` = ticker de la pata (el lector dedupea por Código + fecha:
con el código de la ficha las patas se pisarían) y `Pata` ∈ ARS / MEP /
CABLE. Las patas ya estaban suscriptas al feed (`fx.fx_leg_symbols`) y en
el cierre completo: lo nuevo son la TIR y la fila en la base.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Optional

ARS, MEP, CABLE = "ARS", "MEP", "CABLE"


class Pata(NamedTuple):
    codigo: str        # ticker BYMA de la pata = `Código` de la fila
    nativa: str        # ficha con la que se calcula (AO27D / GD30C)
    pata: str          # ARS | MEP | CABLE
    directa: bool      # True: precio crudo contra la nativa; False: precio ÷ FX del día
    moneda: str        # moneda de la ficha nativa: USD (cable) / USB (MEP)


def soberanas() -> Dict[str, Pata]:
    """{Código de pata: Pata} para globales + bonares — dos entradas por base
    (pesos + cruzada); las nativas NO están (ya son filas de curva)."""
    from backend.services import curves, pricing
    cc = curves.build_curve_codes()
    out: Dict[str, Pata] = {}
    for curva, suf_cruzada, pata_cruzada in (("globales", "D", MEP), ("bonares", "C", CABLE)):
        for nat in cc.get(curva) or []:
            if not nat or nat[-1] not in ("C", "D"):
                continue
            meta = pricing.bond_meta(nat) or {}
            moneda = meta.get("moneda") or ("USD" if nat.endswith("C") else "USB")
            base = nat[:-1]
            out[base] = Pata(base, nat, ARS, False, moneda)
            out[base + suf_cruzada] = Pata(base + suf_cruzada, nat, pata_cruzada, True, moneda)
    return out


def pata_de(code: Optional[str]) -> Optional[Pata]:
    c = (code or "").strip()
    return soberanas().get(c) if c else None


def calc_para(code: str) -> str:
    """Ficha de cálculo de cualquier código: la nativa si es una pata, si no
    el código mismo."""
    p = pata_de(code)
    return p.nativa if p else code


def fx_usado(fx: object, moneda: str) -> Optional[float]:
    """El tipo de cambio por el que se dividió un precio en pesos: MEP (usb)
    para una ficha USB, CCL para una USD. None sin snapshot."""
    if fx is None:
        return None
    v = getattr(fx, "usb", None) if moneda == "USB" else getattr(fx, "ccl", None)
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None
