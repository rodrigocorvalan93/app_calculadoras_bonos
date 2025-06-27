# -*- coding: utf-8 -*-
#%% Imports         
import os
from utils import *
from plotter import *
from datetime import date, datetime
import requests
import pandas as pd
import rentafija
from especies import *  # Se asume que este módulo define los objetos bono, etc.


#Rodricor last version
# =============================================================================
# Constantes
# =============================================================================
# BASE_URL = "https://api.cocos.xoms.com.ar/"

BASE_URL = "https://api.latinsecurities.matrizoms.com.ar/"

# =============================================================================
# Funciones de conexión y obtención de datos de la API
# =============================================================================
def login_xoms(username: str, password: str) -> requests.Session:
    """
    Inicia sesión en la API de Cocos y retorna una sesión autenticada.
    """
    session = requests.Session()
    url = BASE_URL + "j_spring_security_check"
    credentials = {"j_username": username, "j_password": password}
    response = session.post(url, data=credentials)
    if response.ok:
        print("Autenticación exitosa en Cocos")
        return session
    else:
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
    Obtiene la descripción detallada de un instrumento desde la API Cocos.

    Parámetros:
      session (requests.Session): Sesión autenticada para realizar la consulta.
      symbol (str): El símbolo del instrumento, por ejemplo "DLR/ABR25".

    Retorna:
      pd.DataFrame: Un DataFrame con una sola fila que contiene la descripción detallada del instrumento.
      
    Ejemplo de uso:
      >>> session = requests.Session()  # O una sesión ya autenticada
      >>> df_instrument = get_instrument_detail(session, "DLR/ABR25")
      >>> print(df_instrument)
    """
    # URL base utilizando el dominio correcto y la ruta "detail" (sin 's')
    url = BASE_URL + "rest/instruments/detail"
    
    # Parámetros para la solicitud GET
    params = {
        "marketId": "ROFX",
        "symbol": symbol
    }
    
    # Realizamos la solicitud GET
    response = session.get(url, params=params)
    
    # Verificamos que la respuesta HTTP sea exitosa (código 200)
    if response.status_code == 200:
        data = response.json()
        # Verificamos que el status de la respuesta sea "OK" y que se incluya la clave "instrument"
        if data.get("status") == "OK" and "instrument" in data:
            instrument_detail = data["instrument"]
            # Convertimos el diccionario a un DataFrame de una sola fila
            df = pd.DataFrame([instrument_detail])
            return df
        else:
            raise ValueError(f"Error en la respuesta de la API: {data}")
    else:
        raise Exception(f"Error HTTP {response.status_code}: {response.text}")

def search_instrument_by_description(instruments_df: pd.DataFrame, description: str) -> pd.DataFrame:
    """
    Retorna las filas cuyo 'securityDescription' coincide exactamente con el valor buscado.
    """
    return instruments_df[instruments_df["securityDescription"] == description]


def get_market_data(session: requests.Session, market_id: str, symbol: str,
                    entries: str = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP", depth: int = 3) -> dict:
    """
    Obtiene datos de mercado para un instrumento dado.
    """
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{BASE_URL}rest/marketdata/get?marketId={market_id}&symbol={symbol_encoded}&entries={entries}&depth={depth}"
    response = session.get(url)
    if response.status_code == 200:
        mkt_dict = response.json()
        if mkt_dict.get("status") != "ERROR":
            data = mkt_dict.get("marketData", {})
            data["symbol"] = symbol
            return data
        else:
            print(f"Error en los datos de mercado para {symbol}")
    else:
        print(f"Error en la solicitud para {symbol}: {response.status_code}")
    return {}

def get_mktdata(session: requests.Session, symbol: str, plazo = 1, prefix: bool = True,
                market_id: str = "ROFX",
                entries: str = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP",
                depth: int = 3) -> dict:
    """
    Obtiene datos de mercado para un instrumento dado. Usable más para un humano tipo rodricor
    
    Args:
        session (requests.Session): Sesión de requests.
        symbol (str): Símbolo del instrumento.
        plazo: Valor que determina el tipo de plazo (1 para "24hs", 0 para "CI", otro para ninguno).
        prefix (bool, optional): Si True, añade un prefijo. Por defecto True.
        market_id (str, optional): ID del mercado. Por defecto "ROFX".
        entries (str, optional): Entradas de datos. Por defecto "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP".
        depth (int, optional): Profundidad de datos. Por defecto 3.
        
    Returns:
        dict: Diccionario con los datos de mercado o vacío en caso de error.
    """
    # Determinar el prefijo y el sufijo según el parámetro 'plazo'
    prefix_str = "MERV - XMEV - " if prefix else ""
    suffix = " - 24hs" if plazo == 1 else " - CI" if plazo == 0 else ""
    
    # Construir y codificar el símbolo
    code = f"{prefix_str}{symbol}{suffix}"
    code_encoded = requests.utils.quote(code)
    
    # Construir la URL de la solicitud
    url = f"{BASE_URL}rest/marketdata/get?marketId={market_id}&symbol={code_encoded}&entries={entries}&depth={depth}"
    response = session.get(url)
    
    if response.ok:
        mkt_dict = response.json()
        if mkt_dict.get("status") != "ERROR":
            data = mkt_dict.get("marketData", {})
            data["symbol"] = symbol
            return data
        else:
            print(f"Error en los datos de mercado para {symbol}")
    else:
        print(f"Error en la solicitud para {symbol}: {response.status_code}")
    return {}

def get_instrumento_detalle(session: requests.Session, symbol: str, prefix=True, plazo=1) -> pd.DataFrame:
    """
    Obtiene la descripción detallada de un instrumento desde la API Cocos y lo devuelve
    en un DataFrame vertical con dos columnas: 'Atributo' y 'Valor'.

    Parámetros:
      session (requests.Session): Sesión autenticada para realizar la consulta.
      symbol (str): El símbolo del instrumento, por ejemplo "DLR/ABR25".
      prefix (bool): Si True, se antepone el prefijo "MERV - XMEV - " al símbolo.
      plazo (int): Si es 1 se añade " - 24hs", si es 0 " - CI", de lo contrario, ningún sufijo.

    Retorna:
      pd.DataFrame: DataFrame vertical con dos columnas: 'Atributo' y 'Valor'.
    """
    url = BASE_URL + "rest/instruments/detail"
    prefix_str = "MERV - XMEV - " if prefix else ""
    suffix = " - 24hs" if plazo == 1 else " - CI" if plazo == 0 else ""
    
    code = f"{prefix_str}{symbol}{suffix}"
    params = {
        "marketId": "ROFX",
        "symbol": code
    }
    
    response = session.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "OK" and "instrument" in data:
            instrument_detail = data["instrument"]
            df = pd.DataFrame([instrument_detail])
            # Transponer y reiniciar el índice sin eliminarlo para obtener dos columnas
            df_vertical = df.transpose().reset_index()
            df_vertical.columns = ['Atributo', 'Valor']
            return df_vertical
        else:
            raise ValueError(f"Error en la respuesta de la API: {data}")
    else:
        raise Exception(f"Error HTTP {response.status_code}: {response.text}")

def get_market_data_for_symbols(session: requests.Session, symbols: list,
                                market_id: str = "ROFX",
                                entries: str = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP", depth: int = 3) -> pd.DataFrame:
    market_data_list = []
    for symbol in symbols:
        data = get_market_data(session, market_id, symbol, entries, depth)
        if data:
            market_data_list.append(data)
    if market_data_list:
        df = pd.DataFrame(market_data_list)
        return df.set_index("symbol")
    return pd.DataFrame()


def extract_last_prices(market_data_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae el 'Last Price' de la entrada 'LA' en los datos de mercado y retorna un DataFrame.
    """
    last_prices = market_data_df["LA"].apply(lambda entry: entry.get("price") if isinstance(entry, dict) else None)
    return pd.DataFrame({"symbol": market_data_df.index, "Last Price": last_prices})


