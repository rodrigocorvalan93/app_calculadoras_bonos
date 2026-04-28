# -*- coding: utf-8 -*-
# bymaapi.py — versión mejorada (perf + legibilidad) 
# Rodricor last version base 11/2025 — refactor 02/2026 240226
# =============================================================================

# %% Imports
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import numpy as np
import pandas as pd
import requests

import OMSsecrets  # noqa: F401 — auto-carga secrets.txt a os.environ
import rentafija
from especies import *  # asume que define objetos bono y/o colecciones (todos_los_bonos, etc.)
from plotter import *
from utils import *

# =============================================================================
# Config performance
# =============================================================================
MAX_WORKERS = 9  # ajustá según tu máquina / red
GUARDAR_BYMA_XLSX = False  # ponelo True solo para debug
DEFAULT_ENTRIES = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP,IV"
DEFAULT_DEPTH = 3

# =============================================================================
# Constantes
# =============================================================================
BASE_URL = "https://api.latinsecurities.matrizoms.com.ar/"

# =============================================================================
# Conexión / Instrumentos
# =============================================================================
def login_xoms(username: str, password: str) -> requests.Session:
    """
    Inicia sesión en la API de la alyc y retorna una sesión autenticada.
    """
    session = requests.Session()
    url = BASE_URL + "j_spring_security_check"
    credentials = {"j_username": username, "j_password": password}
    response = session.post(url, data=credentials)
    if response.ok:
        print("Autenticación exitosa en Cocos")
        return session
    raise Exception(f"Autenticación fallida: {response.status_code} {response.text}")


def get_segments(session: requests.Session) -> pd.DataFrame:
    """
    Obtiene la lista de segmentos y retorna un DataFrame con la columna 'marketSegmentId'.
    """
    url = BASE_URL + "rest/segment/all"
    response = session.get(url)
    segments_dict = response.json()
    segments_df = pd.DataFrame(segments_dict.get("segments", []))
    return segments_df[["marketSegmentId"]] if "marketSegmentId" in segments_df.columns else segments_df


