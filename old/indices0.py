
from utils import *
import dias_habiles

# Last version 7-11-24
BCRA_API_URL = "https://api.estadisticasbcra.com/"
TOKEN = "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDk2Nzc1NTgsInR5cGUiOiJleHRuYWwiLCJ1c2VyIjoicm9kcmlnb2NvcnZhbGFuOTNAZ21haWwuY29tIn0.RVyV_mkp-ziJMBxTJpqITRBwoL25X2tVxGivQ8_fhERpA_rcHZtXghPKhSS9E_iNbQHcv8oerMMX0ZS5h7qYTg"
HEADERS = {"Authorization": f"BEARER {TOKEN}"}

# Nueva Api
def fetch_bcra_data(serie_id):
    response = requests.get(BCRA_API_URL + serie_id, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data)
        df["d"] = pd.to_datetime(df["d"]).dt.date
        df.set_index("d", inplace=True)
        return df
    else:
        print("Error al obtener los datos:", response.status_code)
        return None

def fetch_principales_variables():
    url = "https://api.bcra.gob.ar/estadisticas/v2.0/principalesvariables"
    headers = {
        "Accept-Language": "es-AR"
    }

    try:
        # Realizar la solicitud a la API
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        response.raise_for_status()  # Lanza un error si el status_code no es exitoso (200-299)
        
        # Parsear los datos de respuesta
        data = response.json()

        # Verificar si el estado es exitoso
        if data.get("status") == 200:
            results = data.get("results", [])
            if results:
                df = pd.DataFrame(results)
                return df
            else:
                print("No se encontraron datos en la clave 'results'.")
                return None
        else:
            print(f"Error en la API: {data.get('errorMessages', 'Error desconocido')}")
            return None
        
    except requests.exceptions.Timeout:
        print("La solicitud a la API excedió el tiempo de espera.")
        return None
    except requests.exceptions.RequestException as e:
        # Capturar cualquier error de solicitud HTTP
        print(f"Ocurrió un error al conectarse a la API: {e}")
        return None

#%% Nueva API Ad-hoc Implementation
def fetch_variable_data_api_nueva(idVariable, start_date, end_date):
    base_url = "https://api.bcra.gob.ar/estadisticas/v2.0/datosvariable"
    url = f"{base_url}/{idVariable}/{start_date}/{end_date}"

    try:
        # Configurar un tiempo de espera (timeout)
        response = requests.get(url, verify=False, timeout=20)  # Timeout de 20 segundos
        response.raise_for_status()

        # Intentar parsear el JSON
        try:
            data = response.json()
        except ValueError:
            print("La respuesta no es un JSON válido.")
            return None

        # Validar si el estado es exitoso
        if data.get("status") == 200:
            results = data.get("results", [])
            if results:
                df = pd.DataFrame(results)
                return df
            else:
                print("No se encontraron datos en la clave 'results'.")
                return None
        else:
            print(f"Error en la API: {data.get('errorMessages', 'Error desconocido')}")
            return None

    except requests.exceptions.Timeout:
        print("La solicitud a la API excedió el tiempo de espera.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Ocurrió un error durante la solicitud: {e}")
        return None

# Ejemplo de uso de las funciones
variables_df = fetch_principales_variables()
if variables_df is not None:
    pass
else:
    print("ERROR! No se pudieron obtener las principales variables.")

# A3500:
idVariable = 5
start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
end_date = datetime.now().strftime("%Y-%m-%d")
a3500_new_df = fetch_variable_data_api_nueva(idVariable, start_date, end_date)
if a3500_new_df is not None:
    pass
else:
    print("ERROR: No se pudieron obtener los datos de la variable A3500.")

# BADLAR:
idVariable = 7
badlar_new_df = fetch_variable_data_api_nueva(idVariable, start_date, end_date)
if badlar_new_df is not None:
    pass
else:
    print("ERROR: No se pudieron obtener los datos de la variable BADLAR.")

# CER:
idVariable = 30
cer_new_df = fetch_variable_data_api_nueva(idVariable, start_date, end_date)
if cer_new_df is not None:
    pass
