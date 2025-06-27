#%%
import requests
import json
import pandas as pd
import os
from datetime import date
import rentafija
from especies import *

# =============================================================================
# Configuración de la API de Cocos
# =============================================================================
BASE_URL = "https://api.cocos.xoms.com.ar/"

# =============================================================================
# Funciones de Autenticación
# =============================================================================
def login_cocos(username: str, password: str) -> requests.Session:
    """
    Inicia sesión en la API de Cocos y retorna una sesión autenticada.
    """
    session = requests.Session()
    form_action_url = BASE_URL + "j_spring_security_check"
    credentials = {
        "j_username": username,
        "j_password": password
    }
    response = session.post(form_action_url, data=credentials)
    if response.ok:
        print("Autenticación exitosa en Cocos")
        return session
    else:
        raise Exception(f"Autenticación fallida: {response.status_code} {response.text}")

# =============================================================================
# Funciones de Obtención de Datos
# =============================================================================
def get_segments(session: requests.Session) -> pd.DataFrame:
    """
    Obtiene la lista de segmentos y retorna un DataFrame con la columna 'marketSegmentId'.
    """
    url = BASE_URL + "rest/segment/all"
    response = session.get(url)
    segments_dict = response.json()
    segments_df = pd.DataFrame(segments_dict.get('segments', []))
    if 'marketSegmentId' in segments_df.columns:
        return segments_df[['marketSegmentId']]
    else:
        return segments_df

