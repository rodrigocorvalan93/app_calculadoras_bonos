# -*- coding: utf-8 -*-
"""delta_especies.py — Loader de la base interna de especies Delta.

Lee `Delta - Especies.xlsx` (hoja "Base RF") y expone metadata adicional por
bono (clasificación, emisor, sector, calificación, callable, códigos, etc.)
para enriquecer Posiciones, YAS y Comparador.

Configuración (secrets.txt):
    DELTA_ESPECIES_PATH=%USERPROFILE%\\DELTA ASSET MANAGEMENT S.A\\Inversiones - Documentos\\Delta Bases\\Delta - Especies.xlsx

Fallback:
    Si no se setea, busca `Delta - Especies.xlsx` en `DELTA_BASES_DIR/..`
    (la carpeta padre de Carteras), ya que las carteras viven en
    `Delta Bases/Carteras` y este archivo en `Delta Bases/`.

Diseño:
    - Cache 24h (el archivo cambia ≤ 2 veces por día).
    - Llave de match con nuestros códigos: columna **BYMA** (≠ Cod_Delta
      en algunos casos: e.g. "M31G6 CI" → BYMA "M31G6").
    - Failure-silent: si el archivo no existe / da error, retorna DF vacío
      y `get_especie_info(code)` → {}.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

_ESPECIES_FILENAME = "Delta - Especies.xlsx"
_SHEET_RF = "Base RF"
_HEADER_ROWS = [2, 3]  # multi-header (grupo + campo)

# Columnas a conservar de Base RF (post-flatten del multi-header).
# Si una columna no existe, se ignora silenciosamente.
_KEEP_COLS: List[str] = [
    "Cod_Delta", "Corto", "Descripción", "Nombre",
    # Moneda / Tasa
    "Pago", "Ajuste", "Cotización", "Tasa", "Cupón",
    "Valuación Ref.", "Exposición", "Emisión", "Vencimiento",
    # Callable
    "Call_Tiene", "Total_Parcial",
    "Fecha_Call", "Precio_Call",
    "Fecha_Call_2", "Precio_Call_2",
    "Fecha_Call_3", "Precio_Call_3",
    # Categorías
    "Clase de Activo", "Subclase de Activo", "Terclase de Activo",
    "Geografía", "Legislación", "Plazo", "Instrumento",
    "CAFCI_Nivel0", "CAFCI_Nivel1", "CAFCI_Nivel2",
    "Cap", "VGB", "Ciclo",
    "Pais de Domicilio", "Pais de Riesgo", "Pais de Cotizacion",
    "Pais Clasificación", "CNV_Local_Extranjero",
    # Emisor
    "Emisor / Sponsor", "Cod Emisor", "Grupo Emisor",
    "Sector", "Grupo Industria", "Industria", "Sub Industria",
    "Sector Delta", "Clasificacion_asg", "Clasificacion_especifico",
    # Códigos
    "ECONOMÁTICA", "ISIN", "BYMA", "BYMA_API",
    "CAFCI_BYMA", "BLOOM", "FIGI", "REUTERS",
    "Precio_Elegido", "Precios_Back", "Plazo_Precio",
    # Subyacente
    "Subyacente",
    # Calificaciones
    "Califica_Local", "Califica_Extranjera", "Calificadora",
    "Ultima Revisión", "Fecha FIX",
]


def _resolve_path() -> Optional[str]:
    """Resuelve ruta al Excel de especies. Prioridad:
      1. DELTA_ESPECIES_PATH (ruta completa al archivo).
      2. DELTA_BASES_DIR / ../Delta - Especies.xlsx (sube un nivel desde Carteras).
      3. DELTA_BASES_DIR / Delta - Especies.xlsx (por si está en la misma carpeta).
    Retorna None si nada existe.
    """
    env = os.getenv("DELTA_ESPECIES_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env

    base = os.getenv("DELTA_BASES_DIR")
    if base:
        base = os.path.expandvars(os.path.expanduser(base))
        for candidate in (
            os.path.join(os.path.dirname(base.rstrip("\\/")), _ESPECIES_FILENAME),
            os.path.join(base, _ESPECIES_FILENAME),
        ):
            if os.path.isfile(candidate):
                return candidate
    return None


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Aplana el multi-header (grupo, campo) → campo, descartando Unnamed."""
    new_cols = []
    for c in df.columns:
        if isinstance(c, tuple):
            a, b = c
            name = b if isinstance(b, str) and not b.startswith("Unnamed") else a
        else:
            name = c
        new_cols.append(name)
    df = df.copy()
    df.columns = new_cols
    return df


