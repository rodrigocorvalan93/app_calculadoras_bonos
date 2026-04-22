#%% 
import requests
import json
import pandas as pd
# import rentafija
# from especies import *

# URL base de la API
BASE_URL = "https://api.eco.xoms.com.ar/"

def login(username: str, password: str) -> requests.Session:
    """
    Inicia sesión en la API y retorna una sesión autenticada.
    """
    session = requests.Session()
    form_action_url = BASE_URL + "j_spring_security_check"
    credentials = {
        "j_username": username,
        "j_password": password
    }
    response = session.post(form_action_url, data=credentials)
    if response.ok:
        print("Autenticación exitosa")
        return session
    else:
        raise Exception(f"Autenticación fallida: {response.status_code} {response.text}")

def get_positions(session: requests.Session, comitente: int) -> pd.DataFrame:
    """
    Obtiene las posiciones para un comitente dado y retorna un DataFrame.
    
    Args:
        session: Sesión autenticada de requests.
        comitente: Número de comitente a consultar.
    
    Returns:
        DataFrame con las posiciones.
    """
    url = BASE_URL + f"rest/risk/position/getPositions/{comitente}"
    response = session.get(url)
    if response.ok:
        posicion_dict = json.loads(response.text)
        # Extraer cada posición y agregar el symbolReference directamente
        positions = [
            {**position, "symbolReference": position["instrument"]["symbolReference"]}
            for position in posicion_dict.get("positions", [])
        ]
        posicion_df = pd.DataFrame(positions)
        # Eliminamos la columna 'instrument' que es redundante
        if "instrument" in posicion_df.columns:
            posicion_df.drop(columns=["instrument"], inplace=True)
        return posicion_df
    else:
        print("Error al obtener posiciones:", response.status_code, response.text)
        return pd.DataFrame()

def get_balance(session: requests.Session, comitente: int) -> pd.DataFrame:
    """
    Obtiene el saldo para un comitente dado y retorna un DataFrame.
    
    Args:
        session: Sesión autenticada de requests.
        comitente: Número de comitente a consultar.
    
    Returns:
        DataFrame con el detalle del saldo.
    """
    url = BASE_URL + f"rest/risk/accountReport/{comitente}"
    response = session.get(url)
    if response.ok:
        saldo_dict = json.loads(response.text)
        saldo = []
        # Recorremos los reportes detallados
        for plazo, report in saldo_dict["accountData"]["detailedAccountReports"].items():
            for currency, details in report["currencyBalance"]["detailedCurrencyBalance"].items():
                saldo.append({
                    "Plazo": plazo,
                    "currency": currency,
                    "consumed": details["consumed"],
                    "available": details["available"],
                    "settlementDate": report["settlementDate"]
                })
        saldo_df = pd.DataFrame(saldo)
        return saldo_df
    else:
        print("Error al obtener saldo:", response.status_code, response.text)
        return pd.DataFrame()
    
import requests
from typing import List, Dict, Any

def get_market_data(market_id: str, symbol: str, entries: List[str], depth: int = 1) -> Dict[str, Any]:
    """
    Realiza una solicitud GET a la API de marketdata de reMarkets Primary.

    Parámetros:
      - market_id: Identificador de Ejecución (ejemplo: "ROFX").
      - symbol: Símbolo del instrumento (ejemplo: "DLR/DIC23").
      - entries: Lista de códigos de información solicitada (ejemplo: ["BI", "OF", "LA", "OP", "CL", "SE", "OI"]).
      - depth: Profundidad del book (por defecto 1, puede usarse, por ejemplo, 3).

    Retorna:
      - Un diccionario con la respuesta JSON de la API.

    Ejemplo de uso:
      >>> data = get_market_data("ROFX", "DLR/DIC23", ["BI", "OF", "LA", "OP", "CL", "SE", "OI"], depth=3)
      >>> print(data)
    """
    base_url = "https://api.remarkets.primary.com.ar/rest/marketdata/get"
    
    # Convertir la lista de entries a una cadena separada por comas
    entries_str = ",".join(entries)
    
    # Construir los parámetros de la URL
    params = {
        "marketId": market_id,
        "symbol": symbol,
        "entries": entries_str,
        "depth": depth
    }
    
    # Realizar la solicitud GET
    response = requests.get(base_url, params=params)
    
    # Verificar si la respuesta fue exitosa
    if response.status_code == 200:
        return response.json()
    else:
        # Lanza una excepción si la solicitud falla
        response.raise_for_status()


if __name__ == '__main__':
    # Tus credenciales
    username = "20373762939"
    password = "8eMnT0fU_"
    
    # Inicia la sesión autenticada
    session = login(username, password)
    
    # Define el número de comitente que deseas consultar
    comitente = 93481  # Puedes cambiar este valor según necesites
    
    # Obtén y muestra las posiciones
    posiciones_df = get_positions(session, comitente)
    print("Posiciones:")
    print(posiciones_df)
    
    # Obtén y muestra el saldo
    saldo_df = get_balance(session, comitente)
    print("\nSaldo:")
    print(saldo_df)

    # Market data
    market_data = get_market_data(
        market_id="ROFX",
        symbol="DLR/DIC23",
        entries=["BI", "OF", "LA", "OP", "CL", "SE", "OI"],
        depth=3
    )
    print("Datos de mercado recibidos:")
    print(market_data)