else:
    print("ERROR: No se pudieron obtener los datos de la variable CER.")

# INFLAMOM:
idVariable = 27
inflamom_new_df = fetch_variable_data_api_nueva(idVariable, start_date, end_date)
if inflamom_new_df is not None:
    pass
else:
    print("ERROR: No se pudieron obtener los datos de la variable INFLAMOM.")

# UVA:
idVariable = 31
uva_new_df = fetch_variable_data_api_nueva(idVariable, start_date, end_date)
if uva_new_df is not None:
    pass
else:
    print("ERROR: No se pudieron obtener los datos de la variable UVA.")

#%%

def calcular_CER_diario_proyectado(df_inflamom, cer_inicial, fecha_inicial):
    fecha_inicial = pd.to_datetime(fecha_inicial)
    if fecha_inicial not in pd.date_range(start=df_inflamom.index.min(), end=df_inflamom.index.max()):
        raise ValueError("La fecha inicial está fuera del rango del DataFrame de inflación.")

    rango_fechas = pd.date_range(start=fecha_inicial, end=df_inflamom.index.max() + MonthEnd(1), freq='D')
    df_cer = pd.DataFrame(index=rango_fechas, columns=['CER'])
    df_cer.iloc[0, df_cer.columns.get_loc('CER')] = cer_inicial

    for fecha in rango_fechas[1:]:
        j_1 = (fecha - pd.DateOffset(months=1)).to_period('M')
        j_2 = (fecha - pd.DateOffset(months=2)).to_period('M')
        k = pd.Period(fecha, freq='M').days_in_month
        k_1 = pd.Period(fecha - pd.DateOffset(months=1), freq='M').days_in_month

        if fecha.day <= 15:
            F_t = (1 + df_inflamom.loc[df_inflamom.index.to_period('M') == j_2, 'inflacionmom'].iloc[0]/100) ** (1/k_1)
        else:
            F_t = (1 + df_inflamom.loc[df_inflamom.index.to_period('M') == j_1, 'inflacionmom'].iloc[0]/100) ** (1/k)

        df_cer.loc[fecha, 'CER'] = df_cer.loc[fecha - pd.DateOffset(days=1), 'CER'] * F_t

    df_cer.index = df_cer.index.date
    return df_cer

def proyectadeva(proyeccion_mensual, fecha_inicial, valor_inicial):
    serie_temporal = []
    fechas = sorted(proyeccion_mensual.keys())
    fechas_dt = [datetime.strptime(fecha, '%Y-%m-%d').date() for fecha in fechas]
    fecha_siguiente = datetime.strptime(fecha_inicial, '%Y-%m-%d').date() + timedelta(days=1)
    proyeccion_anterior = valor_inicial

    for fecha_actual in fechas_dt:
        proyeccion_actual = proyeccion_mensual[fecha_actual.strftime('%Y-%m-%d')]

        while fecha_siguiente < fecha_actual:
            dias_entre_fechas = (fecha_actual - fecha_siguiente).days
            tasa_diaria = (proyeccion_actual / proyeccion_anterior) ** (1 / dias_entre_fechas)
            proyeccion_diaria = proyeccion_anterior * tasa_diaria
            serie_temporal.append((fecha_siguiente, proyeccion_diaria))
            fecha_siguiente += timedelta(days=1)
            proyeccion_anterior = proyeccion_diaria

    df = pd.DataFrame(serie_temporal, columns=['Fecha', 'tca3500'])
    df['Fecha'] = pd.to_datetime(df['Fecha'])
    df.set_index('Fecha', inplace=True)
    df.index = df.index.date

    return df

def save_to_json(data):
    with open('bcra_data_backup.json', 'w') as file:
        json.dump({key: value[~value.index.duplicated(keep='first')].to_json(orient='index', date_format='iso') for key, value in data.items()}, file)

def load_from_json():
    with open('bcra_data_backup.json', 'r') as file:
        data_json = json.load(file)
        return {key: pd.read_json(io.StringIO(value), orient='index').rename_axis('fecha').reset_index().set_index('fecha') for key, value in data_json.items()}