def get_instruments(session: requests.Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Obtiene la lista de instrumentos y retorna:
      - instruments_df: DataFrame original.
      - instruments_df2: DataFrame con el campo 'instrumentId' desanidado.
    """
    url = BASE_URL + "rest/instruments/all"
    response = session.get(url)
    instruments_dict = response.json()
    instruments_df = pd.DataFrame(instruments_dict.get("instruments", []))
    if "instrumentId" in instruments_df.columns:
        instruments_df2 = pd.concat(
            [instruments_df.drop(["instrumentId"], axis=1), instruments_df["instrumentId"].apply(pd.Series)],
            axis=1
        )
    else:
        instruments_df2 = instruments_df.copy()
    return instruments_df, instruments_df2


def get_instruments_details(session: requests.Session) -> pd.DataFrame:
    """
    Obtiene los instrumentos detallados y retorna un DataFrame.
    """
    url = BASE_URL + "rest/instruments/details"
    response = session.get(url)
    detalles_dict = response.json()
    return pd.DataFrame(detalles_dict.get("instruments", []))


def get_instrument_detail(session: requests.Session, symbol: str) -> pd.DataFrame:
    """
    Obtiene la descripción detallada de un instrumento.
    """
    url = BASE_URL + "rest/instruments/detail"
    params = {"marketId": "ROFX", "symbol": symbol}
    response = session.get(url, params=params)

    if response.status_code != 200:
        raise Exception(f"Error HTTP {response.status_code}: {response.text}")

    data = response.json()
    if data.get("status") == "OK" and "instrument" in data:
        return pd.DataFrame([data["instrument"]])

    raise ValueError(f"Error en la respuesta de la API: {data}")


def search_instrument_by_description(instruments_df: pd.DataFrame, description: str) -> pd.DataFrame:
    """Retorna filas cuyo 'securityDescription' coincide exactamente."""
    return instruments_df[instruments_df["securityDescription"] == description]


# =============================================================================
# Market Data
# =============================================================================
def get_market_data(
    session: requests.Session,
    market_id: str,
    symbol: str,
    entries: str = DEFAULT_ENTRIES,
    depth: int = DEFAULT_DEPTH
) -> dict:
    """
    Obtiene datos de mercado para un instrumento dado.
    """
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{BASE_URL}rest/marketdata/get?marketId={market_id}&symbol={symbol_encoded}&entries={entries}&depth={depth}"
    response = session.get(url)

    if response.status_code != 200:
        print(f"Error en la solicitud para {symbol}: {response.status_code}")
        return {}

    mkt_dict = response.json()
    if mkt_dict.get("status") == "ERROR":
        print(f"Error en los datos de mercado para {symbol}")
        return {}

    data = mkt_dict.get("marketData", {}) or {}
    data["symbol"] = symbol
    return data


def bulk_get_market_data(
    session: requests.Session,
    symbols: list[str],
    market_id: str = "ROFX",
    entries: str = DEFAULT_ENTRIES,
    depth: int = DEFAULT_DEPTH,
    max_workers: int = MAX_WORKERS
) -> pd.DataFrame:
    """
    Versión paralela de get_market_data.
    Devuelve un DataFrame indexado por 'symbol'.
    Robusto: no se cae por 1 request fallido.
    """
    if not symbols:
        return pd.DataFrame()

    results = []

    def _worker(symbol: str):
        return get_market_data(session, market_id, symbol, entries, depth)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_worker, s): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                data = fut.result()
                if data:
                    results.append(data)
            except Exception as e:
                print(f"[bulk_get_market_data] {sym}: {e}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    return df.set_index("symbol")


def get_market_data_for_symbols(
    session: requests.Session,
    symbols: list,
    market_id: str = "ROFX",
    entries: str = DEFAULT_ENTRIES,
    depth: int = DEFAULT_DEPTH,
    max_workers: int = MAX_WORKERS
) -> pd.DataFrame:
    """Wrapper para no romper firma vieja."""
    if not symbols:
        return pd.DataFrame()
    return bulk_get_market_data(session, symbols, market_id, entries, depth, max_workers)


def get_mktdata(
    session: requests.Session,
    symbol: str,
    plazo=1,
    prefix: bool = True,
    market_id: str = "ROFX",
    entries: str = DEFAULT_ENTRIES,
    depth: int = DEFAULT_DEPTH
) -> dict:
    """
    Atajo “humano” para buscar marketdata por ticker y plazo.
    """
    prefix_str = "MERV - XMEV - " if prefix else ""
    suffix = " - 24hs" if plazo == 1 else " - CI" if plazo == 0 else ""
    code = f"{prefix_str}{symbol}{suffix}"
    code_encoded = requests.utils.quote(code)

    url = f"{BASE_URL}rest/marketdata/get?marketId={market_id}&symbol={code_encoded}&entries={entries}&depth={depth}"
    response = session.get(url)

    if not response.ok:
        print(f"Error en la solicitud para {symbol}: {response.status_code}")
        return {}

    mkt_dict = response.json()
    if mkt_dict.get("status") == "ERROR":
        print(f"Error en los datos de mercado para {symbol}")
        return {}

    data = mkt_dict.get("marketData", {}) or {}
    data["symbol"] = symbol
    return data


def extract_last_prices(market_data_df: pd.DataFrame) -> pd.DataFrame:
    """Extrae 'Last Price' con fallback LA → CL → ACP (post-mercado).

    Devuelve columnas:
        - symbol
        - Last Price
        - Price Source: 'LA' (último operado), 'CL' (cierre oficial),
          'ACP' (subasta de cierre), o None si no hay precio.
        - Price Date: fecha/hora del entry que terminó usándose (o None).
    """
    if market_data_df is None or market_data_df.empty:
        return pd.DataFrame(columns=["symbol", "Last Price", "Price Source", "Price Date"])

    idx = market_data_df.index
    symbols = idx.to_numpy()

    def _price(entry):
        return entry.get("price") if isinstance(entry, dict) else None

    def _date(entry):
        return entry.get("date") if isinstance(entry, dict) else None

    def _to_float(s):
        return pd.to_numeric(s, errors="coerce")

    la_p = _to_float(market_data_df["LA"].apply(_price)) if "LA" in market_data_df.columns else pd.Series(np.nan, index=idx, dtype="float64")
    cl_p = _to_float(market_data_df["CL"].apply(_price)) if "CL" in market_data_df.columns else pd.Series(np.nan, index=idx, dtype="float64")
    acp_p = _to_float(market_data_df["ACP"].apply(_price)) if "ACP" in market_data_df.columns else pd.Series(np.nan, index=idx, dtype="float64")

    la_d = market_data_df["LA"].apply(_date) if "LA" in market_data_df.columns else pd.Series(None, index=idx, dtype="object")
    cl_d = market_data_df["CL"].apply(_date) if "CL" in market_data_df.columns else pd.Series(None, index=idx, dtype="object")
    acp_d = market_data_df["ACP"].apply(_date) if "ACP" in market_data_df.columns else pd.Series(None, index=idx, dtype="object")

    last = la_p.fillna(cl_p).fillna(acp_p)

    source = pd.Series(index=idx, dtype="object")
    date = pd.Series(index=idx, dtype="object")

    use_la = la_p.notna()
    use_cl = (~use_la) & cl_p.notna()
    use_acp = (~use_la) & (~use_cl) & acp_p.notna()

    source[use_la] = "LA"
    source[use_cl] = "CL"
    source[use_acp] = "ACP"

    date[use_la] = la_d[use_la]
    date[use_cl] = cl_d[use_cl]
    date[use_acp] = acp_d[use_acp]

    return pd.DataFrame({
        "symbol": symbols,
        "Last Price": last.to_numpy(),
        "Price Source": source.to_numpy(),
        "Price Date": date.to_numpy(),
    })


# =============================================================================
# Helpers bonos — FIX sufijos v/j + perf + legibilidad
# =============================================================================
def _bond_obj(bond_code: str, eval_suffix: str = ""):
    """
    Devuelve el objeto bono correcto desde globals() usando bond_code+eval_suffix.
    Fallback: si no existe con sufijo, usa el base (solo si eval_suffix != "").
    """
    name = f"{bond_code}{eval_suffix}" if eval_suffix else bond_code
    obj = globals().get(name)
    if obj is None and eval_suffix:
        obj = globals().get(bond_code)
    return obj


def compute_bond_metrics(
    bond_code: str,
    last_price: float,
    bond_type: str = "lecap",
    today_str: str = None,
    eval_suffix: str = ""
) -> dict:
    """
    Calcula métricas financieras para un bono.

    Retorna dict con:
      - TIREA
      - TNA
      - TEM
      - Paridad
      - Duration

    FIX CLAVE: la TNA sale del MISMO instrumento que la TIR
    (ej: si eval_suffix="v" usa TXxxv, no TXxx).

    NUEVO: si el bond_type no está contemplado, usa la TNA nativa
    del instrumento (la misma convención que ves en genera_ticket).
    """
    try:
        bond_obj = _bond_obj(bond_code, eval_suffix)
        if bond_obj is None:
            raise KeyError(f"No existe bono '{bond_code}{eval_suffix}' en globals()")

        # --- TIR ---
        if today_str:
            tirea = bond_obj.calcula_tirea(last_price, today_str)
        else:
            tirea = bond_obj.calcula_tirea(last_price)

        bt = (bond_type or "").lower()

        # --- TNA nativa (convención del instrumento; la usa genera_ticket) ---
        tna_native = getattr(bond_obj, "tna", None)

        # --- TNA (convenciones tuyas + fallback a nativa) ---
        if bt in ("lecap", "tamar", "dlksob"):
            dias = getattr(bond_obj, "dias_remanentes", None)
            tna = rentafija.tir_a_tna(tirea, dias, 365) if dias else tna_native

        elif bt == "cer":
            tna = rentafija.tir_a_tna(tirea, 180, 365)

        elif bt == "hdsob":
            tna = rentafija.tir_a_tna(tirea, 180, 360)

        elif bt == "dual":
            tna = rentafija.tir_a_tna(tirea, 30, 365)

        else:
            # Si no es ninguno de los tipos conocidos: usar convención nativa del bono
            tna = tna_native

        # --- TEM ---
        tem = (1 + tirea) ** (30 / 360) - 1

        # --- Paridad / Duration ---
        paridad = getattr(bond_obj, "paridad", None)

        if today_str:
            duration = bond_obj.calcula_duration(tirea, today_str)
        else:
            duration = bond_obj.calcula_duration(tirea)

        return {"TIREA": tirea, "TNA": tna, "TEM": tem, "Paridad": paridad, "Duration": duration}

    except Exception as e:
        print(f"Error al procesar {bond_code}{eval_suffix}: {e}")
        return {"TIREA": None, "TNA": None, "TEM": None, "Paridad": None, "Duration": None}


def process_bond_dataframe(
    df: pd.DataFrame,
    bond_type: str = "lecap",
    today_str: str = None,
    eval_suffix: str = ""
) -> pd.DataFrame:
    """
    Procesa un DataFrame con columnas: 'Código' y 'Last Price'
    agrega métricas.

    Mejora: tem_spread se calcula numérico antes de formatear strings.
    """
    df = df.copy()

    def calcular_metricas(row):
        lp = row.get("Last Price", None)
        if pd.notnull(lp):
            price = lp / 100  # tu convención (precio*100)
            return compute_bond_metrics(row["Código"], price, bond_type, today_str, eval_suffix)
        return {"TIREA": None, "TNA": None, "TEM": None, "Paridad": None, "Duration": None}

    metrics = df.apply(calcular_metricas, axis=1, result_type="expand")
    df = pd.concat([df, metrics], axis=1)

    # --- Spread numérico ---
    try:
        tem_num = pd.to_numeric(df["TEM"], errors="coerce")
        df["tem_spread"] = tem_num.diff().fillna(0)
    except Exception as e:
        print(f"Error al calcular tem_spread: {e}")
        df["tem_spread"] = np.nan

    # --- Formateo a % (mantengo tu salida para no romper cosas aguas abajo) ---
    for col in ["TEM", "TNA", "TIREA"]:
        df[col] = df[col].apply(lambda x: f"{x:.2%}" if isinstance(x, (float, int, np.floating)) else None)

    df["tem_spread"] = df["tem_spread"].apply(
        lambda x: f"{(x*100):.2f}%" if isinstance(x, (float, int, np.floating)) else None
    )

    return df.sort_values(by="Duration").reset_index(drop=True)


def create_bond_prices_df(
    full_symbols: list,
    last_prices_df: pd.DataFrame,
    prefix: str = "MERV - XMEV - ",
    suffix: str = " - 24hs"
) -> pd.DataFrame:
    """
    Crea DF con columnas: symbol, Código, Last Price.
    Robusto ante casos donde 'symbol' está como índice y columna (merge ambiguo).
    """
    if not full_symbols:
        return pd.DataFrame(columns=["symbol", "Código", "Last Price"])

    base = pd.DataFrame({"symbol": full_symbols})
    base["Código"] = base["symbol"].str.replace(prefix, "", regex=False).str.replace(suffix, "", regex=False)

    if last_prices_df is None or last_prices_df.empty:
        base["Last Price"] = np.nan
        return base

    lp = last_prices_df.copy()

    # --- Normalizar: 'symbol' SOLO como columna (nunca como índice) ---
    # Si 'symbol' es nombre de índice (o multiindex), lo bajamos a columna
    if getattr(lp.index, "names", None) and "symbol" in lp.index.names:
        lp = lp.reset_index()

    # Si el índice se llama 'symbol' (caso simple), también lo bajamos
    if lp.index.name == "symbol":
        lp = lp.reset_index()

    # Si por reset_index quedaron dos columnas symbol, nos quedamos con la primera
    if isinstance(lp.columns, pd.Index):
        cols = list(lp.columns)
        if cols.count("symbol") > 1:
            # elimina duplicadas manteniendo la primera
            seen = set()
            keep_cols = []
            for c in cols:
                if c == "symbol":
                    if "symbol" in seen:
                        continue
                    seen.add("symbol")
                keep_cols.append(c)
            lp = lp.loc[:, keep_cols]

    # Asegurar que están las columnas mínimas
    if "symbol" not in lp.columns or "Last Price" not in lp.columns:
        raise ValueError("last_prices_df debe tener columnas ['symbol', 'Last Price'] (o 'symbol' en el índice).")

    # Merge limpio (incluye Price Source / Price Date si vienen)
    merge_cols = ["symbol", "Last Price"]
    for opt_col in ("Price Source", "Price Date"):
        if opt_col in lp.columns:
            merge_cols.append(opt_col)
    out = base.merge(lp[merge_cols], on="symbol", how="left")
    return out



# =============================================================================
# Aplanar DataFrame de datos anidados
# =============================================================================
def aplanar_df(df: pd.DataFrame, keys_adicionales: list = None) -> pd.DataFrame:
    """
    Convierte un DataFrame con datos anidados (BI, SE, LA, OI, OF, etc.)
    en uno plano (cada fila una cotización).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["symbol", "side", "price", "size"])

    filas_planas = []
    for symbol, row in df.iterrows():
        for side in df.columns:
            celda = row[side]
            if celda is None or celda == []:
                continue
            if not isinstance(celda, list):
                celda = [celda]

            for registro in celda:
                if isinstance(registro, dict):
                    nueva_fila = {
                        "symbol": symbol,
                        "side": side,
                        "price": registro.get("price"),
                        "size": registro.get("size")
                    }
                    if keys_adicionales:
                        for key in keys_adicionales:
                            nueva_fila[key] = registro.get(key)
                    filas_planas.append(nueva_fila)
                else:
                    filas_planas.append({"symbol": symbol, "side": side, "price": None, "size": registro})

    return pd.DataFrame(filas_planas)