# =============================================================================
# Funciones para cálculos financieros (Bonos)
# =============================================================================
def compute_bond_metrics(bond_code: str, last_price: float, bond_type: str = "lecap",
                         today_str: str = None, eval_suffix: str = "") -> dict:
    """
    Calcula métricas financieras para un bono utilizando eval.

    Retorna un diccionario con: TIREA, TNA, TEM, Paridad, Duration.
    """
    try:
        # Calcular TIREA
        if today_str:
            command_tirea = f"{bond_code}{eval_suffix}.calcula_tirea({last_price}, '{today_str}')"
        else:
            command_tirea = f"{bond_code}{eval_suffix}.calcula_tirea({last_price})"
        tirea = eval(command_tirea)

        bond_obj = eval(bond_code)
        if bond_type.lower() == "lecap":
            tna = rentafija.tir_a_tna(bond_obj.tirea, bond_obj.dias_remanentes, 365)
        elif bond_type.lower() == "cer":
            tna = rentafija.tir_a_tna(bond_obj.tirea, 180, 365)
        elif bond_type.lower() == "dlksob":
            tna = rentafija.tir_a_tna(bond_obj.tirea, bond_obj.dias_remanentes, 365)
        else:
            tna = None

        tem = (1 + tirea) ** (30 / 360) - 1

        paridad = eval(f"{bond_code}{eval_suffix}.paridad")

        if today_str:
            command_duration = f"{bond_code}{eval_suffix}.calcula_duration({bond_code}{eval_suffix}.tirea, '{today_str}')"
        else:
            command_duration = f"{bond_code}{eval_suffix}.calcula_duration({bond_code}{eval_suffix}.tirea)"
        duration = eval(command_duration)

        return {"TIREA": tirea, "TNA": tna, "TEM": tem, "Paridad": paridad, "Duration": duration}
    except Exception as e:
        print(f"Error al procesar {bond_code}: {e}")
        return {"TIREA": None, "TNA": None, "TEM": None, "Paridad": None, "Duration": None}


def process_bond_dataframe(df: pd.DataFrame, bond_type: str = "lecap",
                           today_str: str = None, eval_suffix: str = "") -> pd.DataFrame:
    """
    Procesa un DataFrame con precios de bonos (debe tener las columnas 'Código' y 'Last Price')
    y agrega las métricas calculadas.
    """
    def calcular_metricas(row):
        if pd.notnull(row["Last Price"]):
            # Se asume que el precio viene multiplicado por 100
            price = row["Last Price"] / 100
            return compute_bond_metrics(row["Código"], price, bond_type, today_str, eval_suffix)
        return {"TIREA": None, "TNA": None, "TEM": None, "Paridad": None, "Duration": None}

    metrics = df.apply(calcular_metricas, axis=1, result_type="expand")
    df = pd.concat([df, metrics], axis=1)

    # Formatear las tasas a porcentaje
    for col in ["TEM", "TNA", "TIREA"]:
        df[col] = df[col].apply(lambda x: f"{x:.2%}" if isinstance(x, (float, int)) else None)

    # Calcular spread entre TEM (si procede)
    try:
        df["tem_spread"] = df["TEM"].str.rstrip("%").astype(float).diff().fillna(0)
        df["tem_spread"] = df["tem_spread"].apply(lambda x: f"{x:.2f}%")
    except Exception as e:
        print(f"Error al calcular tem_spread: {e}")
        df["tem_spread"] = None

    return df


def create_bond_prices_df(full_symbols: list, last_prices_df: pd.DataFrame,
                          prefix: str = "MERV - XMEV - ", suffix: str = " - 24hs") -> pd.DataFrame:
    """
    A partir de una lista de símbolos completos y el DataFrame con los Last Prices,
    crea un DataFrame con las columnas: 'symbol', 'Código' y 'Last Price'.
    """
    records = []
    for symbol in full_symbols:
        codigo = symbol.replace(prefix, "").replace(suffix, "")
        match = last_prices_df[last_prices_df["symbol"] == symbol]
        price = match.iloc[0]["Last Price"] if not match.empty else None
        records.append({"symbol": symbol, "Código": codigo, "Last Price": price})
    return pd.DataFrame(records)


