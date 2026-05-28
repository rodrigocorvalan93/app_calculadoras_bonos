# -*- coding: utf-8 -*-
"""OMSprices.py

Helpers de extracción / normalización de MarketData (REST OMS/Primary).

Notas:
- Los entries (LA, CL, OP, HI, LO, BI, OF, TV, NV, etc.) vienen como dict o list[dict].
- Este módulo intenta ser robusto: si cambia la forma del JSON, no rompe.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return a / b if (a is not None and b not in (0, 0.0, np.nan)) else None


# -----------------------------------------------------------------------------
# Parsers robustos
# -----------------------------------------------------------------------------

def _first(x: Any) -> Any:
    """Si x es lista, devuelve el primer elemento; si no, devuelve x."""
    if isinstance(x, list):
        return x[0] if x else None
    return x


def _extract_num_from_dict(d: dict, keys: tuple[str, ...]) -> float:
    for k in keys:
        if k in d and d[k] is not None:
            return float(d[k])
    return np.nan


def extract_price(entry: Any) -> float:
    """Intenta extraer 'price' (float)."""
    e = _first(entry)
    if isinstance(e, dict):
        return _extract_num_from_dict(e, ("price", "px", "value"))
    if isinstance(e, (int, float, np.floating)):
        return float(e)
    return np.nan


def extract_size(entry: Any) -> float:
    """Intenta extraer 'size' (float)."""
    e = _first(entry)
    if isinstance(e, dict):
        return _extract_num_from_dict(e, ("size", "qty", "quantity", "volume", "nominal", "amount"))
    if isinstance(e, (int, float, np.floating)):
        return float(e)
    return np.nan


def extract_date(entry: Any):
    """Extrae 'date' del entry y lo convierte a Timestamp tz-aware (Argentina) o None.

    BYMA suele enviar millis epoch como número. También se aceptan segundos epoch
    e ISO strings.
    """
    e = _first(entry)
    if not isinstance(e, dict):
        return None
    for k in ("date", "datetime", "timestamp", "ts"):
        v = e.get(k)
        if v is None:
            continue
        try:
            if isinstance(v, (int, float)):
                if v > 1e12:
                    ts = pd.to_datetime(v, unit="ms", utc=True, errors="coerce")
                elif v > 1e9:
                    ts = pd.to_datetime(v, unit="s", utc=True, errors="coerce")
                else:
                    continue
            else:
                ts = pd.to_datetime(v, utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            try:
                return ts.tz_convert("America/Argentina/Buenos_Aires")
            except Exception:
                return ts
        except Exception:
            continue
    return None


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def market_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Aplana un DataFrame de marketdata (index=symbol) a un snapshot tabular.

    Devuelve columnas (si están disponibles):
      - last, close, open, high, low
      - bid_price, bid_size, offer_price, offer_size
      - volume (prioriza TV, fallback NV)
      - variation (last/close - 1)
      - change (last - close)
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)

    # Precios básicos
    # Fallback post-mercado: si LA/CL vienen vacíos, BYMA suele publicar ACP
    # (auction close price) como referencia oficial.
    la_raw = pd.to_numeric(df["LA"].map(extract_price), errors="coerce") if "LA" in df.columns else pd.Series(np.nan, index=df.index, dtype="float64")
    cl_raw = pd.to_numeric(df["CL"].map(extract_price), errors="coerce") if "CL" in df.columns else pd.Series(np.nan, index=df.index, dtype="float64")
    acp = pd.to_numeric(df["ACP"].map(extract_price), errors="coerce") if "ACP" in df.columns else pd.Series(np.nan, index=df.index, dtype="float64")

    la_d = df["LA"].map(extract_date) if "LA" in df.columns else pd.Series(None, index=df.index, dtype="object")
    cl_d = df["CL"].map(extract_date) if "CL" in df.columns else pd.Series(None, index=df.index, dtype="object")
    acp_d = df["ACP"].map(extract_date) if "ACP" in df.columns else pd.Series(None, index=df.index, dtype="object")

    out["close"] = cl_raw.fillna(acp)
    out["close_source"] = np.where(cl_raw.notna(), "CL", np.where(acp.notna(), "ACP", None))
    out["close_date"] = np.where(cl_raw.notna(), cl_d, np.where(acp.notna(), acp_d, None))

    out["last"] = la_raw.fillna(out["close"])
    out["last_source"] = np.where(
        la_raw.notna(), "LA",
        np.where(cl_raw.notna(), "CL", np.where(acp.notna(), "ACP", None))
    )
    out["last_date"] = np.where(
        la_raw.notna(), la_d,
        np.where(cl_raw.notna(), cl_d, np.where(acp.notna(), acp_d, None))
    )

    if "OP" in df.columns:
        out["open"] = df["OP"].map(extract_price)
    else:
        out["open"] = np.nan

    if "HI" in df.columns:
        out["high"] = df["HI"].map(extract_price)
    else:
        out["high"] = np.nan

    if "LO" in df.columns:
        out["low"] = df["LO"].map(extract_price)
    else:
        out["low"] = np.nan

    if "IV" in df.columns:
        out["index_value"] = df["IV"].map(extract_price)
    else:
        out["index_value"] = np.nan

    # Book (best)
    if "BI" in df.columns:
        out["bid_price"] = df["BI"].map(extract_price)
        out["bid_size"] = df["BI"].map(extract_size)
    else:
        out["bid_price"] = np.nan
        out["bid_size"] = np.nan

    if "OF" in df.columns:
        out["offer_price"] = df["OF"].map(extract_price)
        out["offer_size"] = df["OF"].map(extract_size)
    else:
        out["offer_price"] = np.nan
        out["offer_size"] = np.nan

    # Volumen: prioriza TV, fallback NV (fila a fila)
    vol_tv = df["TV"].map(extract_size) if "TV" in df.columns else pd.Series(np.nan, index=df.index)
    vol_nv = df["NV"].map(extract_size) if "NV" in df.columns else pd.Series(np.nan, index=df.index)
    out["volume"] = vol_tv.fillna(vol_nv)

    # VWAP intradía (si la API lo expone como entry WA)
    if "WA" in df.columns:
        out["vwap"] = df["WA"].map(extract_price)
    else:
        out["vwap"] = np.nan

    # Trade count del día (entry TC, si está)
    if "TC" in df.columns:
        out["trade_count"] = df["TC"].map(extract_size)
    else:
        out["trade_count"] = np.nan

    # Variaciones
    with np.errstate(divide="ignore", invalid="ignore"):
        out["variation"] = out["last"] / out["close"] - 1
        out["change"] = out["last"] - out["close"]

    return out


def last_price(df: pd.DataFrame) -> pd.DataFrame:
    """Compat: extrae último y cierre + variación."""
    snap = market_snapshot(df)
    if snap.empty:
        return pd.DataFrame()
    return snap[["last", "close", "variation"]].copy()