# =============================================================================
# Futuros — helpers
# =============================================================================
def process_future_data(
    df: pd.DataFrame,
    symbol_length: int,
    instrumentos_vencimientos: pd.DataFrame,
    a3500_override: float
) -> pd.DataFrame:
    """
    Filtra y procesa futuros según longitud de símbolo.
    """
    df_filtered = df[(df["side"] == "LA") & (df["symbol"].str.len() == symbol_length)].copy()
    df_filtered = df_filtered.merge(instrumentos_vencimientos, on="symbol", how="left")
    df_filtered["maturityDate"] = pd.to_datetime(df_filtered["maturityDate"], format="%Y%m%d")
    df_filtered["days_to_maturity"] = (pd.Timestamp.today() - df_filtered["maturityDate"]).dt.days * -1

    df_filtered["tasa_directa"] = df_filtered["price"] / a3500_override - 1
    df_filtered["TNA"] = df_filtered["tasa_directa"] * (365 / df_filtered["days_to_maturity"])
    df_filtered["TEA"] = (1 + df_filtered["tasa_directa"]) ** (365 / df_filtered["days_to_maturity"]) - 1
    df_filtered = df_filtered.sort_values(by="days_to_maturity", ascending=True).reset_index(drop=True)
    return df_filtered


# =============================================================================
# Excel
# =============================================================================
def guardar_excel(df: pd.DataFrame, file_path: str) -> None:
    """
    Guarda el DF en Excel, concatenando con datos existentes si existe.
    Mantengo tu lógica, pero ojo: ahora TEM/TNA/TIREA vienen formateadas como % strings.
    """
    for col in ['TIREA', 'TNA', 'TEM', 'tem_spread']:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace('%', '').str.replace(',', '.').str.strip(),
            errors='coerce'
        ) / 100

    try:
        if os.path.exists(file_path):
            df_existente = pd.read_excel(file_path, parse_dates=["fecha_hoy"])
            df_existente["fecha_hoy"] = pd.to_datetime(df_existente["fecha_hoy"]).dt.date
            df_final = pd.concat([df_existente, df], ignore_index=True)
        else:
            df_final = df

        df_last = df_final.drop_duplicates(subset=['symbol', 'Código', 'fecha_hoy'], keep='last')
        df_last = df_last.dropna(subset=['Last Price', 'TIREA', 'TNA', 'TEM', 'Paridad', 'Duration'])
        df_last['Proy'] = np.where(df_last['Código'].str.endswith('j'), 1, 0)

        for col in ['TIREA', 'TNA', 'TEM']:
            df_last[col].replace('nan%', '', inplace=True)

        df_last.to_excel(file_path, index=False)
        print(f"DataFrame guardado con éxito en '{file_path}'.")

    except Exception as e:
        print(f"Error al guardar el archivo: {e}")


