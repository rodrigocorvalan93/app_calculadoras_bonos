#%% 
import requests
import json
import pandas as pd
import rentafija
from especies import *


# URL de la página de inicio de sesión (podría ser diferente de la URL del formulario)
login_url = "https://api.cocos.xoms.com.ar/auth/login"  # Asumiendo que esta es la URL de la página de login

# URL a la que el formulario envía sus datos
form_action_url = "https://api.cocos.xoms.com.ar/j_spring_security_check"  # Ajusta según la acción del formulario

# Tus credenciales
credentials = {
    "j_username": "37376293",
    "j_password": "ZEfM77iQ_"
}

# Crear una sesión para mantener las cookies
session = requests.Session()

# Envía la solicitud de inicio de sesión
response = session.post(form_action_url, data=credentials)

# Verifica si la autenticación fue exitosa
if response.ok:
    print("Autenticación exitosa")
    # Ahora puedes usar la sesión para hacer solicitudes autenticadas
    # response = session.get('URL de algún recurso protegido')
else:
    print("Autenticación fallida", response.status_code, response.text)

# Opcional: revisa el contenido de la respuesta para verificar el éxito
# print(response.text)


#%% Segmentos
segments = session.get("https://api.cocos.xoms.com.ar/rest/segment/all").text

# Convertir el string JSON a un diccionario de Python
segments_dict = json.loads(segments)

# Convertir el diccionario a un DataFrame de pandas, específicamente la lista de segmentos
segments_df = pd.DataFrame(segments_dict['segments'])['marketSegmentId']

#%% Instrumentos
instruments = session.get("https://api.cocos.xoms.com.ar/rest/instruments/all").text

# Convertir el string JSON a un diccionario de Python
instruments_dict = json.loads(instruments)

# Convertir el diccionario a un DataFrame de pandas, específicamente la lista de segmentos
instruments_df = pd.DataFrame(instruments_dict['instruments'])

instruments_df2 = pd.concat([instruments_df.drop(['instrumentId'], axis=1), instruments_df['instrumentId'].apply(pd.Series)], axis=1)

#%% Instrumentos detallados
instrumentos_detallados = session.get("https://api.cocos.xoms.com.ar/rest/instruments/details").text

# Convertir el string JSON a un diccionario de Python
instrumentos_detallados_dict = json.loads(instrumentos_detallados)

# Convertir el diccionario a un DataFrame de pandas, específicamente la lista de segmentos
instrumentos_detallados_df = pd.DataFrame(instrumentos_detallados_dict['instruments'])


search_description = "MERV - XMEV - TX26 - 24hs"

# Buscar la fila por 'securityDescription'
row = instrumentos_detallados_df[instrumentos_detallados_df['securityDescription'] == search_description]

row

#%% Market data Futuros

futuros = list(instrumentos_detallados_df[instrumentos_detallados_df['underlying'] =='Dólar USA A3500']['instrumentId'])
futuros_df = pd.DataFrame(futuros)
base_url = 'https://api.cocos.xoms.com.ar/rest/marketdata/get'
mkt_data_futuros = []
for index, row in futuros_df.iterrows():
    

    market_id, symbol = row['marketId'], row['symbol']
    # Asegúrate de codificar adecuadamente el valor de 'symbol' para URLs
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{base_url}?marketId={market_id}&symbol={symbol}&entries=BI,OF,OI,LA,SE&depth=3"
    
    # Realizar la solicitud GET
    response = session.get(url)
    mkt_dict = json.loads(response.text)
    mkt_dict["marketData"]["symbol"] = symbol
    mkt_data_futuros.append(mkt_dict['marketData'])

mkt_data_df = pd.DataFrame(mkt_data_futuros)
mkt_data_df.set_index('symbol', inplace=True)

