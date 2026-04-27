# gui_app.py  ------------------------------------------------------------
"""
GUI ligera para BYMA/XOMS con Streamlit (archivos en la misma carpeta)

Ejecutar:

    streamlit run gui_app.py
"""

from __future__ import annotations

import os
from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# --- módulos propios (sin carpeta src) --------------------------------- #
from api import iniciar_sesion, mercado_masivo
from bonosmetricas import catalogo_desde_especies
import especies  # noqa: E402  (tu viejo módulo de bonos)
# from transformaciones import aplanar_df   # si lo necesitas más adelante

# -------------------------------------------------------------------- #
# Configuración inicial
# -------------------------------------------------------------------- #
st.set_page_config(page_title="BYMA API – Dashboard", layout="wide")
load_dotenv()

# Estado de sesión
if "ses" not in st.session_state:
    st.session_state.ses = None
if "catalogo" not in st.session_state:
    st.session_state.catalogo = catalogo_desde_especies(especies)
if "df_lecap" not in st.session_state:
    st.session_state.df_lecap = pd.DataFrame()
if "df_cer" not in st.session_state:
    st.session_state.df_cer = pd.DataFrame()
if "ult_fetch" not in st.session_state:
    st.session_state.ult_fetch = None

# -------------------------------------------------------------------- #
# Sidebar – Login
# -------------------------------------------------------------------- #
st.sidebar.header("Credenciales XOMS")
usuario = st.sidebar.text_input("Usuario", value=os.getenv("XOMS_USER", ""))
contraseña = st.sidebar.text_input(
    "Contraseña", type="password", value=os.getenv("XOMS_PWD", "")
)

if st.sidebar.button("Iniciar sesión"):
    try:
        st.session_state.ses = iniciar_sesion(usuario, contraseña)
        st.success("Sesión iniciada correctamente")
    except Exception as e:
        st.error(f"Error al iniciar sesión: {e}")

sesión_activa = st.session_state.ses is not None

# -------------------------------------------------------------------- #
# Funciones auxiliares
# -------------------------------------------------------------------- #
CURVA_LECAP = [
    "S31L5", "S15G5", "S29G5", "S12S5", "S30S5",
    "T17O5", "S31O5", "S10N5", "S28N5", "T15D5", "T30E6",
    "T13F6", "TTM26", "S29Y6", "TTJ26", "T30J6", "TTS26",
    "TO26", "TTD26", "T15E7", "TY30P",
]

CURVA_CER = [
    "TZXO5", "TX25", "TZXD5", "TX26", "TZXM6", "TZX26",
    "TZXO6", "TZXD6", "TZXM7", "TZX27", "TZXD7", "TZX28",
    "TX28", "DICP", "PARP", "CUAP",
]


def _simbolos(códigos, plazo="24hs"):
    pre, suf = "MERV - XMEV - ", f" - {plazo}"
    return [f"{pre}{c}{suf}" for c in códigos]


def _descargar_curvas():
    """Descarga market-data y calcula métricas mínimas para Lecap y CER."""
    cat = st.session_state.catalogo
    ses = st.session_state.ses

    sims_lecap = _simbolos(CURVA_LECAP)
    sims_cer = _simbolos(CURVA_CER)

    df_lecap_raw = mercado_masivo(ses, sims_lecap)
    df_cer_raw = mercado_masivo(ses, sims_cer)

    def _extraer(df_raw: pd.DataFrame) -> pd.DataFrame:
        last = df_raw["LA"].apply(
            lambda d: d.get("price") if isinstance(d, dict) else np.nan
        )
        df = pd.DataFrame({"symbol": df_raw.index, "Último": last}).dropna()
        df["Código"] = (
            df["symbol"].str.replace("MERV - XMEV - ", "", regex=False).str[:6]
        )
        return df

    df_lecap = _extraer(df_lecap_raw)
    df_cer = _extraer(df_cer_raw)

    def _ticket(row):
        bono = cat.get(row["Código"])
        return bono.metricas(row["Último"] / 100) if bono else {}

    df_lecap = pd.concat(
        [df_lecap, df_lecap.apply(_ticket, axis=1, result_type="expand")], axis=1
    )
    df_cer = pd.concat(
        [df_cer, df_cer.apply(_ticket, axis=1, result_type="expand")], axis=1
    )

    st.session_state.df_lecap = df_lecap
    st.session_state.df_cer = df_cer
    st.session_state.ult_fetch = date.today()


def _df_to_csv(df: pd.DataFrame) -> BytesIO:
    return BytesIO(df.to_csv(index=False).encode())


# -------------------------------------------------------------------- #
# Zona principal
# -------------------------------------------------------------------- #
st.title("Dashboard BYMA – Renta Fija")

if not sesión_activa:
    st.info("Inicia sesión para continuar.")
    st.stop()

# Botón de refresh
if st.button("🔄 Refrescar mercado (Curvas Lecap / CER)"):
    with st.spinner("Descargando precios…"):
        _descargar_curvas()
    st.success("Datos descargados")

# Tabs
tab_lecap, tab_cer = st.tabs(["Curva Lecap 24 hs", "Curva CER 24 hs"])

with tab_lecap:
    if not st.session_state.df_lecap.empty:
        st.dataframe(st.session_state.df_lecap, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar CSV",
            data=_df_to_csv(st.session_state.df_lecap),
            file_name="lecap_24hs.csv",
            mime="text/csv",
        )
    else:
        st.warning("Aún no hay datos")

with tab_cer:
    if not st.session_state.df_cer.empty:
        st.dataframe(st.session_state.df_cer, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar CSV",
            data=_df_to_csv(st.session_state.df_cer),
            file_name="cer_24hs.csv",
            mime="text/csv",
        )
    else:
        st.warning("Aún no hay datos")

# -------------------------------------------------------------------- #
# Consulta de bono individual
# -------------------------------------------------------------------- #
st.header("Consulta de bono")

todos = sorted(st.session_state.catalogo.keys())
código_sel = st.selectbox("Elegí un bono", todos)
bono_obj = st.session_state.catalogo[código_sel].objeto

col1, col2 = st.columns([1, 2])

with col1:
    precio_sucio = st.number_input(
        "Precio sucio (paridad = 1)",
        min_value=0.0,
        step=0.01,
        format="%.4f",
        value=getattr(bono_obj, "precio", 1.0),
    )
    if st.button("Generar ticket"):
        ticket = bono_obj.genera_ticket(precio_sucio)
        st.json(ticket)

with col2:
    if st.button("Mostrar cash-flow completo"):
        cf = bono_obj.cashflow_pmt_full()
        st.dataframe(cf, use_container_width=True)
        st.download_button(
            "Descargar cash-flow CSV",
            data=_df_to_csv(cf),
            file_name=f"{código_sel}_cashflow.csv",
            mime="text/csv",
        )