# =============================================================================
# Main
# =============================================================================
def main():
    global lecap_24hs_prices_df, lecap_ci_prices_df, tamar_24hs_prices_df, dual_24hs_prices_df
    global cer_ci_prices_df, cer_24hs_prices_df, mkt_data_global_df, cerproyectado_24hs_prices_df
    global fx_resumen, fx_resumen_styled, futuros_minorista, futuros_mayorista, futuros_df
    global dlksob_24hs_prices_df, global_24hs_prices_df, bonar_24hs_prices_df, dual_fija_24hs_prices_df, bopreal_24hs_prices_df
    global todos_24hs_df, session

    # --- Credenciales por env (NO hardcode) ---
    username = os.getenv("OMS_USER")
    password = os.getenv("OMS_PASS")
    if not username or not password:
        raise RuntimeError(
            "Faltan OMS_USER / OMS_PASS. Definilas en secrets.txt (formato KEY=VALUE)."
        )

    session = login_xoms(username, password)

    # --- A3500 override (por env o por variable global preexistente) ---
    from indices import fx_status_text, refresh_a3500_in_rentafija
 
    session = login_xoms(username, password)
    
    # Refrescar FX con session (ahora puede usar DLR/SPOT como fallback)
    a3500_override = refresh_a3500_in_rentafija(session=session)
    print(f"[FX] {fx_status_text()}")

    # --- Básicos ---
    segments_df = get_segments(session)
    print("Segmentos:")
    print(segments_df)

    instruments_df, instruments_df2 = get_instruments(session)
    instrumentos_detallados_df = get_instruments_details(session)

    # --- Market Data para Futuros ---
    futuros_market_data = []
    df_filtrado = instrumentos_detallados_df[instrumentos_detallados_df["underlying"] == "Dólar USA A3500"]
    instrumentos_ids = pd.json_normalize(df_filtrado["instrumentId"])

    for instrument in instrumentos_ids.itertuples():
        market_id = getattr(instrument, "marketId", None)
        symbol = getattr(instrument, "symbol", None)
        if market_id and symbol:
            data = get_market_data(session, market_id, symbol)
            if data:
                futuros_market_data.append(data)

    if futuros_market_data:
        futuros_df = pd.DataFrame(futuros_market_data).set_index("symbol")
        print("\nMarket data para futuros: OK")
    else:
        print("No se obtuvieron datos de mercado para futuros.")
        futuros_df = pd.DataFrame()

    futuros_dff = aplanar_df(futuros_df)

    futuros_dff_minorista = futuros_dff[(futuros_dff["side"] == "LA") & (futuros_dff["symbol"].str.len() == 9)]
    futuros_dff_mayorista = futuros_dff[(futuros_dff["side"] == "LA") & (futuros_dff["symbol"].str.len() == 10)]

    instrumentos_detallados_df["symbol"] = instrumentos_detallados_df["instrumentId"].apply(
        lambda x: x.get("symbol") if isinstance(x, dict) else None
    )
    instrumentos_vencimientos = instrumentos_detallados_df[["symbol", "maturityDate"]]

    futuros_mayorista = process_future_data(
        futuros_dff_mayorista, symbol_length=10,
        instrumentos_vencimientos=instrumentos_vencimientos,
        a3500_override=a3500_override
    )
    futuros_minorista = process_future_data(
        futuros_dff_minorista, symbol_length=9,
        instrumentos_vencimientos=instrumentos_vencimientos,
        a3500_override=a3500_override
    )

    # --- Listas Bonos ---
    '''
    lista_curva_cer = ["TX26", "TZXM6", "X29Y6", "TZX26", "X31L6",
                       "TZXO6", "X30N6", "TZXD6", "TZXM7",
                       "TZXA7", "TZXY7", "TZX27", "TZXD7", "TZX28", 
                       "TX28", "DICP", "TX31", "PARP", "CUAP"]
    '''
    lista_curva_cer = [
        b.codigo for b in todos_los_bonos
        if b.industria == "Soberano Inflación"
    ]
    lista_cer_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_cer]
    lista_cer_ci = [f"MERV - XMEV - {s} - CI" for s in lista_curva_cer]

    '''lista_curva_lecap = ["S27F6", "S16M6", "S17A6", "S30A6", "S29Y6", "T30J6",
                         "S31L6", "S31G6", "TO26", "S30O6", "S30N6",
                         "T15E7", "T30A7", "T31Y7", "T30J7", "TY30P"]'''

    lista_curva_lecap = [
        b.codigo for b in todos_los_bonos
        if b.industria == "Soberano ARS Tasa Fija"
        and b.clasificacion == "Soberano"
        or b.industria == "Soberano Letras Zero Cupón (Ledes y Letes)"
    ]
    lista_lecap_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_lecap]
    lista_lecap_ci = [f"MERV - XMEV - {s} - CI" for s in lista_curva_lecap]


    lista_tamar_24hs = [
        b.codigo for b in todos_los_bonos
        if b.industria == "Soberano ARS TAMAR"
    ]
    lista_tamar_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_tamar_24hs]

    lista_curva_global = [
            b.codigo for b in todos_los_bonos
            if b.industria == "Soberano USD Ley Extranjera"
            and b.quote_price_cnv == "DIRTY"
        ]
    lista_global_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_global]
    lista_global_ci = [f"MERV - XMEV - {s} - CI" for s in lista_curva_global]

    lista_curva_dlksob = [
            b.codigo for b in todos_los_bonos
            if b.industria == "Soberanos Dolar Linked"
        ]
    lista_dlksob_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_dlksob]

    lista_curva_dual_fija = [
        b.codigo for b in todos_los_bonos
        if b.clasificacion == "Soberano"
        and b.industria == "Soberano ARS Dual Fija/Tamar"
    ]
    lista_curva_dual_fija_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_dual_fija]

    lista_curva_bonar = [
        b.codigo for b in todos_los_bonos
        if b.clasificacion == "Soberano"
        and b.industria == "Soberano USD Ley Argentina D"
        and b.quote_price_cnv == "DIRTY"
    ]

    lista_curva_bonar_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_bonar]

    lista_curva_bopreal = [
        b.codigo for b in todos_los_bonos
        if b.clasificacion == "Soberano"
        and b.industria == "Soberanos USD BCRA D"
        and b.quote_price_cnv == "DIRTY"
    ]
    lista_curva_bopreal_24hs = [f"MERV - XMEV - {s} - 24hs" for s in lista_curva_bopreal]

    # --- Market Data Bonos ---
    lista_all = (
        lista_cer_24hs + lista_lecap_24hs + lista_tamar_24hs + lista_global_24hs
        + lista_cer_ci + lista_lecap_ci
        + lista_dlksob_24hs + lista_curva_dual_fija_24hs + lista_curva_bonar_24hs + lista_curva_bopreal_24hs
    )

    mkt_data_global_df = get_market_data_for_symbols(session, lista_all, market_id="ROFX")

    if GUARDAR_BYMA_XLSX:
        mkt_data_global_df.to_excel("bymaprices.xlsx")
        print("\nMarket data para curvas combinadas obtenida y guardada en 'bymaprices.xlsx'.")
    else:
        print("\nMarket data para curvas combinadas obtenida (sin guardar Excel).")

    last_px_global_df = extract_last_prices(mkt_data_global_df)

    # --- DFs precios ---
    cer_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df, suffix=" - 24hs")
    lecap_24hs_prices_df = create_bond_prices_df(lista_lecap_24hs, last_px_global_df, suffix=" - 24hs")
    tamar_24hs_prices_df = create_bond_prices_df(lista_tamar_24hs, last_px_global_df, suffix=" - 24hs")
    dlksob_24hs_prices_df = create_bond_prices_df(lista_dlksob_24hs, last_px_global_df, suffix=" - 24hs")
    global_24hs_prices_df = create_bond_prices_df(lista_global_24hs, last_px_global_df, suffix=" - 24hs")
    dual_fija_24hs_prices_df = create_bond_prices_df(lista_curva_dual_fija_24hs, last_px_global_df, suffix=" - 24hs")
    bonar_24hs_prices_df = create_bond_prices_df(lista_curva_bonar_24hs, last_px_global_df, suffix=" - 24hs")
    bopreal_24hs_prices_df = create_bond_prices_df(lista_curva_bopreal_24hs, last_px_global_df, suffix=" - 24hs")

    # --- Métricas (24hs) ---
    cer_24hs_prices_df = process_bond_dataframe(cer_24hs_prices_df, bond_type="cer", today_str=None, eval_suffix="")
    lecap_24hs_prices_df = process_bond_dataframe(lecap_24hs_prices_df, bond_type="lecap", today_str=None, eval_suffix="")
    tamar_24hs_prices_df = process_bond_dataframe(tamar_24hs_prices_df, bond_type="tamar", today_str=None, eval_suffix="")
    dlksob_24hs_prices_df = process_bond_dataframe(dlksob_24hs_prices_df, bond_type="dlksob", today_str=None, eval_suffix="")
    global_24hs_prices_df = process_bond_dataframe(global_24hs_prices_df, bond_type="hdsob", today_str=None, eval_suffix="")
    dual_fija_24hs_prices_df = process_bond_dataframe(dual_fija_24hs_prices_df, bond_type="lecap", today_str=None, eval_suffix="")
    bonar_24hs_prices_df = process_bond_dataframe(bonar_24hs_prices_df, bond_type="hdsob", today_str=None, eval_suffix="")
    bopreal_24hs_prices_df = process_bond_dataframe(bopreal_24hs_prices_df, bond_type="bopreal", today_str=None, eval_suffix="")

    print("\nMétricas para CER 24hs:")
    print(cer_24hs_prices_df)
    print("\nMétricas para Lecap 24hs:")
    print(lecap_24hs_prices_df)
    print("\nMétricas para Bonar 24hs:")
    print(bonar_24hs_prices_df)

    # --- CER proyectado (sufijo j) ---
    cerproyectado_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df, suffix=" - 24hs")
    cerproyectado_24hs_prices_df = process_bond_dataframe(
        cerproyectado_24hs_prices_df, bond_type="cer", today_str=None, eval_suffix="j"
    )
    cerproyectado_24hs_prices_df["Código"] = cerproyectado_24hs_prices_df["Código"] + "j"

    # --- Dual variable (sufijo v) — FIX: TNA ahora sale del v ---
    dual_24hs_prices_df = create_bond_prices_df(lista_curva_dual_fija_24hs, last_px_global_df, suffix=" - 24hs")
    dual_24hs_prices_df = process_bond_dataframe(dual_24hs_prices_df, bond_type="dual", today_str=None, eval_suffix="v")
    dual_24hs_prices_df["Código"] = dual_24hs_prices_df["Código"] + "v"

    # --- CI ---
    today_str = rentafija.n_dias_laborales(date.today(), 0).strftime("%d/%m/%Y")
    cer_ci_prices_df = create_bond_prices_df(lista_cer_ci, last_px_global_df, suffix=" - CI")
    lecap_ci_prices_df = create_bond_prices_df(lista_lecap_ci, last_px_global_df, suffix=" - CI")

    cer_ci_prices_df = process_bond_dataframe(cer_ci_prices_df, bond_type="cer", today_str=today_str, eval_suffix="")
    lecap_ci_prices_df = process_bond_dataframe(lecap_ci_prices_df, bond_type="lecap", today_str=today_str, eval_suffix="")

    print("\nMétricas para CER CI:")
    print(cer_ci_prices_df)
    print("\nMétricas para Lecap CI:")
    print(lecap_ci_prices_df)

    # --- Combine / histórico ---
    df_combined = pd.concat(
        [cer_24hs_prices_df, lecap_24hs_prices_df, tamar_24hs_prices_df, global_24hs_prices_df,
         bonar_24hs_prices_df, cerproyectado_24hs_prices_df, dual_24hs_prices_df, bopreal_24hs_prices_df],
        ignore_index=True
    )
    df_combined["fecha_hoy"] = datetime.today().date()
    todos_24hs_df = df_combined

    user_profile = os.environ.get("USERPROFILE", "")
    file_path = os.path.join(
        user_profile, "DELTA ASSET MANAGEMENT S.A", "Inversiones - Documentos",
        "Delta Bases", "Delta - historico_byma_px_tasas.xlsx"
    )

    respuesta = input("¿Deseas guardar el DataFrame en un archivo Excel? (S/N): ").strip().upper()
    if respuesta == "S":
        guardar_excel(df_combined, file_path)
    elif respuesta == "N":
        print("No se ha guardado el DataFrame.")
    else:
        print("Respuesta no reconocida. No se ha realizado ninguna acción.")

    # --- A PARTIR DE ACÁ: tu bloque FX lo dejé tal cual lo tenías ---
    # (para no tocar nada / no romper dependencias)
    # Podés pegar tu bloque FX original aquí sin cambios.

    print("\nEjecución de main() finalizada.\n")


