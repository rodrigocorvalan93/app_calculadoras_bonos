# -*- coding: utf-8 -*-
"""OMScredit.py — Módulo de scoring crediticio corporativo

Carga credit_scores.json (exportado del Excel de analistas) y provee:
- Auto-matching emisor → tickers de bonos via nombre_security
- Lookup de métricas crediticias por bono o emisor
- Helpers para display en Streamlit (YAS + pestaña Crédito)

El JSON se carga UNA vez (~5ms, 30KB). El auto-match corre una vez
al llamar init() (~10ms para ~300 bonos). Zero overhead en cada rerun.

Para actualizar scores: correr export_credit_scores.py cuando los
analistas actualicen el Excel.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# Overrides manuales: bond_ticker → issuer_ticker
#
# Solo para casos donde el auto-match falla:
# - Datos sucios en el Excel (ej: ticker "ypf" con compania "edsh")
# - Nombres muy cortos o ambiguos
# - Bancos/financieras que no están en el Excel de corporativos
#
# Cuando cargás una ON nueva y el auto-match no la detecta, agregala acá.
# ──────────────────────────────────────────────────────────────────────

BOND_OVERRIDES: Dict[str, str] = {
    # YPF: en el Excel "ypf" tiene compania="edsh" (error de datos)
    "YCAMO": "ypf", "YMCJO": "ypf", "YMCVO": "ypf", "YMCXO": "ypf",
    "YMCUO": "ypf", "YMC1O": "ypf", "YMCHO": "ypf", "YMCTO": "ypf",
    "YMCRO": "ypf", "YMCWO": "ypf", "YMCYO": "ypf", "YMCZO": "ypf",
    "YM34O": "ypf", "YM35O": "ypf", "YM37O": "ypf", "YM38O": "ypf",
    "YM39O": "ypf", "YM40O": "ypf", "YM41O": "ypf", "YM42O": "ypf",
    "YMCIO": "ypf", "YFCJO": "ypf", "YFCAO": "ypf", "YFCFO": "ypf",
    "YFCDO": "ypf", "YFCIO": "ypf", "YFCKO": "ypf", "YFCLO": "ypf",
    "YFCMO": "ypf", "YFCNO": "ypf", "YFCOO": "ypf",
    # Capex: duplicado en Excel (capx y capex)
    "CP38O": "capx",
}


# ──────────────────────────────────────────────────────────────────────
# Auto-matching engine
# ──────────────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "de", "del", "la", "los", "las", "y", "e", "en", "el", "sa", "srl",
    "argentina", "argentino", "compañía", "compañia", "empresa",
    "sociedad", "ltda", "cia", "corp", "inc", "llc", "sucursal",
    "inversiones", "representaciones", "comercial", "industrial",
    "financiera", "financieros", "servicios", "clase", "vto",
    "serie", "tasa", "dólares", "dolares", "pesos", "banco",
})


def _tokenize(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r'[.,\-\(\)/"\'#%]', ' ', s)
    return [w for w in s.split() if len(w) > 2 and w not in _STOP_WORDS]


def _tok_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) > 5 and len(b) > 5:
        return a in b or b in a
    return False


def _auto_match(bond_name: str, issuer_tokens: Dict[str, List[str]]) -> Optional[str]:
    """Matchea un nombre de bono contra emisores usando coverage scoring."""
    bond_toks = _tokenize(bond_name)
    if not bond_toks:
        return None

    best = None
    best_score = 0.0

    for issuer_ticker, itoks in issuer_tokens.items():
        if not itoks:
            continue
        matched = sum(1 for it in itoks
                      if any(_tok_match(it, bt) for bt in bond_toks))
        if matched == 0:
            continue
        coverage = matched / len(itoks)
        score = coverage + matched * 0.1
        if score > best_score:
            best_score = score
            best = issuer_ticker

    return best if best and best_score >= 0.4 else None


def build_issuer_mapping(bonos: list, credit_data: List[Dict[str, Any]]) -> Dict[str, str]:
    """Construye bond_ticker → issuer_ticker automáticamente."""
    issuer_tokens: Dict[str, List[str]] = {}
    for r in credit_data:
        toks = _tokenize(r.get("compania", ""))
        if toks:
            issuer_tokens[r["ticker"]] = toks

    mapping: Dict[str, str] = {}

    for b in bonos:
        code = (getattr(b, "ticker", None) or getattr(b, "codigo", None)
                or getattr(b, "symbol", None))
        if not code:
            continue

        if code in BOND_OVERRIDES:
            mapping[code] = BOND_OVERRIDES[code]
            continue

        nombre = getattr(b, "nombre_security", "")
        if not nombre:
            continue

        clas = getattr(b, "clasificacion", "") or ""
        if "Corporativo" not in clas and "Sub-soberano" not in clas:
            continue

        issuer = _auto_match(nombre, issuer_tokens)
        if issuer:
            mapping[code] = issuer

    return mapping


# ──────────────────────────────────────────────────────────────────────
# Carga del JSON
# ──────────────────────────────────────────────────────────────────────

_CREDIT_JSON = "credit_scores.json"


def _find_json_path() -> str:
    here = Path(__file__).parent
    p = here / _CREDIT_JSON
    if p.exists():
        return str(p)
    if Path(_CREDIT_JSON).exists():
        return _CREDIT_JSON
    return str(p)


def load_credit_data() -> List[Dict[str, Any]]:
    path = _find_json_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# ──────────────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────────────

_CACHE: Dict[str, Any] = {}


def _ensure_loaded():
    if "lookup" not in _CACHE:
        data = load_credit_data()
        _CACHE["data"] = data
        _CACHE["lookup"] = {r["ticker"]: r for r in data if "ticker" in r}
        _CACHE["bond_to_issuer"] = {}
        _CACHE["issuer_to_bonds"] = {}


def init(bonos: list):
    """Inicializa el auto-match. Llamar una vez con todos_los_bonos."""
    _ensure_loaded()
    data = _CACHE.get("data", [])
    if not data:
        return

    b2i = build_issuer_mapping(bonos, data)
    _CACHE["bond_to_issuer"] = b2i

    i2b: Dict[str, List[str]] = {}
    for bond, issuer in b2i.items():
        i2b.setdefault(issuer, []).append(bond)
    _CACHE["issuer_to_bonds"] = i2b


# ──────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────

def get_issuer_for_bond(bond_ticker: str) -> Optional[str]:
    _ensure_loaded()
    clean = bond_ticker.rstrip("jv") if bond_ticker[-1:] in ("j", "v") else bond_ticker
    return _CACHE.get("bond_to_issuer", {}).get(clean)


def get_credit(issuer_ticker: str) -> Optional[Dict[str, Any]]:
    _ensure_loaded()
    return _CACHE.get("lookup", {}).get(issuer_ticker.lower())


def get_credit_for_bond(bond_ticker: str) -> Optional[Dict[str, Any]]:
    issuer = get_issuer_for_bond(bond_ticker)
    return get_credit(issuer) if issuer else None


def get_bonds_for_issuer(issuer_ticker: str) -> List[str]:
    _ensure_loaded()
    return _CACHE.get("issuer_to_bonds", {}).get(issuer_ticker.lower(), [])


def get_all_issuers_df() -> pd.DataFrame:
    _ensure_loaded()
    data = _CACHE.get("data", [])
    if not data:
        return pd.DataFrame()

    i2b = _CACHE.get("issuer_to_bonds", {})
    rows = []
    for r in data:
        ticker = r.get("ticker", "")
        rows.append({
            "Emisor": r.get("compania", ""),
            "Ticker": ticker,
            "Sector": r.get("sector", ""),
            "Score": r.get("score"),
            "Solvencia": r.get("score_solvencia"),
            "Liquidez": r.get("score_liquidez"),
            "Net Debt/EBITDA": r.get("net_debt_ebitda"),
            "EBITDA/Interest": r.get("ebitda_net_interest"),
            "(EBITDA-CAPEX)/Int": r.get("ebitda_capex_net_interest"),
            "Current Ratio": r.get("current_ratio"),
            "Pasivo/PN": r.get("pasivo_pn"),
            "Liq. Ratio": r.get("liquidity_ratio"),
            "% ST Debt": r.get("pct_st_debt"),
            "DFN (USD M)": r.get("deuda_fin_neta_usd"),
            "EBITDA (USD M)": r.get("ebitda_usd"),
            "Last Q": r.get("last_q", ""),
            "ONs cargadas": len(i2b.get(ticker, [])),
            "Comentario": r.get("comentario", ""),
        })

    df = pd.DataFrame(rows)
    if "Score" in df.columns:
        df = df.sort_values("Score", ascending=False, na_position="last").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────────────

def _score_color(score) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(s):
        return ""
    if s >= 4.5:
        return "background-color: rgba(46,204,113,0.35);"
    if s >= 3.5:
        return "background-color: rgba(46,204,113,0.15);"
    if s >= 2.5:
        return "background-color: rgba(243,156,18,0.20);"
    if s >= 1.5:
        return "background-color: rgba(231,76,60,0.20);"
    return "background-color: rgba(231,76,60,0.40);"


def style_credit_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df is None or df.empty:
        return pd.DataFrame().style

    fmt = {
        "Score": "{:.1f}", "Solvencia": "{:.1f}", "Liquidez": "{:.1f}",
        "Net Debt/EBITDA": "{:.2f}x", "EBITDA/Interest": "{:.1f}x",
        "(EBITDA-CAPEX)/Int": "{:.1f}x", "Current Ratio": "{:.2f}x",
        "Pasivo/PN": "{:.2f}x", "Liq. Ratio": "{:.1f}x",
        "% ST Debt": "{:.0%}", "DFN (USD M)": "{:,.0f}",
        "EBITDA (USD M)": "{:,.0f}", "ONs cargadas": "{:.0f}",
    }

    sty = df.style.format(fmt, na_rep="—")

    if "Score" in df.columns:
        sty = sty.map(lambda v: _score_color(v) if pd.notna(v) else "", subset=["Score"])

    for col in ["Solvencia", "Liquidez"]:
        if col in df.columns:
            sty = sty.background_gradient(subset=[col], cmap="RdYlGn", vmin=1, vmax=5)

    return sty
