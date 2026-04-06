#%%

import requests
import json
from typing import List, Dict, Any

# URL base de la API de Eco Primary
BASE_URL = "https://api.eco.xoms.com.ar/"

def login(username: str, password: str) -> requests.Session:
    """
    Inicia sesión en la API de Eco Primary y retorna una sesión autenticada.
    
    Asegúrate de que:
      - El endpoint y la acción sean los correctos.
      - Las credenciales sean válidas.
    """
    session = requests.Session()
    form_action_url = BASE_URL + "j_spring_security_check"
    credentials = {
        "j_username": username,
        "j_password": password
    }
    response = session.post(form_action_url, data=credentials)
    
    # Imprime el contenido de la respuesta para depuración
    print("Respuesta del login Eco:")
    print(response.text)
    
    # Verificamos que la respuesta no contenga la página de login
    if response.ok and "Login" not in response.text:
        print("Autenticación exitosa en Eco Primary")
        return session
    else:
        raise Exception(f"Autenticación fallida en Eco Primary: {response.status_code}\n{response.text}")

def get_market_data(session: requests.Session, market_id: str, symbol: str, entries: List[str], depth: int = 1) -> Dict[str, Any]:
    """
    Realiza una solicitud GET a la API de marketdata de Eco Primary.
    
    Parámetros:
      - market_id: Identificador de Ejecución (ejemplo: "ROFX").
      - symbol: Símbolo del instrumento (ejemplo: "DLR/DIC23").
      - entries: Lista de códigos de información solicitada (ejemplo: ["BI", "OF", "LA", "OP", "CL", "SE", "OI"]).
      - depth: Profundidad del book (por defecto 1).
    
    Retorna:
      - Un diccionario con la respuesta JSON de la API.
    """
    url = BASE_URL + "rest/marketdata/get"
    entries_str = ",".join(entries)
    params = {
        "marketId": market_id,
        "symbol": symbol,
        "entries": entries_str,
        "depth": depth
    }
    
    response = session.get(url, params=params)
    
    # Imprimir para depuración
    print("Market Data - Código de estado:", response.status_code)
    print("Market Data - Texto de respuesta:", response.text)
    
    if response.status_code == 200:
        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Error al decodificar JSON. Texto de respuesta:\n{response.text}") from e
    else:
        response.raise_for_status()

def ingresar_orden(
    session: requests.Session,
    market_id: str,
    symbol: str,
    side: str,
    timeInForce: str,
    orderQty: int,
    ordType: str,
    account: int,
    price: float,
    cancelPrevious: bool = False,
    iceberg: bool = False,
    expireDate: str = None,  # En formato "YYYYMMDD" (opcional, para GTD)
    displayQty: int = None   # Opcional, para órdenes Iceberg
) -> Dict[str, Any]:
    """
    Envía una orden al mercado mediante la API.
    
    Parámetros:
      - session: sesión autenticada de requests.
      - market_id: Identificador del mercado (ejemplo: "ROFX", en primary).
      - symbol: Símbolo del instrumento (ejemplo: "MERV - XMEV - PESOS - 1D").
      - side: "BUY" o "SELL".
      - timeInForce: "DAY", "IOC", "FOK" o "GTD".
      - orderQty: Cantidad de la orden (entero).
      - ordType: "LIMIT" o "MARKET".
      - account: Número de cuenta (por ejemplo, 93481).
      - price: Precio de la orden (float).
      - cancelPrevious: (opcional) True o False.
      - iceberg: (opcional) True o False.
      - expireDate: (opcional) Fecha de vencimiento para órdenes GTD (en formato "YYYYMMDD").
      - displayQty: (opcional) Cantidad a divulgar para órdenes Iceberg.
      
    Retorna:
      - Un diccionario con la respuesta de la API (se espera que incluya al menos "status" y "orderId").
    """
    url = BASE_URL + "rest/order/newSingleOrder"
    
    # Construir el diccionario de parámetros
    params = {
        "marketId": market_id, 
        "symbol": symbol,
        "side": side,
        "timeInForce": timeInForce,
        "orderQty": orderQty,
        "ordType": ordType,
        "account": account,
        "price": price,
        "cancelPrevious": str(cancelPrevious),
        "iceberg": str(iceberg)
    }
    
    # Incluir parámetros opcionales si se proporcionan
    if expireDate:
        params["expireDate"] = expireDate
    if displayQty:
        params["displayQty"] = displayQty

    # Realizar la solicitud GET (según lo indica la documentación)
    response = session.get(url, params=params)
    print("Orden - Código de estado:", response.status_code)
    print("Orden - Texto de respuesta:", response.text)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "OK":
            print("Orden ingresada correctamente.")
        else:
            print("La API respondió con error:", data)
        return data
    else:
        response.raise_for_status()

def consultar_estado_orden(session: requests.Session, order_id: str) -> Dict[str, Any]:
    """
    Consulta el estado de una orden ingresada mediante su ID.
    
    Parámetros:
      - session: sesión autenticada de requests.
      - order_id: Identificador de la orden (tal como lo devuelve la API en ingresar_orden).
      
    Retorna:
      - Un diccionario con el estado de la orden. Se espera que el campo "status" sea:
          - "NEW": la orden se ingresó correctamente.
          - "REJECTED": la orden fue rechazada (posiblemente se incluya un campo "reason").
    """
    url = BASE_URL + "rest/order/orderStatus"
    params = {"orderId": order_id}
    
    response = session.get(url, params=params)
    print("Estado Orden - Código de estado:", response.status_code)
    print("Estado Orden - Texto de respuesta:", response.text)
    
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def consultar_orden_por_client_order_id(
    session: requests.Session,
    clOrdId: str,
    proprietary: str = "api"
) -> Dict[str, Any]:
    """
    Consulta el último estado de una orden utilizando el Client Order ID.
    
    Parámetros:
      - session: Sesión autenticada de requests.
      - clOrdId: El ID del request realizado al Mercado, devuelto por la API de Ingreso y Cancelación de Orden.
      - proprietary: Identificador fijo del participante del mercado para la cuenta (por defecto "api").
    
    Retorna:
      - Un diccionario con la respuesta JSON que indica el estado de la orden.
    
    Ejemplo de solicitud:
      GET https://api.eco.xoms.com.ar/rest/order/id?clOrdId=user1144720678549411&proprietary=api
    """
    url = BASE_URL + "rest/order/id"
    params = {
        "clOrdId": clOrdId,
        "proprietary": proprietary
    }
    
    response = session.get(url, params=params)
    print("Consulta Orden por Client Order ID - Código de estado:", response.status_code)
    print("Consulta Orden por Client Order ID - Texto de respuesta:", response.text)
    
    if response.status_code == 200:
        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Error al decodificar JSON. Respuesta:\n{response.text}") from e
    else:
        response.raise_for_status()

if __name__ == '__main__':
    # --- Autenticación en Eco Primary ---
    # Reemplaza estos valores con tus credenciales reales para Eco Primary
    username = "20373762939"
    password = "8eMnT0fU_"
    
    try:
        session_eco = login(username, password)
    except Exception as e:
        print("Error en el login de Eco Primary:")
        print(e)
        exit(1)
    
    # --- Solicitud de Market Data ---
    try:
        market_data = get_market_data(
            session=session_eco,
            market_id="ROFX",
            symbol="DLR/DIC25",
            entries=["BI", "OF", "LA", "OP", "CL", "SE", "OI"],
            depth=3
        )
        print("Datos de mercado recibidos:")
        print(market_data)
    except Exception as e:
        print("Error al obtener market data:")
        print(e)

        
