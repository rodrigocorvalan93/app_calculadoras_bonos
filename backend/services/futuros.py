"""Futuros de dólar (DLR ROFEX) — tasas implícitas vs spot A3500.

Símbolos crudos generados dinámicamente: `DLR/MMMYY` (minorista) y `DLR/MMMYYM`
(mayorista), leídos del store (mismo WS que todo lo demás; igual que DLR/SPOT).

Tasa implícita de cada contrato vs el spot oficial (A3500), como en el OMSweb_app:
    td  = precio / spot − 1                 (devaluación implícita al vto)
    TNA = td · 365 / días                   (lineal)
    TEA = (1 + td · 30/días) ^ 12 − 1       (mensual capitalizada → anual)
    TEM = (1 + TEA) ^ (1/12) − 1
Sólo lee de cache → sub-50 ms.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.services import dolares, marketdata_store

_MES = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}
_MES_INV = {v: k for k, v in _MES.items()}
_N_MONTHS = 14
_MES_ES = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
           7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}


def symbols(canal: str = "may", n_months: int = _N_MONTHS) -> List[str]:
    """DLR/MMMYY (minorista) o DLR/MMMYYM (mayorista), desde el mes actual."""
    suf = "M" if canal == "may" else ""
    today = date.today()
    y, m = today.year, today.month
    out: List[str] = []
    for _ in range(n_months):
        out.append(f"DLR/{_MES[m]}{y % 100:02d}{suf}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _parse_vto(code: str) -> Optional[date]:
    """'DLR/FEB26' / 'DLR/FEB26M' → último día del mes de vencimiento."""
    m = re.match(r"^DLR/([A-Z]{3})(\d{2})M?$", str(code).strip().upper())
    if not m:
        return None
    mes = _MES_INV.get(m.group(1))
    if not mes:
        return None
    yy = 2000 + int(m.group(2))
    return date(yy, mes, monthrange(yy, mes)[1])


def _label(code: str) -> str:
    v = _parse_vto(code)
    return f"{_MES_ES[v.month]}-{v.year % 100:02d}" if v else code


def spot() -> Optional[float]:
    """Spot mayorista de referencia (oficial A3500/SIOPEL)."""
    o = dolares.official_fx() or {}
    s = o.get("last")
    try:
        return float(s) if s and float(s) > 0 else None
    except (TypeError, ValueError):
        return None


def _impl(px: Optional[float], sp: Optional[float], dias: Optional[int]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(devaluación td, TNA, TEM) implícitas de un precio de futuro vs spot."""
    if px is None or not sp or not dias or dias <= 0:
        return None, None, None
    try:
        td = px / sp - 1.0
        tna = td * 365.0 / dias
        tea = (1.0 + td * 30.0 / dias) ** 12 - 1.0
        tem = (1.0 + tea) ** (1.0 / 12.0) - 1.0
        return td, tna, tem
    except (ValueError, ZeroDivisionError, OverflowError):
        return None, None, None


def rows(canal: str = "may") -> List[Dict[str, Any]]:
    """Filas de futuros con su tasa implícita, ordenadas por vencimiento."""
    store = marketdata_store.get_store()
    sp = spot()
    today = date.today()
    out: List[Dict[str, Any]] = []
    for sym in symbols(canal):
        snap = store.get(sym)
        if snap is None:
            continue
        last, bid, offer, close = snap.last, snap.bid, snap.offer, snap.close
        if last is None and bid is None and offer is None:
            continue
        vto = _parse_vto(sym)
        dias = (vto - today).days if vto else None
        td, tna_last, tem_last = _impl(last, sp, dias)
        _, tna_bid, _ = _impl(bid, sp, dias)
        _, tna_off, _ = _impl(offer, sp, dias)
        var = None
        try:
            if last is not None and close not in (None, 0):
                var = last / close - 1.0
        except (TypeError, ZeroDivisionError):
            var = None
        out.append({
            "code": sym, "label": _label(sym), "vto": vto.isoformat() if vto else None,
            "dias": dias, "last": last, "bid": bid, "offer": offer, "close": close,
            "var_pct": var, "td": td, "tna": tna_last, "tem": tem_last,
            "tna_bid": tna_bid, "tna_offer": tna_off, "volume": snap.volume,
        })
    out.sort(key=lambda r: (r["dias"] if r["dias"] is not None else 9999))
    return out


def nearest(canal: str = "may") -> Optional[Dict[str, Any]]:
    """Contrato más cercano con tasa implícita (para el panel DLK)."""
    for r in rows(canal):
        if r["dias"] and r["dias"] > 0 and r["tna"] is not None:
            return r
    return None


def all_symbols() -> List[str]:
    """Para sembrar en el WS (minorista + mayorista)."""
    return symbols("min") + symbols("may")