def get_instruments(session: requests.Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Obtiene la lista de instrumentos y retorna:
      - instruments_df: DataFrame original.
      - instruments_df2: DataFrame con el campo 'instrumentId' desanidado.
    """
    url = BASE_URL + "rest/instruments/all"
    response = session.get(url)
    instruments_dict = response.json()
    instruments_df = pd.DataFrame(instruments_dict.get('instruments', []))
    if 'instrumentId' in instruments_df.columns:
        instruments_df2 = pd.concat([instruments_df.drop(['instrumentId'], axis=1), instruments_df['instrumentId'].apply(pd.Series)], axis=1)
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
    instrumentos_detallados_df = pd.DataFrame(detalles_dict.get('instruments', []))
    return instrumentos_detallados_df

def search_instrument_by_description(instruments_df: pd.DataFrame, description: str) -> pd.DataFrame:
    """
    Retorna las filas del DataFrame cuyo 'securityDescription' coincide con el valor buscado.
    """
    return instruments_df[instruments_df['securityDescription'] == description]

def get_market_data(session: requests.Session, market_id: str, symbol: str, entries="BI,OF,OI,LA,SE", depth=3) -> dict:
    """
    Obtiene datos de mercado para un instrumento dado.
    """
    base_url = BASE_URL + "rest/marketdata/get"
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{base_url}?marketId={market_id}&symbol={symbol_encoded}&entries={entries}&depth={depth}"
    response = session.get(url)
    if response.status_code == 200:
        mkt_dict = response.json()
        if mkt_dict.get("status") != "ERROR":
            data = mkt_dict.get("marketData", {})
            data["symbol"] = symbol
            return data
        else:
            print(f"Error en los datos de mercado para {symbol}")
            return {}
    else:
        print(f"Error en la solicitud para {symbol}: {response.status_code}")
        return {}

def get_market_data_for_symbols(session: requests.Session, symbols: list, market_id="ROFX", entries="BI,OF,OI,LA,SE", depth=3) -> pd.DataFrame:
    """
    Obtiene datos de mercado para una lista de símbolos y retorna un DataFrame indexado por 'symbol'.
    """
    market_data_list = []
    for symbol in symbols:
        data = get_market_data(session, market_id, symbol, entries, depth)
        if data:
            market_data_list.append(data)
    if market_data_list:
        df = pd.DataFrame(market_data_list)
        return df.set_index('symbol')
    else:
        return pd.DataFrame()

def extract_last_prices(market_data_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae los 'Last Price' de la entrada 'LA' en los datos de mercado y retorna un DataFrame.
    """
    last_prices = market_data_df['LA'].apply(lambda entry: entry['price'] if entry is not None and 'price' in entry else None)
    return pd.DataFrame({'symbol': market_data_df.index, 'Last Price': last_prices})

# =============================================================================
# Funciones para Cálculos Financieros (Bonos)
# =============================================================================
def compute_bond_metrics(bond_code: str, last_price: float, bond_type: str='lecap', today_str: str=None, eval_suffix: str='') -> dict:
    """
    Calcula métricas financieras para un bono mediante eval.
    
    Parámetros:
      - bond_code: Código del bono (por ejemplo, "TX26").
      - last_price: Precio ya dividido entre 100.
      - bond_type: 'lecap' o 'cer' para seleccionar la función de TNA.
      - today_str: Fecha (string) si se requiere incluirla en la llamada.
      - eval_suffix: Sufijo a agregar en las llamadas (por ejemplo, 'j' para bonos proyectados).
      
    Retorna un diccionario con: TIREA, TNA, TEM, Paridad, Duration.
    """
    try:
        if today_str:
            command_tirea = f"{bond_code}{eval_suffix}.calcula_tirea({last_price}, '{today_str}')"
        else:
            command_tirea = f"{bond_code}{eval_suffix}.calcula_tirea({last_price})"
        tirea = eval(command_tirea)
        bond_obj = eval(bond_code)
        if bond_type.lower() == 'lecap':
            tna = rentafija.tir_a_tna(bond_obj.tirea, bond_obj.dias_remanentes, 365)
        elif bond_type.lower() == 'cer':
            tna = tna_a_tir(bond_obj.tirea, bond_obj.dias_remanentes, 365)
        else:
            tna = None
        tem = (1 + tirea)**(30/365) - 1
        command_paridad = f"{bond_code}{eval_suffix}.paridad"
        paridad = eval(command_paridad)
        if today_str:
            command_duration = f"{bond_code}{eval_suffix}.calcula_duration({bond_code}{eval_suffix}.tirea, '{today_str}')"
        else:
            command_duration = f"{bond_code}{eval_suffix}.calcula_duration({bond_code}{eval_suffix}.tirea)"
        duration = eval(command_duration)
        return {'TIREA': tirea, 'TNA': tna, 'TEM': tem, 'Paridad': paridad, 'Duration': duration}
    except Exception as e:
        print(f"Error al procesar {bond_code}: {e}")
        return {'TIREA': None, 'TNA': None, 'TEM': None, 'Paridad': None, 'Duration': None}

def process_bond_dataframe(df: pd.DataFrame, bond_type: str='lecap', today_str: str=None, eval_suffix: str='') -> pd.DataFrame:
    """
    Procesa un DataFrame con precios de bonos (debe tener las columnas 'Código' y 'Last Price')
    y agrega las métricas calculadas.
    """
    for idx, row in df.iterrows():
        codigo = row['Código']
        if pd.notnull(row['Last Price']):
            price = row['Last Price'] / 100  # Se asume que se requiere dividir el precio
            metrics = compute_bond_metrics(codigo, price, bond_type=bond_type, today_str=today_str, eval_suffix=eval_suffix)
        else:
            metrics = {'TIREA': None, 'TNA': None, 'TEM': None, 'Paridad': None, 'Duration': None}
        for key, value in metrics.items():
            df.at[idx, key] = value
    # Dar formato a las tasas (si no son None)
    for col in ['TEM', 'TNA', 'TIREA']:
        df[col] = df[col].apply(lambda x: "{:.2%}".format(x) if x is not None else None)
    try:
        df['tem_spread'] = df['TEM'].str.rstrip('%').astype(float).diff().fillna(0)
        df['tem_spread'] = df['tem_spread'].apply(lambda x: "{:.2f}%".format(x))
    except Exception as e:
        print(f"Error al calcular tem_spread: {e}")
        df['tem_spread'] = None
    return df

def create_bond_prices_df(full_symbols: list, last_prices_df: pd.DataFrame, prefix="MERV - XMEV - ", suffix=" - 24hs") -> pd.DataFrame:
    """
    A partir de una lista de símbolos completos (por ejemplo, "MERV - XMEV - TX26 - 24hs")
    y el DataFrame con los last prices, crea un DataFrame con las columnas:
      - symbol (nombre completo),
      - Código (el código limpio, sin prefijo ni sufijo),
      - Last Price.
    """
    records = []
    for symbol in full_symbols:
        codigo = symbol.replace(prefix, "").replace(suffix, "")
        match = last_prices_df[last_prices_df['symbol'] == symbol]
        price = match.iloc[0]['Last Price'] if not match.empty else None
        records.append({'symbol': symbol, 'Código': codigo, 'Last Price': price})
    return pd.DataFrame(records)

# =============================================================================
# Bloque Principal (Main)
# =============================================================================
#%% Refresh Main
if __name__ == '__main__':
    # --- Autenticación ---
    username = "37376293"
    password = "ZEfM77iQ_"
    session = login_cocos(username, password)
    
    # --- Obtención de Datos Básicos ---
    segments_df = get_segments(session)
    print("Segmentos:")
    print(segments_df)
    
    instruments_df, instruments_df2 = get_instruments(session)
    instrumentos_detallados_df = get_instruments_details(session)
    
    # Ejemplo: Buscar un instrumento por descripción
    search_description = "MERV - XMEV - TX26 - 24hs"
    resultado_busqueda = search_instrument_by_description(instrumentos_detallados_df, search_description)
    print("\nResultado de búsqueda por descripción:")
    print(resultado_busqueda)
    
    # --- Market Data para Futuros (ejemplo) ---
    # Se buscan instrumentos con underlying 'Dólar USA A3500'
    futuros_market_data = []
    for instrument in pd.json_normalize(instrumentos_detallados_df[instrumentos_detallados_df['underlying'] == 'Dólar USA A3500']['instrumentId']).itertuples():
        market_id = getattr(instrument, 'marketId', None)
        symbol = getattr(instrument, 'symbol', None)
        if market_id and symbol:
            data = get_market_data(session, market_id, symbol)
            if data:
                futuros_market_data.append(data)
    if futuros_market_data:
        futuros_df = pd.DataFrame(futuros_market_data).set_index('symbol')
        print("\nMarket data para futuros:")
        print(futuros_df)
    else:
        print("No se obtuvieron datos de mercado para futuros.")


    ###### Funcion para hacer plano precios bid offer etc #######


    def aplanar_df(df, keys_adicionales=None):
        """
        Convierte un DataFrame con datos anidados en columnas (por ejemplo, BI, SE, LA, OI, OF)
        a un DataFrame "plano" en el que cada fila representa una cotización individual.

        Parámetros:
        -----------
        df : pandas.DataFrame
            DataFrame original, cuyo índice representa el símbolo y las columnas contienen datos anidados.
        keys_adicionales : list (opcional)
            Lista de nombres de claves adicionales a extraer de cada diccionario (por ejemplo, ['date']).

        Retorna:
        --------
        pandas.DataFrame
            DataFrame aplanado con las columnas:
            - 'symbol': el símbolo (tomado del índice original)
            - 'side': el nombre de la columna de origen (por ejemplo, 'BI', 'SE', etc.)
            - 'price': el precio extraído del diccionario
            - 'size': el tamaño extraído del diccionario
            - Otras columnas adicionales según keys_adicionales
        """
        filas_planas = []

        # Iteramos sobre cada fila (cada símbolo)
        for symbol, row in df.iterrows():
            # Iteramos sobre cada columna (se asume que cada una representa un "side": BI, SE, etc.)
            for side in df.columns:
                celda = row[side]
                # Si la celda es None o una lista vacía, se ignora
                if celda is None or celda == []:
                    continue

                # Si la celda no es una lista, la convertimos en lista para procesarla uniformemente
                if not isinstance(celda, list):
                    celda = [celda]

                # Iteramos sobre cada registro dentro de la celda
                for registro in celda:
                    if isinstance(registro, dict):
                        nueva_fila = {
                            'symbol': symbol,
                            'side': side,
                            'price': registro.get('price', None),
                            'size': registro.get('size', None)
                        }
                        # Si se requieren claves adicionales, se extraen
                        if keys_adicionales:
                            for key in keys_adicionales:
                                nueva_fila[key] = registro.get(key, None)
                        filas_planas.append(nueva_fila)
                    else:
                        # Si el registro no es un diccionario, se almacena el valor en 'size'
                        filas_planas.append({
                            'symbol': symbol,
                            'side': side,
                            'price': None,
                            'size': registro
                        })

        return pd.DataFrame(filas_planas)

    futuros_dff = aplanar_df(futuros_df)
    futuros_dff_last = futuros_dff[(futuros_dff['side'] == 'LA') & (futuros_dff['symbol'].str.len() == 9)]
    futuros_dffa_last = futuros_dff[(futuros_dff['side'] == 'LA') & (futuros_dff['symbol'].str.len() == 10)]

    instrumentos_detallados_df['symbol'] = instrumentos_detallados_df['instrumentId'].apply(
    lambda x: x.get('symbol') if isinstance(x, dict) else None)

    # 2. Seleccionar solo la información que necesitamos para el merge
    instrumentos_vencimientos = instrumentos_detallados_df[['symbol', 'maturityDate']]

    # 3. Realizar el merge
    # Mayorista
    futuros_dffa_last = futuros_dffa_last.merge(instrumentos_vencimientos, on='symbol', how='left')
    futuros_dffa_last["maturityDate"] = pd.to_datetime(futuros_dffa_last["maturityDate"], format="%Y%m%d")
    futuros_dffa_last["days_to_maturity"] = (futuros_dffa_last["maturityDate"] - pd.Timestamp.today()).dt.days
    # Calcular la tasa directa
    futuros_dffa_last["tasa_directa"] = futuros_dffa_last["price"] / a3500_override - 1
    # Calcular la TNA (Tasa Nominal Anual)
    futuros_dffa_last["TNA"] = futuros_dffa_last["tasa_directa"] * (365 / futuros_dffa_last["days_to_maturity"])
    # Calcular la TEA (Tasa Efectiva Anual)
    futuros_dffa_last["TEA"] = (1 + futuros_dffa_last["tasa_directa"])**(365 / futuros_dffa_last["days_to_maturity"]) - 1
    futuros_dffa_last = futuros_dffa_last.sort_values(by="days_to_maturity", ascending=True).reset_index(drop=True)


    # Minorista
    futuros_dff_last = futuros_dff_last.merge(instrumentos_vencimientos, on='symbol', how='left')
    futuros_dff_last["maturityDate"] = pd.to_datetime(futuros_dff_last["maturityDate"], format="%Y%m%d")
    futuros_dff_last["days_to_maturity"] = (futuros_dff_last["maturityDate"] - pd.Timestamp.today()).dt.days
    # Calcular la tasa directa
    futuros_dff_last["tasa_directa"] = futuros_dff_last["price"] / a3500_override - 1
    # Calcular la TNA (Tasa Nominal Anual)
    futuros_dff_last["TNA"] = futuros_dff_last["tasa_directa"] * (365 / futuros_dff_last["days_to_maturity"])
    # Calcular la TEA (Tasa Efectiva Anual)
    futuros_dff_last["TEA"] = (1 + futuros_dff_last["tasa_directa"])**(365 / futuros_dff_last["days_to_maturity"]) - 1
    futuros_dff_last = futuros_dff_last.sort_values(by="days_to_maturity", ascending=True).reset_index(drop=True)

        

    #############################################################
    
    # --- Listas de Símbolos para Bonos ---
    lista_curva_cer = ["T2X5", "T4X5", "TZXM5", "TC25", "TZXY5", "TZX25", "TG25", "TZXO5", 
                       "TX25", "TZXD5", "TX26", "TZXM6", "TZX26", "TZXO6", "TZXD6", "TZXM7", 
                       "TZX27", "TZXD7", "TZX28", "TX28", "DICP", "PARP", "CUAP"]
    
    lista_cer_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_cer]
    lista_cer_ci   = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_cer]
    
    lista_curva_lecap = ["S14F5", "S28F5", "S14M5", "S31M5", "S16A5", "S28A5", "S16Y5", "S30Y5",
                         "S18J5", "S30J5", "S31L5", "S15G5", "S29G5", "S12S5", "S30S5", "T17O5",
                         "S31O5", "S10N5", "T15D5", "T30E6", "T13F6", "TTM26", "TTJ26", "T30J6",
                         "TTS26", "TO26", "TTD26", "T15E7"]
    lista_lecap_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_lecap]
    lista_lecap_ci   = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_lecap]
    
    lista_curva_global = ["GD29", "GD30", "GD35", "GD38", "GD41", "GD46"]
    lista_global_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_global]
    lista_global_ci   = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_global]
    
    # --- Market Data para Bonos (globales) ---
    # Se combinan las listas de símbolos según lo requerido.
    lista_curva_cer_lecap_global = lista_cer_24hs + lista_lecap_24hs + lista_global_24hs + lista_cer_ci + lista_lecap_ci
    mkt_data_global_df = get_market_data_for_symbols(session, lista_curva_cer_lecap_global, market_id="ROFX")
    mkt_data_global_df.to_excel('bymaprices.xlsx')  # Se guarda en Excel si se desea
    print("\nMarket data para curvas combinadas obtenida y guardada en 'bymaprices.xlsx'.")
    
    # Extraer los precios de mercado (Last Price)
    last_px_global_df = extract_last_prices(mkt_data_global_df)
    
    # --- Creación de DataFrames de Precios para Bonos ---
    # Para CER 24hs y LEcap 24hs (se asume que el prefijo y sufijo son "MERV - XMEV - " y " - 24hs")
    cer_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df, prefix="MERV - XMEV - ", suffix=" - 24hs")
    lecap_24hs_prices_df = create_bond_prices_df(lista_lecap_24hs, last_px_global_df, prefix="MERV - XMEV - ", suffix=" - 24hs")
    
    # Calcular las métricas (sin incluir today_str)
    cer_24hs_prices_df = process_bond_dataframe(cer_24hs_prices_df, bond_type='cer', today_str=None, eval_suffix='')
    lecap_24hs_prices_df = process_bond_dataframe(lecap_24hs_prices_df, bond_type='lecap', today_str=None, eval_suffix='')
    
    print("\nMétricas para CER 24hs:")
    print(cer_24hs_prices_df)
    
    print("\nMétricas para LEcap 24hs:")
    print(lecap_24hs_prices_df)
    
    # --- Bonos Proyectados CER 24hs ---
    cerproyectado_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df, prefix="MERV - XMEV - ", suffix=" - 24hs")
    # Se procesa utilizando un sufijo 'j'
    cerproyectado_24hs_prices_df = process_bond_dataframe(cerproyectado_24hs_prices_df, bond_type='cer', today_str=None, eval_suffix='j')
    cerproyectado_24hs_prices_df['Código'] = cerproyectado_24hs_prices_df['Código'] + 'j'
    
    # --- Bonos en Contado Inmediato (CI) ---
    today_str = rentafija.n_dias_laborales(date.today(), 0).strftime("%d/%m/%Y")
    cer_ci_prices_df = create_bond_prices_df(lista_cer_ci, last_px_global_df, prefix="MERV - XMEV - ", suffix=" - CI")
    lecap_ci_prices_df = create_bond_prices_df(lista_lecap_ci, last_px_global_df, prefix="MERV - XMEV - ", suffix=" - CI")
    
    cer_ci_prices_df = process_bond_dataframe(cer_ci_prices_df, bond_type='cer', today_str=today_str, eval_suffix='')
    lecap_ci_prices_df = process_bond_dataframe(lecap_ci_prices_df, bond_type='lecap', today_str=today_str, eval_suffix='')
    
    print("\nMétricas para CER CI:")
    print(cer_ci_prices_df)
    
    print("\nMétricas para LEcap CI:")
    print(lecap_ci_prices_df)
    
    # --- Guardar Resultados en Excel ---
    df_combined = pd.concat([cer_24hs_prices_df, lecap_24hs_prices_df, cerproyectado_24hs_prices_df], ignore_index=True)
    df_combined['fecha_hoy'] = pd.to_datetime('today').date()
    
    # Construir la ruta de archivo (se asume que USERPROFILE existe)
    user_profile = os.environ.get('USERPROFILE', '')
    file_path = os.path.join(user_profile, "DELTA ASSET MANAGEMENT S.A", "Inversiones - Documentos", "Delta Bases", "Delta - historico_byma_px_tasas.xlsx")
    
    respuesta = input("¿Deseas guardar el DataFrame en un archivo Excel? (S/N): ")
    if respuesta.upper() == 'S':
        try:
            df_existente = pd.read_excel(file_path, parse_dates=['fecha_hoy'])
            df_final = pd.concat([df_existente, df_combined], ignore_index=True)
            df_final['fecha_hoy'] = pd.to_datetime(df_final['fecha_hoy']).dt.date
        except FileNotFoundError:
            df_final = df_combined
        df_final.to_excel(file_path, index=False)
        print(f"DataFrame guardado con éxito en '{file_path}'.")
    elif respuesta.upper() == 'N':
        print("No se ha guardado el DataFrame.")
    else:
        print("Respuesta no reconocida. No se ha realizado ninguna acción.")

# %%
