#%% Imports
# Imports

from utils import *
import dias_habiles
import urllib3

# Desactiva la advertencia al usar verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


#%% API V 3.0 BCRA. Setting functions
# Funciones

# Fetch de data con nuevas implementaciones de la api
def fetch_variable_data_api_v3(id_variable, fecha_desde, fecha_hasta, offset=None, limit=None):
    """
    Obtiene datos de una variable (id_variable) desde 'fecha_desde' hasta 'fecha_hasta'
    usando la API v3 de Principales Variables del BCRA.

    Parámetros:
    -----------
    id_variable : int
        ID de la variable a consultar (por ej., 5 corresponde a la serie A3500 según el doc).
    fecha_desde : str
        Fecha inicial en formato 'AAAA-MM-DD'.
    fecha_hasta : str
        Fecha final en formato 'AAAA-MM-DD'.
    offset : int, opcional
        Desplazamiento (cuántos registros saltar). Si no se especifica, se omite el parámetro.
    limit : int, opcional
        Límite máximo de registros a traer. Si no se especifica, se omite el parámetro.

    Retorna:
    --------
    pd.DataFrame o None
        DataFrame con los datos solicitados o None en caso de error.
    """

    # Endpoint base (según lo indicado en el PDF principales-variables-v3.pdf)
    base_url = "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"

    # Construimos la URL agregando el ID de la variable como parte del path
    url = f"{base_url}/{id_variable}"

    # Construimos los parámetros de query
    # (el PDF indica fecha_desde y fecha_hasta; si se llaman distinto, cámbialos)
    params = {
        "desde": fecha_desde,
        "hasta": fecha_hasta
    }

    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    try:
        # Hacemos la solicitud GET con un tiempo de espera (timeout)
        # verify=True recomendado en producción para validar el certificado SSL
        response = requests.get(url, params=params, verify=False, timeout=20)
        response.raise_for_status()  # Lanza excepción si el status_code es 4xx o 5xx

        # Parseamos el contenido como JSON
        data = response.json()

        # Revisar la estructura que describe el PDF. Por lo general:
        # {
        #    "metadata": {
        #       "offset": ...,
        #       "limit": ...,
        #       "total_count": ...
        #    },
        #    "results": [
        #       { "fecha": "2023-01-01", "valor": 123.45 },
        #       ...
        #    ]
        # }
        #
        # Validamos si tenemos la clave "data"
        if "results" in data:
            # Extraemos la sección de datos
            results = data["results"]

            if isinstance(results, list) and len(results) > 0:
                # Creamos un DataFrame con esos registros
                df = pd.DataFrame(results)
                # Asegurar que las columnas "fecha" y "valor" existan según el doc
                return df
            else:
                print("No se encontraron registros en 'resykts'.")
                return None
        else:
            # Si la API maneja errores dentro de la respuesta, revisa el PDF
            # En el doc, si hay un error, generalmente se envía un 4xx/5xx
            # (lo cual se capturaría en raise_for_status).
            # Aquí capturamos cualquier estructura inesperada.
            print("La clave 'data' no está presente en la respuesta.")
            return None

    except requests.exceptions.Timeout:
        print("La solicitud a la API excedió el tiempo de espera (timeout).")
        return None
    except requests.exceptions.RequestException as e:
        # Captura errores de conexión, DNS, etc.
        print(f"Ocurrió un error al realizar la solicitud: {e}")
        return None
    except ValueError:
        # Si el response no es JSON válido, se lanza ValueError en response.json()
        print("La respuesta de la API no es un JSON válido.")
        return None

# listado de variables disponibles:
def fetch_principales_variables():
    url = "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias/"
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

# Funciones extras
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

# Intentamos leer el backup para reducir la ventana de consulta a la API
try:
    _bcra_backup = load_from_json()
    # Normalizamos nombres de claves por las dudas
    if 'uva' in _bcra_backup and 'UVA' not in _bcra_backup:
        _bcra_backup['UVA'] = _bcra_backup.pop('uva')
    if 'cer' in _bcra_backup and 'CER' not in _bcra_backup:
        _bcra_backup['CER'] = _bcra_backup.pop('cer')
except FileNotFoundError:
    _bcra_backup = {}