# Como no se cuales son futuros y cuales son diferncia entre futuros etc busco aquellos que tengan 10 caracteres (mayorista) y 9 minorista
df_fut_may = mkt_data_df[mkt_data_df.index.map(len) == 10] # Futuros mayorista (10 digitos)
df_fut_min = mkt_data_df[mkt_data_df.index.map(len) == 9] # Futuros minorista (9 digitos)


#%% Market data todos los bonos
'''
all_bonds = list(instrumentos_detallados_df[(instrumentos_detallados_df['cficode'] == 'DBXXXX') | (instrumentos_detallados_df['cficode'] == 'DYXTXR')]['instrumentId'])
all_bonds_df = pd.DataFrame(all_bonds)

base_url = 'https://api.cocos.xoms.com.ar/rest/marketdata/get'
mkt_data_all_bonds = []
for index, row in all_bonds_df.iterrows():

    market_id, symbol = row['marketId'], row['symbol']
    # Asegúrate de codificar adecuadamente el valor de 'symbol' para URLs
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{base_url}?marketId={market_id}&symbol={symbol}&entries=BI,OF,OI,LA,SE&depth=3"
    
    # Realizar la solicitud GET
    response = session.get(url)
    print(response.text)
    mkt_dict = json.loads(response.text)
    mkt_dict["marketData"]["symbol"] = symbol
    mkt_data_all_bonds.append(mkt_dict['marketData'])

mkt_data_all_bonds_df = pd.DataFrame(mkt_data_all_bonds)
mkt_data_all_bonds_df.set_index('symbol', inplace=True)
mkt_data_all_bonds_df.to_excel('bymaprices.xlsx')

%% filtramos Last Prices

last_px_all_bonds = [entry['price'] if entry is not None else None for entry in mkt_data_all_bonds_df['LA']]

# Crear un nuevo DataFrame con symbol como índice y los precios como columna
last_px_all_bonds_df = pd.DataFrame({
    'symbol': mkt_data_all_bonds_df.index,
    'price': last_px_all_bonds
})

last_px_all_bonds_df
'''

lista_curva_cer = ["T2X5",
                   "T4X5",
                   "TZXM5",
                   "TC25",
                   "TZXY5",
                   "TZX25",
                   "TG25",
                   "TZXO5",
                   "TX25",
                   "TZXD5",
                   "TX26",
                   "TZXM6",
                   "TZX26",
                   "TZXO6",
                   "TZXD6",
                   "TZXM7",
                   "TZX27",
                   "TZXD7",
                   "TZX28",
                   "TX28",
                   "DICP",
                   "PARP",
                   "CUAP"]


# Lista para liquidación en 24hs
lista_cer_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_cer]

# Lista para contado inmediato
lista_cer_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_cer]


lista_curva_lecap= ["S14F5",
                    "S28F5",
                    "S14M5",
                    "S31M5",
                    "S16A5",
                    "S28A5",
                    "S16Y5",
                    "S30Y5",
                    "S18J5",
                    "S30J5",
                    "S31L5",
                    "S15G5",
                    "S29G5",
                    "S12S5",
                    "S30S5",
                    "T17O5",
                    "S31O5",
                    "S10N5",
                    "T15D5",
                    "T30E6",
                    "T13F6",
                    "TTM26",
                    "TTJ26",
                    "T30J6",
                    "TTS26",
                    "TO26",
                    "TTD26",
                    "T15E7"
                    ]

# Lista para liquidación en 24hs
lista_lecap_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_lecap]

# Lista para contado inmediato
lista_lecap_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_lecap]


lista_curva_global= ["GD29",
                    "GD30",
                    "GD35",
                    "GD38",
                    "GD41",
                    "GD46"]


# Lista para liquidación en 24hs
lista_global_24hs = [f"MERV - XMEV - {simbolo} - 24hs" for simbolo in lista_curva_global]

# Lista para contado inmediato
lista_global_ci = [f"MERV - XMEV - {simbolo} - CI" for simbolo in lista_curva_global]