def main():
    try:
        data = load_from_json()
        if 'uva' in data:
            data['UVA'] = data.pop('uva')
        if 'cer' in data:
            data['CER'] = data.pop('cer')

        a3500_df = data['a3500'].reset_index()
        a3500_new_df.rename(columns={"valor": "tca3500"}, inplace=True)
        a3500_df.columns = ['fecha', 'tca3500']
        a3500_new_df_fus = a3500_new_df[['fecha', 'tca3500']]
        combined_df_a3500 = pd.concat([a3500_df, a3500_new_df_fus])
        combined_df_a3500['fecha'] = pd.to_datetime(combined_df_a3500['fecha']).dt.date
        combined_df_a3500 = combined_df_a3500.sort_values(by='fecha').set_index('fecha')
        combined_df_a3500 = combined_df_a3500[~combined_df_a3500.index.duplicated(keep='first')]
        print(f"El último dólar A3500: {combined_df_a3500.iloc[-1]}")

        badlar_df = data['badlar'].reset_index()
        badlar_new_df.rename(columns={"valor": "BADLAR"}, inplace=True)
        badlar_df.columns = ['fecha', 'BADLAR']
        badlar_new_df_fus = badlar_new_df[['fecha', 'BADLAR']]
        combined_df_badlar = pd.concat([badlar_df, badlar_new_df_fus])
        combined_df_badlar['fecha'] = pd.to_datetime(combined_df_badlar['fecha']).dt.date
        combined_df_badlar = combined_df_badlar.sort_values(by='fecha').set_index('fecha')
        combined_df_badlar = combined_df_badlar[~combined_df_badlar.index.duplicated(keep='first')]
        print(f"El último Badlar: {combined_df_badlar.iloc[-1]}")
        badlar_aplicable = combined_df_badlar.tail(5)["BADLAR"].mean()
        print(f"Badlar aplicable: {badlar_aplicable}")

        cer_df = data['CER'].reset_index()
        cer_new_df.rename(columns={"valor": "CER"}, inplace=True)
        cer_df.columns = ['fecha', 'CER']
        cer_new_df_fus = cer_new_df[['fecha', 'CER']]
        combined_df_cer = pd.concat([cer_df, cer_new_df_fus])
        combined_df_cer['fecha'] = pd.to_datetime(combined_df_cer['fecha']).dt.date
        combined_df_cer = combined_df_cer.sort_values(by='fecha').set_index('fecha')
        combined_df_cer = combined_df_cer[~combined_df_cer.index.duplicated(keep='first')]
        print(f"El último dólar CER: {combined_df_cer.iloc[-1]}")

        #inflamom_df = data['inflamom'].reset_index() aca traia la data arrastrando proyeccion + barrido de api
        try:
            # Intentar convertir la fecha
            ultima_fecha_dato_inflamom_segun_api = datetime.strptime(inflamom_new_df.iloc[-1]['fecha'], '%Y-%m-%d')
            if pd.isna(ultima_fecha_dato_inflamom_segun_api):
                raise ValueError("Fecha es NaN, probable error de API BCRA!!!!!!!!!!!!")
        except (ValueError, IndexError):
            # Si hay un error o la fecha es NaN, usar la fecha de hoy menos 30 días
            ultima_fecha_dato_inflamom_segun_api = datetime.today() - timedelta(days=30)
        inflamom_df = data['inflamom'].reset_index().loc[data['inflamom'].index <= ultima_fecha_dato_inflamom_segun_api]

        inflamom_new_df.rename(columns={"valor": "inflacionmom"}, inplace=True)
        inflamom_df.columns = ['fecha', 'inflacionmom']
        inflamom_new_df_fus = inflamom_new_df[['fecha', 'inflacionmom']]
        combined_df_inflamom = pd.concat([inflamom_df, inflamom_new_df_fus])
        combined_df_inflamom['fecha'] = pd.to_datetime(combined_df_inflamom['fecha']).dt.date
        combined_df_inflamom = combined_df_inflamom.sort_values(by='fecha').set_index('fecha')
        combined_df_inflamom = combined_df_inflamom[~combined_df_inflamom.index.duplicated(keep='first')]
        print(f"El último dato inflación MOM: {combined_df_inflamom.iloc[-1]}")

        uva_df = data['UVA'].reset_index()
        uva_new_df.rename(columns={"valor": "UVA"}, inplace=True)
        uva_df.columns = ['fecha', 'UVA']
        uva_new_df_fus = uva_new_df[['fecha', 'UVA']]
        combined_df_uva = pd.concat([uva_df, uva_new_df_fus])
        combined_df_uva['fecha'] = pd.to_datetime(combined_df_uva['fecha']).dt.date
        combined_df_uva = combined_df_uva.sort_values(by='fecha').set_index('fecha')
        combined_df_uva = combined_df_uva[~combined_df_uva.index.duplicated(keep='first')]
        print(f"El último UVA: {combined_df_uva.iloc[-1]}")


        proyeccion_inflacion_mensual = { 'Jan-25': 2.5, 'Feb-25': 1.7, 'Mar-25': 1.9,
                                'Apr-25': 1.6, 'May-25': 1.3, 'Jun-25': 1.3 ,
                                'Jul-25': 1.1, 'Aug-25': 1.3, 'Sep-25': 1.3,
                                'Oct-25': 1.2, 'Nov-25': 1.2, 'Dec-25': 1.2,
                                'Jan-26': 1.0, 'Feb-26': 1.1, 'Mar-26': 1,
                                'Apr-26': 0.7, 'May-26': 0.5, 'Jun-26': 0.4 ,
                                'Jul-26': 0.4, 'Aug-26': 0.4, 'Sep-26': 0.4,
                                'Oct-26': 0.4, 'Nov-26': 0.4, 'Dec-26': 0.4,
                                'Jan-27': 0.4, 'Feb-27': 0.4, 'Mar-27': 0.4,
                                'Apr-27': 0.5, 'May-27': 0.5, 'Jun-27': 0.5 ,
                                'Jul-27': 0.5, 'Aug-27': 0.5, 'Sep-27': 0.5,
                                'Oct-27': 0.5, 'Nov-27': 0.5, 'Dec-27': 0.5,
                                'Jan-28': 0.5, 'Feb-28': 0.5, 'Mar-28': 0.5,
                                'Apr-28': 0.5, 'May-28': 0.5, 'Jun-28': 0.5 ,
                                'Jul-28': 0.5, 'Aug-28': 0.5, 'Sep-28': 0.5,
                                'Oct-28': 0.5, 'Nov-28': 0.5, 'Dec-28': 0.5
                                }

        proyeccion_inflacion_mensual_df = pd.DataFrame(list(proyeccion_inflacion_mensual.items()), columns=['d', 'inflacionmomproy'])
        proyeccion_inflacion_mensual_df['d'] = pd.to_datetime(proyeccion_inflacion_mensual_df['d'], format='%b-%y').dt.strftime('%Y-%m-%d')
        proyeccion_inflacion_mensual_df.set_index('d', inplace=True)
        proyeccion_inflacion_mensual_df.index = pd.to_datetime(proyeccion_inflacion_mensual_df.index).to_period('M').to_timestamp('M').date
        proyeccion_inflacion_mensual_df.rename(columns={'inflacionmomproy': 'inflacionmom'}, inplace=True)
        proyeccion_inflacion_mensual_df.sort_index(inplace=True)
        proyeccion_inflacion_mensual_df.index.name = 'fecha'
        df_inflamom_combinado = proyeccion_inflacion_mensual_df.combine_first(combined_df_inflamom)
        # df_inflamom_combinado = pd.concat([proyeccion_inflacion_mensual_df, combined_df_inflamom]) old porque tenia datos repetidos de la base vs proy
        df_inflamom_combinado.sort_index(inplace=True)
        df_inflamom_combinado.index = pd.to_datetime(df_inflamom_combinado.index)

        cer_inicial = combined_df_cer['CER'].iloc[-1]
        fecha_inicial = combined_df_cer.index[-1]
        df_cer_proyectado = calcular_CER_diario_proyectado(df_inflamom_combinado, cer_inicial, fecha_inicial)

        cer_completo_escenario_base = pd.concat([combined_df_cer.iloc[:-1], df_cer_proyectado], axis=0)
        cer_completo_escenario_base.to_csv('cer_completo.csv', header=['Proyeccion CER'])

        hoy = combined_df_badlar.index[-1]
        inicio_fechas_futuras = hoy + pd.Timedelta(days=1)
        fechas_futuras = pd.date_range(inicio_fechas_futuras, periods=30*365, freq='D')
        fechas_futuras_habiles = np.array([fecha for fecha in fechas_futuras if fecha.weekday() < 5 and fecha.strftime('%Y-%m-%d') not in dias_habiles.ar_holidays], dtype='datetime64[D]')
        nuevos_datos = pd.DataFrame({'d': fechas_futuras_habiles, 'BADLAR': [badlar_aplicable] * len(fechas_futuras_habiles)})
        nuevos_datos.set_index("d", inplace=True)
        nuevos_datos.index = nuevos_datos.index.date
        badlar_serie_completa = pd.concat([combined_df_badlar, nuevos_datos])

        fecha_inicial = data['a3500'].index[-1].strftime('%Y-%m-%d')
        valor_inicial = data['a3500'].iloc[-1].iloc[0]
        proyeccion_devaoficial_escenariobase = {
            '2024-11-30': 1017, '2024-12-31': 1046.5, '2025-01-31': 1080.5, '2025-02-28': 1106,
            '2025-03-31': 1131, '2025-04-30': 1154, '2025-05-31': 1173, '2025-06-30': 1190.5,
            '2025-07-31': 1213, '2025-08-31': 1230, '2025-09-30': 1258, '2025-10-31': 1258*1.013,
            '2025-11-30': 1258*1.013*1.011, '2025-12-31': 1258*1.013*1.011*1.01, '2026-01-31': 1258*1.013*1.011*1.01*1.01, '2026-02-28': 1258*1.013*1.011*1.01*1.01*1.01,
            '2026-03-31': 1258*1.013*1.011*(1.01**4), '2026-04-30': 1258*1.013*1.011*(1.01**5), '2026-05-31': 1258*1.013*1.011*(1.01**6), '2026-06-30': 1258*1.013*1.011*(1.01**7),
            '2026-07-31': 1258*1.013*1.011*(1.01**8), '2026-08-31': 1258*1.013*1.011*(1.01**9)*(1.005), '2026-09-30': 1258*1.013*1.011*(1.01**5)*(1.005**2)}
        a3500_proy_escenario_base = proyectadeva(proyeccion_devaoficial_escenariobase, fecha_inicial, valor_inicial)
        a3500_completo_escenario_base = pd.concat([df for df in [data['a3500'], a3500_proy_escenario_base] if not df.empty], axis=0)
        a3500_proy_escenario_base.to_csv('a3500completo.csv', header=['Proyeccion A3500'])

        data = {'a3500': combined_df_a3500, 'badlar': combined_df_badlar, 'CER': combined_df_cer, 'a3500_proyectado': a3500_completo_escenario_base, 'badlar_proyectado': badlar_serie_completa, 'cer_proyectado': cer_completo_escenario_base, 'UVA': combined_df_uva, 'inflamom': df_inflamom_combinado}
        save_to_json(data)
    except (requests.exceptions.RequestException, URLError) as e:
        print(f"Error al obtener datos de la API: {e}")
        if os.path.exists('bcra_data_backup.json'):
            data = load_from_json()
            print("Datos cargados desde el archivo JSON de respaldo.")
        else:
            print("No hay datos de respaldo disponibles.")
            data = None

    return data

if __name__ == '__main__':
    data = main()


# data['a3500_proyectado']


# data['a3500_proyectado']['2023-09-18':'2023-09-22']