# =============================================================================
# Función para "aplanar" DataFrame de datos anidados
# =============================================================================
def aplanar_df(df: pd.DataFrame, keys_adicionales: list = None) -> pd.DataFrame:
    """
    Convierte un DataFrame con datos anidados (por ejemplo, BI, SE, LA, OI, OF)
    en uno "plano" donde cada fila es una cotización individual.
    """
    filas_planas = []
    for symbol, row in df.iterrows():
        for side in df.columns:
            celda = row[side]
            if celda is None or celda == []:
                continue
            # Convertir a lista si no lo es
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
                    filas_planas.append({
                        "symbol": symbol,
                        "side": side,
                        "price": None,
                        "size": registro
                    })
    return pd.DataFrame(filas_planas)


# =============================================================================
# Funciones auxiliares para procesar datos de futuros
# =============================================================================
def process_future_data(df: pd.DataFrame, symbol_length: int,
                        instrumentos_vencimientos: pd.DataFrame,
                        a3500_override: float) -> pd.DataFrame:
    """
    Filtra y procesa datos de futuros (por ejemplo, de mayoristas o minoristas) según la longitud del símbolo.
    Se realiza el merge con la información de vencimientos y se calculan las tasas.
    """
    df_filtered = df[(df["side"] == "LA") & (df["symbol"].str.len() == symbol_length)].copy()
    df_filtered = df_filtered.merge(instrumentos_vencimientos, on="symbol", how="left")
    df_filtered["maturityDate"] = pd.to_datetime(df_filtered["maturityDate"], format="%Y%m%d")
    df_filtered["days_to_maturity"] = (pd.Timestamp.today() - df_filtered["maturityDate"]).dt.days * -1  # días restantes
    df_filtered["tasa_directa"] = df_filtered["price"] / a3500_override - 1
    df_filtered["TNA"] = df_filtered["tasa_directa"] * (365 / df_filtered["days_to_maturity"])
    df_filtered["TEA"] = (1 + df_filtered["tasa_directa"]) ** (365 / df_filtered["days_to_maturity"]) - 1
    df_filtered = df_filtered.sort_values(by="days_to_maturity", ascending=True).reset_index(drop=True)
    return df_filtered



def calcula_tipo_de_cambio(bono, fx, plazo, postura, session):
    """
    Calcula el tipo de cambio implícito para un bono dado.

    Parámetros:
      bono (str): Por ejemplo, "TX26", "AL30", etc.
      fx (str): "CCL" o "MEP".  
                - Si es "CCL" se usará el sufijo "C" para identificar el bono en dólares.
                - Si es "MEP" se usará el sufijo "D".
      plazo (str): "CI" (t+0) o "24hs" (t+1).
      postura (str): Define qué precios usar:
                     - "LAST": utiliza el último precio ('LA') para ambos lados.
                     - "BI": utiliza el precio BID para el bono en pesos (numerador)
                             y el precio OFFER para el bono en dólares (denominador).
                     - "OF": utiliza el precio OFFER para el bono en pesos (numerador)
                             y el precio BID para el bono en dólares (denominador).
      session: Objeto de sesión que requiere la función get_market_data.

    Retorna:
      float: El tipo de cambio implícito calculado.

    Ejemplos:
      >>> calcula_tipo_de_cambio("TX26", "CCL", "CI", "LAST", session)
         # Calcula:
         # CCL_TX26_LAST_CI = get_market_data(session, "ROFX", "MERV - XMEV - TX26 - CI")['LA']['price']
         #                    / get_market_data(session, "ROFX", "MERV - XMEV - TX26C - CI")['LA']['price']
      
      >>> calcula_tipo_de_cambio("AL30", "MEP", "24hs", "OF", session)
         # Calcula:
         # MEP_AL30_OF_24hs = get_market_data(session, "ROFX", "MERV - XMEV - AL30 - 24hs")['OF'][0]['price']
         #                    / get_market_data(session, "ROFX", "MERV - XMEV - AL30D - 24hs")['BI'][0]['price']
    """
    # Convertir los parámetros a mayúsculas para evitar inconsistencias.
    fx = fx.upper()
    plazo = plazo.upper()
    postura = postura.upper()

    # Determinar el sufijo según el tipo de FX:
    # Si fx es "CCL", usamos "C"; si es "MEP", usamos "D".
    if fx == "CCL":
        sufijo = "C"
    elif fx == "MEP":
        sufijo = "D"
    else:
        raise ValueError("El parámetro fx debe ser 'CCL' o 'MEP'")

    # Construir los símbolos de mercado para el bono en pesos (numerador)
    # y para el bono en dólares (denominador).
    # Ejemplo: bono = "TX26", plazo = "CI"
    #         simbolo_numerador -> "MERV - XMEV - TX26 - CI"
    #         simbolo_denominador -> "MERV - XMEV - TX26C - CI"  (si fx == "CCL")
    simbolo_numerador = f"MERV - XMEV - {bono} - {plazo}"
    simbolo_denominador = f"MERV - XMEV - {bono}{sufijo} - {plazo}"

    # Obtener los datos de mercado para ambos símbolos.
    data_num = get_market_data(session, "ROFX", simbolo_numerador)
    data_den = get_market_data(session, "ROFX", simbolo_denominador)

    # Validar que se hayan obtenido datos correctamente.
    if data_num is None:
        raise ValueError(f"No se encontraron datos para el símbolo: {simbolo_numerador}")
    if data_den is None:
        raise ValueError(f"No se encontraron datos para el símbolo: {simbolo_denominador}")

    # Según la postura, extraemos los precios correspondientes:
    if postura == "LAST":
        # Se utiliza el precio 'LA' (último) para ambos lados.
        precio_num = data_num.get('LA', {}).get('price')
        precio_den = data_den.get('LA', {}).get('price')
    elif postura == "BI":
        # Se usa el primer precio del bid para el bono en pesos (numerador)
        # y el primer precio de la offer para el bono en dólares (denominador).
        precio_num = data_num.get("BI", [{}])[0].get('price')
        precio_den = data_den.get("OF", [{}])[0].get('price')
    elif postura == "OF":
        # Se usa el primer precio de la offer para el bono en pesos (numerador)
        # y el primer precio del bid para el bono en dólares (denominador).
        precio_num = data_num.get("OF", [{}])[0].get('price')
        precio_den = data_den.get("BI", [{}])[0].get('price')
    else:
        raise ValueError("El parámetro postura debe ser 'LAST', 'BI' o 'OF'")

    # Validar que se hayan obtenido los precios correctamente.
    if precio_num is None:
        raise ValueError(f"No se encontró el precio en el símbolo: {simbolo_numerador} para la postura {postura}")
    if precio_den is None:
        raise ValueError(f"No se encontró el precio en el símbolo: {simbolo_denominador} para la postura {postura}")

    # Retornar el tipo de cambio implícito (división del precio del bono en pesos por el precio del bono en dólares)
    return precio_num / precio_den

