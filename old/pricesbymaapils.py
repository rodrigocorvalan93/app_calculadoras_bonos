#%% 
import requests
import logging
import json
import pandas as pd
from pathlib import Path
import os
#import rentafija
#from especies import *


credentials = {
    "j_username": 'delta_api',
    "j_password": 'D3lt41210*-*'
}

url_gral = "https://api.latinsecurities.matrizoms.com.ar/"


url_market_data = url_gral + "rest/marketdata/get"
url_form_action = url_gral + "j_spring_security_check"  # URL a la que el formulario envía sus datos - Ajusta según la acción del formulario

path = Path(os.getcwd())
path_general = path.parent.parent
path_save = os.path.join(path_general, "Inputs_Esco")



# Conexión y Token

url_token = url_gral + "auth/getToken"

def get_auth_token(url, username, password):
    headers = {"X-Username": username, "X-Password": password}
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        logging.info("Authentication successful.")
        return response.headers.get("X-Auth-Token")
    else:
        logging.error("Authentication failed.")
        raise Exception("Authentication Failed")
    


session = requests.Session()                                  # Crear una sesión para mantener las cookies
response = session.post(url_form_action, data=credentials)    # Envía la solicitud de inicio de sesión

# Verifica si la autenticación fue exitosa
if response.ok:
    print("Autenticación exitosa")
else:
    print("Autenticación fallida", response.status_code, response.text)



instruments = session.get("https://api.latinsecurities.matrizoms.com.ar/rest/instruments/all").text

# Convertir el string JSON a un diccionario de Python
instruments_dict = json.loads(instruments)

# Convertir el diccionario a un DataFrame de pandas, específicamente la lista de segmentos
instruments_df = pd.DataFrame(instruments_dict['instruments'])

instruments_df2 = pd.concat([instruments_df.drop(['instrumentId'], axis=1), instruments_df['instrumentId'].apply(pd.Series)], axis=1)


#%% Instrumentos detallados
instrumentos_detallados = session.get("https://api.latinsecurities.matrizoms.com.ar/rest/instruments/details").text

# Convertir el string JSON a un diccionario de Python
instrumentos_detallados_dict = json.loads(instrumentos_detallados)

# Convertir el diccionario a un DataFrame de pandas, específicamente la lista de segmentos
instrumentos_detallados_df = pd.DataFrame(instrumentos_detallados_dict['instruments'])

#%% Todos los activos:
all_bonds = list(instrumentos_detallados_df[
    (instrumentos_detallados_df['cficode'] == 'DBXXFR') |  # ONS
    (instrumentos_detallados_df['cficode'] == 'DBXXXX') | # Bonos del tesoro
    (instrumentos_detallados_df['cficode'] == 'DYXTXR') | # Letras
    (instrumentos_detallados_df['cficode'] == 'EMXXXX') | # CEDEARS
    (instrumentos_detallados_df['cficode'] == 'ESXXXX') | # Acciones
    (instrumentos_detallados_df['cficode'] == 'FXXXSX') | # Rofex
    (instrumentos_detallados_df['cficode'] == 'MRIXXX') | # indices
    (instrumentos_detallados_df['cficode'] == 'RPXXXX') # Caucho 
    ]['instrumentId'])
all_bonds_df = pd.DataFrame(all_bonds)

#Extrae market data
base_url = 'https://api.latinsecurities.matrizoms.com.ar/rest/marketdata/get'
mkt_data_all_bonds = []
for index, row in all_bonds_df.iterrows():

    market_id, symbol = row['marketId'], row['symbol']
    # Asegúrate de codificar adecuadamente el valor de 'symbol' para URLs
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{base_url}?marketId={market_id}&symbol={symbol}&entries=BI,OF,OI,LA,SE,OP,CL,ACP&depth=1"
    
    # Realizar la solicitud GET
    response = session.get(url)
    # print(response.text)
    mkt_dict = json.loads(response.text)
    mkt_dict["marketData"]["symbol"] = symbol
    mkt_data_all_bonds.append(mkt_dict['marketData'])


mkt_data_all_bonds_df = pd.DataFrame(mkt_data_all_bonds)

# Función para expandir columnas con diccionarios
def transform_market_data(df, columns):
    for col in columns:
        if col in df.columns:
            # Convertir listas vacías y valores nulos en None
            df[col] = df[col].apply(lambda x: x[0] if isinstance(x, list) and x else None if x in [None, [], {}] else x)
            
            # Crear nuevas columnas para almacenar los valores expandidos
            expanded_data = {f"{col} {key}": [None] * len(df) for key in ["price", "size", "date"]}

            # Llenar las listas con los valores correctos sin duplicar filas
            for i, row in enumerate(df[col]):
                if isinstance(row, dict):
                    for key in expanded_data.keys():
                        expanded_data[key][i] = row.get(key.split()[-1], None)

            # Agregar las nuevas columnas al DataFrame sin cambiar el número de filas
            for key, values in expanded_data.items():
                df[key] = values

            # Eliminar la columna original después de expandirla
            df = df.drop(columns=[col])
    
    return df



mkt_data_all_bonds_df.set_index('symbol', inplace=True)



# Columnas que contienen diccionarios
columns_to_expand = ["LA", "SE", "BI", "OF","OP","CL","OP","ACP"]

# Aplicar la transformación
market_data = transform_market_data(mkt_data_all_bonds_df, columns_to_expand)


# Mostrar DataFrame resultante
print(market_data)
market_data.to_excel(path_save + '\\byma_prices.xlsx')