def _calcular_start_date_por_backup(default_days_back: int = 365) -> str:
    """
    Usa la última fecha disponible en el backup (a3500/badlar/CER/UVA)
    para pedir solo datos nuevos a la API. Si no hay backup, retrocede
    default_days_back días.
    """
    if not _bcra_backup:
        return (datetime.now() - timedelta(days=default_days_back)).strftime("%Y-%m-%d")

    candidatos = []
    for k in ("a3500", "badlar", "CER", "UVA"):
        if k in _bcra_backup and not _bcra_backup[k].empty:
            candidatos.append(_bcra_backup[k].index.max())

    if not candidatos:
        return (datetime.now() - timedelta(days=default_days_back)).strftime("%Y-%m-%d")

    ultima_fecha = max(pd.to_datetime(candidatos)).date()
    nueva_fecha = ultima_fecha + timedelta(days=1)
    hoy = datetime.now().date()

    # Si por alguna razón la última fecha es >= hoy, no tiene sentido pedir futuro
    if nueva_fecha > hoy:
        nueva_fecha = hoy

    return nueva_fecha.strftime("%Y-%m-%d")


#%% Usos, aplicaciones y proyecciones
# Usos, aplicaciones y proyecciones

'''
# ROFEX DATA simply
csv_rfx_url = "https://docs.google.com/spreadsheets/d/1j-ZrWBO-fCkGUPqWtWRsGgGswMRCm2mnMhsPmX6osLI/export?format=csv&gid=2027743157"
rfx = pd.read_csv(csv_rfx_url, header=2)
# Filtros o Masks
mask_dlr = rfx["Producto"] == "DLR"
mask_futuro = rfx["Tipo de Instrumento"] == "Futuro"
# Filtro y copia
rfx_filtrado = rfx[mask_dlr & mask_futuro].copy()
# Formato datetime para las fechas ya filtrado
rfx_filtrado["Fecha de Vencimiento"] = pd.to_datetime(
    rfx_filtrado["Fecha de Vencimiento"],
    dayfirst=True)
rfx_filtrado["Ajuste/Valor teórico"] = pd.to_numeric(rfx_filtrado["Ajuste/Valor teórico"].str.replace(',', '.'), errors='coerce')
# Diccionario Proyeccioncon .dt.strftime() para formatear 'YYYY-MM-DD'
proyeccion_devaluacion_rofex = dict(zip(
    rfx_filtrado["Fecha de Vencimiento"].dt.strftime("%Y-%m-%d"),
    rfx_filtrado["Ajuste/Valor teórico"]
))
'''


## BLOQUE PRINCIPALES VARIABLES

# Crea variable con la lista de principales variables
principales_variables_df = fetch_principales_variables()
if principales_variables_df is None:
    print("ERROR! No se pudieron obtener las principales variables.")
    # Dejo un DataFrame vacío para que, si alguien lo usa,
    # no rompa por estar en None.
    principales_variables_df = pd.DataFrame()

# ─────────────────────────────────────────────
# Principales Variables BCRA (con fallback)
# ─────────────────────────────────────────────

# Setup de fechas usando el backup como cache: pedimos solo datos nuevos
'''
old:
# Setup de fechas: por ahora usamos un start_date genérico.
# Debajo lo vamos a redefinir para que sea más eficiente.
start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
end_date = datetime.now().strftime("%Y-%m-%d")

'''
start_date = _calcular_start_date_por_backup(default_days_back=365)
end_date = datetime.now().strftime("%Y-%m-%d")


def _df_vacio_bcra():
    # DataFrame vacío con las columnas esperadas por main()
    return pd.DataFrame(columns=["fecha", "valor"])

# A3500:
idVariable = 5
a3500_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if a3500_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable A3500. Usando solo datos del backup.")
    a3500_new_df = _df_vacio_bcra()

# BADLAR:
idVariable = 7
badlar_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if badlar_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable BADLAR. Usando solo datos del backup.")
    badlar_new_df = _df_vacio_bcra()

# TAMAR:
idVariable = 44
tamar_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if tamar_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable TAMAR. Usando solo datos del backup.")
    tamar_new_df = _df_vacio_bcra()

# POMO:
idVariable = 6
pomo_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if pomo_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable POMO. Usando solo datos del backup.")
    pomo_new_df = _df_vacio_bcra()

# CER:
idVariable = 30
cer_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if cer_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable CER. Usando solo datos del backup.")
    cer_new_df = _df_vacio_bcra()

# INFLAMOM:
idVariable = 27
inflamom_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if inflamom_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable INFLAMOM. Usando solo datos del backup.")
    inflamom_new_df = _df_vacio_bcra()