def estimate_usd_volume(
    volume_gd30_ars: float, 
    price_gd30_ars: float, 
    volume_gd30d_usd: float, 
    price_gd30d_usd: float
) -> dict:
    """
    Estima el volumen que podría corresponder a operaciones MEP 
    a partir de los datos de GD30 y GD30D.
    
    Parámetros:
    -----------
    volume_gd30_ars : float
        Volumen operado de GD30 en ARS (por ejemplo, importe total).
    price_gd30_ars : float
        Precio promedio (o de cierre) de GD30 en ARS por nominal.
    volume_gd30d_usd : float
        Volumen operado de GD30D en USd/C.
    price_gd30d_usd : float
        Precio promedio (o de cierre) de GD30D/C en USD/C por nominal.
    
    Retorno:
    --------
    dict
        Diccionario con:
        - "nominal_usd" : float, mínimo de nominales potencialmente usados en MEP.
        - "mep_ccl_ars"     : float, estimación del volumen en ARS involucrado.
        - "mep_ccl_usd"     : float, estimación del volumen en USD involucrado.
    
    Observación:
    ------------
    Este cálculo es un "proxy" y NO representa con exactitud el flujo real
    de dólares comprados o vendidos. Solo sirve para dar una idea de la 
    porción de volumen potencialmente utilizada en arbitraje MEP/USD.
    """
    
    # Nominales teóricos de GD30 (en base al volumen ARS dividido por su precio)
    nominal_gd30 = volume_gd30_ars / price_gd30_ars
    
    # Nominales teóricos de GD30D (en base al volumen USD dividido por su precio)
    nominal_gd30d = volume_gd30d_usd / price_gd30d_usd
    
    # Cantidad mínima de nominales que "podría" haberse usado para MEP
    nominal_mep_ccl = min(nominal_gd30, nominal_gd30d)
    
    # Conversión de ese mínimo de nominales a pesos y dólares
    mep_ccl_ars = nominal_mep_ccl * price_gd30_ars
    mep_ccl_usd = nominal_mep_ccl * price_gd30d_usd
    
    return {
        "nominal_mep_ccl": round(nominal_mep_ccl,2),
        "mep_ccl_ars": round(mep_ccl_ars,2),
        "mep_ccl_usd": round(mep_ccl_usd,2)
    }

# =============================================================================
# Funciones para formateo y guardado de Excel
# =============================================================================

def guardar_excel(df: pd.DataFrame, file_path: str) -> None:
    """
    Guarda el DataFrame en un archivo Excel, concatenando con datos existentes si el archivo ya existe.
    """
    for col in ['TIREA', 'TNA', 'TEM', 'tem_spread']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('%', '').str.replace(',', '.').str.strip(), errors='coerce') / 100
    try:
        if os.path.exists(file_path):
            df_existente = pd.read_excel(file_path, parse_dates=["fecha_hoy"])
            df_existente["fecha_hoy"] = pd.to_datetime(df_existente["fecha_hoy"]).dt.date
            df_final = pd.concat([df_existente, df], ignore_index=True)
        else:
            df_final = df

        # Modificaciones finales
        df_last = df_final.drop_duplicates(subset = ['symbol', 'Código', 'fecha_hoy'], keep='last')
        df_last = df_last.dropna(subset=['Last Price', 'TIREA', 'TNA', 'TEM', 'Paridad', 'Duration'])
        df_last['Proy'] = np.where(df_last['Código'].str.endswith('j'), 1, 0)
        for col in ['TIREA', 'TNA', 'TEM']:
            df_last[col].replace('nan%', '', inplace=True)
        df_last.to_excel(file_path, index=False)
        print(f"DataFrame guardado con éxito en '{file_path}'.")

    except Exception as e:
        print(f"Error al guardar el archivo: {e}")


# =============================================================================
# Bloque Principal (Main)
# =============================================================================
#%% Refresh Main

