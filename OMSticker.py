# -*- coding: utf-8 -*-
"""OMSticker.py

Market Ticker Bar — barra de variaciones de activos clave.

Activos parametrizables por duration (CER, Tasa Fija) o fijos (Hard Dollar,
Merval, EWZ, DLR/SPOT, Caución 1D).

Thread daemon de background, refresh cada N segundos.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import OMSmktdata
import OMSprices


# ──────────────────────────────────────────────────────────────────────
# Activos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TickerAsset:
    label: str
    symbol: str
    market_id: str = "ROFX"
    is_tna: bool = False


# Activos fijos
FIXED_ASSETS: List[TickerAsset] = [
    # Hard Dollar
    TickerAsset("GD30C",      "MERV - XMEV - GD30C - 24hs"),
    TickerAsset("GD35C",      "MERV - XMEV - GD35C - 24hs"),
    TickerAsset("GD41C",      "MERV - XMEV - GD41C - 24hs"),
    # Equity
    TickerAsset("Merval",     "MERV - XMEV - I.MERVAL - 24hs"),
    TickerAsset("EWZ",        "MERV - XMEV - EWZ - 24hs"),
    # FX — DLR/SPOT va DIRECTO al ROFX, sin prefijo MERV - XMEV
    # TickerAsset("DLR/SPOT",   "DLR/SPOT", market_id="ROFX"),
    # Caución 1D
    TickerAsset("Caución 1D", "MERV - XMEV - PESOS - 1D", is_tna=True),
]


# Parametrizables por duration
PARAMETRIC_ASSETS = [
    ("CER", "cer",   [0.5, 1.0, 2.5]),
    ("TF",  "lecap", [0.25, 0.7, 1.0]),
]


# ──────────────────────────────────────────────────────────────────────
# Selección por duration
# ──────────────────────────────────────────────────────────────────────

def select_by_duration(
    df_curve: pd.DataFrame,
    target_durations: List[float],
    code_col: str = "Código",
    dur_col: str = "Duration",
) -> List[str]:
    if df_curve is None or df_curve.empty:
        return []
    df = df_curve[[code_col, dur_col]].copy()
    df[dur_col] = pd.to_numeric(df[dur_col], errors="coerce")
    df = df.dropna(subset=[dur_col])
    if df.empty:
        return []

    selected = []
    used = set()
    for target in target_durations:
        df["_dist"] = (df[dur_col] - target).abs()
        candidates = df[~df[code_col].isin(used)]
        if candidates.empty:
            continue
        best_idx = candidates["_dist"].idxmin()
        code = str(candidates.loc[best_idx, code_col])
        selected.append(code)
        used.add(code)
    return selected


def build_parametric_symbols(
    curve_tables: Dict[str, pd.DataFrame],
    plazo: str = "24hs",
) -> List[TickerAsset]:
    assets = []
    suf = "24hs" if str(plazo).lower().startswith("24") else "CI"
    for label_prefix, curve_key, targets in PARAMETRIC_ASSETS:
        df = curve_tables.get(curve_key)
        if df is None or df.empty:
            continue
        codes = select_by_duration(df, targets)
        for code in codes:
            assets.append(TickerAsset(
                label=f"{label_prefix} {code}",
                symbol=f"MERV - XMEV - {code} - {suf}",
            ))
    return assets


# ──────────────────────────────────────────────────────────────────────
# Fetch
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TickerData:
    label: str
    last: float
    close: float
    variation: float
    is_tna: bool = False

    @property
    def var_pct_str(self) -> str:
        if not np.isfinite(self.variation):
            return "—"
        sign = "+" if self.variation >= 0 else ""
        return f"{sign}{self.variation:.2%}"

    def var_color(self, dark: bool = False) -> str:
        """Verde si sube, rojo si baja, gris si ~0 (< 0.05%)."""
        if not np.isfinite(self.variation):
            return "#8b949e"
        if abs(self.variation) < 0.0005:  # < 0.05%
            return "#8b949e"
        return "#2ecc71" if self.variation > 0 else "#e74c3c"

    @property
    def price_str(self) -> str:
        if not np.isfinite(self.last):
            return "—"
        if self.is_tna:
            return f"{self.last:.2f}%"
        if self.last >= 1000:
            return f"{self.last:,.0f}"
        return f"{self.last:,.2f}"


# Cache
_ticker_lock = threading.Lock()
_ticker_cache: List[TickerData] = []
_ticker_cache_ts: float = 0.0
_TICKER_TTL: int = 15

_ticker_bg_thread: Optional[threading.Thread] = None
_ticker_bg_running = False


def fetch_ticker_data(session, assets: List[TickerAsset]) -> List[TickerData]:
    if not assets:
        return []

    # Agrupar por market_id
    by_market: Dict[str, List[TickerAsset]] = {}
    for a in assets:
        by_market.setdefault(a.market_id, []).append(a)

    results: Dict[str, TickerData] = {}

    for market_id, group in by_market.items():
        symbols = [a.symbol for a in group]
        raw = OMSmktdata.bulk_market_data(
            session, symbols,
            market_id=market_id,
            entries="LA,CL,SE",
            depth=1,
        )
        if raw is None or raw.empty:
            continue

        snap = OMSprices.market_snapshot(raw)
        if snap is None or snap.empty:
            continue

        for a in group:
            if a.symbol not in snap.index:
                continue
            r = snap.loc[a.symbol]
            last_val = float(r.get("last", np.nan))
            close_val = float(r.get("close", np.nan))

            # Fallback SE como close
            if not np.isfinite(close_val) and a.symbol in raw.index and "SE" in raw.columns:
                se = OMSprices.extract_price(raw.loc[a.symbol, "SE"])
                if np.isfinite(se):
                    close_val = se

            var = (last_val / close_val - 1.0) if (
                np.isfinite(last_val) and np.isfinite(close_val) and close_val != 0
            ) else np.nan

            results[a.symbol] = TickerData(
                label=a.label, last=last_val, close=close_val,
                variation=var, is_tna=a.is_tna,
            )

    return [results[a.symbol] for a in assets if a.symbol in results]


def _refresh_ticker(session, assets: List[TickerAsset]):
    global _ticker_cache, _ticker_cache_ts
    data = fetch_ticker_data(session, assets)
    with _ticker_lock:
        _ticker_cache = data
        _ticker_cache_ts = time.time()


def _ticker_bg_worker(session, assets: List[TickerAsset], interval: int):
    global _ticker_bg_running
    while _ticker_bg_running:
        try:
            _refresh_ticker(session, assets)
        except Exception:
            pass
        time.sleep(interval)


def start_ticker_background(session, assets: List[TickerAsset], interval: int = 15):
    global _ticker_bg_thread, _ticker_bg_running
    if _ticker_bg_thread is not None and _ticker_bg_thread.is_alive():
        return
    _ticker_bg_running = True
    _ticker_bg_thread = threading.Thread(
        target=_ticker_bg_worker, args=(session, assets, interval), daemon=True,
    )
    _ticker_bg_thread.start()


def get_ticker_data(session=None, assets: Optional[List[TickerAsset]] = None,
                    force_refresh: bool = False) -> List[TickerData]:
    if force_refresh or not _ticker_cache or (time.time() - _ticker_cache_ts) > _TICKER_TTL:
        if session is not None and assets is not None:
            _refresh_ticker(session, assets)
    with _ticker_lock:
        return list(_ticker_cache)


# ──────────────────────────────────────────────────────────────────────
# HTML marquesina — adaptativa light/dark
# ──────────────────────────────────────────────────────────────────────

def ticker_marquee_html(
    data: Optional[List[TickerData]] = None,
    speed: int = 50,
    dark: bool = False,
) -> str:
    """Genera HTML de marquesina con precios.

    Args:
        speed: segundos para una pasada (más alto = más lento, sync con news).
        dark: True para Bloomberg mode, False para light.
    """
    if data is None:
        data = get_ticker_data()
    if not data:
        return ""

    if dark:
        bg = "linear-gradient(90deg, #161b22 0%, #0d1117 50%, #161b22 100%)"
        border_top = "#ff9800"
        border_bot = "#30363d"
        label_color = "#ff9800"
        price_color = "#e6e6e6"
    else:
        bg = "linear-gradient(90deg, #e8ecf1 0%, #f8f9fa 50%, #e8ecf1 100%)"
        border_top = "#1a5276"
        border_bot = "#d0d7de"
        label_color = "#1a5276"
        price_color = "#1c1c1c"

    parts = []
    for d in data:
        arrow = "▲" if d.variation > 0.0005 else "▼" if d.variation < -0.0005 else "●" if np.isfinite(d.variation) else ""
        vc = d.var_color(dark)
        parts.append(
            f'<span style="color:{label_color};font-weight:700;">{d.label}</span>'
            f'&nbsp;<span style="color:{price_color};font-weight:600;">{d.price_str}</span>'
            f'&nbsp;<span style="color:{vc};font-weight:600;">'
            f'{arrow} {d.var_pct_str}</span>'
        )

    separator = '&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;'
    ticker_text = separator.join(parts)

    return f"""
<div style="
    background: {bg};
    border-top: 2px solid {border_top};
    border-bottom: 1px solid {border_bot};
    padding: 8px 0;
    overflow: hidden;
    white-space: nowrap;
    font-size: 13px;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    letter-spacing: 0.3px;
">
    <div style="
        display: inline-block;
        animation: ticker_scroll {speed}s linear infinite;
        padding-left: 100%;
    ">
        {ticker_text}
    </div>
</div>
<style>
@keyframes ticker_scroll {{
    0%   {{ transform: translateX(0%); }}
    100% {{ transform: translateX(-100%); }}
}}
</style>
"""
