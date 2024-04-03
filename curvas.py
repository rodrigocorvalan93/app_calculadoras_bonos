#%%
import rentafija
from utils import *
from especies import *

#Last version
#%% LEVANTA PRECIOS DE precios.xlsx
df = pd.read_excel("precios.xlsx")

# Inicializa la lista vacía
tires_precios = []

# Itera sobre las filas del DataFrame
for index, row in df.iterrows():
    bono = row['codigo']  # Asume que el nombre del bono está en la columna 'A'
    precio = row['precio_inputs']  # Asume que el precio está en la columna 'B'

    # Usa un enfoque de 'try-except' para manejar posibles errores
    try:
        # Evalúa dinámicamente la función para cada bono
        funcion_bono = eval(bono + ".calcula_tirea")
        tirea = funcion_bono(precio)
        tires_precios.append(tirea)
    except Exception as e:
        print(f"Error al procesar el bono {bono}: {e}")

# Ahora 'tires_precios' contiene los valores calculados
print(tires_precios)

# Curva DOLAR LINKED

# Filtrar bonos por la industria "Soberanos Dual" y "Soberanos Dolar Linked"
bonos_filtrados_dlduo = [bono for bono in todos_los_bonos if bono.industria in ["Soberanos Dual", "Soberanos Dolar Linked"]]

# Crear el diccionario con los códigos y precios (ejemplo de precios, ajusta según necesites)
inputs_dl = {
    "codigo": [bono.codigo for bono in bonos_filtrados_dlduo],
    "precio": [bono.precio for bono in bonos_filtrados_dlduo]  # Asegúrate de ajustar los precios correctamente
}

df_inputs_dl = rentafija.pd.DataFrame(inputs_dl)

# Dictionario de bonos objects en automatico:
bonos_dl = {bono.codigo: bono for bono in bonos_filtrados_dlduo}

curva_dl = []

# Calculating data for each bond
for index, row in df_inputs_dl.iterrows():
    codigo_bono = row['codigo']
    precio_bono = row['precio']

    if codigo_bono in bonos_dl:
        bono = bonos_dl[codigo_bono]
        resultado_aplicar_precio = bono.calcula_tirea(precio_bono)
        resultado_metodo_adicional = bono.calcula_duration(resultado_aplicar_precio)  # Adjust as per method definition
        curva_dl.append([codigo_bono, precio_bono, resultado_aplicar_precio, resultado_metodo_adicional, bono.paridad])
    else:
        print(f"No se encontró el bono con código: {codigo_bono}")

# Convert to DataFrame and sort
df_curva_dl = rentafija.pd.DataFrame(curva_dl, columns=['Codigo', 'Precio Input', 'TIREA', 'Duration', 'Paridad']).sort_values(by='Duration')
# Curva DL personalizado
df_curva_dl = df_curva_dl[df_curva_dl['Codigo'] != 'tdf24'].reset_index(drop=True)


print('Curva DL:\n', df_curva_dl)


# Curva CER

# Filtrar bonos por la industria "Soberano Inflación"
codigos_a_excluir = ['X20F4','TG25', 'T4X5', 'T3X5', 'T7X4']  # Reemplaza esto con los códigos reales que quieres excluir
# Filtrar la lista de bonos para excluir los que tienen los códigos en codigos_a_excluir
bonos_filtrados_cer = [bono for bono in todos_los_bonos if bono.codigo not in codigos_a_excluir and bono.industria in ["Soberano Inflación"]]


# Crear el diccionario con los códigos y precios (ejemplo de precios, ajusta según necesites)
inputs_cer = {
    "codigo": [bono.codigo for bono in bonos_filtrados_cer],
    "precio": [bono.precio for bono in bonos_filtrados_cer]  # Asegurarse de ajustar los precios correctamente
}

df_inputs_cer = rentafija.pd.DataFrame(inputs_cer)

# Dictionario de bonos objects
# en automatico:
bonos_cer = {bono.codigo: bono for bono in bonos_filtrados_cer}

curva_cer = []

# Calculating data for each bond
for index, row in df_inputs_cer.iterrows():
    codigo_bono = row['codigo']
    precio_bono = row['precio']

    if codigo_bono in bonos_cer:
        bono = bonos_cer[codigo_bono]

        try:
            resultado_aplicar_precio = bono.calcula_tirea(precio_bono)
            resultado_metodo_adicional = bono.calcula_duration(resultado_aplicar_precio)  # Adjust as per method definition
            curva_cer.append([codigo_bono, precio_bono, resultado_aplicar_precio, resultado_metodo_adicional, bono.paridad])
        except Exception as e:
            print(f"Error al procesar el bono con código {codigo_bono}: {e}")
            continue  # Esto hace que el ciclo siga con el siguiente bono

    else:
        print(f"No se encontró el bono con código: {codigo_bono}")

