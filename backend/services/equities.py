"""Acciones y CEDEARs — monitor de precios BYMA (sin calculadora).

Listas curadas de tickers (panel líderes + CEDEARs líquidos). Se suscriben al
WS del broker en el arranque igual que los bonos; las filas salen del store en
memoria (OCLH, last, var, VWAP, book, volumen) — son acciones: NO hay
TIR/duration, así que cada fila es puro lookup (~µs), sin pasar por pricing.

EWZ y SPY además alimentan la barra superior con su variación "vista en cable":
    var_cable = (1 + var_ars) / (1 + var_ccl) − 1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services import marketdata_store as mds, symbols as syms

# Panel líderes BYMA (ARS).
LIDERES: List[str] = [
    "GGAL", "YPFD", "PAMP", "ALUA", "BBAR", "BMA", "BYMA", "CEPU", "COME",
    "CRES", "EDN", "IRSA", "LOMA", "METR", "MIRG", "SUPV", "TECO2", "TGNO4",
    "TGSU2", "TRAN", "TXAR", "VALO",
]
# CEDEARs líquidos (ARS; el subyacente cotiza en USD afuera).
CEDEARS: List[str] = [
    "SPY", "EWZ", "QQQ", "DIA", "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL",
    "AMZN", "META", "MELI", "KO", "DIS", "BRKB", "JPM", "XOM", "GOLD",
]
# Índice Merval (si el broker lo sirve; símbolo crudo, sin plazo).
MERVAL_SYMBOLS = ("MERV - XMEV - I.MERVAL - 24hs", "MERV - XMEV - I.MERVAL", "I.MERVAL")


def all_symbols() -> List[str]:
    """Símbolos a suscribir en el WS al arranque (24hs + CI + Merval)."""
    out: List[str] = []
    for code in LIDERES + CEDEARS:
        out.append(syms.md_symbol(code, "24hs"))
        out.append(syms.md_symbol(code, "CI"))
    out.extend(MERVAL_SYMBOLS)
    return out


def _var(last: Optional[float], close: Optional[float]) -> Optional[float]:
    if last is None or close in (None, 0):
        return None
    return last / close - 1.0


def row_for(code: str, plazo: str = "24hs") -> Optional[Dict[str, Any]]:
    """Fila de precio puro desde el store (sin TIR). None si nunca cotizó."""
    snap = mds.get_store().get(syms.md_symbol(code, plazo))
    if snap is None:
        return None
    var = _var(snap.last, snap.close)
    range_pos = None
    if snap.last is not None and snap.low is not None and snap.high is not None and snap.high > snap.low:
        range_pos = max(0.0, min(1.0, (snap.last - snap.low) / (snap.high - snap.low)))
    return {
        "range_pos": range_pos,
        "code": code,
        "open": snap.open, "close": snap.close, "low": snap.low, "high": snap.high,
        "bid": snap.bid, "bid_size": snap.bid_size,
        "offer": snap.offer, "offer_size": snap.offer_size,
        "last": snap.last, "vwap": snap.vwap(),
        "var_pct": (var * 100.0) if var is not None else None,   # en pp, como mercado
        "var_px": (snap.last - snap.close) if (snap.last is not None and snap.close is not None) else None,
        "volume": snap.volume, "nominal": snap.nominal,
        "last_ts": snap.last_ts,
    }


def panel_rows(panel: str, plazo: str = "24hs") -> List[Dict[str, Any]]:
    codes = CEDEARS if panel == "cedears" else LIDERES
    rows = [r for c in codes if (r := row_for(c, plazo)) is not None]
    # Orden: volumen efectivo descendente; sin volumen al final, alfabético.
    rows.sort(key=lambda r: (-(r["volume"] or 0.0), r["code"]))
    return rows


def merval_snapshot():
    """Snapshot del índice Merval, probando las variantes de símbolo."""
    store = mds.get_store()
    for s in MERVAL_SYMBOLS:
        snap = store.get(s)
        if snap is not None and (snap.last is not None or snap.close is not None):
            return snap
    return None