#%% Lista de precios T2 de boncer + lecap y boncap y bote + globales
lista_curva_cer_lecap_global = lista_cer_24hs + lista_lecap_24hs + lista_global_24hs + lista_cer_ci + lista_lecap_ci
base_url = 'https://api.cocos.xoms.com.ar/rest/marketdata/get'
mkt_data_cer_lecap_global = []
for symbol in lista_curva_cer_lecap_global:
    symbol_encoded = requests.utils.quote(symbol)
    url = f"{base_url}?marketId=ROFX&symbol={symbol_encoded}&entries=BI,OF,OI,LA,SE&depth=3"
    
    response = session.get(url)
    if response.status_code == 200:
        mkt_dict = json.loads(response.text)
        if mkt_dict.get("status") != "ERROR":  # Verifica el estado de la respuesta
            mkt_dict["marketData"]["symbol"] = symbol
            mkt_data_cer_lecap_global.append(mkt_dict['marketData'])
        else:
            print(f"Error en los datos de mercado para {symbol}, pasando al siguiente.")
    else:
        print(f"Error en la solicitud para {symbol}, pasando al siguiente.")

mkt_data_cer_lecap_global_df = pd.DataFrame(mkt_data_cer_lecap_global)
mkt_data_cer_lecap_global_df.set_index('symbol', inplace=True)
mkt_data_cer_lecap_global_df.to_excel('bymaprices.xlsx')



#%% filtramos Last Prices

last_px_cer_lecap_global = [entry['price'] if entry is not None else None for entry in mkt_data_cer_lecap_global_df['LA']]

# Crear un nuevo DataFrame con symbol como índice y los precios como columna
last_px_cer_lecap_global_df = pd.DataFrame({
    'symbol': mkt_data_cer_lecap_global_df.index,
    'Last Price': last_px_cer_lecap_global
})

last_px_cer_lecap_global_df

#%%
# Inicializa una lista para guardar los datos antes de convertirlos a DataFrame
curva_cer_append = []

for simbolo in lista_cer_24hs:
    simbolo_limpio = simbolo.replace("MERV - XMEV - ", "").replace(" - 24hs", "")
    # Buscamos el precio en last_px_all_bonds_df
    price = last_px_cer_lecap_global_df.loc[last_px_cer_lecap_global_df['symbol'] == simbolo, 'Last Price'].values
    # Añadimos los datos a la lista
    if len(price) > 0:
        curva_cer_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': price[0]})
    else:
        curva_cer_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': None})

# Convertimos la lista de datos a DataFrame después de salir del bucle
cer_24hs_prices_df = pd.DataFrame(curva_cer_append)


# Inicializa una lista para guardar los datos antes de convertirlos a DataFrame
curva_lecap_append = []

for simbolo in lista_lecap_24hs:
    simbolo_limpio = simbolo.replace("MERV - XMEV - ", "").replace(" - 24hs", "")
    # Buscamos el precio en last_px_all_bonds_df
    price = last_px_cer_lecap_global_df.loc[last_px_cer_lecap_global_df['symbol'] == simbolo, 'Last Price'].values
    # Añadimos los datos a la lista
    if len(price) > 0:
        curva_lecap_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': price[0]})
    else:
        curva_lecap_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': None})

# Convertimos la lista de datos a DataFrame después de salir del bucle
lecap_24hs_prices_df = pd.DataFrame(curva_lecap_append)


#%%
lecap_24hs_prices_df

