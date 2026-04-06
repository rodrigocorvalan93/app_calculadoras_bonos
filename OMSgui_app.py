"""
OMSgui_app.py – Streamlit
Ejecutá:
    streamlit run OMSgui_app.py
"""
import pathlib
import pandas as pd
import streamlit as st

import OMSapi, OMSmktdata, OMSprices
from especies import BONDS                       # dict {ticker: Bond}

# ───────────── sidebar – credenciales ─────────────
st.sidebar.header("Credenciales")
user   = st.sidebar.text_input("Usuario", "delta_api")
passwd = st.sidebar.text_input("Contraseña", "D3lt41210*-*", type="password")

plazo  = st.sidebar.selectbox("Plazo", ["24hs", "CI"], index=0)
run_btn = st.sidebar.button("Conectar y refrescar")

# ───────────── helpers de estilo ─────────────
def style_row(row):
    col = "green" if row["Variación"] > 0 else "red" if row["Variación"] < 0 else "black"
    return pd.Series(
        {"Last Price": f"color:{col}; font-weight:bold;",
         "Variación":  f"color:{col};"}
    )

def style_table(df: pd.DataFrame):
    lim = df["Variación"].abs().max()
    fmt = {
        "Close Price": "{:,.4f}",
        "Last Price":  "{:,.4f}",
        "Variación":   "{:+.2%}",
        "TIREA":       "{:.2%}",
        "TNA":         "{:.2%}",
        "TEM":         "{:.2%}",
        "Paridad":     "{:.4f}",
        "Duration":    "{:.4f}",
        "tem_spread":  "{:+.2%}",
    }
    return (df.style.format(fmt)
                   .apply(style_row, axis=1)
                   .bar(subset=["Variación"], align="mid",
                        color=["#fa7a7a", "#8bf58b"], vmin=-lim, vmax=lim))

def tabla_curva(base: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    sub = base[base["Código"].isin(tickers)].copy()
    sub["tem_spread"] = sub["TEM"].diff().fillna(0)
    front = ["Código", "Close Price", "Last Price", "Variación"]
    return (sub[front + [c for c in sub.columns if c not in front]]
            .sort_values("Duration").reset_index(drop=True))

# ───────────── curvas definidas ─────────────
CURVAS = {
    "tasafijaARS": [
        "S10L5","S31L5","S15G5","S29G5","S12S5","S30S5","T17O5",
        "S31O5","S10N5","S28N5","T15D5","T30E6","T13F6","TTM26",
        "S29Y6","TTJ26","T30J6","TTS26","TO26","TTD26","T15E7","TY30P"],
    "CER": [
        "TZXO5","TX25","TZXD5","TX26","TZXM6","TZX26","TZXO6","TZXD6",
        "TZXM7","TZX27","TZXD7","TZX28","TX28","DICP","PARP","CUAP"],
    "DLK": ["D31O5","TZVD5","D16E6","TZV26"],
}

# checkboxes de selección
sel = {k: st.sidebar.checkbox(k, value=True) for k in CURVAS}

# ───────────── ejecución principal ─────────────
if run_btn:
    try:
        session = OMSapi.login(user, passwd)
        st.success("Conectado ✅")

        # descarga una sola vez
        symbols = [f"MERV - XMEV - {c} - {plazo}" for c in BONDS]
        raw_md  = OMSmktdata.bulk_market_data(session, symbols)
        px      = OMSprices.last_price(raw_md).rename(columns={
                      "last":  "Last Price",
                      "close": "Close Price",
                      "variation": "Variación"})
        px["Código"] = px.index.map(lambda s: s.split(" - ")[2])
        px = px.loc[px["Código"].isin(BONDS)]

        metrics = (pd.DataFrame(
                    {c: BONDS[c].metrics(p)
                     for c, p in zip(px["Código"], px["Last Price"])})
                   .T.reset_index(drop=False).rename(columns={"index": "Código"}))

        base = px.reset_index(drop=True).merge(metrics, on="Código", how="left")

        # render por curva seleccionada
        out_dir = pathlib.Path("curvas_streamlit")
        out_dir.mkdir(exist_ok=True)

        for nombre, tickers in CURVAS.items():
            if not sel[nombre]:
                continue
            df = tabla_curva(base, tickers)
            st.markdown(f"### Curva {nombre} ({plazo})")
            st.dataframe(style_table(df), use_container_width=True)
            df.to_excel(out_dir / f"curva_{nombre}_{plazo}.xlsx", index=False)

        st.success("Curvas actualizadas y archivos .xlsx guardados")

    except Exception as e:
        st.error(f"Error: {e}")
