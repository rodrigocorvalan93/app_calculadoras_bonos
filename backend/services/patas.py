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

from typing import Any, Dict, NamedTuple, Optional, Tuple

ARS, MEP, CABLE = "ARS", "MEP", "CABLE"


# ── Resolver general: ticker de BYMA → ficha que lo valúa (26/11) ────────────
# Un bono hard-dollar es UNA ficha calculada en su dólar natural (GD30C cable,
# AL30D MEP) y hasta tres tickers en BYMA: pesos (GD30 / AL30 / YM34O), MEP
# (…D) y cable (…C). La TIR de cualquiera de los tres sale de la ficha nativa
# con el precio llevado a su dólar: pesos ÷ FX de la moneda de pago (CCL para
# una nativa cable, MEP para una MEP) y la otra pata dólar × MEP / CCL o
# × CCL / MEP (se le saca / suma el canje) — la matriz de `fx.normalize_price`.
# La vista por pata de Mercado / Curvas ya lo hacía entrando por la nativa +
# `leg`; lo que NO había era resolver un TICKER suelto: la pata cruzada no
# tiene ficha (GD30D, AL30C → sin TIR en Órdenes, error en el add-in) y la de
# pesos tiene una ficha en DÓLARES (GD30 clean, AL30) que varios caminos
# usaban con el precio en pesos crudo (add-in y alertas: TIR −100 %) o como
# moneda de la orden (el tope de notional en USD rechazaba una compra de
# AL30 en pesos de VN 10.000). Todo lo que recibe un ticker pasa por acá.
class Leg(NamedTuple):
    ticker: str        # código pedido = ticker BYMA de la pata
    calc: str          # ficha que la valúa (la nativa DIRTY si existe)
    basis: str         # moneda en que cotiza ESE ticker: ARS | USD (cable) | USB (MEP); "" = no es hard-dollar
    native: str        # moneda de la ficha de cálculo (USD / USB); "" = no es hard-dollar
    propia: bool       # el ticker tiene ficha propia en especies

    @property
    def convierte(self) -> bool:
        """El precio del ticker necesita FX para entrar a la ficha de cálculo."""
        return bool(self.basis) and self.basis != self.native


_legs: Dict[str, Optional[Leg]] = {}
_legs_token: Tuple = ()


def _hd(code: str) -> bool:
    from backend.services import pricing
    return (pricing.bond_meta(code) or {}).get("moneda") in ("USD", "USB")


def _resolver_leg(c: str) -> Optional[Leg]:
    from backend.services import bond_universe, pricing
    if bond_universe.get(c) is not None:
        mon = (pricing.bond_meta(c) or {}).get("moneda") or ""
        if mon not in ("USD", "USB"):
            return Leg(c, c, "", "", True)
        if pricing.es_especie_pesos(c):
            calc = pricing.native_dollar_code(c) or c
            return Leg(c, calc, ARS, (pricing.bond_meta(calc) or {}).get("moneda") or mon, True)
        return Leg(c, c, mon, mon, True)                     # la nativa: cotiza en su moneda
    if len(c) < 3:
        return None
    # Sin ficha propia. (1) la OTRA pata dólar de un bono con ficha: GD30D →
    # GD30C, AL30C → AL30D, CO32DD → CO32DC; (2) la pata dólar de un bono que
    # sólo tiene la ficha base (AO29C ← AO29, con ISIN de relleno).
    if c[-1] in ("C", "D"):
        basis = "USD" if c[-1] == "C" else "USB"
        base = c[:-1]
        otra = base + ("D" if c[-1] == "C" else "C")
        if bond_universe.get(otra) is not None and _hd(otra) and not pricing.es_especie_pesos(otra):
            return Leg(c, otra, basis, pricing.bond_meta(otra)["moneda"], False)
        if bond_universe.get(base) is not None and _hd(base):
            calc = pricing.native_dollar_code(base) or base
            return Leg(c, calc, basis, pricing.bond_meta(calc)["moneda"], False)
    # (3) la especie en PESOS de una ON que sólo tiene cargada la nativa:
    # AEC3O → AEC3D (la pata reemplaza la O final), o base + D / C.
    raices = ([c[:-1]] if c[-1] == "O" else []) + [c]
    for raiz in raices:
        for suf in ("D", "C"):
            nat = raiz + suf
            if bond_universe.get(nat) is not None and _hd(nat) and not pricing.es_especie_pesos(nat):
                return Leg(c, nat, ARS, pricing.bond_meta(nat)["moneda"], False)
    return None


