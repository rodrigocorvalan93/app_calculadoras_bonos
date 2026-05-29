"""Thread-safe in-memory store for live market data.

Decoupled from the transport: the WS reader writes into it via
`update_from_md(symbol, marketData_dict)`, REST polling fallbacks could
write too. Routes read from it without touching the broker.

Snapshot fields mirror what the legacy `OMSprices.market_snapshot`
exposes (BI / OF / LA + OP/CL/HI/LO + EV/NV/TV), so we can plug into
the same templates as the legacy app.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class MarketSnapshot:
    symbol: str
    bid: Optional[float] = None
    bid_size: Optional[float] = None
    offer: Optional[float] = None
    offer_size: Optional[float] = None
    last: Optional[float] = None
    last_size: Optional[float] = None
    last_ts: Optional[str] = None
    close_ts: Optional[str] = None       # CL.date — fecha del cierre previo
    open: Optional[float] = None
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None       # EV — accumulated $ traded
    trade_count: Optional[float] = None  # TV — # of trades today
    nominal: Optional[float] = None      # NV — accumulated nominal
    updated_at: float = field(default_factory=time.time)

    def vwap(self) -> Optional[float]:
        if self.volume and self.nominal and self.nominal != 0:
            return self.volume / self.nominal
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["vwap"] = self.vwap()
        return d


def _md_value(v: Any, key: str = "price") -> Optional[float]:
    """Extract `price` / `size` from a Primary marketData field.

    Primary's schema is inconsistent across entries: list-of-dict for
    BI/OF/LA, plain dict sometimes, scalar for OP/HI/LO/EV/NV/TV. Same
    tolerant decoder used by the recorder.
    """
    if v is None:
        return None
    if isinstance(v, list):
        if not v:
            return None
        v = v[0]
    if isinstance(v, dict):
        val = v.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


class MarketDataStore:
    def __init__(self) -> None:
        self._data: Dict[str, MarketSnapshot] = {}
        self._lock = threading.Lock()
        self._updates = 0
        self._last_update_at: float = 0.0

    def update_from_md(self, symbol: str, market_data: Dict[str, Any]) -> MarketSnapshot:
        """Merge a Primary `marketData` envelope into the snapshot for `symbol`.

        Only fields that come back with a value overwrite the current
        snapshot — the rest stay sticky, which is what you want for an
        order book + trade tape coming in over a stream.
        """
        now = time.time()
        with self._lock:
            snap = self._data.get(symbol) or MarketSnapshot(symbol=symbol)
            for entry, attr_price, attr_size in (
                ("BI", "bid", "bid_size"),
                ("OF", "offer", "offer_size"),
                ("LA", "last", "last_size"),
            ):
                raw = market_data.get(entry)
                if raw is None:
                    continue
                p = _md_value(raw, "price")
                s = _md_value(raw, "size")
                if p is not None:
                    setattr(snap, attr_price, p)
                if s is not None:
                    setattr(snap, attr_size, s)
                if entry == "LA" and isinstance(raw, dict):
                    ts = raw.get("date")
                    if ts:
                        snap.last_ts = str(ts)

            for entry, attr in (
                ("OP", "open"),
                ("CL", "close"),
                ("HI", "high"),
                ("LO", "low"),
                ("EV", "volume"),
                ("TV", "trade_count"),
                ("NV", "nominal"),
            ):
                raw = market_data.get(entry)
                if raw is None:
                    continue
                v = _md_value(raw, "price") if entry in ("OP", "CL", "HI", "LO") else _md_value(raw, "size")
                if v is not None:
                    setattr(snap, attr, v)
                if entry == "CL" and isinstance(raw, dict) and raw.get("date"):
                    snap.close_ts = str(raw.get("date"))

            snap.updated_at = now
            self._data[symbol] = snap
            self._updates += 1
            self._last_update_at = now
            return snap

    def get(self, symbol: str) -> Optional[MarketSnapshot]:
        with self._lock:
            return self._data.get(symbol)

    def get_many(self, symbols: Iterable[str]) -> Dict[str, Optional[MarketSnapshot]]:
        with self._lock:
            return {s: self._data.get(s) for s in symbols}

    def symbols(self) -> List[str]:
        with self._lock:
            return sorted(self._data.keys())

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "symbols": len(self._data),
                "updates": self._updates,
                "last_update_at": self._last_update_at,
                "stale_seconds": time.time() - self._last_update_at if self._last_update_at else None,
            }


_store: Optional[MarketDataStore] = None


def get_store() -> MarketDataStore:
    global _store
    if _store is None:
        _store = MarketDataStore()
    return _store
