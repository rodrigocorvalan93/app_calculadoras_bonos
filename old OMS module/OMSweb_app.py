# OMSweb_app.py
# Web UI para curvas y análisis de bonos (usa OMScli + OMSapi + especies)
# Ejecutar con: python -m streamlit run OMSweb_app.py
# =============================================================
import streamlit as st
import pandas as pd
import numpy as np
import io
from contextlib import redirect_stdout, suppress
from datetime import datetime
from functools import lru_cache

from especies import BONDS
from OMScli import CURVAS, FUTUROS_DLR, get_a3500_spot, parsear_vencimiento
import OMSapi, OMSmktdata, OMSprices


# ---------- Constantes derivadas de BONDS (para performance) ----------

ALL_TICKERS = tuple(BONDS.keys())
ALL_TICKERS_SORTED = sorted(ALL_TICKERS)


# ---------- Helpers de compatibilidad Arrow (cashflows, comparadores) ----------

def _make_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    seen = {}
    new_cols = []
    for c in df.columns:
        if c not in seen:
            seen[c] = 0
            new_cols.append(c)
        else:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
    df.columns = new_cols
    return df


def show_df_arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajusta tipos y nombres de columnas para que Streamlit/Arrow no explote.
    - Columnas object -> intenta numérico, si no puede, las pasa a string.
    - Columnas duplicadas -> las renombra con sufijos _1, _2, ...
    """
    if df is None:
        return pd.DataFrame()

    df = _make_unique_columns(df)

    # Solo tocar columnas de tipo object (más eficiente)
    obj_cols = df.select_dtypes(include=["object"]).columns
    for col in obj_cols:
        converted = pd.to_numeric(df[col], errors="ignore")
        if converted.dtype != "object":
            df[col] = converted
        else:
            df[col] = df[col].astype(str)

    return df


def _capture_output(func, *args, **kwargs) -> str:
    """
    Captura lo que imprime la función (stdout) y, si la función devuelve un
    DataFrame o un HTML, lo concatena.
    """
    buf = io.StringIO()
    res = None
    with redirect_stdout(buf):
        res = func(*args, **kwargs)
    txt = buf.getvalue()

    # Si devolvió un DataFrame, lo paso a HTML
    if isinstance(res, pd.DataFrame):
        txt += res.to_html(border=1)
    else:
        # Algunas implementaciones devuelven directamente HTML
        if isinstance(res, str) and "<table" in res:
            txt += res

    return txt or (str(res) if res is not None else "")


# ---------- Unwrap de bonos (BondWrapper -> bono real) ----------

def _unwrap_bono_real(bono):
    """
    Devuelve el objeto 'bono real' que tiene los métodos:
      genera_ticket, genera_ticket_tna,
      genera_cashflow_cpn, genera_cashflow_pmt,
      comparar_precio, comparar_tna, generate_cashflows

    Funciona tanto si BONDS[t] es el bono directo como si es un wrapper.
    """
    if bono is None:
        return None

    target_methods = {
        "genera_ticket",
        "genera_ticket_tna",
        "genera_cashflow_cpn",
        "genera_cashflow_pmt",
        "comparar_precio",
        "comparar_tna",
        "generate_cashflows",
    }

    # 1) Si el objeto ya tiene alguno de esos métodos, usamos eso.
    for m in target_methods:
        if hasattr(bono, m):
            return bono

    # 2) Buscar en atributos típicos de wrapper
    candidate_attr_names = [
        "bond", "bono", "_bond", "_bono",
        "underlying", "obj", "_obj", "base", "wrapped",
    ]
    for name in candidate_attr_names:
        with suppress(Exception):
            inner = getattr(bono, name)
            if inner is None:
                continue
            for m in target_methods:
                if hasattr(inner, m):
                    return inner

    # 3) Buscar en __dict__
    with suppress(Exception):
        for _name, val in getattr(bono, "__dict__", {}).items():
            for m in target_methods:
                if hasattr(val, m):
                    return val

    # 4) Buscar en dir(), por si el wrapper lo expone con nombre “raro”
    for name in dir(bono):
        if name.startswith("_"):
            continue
        with suppress(Exception):
            val = getattr(bono, name)
        for m in target_methods:
            if hasattr(val, m):
                return val

    # Si no encontramos nada, devolvemos el original (por si el wrapper
    # implementa los métodos vía __getattr__ dinámico).
    return bono


@lru_cache(maxsize=None)
def get_bono_real_from_ticker(ticker: str):
    bono = BONDS.get(ticker)
    if bono is None:
        return None
    return _unwrap_bono_real(bono)


# ---------- Carga de datos BYMA (curvas) ----------

@st.cache_data(show_spinner=False, ttl=25)
def load_curvas(plazo: str):
    """
    Descarga precios de todos los BONDS para el plazo dado (CI / 24hs)
    y calcula métricas usando .metrics() de cada bono.
    Devuelve:
      - tabla_base: DF con precios, variación, TIREA, TNA, TEM, Paridad, Duration.
      - timestamp de actualización (string).
    """
    session = OMSapi.login("delta_api", "D3lt41210*-*")

    tickers = ALL_TICKERS
    symbols = [f"MERV - XMEV - {c} - {plazo}" for c in tickers]

    raw_md = OMSmktdata.bulk_market_data(session, symbols)

    px = OMSprices.last_price(raw_md).rename(
        columns={"last": "Last Price", "close": "Close Price", "variation": "Variación"}
    )

    if px.empty:
        tabla_vacia = pd.DataFrame(
            columns=["Código", "Last Price", "Close Price", "Variación"]
        )
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S (sin datos / error conexión)")
        return tabla_vacia, ts

    # Agrego la columna Código a partir del símbolo BYMA
    idx = px.index.to_series()
    # símbolo típico: "MERV - XMEV - TX26 - 24hs"
    px["Código"] = idx.str.split(" - ", expand=True).iloc[:, 2]

    # Filtrar sólo los que están en BONDS
    px = px.loc[px["Código"].isin(tickers)].copy()

    # Métricas usando el wrapper de especies
    metrics_rows = []
    for code, precio in zip(px["Código"].values, px["Last Price"].values):
        bono = BONDS.get(code)
        if bono is None or pd.isna(precio):
            metrics_rows.append({"Código": code})
            continue
        try:
            m = bono.metrics(precio)  # usa el BondWrapper.metrics
            m["Código"] = code
            metrics_rows.append(m)
        except Exception:
            metrics_rows.append({"Código": code})

    metrics_df = pd.DataFrame(metrics_rows)
    tabla_base = px.reset_index(drop=True).merge(metrics_df, on="Código", how="left")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return tabla_base, ts


# ---------- Futuros ROFEX dólar A3500 ----------

@st.cache_data(show_spinner=False, ttl=25)
def load_futuros():
    """
    Descarga futuros DLR/* definidos en FUTUROS_DLR y calcula:
      - Close, Last, Variación
      - Días a vencimiento
      - Tasa directa, TNA, TEA vs A3500 spot
      - Canal (Mayorista / Minorista, usando sufijo A)
    """
    session = OMSapi.login("delta_api", "D3lt41210*-*")
    symbols = FUTUROS_DLR

    try:
        raw = OMSmktdata.bulk_market_data(session, symbols)
    except Exception as e:
        # Si hay un error de conexión, devolvemos DF vacío y lo indicamos en el timestamp
        ts = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S (error conexión OMS: %s)" % e
        )
        return pd.DataFrame(), get_a3500_spot(), ts

    px = OMSprices.last_price(raw).rename(
        columns={"last": "Last Price", "close": "Close Price", "variation": "Variación"}
    )

    if px.empty:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S (sin datos / error conexión)")
        return pd.DataFrame(), get_a3500_spot(), ts

    px["Código"] = px.index

    # Close desde SE si falta
    if "Close Price" not in px.columns:
        closes = []
        for sym in symbols:
            se = raw.get(sym, {}).get("SE", {})
            closes.append(se.get("price"))
        px["Close Price"] = closes

    # Variación vs Close si falta
    if "Variación" not in px.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            px["Variación"] = px["Last Price"] / px["Close Price"] - 1

    # Vencimientos usando parsear_vencimiento de OMScli
    now = pd.Timestamp.now()
    codigos = px["Código"].astype(str)
    uniques = codigos.unique()
    maturity_map = {c: parsear_vencimiento(c) for c in uniques}
    px["maturity"] = codigos.map(maturity_map)
    px["Dias Vto"] = (px["maturity"] - now).dt.days.astype("Int64")

    # Canal: Mayorista si termina en 'A' (contrato mayorista)
    def _canal(c: str) -> str:
        c = str(c)
        return "Mayorista" if c.endswith("A") else "Minorista"

    px["Canal"] = codigos.map(_canal)

    a3500_spot = get_a3500_spot()

    with np.errstate(divide="ignore", invalid="ignore"):
        tasa_dir = px["Last Price"] / float(a3500_spot) - 1
        dias = (px["maturity"] - now).dt.days
        dias_pos = dias.where(dias > 0)
        TNA = tasa_dir * (365 / dias_pos)
        TEA = (1 + tasa_dir) ** (365 / dias_pos) - 1

    out = px[["Código", "Close Price", "Last Price", "Variación", "Dias Vto", "maturity", "Canal"]].copy()
    out["Tasa Directa"] = tasa_dir.astype(float)
    out["TNA"] = TNA.astype(float)
    out["TEA"] = TEA.astype(float)
    out = out.sort_values(by="maturity").reset_index(drop=True)
    out = out.drop(columns=["maturity"])

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out, a3500_spot, ts


# ---------- Estilos (curvas y futuros) ----------

def style_curva(df: pd.DataFrame):
    if df.empty:
        return df

    df = df.copy()
    df["Variación"] = pd.to_numeric(df["Variación"], errors="coerce")

    # tem_spread incremental sobre TEM (decimal)
    if "TEM" in df.columns:
        tem_aux = pd.to_numeric(df["TEM"], errors="coerce")
        df["tem_spread"] = tem_aux.diff().fillna(0)

    # ---------- REORDENAR COLUMNAS ----------
    desired_order = [
        "Código",
        "Close Price",
        "Last Price",
        "Variación",
        "TIREA",
        "TNA",
        "TEM",
        "Paridad",
        "Duration",
        "tem_spread",
    ]

    current_cols = list(df.columns)
    ordered = [c for c in desired_order if c in current_cols]
    rest = [c for c in current_cols if c not in ordered]
    df = df[ordered + rest]
    # ---------------------------------------

    fmt = {
        "Close Price": "{:,.4f}",
        "Last Price": "{:,.4f}",
        "Variación": "{:+.2%}",
        "TIREA": "{:.2%}",
        "TNA": "{:.2%}",
        "TEM": "{:.2%}",
        "Paridad": "{:,.4f}",
        "Duration": "{:.4f}",
        "tem_spread": "{:+.2%}",
    }

    lim = df["Variación"].abs().max()
    vmin, vmax = (-lim, lim) if pd.notnull(lim) and lim > 0 else (-1.0, 1.0)

    def style_row(row):
        col = "green" if row["Variación"] > 0 else "red" if row["Variación"] < 0 else "black"
        return [f"color:{col};"] * len(row)

    sty = (
        df.style
        .format(fmt, na_rep="")
        .apply(style_row, axis=1)
        .bar(
            subset=["Variación"],
            align="mid",
            color=["#fa7a7a", "#8bf58b"],
            vmin=vmin,
            vmax=vmax,
        )
    )
    return sty


def style_futuros(df: pd.DataFrame):
    if df.empty:
        return df

    df = df.copy()
    df["Variación"] = pd.to_numeric(df["Variación"], errors="coerce")

    fmt = {
        "Close Price": "{:,.2f}",
        "Last Price": "{:,.2f}",
        "Variación": "{:+.2%}",
        "Tasa Directa": "{:+.2%}",
        "TNA": "{:.2%}",
        "TEA": "{:.2%}",
    }

    lim = df["Variación"].abs().max()
    vmin, vmax = (-lim, lim) if pd.notnull(lim) and lim > 0 else (-1.0, 1.0)

    def _hl_by_canal(row):
        if row.get("Canal") == "Mayorista":
            return ["background-color: #fff2cc"] * len(row)
        else:
            return [""] * len(row)

    sty = (
        df.style
        .format(fmt, na_rep="")
        .apply(_hl_by_canal, axis=1)
        .bar(subset=["Variación"], align="mid",
             color=["#fa7a7a", "#8bf58b"], vmin=vmin, vmax=vmax)
    )
    return sty


# ---------- Config de página (llamar una vez) ----------

st.set_page_config(
    page_title="OMS Curvas Bonos & Futuros",
    layout="wide",
)


# ---------- UI principal ----------

def main():
    st.title("Curvas, futuros y análisis de bonos")

    # Sidebar: parámetros comunes
    with st.sidebar:
        st.header("Parámetros")
        plazo = st.selectbox("Plazo BYMA", ["CI", "24hs"], index=1)
        st.caption("CI = contado inmediato, 24hs = T+1")
        st.markdown("---")
        st.caption("Para auto-refresh usá este botón o el refresh del navegador.")
        if st.button("🔄 Actualizar ahora"):
            st.rerun()

    # Carga datos de curvas (una vez por run, cacheado)
    tabla_base, ts_curvas = load_curvas(plazo)

    tabs = st.tabs(["Curvas", "Futuros", "Análisis de bono", "Comparador"])

    # ----- Pestaña Curvas -----
    with tabs[0]:
        st.subheader(f"Curvas BYMA ({plazo})")
        st.caption(f"Última actualización: {ts_curvas}")

        for nombre, lista in CURVAS.items():
            st.markdown(f"#### {nombre.capitalize()}")
            df_curva = tabla_base[tabla_base["Código"].isin(lista)].copy()
            if "Duration" in df_curva.columns:
                df_curva = df_curva.sort_values("Duration")
            df_curva = df_curva.reset_index(drop=True)
            if df_curva.empty:
                st.info("Sin datos de mercado para esta curva.")
                continue
            sty = style_curva(df_curva)
            st.write(sty.to_html(), unsafe_allow_html=True)

    # ----- Pestaña Futuros -----
    with tabs[1]:
        st.subheader("Futuros ROFEX dólar A3500")
        df_fut, a3500_spot, ts_fut = load_futuros()
        st.caption(f"Última actualización: {ts_fut}  |  Spot A3500 ref: {a3500_spot:,.2f}")

        if df_fut.empty:
            st.warning("No se pudieron obtener datos de futuros (timeout u otro error de conexión).")
        else:
            sty_f = style_futuros(df_fut)
            st.write(sty_f.to_html(), unsafe_allow_html=True)

    # ----- Pestaña Análisis de bono -----
    with tabs[2]:
        st.subheader("Análisis de bono individual")

        ticker_sel = st.selectbox("Seleccioná el bono", ALL_TICKERS_SORTED)

        bono_real = get_bono_real_from_ticker(ticker_sel)

        # Mini tabla de mercado a precio de mercado
        df_bono = tabla_base[tabla_base["Código"] == ticker_sel].copy()
        if not df_bono.empty:
            st.markdown("##### Métricas a precio de mercado")
            sty_bono = style_curva(df_bono)
            st.write(sty_bono.to_html(), unsafe_allow_html=True)

            precio_mercado = float(df_bono["Last Price"].iloc[0])
        else:
            st.info("No hay datos de mercado para este bono en el plazo seleccionado.")
            precio_mercado = None

        st.markdown("---")
        col_ticket, col_cash = st.columns([1.1, 1.9])

        # Ticket a precio de mercado
        with col_ticket:
            st.markdown("##### Ticket a precio de mercado")
            if precio_mercado is not None:
                precio_unit = precio_mercado / 100.0 if precio_mercado > 10 else precio_mercado
                if bono_real is not None and hasattr(bono_real, "genera_ticket"):
                    try:
                        html_ticket = _capture_output(bono_real.genera_ticket, precio_unit)
                        st.markdown(html_ticket, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error ejecutando genera_ticket: {e}")
                else:
                    st.info("Este bono/wrapper no expone el método `genera_ticket`.")
            else:
                st.info("No se pudo determinar el precio de mercado para este bono.")

        # Cashflows
        with col_cash:
            st.markdown("##### Cashflows (escenario actual)")

            if bono_real is None:
                st.info("No se pudo acceder al bono real para este ticker.")
            elif not hasattr(bono_real, "generate_cashflows"):
                st.info("Este bono no implementa `generate_cashflows` en la librería `rentafija`.")
            else:
                # Intentamos generar los cashflows una sola vez
                try:
                    # Si no pasás fecha, usa t + convención interna del bono
                    bono_real.generate_cashflows()

                    cf_cpn = getattr(bono_real, "cashflow_cpn", None)
                    cf_pmt = getattr(bono_real, "cashflow_pmt", None)
                    cf_error = None
                except Exception as e:
                    cf_cpn, cf_pmt = None, None
                    cf_error = e

                if cf_error is not None:
                    st.error(f"Error generando cashflows: {cf_error}")
                else:
                    c1, c2 = st.columns(2)

                    with c1:
                        st.markdown("**Cupones (CF CPN)**")
                        if isinstance(cf_cpn, pd.DataFrame):
                            st.dataframe(show_df_arrow_safe(cf_cpn), use_container_width=True)
                        elif cf_cpn is not None:
                            # Por si en algún bono raro no es DataFrame
                            st.write(cf_cpn)
                        else:
                            st.info("No se encontró `cashflow_cpn` luego de generar los flujos.")

                    with c2:
                        st.markdown("**Pagos totales (CF PMT)**")
                        if isinstance(cf_pmt, pd.DataFrame):
                            st.dataframe(show_df_arrow_safe(cf_pmt), use_container_width=True)
                        elif cf_pmt is not None:
                            st.write(cf_pmt)
                        else:
                            st.info("No se encontró `cashflow_pmt` luego de generar los flujos.")

        st.markdown("---")
        st.markdown("#### Escenarios")

        col_precio, col_tna = st.columns(2)

        # Escenario desde precio
        with col_precio:
            st.markdown("##### Desde precio")
            if bono_real is not None and hasattr(bono_real, "genera_ticket"):
                precio_default = float(precio_mercado) if precio_mercado is not None else 100.0
                precio_input = st.number_input(
                    "Precio sucio (por 100 VN)",
                    min_value=0.0,
                    value=precio_default,
                    step=0.0001,
                    format="%.4f",
                    key="precio_input",
                )
                if st.button("Calcular ticket a este precio"):
                    try:
                        precio_unit = precio_input / 100.0 if precio_input > 10 else precio_input
                        html_ticket_p = _capture_output(bono_real.genera_ticket, precio_unit)
                        st.markdown(html_ticket_p, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error ejecutando genera_ticket: {e}")
            else:
                st.info("El bono no expone `genera_ticket`.")

        # Escenario desde TNA
        with col_tna:
            st.markdown("##### Desde TNA")
            if bono_real is not None and hasattr(bono_real, "genera_ticket_tna"):
                tna_default = 5.0  # % de ejemplo
                tna_pct = st.number_input(
                    "TNA objetivo (%)",
                    min_value=-100.0,
                    value=tna_default,
                    step=0.01,
                    format="%.2f",
                    key="tna_input",
                )
                if st.button("Calcular ticket a esta TNA"):
                    try:
                        tna_decimal = tna_pct / 100.0
                        html_tna = _capture_output(bono_real.genera_ticket_tna, tna_decimal)
                        st.markdown(html_tna, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error ejecutando genera_ticket_tna: {e}")
            else:
                st.info("El bono no expone `genera_ticket_tna`.")

    # ----- Pestaña Comparador -----
    with tabs[3]:
        st.subheader("Comparador de bonos")

        col_sel = st.columns(2)
        with col_sel[0]:
            base_t = st.selectbox("Bono base", ALL_TICKERS_SORTED, key="comp_base")
        with col_sel[1]:
            comp_t = st.selectbox("Bono a comparar", ALL_TICKERS_SORTED, key="comp_comp")

        bono_base = get_bono_real_from_ticker(base_t)
        bono_comp = get_bono_real_from_ticker(comp_t)

        st.markdown("##### Comparación por precio")

        col_inputs = st.columns(3)
        with col_inputs[0]:
            precio_base = st.number_input(
                f"Precio {base_t} (por 100)",
                min_value=0.0,
                value=100.0,
                step=0.0001,
                format="%.4f",
                key="comp_precio_base",
            )
        with col_inputs[1]:
            precio_comp = st.number_input(
                f"Precio {comp_t} (por 100)",
                min_value=0.0,
                value=100.0,
                step=0.0001,
                format="%.4f",
                key="comp_precio_comp",
            )
        with col_inputs[2]:
            vn_nominales = st.number_input(
                "VN nominales del ticket",
                min_value=0.0,
                value=1_000_000.0,
                step=10000.0,
                format="%.0f",
                key="vn_nominales",
            )

        if st.button("Comparar por precio"):
            if bono_base is None or bono_comp is None:
                st.error("No se pudieron obtener ambos bonos.")
            elif not hasattr(bono_base, "comparar_precio"):
                st.error("El bono base no tiene método `comparar_precio`.")
            else:
                try:
                    p_base_unit = precio_base / 100.0 if precio_base > 10 else precio_base
                    p_comp_unit = precio_comp / 100.0 if precio_comp > 10 else precio_comp
                    df_comp = bono_base.comparar_precio(
                        bono_comp,
                        p_base_unit,
                        p_comp_unit,
                        vn_nominales,
                    )
                    if isinstance(df_comp, pd.DataFrame):
                        st.dataframe(show_df_arrow_safe(df_comp), use_container_width=True)
                    else:
                        st.write(df_comp)
                except Exception as e:
                    st.error(f"Error en comparar_precio: {e}")

        st.markdown("---")
        st.markdown("##### Comparación por TNA")

        col_tna = st.columns(3)
        with col_tna[0]:
            tna_base_pct = st.number_input(
                f"TNA {base_t} (%)",
                min_value=-100.0,
                value=5.0,
                step=0.01,
                format="%.2f",
                key="comp_tna_base",
            )
        with col_tna[1]:
            tna_comp_pct = st.number_input(
                f"TNA {comp_t} (%)",
                min_value=-100.0,
                value=5.0,
                step=0.01,
                format="%.2f",
                key="comp_tna_comp",
            )
        with col_tna[2]:
            vn_tna = st.number_input(
                "VN nominales (TNA)",
                min_value=0.0,
                value=1_000_000.0,
                step=10000.0,
                format="%.0f",
                key="comp_nominales_tna",
            )

        if st.button("Comparar por TNA"):
            if bono_base is None or bono_comp is None:
                st.error("No se pudieron obtener ambos bonos.")
            elif not hasattr(bono_base, "comparar_tna"):
                st.error("El bono base no tiene método `comparar_tna`.")
            else:
                try:
                    tna_base_dec = tna_base_pct / 100.0
                    tna_comp_dec = tna_comp_pct / 100.0

                    df_tna = bono_base.comparar_tna(
                        bono_comp,
                        tna_base_dec,
                        tna_comp_dec,
                        nominales_ticket=vn_tna,
                    )
                    if isinstance(df_tna, pd.DataFrame):
                        st.dataframe(show_df_arrow_safe(df_tna), use_container_width=True)
                    else:
                        st.write(df_tna)
                except Exception as e:
                    st.error(f"Error en comparar_tna: {e}")


if __name__ == "__main__":
    main()