# UVA:
idVariable = 31
uva_new_df = fetch_variable_data_api_v3(idVariable, start_date, end_date)
if uva_new_df is None:
    print("ERROR: No se pudieron obtener los datos de la variable UVA. Usando solo datos del backup.")
    uva_new_df = _df_vacio_bcra()

###### ...---... Proyecciones ...---... #######

proyeccion_inflacion_mensual = {
    "Oct-25": 2.3,
    "Nov-25": 1.8,
    "Dec-25": 1.7,
    "Jan-26": 1.7,
    "Feb-26": 1.4,
    "Mar-26": 1.8,
    "Apr-26": 1.3,
    "May-26": 1.3,
    "Jun-26": 1.5,
    "Jul-26": 1.3,
    "Aug-26": 0.9,
    "Sep-26": 1.2,
    "Oct-26": 1.2,
    "Nov-26": 1.1,
    "Dec-26": 1.3,
    "Jan-27": 1.1,
    "Feb-27": 1.0,
    "Mar-27": 0.9,
    "Apr-27": 0.7,
    "May-27": 0.6,
    "Jun-27": 0.5,
    "Jul-27": 0.5,
    "Aug-27": 0.5,
    "Sep-27": 0.5,
    "Oct-27": 0.5,
    "Nov-27": 0.5,
    "Dec-27": 0.5,
    "Jan-28": 0.5,
    "Feb-28": 0.5,
    "Mar-28": 0.5,
    "Apr-28": 0.5,
    "May-28": 0.5,
    "Jun-28": 0.5,
    "Jul-28": 0.5,
    "Aug-28": 0.5,
    "Sep-28": 0.5,
    "Oct-28": 0.5,
    "Nov-28": 0.5,
    "Dec-28": 0.5,
    "Jan-29": 0.5,
    "Feb-29": 0.5,
    "Mar-29": 0.5,
    "Apr-29": 0.5,
    "May-29": 0.5,
    "Jun-29": 0.5,
    "Jul-29": 0.5,
    "Aug-29": 0.5,
    "Sep-29": 0.5,
    "Oct-29": 0.5,
    "Nov-29": 0.5,
    "Dec-29": 0.5,
    "Jan-30": 0.5,
    "Feb-30": 0.5,
    "Mar-30": 0.4,
    "Apr-30": 0.4,
    "May-30": 0.4,
    "Jun-30": 0.35,
    "Jul-30": 0.35,
    "Aug-30": 0.35,
    "Sep-30": 0.35,
    "Oct-30": 0.35,
    "Nov-30": 0.35,
    "Dec-30": 0.35
}


proyeccion_devaoficial_escenariobase = {
    '2025-06-30': 1145.00,
    '2025-07-31': 1160.00,
    '2025-08-29': 1178.00,
    '2025-09-30': 1198.00,
    '2025-10-31': 1225.50,
    '2025-11-28': 1248.00,
    '2025-12-30': 1270,
    '2026-01-30': 1270,
    '2026-02-27': 1270,
    '2026-03-31': 1270,
    '2026-04-30': 1270,
    '2026-05-29': 1270,
    '2026-06-30': 1270,
    '2026-07-31': 1270,
    '2026-08-31': 1270,
    '2026-09-30': 1270,
    '2026-10-31': 1270,
    '2026-11-30': 1270}

#proyeccion_devaluacion_rofex