refresh = main

if __name__ == '__main__':
    main()

# GUIA:
# buscar activo:        get_market_data(session,"ROFX","MERV - XMEV - AL30 - CI")
# calcular fx:          CCL_AL30_LAST_CI =calcula_tipo_de_cambio("AL30","CCL","CI","LAST",session)
# buscador de detalles: search_instrument_by_description(instrumentos_detallados_df, "MERV - XMEV - AL30 - CI")
# detalle simplificado: get_instrumento_detalle(session, "T30E6")
# market data simple:   get_mktdata(session,"T30E6")
# Ejemplo obtener BID/OFFER de un bono y su tasa: PARP.genera_ticket(get_mktdata(session,"PARP").get("OF")[0].get('price')/100)
# Ejemplo last: PARP.genera_ticket(get_mktdata(session,"PARP").get("LA").get("price")/100)
# Ejemplo de gráfico:
# Gráfico sin zoom: graficar_duration_tir_nss(lecap_24hs_prices_df)
# Gráfico filtrando filas 8 11 y 12: graficar_duration_tir_nss(lecap_24hs_prices_df.drop([8, 11, 12]).reset_index(drop=True),rango_x_min_plot=0.5, rango_x_max_plot=1.0)
# Gráfico con zoom: graficar_duration_tir_nss(lecap_24hs_prices_df, rango_x_min_plot=0.5, rango_x_max_plot=1.0)
# Estimar tir: estimar_dur_tirtem_nss(0.75, lecap_24hs_prices_df)
# Ejmplo usos de Forward:
# Forward alto = premio por extender duration → compro largo / vendo corto; forward bajo = castigo por extender → vendo largo / compro corto.
# La celda es la tasa forward anualizada entre el vencimiento de la fila y el vencimiento de la columna
# all_ars = pd.concat([cerproyectado_24hs_prices_df, lecap_24hs_prices_df], ignore_index=True).sort_values("Duration")
# maturity_map = {b.codigo: b.duration for b in todos_los_bonos}
# fw_lecap = matriz_forwards_tir(lecap_24hs_prices_df, maturity_map=maturity_map)
# fw_cer   = matriz_forwards_tir(cer_24hs_prices_df, maturity_map=maturity_map)
# Export formato excel:
# df.style.format(decimal=',', thousands='.')
# df.to_csv('curva_tasas.csv', sep=';', decimal=',', index=False)


# %%

