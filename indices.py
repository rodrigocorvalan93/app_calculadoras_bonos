# %%
from utils import *
import dias_habiles

#Last version
BCRA_API_URL = "https://api.estadisticasbcra.com/"
TOKEN = "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3MzgwODgwODcsInR5cGUiOiJleHRlcm5hbCIsInVzZXIiOiJyb2RyaWdvLmNvcnZhbGFuQGRlbHRhYW0uY29tLmFyIn0.qgsJs4coY9SjNd-JZ6homWUwcDBQW5XQyr9Lzgi26NediJb0GHaPPCNFDHmT21tN60v0YzspJl-8t7IAYT6pPw"  # Reemplaza esto con tu token de acceso a la API del BCRA
HEADERS = {"Authorization": f"BEARER {TOKEN}"}

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


def calcular_CER_diario_proyectado(df_inflamom, cer_inicial, fecha_inicial):
    """
    Calcula el CER diario proyectado desde una fecha inicial hasta el final del DataFrame de inflación.

    Parámetros:
    df_inflamom (DataFrame): DataFrame que contiene los datos de inflación mensual.
    cer_inicial (float): Valor inicial del CER.
    fecha_inicial (str): Fecha inicial desde la cual se proyectará el CER.

    Retorna:
    DataFrame: Un DataFrame con el CER calculado para cada día desde la fecha inicial hasta el final del rango de datos de inflación.
    """

    # Convertir la fecha inicial en un objeto datetime
    fecha_inicial = pd.to_datetime(fecha_inicial)

    # Verificar si la fecha inicial está dentro del rango del DataFrame de inflación
    if fecha_inicial not in pd.date_range(start=df_inflamom.index.min(), end=df_inflamom.index.max()):
        raise ValueError("La fecha inicial está fuera del rango del DataFrame de inflación.")

    # Crear un rango de fechas que comience desde la fecha inicial y termine al final del DataFrame de inflación
    rango_fechas = pd.date_range(start=fecha_inicial, end=df_inflamom.index.max() + MonthEnd(1), freq='D')

    # Inicializar el DataFrame de CER
    df_cer = pd.DataFrame(index=rango_fechas, columns=['CER'])
    df_cer.iloc[0, df_cer.columns.get_loc('CER')] = cer_inicial  # Establecer el valor inicial de CER

    # Calcular CER para cada día
    for fecha in rango_fechas[1:]:
        # Calcular los períodos mensuales anteriores
        j_1 = (fecha - pd.DateOffset(months=1)).to_period('M')
        j_2 = (fecha - pd.DateOffset(months=2)).to_period('M')

        # Calcular el número de días en el mes actual y el mes anterior
        k = pd.Period(fecha, freq='M').days_in_month
        k_1 = pd.Period(fecha - pd.DateOffset(months=1), freq='M').days_in_month

        # Determinar el factor F(t) basado en la regla del día 15
        if fecha.day <= 15:
            F_t = (1 + df_inflamom['inflacion'].iloc[df_inflamom.index.to_period('M').get_loc(j_2)]/100) ** (1/k_1)
        else:
            F_t = (1 + df_inflamom['inflacion'].iloc[df_inflamom.index.to_period('M').get_loc(j_1)]/100) ** (1/k)

        # Calcular y actualizar el CER para el día actual
        df_cer.loc[fecha, 'CER'] = df_cer.loc[fecha - pd.DateOffset(days=1), 'CER'] * F_t

    # Index como date
    df_cer.index = df_cer.index.date

    return df_cer



def proyectadeva(proyeccion_mensual, fecha_inicial, valor_inicial):
    serie_temporal = []

    # Ordena las fechas en orden ascendente
    fechas = sorted(proyeccion_mensual.keys())

    # Convierte las fechas a objetos datetime
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
        json.dump({key: value.to_json(orient='index', date_format='iso') for key, value in data.items()}, file)

def load_from_json():
    with open('bcra_data_backup.json', 'r') as file:
        data_json = json.load(file)
        return {key: pd.read_json(io.StringIO(value), orient='index').rename_axis('fecha').reset_index().set_index('fecha') for key, value in data_json.items()}