#%% Aplicación final main
# Aplicación final main

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


        tamar_new_df.rename(columns={"valor": "TAMAR"}, inplace=True)
        tamar_df = tamar_new_df[['fecha', 'TAMAR']].set_index('fecha').reset_index('fecha')
        tamar_df.columns = ['fecha', 'TAMAR']
        tamar_new_df_fus = tamar_new_df[['fecha', 'TAMAR']]
        combined_df_tamar = pd.concat([tamar_df, tamar_new_df_fus])
        combined_df_tamar['fecha'] = pd.to_datetime(combined_df_tamar['fecha']).dt.date
        combined_df_tamar = combined_df_tamar.sort_values(by='fecha').set_index('fecha')
        combined_df_tamar = combined_df_tamar[~combined_df_tamar.index.duplicated(keep='first')]
        print(f"El último Tamar: {combined_df_tamar.iloc[-1]}")
        tamar_aplicable = combined_df_tamar.tail(5)["TAMAR"].mean()
        tamar_aplicable_10d = combined_df_tamar.tail(10)["TAMAR"].mean()
        tamar_aplicable_tem = 100*(((1+((tamar_aplicable_10d/100)/(365/32)))**(365/32))**(1/12)-1)
        print(f"Tamar aplicable 5d: {tamar_aplicable}")
        print(f"Tamar aplicable 10d: {tamar_aplicable_10d}")
        print(f"Tamar aplicable 10d tem: {tamar_aplicable_tem}")

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

        uva_completo_escenario_base = cer_completo_escenario_base*2.5217
        uva_completo_escenario_base.rename(columns={"CER": "UVA"}, inplace=True)

        hoy = combined_df_badlar.index[-1]
        inicio_fechas_futuras = hoy + pd.Timedelta(days=1)
        fechas_futuras = pd.date_range(inicio_fechas_futuras, periods=30*365, freq='D')
        fechas_futuras_habiles = np.array([fecha for fecha in fechas_futuras if fecha.weekday() < 5 and fecha.strftime('%Y-%m-%d') not in dias_habiles.ar_holidays], dtype='datetime64[D]')
        nuevos_datos = pd.DataFrame({'d': fechas_futuras_habiles, 'BADLAR': [badlar_aplicable] * len(fechas_futuras_habiles)})
        nuevos_datos.set_index("d", inplace=True)
        nuevos_datos.index = nuevos_datos.index.date
        badlar_serie_completa = pd.concat([combined_df_badlar, nuevos_datos])

        hoy2 = combined_df_tamar.index[-1]
        inicio_fechas_futuras = hoy2 + pd.Timedelta(days=1)
        fechas_futuras = pd.date_range(inicio_fechas_futuras, periods=30*365, freq='D')
        fechas_futuras_habiles = np.array([fecha for fecha in fechas_futuras if fecha.weekday() < 5 and fecha.strftime('%Y-%m-%d') not in dias_habiles.ar_holidays], dtype='datetime64[D]')
        nuevos_datos = pd.DataFrame({'d': fechas_futuras_habiles, 'TAMAR': [tamar_aplicable] * len(fechas_futuras_habiles)})
        nuevos_datos.set_index("d", inplace=True)
        nuevos_datos.index = nuevos_datos.index.date
        tamar_serie_completa = pd.concat([combined_df_tamar, nuevos_datos])

        fecha_inicial = data['a3500'].index[-1].strftime('%Y-%m-%d')
        valor_inicial = data['a3500'].iloc[-1].iloc[0]
        '''
        proyeccion_devaoficial_escenariobase = {
            '2024-11-30': 1017, '2024-12-31': 1046.5, '2025-01-31': 1080.5, '2025-02-28': 1106,
            '2025-03-31': 1131, '2025-04-30': 1154, '2025-05-31': 1173, '2025-06-30': 1190.5,
            '2025-07-31': 1213, '2025-08-31': 1230, '2025-09-30': 1258, '2025-10-31': 1258*1.013,
            '2025-11-30': 1258*1.013*1.011, '2025-12-31': 1258*1.013*1.011*1.01, '2026-01-31': 1258*1.013*1.011*1.01*1.01, '2026-02-28': 1258*1.013*1.011*1.01*1.01*1.01,
            '2026-03-31': 1258*1.013*1.011*(1.01**4), '2026-04-30': 1258*1.013*1.011*(1.01**5), '2026-05-31': 1258*1.013*1.011*(1.01**6), '2026-06-30': 1258*1.013*1.011*(1.01**7),
            '2026-07-31': 1258*1.013*1.011*(1.01**8), '2026-08-31': 1258*1.013*1.011*(1.01**9)*(1.005), '2026-09-30': 1258*1.013*1.011*(1.01**5)*(1.005**2)}
        '''
        a3500_proy_escenario_base = proyectadeva(proyeccion_devaoficial_escenariobase, fecha_inicial, valor_inicial)
        a3500_completo_escenario_base = pd.concat([df for df in [data['a3500'], a3500_proy_escenario_base] if not df.empty], axis=0)
        a3500_proy_escenario_base.to_csv('a3500completo.csv', header=['Proyeccion A3500'])

        data = {'a3500': combined_df_a3500, 'badlar': combined_df_badlar, 'tamar': combined_df_tamar,  'CER': combined_df_cer, 'a3500_proyectado': a3500_completo_escenario_base, 'badlar_proyectado': badlar_serie_completa, 'tamar_proyectado': tamar_serie_completa ,'cer_proyectado': cer_completo_escenario_base, 'UVA': combined_df_uva,'uva_proyectado': uva_completo_escenario_base, 'inflamom': df_inflamom_combinado}
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