def leg_de(code: Any) -> Optional[Leg]:
    """Ficha y moneda de cotización de un ticker de BYMA, o None si no hay con
    qué valuarlo. Sin distinguir mayúsculas; memo por universo (µs)."""
    global _legs, _legs_token
    from backend.services import bond_universe
    raw = str(code or "").strip()
    if not raw:
        return None
    bond_universe.ensure_loaded()
    objs = bond_universe._objs or {}
    tok = (id(objs), len(objs))
    if tok != _legs_token:
        _legs, _legs_token = {}, tok
    if raw in _legs:
        return _legs[raw]
    c = bond_universe.resolve(raw) or raw.upper()
    lg = _resolver_leg(c)
    if len(_legs) > 8000:
        _legs.clear()
    _legs[raw] = lg
    return lg


def moneda_ticker(code: Any) -> str:
    """Moneda en la que se OPERA un ticker (para el tope de una orden y el
    ticket): ARS la especie en pesos de un hard-dollar, USB la …D, USD la …C;
    un bono común, la de su ficha. Desconocido = ARS."""
    from backend.services import pricing
    lg = leg_de(code)
    if lg is None:
        return "ARS"
    if lg.basis:
        return lg.basis
    return (pricing.bond_meta(lg.calc) or {}).get("moneda") or "ARS"


def precio_nativo(lg: Leg, px: Any, plazo: str = "24hs", fx: Any = None) -> Optional[float]:
    """Precio del ticker → el dólar de la ficha de cálculo (DIRTY por 100 VN).
    None si falta el FX que hace falta."""
    from backend.services import fx as fx_svc
    try:
        v = float(px)
    except (TypeError, ValueError):
        return None
    if not (v == v and v > 0):
        return None
    if not lg.convierte:
        return v
    return fx_svc.normalize_price(v, lg.basis, lg.native, fx or fx_svc.get_fx(plazo))


def precio_ficha(lg: Leg, px: Any, plazo: str = "24hs", settle: Optional[str] = None,
                 fx: Any = None) -> Optional[float]:
    """Como `precio_nativo` y además en la convención de cotización de la
    ficha de cálculo (una CLEAN sin nativa cargada: PLC4O, YMCJO): lo que hay
    que pasarle a `metrics_for_market_price(lg.calc, …)`."""
    from backend.services import pricing
    v = precio_nativo(lg, px, plazo, fx)
    if v is None or not lg.basis:
        return v
    return pricing.dirty_a_cotizacion(lg.calc, v, settle or pricing.settlement_date_str(plazo))


def desde_nativo(lg: Leg, px: Any, plazo: str = "24hs", fx: Any = None) -> Optional[float]:
    """Al revés: un precio en el dólar de la ficha → la moneda del ticker
    (valor técnico de referencia de una orden en pesos, p. ej.)."""
    from backend.services import fx as fx_svc
    try:
        v = float(px)
    except (TypeError, ValueError):
        return None
    if not (v == v and v > 0):
        return None
    if not lg.convierte:
        return v
    return fx_svc.normalize_price(v, lg.native, lg.basis, fx or fx_svc.get_fx(plazo))


def como_se_valua(lg: Optional[Leg]) -> str:
    """Una línea para el libro / el ticket: con qué ficha y qué conversión
    sale la TIR de este ticker. Vacío si es la nativa o un bono común."""
    if lg is None or not lg.basis or (lg.calc == lg.ticker and not lg.convierte):
        return ""
    if not lg.convierte:
        return f"TIR con la ficha {lg.calc}"
    if lg.basis == ARS:
        return f"TIR con la ficha {lg.calc}: precio ÷ {'CCL' if lg.native == 'USD' else 'MEP'}"
    if lg.native == "USD":
        return f"TIR con la ficha {lg.calc}: precio × MEP ÷ CCL (se le saca el canje)"
    return f"TIR con la ficha {lg.calc}: precio × CCL ÷ MEP (se le suma el canje)"


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
