# -*- coding: utf-8 -*-
"""OMSposiciones.py — Carteras / Tenencias / Matriz de Posiciones

Carga los 3 Excel de carteras desde la carpeta configurada en secrets.txt
vía la variable DELTA_BASES_DIR:

    $DELTA_BASES_DIR/
        Delta_Composicion.xlsx  (tenencias por fondo)
        Delta_PN.xlsx           (patrimonio neto por fondo)
        Delta_Futuros.xlsx      (futuros ROFEX por fondo)

El mapeo CodFondo → Nombre se lee de un .txt exportado del back (Esco).
Se busca en orden: DELTA_FONDOS_PATH (ruta explícita), luego
DELTA_BASES_DIR/../Text/Esco/Delta_Fondos.txt (ubicación estándar).
Si no se encuentra, cae a un dict hardcodeado de fallback.

Expone 3 renders:
    render_tab_posiciones(username, password, plazo)   # 1 fondo → TIR/DUR/VN/%PN + futuros
    render_tab_buscador(username, password, plazo)     # 1 especie → en qué fondos está
    render_tab_matriz()                                # matriz especies×fondos

El módulo reutiliza el pipeline existente de OMSweb_app:
    - _global_snapshot / _effective_price_series  → precios vivos
    - _parallel_metrics                            → TIREA / Duration / TEM / Paridad
    - BONDS                                        → universo de instrumentos con curva

Diseño Bloomberg:
    - % sobre PN con barras horizontales
    - TIR / Duration con deadband 0.05%
    - Adaptativo dark/light (hereda el tema global del app)

Compatible Python < 3.10 (anotaciones con quoted strings donde aplica).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

import delta_especies

# ──────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────

_BASES_DIR_ENV = "DELTA_BASES_DIR"

_COMPOSICION_FILE = "Delta_Composicion.xlsx"
_PN_FILE = "Delta_PN.xlsx"
_FUTUROS_FILE = "Delta_Futuros.xlsx"

# Mapeo de fondos: archivo de texto exportado del back interno (Esco).
# Se configura vía secrets.txt → DELTA_FONDOS_PATH (ruta completa al .txt),
# típicamente algo como:
#   %USERPROFILE%\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Delta Bases\Text\Esco\Delta_Fondos.txt
_FONDOS_PATH_ENV = "DELTA_FONDOS_PATH"

# Fallback hardcodeado (provisto por Rorru) — sólo se usa si Delta_Fondos.txt
# no está disponible. Mantener sincronizado a mano hasta que el archivo esté
# garantizado en todos los entornos.
_FONDO_NOMBRES_FALLBACK: Dict[int, str] = {
    1: "Acciones",
    2: "Ahorro",
    13: "Ahorro Plus",
    39: "Cohen Pesos",
    18: "Crecimiento",
    37: "CRF DOL",
    14: "FEDERAL I",
    15: "Gestion I",
    16: "Gestion II",
    19: "Gestion III",
    9: "Gestion IV",
    28: "Gestion IX",
    41: "Gestion Pyme",
    21: "Gestion V",
    23: "Gestión VI",
    24: "Gestion VII",
    25: "Gestion VIII",
    34: "Gestion X",
    40: "Gestion XI",
    8: "Internacional",
    3: "Latinoamerica",
    7: "Moneda",
    12: "Multimercado I",
    35: "MULTIMERCADO II",
    27: "Patrimonio I",
    20: "Performance",
    5: "Pesos",
    36: "PLUS",
    11: "Pyme",
    38: "PYMES",
    6: "Recursos",
    4: "Renta",
    22: "Renta Dolares",
    26: "DOLARES PLUS",
    10: "Select",
    42: "Gestion XIII",
}


# ──────────────────────────────────────────────────────────────────────
# Resolución de paths
# ──────────────────────────────────────────────────────────────────────

def _bases_dir() -> Optional[str]:
    """Carpeta raíz donde viven los Excel internos de Delta.

    Se configura exclusivamente vía secrets.txt:
        DELTA_BASES_DIR=~\\...\\Delta Bases\\Carteras

    Retorna None si no está configurada — en ese caso los loaders muestran
    un warning pidiendo configurar secrets.txt.
    """
    env = os.getenv(_BASES_DIR_ENV)
    if env:
        return os.path.expandvars(os.path.expanduser(env))
    return None


def _resolve_base_path(filename: str, env_override: Optional[str] = None) -> Optional[str]:
    """Resuelve ruta al Excel interno.

    Prioridad:
    1. Env var específica del archivo (ej. DELTA_COMPOSICION_PATH) → ruta completa.
    2. Env var DELTA_BASES_DIR + filename.

    Retorna None si no hay ninguna configurada o el archivo no existe.
    """
    # 1) Override específico (path completo al archivo)
    if env_override:
        env = os.getenv(env_override)
        if env:
            env = os.path.expandvars(os.path.expanduser(env))
            if os.path.isfile(env):
                return env

    # 2) Carpeta base + filename
    base = _bases_dir()
    if base:
        candidate = os.path.join(base, filename)
        if os.path.isfile(candidate):
            return candidate

    return None


# ──────────────────────────────────────────────────────────────────────
# Mapeo Cod Fondo → Nombre (desde Delta_Fondos.txt)
# ──────────────────────────────────────────────────────────────────────

_FONDOS_FILENAME = "Delta_Fondos.txt"

def _fondos_file_path() -> Optional[str]:
    """Resuelve ruta al .txt de mapeo de fondos. Prioridad:
      1. DELTA_FONDOS_PATH (ruta completa al archivo).
      2. DELTA_BASES_DIR/../Text/Esco/Delta_Fondos.txt (ubicación estándar Esco).
      3. DELTA_BASES_DIR/../Delta_Fondos.txt (raíz de Delta Bases).
      4. DELTA_BASES_DIR/Delta_Fondos.txt (por si está junto a los Excel).
    """
    env = os.getenv(_FONDOS_PATH_ENV)
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env

    base = _bases_dir()
    if base:
        parent = os.path.dirname(base.rstrip("\\/"))
        for candidate in (
            os.path.join(parent, "Text", "Esco", _FONDOS_FILENAME),
            os.path.join(parent, _FONDOS_FILENAME),
            os.path.join(base, _FONDOS_FILENAME),
        ):
            if os.path.isfile(candidate):
                return candidate
    return None


def _parse_fondos_txt(path: str) -> Dict[int, str]:
    """Parsea Delta_Fondos.txt → {CodFondo: Nombre}.

    Auto-detecta delimitador (tab, pipe, semicolon, coma) y header. Si la
    primera línea contiene texto tipo 'cod' y 'nombre/denomina/descrip',
    usa esos índices; si no, asume col0=código, col1=nombre. Ignora líneas
    vacías y comentarios ('#'). Lee con encoding tolerante (utf-8 → latin-1).
    """
    raw: Optional[str] = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        return {}

    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return {}

    # Detectar delimitador: el que más veces aparece consistentemente.
    candidates = ["\t", "|", ";", ","]
    delim = max(
        candidates,
        key=lambda d: sum(1 for ln in lines[:10] if d in ln),
    )
    if not any(delim in ln for ln in lines[:10]):
        # Sin delimitador claro → probar espacios múltiples.
        import re as _re
        rows = [_re.split(r"\s{2,}|\t+", ln.strip()) for ln in lines]
    else:
        rows = [[c.strip() for c in ln.split(delim)] for ln in lines]

    if not rows or len(rows[0]) < 2:
        return {}

    # Detectar header
    header = [c.strip().lower() for c in rows[0]]
    is_header = any(
        any(tok in h for tok in ("cod", "id", "num")) for h in header
    ) and any(
        any(tok in h for tok in ("nombre", "denomi", "descri", "fondo")) for h in header
    )

    col_code = 0
    col_name = 1
    if is_header:
        for i, h in enumerate(header):
            if any(tok in h for tok in ("codfondo", "cod_fondo", "cod fondo", "id")) or h == "cod":
                col_code = i
                break
        # Para el nombre, preferí NombreCorto > Denominacion > Nombre > Descripcion.
        # NombreCorto matchea el estilo de display existente ("ACCIONES" vs "DELTA ACCIONES").
        name_priority = (
            ("nombrecorto", "nombre_corto", "nombre corto", "corto"),
            ("denomi",),
            ("nombre",),
            ("descri",),
        )
        col_name = -1
        for tokens in name_priority:
            for i, h in enumerate(header):
                if i == col_code:
                    continue
                if any(tok in h for tok in tokens):
                    col_name = i
                    break
            if col_name >= 0:
                break
        if col_name < 0:
            col_name = 1 if col_code != 1 else (2 if len(header) > 2 else 1)
        data_rows = rows[1:]
    else:
        data_rows = rows

    out: Dict[int, str] = {}
    for r in data_rows:
        if len(r) <= max(col_code, col_name):
            continue
        code_raw = r[col_code].strip().strip('"').strip("'")
        name_raw = r[col_name].strip().strip('"').strip("'")
        if not code_raw or not name_raw:
            continue
        try:
            code = int(float(code_raw))
        except (TypeError, ValueError):
            continue
        out[code] = name_raw
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _fondo_nombres() -> Dict[int, str]:
    """Mapeo CodFondo → Nombre. Lee Delta_Fondos.txt si está disponible;
    cae al fallback hardcodeado si no. Cacheado 1h."""
    path = _fondos_file_path()
    if path is None:
        return dict(_FONDO_NOMBRES_FALLBACK)
    parsed = _parse_fondos_txt(path)
    if not parsed:
        return dict(_FONDO_NOMBRES_FALLBACK)
    return parsed


# ──────────────────────────────────────────────────────────────────────
# Loaders cacheados
# ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="Cargando composición Delta…")
def load_delta_composicion() -> pd.DataFrame:
    """Composición de carteras por fondo. Limpieza:
    - Cod_Delta normalizado (str, strip, upper).
    - Numéricos coercionados.
    - Fechas de vencimiento a datetime.
    - Filas con CodFondo NaN descartadas.
    """
    path = _resolve_base_path(_COMPOSICION_FILE, "DELTA_COMPOSICION_PATH")
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"Error leyendo composición: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # Normalización
    df = df.dropna(subset=["CodFondo"]).copy()
    df["CodFondo"] = pd.to_numeric(df["CodFondo"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["CodFondo"])

    for col in ("Cantidad", "Valor"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Vencimiento" in df.columns:
        df["Vencimiento"] = pd.to_datetime(df["Vencimiento"], errors="coerce")

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    # Cod_Delta limpio (clave para merge con BONDS / snapshot de mercado)
    if "Cod_Delta" in df.columns:
        df["Cod_Delta"] = df["Cod_Delta"].astype(str).str.strip().str.upper()
        # "NC" (no corresponde) → NaN para no confundir con especie real
        df.loc[df["Cod_Delta"].isin(["NC", "NAN", "NONE", ""]), "Cod_Delta"] = np.nan

    return df.reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner="Cargando PN…")
def load_delta_pn() -> pd.DataFrame:
    """Patrimonio neto por fondo. Retorna DF con CodFondo (Int) + PN (float)."""
    path = _resolve_base_path(_PN_FILE, "DELTA_PN_PATH")
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"Error leyendo PN: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    df["CodFondo"] = pd.to_numeric(df["CodFondo"], errors="coerce").astype("Int64")
    df["PN"] = pd.to_numeric(df["PN"], errors="coerce")
    df = df.dropna(subset=["CodFondo", "PN"]).reset_index(drop=True)
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando futuros…")
def load_delta_futuros() -> pd.DataFrame:
    """Futuros ROFEX por fondo. Renombra columnas [NUM]xxx|yyy → yyy para usabilidad."""
    path = _resolve_base_path(_FUTUROS_FILE, "DELTA_FUTUROS_PATH")
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"Error leyendo futuros: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # Las columnas vienen con prefijos [NUM], [FECHA], [OCULTA] seguidos de
    # "Tecnica|Display". Nos quedamos con la parte display (después del '|').
    rename_map: Dict[str, str] = {}
    for c in df.columns:
        if "|" in str(c):
            rename_map[c] = str(c).split("|", 1)[1].strip()
    df = df.rename(columns=rename_map)

    df["CodFondo"] = pd.to_numeric(df["CodFondo"], errors="coerce").astype("Int64")

    for col in ("Cantidad", "Cierre", "Total", "% (1)", "Costo", "Duration"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Vencimiento" in df.columns:
        df["Vencimiento"] = pd.to_datetime(df["Vencimiento"], errors="coerce")
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    df = df.dropna(subset=["CodFondo"]).reset_index(drop=True)
    return df


# ──────────────────────────────────────────────────────────────────────
# Helpers de fondo / label
# ──────────────────────────────────────────────────────────────────────

def _fondo_label(cod: Any) -> str:
    """Arma label 'NN — Nombre'. Si no está mapeado, usa sólo el número."""
    try:
        n = int(cod)
    except (TypeError, ValueError):
        return str(cod)
    nombre = _fondo_nombres().get(n)
    return f"{n:>2} — {nombre}" if nombre else f"{n:>2}"


def _fondos_disponibles(df_comp: pd.DataFrame) -> List[int]:
    """Lista ordenada de CodFondo presentes en composición."""
    if df_comp is None or df_comp.empty:
        return []
    fondos = sorted({int(x) for x in df_comp["CodFondo"].dropna().unique()})
    return fondos


def _pn_for(cod: int, df_pn: pd.DataFrame) -> Optional[float]:
    if df_pn is None or df_pn.empty:
        return None
    row = df_pn[df_pn["CodFondo"] == cod]
    if row.empty:
        return None
    return float(row["PN"].iloc[0])


# ──────────────────────────────────────────────────────────────────────
# Enriquecimiento con métricas vivas (TIR / Duration / Precio)
# ──────────────────────────────────────────────────────────────────────

def _build_market_metrics_table(
    codes: List[str],
    snapshot_fn,
    parallel_metrics_fn,
    effective_price_fn,
    settle: Optional[str],
    bond_type_default: str = "lecap",
    bonds_universe: Optional[set] = None,
) -> pd.DataFrame:
    """Toma una lista de Cod_Delta únicos, consulta el snapshot global y devuelve
    DataFrame con columnas: Código | Precio | TIR | Duration.

    Ignora silenciosamente los códigos que no estén en BONDS o no tengan curva
    — quedan como NaN en el merge posterior.

    Parámetros son funciones inyectadas desde OMSweb_app para evitar import
    circular (OMSposiciones no importa OMSweb_app).
    """
    empty = pd.DataFrame(columns=["Código", "Precio", "TIR", "Duration"])

    if not codes:
        return empty

    try:
        snap = snapshot_fn()
    except Exception:
        return empty

    if snap is None or snap.empty:
        return empty

    # Filtrar snapshot a los códigos relevantes
    snap = snap[snap["Código"].astype(str).isin(set(codes))].copy()
    if snap.empty:
        return empty

    # Filtrar a universo BONDS si se pasó (evita llamar calcula_tirea sobre
    # códigos sin curva cargada)
    if bonds_universe is not None:
        snap = snap[snap["Código"].astype(str).isin(bonds_universe)].copy()
        if snap.empty:
            return empty

    # Precio efectivo: Last si hay, si no Close
    snap = snap.rename(columns={"close": "Close", "last": "Last"})
    try:
        price_eff = effective_price_fn(snap, last_col="Last", close_col="Close")
    except Exception:
        return empty

    codes_arr = snap["Código"].astype(str).to_numpy()
    price_arr = price_eff.to_numpy(dtype="float64")

    try:
        mdf = parallel_metrics_fn(codes_arr, price_arr, bond_type_default, settle)
    except Exception:
        return empty

    out = pd.DataFrame({
        "Código": codes_arr,
        "Precio": price_arr,
        "TIR": pd.to_numeric(mdf.get("TIREA"), errors="coerce").values if "TIREA" in mdf else np.nan,
        "Duration": pd.to_numeric(mdf.get("Duration"), errors="coerce").values if "Duration" in mdf else np.nan,
    })
    return out


_ESPECIES_EXTRA_COLS: List[str] = [
    "Ajuste", "Tasa", "Sector Delta", "Califica_Local", "Calificadora",
    "Emisor / Sponsor", "Clasificacion_especifico",
]


def _categoria_bono(ajuste: Any, tasa: Any) -> str:
    """Categoría combinada para la breakdown de Posiciones.

    Reglas (en orden):
      - Duales ya vienen en Ajuste como 'Dual (Fija/TAMAR)', 'Dual (CER/TAMAR)',
        'Dual (USD-Linked/CER)' → se preservan tal cual.
      - CER / UVA: ajuste de inflación.
      - USD / USD-Linked / USB: divisa.
      - ARS: se abre por Tasa → 'ARS Fija', 'ARS TAMAR', 'ARS BADLAR',
        'ARS Step Up', etc.
      - Vacío / NC → '(sin clasif.)'.
    """
    aj = str(ajuste).strip() if ajuste is not None and not (isinstance(ajuste, float) and pd.isna(ajuste)) else ""
    ta = str(tasa).strip() if tasa is not None and not (isinstance(tasa, float) and pd.isna(tasa)) else ""

    # Duales: el Ajuste ya describe la combinación; se preserva el string original.
    if aj.lower().startswith("dual"):
        return aj

    if aj == "CER":
        return "CER"
    if aj == "UVA":
        return "UVA"
    if aj in ("USD-Linked", "USD Linked", "DLK"):
        return "USD-Linked"
    if aj == "USD":
        return "USD"
    if aj == "USB":
        return "USB"

    # ARS: abrir por Tasa
    if aj == "ARS" or aj.lower() == "en pesos":
        if ta == "Fija":
            return "ARS Fija"
        if ta == "TAMAR":
            return "ARS TAMAR"
        if ta.upper() == "BADLAR":
            return "ARS BADLAR"
        if ta == "Step Up":
            return "ARS Step Up"
        if not ta or ta.upper() == "NC":
            return "ARS (s/tasa)"
        return f"ARS {ta}"

    if not aj or aj.upper() == "NC":
        return "(sin clasif.)"
    return aj


def _enrich_posiciones(
    df_fondo: pd.DataFrame,
    metrics: pd.DataFrame,
    pn: Optional[float],
) -> pd.DataFrame:
    """Merge de posiciones del fondo con métricas vivas + cálculo de % sobre PN."""
    if df_fondo is None or df_fondo.empty:
        return pd.DataFrame()

    df = df_fondo.copy()

    # Merge por Cod_Delta ↔ Código
    if metrics is not None and not metrics.empty:
        df = df.merge(
            metrics.rename(columns={"Código": "Cod_Delta"}),
            on="Cod_Delta", how="left",
        )
    else:
        df["Precio"] = np.nan
        df["TIR"] = np.nan
        df["Duration"] = np.nan

    # Enriquecimiento con base Delta - Especies (silent fail si no está)
    esp = delta_especies.load_delta_especies()
    if esp is not None and not esp.empty:
        cols_keep = ["BYMA"] + [c for c in _ESPECIES_EXTRA_COLS if c in esp.columns]
        esp_slim = esp[cols_keep].drop_duplicates("BYMA")
        df = df.merge(
            esp_slim.rename(columns={"BYMA": "Cod_Delta"}),
            on="Cod_Delta", how="left",
            suffixes=("", "_esp"),
        )

    # Categoría combinada (Ajuste × Tasa) — sólo si tenemos ambas columnas
    if "Ajuste" in df.columns and "Tasa" in df.columns:
        df["Categoría"] = [
            _categoria_bono(a, t) for a, t in zip(df["Ajuste"], df["Tasa"])
        ]

    # % sobre PN
    if pn and pn > 0:
        df["% PN"] = df["Valor"] / pn
    else:
        df["% PN"] = np.nan

    return df


def _composicion_por_categoria(
    df_enriched: pd.DataFrame,
    pn: Optional[float],
) -> Dict[str, pd.DataFrame]:
    """Devuelve dict {nombre_categoría → DataFrame [Categoría, Valor, % PN]}.

    Sólo categorías con al menos una asignación. Categorías mostradas:
      - 'Clase de Activo' (viene de Composición)
      - 'Ajuste' y 'Tasa' (vienen de Especies)
    """
    if df_enriched is None or df_enriched.empty:
        return {}

    out: Dict[str, pd.DataFrame] = {}
    total = float(pd.to_numeric(df_enriched["Valor"], errors="coerce").sum())
    denom = float(pn) if pn and pn > 0 else (total if total > 0 else 1.0)

    for col, label in (
        ("Clase de Activo", "Clase de Activo"),
        ("Categoría", "Categoría (CER / UVA / ARS Fija / ARS TAMAR / Dual / …)"),
        ("Tasa", "Tasa (Fija / BADLAR / TAMAR / …)"),
    ):
        if col not in df_enriched.columns:
            continue
        sub = df_enriched[[col, "Valor"]].copy()
        sub[col] = sub[col].fillna("(sin clasif.)")
        sub["Valor"] = pd.to_numeric(sub["Valor"], errors="coerce")
        grp = sub.groupby(col, dropna=False)["Valor"].sum().reset_index()
        grp = grp.rename(columns={col: "Categoría", "Valor": "Monto"})
        grp["% sobre PN"] = grp["Monto"] / denom
        grp = grp.sort_values("Monto", ascending=False).reset_index(drop=True)
        out[label] = grp
    return out


# ──────────────────────────────────────────────────────────────────────
# Estilos (Bloomberg-adaptative)
# ──────────────────────────────────────────────────────────────────────

def _fmt_num_ar(x: Any, nd: int = 0) -> str:
    """Formato numérico estilo AR (separador de miles con punto)."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    try:
        return f"{float(x):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(x: Any, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    try:
        return f"{float(x) * 100:,.{nd}f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _style_posiciones(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Estilo Bloomberg para tabla de posiciones.

    Barras sobre % sobre PN, colores por TIR con deadband ~0.05%, Duration numérico limpio.
    """
    # Copia visible (df ya viene con las columnas ordenadas)
    sty = df.style

    # Barras para % sobre PN sólo en rango [0, max]
    if "% sobre PN" in df.columns:
        max_pn = df["% sobre PN"].abs().max() if not df["% sobre PN"].isna().all() else 0.01
        if max_pn and max_pn > 0:
            sty = sty.bar(subset=["% sobre PN"], color="#2962ff", vmin=0, vmax=float(max_pn))

    # Formato
    fmt_map: Dict[str, Any] = {}
    for col, nd in (("VN", 0), ("Monto Invertido", 0), ("Precio", 4)):
        if col in df.columns:
            fmt_map[col] = lambda v, _nd=nd: _fmt_num_ar(v, _nd)
    for col in ("TIR", "% sobre PN", "TEM"):
        if col in df.columns:
            fmt_map[col] = lambda v: _fmt_pct(v, 2)
    if "Duration" in df.columns:
        fmt_map["Duration"] = lambda v: "—" if pd.isna(v) else f"{float(v):.2f}"

    if fmt_map:
        sty = sty.format(fmt_map, na_rep="—")

    return sty


# ──────────────────────────────────────────────────────────────────────
# Render 1: Tab Posiciones (un fondo)
# ──────────────────────────────────────────────────────────────────────

def render_tab_posiciones(
    *,
    snapshot_fn,
    parallel_metrics_fn,
    effective_price_fn,
    settle: Optional[str],
    bonds_universe: Optional[set] = None,
) -> None:
    """Render de la pestaña 'Posiciones'.

    Los 3 primeros parámetros son las funciones internas de OMSweb_app
    (inyectadas para evitar import circular).
    """
    df_comp = load_delta_composicion()
    df_pn = load_delta_pn()
    df_fut = load_delta_futuros()

    if df_comp.empty:
        base = _bases_dir()
        if base:
            # Config OK, pero archivo no encontrado en esa carpeta
            st.warning(
                f"No se pudo cargar `Delta_Composicion.xlsx`.\n\n"
                f"Carpeta buscada: `{base}`\n\n"
                "Verificá que el archivo exista ahí, o definí "
                "`DELTA_COMPOSICION_PATH` en `secrets.txt` con la ruta completa."
            )
        else:
            # No hay nada configurado
            st.warning(
                "⚠️ Paths no configurados.\n\n"
                "Agregá a `secrets.txt`:\n\n"
                "```\nDELTA_BASES_DIR=<ruta-a-carpeta-Carteras>\n```\n\n"
                "Podés usar `~` o `%USERPROFILE%` para independencia de usuario."
            )
        return

    fecha_comp = df_comp["Fecha"].max() if "Fecha" in df_comp.columns else None
    st.caption(
        f"Composición al **{fecha_comp.date() if fecha_comp is not None and pd.notna(fecha_comp) else '—'}**  |  "
        f"{df_comp['CodFondo'].nunique()} fondos  |  "
        f"{len(df_comp):,} posiciones"
    )

    # Selector de fondo
    fondos = _fondos_disponibles(df_comp)
    if not fondos:
        st.info("No hay fondos en la composición.")
        return

    col_sel, col_cls = st.columns([3, 2])
    with col_sel:
        fondo_sel = st.selectbox(
            "Fondo",
            options=fondos,
            format_func=_fondo_label,
            key="pos_fondo_sel",
        )
    with col_cls:
        clases_disp = sorted(df_comp["Clase de Activo"].dropna().unique().tolist())
        clases_sel = st.multiselect(
            "Clase de Activo",
            options=clases_disp,
            default=clases_disp,
            key="pos_clase_sel",
        )

    df_fondo = df_comp[df_comp["CodFondo"] == fondo_sel].copy()
    if clases_sel:
        df_fondo = df_fondo[df_fondo["Clase de Activo"].isin(clases_sel)]

    if df_fondo.empty:
        st.info("Sin posiciones con los filtros actuales.")
        return

    pn = _pn_for(fondo_sel, df_pn)
    valor_total = float(pd.to_numeric(df_fondo["Valor"], errors="coerce").sum())

    # Liquidez = suma Valor donde Clase de Activo == Liquidez
    valor_liq = float(pd.to_numeric(
        df_fondo.loc[df_fondo["Clase de Activo"] == "Liquidez", "Valor"],
        errors="coerce",
    ).sum())

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("PN", _fmt_num_ar(pn, 0) if pn else "—")
    k2.metric("Σ Valor invertido", _fmt_num_ar(valor_total, 0))
    k3.metric(
        "% Liquidez / PN",
        _fmt_pct(valor_liq / pn, 2) if pn and pn > 0 else "—",
    )
    k4.metric("# Posiciones", str(len(df_fondo)))

    # Métricas vivas — sólo para Cod_Delta reales (no NaN, y que estén en BONDS)
    codes_unicos = (
        df_fondo["Cod_Delta"].dropna().astype(str).str.strip().unique().tolist()
    )
    metrics = _build_market_metrics_table(
        codes=codes_unicos,
        snapshot_fn=snapshot_fn,
        parallel_metrics_fn=parallel_metrics_fn,
        effective_price_fn=effective_price_fn,
        settle=settle,
        bonds_universe=bonds_universe,
    )

    df_enriched = _enrich_posiciones(df_fondo, metrics, pn)

    # KPIs regulatorios por fondo (Clasificacion_especifico)
    if "Clasificacion_especifico" in df_enriched.columns and pn and pn > 0:
        clas = df_enriched[["Clasificacion_especifico", "Valor"]].copy()
        clas["Valor"] = pd.to_numeric(clas["Valor"], errors="coerce")

        if fondo_sel == 18:
            _infra_multi = float(clas.loc[
                clas["Clasificacion_especifico"] == "Infraestructura Multidestino", "Valor"
            ].sum())
            _infra_dest = float(clas.loc[
                clas["Clasificacion_especifico"] == "Infraestructura Destino Específico", "Valor"
            ].sum())
            ki1, ki2 = st.columns(2)
            ki1.metric("% Infra Multidestino / PN", _fmt_pct(_infra_multi / pn, 2))
            ki2.metric("% Infra Destino Específico / PN", _fmt_pct(_infra_dest / pn, 2))

        elif fondo_sel == 11:
            _pyme_cats = ("Pymes", "Pyme Multidestino", "Pyme Destino Específico",
                          "Pymes e Infraestructura")
            _pyme_val = float(clas.loc[
                clas["Clasificacion_especifico"].isin(_pyme_cats), "Valor"
            ].sum())
            st.metric("% Activos PyME / PN", _fmt_pct(_pyme_val / pn, 2))

    # Federal I (14): breakdown Soberano / Corporativo / Subsoberano
    if fondo_sel == 14 and "Sector Delta" in df_enriched.columns and pn and pn > 0:
        _sec = df_enriched[["Sector Delta", "Valor"]].copy()
        _sec["Valor"] = pd.to_numeric(_sec["Valor"], errors="coerce")
        _sec_grp = (
            _sec.groupby("Sector Delta", dropna=False)["Valor"].sum()
            .sort_values(ascending=False)
        )
        _sec_cols = st.columns(len(_sec_grp))
        for _col, (sector, monto) in zip(_sec_cols, _sec_grp.items()):
            _label = str(sector) if pd.notna(sector) and str(sector).strip() else "(sin sector)"
            _col.metric(f"% {_label} / PN", _fmt_pct(monto / pn, 2))

    # Todos los fondos: rating crediticio con Soberano aparte
    if "Califica_Local" in df_enriched.columns and "Sector Delta" in df_enriched.columns and pn and pn > 0:
        _rat = df_enriched[["Sector Delta", "Califica_Local", "Valor"]].copy()
        _rat["Valor"] = pd.to_numeric(_rat["Valor"], errors="coerce")
        _is_sov = _rat["Sector Delta"].astype(str).str.strip().str.lower() == "soberano"
        _val_sov = float(_rat.loc[_is_sov, "Valor"].sum())
        _rat_no_sov = (
            _rat.loc[~_is_sov]
            .groupby("Califica_Local", dropna=False)["Valor"].sum()
            .sort_values(ascending=False)
        )
        parts = [f"Soberano {_fmt_pct(_val_sov / pn, 2)}"]
        for rating, monto in _rat_no_sov.items():
            _rlabel = str(rating).strip() if pd.notna(rating) and str(rating).strip() else "s/rating"
            parts.append(f"{_rlabel} {_fmt_pct(monto / pn, 2)}")
        st.caption("**Rating:** " + " · ".join(parts))

    # Columnas de salida — orden explícito solicitado por Rorru:
    # [métricas de mercado y clasificación] … luego [VN | Monto Invertido | % sobre PN]
    rename_out = {
        "Instrumento": "Instrumento",
        "Cod_Delta": "Especie",
        "Inversion": "Denominación",
        "Precio": "Precio",
        "TIR": "TIR",
        "Duration": "Duration",
        "Vencimiento": "Vto.",
        "Ajuste": "Ajuste",
        "Tasa": "Tasa",
        "Sector Delta": "Sector",
        "Califica_Local": "Rating",
        "Cantidad": "VN",
        "Valor": "Monto Invertido",
        "% PN": "% sobre PN",
    }
    cols_out = [c for c in rename_out if c in df_enriched.columns]
    tbl = df_enriched[cols_out].rename(columns=rename_out)

    # Orden: primero por % sobre PN desc, luego por Monto Invertido desc
    if "% sobre PN" in tbl.columns:
        tbl = tbl.sort_values("% sobre PN", ascending=False, na_position="last")
    elif "Monto Invertido" in tbl.columns:
        tbl = tbl.sort_values("Monto Invertido", ascending=False, na_position="last")

    st.markdown(f"#### Tenencias — {_fondo_label(fondo_sel)}")
    st.dataframe(
        _style_posiciones(tbl),
        width="stretch",
        height=min(650, 50 + 32 * len(tbl)),
    )

    # ── Composición por categoría (Clase / Ajuste / Tasa) ──
    breakdown = _composicion_por_categoria(df_enriched, pn)
    if breakdown:
        with st.expander("📊 Composición por categoría", expanded=False):
            cols_b = st.columns(len(breakdown))
            for col_w, (label, df_b) in zip(cols_b, breakdown.items()):
                with col_w:
                    st.caption(f"**{label}**")
                    sty_b = df_b.style.format({
                        "Monto": lambda v: _fmt_num_ar(v, 0),
                        "% sobre PN": lambda v: _fmt_pct(v, 2),
                    }, na_rep="—")
                    max_pct = df_b["% sobre PN"].abs().max() if not df_b.empty else 0.0
                    if max_pct and max_pct > 0:
                        sty_b = sty_b.bar(
                            subset=["% sobre PN"], color="#2962ff",
                            vmin=0, vmax=float(max_pct),
                        )
                    st.dataframe(sty_b, width="stretch", hide_index=True)

    # Export CSV
    csv = tbl.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar posiciones (CSV)",
        data=csv,
        file_name=f"posiciones_fondo_{fondo_sel}.csv",
        mime="text/csv",
        key=f"dl_pos_{fondo_sel}",
    )

    # Futuros del fondo
    if not df_fut.empty and (df_fut["CodFondo"] == fondo_sel).any():
        with st.expander("🎯 Futuros ROFEX del fondo", expanded=False):
            df_fut_f = df_fut[df_fut["CodFondo"] == fondo_sel].copy()
            cols_fut = [c for c in (
                "TpEspecie", "Denominacion", "Cantidad", "Cierre",
                "Total", "% (1)", "Duration", "Vencimiento",
            ) if c in df_fut_f.columns]
            df_fut_f = df_fut_f[cols_fut].rename(columns={"% (1)": "% PN", "TpEspecie": "Tipo"})

            sty = df_fut_f.style.format({
                "Cantidad": lambda v: _fmt_num_ar(v, 0),
                "Cierre": lambda v: _fmt_num_ar(v, 2),
                "Total": lambda v: _fmt_num_ar(v, 0),
                "% PN": lambda v: f"{v:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(v) else "—",
                "Duration": lambda v: f"{v:.0f}" if pd.notna(v) else "—",
            }, na_rep="—")
            if "% PN" in df_fut_f.columns:
                max_abs = df_fut_f["% PN"].abs().max() or 1.0
                sty = sty.bar(
                    subset=["% PN"],
                    color=["#ef5350", "#26a69a"],
                    align="zero",
                    vmin=-float(max_abs), vmax=float(max_abs),
                )
            st.dataframe(sty, width="stretch", height=min(400, 50 + 35 * len(df_fut_f)))


# ──────────────────────────────────────────────────────────────────────
# Render 2: Buscador + Matriz de Tenencias
# ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _especies_disponibles(df_comp: pd.DataFrame) -> List[str]:
    """Lista ordenada única de Cod_Delta. Cacheada: se recalcula sólo si
    la composición cambia (el ttl matchea el de load_delta_composicion)."""
    if df_comp is None or df_comp.empty:
        return []
    return sorted(
        df_comp["Cod_Delta"].dropna().astype(str).str.strip().unique().tolist()
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _agregado_por_especie(
    df_comp: pd.DataFrame,
    df_pn: pd.DataFrame,
    especie: str,
    only_nonzero: bool,
) -> pd.DataFrame:
    """Agrega tenencias de una especie por fondo + % PN. Cacheada por (especie, toggle)."""
    df_e = df_comp[df_comp["Cod_Delta"] == especie]
    if only_nonzero:
        df_e = df_e[df_e["Cantidad"].fillna(0) != 0]
    if df_e.empty:
        return pd.DataFrame()

    agg = (
        df_e.groupby("CodFondo", dropna=True)
        .agg(VN=("Cantidad", "sum"), Valor=("Valor", "sum"))
        .reset_index()
    )
    agg = agg.merge(df_pn, on="CodFondo", how="left")
    agg["% PN"] = np.where(
        agg["PN"].fillna(0) > 0, agg["Valor"] / agg["PN"], np.nan
    )
    agg["Fondo"] = agg["CodFondo"].map(_fondo_label)

    # Info de vto / denom — se guardan en attrs como strings serializables
    # (Streamlit serializa attrs a JSON y Timestamp no es JSON-nativo).
    vto = df_e["Vencimiento"].dropna().iloc[0] if "Vencimiento" in df_e and df_e["Vencimiento"].notna().any() else None
    denom = df_e["Inversion"].dropna().iloc[0] if "Inversion" in df_e and df_e["Inversion"].notna().any() else ""
    agg.attrs["vto"] = vto.date().isoformat() if vto is not None and pd.notna(vto) else ""
    agg.attrs["denom"] = str(denom) if denom else ""
    return agg


@st.cache_data(ttl=3600, show_spinner=False)
def _matriz_especies_fondos(
    df_comp: pd.DataFrame,
    df_pn: pd.DataFrame,
    clase_sel_tuple: Tuple[str, ...],
    unidad: str,
    top_n: int,
) -> pd.DataFrame:
    """Genera la matriz pivot especies × fondos cacheada.
    clase_sel se pasa como tuple para ser hasheable."""
    df_m = df_comp[df_comp["Cod_Delta"].notna()]
    if clase_sel_tuple:
        df_m = df_m[df_m["Clase de Activo"].isin(clase_sel_tuple)]
    if df_m.empty:
        return pd.DataFrame()

    agg = (
        df_m.groupby(["Cod_Delta", "CodFondo"], dropna=True)
        .agg(VN=("Cantidad", "sum"), Valor=("Valor", "sum"))
        .reset_index()
    )

    if unidad == "% sobre PN":
        agg = agg.merge(df_pn, on="CodFondo", how="left")
        agg["cell"] = np.where(
            agg["PN"].fillna(0) > 0, agg["Valor"] / agg["PN"], np.nan
        )
    elif unidad == "VN":
        agg["cell"] = agg["VN"]
    else:  # "Monto Invertido"
        agg["cell"] = agg["Valor"]

    presencias = (
        agg[agg["cell"].fillna(0) != 0]
        .groupby("Cod_Delta")
        .size()
        .sort_values(ascending=False)
    )
    especies_top = presencias.head(top_n).index.tolist()
    if not especies_top:
        return pd.DataFrame()

    agg_top = agg[agg["Cod_Delta"].isin(especies_top)]

    matriz = agg_top.pivot_table(
        index="Cod_Delta",
        columns="CodFondo",
        values="cell",
        aggfunc="sum",
    ).fillna(0.0)

    matriz = matriz.loc[especies_top]
    cols_ordenadas = sorted(matriz.columns.tolist())
    matriz = matriz[cols_ordenadas]
    matriz.columns = [_fondo_label(c) for c in matriz.columns]
    matriz.index.name = "Especie"
    return matriz


def tenencias_por_especie(cod_delta: str, only_nonzero: bool = True) -> Optional[pd.DataFrame]:
    """API pública: dado un Cod_Delta, retorna tenencias agregadas por fondo.

    Pensada para uso externo (YAS / Comparador) con costo bajo: los loaders
    están cacheados con TTL 3600 y `_agregado_por_especie` cachea por
    (especie, toggle). Si la base no está disponible, retorna None.

    Returns:
        DataFrame con columnas ['Fondo', 'VN', 'Valor', '% PN'] ordenado por
        |Valor| desc, o None si no hay base. attrs['vn_total'] y
        attrs['valor_total'] con los totales agregados, attrs['vto'] y
        attrs['denom'] con metadata del bono.
    """
    if not cod_delta:
        return None
    code = str(cod_delta).strip().upper()
    if not code:
        return None

    df_comp = load_delta_composicion()
    if df_comp is None or df_comp.empty:
        return None

    df_pn = load_delta_pn()
    agg = _agregado_por_especie(df_comp, df_pn, code, only_nonzero)
    if agg is None or agg.empty:
        return None

    out = agg.sort_values("Valor", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    out = out[["Fondo", "VN", "Valor", "% PN"]]
    out.attrs["vn_total"] = float(out["VN"].sum(skipna=True))
    out.attrs["valor_total"] = float(out["Valor"].sum(skipna=True))
    out.attrs["vto"] = agg.attrs.get("vto", "")
    out.attrs["denom"] = agg.attrs.get("denom", "")
    return out


def render_tab_matriz() -> None:
    """Pestaña 'Matriz Tenencias' con 2 subsecciones:
    1) Buscador: una especie → en qué fondos está.
    2) Matriz: especies (filas) × fondos (columnas).
    """
    df_comp = load_delta_composicion()
    df_pn = load_delta_pn()

    if df_comp.empty:
        st.warning("No se pudo cargar la composición. Ver pestaña 'Posiciones' para detalles.")
        return

    sub_buscador, sub_matriz = st.tabs(["🔎 Buscador por especie", "🗂️ Matriz Especies × Fondos"])

    # ── Sub: buscador ──
    with sub_buscador:
        especies_disp = _especies_disponibles(df_comp)

        col_1, col_2 = st.columns([2, 1])
        with col_1:
            especie = st.selectbox(
                "Especie",
                options=especies_disp,
                index=especies_disp.index("TX26") if "TX26" in especies_disp else 0,
                key="busc_especie_sel",
            )
        with col_2:
            only_nonzero = st.toggle("Sólo fondos con tenencia ≠ 0", value=True, key="busc_nonzero")

        agg = _agregado_por_especie(df_comp, df_pn, especie, only_nonzero)

        if agg.empty:
            st.info(f"No hay tenencias de **{especie}**.")
        else:
            vto = agg.attrs.get("vto", "")
            denom = agg.attrs.get("denom", "")

            total_vn = float(agg["VN"].sum())
            total_val = float(agg["Valor"].sum())

            k1, k2, k3, k4 = st.columns(4)
            k1.metric(f"🔹 {especie}", "")
            k2.metric("Σ VN (todos los fondos)", _fmt_num_ar(total_vn, 0))
            k3.metric("Σ Monto Invertido", _fmt_num_ar(total_val, 0))
            k4.metric("Vto.", vto if vto else "—")

            if denom:
                st.caption(f"**{denom}**")

            tbl = (
                agg.rename(columns={"Valor": "Monto Invertido", "% PN": "% sobre PN"})
                   [["Fondo", "VN", "Monto Invertido", "% sobre PN"]]
                   .sort_values("Monto Invertido", ascending=False)
            )

            sty = tbl.style.format({
                "VN": lambda v: _fmt_num_ar(v, 0),
                "Monto Invertido": lambda v: _fmt_num_ar(v, 0),
                "% sobre PN": lambda v: _fmt_pct(v, 2),
            }, na_rep="—")
            max_pn = tbl["% sobre PN"].abs().max()
            if max_pn and max_pn > 0 and np.isfinite(max_pn):
                sty = sty.bar(subset=["% sobre PN"], color="#2962ff", vmin=0, vmax=float(max_pn))
            st.dataframe(sty, width="stretch", height=min(550, 50 + 32 * len(tbl)))

    # ── Sub: matriz ──
    with sub_matriz:
        col_a, col_b, col_c = st.columns([2, 2, 2])
        with col_a:
            clases_disp = sorted(df_comp["Clase de Activo"].dropna().unique().tolist())
            clase_sel = st.multiselect(
                "Clase de Activo",
                options=clases_disp,
                default=["Renta Fija"] if "Renta Fija" in clases_disp else clases_disp,
                key="mat_clase",
            )
        with col_b:
            unidad = st.radio(
                "Unidad de celda",
                options=["VN", "% sobre PN", "Monto Invertido"],
                horizontal=True,
                key="mat_unidad",
            )
        with col_c:
            top_n = st.slider(
                "Top N especies (por presencia en fondos)",
                min_value=10, max_value=200, value=60, step=10,
                key="mat_topn",
            )

        # Cacheado por (clase_sel, unidad, top_n); df_comp y df_pn son inmutables
        # dentro del TTL, entonces cualquier cambio de widget que coincida con
        # una combinación previamente vista es instantáneo.
        matriz = _matriz_especies_fondos(
            df_comp, df_pn, tuple(sorted(clase_sel)), unidad, top_n
        )

        if matriz.empty:
            st.info("No hay especies con tenencia > 0 en el recorte actual.")
            return

        # Styling (NO cacheable — devuelve Styler que es un objeto mutable)
        if unidad == "% sobre PN":
            fmt_fn = lambda v: _fmt_pct(v, 2) if v else ""
            cmap = "Blues"
        elif unidad == "VN":
            fmt_fn = lambda v: _fmt_num_ar(v, 0) if v else ""
            cmap = "Greens"
        else:  # Monto Invertido
            fmt_fn = lambda v: _fmt_num_ar(v, 0) if v else ""
            cmap = "Oranges"

        sty = (
            matriz.style
            .format(fmt_fn, na_rep="")
            .background_gradient(cmap=cmap, vmin=0.0, axis=None)
        )

        st.caption(
            f"Matriz {len(matriz)} especies × {len(matriz.columns)} fondos  |  "
            f"Unidad: **{unidad}**  |  Clases: {', '.join(clase_sel) if clase_sel else 'todas'}"
        )
        st.dataframe(sty, width="stretch", height=min(700, 50 + 28 * len(matriz)))

        # Export Excel conservando formato numérico
        try:
            import io
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                matriz.to_excel(writer, sheet_name="Matriz")
            st.download_button(
                "📥 Descargar matriz (Excel)",
                data=buf.getvalue(),
                file_name=f"matriz_tenencias_{unidad.replace(' ', '_').replace('%','pct')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_matriz",
            )
        except Exception:
            pass