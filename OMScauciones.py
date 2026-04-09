# -*- coding: utf-8 -*-
"""OMScauciones.py

Monitor de Cauciones BYMA (Pesos y Dólares).

Symbols:
  - Pesos:  MERV - XMEV - PESOS - {n}D   (n = 1..120)
  - Dólares: MERV - XMEV - DOLAR - {n}D   (n = 1..120)

No calcula TIRs — la caución se negocia directamente por TNA.
Tabla ligera de lectura rápida estilo Bloomberg.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

import OMSmktdata
import OMSprices
import OMSsettings as cfg


# ──────────────────────────────────────────────────────────────────────
# Generación de symbols
# ──────────────────────────────────────────────────────────────────────

PLAZOS_DEFAULT: List[int] = [1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 35, 60, 90, 120]


def caucion_symbols(moneda: str = "PESOS", plazos: Optional[List[int]] = None) -> List[str]:
    m = moneda.upper()
    if m not in ("PESOS", "DOLAR"):
        raise ValueError("moneda debe ser 'PESOS' o 'DOLAR'")
    ps = plazos or PLAZOS_DEFAULT
    return [f"MERV - XMEV - {m} - {n}D" for n in ps]


def _plazo_from_symbol(symbol: str) -> int:
    try:
        part = symbol.strip().split(" - ")[-1]
        return int(part.replace("D", "").strip())
    except Exception:
        return 0


def _moneda_from_symbol(symbol: str) -> str:
    return "USD" if "DOLAR" in symbol.upper() else "ARS"


# ──────────────────────────────────────────────────────────────────────
# Fetch + snapshot
# ──────────────────────────────────────────────────────────────────────

def _extract_timestamp(raw_df: pd.DataFrame, symbol: str) -> str:
    """Intenta extraer la hora de la última operación desde el entry LA."""
    try:
        la = raw_df.loc[symbol, "LA"]
        if isinstance(la, list) and la:
            la = la[0]
        if isinstance(la, dict):
            ts = la.get("date") or la.get("datetime") or la.get("time") or la.get("timestamp")
            if ts is not None:
                s = str(ts)
                # Epoch ms
                if s.isdigit() and len(s) >= 10:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(int(s[:10]))
                    return dt.strftime("%H:%M:%S")
                # ISO string
                if "T" in s:
                    return s.split("T")[-1][:8]
                return s[-8:] if len(s) >= 8 else s
    except Exception:
        pass
    return "—"


def fetch_cauciones(
    session,
    moneda: str = "PESOS",
    plazos: Optional[List[int]] = None,
    entries: str = "LA,BI,OF,CL,OP,TV,NV,EV",
    depth: int = 1,
) -> pd.DataFrame:
    """Fetchea market data de cauciones y devuelve tabla procesada.

    Columnas (en orden):
        Plazo, Moneda, Apertura TNA, Cierre TNA, Variación %,
        Bid TNA, Bid Size, Last TNA, Offer TNA, Offer Size,
        Hora, Volumen Operado
    """
    symbols = caucion_symbols(moneda, plazos)

    raw = OMSmktdata.bulk_market_data(
        session, symbols,
        market_id="ROFX",
        entries=entries,
        depth=depth,
    )

    if raw is None or raw.empty:
        return pd.DataFrame()

    snap = OMSprices.market_snapshot(raw)
    if snap is None or snap.empty:
        return pd.DataFrame()

    # Volumen efectivo (EV) = monto operado
    vol_ev = pd.Series(np.nan, index=raw.index)
    if "EV" in raw.columns:
        vol_ev = raw["EV"].map(OMSprices.extract_size)

    rows = []
    for symbol in snap.index:
        r = snap.loc[symbol]
        plazo = _plazo_from_symbol(symbol)
        mon = _moneda_from_symbol(symbol)
        hora = _extract_timestamp(raw, symbol)

        rows.append({
            "Plazo": f"{plazo}D",
            "_plazo_num": plazo,
            "Moneda": mon,
            "Apertura TNA": r.get("open", np.nan),
            "Cierre TNA": r.get("close", np.nan),
            "Variación %": r.get("variation", np.nan),
            "Bid TNA": r.get("bid_price", np.nan),
            "Bid Size": r.get("bid_size", np.nan),
            "Last TNA": r.get("last", np.nan),
            "Offer TNA": r.get("offer_price", np.nan),
            "Offer Size": r.get("offer_size", np.nan),
            "Hora": hora,
            "Volumen Operado": vol_ev.get(symbol, np.nan),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("_plazo_num").reset_index(drop=True)

    # Filtrar plazos sin ningún dato
    data_cols = ["Bid TNA", "Offer TNA", "Last TNA", "Volumen Operado"]
    mask = df[data_cols].notna().any(axis=1)
    df = df[mask].reset_index(drop=True)

    display_cols = [
        "Plazo", "Moneda",
        "Apertura TNA", "Cierre TNA", "Variación %",
        "Bid TNA", "Bid Size",
        "Last TNA",
        "Offer TNA", "Offer Size",
        "Hora", "Volumen Operado",
    ]
    return df[[c for c in display_cols if c in df.columns]].copy()


# ──────────────────────────────────────────────────────────────────────
# Estilo (pandas Styler)
# ──────────────────────────────────────────────────────────────────────

def style_cauciones(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Estilo Bloomberg-style para la tabla de cauciones."""
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Apertura TNA": "{:.2f}%",
        "Cierre TNA": "{:.2f}%",
        "Bid TNA": "{:.2f}%",
        "Bid Size": "{:,.0f}",
        "Last TNA": "{:.2f}%",
        "Offer TNA": "{:.2f}%",
        "Offer Size": "{:,.0f}",
        "Variación %": "{:+.2%}",
        "Volumen Operado": "{:,.0f}",
    }

    sty = df.style.format(fmt, na_rep="—")

    # ── Last TNA en negrita siempre ──
    if "Last TNA" in df.columns:
        sty = sty.map(
            lambda v: "font-weight: 900; font-size: 13px;" if pd.notna(v) else "",
            subset=["Last TNA"],
        )

    # ── Variación % con color ──
    if "Variación %" in df.columns:
        var = pd.to_numeric(df["Variación %"], errors="coerce")
        lim = float(np.nanmax(np.abs(var.to_numpy(dtype="float64")))) if var.notna().any() else 0.01
        if not np.isfinite(lim) or lim <= 0:
            lim = 0.01

        sty = sty.bar(
            subset=["Variación %"], align="mid",
            color=["#fa7a7a", "#8bf58b"],
            vmin=-lim, vmax=lim,
        )

        def _var_color(val):
            try:
                x = float(val)
            except Exception:
                return ""
            if not np.isfinite(x):
                return ""
            a = min(abs(x) / lim, 1.0)
            if x > 0:
                return f"background-color: rgba(46,204,113,{0.12 + 0.55*a:.3f}); font-weight:700;"
            elif x < 0:
                return f"background-color: rgba(231,76,60,{0.12 + 0.55*a:.3f}); font-weight:700;"
            return ""

        sty = sty.map(_var_color, subset=["Variación %"])

    # ── Bid verde / Offer rojo ──
    if "Bid TNA" in df.columns:
        sty = sty.map(
            lambda v: "color: #1b8a3a; font-weight: 600;" if pd.notna(v) else "",
            subset=["Bid TNA"],
        )
    if "Offer TNA" in df.columns:
        sty = sty.map(
            lambda v: "color: #b02a37; font-weight: 600;" if pd.notna(v) else "",
            subset=["Offer TNA"],
        )

    # ── Separadores visuales ──
    table_styles = []
    if "Last TNA" in df.columns:
        j = df.columns.get_loc("Last TNA")
        table_styles.append({"selector": f"th.col{j}", "props": "border-left: 3px solid #444;"})
        table_styles.append({"selector": f"td.col{j}", "props": "border-left: 3px solid #444;"})
    if "Hora" in df.columns:
        j = df.columns.get_loc("Hora")
        table_styles.append({"selector": f"th.col{j}", "props": "border-left: 3px solid #444;"})
        table_styles.append({"selector": f"td.col{j}", "props": "border-left: 3px solid #444;"})
    if table_styles:
        sty = sty.set_table_styles(table_styles, overwrite=False)

    return sty
