"""Implicit FX reference — Phase 2 keystone.

Computes the live CCL (USD / cable) and MEP (USB) reference rates from the
most-traded liquid USD sovereign, the same implicit method the legacy uses
(`OMSweb_app._build_implicit_fx_both` / `_ccl_last_close`):

    CCL(base) = ARS_price(base) / cable_price(base + "C")
    MEP(base) = ARS_price(base) / mep_price(base + "D")

per the app's BYMA convention — USD = cable = ticker C, USB = MEP = ticker
D (`OMSweb_app._FX_LEG_SUFFIX`). The reference is the implicit FX of the
base with the highest USD-leg volume; canje = CCL/MEP − 1.

Bases are the `globales` + `bonares` curve codes (the liquid sovereigns
that quote in all three legs). Reads exclusively from the in-process
market store — no broker call — so it's cheap and cache-friendly, and
degrades to NaN-ish (None) fields when the legs aren't in the store yet
(dev / pre-open).

`to_cable_usd` is the companion the curve/pricing layer will use to put a
quote on one consistent cable-USD basis before computing yield:

    leg ARS  (…O):  price / CCL
    leg USB  (…D):  price * USB / CCL     (MEP → ARS → cable)
    leg USD  (…C):  price                 (already cable-USD)
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.cache import LockedTTLCache
from backend.services import curves, marketdata_store, symbols as syms

logger = logging.getLogger("backend.fx")

# USD = cable = ticker C ; USB = MEP = ticker D  (OMSweb_app._FX_LEG_SUFFIX).
LEG_SUFFIX = {"USD": "C", "USB": "D"}

# Short TTL: reading the store is cheap, but a curve sweep can ask for the
# reference once per row — cache it so we compute once per few seconds.
_fx_cache = LockedTTLCache(maxsize=8, ttl=5)


def _norm_base(code: str) -> str:
    """Strip a trailing C/D leg suffix → the ARS base. Mirrors
    `OMSweb_app._normalize_bond_base` (bases never end in C/D here)."""
    c = str(code or "").strip()
    if len(c) > 2 and c[-1] in ("C", "D") and not c.endswith(("CC", "DD")):
        return c[:-1]
    return c


def _pos(x: object) -> Optional[float]:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def fx_bases() -> List[str]:
    """Liquid USD sovereigns used as implicit-FX bases (globales + bonares)."""
    table = curves.build_curve_codes()
    bases = {
        _norm_base(c)
        for c in (table.get("globales") or []) + (table.get("bonares") or [])
        if c
    }
    return sorted(bases)


def fx_leg_symbols(plazo: str = "24hs") -> List[str]:
    """Every market symbol the FX service needs subscribed: each base plus
    its C and D legs. Fed to the WS seed so the store has the prices."""
    out: set[str] = set()
    for base in fx_bases():
        for code in (base, base + "C", base + "D"):
            out.add(syms.md_symbol(code, plazo))
    return sorted(out)


@dataclass
class FxLeg:
    base: str
    last: Optional[float] = None
    bid: Optional[float] = None
    offer: Optional[float] = None
    close: Optional[float] = None
    vol_usd_m: Optional[float] = None  # USD-leg accumulated $ volume / 1e6


def leg_table(leg: str, plazo: str = "24hs") -> List[FxLeg]:
    """Per-base implicit FX for one leg ("USD"→C / "USB"→D), from the store.

    bid/offer cross the book the way the legacy does: implied-bid uses the
    ARS bid over the USD offer (and vice-versa), so the spread reflects a
    real round-trip, not two same-side mids.
    """
    suf = LEG_SUFFIX[leg.upper()]
    store = marketdata_store.get_store()
    rows: List[FxLeg] = []
    for base in fx_bases():
        ars = store.get(syms.md_symbol(base, plazo))
        usd = store.get(syms.md_symbol(base + suf, plazo))
        if ars is None or usd is None:
            continue

        def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
            return (num / den) if (num is not None and den is not None) else None

        usd_vol = _pos(usd.volume)
        rows.append(
            FxLeg(
                base=base,
                last=_ratio(_pos(ars.last), _pos(usd.last)),
                bid=_ratio(_pos(ars.bid), _pos(usd.offer)),
                offer=_ratio(_pos(ars.offer), _pos(usd.bid)),
                close=_ratio(_pos(ars.close), _pos(usd.close)),
                vol_usd_m=(usd_vol / 1e6) if usd_vol is not None else None,
            )
        )
    return rows


def _reference(rows: List[FxLeg]) -> Optional[FxLeg]:
    """Pick the reference row: highest USD-leg volume (legacy `_top_volume_bond`),
    falling back to the first row with a finite `last` when no volume is
    reported yet (dev / pre-open)."""
    priced = [r for r in rows if r.last is not None]
    if not priced:
        return None
    with_vol = [r for r in priced if r.vol_usd_m is not None]
    if with_vol:
        return max(with_vol, key=lambda r: r.vol_usd_m or 0.0)
    return priced[0]


@dataclass
class FxSnapshot:
    ccl: Optional[float] = None       # USD / cable
    usb: Optional[float] = None       # MEP
    ccl_base: Optional[str] = None
    usb_base: Optional[str] = None
    canje: Optional[float] = None     # CCL / MEP − 1
    bases: int = 0
    as_of: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "ccl": self.ccl,
            "usb": self.usb,
            "ccl_base": self.ccl_base,
            "usb_base": self.usb_base,
            "canje": self.canje,
            "bases": self.bases,
            "as_of": self.as_of,
        }


def compute_fx(plazo: str = "24hs") -> FxSnapshot:
    usd_ref = _reference(leg_table("USD", plazo))
    usb_ref = _reference(leg_table("USB", plazo))
    ccl = usd_ref.last if usd_ref else None
    usb = usb_ref.last if usb_ref else None
    canje = (ccl / usb - 1.0) if (ccl and usb) else None
    return FxSnapshot(
        ccl=ccl,
        usb=usb,
        ccl_base=usd_ref.base if usd_ref else None,
        usb_base=usb_ref.base if usb_ref else None,
        canje=canje,
        bases=len(fx_bases()),
        as_of=time.time(),
    )


def get_fx(plazo: str = "24hs") -> FxSnapshot:
    """Cached reference FX (CCL / USB) from the in-process store."""
    return _fx_cache.get_or_compute(("fx", plazo), lambda: compute_fx(plazo))


def invalidate() -> None:
    _fx_cache.clear()


def _leg_code(x: object) -> Optional[str]:
    """Normalize a leg/native alias to one of ARS / USD (cable) / USB (MEP)."""
    c = str(x or "").strip().upper()
    if c in ("ARS", "O", "PESOS"):
        return "ARS"
    if c in ("USD", "C", "CABLE"):
        return "USD"
    if c in ("USB", "D", "MEP"):
        return "USB"
    return None


def normalize_price(
    price: object,
    leg: str,
    native: str = "USD",
    fx: Optional[FxSnapshot] = None,
) -> Optional[float]:
    """Convert a quoted `price` from its BYMA `leg` currency to the bond's
    `native`-dollar basis, two-step (leg → ARS → native), using the implicit
    rates CCL (USD/ARS) and MEP (USB/ARS).

        leg / native ∈ {"ARS"/"O", "USB"/"D"/"MEP", "USD"/"C"/"CABLE"}

    `native` is the Moneda of the bond's DIRTY ficha (USD = cable, USB =
    MEP). The native leg is a no-op, so the basic curve (native ficha +
    native ticker) needs no FX; this only powers the cross-leg O/D/C view
    and price fallbacks. Returns None when a needed rate is missing or the
    price is invalid.
    """
    p = _pos(price)
    if p is None:
        return None
    L, N = _leg_code(leg), _leg_code(native)
    if L is None or N is None:
        return None
    if L == N:
        return p
    fx = fx or get_fx()
    # step 1: leg → ARS
    if L == "ARS":
        ars: Optional[float] = p
    elif L == "USD":
        ars = (p * fx.ccl) if fx.ccl else None
    else:  # USB / MEP
        ars = (p * fx.usb) if fx.usb else None
    if ars is None:
        return None
    # step 2: ARS → native
    if N == "ARS":
        return ars
    if N == "USD":
        return (ars / fx.ccl) if fx.ccl else None
    return (ars / fx.usb) if fx.usb else None  # USB / MEP


def to_cable_usd(price: object, leg: str, fx: Optional[FxSnapshot] = None) -> Optional[float]:
    """Normalize a quote to the cable-USD (CCL) basis — `normalize_price`
    with native=USD. Kept for the globales/cable curves."""
    return normalize_price(price, leg, native="USD", fx=fx)