for index, row in lecap_24hs_prices_df.iterrows():
    codigo_bono = row['Código']
    precio = row['Last Price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        lecap_24hs_prices_df.at[index, 'TIREA'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = rentafija.tir_a_tna(bono.tirea,bono.dias_remanentes, 365)
        lecap_24hs_prices_df.at[index, 'TNA'] = tna

        # Calcula tem
        lecap_24hs_prices_df.at[index, 'TEM'] = (1+tirea)**(30/365)-1

        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        lecap_24hs_prices_df.at[index, 'Paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        lecap_24hs_prices_df.at[index, 'Duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        lecap_24hs_prices_df.at[index, 'TIREA'] = None
        lecap_24hs_prices_df.at[index, 'TNA'] = None
        lecap_24hs_prices_df.at[index, 'TEM'] = None
        lecap_24hs_prices_df.at[index, 'Paridad'] = None
        lecap_24hs_prices_df.at[index, 'Duration'] = None

lecap_24hs_prices_df['TEM'] = lecap_24hs_prices_df['TEM'].apply(lambda x: "{:.2%}".format(x))
lecap_24hs_prices_df['TNA'] = lecap_24hs_prices_df['TNA'].apply(lambda x: "{:.2%}".format(x))
lecap_24hs_prices_df['TIREA'] = lecap_24hs_prices_df['TIREA'].apply(lambda x: "{:.2%}".format(x))

# Adding a new column with the difference in 'TEM' between each row and the previous row
lecap_24hs_prices_df['tem_spread'] = lecap_24hs_prices_df['TEM'].str.rstrip('%').astype(float).diff().fillna(0)

# Convert the difference back to percentage format
lecap_24hs_prices_df['tem_spread'] = lecap_24hs_prices_df['tem_spread'].apply(lambda x: "{:.2f}%".format(x))

    



#%% CURVA CER 24hs
cer_24hs_prices_df
#cer_24hs_prices_df['price'] = cer_24hs_prices_df['price'].fillna(2)

for index, row in cer_24hs_prices_df.iterrows():
    codigo_bono = row['Código']
    precio = row['Last Price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        cer_24hs_prices_df.at[index, 'TIREA'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(bono.tirea,bono.dias_remanentes, 365)
        cer_24hs_prices_df.at[index, 'TNA'] = tna


        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        cer_24hs_prices_df.at[index, 'Paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        cer_24hs_prices_df.at[index, 'Duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        cer_24hs_prices_df.at[index, 'TIREA'] = None
        cer_24hs_prices_df.at[index, 'TNA'] = None
        cer_24hs_prices_df.at[index, 'Paridad'] = None
        cer_24hs_prices_df.at[index, 'Duration'] = None
        

cer_24hs_prices_df['TNA'] = cer_24hs_prices_df['TNA'].apply(lambda x: "{:.2%}".format(x))
cer_24hs_prices_df['TIREA'] = cer_24hs_prices_df['TIREA'].apply(lambda x: "{:.2%}".format(x))
#%% Cer proyectado
        

cerproyectado_24hs_prices_df = pd.DataFrame(curva_cer_append)

for index, row in cerproyectado_24hs_prices_df.iterrows():
    codigo_bono = row['Código']
    precio = row['Last Price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}j.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        cerproyectado_24hs_prices_df.at[index, 'TIREA'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(tirea,bono.dias_remanentes, 365)
        cerproyectado_24hs_prices_df.at[index, 'TNA'] = tna

        # Calcula tem
        cerproyectado_24hs_prices_df.at[index, 'TEM'] = (1+tirea)**(30/365)-1

        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}j.paridad"
        paridad = eval(comando_paridad)
        cerproyectado_24hs_prices_df.at[index, 'Paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}j.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        cerproyectado_24hs_prices_df.at[index, 'Duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        cerproyectado_24hs_prices_df.at[index, 'TIREA'] = None
        cerproyectado_24hs_prices_df.at[index, 'TNA'] = None
        cerproyectado_24hs_prices_df.at[index, 'TEM'] = None
        cerproyectado_24hs_prices_df.at[index, 'Paridad'] = None
        cerproyectado_24hs_prices_df.at[index, 'Duration'] = None

cerproyectado_24hs_prices_df['Código'] = cerproyectado_24hs_prices_df['Código'] + 'j'

cerproyectado_24hs_prices_df['TEM'] = cerproyectado_24hs_prices_df['TEM'].apply(lambda x: "{:.2%}".format(x))
cerproyectado_24hs_prices_df['TNA'] = cerproyectado_24hs_prices_df['TNA'].apply(lambda x: "{:.2%}".format(x))
cerproyectado_24hs_prices_df['TIREA'] = cerproyectado_24hs_prices_df['TIREA'].apply(lambda x: "{:.2%}".format(x))


############################################################################
#%% Cer en Contado Inmediato y lecap en ci levanta listados
curva_cer_ci_append = []

for simbolo in lista_cer_ci:
    simbolo_limpio = simbolo.replace("MERV - XMEV - ", "").replace(" - CI", "")
    # Buscamos el precio en last_px_all_bonds_df
    price = last_px_cer_lecap_global_df.loc[last_px_cer_lecap_global_df['symbol'] == simbolo, 'Last Price'].values
    # Añadimos los datos a la lista
    if len(price) > 0:
        curva_cer_ci_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': price[0]})
    else:
        curva_cer_ci_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': None})

# Convertimos la lista de datos a DataFrame después de salir del bucle
cer_ci_prices_df = pd.DataFrame(curva_cer_ci_append)


# Inicializa una lista para guardar los datos antes de convertirlos a DataFrame
curva_lecap_ci_append = []

for simbolo in lista_lecap_ci:
    simbolo_limpio = simbolo.replace("MERV - XMEV - ", "").replace(" - CI", "")
    # Buscamos el precio en last_px_all_bonds_df
    price = last_px_cer_lecap_global_df.loc[last_px_cer_lecap_global_df['symbol'] == simbolo, 'Last Price'].values
    # Añadimos los datos a la lista
    if len(price) > 0:
        curva_lecap_ci_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': price[0]})
    else:
        curva_lecap_ci_append.append({'symbol': simbolo, 'Código': simbolo_limpio, 'Last Price': None})

# Convertimos la lista de datos a DataFrame después de salir del bucle
lecap_ci_prices_df = pd.DataFrame(curva_lecap_ci_append)


#%% Curva con tasas de lecap y cer ci
lecap_ci_prices_df
today_str = rentafija.n_dias_laborales(date.today(), 0).strftime("%d/%m/%Y")
for index, row in lecap_ci_prices_df.iterrows():
    codigo_bono = row['Código']
    precio = row['Last Price']/100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio},today_str)"
        tirea = eval(comando_tirea)
        lecap_ci_prices_df.at[index, 'TIREA'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = rentafija.tir_a_tna(bono.tirea,bono.dias_remanentes, 365)
        lecap_ci_prices_df.at[index, 'TNA'] = tna

        # Calcula tem
        lecap_ci_prices_df.at[index, 'TEM'] = (1+tirea)**(30/365)-1

        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        lecap_ci_prices_df.at[index, 'Paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea,today_str)"
        duration = eval(comando_duration)
        lecap_ci_prices_df.at[index, 'Duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        lecap_ci_prices_df.at[index, 'TIREA'] = None
        lecap_ci_prices_df.at[index, 'TNA'] = None
        lecap_ci_prices_df.at[index, 'TEM'] = None
        lecap_ci_prices_df.at[index, 'Paridad'] = None
        lecap_ci_prices_df.at[index, 'Duration'] = None

lecap_ci_prices_df['TEM'] = lecap_ci_prices_df['TEM'].apply(lambda x: "{:.2%}".format(x))
lecap_ci_prices_df['TNA'] = lecap_ci_prices_df['TNA'].apply(lambda x: "{:.2%}".format(x))
lecap_ci_prices_df['TIREA'] = lecap_ci_prices_df['TIREA'].apply(lambda x: "{:.2%}".format(x))

# Adding a new column with the difference in 'TEM' between each row and the previous row
lecap_ci_prices_df['tem_spread'] = lecap_ci_prices_df['TEM'].str.rstrip('%').astype(float).diff().fillna(0)

# Convert the difference back to percentage format
lecap_ci_prices_df['tem_spread'] = lecap_ci_prices_df['tem_spread'].apply(lambda x: "{:.2f}%".format(x))


cer_ci_prices_df
#cer_ci_prices_df['price'] = cer_ci_prices_df['price'].fillna(2)

for index, row in cer_ci_prices_df.iterrows():
    codigo_bono = row['Código']
    precio = row['Last Price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio},today_str)"
        tirea = eval(comando_tirea)
        cer_ci_prices_df.at[index, 'TIREA'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(bono.tirea,bono.dias_remanentes, 365)
        cer_ci_prices_df.at[index, 'TNA'] = tna


        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        cer_ci_prices_df.at[index, 'Paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea,today_str)"
        duration = eval(comando_duration)
        cer_ci_prices_df.at[index, 'Duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        cer_ci_prices_df.at[index, 'TIREA'] = None
        cer_ci_prices_df.at[index, 'TNA'] = None
        cer_ci_prices_df.at[index, 'Paridad'] = None
        cer_ci_prices_df.at[index, 'Duration'] = None
        

cer_ci_prices_df['TNA'] = cer_ci_prices_df['TNA'].apply(lambda x: "{:.2%}".format(x))
cer_ci_prices_df['TIREA'] = cer_ci_prices_df['TIREA'].apply(lambda x: "{:.2%}".format(x))



#############################################################################

#%% Guarda archivo (opcional)

df = pd.concat([cer_24hs_prices_df, lecap_24hs_prices_df, cerproyectado_24hs_prices_df], ignore_index=True)

df['fecha_hoy'] = pd.to_datetime('today').date()


nombre_archivo = "Delta - historico_byma_px_tasas.xlsx"

# Mostrar el DataFrame resultante (opcional)
df
print(df)

# Obtener la ruta del perfil del usuario desde las variables de entorno
user_profile = os.environ['USERPROFILE']

# Construir la ruta completa para el nombre del archivo, incluyendo la carpeta específica
nombre_archivo = os.path.join(user_profile, "DELTA ASSET MANAGEMENT S.A", "Inversiones - Documentos", "Delta Bases", "Delta - historico_byma_px_tasas.xlsx")

# Preguntar al usuario si desea guardar el DataFrame
respuesta = input("¿Deseas guardar el DataFrame en un archivo Excel? (S/N): ")

if respuesta.upper() == 'S':
    # Si el usuario responde 'S', proceder a guardar el DataFrame en el archivo Excel
    try:
        # Intentar leer el archivo Excel existente
        df_existente = pd.read_excel(nombre_archivo, parse_dates=['fecha_hoy'])
        # Si se logra leer, concatenar el DataFrame existente con el nuevo
        df_final = pd.concat([df_existente, df], ignore_index=True)
        df_final['fecha_hoy'] = pd.to_datetime(df_final['fecha_hoy']).dt.date
    except FileNotFoundError:
        # Si el archivo no existe, simplemente usar el nuevo DataFrame
        df_final = df
    df_final.to_excel(nombre_archivo, index=False)
    print(f"DataFrame guardado con éxito en '{nombre_archivo}'.")
elif respuesta.upper() == 'N':
    # Si el usuario responde 'N', no hacer nada
    print("No se ha guardado el DataFrame.")
else:
    # Si el usuario proporciona una respuesta diferente
    print("Respuesta no reconocida. No se ha realizado ninguna acción.")

#%% Bid offers
'''
mkt_data_cer_lecap_global_df

offer_px_cer_lecap_global = [entry['price'] if entry is not None else None for entry in mkt_data_cer_lecap_global_df['OF']]

# Crear un nuevo DataFrame con symbol como índice y los precios como columna
last_px_cer_lecap_global_df = pd.DataFrame({
    'symbol': mkt_data_cer_lecap_global_df.index,
    'Last Price': last_px_cer_lecap_global
})

last_px_cer_lecap_global_df
'''