@st.cache_data(ttl=86_400, show_spinner=False)
def load_delta_especies() -> pd.DataFrame:
    """DataFrame con metadata Delta indexado por código BYMA.

    Cacheado 24 h. Retorna DataFrame vacío si el archivo no está disponible.
    """
    path = _resolve_path()
    if path is None:
        return pd.DataFrame()

    try:
        raw = pd.read_excel(path, sheet_name=_SHEET_RF, header=_HEADER_ROWS)
    except Exception:
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    df = _flatten_columns(raw)

    # Quedarnos con columnas útiles que efectivamente existen
    cols = [c for c in _KEEP_COLS if c in df.columns]
    if "BYMA" not in cols:
        return pd.DataFrame()
    df = df[cols].copy()

    # Normalizaciones livianas
    df["BYMA"] = df["BYMA"].astype(str).str.strip().str.upper()
    df = df[df["BYMA"].notna() & (df["BYMA"] != "") & (df["BYMA"] != "NAN")]

    if "Cod_Delta" in df.columns:
        df["Cod_Delta"] = df["Cod_Delta"].astype(str).str.strip().str.upper()
    if "ISIN" in df.columns:
        df["ISIN"] = df["ISIN"].astype(str).str.strip()

    # Deduplicar por BYMA: si hay múltiples filas para el mismo BYMA
    # (ej. CI vs 24hs), tomar la primera (la base ya trae prioridad).
    df = df.drop_duplicates(subset=["BYMA"], keep="first").reset_index(drop=True)
    return df


@st.cache_data(ttl=86_400, show_spinner=False)
def especies_lookup() -> Dict[str, Dict[str, Any]]:
    """Dict {BYMA → fila como dict}. O(1) per-code, cacheado 24 h."""
    df = load_delta_especies()
    if df is None or df.empty:
        return {}
    return df.set_index("BYMA").to_dict("index")


def get_especie_info(code: Optional[str]) -> Dict[str, Any]:
    """Devuelve metadata Delta para un código (BYMA o Cod_Delta). {} si no hay."""
    if not code:
        return {}
    c = str(code).strip().upper()
    lk = especies_lookup()
    if c in lk:
        return lk[c]
    # Fallback por Cod_Delta (e.g. 'M31G6 CI')
    df = load_delta_especies()
    if df is None or df.empty or "Cod_Delta" not in df.columns:
        return {}
    m = df[df["Cod_Delta"] == c]
    if m.empty:
        return {}
    return m.iloc[0].to_dict()


def is_available() -> bool:
    """True si el Excel se cargó con al menos 1 fila."""
    df = load_delta_especies()
    return df is not None and not df.empty


# ──────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ──────────────────────────────────────────────────────────────────────

# Subset 'pretty' para mostrar en YAS/Comparador (orden lógico).
_PRETTY_FIELDS: List[str] = [
    "Emisor / Sponsor", "Grupo Emisor",
    "Sector Delta", "Sector", "Sub Industria", "Industria",
    "Clasificacion_especifico", "Clasificacion_asg",
    "Clase de Activo", "Subclase de Activo", "Terclase de Activo",
    "Instrumento", "Ajuste", "Tasa", "Cupón",
    "Plazo", "Geografía", "Legislación", "Pais de Riesgo",
    "Calificadora", "Califica_Local", "Califica_Extranjera",
    "Ultima Revisión", "Fecha FIX",
    "Call_Tiene", "Total_Parcial",
    "Fecha_Call", "Precio_Call", "Fecha_Call_2", "Precio_Call_2",
    "Fecha_Call_3", "Precio_Call_3",
    "Emisión", "Vencimiento", "Valuación Ref.",
    "ISIN", "BLOOM", "BYMA", "Cod_Delta",
]


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if not np.isfinite(v):
            return "—"
        # Heurística: si parece fecha (timestamp), no formatear como float
        return f"{v:,.4f}".rstrip("0").rstrip(".") or "0"
    try:
        if pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        pass
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%d/%m/%Y")
        except Exception:
            return str(v)
    s = str(v).strip()
    return s if s and s.lower() != "nan" else "—"


def pretty_info(code: str) -> List[tuple]:
    """Lista [(campo, valor_str)] para mostrar — sólo campos con valor real."""
    info = get_especie_info(code)
    if not info:
        return []
    out: List[tuple] = []
    for f in _PRETTY_FIELDS:
        if f in info:
            s = _fmt_val(info[f])
            if s and s != "—":
                out.append((f, s))
    return out