def main():
    # --- Variables que queden en memoria global ---
    global lecap_24hs_prices_df, lecap_ci_prices_df, cer_ci_prices_df, cer_24hs_prices_df, mkt_data_global_df, cerproyectado_24hs_prices_df, fx_resumen, fx_resumen_styled, futuros_minorista, futuros_mayorista, futuros_df, dlksob_24hs_prices_df, session

    # --- Autenticación ---
    #username = "37376293"
    #password = "ZEfM77iQ_"
    username = "delta_api"
    password = "D3lt41210*-*"

    session = login_xoms(username, password)

    # --- Obtención de datos básicos ---
    segments_df = get_segments(session)
    print("Segmentos:")
    print(segments_df)

    instruments_df, instruments_df2 = get_instruments(session)
    instrumentos_detallados_df = get_instruments_details(session)

    # Ejemplo de búsqueda por descripción  BUSCADOR DESC!
    search_description = "MERV - XMEV - TX26 - 24hs"
    resultado_busqueda = search_instrument_by_description(instrumentos_detallados_df, search_description)
    #print("\nResultado de búsqueda por descripción:")
    #print(resultado_busqueda)

    # --- Market Data para Futuros ---
    # Se filtran instrumentos con underlying 'Dólar USA A3500'
    futuros_market_data = []
    df_filtrado = instrumentos_detallados_df[instrumentos_detallados_df["underlying"] == "Dólar USA A3500"]
    # Se asume que 'instrumentId' es un diccionario con keys 'marketId' y 'symbol'
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
        #print(futuros_df)
    else:
        print("No se obtuvieron datos de mercado para futuros.")

    # --- Aplanar el DataFrame de futuros ---
    futuros_dff = aplanar_df(futuros_df)
    # Se pueden filtrar distintos grupos (por ejemplo, según la longitud del símbolo)
    futuros_dff_minorista = futuros_dff[(futuros_dff["side"] == "LA") & (futuros_dff["symbol"].str.len() == 9)]
    futuros_dff_mayorista = futuros_dff[(futuros_dff["side"] == "LA") & (futuros_dff["symbol"].str.len() == 10)]

    # Se extrae la columna 'symbol' de los instrumentos detallados para realizar merge con vencimientos
    instrumentos_detallados_df["symbol"] = instrumentos_detallados_df["instrumentId"].apply(
        lambda x: x.get("symbol") if isinstance(x, dict) else None)
    instrumentos_vencimientos = instrumentos_detallados_df[["symbol", "maturityDate"]]

    # Se asume que 'a3500_override' está definido (debe provenir de alguna configuración o módulo)
    # Ejemplo: a3500_override = 3500.0 CORREGIR
    #a3500_override = 1056.75

    # Procesar datos de futuros (mayoristas y minoristas)
    futuros_mayorista = process_future_data(futuros_dff_mayorista, symbol_length=10,
                                            instrumentos_vencimientos=instrumentos_vencimientos,
                                            a3500_override=a3500_override)
    futuros_minorista = process_future_data(futuros_dff_minorista, symbol_length=9,
                                            instrumentos_vencimientos=instrumentos_vencimientos,
                                            a3500_override=a3500_override)
    # Se pueden imprimir o guardar estos DataFrames según convenga
    # print(futuros_mayorista)
    # print(futuros_minorista)

    # --- Preparación de listas de símbolos para Bonos ---
    lista_curva_cer = ["TZX25", "TZXO5",
                        "TX25", "TZXD5", "TX26", "TZXM6", "TZX26", "TZXO6", "TZXD6", "TZXM7",
                        "TZX27", "TZXD7", "TZX28", "TX28", "DICP", "PARP", "CUAP"]
    lista_cer_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_cer]
    lista_cer_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_cer]

    lista_curva_lecap = ["S30J5","S10L5", "S31L5", "S15G5", "S29G5", "S12S5", "S30S5", "T17O5",
                        "S31O5", "S10N5", "S28N5", "T15D5", "T30E6", "T13F6", "TTM26", "S29Y6", "TTJ26", "T30J6",
                        "TTS26", "TO26", "TTD26", "T15E7","TY30P"]
    lista_lecap_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_lecap]
    lista_lecap_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_lecap]

    lista_curva_global = ["GD29", "GD30", "GD35", "GD38", "GD41", "GD46"]
    lista_global_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_global]
    lista_global_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_global]


    lista_curva_dlksob = ["TZV25", "TZVD5", "D16E6", "TZV26"]
    lista_dlksob_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_dlksob]



    # Combinar las listas para obtener los símbolos que se consultarán
    lista_curva_cer_lecap_global_dlk = lista_cer_24hs + lista_lecap_24hs + lista_global_24hs + lista_cer_ci + lista_lecap_ci + lista_dlksob_24hs

    # --- Market Data para Bonos ---
    mkt_data_global_df = get_market_data_for_symbols(session, lista_curva_cer_lecap_global_dlk, market_id="ROFX")
    # Se guarda en Excel (archivo temporal o para depuración)
    mkt_data_global_df.to_excel("bymaprices.xlsx")
    print("\nMarket data para curvas combinadas obtenida y guardada en 'bymaprices.xlsx'.")

    # Extraer los precios de mercado (Last Price)
    last_px_global_df = extract_last_prices(mkt_data_global_df)

    # --- Creación de DataFrames de Precios para Bonos ---
    cer_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df,
                                                prefix="MERV - XMEV - ", suffix=" - 24hs")
    lecap_24hs_prices_df = create_bond_prices_df(lista_lecap_24hs, last_px_global_df,
                                                prefix="MERV - XMEV - ", suffix=" - 24hs")
    dlksob_24hs_prices_df = create_bond_prices_df(lista_dlksob_24hs, last_px_global_df,
                                                prefix="MERV - XMEV - ", suffix=" - 24hs")

    # Calcular las métricas para bonos (sin today_str para 24hs)
    cer_24hs_prices_df = process_bond_dataframe(cer_24hs_prices_df, bond_type="cer", today_str=None, eval_suffix="")
    lecap_24hs_prices_df = process_bond_dataframe(lecap_24hs_prices_df, bond_type="lecap", today_str=None, eval_suffix="")
    dlksob_24hs_prices_df = process_bond_dataframe(dlksob_24hs_prices_df, bond_type="dlksob", today_str=None, eval_suffix="")

    print("\nMétricas para CER 24hs:")
    print(cer_24hs_prices_df)
    print("\nMétricas para Lecap 24hs:")
    print(lecap_24hs_prices_df)

    # --- Bonos Proyectados CER 24hs (sufijo 'j') ---
    cerproyectado_24hs_prices_df = create_bond_prices_df(lista_cer_24hs, last_px_global_df,
                                                        prefix="MERV - XMEV - ", suffix=" - 24hs")
    cerproyectado_24hs_prices_df = process_bond_dataframe(cerproyectado_24hs_prices_df,
                                                        bond_type="cer", today_str=None, eval_suffix="j")
    cerproyectado_24hs_prices_df["Código"] = cerproyectado_24hs_prices_df["Código"] + "j"

    # --- Bonos en Contado Inmediato (CI) ---
    today_str = rentafija.n_dias_laborales(date.today(), 0).strftime("%d/%m/%Y")
    cer_ci_prices_df = create_bond_prices_df(lista_cer_ci, last_px_global_df,
                                            prefix="MERV - XMEV - ", suffix=" - CI")
    lecap_ci_prices_df = create_bond_prices_df(lista_lecap_ci, last_px_global_df,
                                            prefix="MERV - XMEV - ", suffix=" - CI")

    cer_ci_prices_df = process_bond_dataframe(cer_ci_prices_df, bond_type="cer", today_str=today_str, eval_suffix="")
    lecap_ci_prices_df = process_bond_dataframe(lecap_ci_prices_df, bond_type="lecap", today_str=today_str, eval_suffix="")

    print("\nMétricas para CER CI:")
    print(cer_ci_prices_df)
    print("\nMétricas para Lecap CI:")
    print(lecap_ci_prices_df)

    # --- Guardar resultados combinados en Excel ---
    df_combined = pd.concat([cer_24hs_prices_df, lecap_24hs_prices_df, cerproyectado_24hs_prices_df], ignore_index=True)
    df_combined["fecha_hoy"] = datetime.today().date()

    # Construir la ruta de archivo (se asume que la variable de entorno USERPROFILE existe)
    user_profile = os.environ.get("USERPROFILE", "")
    file_path = os.path.join(user_profile, "DELTA ASSET MANAGEMENT S.A", "Inversiones - Documentos",
                            "Delta Bases", "Delta - historico_byma_px_tasas.xlsx")
    
    respuesta = input("¿Deseas guardar el DataFrame en un archivo Excel? (S/N): ").strip().upper()
    if respuesta == "S":
        guardar_excel(df_combined, file_path)
    elif respuesta == "N":
        print("No se ha guardado el DataFrame.")
    else:
        print("Respuesta no reconocida. No se ha realizado ninguna acción.")
    # Tipos de cambio - USD
    data_al30_ci   = get_market_data(session,"ROFX","MERV - XMEV - AL30 - CI")
    data_al30c_ci  = get_market_data(session,"ROFX","MERV - XMEV - AL30C - CI")
    data_gd30_ci   = get_market_data(session,"ROFX","MERV - XMEV - GD30 - CI")
    data_gd30c_ci  = get_market_data(session,"ROFX","MERV - XMEV - GD30C - CI")
    data_al30d_ci  = get_market_data(session,"ROFX","MERV - XMEV - AL30D - CI")
    data_gd30d_ci  = get_market_data(session,"ROFX","MERV - XMEV - GD30D - CI")
    data_al30_24hs   = get_market_data(session,"ROFX","MERV - XMEV - AL30 - 24hs")
    data_al30c_24hs  = get_market_data(session,"ROFX","MERV - XMEV - AL30C - 24hs")
    data_gd30_24hs   = get_market_data(session,"ROFX","MERV - XMEV - GD30 - 24hs")
    data_gd30c_24hs  = get_market_data(session,"ROFX","MERV - XMEV - GD30C - 24hs")
    data_al30d_24hs  = get_market_data(session,"ROFX","MERV - XMEV - AL30D - 24hs")
    data_gd30d_24hs  = get_market_data(session,"ROFX","MERV - XMEV - GD30D - 24hs")




    
    #CCL

    CCL_AL30_LAST_CI = safe_div(
        data_al30_ci['LA'].get('price') if data_al30_ci.get('LA') else None,
        data_al30c_ci['LA'].get('price') if data_al30c_ci.get('LA') else None
    )

    CCL_GD30_LAST_CI = safe_div(
        data_gd30_ci['LA'].get('price') if data_gd30_ci.get('LA') else None,
        data_gd30c_ci['LA'].get('price') if data_gd30c_ci.get('LA') else None
    )
    CCL_GD30_BI_CI = safe_div(
        data_gd30_ci['BI'][0].get('price') if data_gd30_ci.get('BI') and len(data_gd30_ci['BI']) > 0 else None,
        data_gd30c_ci['OF'][0].get('price') if data_gd30c_ci.get('OF') and len(data_gd30c_ci['OF']) > 0 else None
    )

    CCL_AL30_BI_CI = safe_div(
        data_al30_ci['BI'][0].get('price') if data_al30_ci.get('BI') and len(data_al30_ci['BI']) > 0 else None,
        data_al30c_ci['OF'][0].get('price') if data_al30c_ci.get('OF') and len(data_al30c_ci['OF']) > 0 else None
    )

    CCL_AL30_OF_CI = safe_div(
        data_al30_ci['OF'][0].get('price') if data_al30_ci.get('OF') and len(data_al30_ci['OF']) > 0 else None,
        data_al30c_ci['BI'][0].get('price') if data_al30c_ci.get('BI') and len(data_al30c_ci['BI']) > 0 else None
    )

    CCL_GD30_OF_CI = safe_div(
        data_gd30_ci['OF'][0].get('price') if data_gd30_ci.get('OF') and len(data_gd30_ci['OF']) > 0 else None,
        data_gd30c_ci['BI'][0].get('price') if data_gd30c_ci.get('BI') and len(data_gd30c_ci['BI']) > 0 else None
    )

    CCL_AL30_LAST_24hs = safe_div(
        data_al30_24hs['LA'].get('price') if data_al30_24hs.get('LA') else None,
        data_al30c_24hs['LA'].get('price') if data_al30c_24hs.get('LA') else None
    )

    CCL_GD30_LAST_24hs = safe_div(
        data_gd30_24hs['LA'].get('price') if data_gd30_24hs.get('LA') else None,
        data_gd30c_24hs['LA'].get('price') if data_gd30c_24hs.get('LA') else None
    )

    CCL_AL30_BI_24hs = safe_div(
        data_al30_24hs['BI'][0].get('price') if data_al30_24hs.get('BI') and len(data_al30_24hs['BI']) > 0 else None,
        data_al30c_24hs['OF'][0].get('price') if data_al30c_24hs.get('OF') and len(data_al30c_24hs['OF']) > 0 else None
    )

    CCL_GD30_BI_24hs = safe_div(
        data_gd30_24hs['BI'][0].get('price') if data_gd30_24hs.get('BI') and len(data_gd30_24hs['BI']) > 0 else None,
        data_gd30c_24hs['OF'][0].get('price') if data_gd30c_24hs.get('OF') and len(data_gd30c_24hs['OF']) > 0 else None
    )

    CCL_AL30_OF_24hs = safe_div(
        data_al30_24hs['OF'][0].get('price') if data_al30_24hs.get('OF') and len(data_al30_24hs['OF']) > 0 else None,
        data_al30c_24hs['BI'][0].get('price') if data_al30c_24hs.get('BI') and len(data_al30c_24hs['BI']) > 0 else None
    )

    CCL_GD30_OF_24hs = safe_div(
        data_gd30_24hs['OF'][0].get('price') if data_gd30_24hs.get('OF') and len(data_gd30_24hs['OF']) > 0 else None,
        data_gd30c_24hs['BI'][0].get('price') if data_gd30c_24hs.get('BI') and len(data_gd30c_24hs['BI']) > 0 else None
    )


    # MEP
    MEP_AL30_LAST_CI = safe_div(
        data_al30_ci['LA'].get('price') if data_al30_ci.get('LA') else None,
        data_al30d_ci['LA'].get('price') if data_al30d_ci.get('LA') else None
    )

    MEP_GD30_LAST_CI = safe_div(
        data_gd30_ci['LA'].get('price') if data_gd30_ci.get('LA') else None,
        data_gd30d_ci['LA'].get('price') if data_gd30d_ci.get('LA') else None
    )

    MEP_AL30_BI_CI = safe_div(
        data_al30_ci['BI'][0].get('price') if data_al30_ci.get('BI') and len(data_al30_ci['BI']) > 0 else None,
        data_al30d_ci['OF'][0].get('price') if data_al30d_ci.get('OF') and len(data_al30d_ci['OF']) > 0 else None
    )

    MEP_GD30_BI_CI = safe_div(
        data_gd30_ci['BI'][0].get('price') if data_gd30_ci.get('BI') and len(data_gd30_ci['BI']) > 0 else None,
        data_gd30d_ci['OF'][0].get('price') if data_gd30d_ci.get('OF') and len(data_gd30d_ci['OF']) > 0 else None
    )

    MEP_AL30_OF_CI = safe_div(
        data_al30_ci['OF'][0].get('price') if data_al30_ci.get('OF') and len(data_al30_ci['OF']) > 0 else None,
        data_al30d_ci['BI'][0].get('price') if data_al30d_ci.get('BI') and len(data_al30d_ci['BI']) > 0 else None
    )

    MEP_GD30_OF_CI = safe_div(
        data_gd30_ci['OF'][0].get('price') if data_gd30_ci.get('OF') and len(data_gd30_ci['OF']) > 0 else None,
        data_gd30d_ci['BI'][0].get('price') if data_gd30d_ci.get('BI') and len(data_gd30d_ci['BI']) > 0 else None
    )

    MEP_AL30_LAST_24hs = safe_div(
        data_al30_24hs['LA'].get('price') if data_al30_24hs.get('LA') else None,
        data_al30d_24hs['LA'].get('price') if data_al30d_24hs.get('LA') else None
    )

    MEP_GD30_LAST_24hs = safe_div(
        data_gd30_24hs['LA'].get('price') if data_gd30_24hs.get('LA') else None,
        data_gd30d_24hs['LA'].get('price') if data_gd30d_24hs.get('LA') else None
    )

    MEP_AL30_BI_24hs = safe_div(
        data_al30_24hs['BI'][0].get('price') if data_al30_24hs.get('BI') and len(data_al30_24hs['BI']) > 0 else None,
        data_al30d_24hs['OF'][0].get('price') if data_al30d_24hs.get('OF') and len(data_al30d_24hs['OF']) > 0 else None
    )

    MEP_GD30_BI_24hs = safe_div(
        data_gd30_24hs['BI'][0].get('price') if data_gd30_24hs.get('BI') and len(data_gd30_24hs['BI']) > 0 else None,
        data_al30d_24hs['OF'][0].get('price') if data_al30d_24hs.get('OF') and len(data_al30d_24hs['OF']) > 0 else None
    )

    MEP_AL30_OF_24hs = safe_div(
        data_al30_24hs['OF'][0].get('price') if data_al30_24hs.get('OF') and len(data_al30_24hs['OF']) > 0 else None,
        data_al30d_24hs['BI'][0].get('price') if data_al30d_24hs.get('BI') and len(data_al30d_24hs['BI']) > 0 else None
    )

    MEP_GD30_OF_24hs = safe_div(
        data_gd30_24hs['OF'][0].get('price') if data_gd30_24hs.get('OF') and len(data_gd30_24hs['OF']) > 0 else None,
        data_gd30d_24hs['BI'][0].get('price') if data_gd30d_24hs.get('BI') and len(data_gd30d_24hs['BI']) > 0 else None
    )


    #### cierres fx ####
    # CCL
    CCL_AL30_CL_CI = safe_div(
        data_al30_ci['CL'].get('price') if data_al30_ci.get('CL') else None,
        data_al30c_ci['CL'].get('price') if data_al30c_ci.get('CL') else None
    )

    CCL_GD30_CL_CI = safe_div(
        data_gd30_ci['CL'].get('price') if data_gd30_ci.get('CL') else None,
        data_gd30c_ci['CL'].get('price') if data_gd30c_ci.get('CL') else None
    )

    CCL_AL30_CL_24hs = safe_div(
        data_al30_24hs['CL'].get('price') if data_al30_24hs.get('CL') else None,
        data_al30c_24hs['CL'].get('price') if data_al30c_24hs.get('CL') else None
    )

    CCL_GD30_CL_24hs = safe_div(
        data_gd30_24hs['CL'].get('price') if data_gd30_24hs.get('CL') else None,
        data_gd30c_24hs['CL'].get('price') if data_gd30c_24hs.get('CL') else None
    )

    # MEP
    MEP_AL30_CL_CI = safe_div(
        data_al30_ci['CL'].get('price') if data_al30_ci.get('CL') else None,
        data_al30d_ci['CL'].get('price') if data_al30d_ci.get('CL') else None
    )

    MEP_GD30_CL_CI = safe_div(
        data_gd30_ci['CL'].get('price') if data_gd30_ci.get('CL') else None,
        data_gd30d_ci['CL'].get('price') if data_gd30d_ci.get('CL') else None
    )

    MEP_AL30_CL_24hs = safe_div(
        data_al30_24hs['CL'].get('price') if data_al30_24hs.get('CL') else None,
        data_al30d_24hs['CL'].get('price') if data_al30d_24hs.get('CL') else None
    )

    MEP_GD30_CL_24hs = safe_div(
        data_gd30_24hs['CL'].get('price') if data_gd30_24hs.get('CL') else None,
        data_gd30d_24hs['CL'].get('price') if data_gd30d_24hs.get('CL') else None
    )

    ### variaciones fx ####
    #CCL
    CCL_GD30_VAR_CI     = safe_div(CCL_GD30_LAST_CI      , CCL_GD30_CL_CI)   - 1
    CCL_AL30_VAR_CI     = safe_div(CCL_AL30_LAST_CI      , CCL_AL30_CL_CI)   - 1
    CCL_GD30_VAR_24hs   = safe_div(CCL_GD30_LAST_24hs    , CCL_GD30_CL_24hs) - 1
    CCL_AL30_VAR_24hs   = safe_div(CCL_AL30_LAST_24hs    , CCL_AL30_CL_24hs) - 1
    #MEP
    MEP_GD30_VAR_CI     = safe_div(MEP_GD30_LAST_CI      , MEP_GD30_CL_CI)   - 1
    MEP_AL30_VAR_CI     = safe_div(MEP_AL30_LAST_CI      , MEP_AL30_CL_CI)   - 1
    MEP_GD30_VAR_24hs   = safe_div(MEP_GD30_LAST_24hs    , MEP_GD30_CL_24hs) - 1
    MEP_AL30_VAR_24hs   = safe_div(MEP_AL30_LAST_24hs    , MEP_AL30_CL_24hs) - 1

    # Cuadro resumen

    # Se arma un diccionario con la información para cada instrumento y timeframe.
    fx = {
        'Instrumento': ['AL30', 'AL30', 'GD30', 'GD30'],
        'TimeFrame': ['CI', '24hs', 'CI', '24hs'],
        # Valores CCL:
        'CCL_LAST': [CCL_AL30_LAST_CI,   CCL_AL30_LAST_24hs,   CCL_GD30_LAST_CI,   CCL_GD30_LAST_24hs],
        'CCL_BID': [CCL_AL30_BI_CI,     CCL_AL30_BI_24hs,     CCL_GD30_BI_CI,     CCL_GD30_BI_24hs],
        'CCL_OFFER': [CCL_AL30_OF_CI,     CCL_AL30_OF_24hs,     CCL_GD30_OF_CI,     CCL_GD30_OF_24hs],
        'CCL_CLOSE': [CCL_AL30_CL_CI,     CCL_AL30_CL_24hs,     CCL_GD30_CL_CI,     CCL_GD30_CL_24hs],
        'CCL_VAR': [CCL_AL30_VAR_CI,   CCL_AL30_VAR_24hs,    CCL_GD30_VAR_CI,    CCL_GD30_VAR_24hs],
        'CCL_VOL': [data_al30c_ci['EV'],
                    data_al30c_24hs['EV'],
                    data_gd30c_ci['EV'],
                    data_gd30c_24hs['EV']],
        # Valores MEP:
        'MEP_LAST': [MEP_AL30_LAST_CI,   MEP_AL30_LAST_24hs,   MEP_GD30_LAST_CI,   MEP_GD30_LAST_24hs],
        'MEP_BID': [MEP_AL30_BI_CI,     MEP_AL30_BI_24hs,     MEP_GD30_BI_CI,     MEP_GD30_BI_24hs],
        'MEP_OFFFER': [MEP_AL30_OF_CI,     MEP_AL30_OF_24hs,     MEP_GD30_OF_CI,     MEP_GD30_OF_24hs],
        'MEP_CLOSE': [MEP_AL30_CL_CI,     MEP_AL30_CL_24hs,     MEP_GD30_CL_CI,     MEP_GD30_CL_24hs],
        'MEP_VAR': [MEP_AL30_VAR_CI,   MEP_AL30_VAR_24hs,    MEP_GD30_VAR_CI,    MEP_GD30_VAR_24hs],
        'MEP_VOL': [data_al30d_ci['EV'],
                    data_al30d_24hs['EV'],
                    data_gd30d_ci['EV'],
                    data_gd30d_24hs['EV']],
    }
    fx_resumen = pd.DataFrame(fx)

    # 3. Crear un diccionario de formatos para aplicar el redondeo solo a las columnas numéricas:
    numeric_cols = fx_resumen.select_dtypes(include=["number"]).columns
    format_dict = {col: "{:,.4f}" for col in numeric_cols}

    # 4. Aplicar el formato y el estilo condicional a las columnas de variación:
    fx_resumen_styled = (
        fx_resumen.style
        .format(format_dict)  # Aplica formato únicamente a columnas numéricas
        .applymap(color_variation, subset=['CCL_VAR', 'MEP_VAR'])  # Colorea las variaciones
    )
    print("\nResumen FX CCL y MEP:")
    print(fx_resumen_styled)
    print("\nEjecución de main() finalizada.\n")

refresh = main

if __name__ == '__main__':
    main()
## GUIA:
# buscar activo:        get_market_data(session,"ROFX","MERV - XMEV - AL30 - CI")
# calcular fx:          CCL_AL30_LAST_CI =calcula_tipo_de_cambio("AL30","CCL","CI","LAST",session)
# buscador de detalles: search_instrument_by_description(instrumentos_detallados_df, "MERV - XMEV - AL30 - CI")
# detalle simplificado: get_instrumento_detalle(session, "T30E6")
# market data simple:   get_mktdata(session,"T30E6")
# Ejemplo obtener BID/OFFER de un bono y su tasa: PARP.genera_ticket(get_mktdata(session,"PARP").get("OF")[0].get('price')/100)
# Ejemplo last: PARP.genera_ticket(get_mktdata(session,"PARP").get("LA").get("price")/100)
# %%