def main():
    try:
        '''
        # Bajar y mostrar datos A3500
        a3500 = pd.read_excel(
            'http://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/com3500.xls',
            sheet_name='TCR diario y TCNPM', usecols="C,D", index_col=0,
            skiprows=4, header=None, parse_dates=True,
            names=['fecha','tca3500'])
        print(f"El último dólar A3500: {a3500.iloc[-1]}")
        '''
        # Bajar y mostrar datos USD A3500
        a3500 = fetch_bcra_data("usd_of")
        if a3500 is not None:
            print("API BCRA OK (a3500)")
            a3500.rename(columns={"v": "tca3500"}, inplace=True)
            print(f"El último dólar A3500: {a3500.iloc[-1]}")


        # Bajar y mostrar datos BADLAR
        badlar = fetch_bcra_data("tasa_badlar")
        if badlar is not None:
            print("API BCRA OK (badlar)")
            badlar.rename(columns={"v": "BADLAR"}, inplace=True)
            print(f"El último Badlar: {badlar.iloc[-1]}")
            badlar_aplicable = badlar.tail(5)["BADLAR"].mean()
            print(f"Badlar aplicable: {badlar_aplicable}")

        # Bajar y mostrar datos CER
        cer = fetch_bcra_data("cer")
        if cer is not None:
            print("API BCRA OK (CER)")
            cer.rename(columns={"v": "CER"}, inplace=True)
            print(f"El último CER: {cer.iloc[-1]}")

        # Bajar y mostrar datos inflación MoM
        inflamom = fetch_bcra_data("inflacion_mensual_oficial")
        if inflamom is not None:
            print("API BCRA OK (inflacionmom)")
            inflamom.rename(columns={"v": "inflacionmom"}, inplace=True)
            print(f"El último dato inflación MOM: {inflamom.iloc[-1]}")


        # Proyección CER
        # Definir las tasas de inflación mensual y las fechas iniciales
        #  -------------SANDBOX para proyectar CER:------------. Acá se aplican las proyecciones: (esto es importante para barby, esto )
        '''
        proyeccion_inflacion_mensual = {'Mar-24': 13,
                                        'Apr-24': 11, 'May-24': 8, 'Jun-24': 7 ,
                                        'Jul-24': 6, 'Aug-24': 6, 'Sep-24': 6,
                                        'Oct-24': 6, 'Nov-24': 6, 'Dec-24': 3.92,
                                        'Jan-25': 3.92, 'Feb-25': 3.92, 'Mar-25': 3.92,
                                        'Apr-25': 3.92, 'May-25': 3.92, 'Jun-25': 3.92 ,
                                        'Jul-25': 3.92, 'Aug-25': 3.92, 'Sep-25': 3.92,
                                        'Oct-25': 3.92, 'Nov-25': 3.92, 'Dec-25': 3.92,
                                        'Jan-26': 1.1, 'Feb-26': 1.1, 'Mar-26': 1,
                                        'Apr-26': 0.9, 'May-26': 0.7, 'Jun-26': 0.6 ,
                                        'Jul-26': 0.5, 'Aug-26': 0.5, 'Sep-26': 0.5,
                                        'Oct-26': 0.5, 'Nov-26': 0.5, 'Dec-26': 0.5,
                                        'Jan-27': 0.5, 'Feb-27': 0.5, 'Mar-27': 0.5,
                                        'Apr-27': 0.5, 'May-27': 0.5, 'Jun-27': 0.5 ,
                                        'Jul-27': 0.5, 'Aug-27': 0.5, 'Sep-27': 0.5,
                                        'Oct-27': 0.5, 'Nov-27': 0.5, 'Dec-27': 0.5,
                                        'Jan-28': 0.5, 'Feb-28': 0.5, 'Mar-28': 0.5,
                                        'Apr-28': 0.5, 'May-28': 0.5, 'Jun-28': 0.5 ,
                                        'Jul-28': 0.5, 'Aug-28': 0.5, 'Sep-28': 0.5,
                                        'Oct-28': 0.5, 'Nov-28': 0.5, 'Dec-28': 0.5
                                        } # IMPORTANTE
        '''
        proyeccion_inflacion_mensual = {'Mar-24': 11,
                                'Apr-24': 8, 'May-24': 6, 'Jun-24': 4,
                                'Jul-24': 4.6, 'Aug-24': 3.9, 'Sep-24': 3.6,
                                'Oct-24': 3.1, 'Nov-24': 3, 'Dec-24': 3,
                                'Jan-25': 2.1, 'Feb-25': 2.8, 'Mar-25': 3.2,
                                'Apr-25': 2.2, 'May-25': 1.6, 'Jun-25': 1.3 ,
                                'Jul-25': 1, 'Aug-25': 0.9, 'Sep-25': 1,
                                'Oct-25': 1, 'Nov-25': 1, 'Dec-25': 1,
                                'Jan-26': 1.1, 'Feb-26': 1.1, 'Mar-26': 1,
                                'Apr-26': 0.9, 'May-26': 0.7, 'Jun-26': 0.6 ,
                                'Jul-26': 0.5, 'Aug-26': 0.5, 'Sep-26': 0.5,
                                'Oct-26': 0.5, 'Nov-26': 0.5, 'Dec-26': 0.5,
                                'Jan-27': 0.5, 'Feb-27': 0.5, 'Mar-27': 0.5,
                                'Apr-27': 0.5, 'May-27': 0.5, 'Jun-27': 0.5 ,
                                'Jul-27': 0.5, 'Aug-27': 0.5, 'Sep-27': 0.5,
                                'Oct-27': 0.5, 'Nov-27': 0.5, 'Dec-27': 0.5,
                                'Jan-28': 0.5, 'Feb-28': 0.5, 'Mar-28': 0.5,
                                'Apr-28': 0.5, 'May-28': 0.5, 'Jun-28': 0.5 ,
                                'Jul-28': 0.5, 'Aug-28': 0.5, 'Sep-28': 0.5,
                                'Oct-28': 0.5, 'Nov-28': 0.5, 'Dec-28': 0.5
                                } # IMPORTANTE


        # Traducción a DF
        proyeccion_inflacion_mensual_df = pd.DataFrame(list(proyeccion_inflacion_mensual.items()), columns=['d', 'inflacionmomproy'])
        proyeccion_inflacion_mensual_df['d'] = pd.to_datetime(proyeccion_inflacion_mensual_df['d'], format='%b-%y').dt.strftime('%Y-%m-%d')
        proyeccion_inflacion_mensual_df.set_index('d', inplace=True)
        # Ajustar las fechas para que sean fin de mes
        proyeccion_inflacion_mensual_df.index = pd.to_datetime(proyeccion_inflacion_mensual_df.index).to_period('M').to_timestamp('M').date
        # Empalme series
        proyeccion_inflacion_mensual_df.rename(columns={'inflacionmomproy': 'inflacion'}, inplace=True)
        inflamom.rename(columns={'inflacionmom': 'inflacion'}, inplace=True)
        df_inflamom_combinado = pd.concat([proyeccion_inflacion_mensual_df, inflamom])
        # Ordenar por fecha si es necesario
        df_inflamom_combinado.sort_index(inplace=True)
        df_inflamom_combinado.index = pd.to_datetime(df_inflamom_combinado.index)

        # Mostrar el DataFrame combinado print(df_inflamom_combinado)

        # Proyección
        cer_inicial = cer['CER'].iloc[-1]  # Reemplaza con el valor inicial real
        fecha_inicial = cer.index[-1]  # Reemplaza con la fecha inicial real
        df_cer_proyectado = calcular_CER_diario_proyectado(df_inflamom_combinado, cer_inicial, fecha_inicial)

        #print(df_cer_diario)

        #Combina proyección cer con dato (elimina [cer.iloc[:-1] el ultimo dato de cer ya que coincide con el primer dato de df_cer_proyectado)
        cer_completo_escenario_base = pd.concat([cer.iloc[:-1], df_cer_proyectado], axis=0) # dato + proy
        # Print Cer proy
        #df_cer_proyectado.to_csv('proycer.csv', header=['Proyeccion CER'])
        cer_completo_escenario_base.to_csv('cer_completo.csv', header=['Proyeccion CER'])

        # Proyección BADLAR
        # Crear una serie de fechas para los próximos 50 años
        hoy = badlar.index[-1]
        inicio_fechas_futuras = hoy + pd.Timedelta(days=1)
        fechas_futuras = pd.date_range(inicio_fechas_futuras, periods=30*365, freq='D')
        fechas_futuras_habiles = np.array([fecha for fecha in fechas_futuras if fecha.weekday() < 5 and fecha.strftime('%Y-%m-%d') not in dias_habiles.ar_holidays], dtype='datetime64[D]')
        # Crear un DataFrame con las fechas y el valor del último promedio de BADLAR
        nuevos_datos = pd.DataFrame({'d': fechas_futuras_habiles, 'BADLAR': [badlar_aplicable] * len(fechas_futuras_habiles)})
        nuevos_datos.set_index("d", inplace=True)
        nuevos_datos.index = nuevos_datos.index.date
        # Concatenar el DataFrame con los datos existentes
        badlar_serie_completa = pd.concat([badlar, nuevos_datos])


        # Proyección A3500
        # Hoy
        fecha_inicial = a3500.index[-1].strftime('%Y-%m-%d')
        valor_inicial = a3500['tca3500'].iloc[-1]
        # -------------SANDBOX para proyectar A3500:------------
        proyeccion_devaoficial_escenariobase = {'2024-01-31': 831.6, '2024-02-29': 870.4, '2024-03-27': 890.2, '2024-04-30':912.4, '2024-05-31':930.68} #fin de cada mes como los futuros
        a3500_proy_escenario_base = proyectadeva(proyeccion_devaoficial_escenariobase, fecha_inicial, valor_inicial)
        # Construye la serie temporal a3500 (aca puede haber conflicto futuro ya que en el futuro no se va a poder concatenar a3500 con la proyeccion si la misma tiene valores nulos)
        a3500_completo_escenario_base = pd.concat([a3500, a3500_proy_escenario_base], axis=0) # dato + proy
        # Print A3500 proy
        a3500_proy_escenario_base.to_csv('a3500completo.csv', header=['Proyeccion A3500'])

        data = {'a3500':a3500, 'badlar':badlar, 'cer':cer,'a3500_proyectado': a3500_completo_escenario_base, 'badlar_proyectado': badlar_serie_completa, 'cer_proyectado': cer_completo_escenario_base}
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

# %%
#data['a3500_proyectado']

# %%
#data['a3500_proyectado']['2023-09-18':'2023-09-22']