# Convert to DataFrame and sort
df_curva_cer = rentafija.pd.DataFrame(curva_cer, columns=['Codigo', 'Precio Input', 'TIREA', 'Duration', 'Paridad']).sort_values(by='Duration')

# Filtros personalizados CER
df_curva_cer = df_curva_cer[~((df_curva_cer['TIREA'] < df_curva_cer['TIREA'].mean() - 2 * df_curva_cer['TIREA'].std()) | (df_curva_cer['TIREA'] > df_curva_cer['TIREA'].mean() + 2 * df_curva_cer['TIREA'].std()))].reset_index(drop=True)
df_curva_cer = df_curva_cer[df_curva_cer['Codigo'] != 'TG25'].reset_index(drop=True) # extrae TG25
df_curva_cer = df_curva_cer[df_curva_cer['Codigo'] != 'TX25'].reset_index(drop=True)
df_curva_cer = df_curva_cer[df_curva_cer['Codigo'] != 'X18E4'].reset_index(drop=True)
df_curva_cer = df_curva_cer[df_curva_cer['Codigo'] != 'T7X4'].reset_index(drop=True)
df_curva_cer = df_curva_cer[df_curva_cer['Codigo'] != 'T3X5'].reset_index(drop=True)
print('Curva CER:\n', df_curva_cer)

# NSS CER
def to_percent(y, position):
    # Convertir el valor a porcentaje y formatearlo con 1 dígito decimal
    s = f"{100 * y:.1f}%"

    # Devolver el valor formateado
    return s

# Función de la Curva Nelson-Siegel-Svensson
def nelson_siegel_svensson(maturities, beta0, beta1, beta2, beta3, tau1, tau2):
    t = maturities
    term1 = (1 - np.exp(-t/tau1)) / (t/tau1)
    term2 = (1 - np.exp(-t/tau2)) / (t/tau2)
    return beta0 + beta1 * term1 + beta2 * (term1 - np.exp(-t/tau1)) + beta3 * (term2 - np.exp(-t/tau2))

# Función de pérdida para minimizar
def loss(params):
    beta0, beta1, beta2, beta3, tau1, tau2 = params
    fitted_rates = nelson_siegel_svensson(df_curva_cer["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)
    return np.sum((fitted_rates - df_curva_cer["TIREA"]) ** 2)

# Función para clasificar los bonos
def clasificar_bono(tirea, tasa_modelo, desvio):
    if tirea > tasa_modelo + desvio:
        return 'Barato'
    elif tirea < tasa_modelo - desvio:
        return 'Caro'
    else:
        return 'Neutro'

# Estimación inicial de parámetros
initial_guess = [-0.05, -0.02, 0.01, 0.01, 1.0, 1.0]

# Optimización
result = minimize(loss, initial_guess, method='Nelder-Mead')
beta0, beta1, beta2, beta3, tau1, tau2 = result.x

cer_params_save = result.x

# Usar los parámetros estimados para generar la curva
fitted_curve = nelson_siegel_svensson(df_curva_cer["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)

#"Estimar curva: fitted_curve = nelson_siegel_svensson("duration", cer_params_save[0], cer_params_save[1], cer_params_save[2], cer_params_save[3], cer_params_save[4], cer_params_save[5])"

# Graficar la curva ajustada
plt.figure(figsize=(10, 6))
plt.plot(df_curva_cer["Duration"], df_curva_cer["TIREA"], 'o', label='TIREA Observada')
plt.plot(df_curva_cer["Duration"], fitted_curve, label='Curva Ajustada Nelson-Siegel-Svensson')
for i in range(len(df_curva_cer)):
    plt.text(df_curva_cer["Duration"][i], df_curva_cer["TIREA"][i], df_curva_cer["Codigo"][i], fontsize=9)
plt.title('Curva CER')
plt.xlabel('Duration')
plt.ylabel('TIREA')

# Configurar el formato del eje y
formatter = FuncFormatter(to_percent)
plt.gca().yaxis.set_major_formatter(formatter)

plt.grid(True)
plt.legend()
plt.show()

df_curva_cer['Tasa Modelo'] = nelson_siegel_svensson(df_curva_cer['Duration'], beta0, beta1, beta2, beta3, tau1, tau2)

#Clasificación
# Definir un desvío tolerable para clasificar los bonos
desvio_tolerable = 0.008  # Ejemplo: 0.8%
# Aplicar la clasificación a cada bono
df_curva_cer['Clasificación'] = df_curva_cer.apply(lambda row: clasificar_bono(row['TIREA'], row['Tasa Modelo'], desvio_tolerable), axis=1)



# Formateo
df_curva_cer_formateada = df_curva_cer.copy()

df_curva_cer_formateada['Tasa Modelo'] = (df_curva_cer_formateada['Tasa Modelo'] * 100).round(4).astype(str) + '%'
df_curva_cer_formateada['TIREA'] = (df_curva_cer_formateada['TIREA'] * 100).round(4).astype(str) + '%'


df_curva_cer_formateada



# NSS DL

# Datos proporcionados FILTRADOS
#df_curva_dl = df_curva_dl[~((df_curva_dl['TIREA'] < df_curva_dl['TIREA'].mean() - 2 * df_curva_dl['TIREA'].std()) | (df_curva_dl['TIREA'] > df_curva_dl['TIREA'].mean() + 2 * df_curva_dl['TIREA'].std()))]


# Función de pérdida para minimizar
def loss(params):
    beta0, beta1, beta2, beta3, tau1, tau2 = params
    fitted_rates = nelson_siegel_svensson(df_curva_dl["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)
    return np.sum((fitted_rates - df_curva_dl["TIREA"]) ** 2)

# Estimación inicial de parámetros
initial_guess = [0.03, -0.02, 0.01, 0.01, 1.0, 1.0]

# Optimización
result = minimize(loss, initial_guess, method='Nelder-Mead')
beta0, beta1, beta2, beta3, tau1, tau2 = result.x

# Usar los parámetros estimados para generar la curva
fitted_curve = nelson_siegel_svensson(df_curva_dl["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)

# Graficar la curva ajustada
plt.figure(figsize=(10, 6))
plt.plot(df_curva_dl["Duration"], df_curva_dl["TIREA"], 'o', label='TIREA Observada')
plt.plot(df_curva_dl["Duration"], fitted_curve, label='Curva Ajustada Nelson-Siegel-Svensson')
for i in range(len(df_curva_dl)):
    plt.text(df_curva_dl["Duration"][i], df_curva_dl["TIREA"][i], df_curva_dl["Codigo"][i], fontsize=9)
plt.title('Curva Dólar Linked y Duales')
plt.xlabel('Duration')
plt.ylabel('TIREA')
# Configurar el formato del eje y
formatter = FuncFormatter(to_percent)
plt.gca().yaxis.set_major_formatter(formatter)

plt.grid(True)
plt.legend()
plt.show()


df_curva_dl['Tasa Modelo'] = nelson_siegel_svensson(df_curva_dl['Duration'], beta0, beta1, beta2, beta3, tau1, tau2)


#Clasificación
# Definir un desvío tolerable para clasificar los bonos
desvio_tolerable = 0.008  # Ejemplo: 0.8%
# Aplicar la clasificación a cada bono
df_curva_dl['Clasificación'] = df_curva_dl.apply(lambda row: clasificar_bono(row['TIREA'], row['Tasa Modelo'], desvio_tolerable), axis=1)


# Formateo
df_curva_dl_formateada = df_curva_dl.copy()

df_curva_dl_formateada['Tasa Modelo'] = (df_curva_dl_formateada['Tasa Modelo'] * 100).round(4).astype(str) + '%'
df_curva_dl_formateada['TIREA'] = (df_curva_dl_formateada['TIREA'] * 100).round(4).astype(str) + '%'

df_curva_dl_formateada








# Curva CER Proyectada

# Filtrar bonos por la industria "Soberano Inflación"
codigos_a_excluir_cerproy = ['TX24j','TG25j', 'T4X5j', 'T7X4j']  # Reemplaza esto con los códigos reales que quieres excluir
# Filtrar la lista de bonos para excluir los que tienen los códigos en codigos_a_excluir
bonos_filtrados_cer_proyectado = [bono for bono in todos_los_bonos if bono.codigo not in codigos_a_excluir_cerproy and bono.industria in ["Soberano Inflación Proyectado"]]


# Crear el diccionario con los códigos y precios (ejemplo de precios, ajusta según necesites)
inputs_cer_proyectado = {
    "codigo": [bono.codigo for bono in bonos_filtrados_cer_proyectado],
    "precio": [bono.precio for bono in bonos_filtrados_cer_proyectado]  # Asegurarse de ajustar los precios correctamente
}

df_inputs_cer_proyectado = rentafija.pd.DataFrame(inputs_cer_proyectado)

# Dictionario de bonos objects en automatico:
bonos_cer_proyectado = {bono.codigo: bono for bono in bonos_filtrados_cer_proyectado}

curva_cer_proyectado = []

# Calculating data for each bond
for index, row in df_inputs_cer_proyectado.iterrows():
    codigo_bono = row['codigo']
    precio_bono = row['precio']

    if codigo_bono in bonos_cer_proyectado:
        bono = bonos_cer_proyectado[codigo_bono]
        resultado_aplicar_precio = rentafija.tir_a_tna(bono.calcula_tirea(precio_bono),(bono.vencimiento -bono.fecha_settlement).days,365)
        resultado_metodo_adicional = bono.calcula_duration(resultado_aplicar_precio)  # Adjust as per method definition
        curva_cer_proyectado.append([codigo_bono, precio_bono, resultado_aplicar_precio, resultado_metodo_adicional, bono.paridad])
    else:
        print(f"No se encontró el bono con código: {codigo_bono}")

# Convert to DataFrame and sort
df_curva_cer_proyectado = rentafija.pd.DataFrame(curva_cer_proyectado, columns=['Codigo', 'Precio Input', 'TNA', 'Duration', 'Paridad']).sort_values(by='Duration')
# Curva CER Proy personalizado
df_curva_cer_proyectado = df_curva_cer_proyectado[df_curva_cer_proyectado['Codigo'] != 'tdf24'].reset_index(drop=True)


print('Curva CER Proyectada:\n', df_curva_cer_proyectado)

# Función de pérdida para minimizar
def loss(params):
    beta0, beta1, beta2, beta3, tau1, tau2 = params
    fitted_rates = nelson_siegel_svensson(df_curva_cer_proyectado["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)
    return np.sum((fitted_rates - df_curva_cer_proyectado["TNA"]) ** 2)

# Estimación inicial de parámetros
initial_guess = [0.01, 0.01, 0.01, 0.01, 1.0, 1.0]

# Optimización
result = minimize(loss, initial_guess, method='Nelder-Mead')
beta0, beta1, beta2, beta3, tau1, tau2 = result.x

cer_proy_params_save = result.x
#"Estimar curva: fitted_curve = nelson_siegel_svensson("duration", cer_proy_params_save[0], cer_proy_params_save[1], cer_proy_params_save[2], cer_proy_params_save[3], cer_proy_params_save[4], cer_proy_params_save[5])"


# Usar los parámetros estimados para generar la curva
fitted_curve = nelson_siegel_svensson(df_curva_cer_proyectado["Duration"], beta0, beta1, beta2, beta3, tau1, tau2)

# Graficar la curva ajustada
plt.figure(figsize=(10, 6))
plt.plot(df_curva_cer_proyectado["Duration"], df_curva_cer_proyectado["TNA"], 'o', label='TIREA Observada')
plt.plot(df_curva_cer_proyectado["Duration"], fitted_curve, label='Curva Ajustada Nelson-Siegel-Svensson')
for i in range(len(df_curva_cer_proyectado)):
    plt.text(df_curva_cer_proyectado["Duration"][i], df_curva_cer_proyectado["TNA"][i], df_curva_cer_proyectado["Codigo"][i], fontsize=9)
plt.title('Curva CER con inflación proyectada')
plt.xlabel('Duration')
plt.ylabel('TNA')
# Configurar el formato del eje y
formatter = FuncFormatter(to_percent)
plt.gca().yaxis.set_major_formatter(formatter)

plt.grid(True)
plt.legend()
plt.show()


df_curva_cer_proyectado['Tasa Modelo'] = nelson_siegel_svensson(df_curva_cer_proyectado['Duration'], beta0, beta1, beta2, beta3, tau1, tau2)


#Clasificación
# Definir un desvío tolerable para clasificar los bonos
desvio_tolerable = 0.008  # Ejemplo: 0.8%
# Aplicar la clasificación a cada bono
df_curva_cer_proyectado['Clasificación'] = df_curva_cer_proyectado.apply(lambda row: clasificar_bono(row['TNA'], row['Tasa Modelo'], desvio_tolerable), axis=1)


# Formateo
df_curva_cer_proyectado_formateada = df_curva_cer_proyectado.copy()

df_curva_cer_proyectado_formateada['Tasa Modelo'] = (df_curva_cer_proyectado_formateada['Tasa Modelo'] * 100).round(4).astype(str) + '%'
df_curva_cer_proyectado_formateada['TNA'] = (df_curva_cer_proyectado_formateada['TNA'] * 100).round(4).astype(str) + '%'

df_curva_cer_proyectado_formateada
# %%
