#%% Bonos:
import rentafija
from utils import *

#%% Overrides
# ------Override A3500 hoy ------:
# Fecha específica y dato que desea modificar
# Modificar el valor para esa fecha específica en la columna 'tca3500'


fx_mae = requests.get(
    "https://api.mae.com.ar/MarketData/v1/mercado/cotizaciones/forex",
    headers={"x-api-key": "nuDX73vj2483KSUgvenkj9t50oA0vgvA4WcuRAER"}
)
USDTSIOPEL0MAE = next(i['precioUltimo'] for i in fx_mae.json() if i['ticker'] == 'UST$T' and i['segmento'] == 'Mayorista')
fecha_especifica_override = date.today().isoformat() #'2025-06-17'  # Formato 'YYYY-MM-DD'
a3500_override = USDTSIOPEL0MAE  # USBMEPSIOPEL0MAY O Valor que desea establecer tipo 1641.2
rentafija.inputs['a3500'].loc[fecha_especifica_override, 'tca3500'] = a3500_override

# V2 Badlar aplicable rentafija.inputs['badlar'].tail(5)["BADLAR"].mean()
#Last version

#%% Bonds
'''
Modelo:
bono = {
    "Nombre Security": "EjemploNombre",
    "Código": "EjemploCodigo",
    "ISIN": "EjemploISIN",
    "Calificación": "EjemploCalificación",
    "País": "EjemploPaís",
    "Clasificación": "EjemploClasificación",
    "Industria": "EjemploIndustria",
    "Moneda": "EjemploMoneda",
    "Plazo habitual de liquidación: t +": "EjemploPlazo", # debe ser un entero
    "Emisión": "01/01/2020",
    "Vencimiento": "01/01/2030",
    "Fecha Primer Cupón": "01/01/2021",
    "Cupón / Spread": "EjemploCupón", # es un numero flotante
    "Step-up": "EjemploStep-up", # Es binario True or False
    "Frecuencia de pago de cupón anual": "EjemploFrecuencia", # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "EjemploConvenciónFechas", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "EjemploConvenciónDevengamiento", # Actual, ISMA-30, NASD-30
    "Convención Base": "EjemploConvenciónBase", # 365 o 360
    "Tipo de Amortización": "EjemploTipoAmortización", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "EjemploTipoTasa", # FIJA o VARIABLE
    "Index": "EjemploIndex", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": "EjemploDíasLagDesde", # enteros negativos
    "Días Lag índice hasta inc": "EjemploDíasLagHasta", # enteros negativos
    "Valor Nominal": 100.,
    "Quote Price Convention": "DIRTY", # puede ser clean dirty o nada en tal caso asume dirty
    "Ajuste sobre Capital": "EjemploAjuste", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "29/6/2017", "29/9/2017", "29/12/2017", "29/3/2018", "29/6/2018", "29/9/2018", "29/12/2018",
    "29/3/2019", "29/6/2019", "29/9/2019", "29/12/2019", "29/3/2020", "29/6/2020", "29/9/2020",
    "29/12/2020", "29/3/2021", "29/6/2021", "29/9/2021", "29/12/2021", "29/3/2022", "29/6/2022",
    "29/9/2022", "29/12/2022", "29/3/2023", "29/6/2023", "29/9/2023", "29/12/2023", "29/3/2024"
    ],  # Lista de fechas como ejemplo
    "Amortización": [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 25, 25, 50.], # Ejemplo de amortizacion (solo si no es bullet)
    "Callable": "EjemploCallable", # Es binario True or False
    "Tipo de Call": "EjemploTipoCall",
    "Fecha Call": "01/01/2025",
    "Precio Call": "EjemploPrecioCall2"  # Precio Call
'''
TX26 = {
    "Nombre Security": "BONCER 2026",
    "Código": "TX26",
    "ISIN": "ARARGE3209W8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/11/2026",
    "Fecha Primer Cupón": "09/05/2021",
    "Cupón / Spread": 2., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": [
    "09/05/2021",
    "09/11/2021",
    "09/05/2022",
    "09/11/2022",
    "09/05/2023",
    "09/11/2023",
    "09/05/2024",
    "09/11/2024",
    "09/05/2025",
    "09/11/2025",
    "09/05/2026",
    "09/11/2026"], # Lista de fechas como ejemplo
    "Amortización": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    20.0000,
    20.0000,
    20.0000,
    20.0000,
    20.0000],
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TX26j = {
    "Nombre Security": "BONCER 2026",
    "Código": "TX26j",
    "ISIN": "ARARGE3209W8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/11/2026",
    "Fecha Primer Cupón": "09/05/2021",
    "Cupón / Spread": 2., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": [
    "09/05/2021",
    "09/11/2021",
    "09/05/2022",
    "09/11/2022",
    "09/05/2023",
    "09/11/2023",
    "09/05/2024",
    "09/11/2024",
    "09/05/2025",
    "09/11/2025",
    "09/05/2026",
    "09/11/2026"], # Lista de fechas como ejemplo
    "Amortización": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    20.0000,
    20.0000,
    20.0000,
    20.0000,
    20.0000],
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S10L5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 10 07 2025",
    "Código": "S10L5",
    "ISIN": "S10L5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "18/06/2025",
    "Vencimiento": "10/07/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0258)**((22/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['10/07/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S31L5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 31 07 2025",
    "Código": "S31L5",
    "ISIN": "AR0112750168",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/09/2024",
    "Vencimiento": "31/07/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0398)**((300/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['31/07/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S15G5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 15 08 2025",
    "Código": "S15G5",
    "ISIN": "AR0708856205",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/10/2024",
    "Vencimiento": "15/08/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0390)**((301/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/08/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S29G5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 29 08 2025",
    "Código": "S29G5",
    "ISIN": "AR0308405304",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/08/2024",
    "Vencimiento": "29/08/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0388)**((359/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['29/08/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S12S5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 12 09 2025",
    "Código": "S12S5",
    "ISIN": "AR0574478217",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/09/2024",
    "Vencimiento": "12/09/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0395)**((359/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['12/09/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S30S5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 30 09 2025",
    "Código": "S30S5",
    "ISIN": "AR0145235914",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/09/2024",
    "Vencimiento": "30/09/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0398)**((360/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/09/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T17O5 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2025 Vto 17 10 2025",
    "Código": "T17O5",
    "ISIN": "AR0323021003",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/10/2024",
    "Vencimiento": "17/10/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0390)**((363/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['17/10/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S31O5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 31 10 2025",
    "Código": "S31O5",
    "ISIN": "AR0476306649",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/12/2024",
    "Vencimiento": "31/10/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0274)**((315/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['31/10/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S10N5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 10 11 2025",
    "Código": "S10N5",
    "ISIN": "S10N5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/01/2025",
    "Vencimiento": "10/11/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.022)**((277/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['10/11/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S28N5 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 28 11 2025",
    "Código": "S28N5",
    "ISIN": "S28N5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/02/2025",
    "Vencimiento": "28/11/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0226)**((284/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['28/11/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T15D5 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2025 Vto 15 12 2025",
    "Código": "T15D5",
    "ISIN": "AR0057122373",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/10/2024",
    "Vencimiento": "15/12/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0389)**((421/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/12/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T30E6 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2026 Vto 30 012 2026",
    "Código": "T30E6",
    "ISIN": "AR0398003852",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/12/2024",
    "Vencimiento": "30/01/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0265)**((404/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/01/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T13F6 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2026 Vto 13 02 2026",
    "Código": "T13F6",
    "ISIN": "AR0647336129",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "13/02/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0260)**((434/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['13/02/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
S29Y6 = {
    "Nombre Security": "Letra del Tesoro Nacional en Pesos Capitalizable Vto 29 05 2026",
    "Código": "S29Y6",
    "ISIN": "AR0716680340",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/05/2025",
    "Vencimiento": "29/05/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0235)**((359/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['29/05/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T30J6 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2026 Vto 30 06 2026",
    "Código": "T30J6",
    "ISIN": "T30J6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2025",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0215)**((523/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/06/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T15E7 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos Capitalizable 2027 Vto 15 01 2027",
    "Código": "T15E7",
    "ISIN": "T15E7",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/01/2025",
    "Vencimiento": "15/01/2027",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0205)**((705/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/01/2027'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TO26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a tasa fija 2026 Vto 17 10 2026",
    "Código": "TO26",
    "ISIN": "ARARGE4502K0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/10/2016",
    "Vencimiento": "17/10/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 15.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": [
    "17/04/2017",
    "17/10/2017",
    "17/04/2018",
    "17/10/2018",
    "17/04/2019",
    "17/10/2019",
    "17/04/2020",
    "17/10/2020",
    "17/04/2021",
    "17/10/2021",
    "17/04/2022",
    "17/10/2022",
    "17/04/2023",
    "17/10/2023",
    "17/04/2024",
    "17/10/2024",
    "17/04/2025",
    "17/10/2025",
    "17/04/2026",
    "17/10/2026"], # Lista de fechas como ejemplo
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TY30P = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a tasa fija 2030 Vto 30 05 2030",
    "Código": "TY30P",
    "ISIN": "AR0193433734",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/06/2025",
    "Vencimiento": "30/05/2030",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 29.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": [
    "30/11/2025",
    "30/05/2026",
    "30/11/2026",
    "30/05/2027",
    "30/11/2027",
    "30/05/2028",
    "30/11/2028",
    "30/05/2029",
    "30/11/2029",
    "30/05/2030"], # Lista de fechas como ejemplo
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Es putable, tiene opcion de venta en el 4to cupón",
    "Fecha Call": "27/05/2027",
    "Precio Call": None,  # Precio Call
    "Comentarios": "Es putable al 27/05/2027 https://www.argentina.gob.ar/noticias/llamado-licitacion-para-inversores-internacionales-del-bono-del-tesoro-nacional-en-pesos"
}
TX28 = {
    "Nombre Security": "BONCER 2028",
    "Código": "TX28",
    "ISIN": "ARARGE3209X6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/11/2028",
    "Fecha Primer Cupón": "09/05/2021",
    "Cupón / Spread": 2.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZBALE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": [
    "09/05/2021",
    "09/11/2021",
    "09/05/2022",
    "09/11/2022",
    "09/05/2023",
    "09/11/2023",
    "09/05/2024",
    "09/11/2024",
    "09/05/2025",
    "09/11/2025",
    "09/05/2026",
    "09/11/2026",
    "09/05/2027",
    "09/11/2027",
    "09/05/2028",
    "09/11/2028"], # Lista de fechas como ejemplo
    "Amortización": [
    0, 0, 0, 0, 0, 0,
    10., 10., 10., 10., 10., 10.,
    10., 10., 10., 10.],
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
DICP = {
    "Nombre Security": "AR Discount 33",
    "Código": "DICP",
    "ISIN": "ARARGE03E121",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/12/2003",
    "Vencimiento": "31/12/2033",
    "Fecha Primer Cupón": "31/12/2005",
    "Cupón / Spread": 5.83, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Personalizado", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZBALE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1.26993670032672, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": [
    "31/12/2005", "30/06/2006", "31/12/2006", "30/06/2007", "31/12/2007", "30/06/2008", "31/12/2008",
    "30/06/2009", "31/12/2009", "30/06/2010", "31/12/2010", "30/06/2011", "31/12/2011", "30/06/2012",
    "31/12/2012", "30/06/2013", "31/12/2013", "30/06/2014", "31/12/2014", "30/06/2015", "31/12/2015",
    "30/06/2016", "31/12/2016", "30/06/2017", "31/12/2017", "30/06/2018", "31/12/2018", "30/06/2019",
    "31/12/2019", "30/06/2020", "31/12/2020", "30/06/2021", "31/12/2021", "30/06/2022", "31/12/2022",
    "30/06/2023", "31/12/2023", "30/06/2024", "31/12/2024", "30/06/2025", "31/12/2025", "30/06/2026",
    "31/12/2026", "30/06/2027", "31/12/2027", "30/06/2028", "31/12/2028", "30/06/2029", "31/12/2029",
    "30/06/2030", "31/12/2030", "30/06/2031", "31/12/2031", "30/06/2032", "31/12/2032", "30/06/2033", "31/12/2033"], # Lista de fechas como ejemplo
    "Amortización": [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZV25 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 30 06 2025",
    "Código": "TZV25",
    "ISIN": "AR0611241768",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2024",
    "Vencimiento": "30/06/2025",
    "Fecha Primer Cupón": "30/06/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -1, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/06/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZVD5 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 15 12 2025",
    "Código": "TZVD5",
    "ISIN": "TZVD5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/07/2024",
    "Vencimiento": "15/12/2025",
    "Fecha Primer Cupón": "15/12/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -1, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["15/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
D16E6 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 16 01 2026",
    "Código": "D16E6",
    "ISIN": "AR0306034593",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/02/2025",
    "Vencimiento": "16/01/2026",
    "Fecha Primer Cupón": "16/01/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -1, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["16/01/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZV26 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 30 06 2026",
    "Código": "TZV26",
    "ISIN": "TZV26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2024",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": "30/06/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -1, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZV27 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 30 06 2027",
    "Código": "TZV27",
    "ISIN": "TZV27",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/07/2024",
    "Vencimiento": "30/06/2027",
    "Fecha Primer Cupón": "30/06/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -1, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/06/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TG25 = {
    "Nombre Security": "TG25*",
    "Código": "TG25",
    "ISIN": "ARARGE320DS6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/05/2023",
    "Vencimiento": "23/08/2025",
    "Fecha Primer Cupón": "19/11/2024",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Personalizado", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["19/11/2024",
    "23/02/2025",
    "23/05/2025",
    "23/08/2025"], # Lista de fechas como ejemplo
    "Amortización": ([25]*4),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TX25 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.8% Vto. 09 11 2025*",
    "Código": "TX25",
    "ISIN": "ARARGE320C83",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/05/2022",
    "Vencimiento": "09/11/2025",
    "Fecha Primer Cupón": "09/11/2022",
    "Cupón / Spread": 1.8, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["09/11/2022",
    "09/05/2023",
    "09/11/2023",
    "09/05/2024",
    "09/11/2024",
    "09/05/2025",
    "09/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXO5 = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 31 10 2025",
    "Código": "TZXO5",
    "ISIN": "AR0676005041",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/10/2024",
    "Vencimiento": "31/10/2025",
    "Fecha Primer Cupón": "31/10/2025",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/10/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXO5j = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 31 10 2025",
    "Código": "TZXO5j",
    "ISIN": "AR0676005041",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/10/2024",
    "Vencimiento": "31/10/2025",
    "Fecha Primer Cupón": "31/10/2025",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/10/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD5 = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 15 12 2025",
    "Código": "TZXD5",
    "ISIN": "AR0137939010",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2025",
    "Fecha Primer Cupón": "15/12/2025",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD5j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2025",
    "Código": "TZXD5j",
    "ISIN": "AR0137939010",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2025",
    "Fecha Primer Cupón": "15/12/2025",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXM6 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 31 03 2026",
    "Código": "TZXM6",
    "ISIN": "AR0889577216",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2024",
    "Vencimiento": "31/03/2026",
    "Fecha Primer Cupón": "31/03/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXM6j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 31 03 2026",
    "Código": "TZXM6j",
    "ISIN": "AR0889577216",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2024",
    "Vencimiento": "31/03/2026",
    "Fecha Primer Cupón": "31/03/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXO6 = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 31 10 2026",
    "Código": "TZXO6",
    "ISIN": "AR0881212424",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/10/2024",
    "Vencimiento": "31/10/2026",
    "Fecha Primer Cupón": "31/10/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXO6j = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 31 10 2026",
    "Código": "TZXO6j",
    "ISIN": "AR0881212424",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/10/2024",
    "Vencimiento": "31/10/2026",
    "Fecha Primer Cupón": "31/10/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXM7 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 31 03 2027",
    "Código": "TZXM7",
    "ISIN": "AR0465885959",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/05/2024",
    "Vencimiento": "31/03/2027",
    "Fecha Primer Cupón": "31/03/2027",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/03/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXM7j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 31 03 2027",
    "Código": "TZXM7j",
    "ISIN": "AR0465885959",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/05/2024",
    "Vencimiento": "31/03/2027",
    "Fecha Primer Cupón": "31/03/2027",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/03/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX26 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2026",
    "Código": "AR0643350728",
    "ISIN": "AR0643350728",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": "30/06/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX26j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2026",
    "Código": "TZX26j",
    "ISIN": "AR0643350728",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": "30/06/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TX25j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.8% Vto. 09 11 2025*",
    "Código": "TX25j",
    "ISIN": "ARARGE320C83",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/05/2022",
    "Vencimiento": "09/11/2025",
    "Fecha Primer Cupón": "09/11/2022",
    "Cupón / Spread": 1.8, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["09/11/2022",
    "09/05/2023",
    "09/11/2023",
    "09/05/2024",
    "09/11/2024",
    "09/05/2025",
    "09/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD6 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2026",
    "Código": "TZXD6",
    "ISIN": "AR0465304779",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2026",
    "Fecha Primer Cupón": "15/12/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD6j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2026",
    "Código": "TZXD6j",
    "ISIN": "AR0465304779",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2026",
    "Fecha Primer Cupón": "15/12/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX27 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2027",
    "Código": "TZX27",
    "ISIN": "AR0487777218",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2027",
    "Fecha Primer Cupón": "30/06/2027",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX27j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2027",
    "Código": "TZX27j",
    "ISIN": "AR0487777218",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2027",
    "Fecha Primer Cupón": "30/06/2026",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD7 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2027",
    "Código": "TZXD7",
    "ISIN": "AR0611949808",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2027",
    "Fecha Primer Cupón": "15/12/2027",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD7j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2027",
    "Código": "TZXD7j",
    "ISIN": "AR0611949808",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/03/2024",
    "Vencimiento": "15/12/2027",
    "Fecha Primer Cupón": "15/12/2027",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["15/12/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX28 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2028",
    "Código": "TZX28",
    "ISIN": "AR0404416296",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2028",
    "Fecha Primer Cupón": "30/06/2028",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX28j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2028",
    "Código": "TZX28j",
    "ISIN": "AR0404416296",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/02/2024",
    "Vencimiento": "30/06/2028",
    "Fecha Primer Cupón": "30/06/2028",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
PARP = {
    "Nombre Security": "AR Par 38",
    "Código": "PARP",
    "ISIN": "ARARGE03E105",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/12/2003",
    "Vencimiento": "31/12/2038",
    "Fecha Primer Cupón": "31/03/2004",
    "Cupón / Spread": [1.77,2.48], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Personalizado", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/03/2004", "30/09/2004", "31/03/2005", "30/09/2005",
    "31/03/2006", "30/09/2006", "31/03/2007", "30/09/2007",
    "31/03/2008", "30/09/2008", "31/03/2009", "30/09/2009",
    "31/03/2010", "30/09/2010", "31/03/2011", "30/09/2011",
    "31/03/2012", "30/09/2012", "31/03/2013", "30/09/2013",
    "31/03/2014", "30/09/2014", "31/03/2015", "30/09/2015",
    "31/03/2016", "30/09/2016", "31/03/2017", "30/09/2017",
    "31/03/2018", "30/09/2018", "31/03/2019", "30/09/2019",
    "31/03/2020", "30/09/2020", "31/03/2021", "30/09/2021",
    "31/03/2022", "30/09/2022", "31/03/2023", "30/09/2023",
    "31/03/2024", "30/09/2024", "31/03/2025", "30/09/2025",
    "31/03/2026", "30/09/2026", "31/03/2027", "30/09/2027",
    "31/03/2028", "30/09/2028", "31/03/2029", "30/09/2029",
    "31/03/2030", "30/09/2030", "31/03/2031", "30/09/2031",
    "31/03/2032", "30/09/2032", "31/03/2033", "30/09/2033",
    "31/03/2034", "30/09/2034", "31/03/2035", "30/09/2035",
    "31/03/2036", "30/09/2036", "31/03/2037", "30/09/2037",
    "31/03/2038", "30/09/2038", "31/12/2038"], # Lista de fechas como ejemplo
    "Intereses":[    0.4425, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850,
    0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850,
    0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850,
    0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850,
    0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850, 0.8850,
    0.8850, 1.2400, 1.1780, 1.1160, 1.0540, 0.9920, 0.9300, 0.8680, 0.8060, 0.7440,
    0.6820, 0.6200, 0.5580, 0.4960, 0.4340, 0.3720, 0.3100, 0.2480, 0.1860, 0.1240,
    0.0310],
    "Amortización": ([0] * 51 + [5.0000] * 20),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
CUAP = {
    "Nombre Security": "Cuasipar 2045",
    "Código": "CUAP",
    "ISIN": "ARARGE03E139",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/12/2003",
    "Vencimiento": "31/12/2045",
    "Fecha Primer Cupón": "31/12/2005",
    "Cupón / Spread": 3.31, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Personalizado", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/12/2005", "30/06/2006", "31/12/2006", "30/06/2007", "31/12/2007",
    "30/06/2008", "31/12/2008", "30/06/2009", "31/12/2009", "30/06/2010",
    "31/12/2010", "30/06/2011", "31/12/2011", "30/06/2012", "31/12/2012",
    "30/06/2013", "31/12/2013", "30/06/2014", "31/12/2014", "30/06/2015",
    "31/12/2015", "30/06/2016", "31/12/2016", "30/06/2017", "31/12/2017",
    "30/06/2018", "31/12/2018", "30/06/2019", "31/12/2019", "30/06/2020",
    "31/12/2020", "30/06/2021", "31/12/2021", "30/06/2022", "31/12/2022",
    "30/06/2023", "31/12/2023", "30/06/2024", "31/12/2024", "30/06/2025",
    "31/12/2025", "30/06/2026", "31/12/2026", "30/06/2027", "31/12/2027",
    "30/06/2028", "31/12/2028", "30/06/2029", "31/12/2029", "30/06/2030",
    "31/12/2030", "30/06/2031", "31/12/2031", "30/06/2032", "31/12/2032",
    "30/06/2033", "31/12/2033", "30/06/2034", "31/12/2034", "30/06/2035",
    "31/12/2035", "30/06/2036", "31/12/2036", "30/06/2037", "31/12/2037",
    "30/06/2038", "31/12/2038", "30/06/2039", "31/12/2039", "30/06/2040",
    "31/12/2040", "30/06/2041", "31/12/2041", "30/06/2042", "31/12/2042",
    "30/06/2043", "31/12/2043", "30/06/2044", "31/12/2044", "30/06/2045",
    "31/12/2045"], # Lista de fechas como ejemplo
    "Intereses":[6.62, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655, 1.655,
    1.5723, 1.4895, 1.4068, 1.3240, 1.2413, 1.1585, 1.0758, 0.9930, 0.9103,
    0.8275, 0.7448, 0.6620, 0.5793, 0.4965, 0.4138, 0.3310, 0.2483, 0.1655, 0.0828],
    "Amortización": ([0] * 61 + [5.0000] * 20),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD29 = {
    "Nombre Security": "BONO USD 2029 Accrued ley ny",
    "Código": "GD29",
    "ISIN": "US040114HS26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2029",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD30 = {
    "Nombre Security": "BONO USD 2030 ley ny",
    "Código": "GD30",
    "ISIN": "US040114HS26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2030",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,0.5,0.75,1.75], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',
                        '09/01/2030',
                        '09/07/2030'], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                0.2500,
                0.2500,
                0.2500,
                0.2500,
                0.3750,
                0.3750,
                0.3600,
                0.3300,
                0.3000,
                0.2700,
                0.2400,
                0.2100,
                0.4200,
                0.3500,
                0.2800,
                0.2100,
                0.1400,
                0.0700],
    "Amortización": ([0] * 6 + [4] + [8] * 12),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD35 = {
    "Nombre Security": "BONO USD 2035 ley ny",
    "Código": "GD35",
    "ISIN": "US040114HT09",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2035",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,1.1250,1.5,3.625,4.125,4.75,5], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',
                        '09/01/2030',
                        '09/07/2030',
                        '09/01/2031',
                        '09/07/2031',
                        '09/01/2032',
                        '09/07/2032',
                        '09/01/2033',
                        '09/07/2033',
                        '09/01/2034',
                        '09/07/2034',
                        '09/01/2035',
                        '09/07/2035'], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                0.5625000000,
                0.5625000000,
                0.7500000000,
                0.7500000000,
                1.8125000000,
                1.8125000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.3750000000,
                2.3750000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.2500000000,
                2.0000000000,
                1.7500000000,
                1.5000000000,
                1.2500000000,
                1.0000000000,
                0.7500000000,
                0.5000000000,
                0.2500000000],
    "Amortización": ([0] * 19 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD38 = {
    "Nombre Security": "BONO USD 2038 ley ny",
    "Código": "GD38",
    "ISIN": "US040114HU71",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/01/2038",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,2.0,3.875,4.25,5.00], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["9/7/2021", "9/1/2022", "9/7/2022", "9/1/2023",
    "9/7/2023", "9/1/2024", "9/7/2024", "9/1/2025",
    "9/7/2025", "9/1/2026", "9/7/2026", "9/1/2027",
    "9/7/2027", "9/1/2028", "9/7/2028", "9/1/2029",
    "9/7/2029", "9/1/2030", "9/7/2030", "9/1/2031",
    "9/7/2031", "9/1/2032", "9/7/2032", "9/1/2033",
    "9/7/2033", "9/1/2034", "9/7/2034", "9/1/2035",
    "9/7/2035", "9/1/2036", "9/7/2036", "9/1/2037",
    "9/7/2037", "9/1/2038"], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                1.0000,
                1.0000,
                1.9375,
                1.9375,
                2.1250,
                2.1250,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.3864,
                2.2727,
                2.1591,
                2.0455,
                1.9318,
                1.8182,
                1.7045,
                1.5909,
                1.4773,
                1.3636,
                1.2500,
                1.1364,
                1.0227,
                0.9091,
                0.7955,
                0.6818,
                0.5682,
                0.4545,
                0.3409,
                0.2273,
                0.1136],
    "Amortización": ([0] * 12 + [(100/22)] * 22),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD41 = {
    "Nombre Security": "BONO USD 2041 ley ny",
    "Código": "GD41",
    "ISIN": "US040114HV54",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2041",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,2.50,3.50,4.875], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["9/7/2021", "9/1/2022", "9/7/2022", "9/1/2023",
    "9/7/2023", "9/1/2024", "9/7/2024", "9/1/2025",
    "9/7/2025", "9/1/2026", "9/7/2026", "9/1/2027",
    "9/7/2027", "9/1/2028", "9/7/2028", "9/1/2029",
    "9/7/2029", "9/1/2030", "9/7/2030", "9/1/2031",
    "9/7/2031", "9/1/2032", "9/7/2032", "9/1/2033",
    "9/7/2033", "9/1/2034", "9/7/2034", "9/1/2035",
    "9/7/2035", "9/1/2036", "9/7/2036", "9/1/2037",
    "9/7/2037", "9/1/2038", "9/7/2038", "9/1/2039",
    "9/7/2039", "9/1/2040", "9/7/2040", "9/1/2041",
    "9/7/2041"], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                1.2500,
                1.2500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.6875,
                1.6250,
                1.5625,
                2.0893,
                2.0022,
                1.9152,
                1.8281,
                1.7411,
                1.6540,
                1.5670,
                1.4799,
                1.3929,
                1.3058,
                1.2188,
                1.1317,
                1.0446,
                0.9576,
                0.8705,
                0.7835,
                0.6964,
                0.6094,
                0.5223,
                0.4353,
                0.3482,
                0.2612,
                0.1741,
                0.0871],
    "Amortización": ([0] * 13 + [(100/28)] * 28),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
GD46 = {
    "Nombre Security": "BONO USD 2046 ley ny",
    "Código": "GD46",
    "ISIN": "US040114HW38",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2046",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,1.125,1.50,3.6250,4.125,4.375,5.00], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["9/7/2021", "9/1/2022", "9/7/2022", "9/1/2023",
    "9/7/2023", "9/1/2024", "9/7/2024", "9/1/2025",
    "9/7/2025", "9/1/2026", "9/7/2026", "9/1/2027",
    "9/7/2027", "9/1/2028", "9/7/2028", "9/1/2029",
    "9/7/2029", "9/1/2030", "9/7/2030", "9/1/2031",
    "9/7/2031", "9/1/2032", "9/7/2032", "9/1/2033",
    "9/7/2033", "9/1/2034", "9/7/2034", "9/1/2035",
    "9/7/2035", "9/1/2036", "9/7/2036", "9/1/2037",
    "9/7/2037", "9/1/2038", "9/7/2038", "9/1/2039",
    "9/7/2039", "9/1/2040", "9/7/2040", "9/1/2041",
    "9/7/2041", "9/1/2042", "9/7/2042", "9/1/2043",
    "9/7/2043", "9/1/2044", "9/7/2044", "9/1/2045",
    "9/7/2045", "9/1/2046", "9/7/2046"], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                0.5625,
                0.5625,
                0.7500,
                0.7500,
                1.8125,
                1.8125,
                2.0625,
                2.0156,
                1.9688,
                1.9219,
                1.8750,
                1.8281,
                1.8892,
                1.8395,
                2.0455,
                1.9886,
                1.9318,
                1.8750,
                1.8182,
                1.7614,
                1.7045,
                1.6477,
                1.5909,
                1.5341,
                1.4773,
                1.4205,
                1.3636,
                1.3068,
                1.2500,
                1.1932,
                1.1364,
                1.0795,
                1.0227,
                0.9659,
                0.9091,
                0.8523,
                0.7955,
                0.7386,
                0.6818,
                0.6250,
                0.5682,
                0.5114,
                0.4545,                
                0.3977,
                0.3409,
                0.2841,
                0.2273,
                0.1705,
                0.1136,
                0.0568],
    "Amortización": ([0] * 7 + [(100/44)] * 44),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
AL29 = {
    "Nombre Security": "BONO USD 2029 Accrued ley ar",
    "Código": "AL29",
    "ISIN": "ARARGE3209Y4",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2029",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
AL30 = {
    "Nombre Security": "BONO USD 2030 ley ar",
    "Código": "AL30",
    "ISIN": "ARARGE3209S6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2030",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,0.5,0.75,1.75], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',
                        '09/01/2030',
                        '09/07/2030'], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                0.2500,
                0.2500,
                0.2500,
                0.2500,
                0.3750,
                0.3750,
                0.3600,
                0.3300,
                0.3000,
                0.2700,
                0.2400,
                0.2100,
                0.4200,
                0.3500,
                0.2800,
                0.2100,
                0.1400,
                0.0700],
    "Amortización": ([0] * 6 + [4] + [8] * 12),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
AL35 = {
    "Nombre Security": "BONO USD 2035 ley ar",
    "Código": "AL35",
    "ISIN": "ARARGE3209T4",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2035",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,1.1250,1.5,3.625,4.125,4.75,5], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['09/07/2021',
                        '09/01/2022',
                        '09/07/2022',
                        '09/01/2023',
                        '09/07/2023',
                        '09/01/2024',
                        '09/07/2024',
                        '09/01/2025',
                        '09/07/2025',
                        '09/01/2026',
                        '09/07/2026',
                        '09/01/2027',
                        '09/07/2027',
                        '09/01/2028',
                        '09/07/2028',
                        '09/01/2029',
                        '09/07/2029',
                        '09/01/2030',
                        '09/07/2030',
                        '09/01/2031',
                        '09/07/2031',
                        '09/01/2032',
                        '09/07/2032',
                        '09/01/2033',
                        '09/07/2033',
                        '09/01/2034',
                        '09/07/2034',
                        '09/01/2035',
                        '09/07/2035'], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                0.5625000000,
                0.5625000000,
                0.7500000000,
                0.7500000000,
                1.8125000000,
                1.8125000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.0625000000,
                2.3750000000,
                2.3750000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.5000000000,
                2.2500000000,
                2.0000000000,
                1.7500000000,
                1.5000000000,
                1.2500000000,
                1.0000000000,
                0.7500000000,
                0.5000000000,
                0.2500000000],
    "Amortización": ([0] * 19 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
AE38 = {
    "Nombre Security": "BONO USD 2038 ley ar",
    "Código": "AE38",
    "ISIN": "ARARGE3209U2",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/01/2038",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,2.0,3.875,4.25,5.00], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["9/7/2021", "9/1/2022", "9/7/2022", "9/1/2023",
    "9/7/2023", "9/1/2024", "9/7/2024", "9/1/2025",
    "9/7/2025", "9/1/2026", "9/7/2026", "9/1/2027",
    "9/7/2027", "9/1/2028", "9/7/2028", "9/1/2029",
    "9/7/2029", "9/1/2030", "9/7/2030", "9/1/2031",
    "9/7/2031", "9/1/2032", "9/7/2032", "9/1/2033",
    "9/7/2033", "9/1/2034", "9/7/2034", "9/1/2035",
    "9/7/2035", "9/1/2036", "9/7/2036", "9/1/2037",
    "9/7/2037", "9/1/2038"], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                1.0000,
                1.0000,
                1.9375,
                1.9375,
                2.1250,
                2.1250,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.5000,
                2.3864,
                2.2727,
                2.1591,
                2.0455,
                1.9318,
                1.8182,
                1.7045,
                1.5909,
                1.4773,
                1.3636,
                1.2500,
                1.1364,
                1.0227,
                0.9091,
                0.7955,
                0.6818,
                0.5682,
                0.4545,
                0.3409,
                0.2273,
                0.1136],
    "Amortización": ([0] * 12 + [(100/22)] * 22),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
AL41 = {
    "Nombre Security": "BONO USD 2041 ley ar",
    "Código": "AL41",
    "ISIN": "ARARGE3209V0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano USD Ley Extranjera",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/09/2020",
    "Vencimiento": "09/07/2041",
    "Fecha Primer Cupón": "09/07/2021",
    "Cupón / Spread": [0.1250,2.50,3.50,4.875], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["9/7/2021", "9/1/2022", "9/7/2022", "9/1/2023",
    "9/7/2023", "9/1/2024", "9/7/2024", "9/1/2025",
    "9/7/2025", "9/1/2026", "9/7/2026", "9/1/2027",
    "9/7/2027", "9/1/2028", "9/7/2028", "9/1/2029",
    "9/7/2029", "9/1/2030", "9/7/2030", "9/1/2031",
    "9/7/2031", "9/1/2032", "9/7/2032", "9/1/2033",
    "9/7/2033", "9/1/2034", "9/7/2034", "9/1/2035",
    "9/7/2035", "9/1/2036", "9/7/2036", "9/1/2037",
    "9/7/2037", "9/1/2038", "9/7/2038", "9/1/2039",
    "9/7/2039", "9/1/2040", "9/7/2040", "9/1/2041",
    "9/7/2041"], # Lista de fechas como ejemplo
    "Intereses":[0.1059027778,
                1.2500,
                1.2500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.7500,
                1.6875,
                1.6250,
                1.5625,
                2.0893,
                2.0022,
                1.9152,
                1.8281,
                1.7411,
                1.6540,
                1.5670,
                1.4799,
                1.3929,
                1.3058,
                1.2188,
                1.1317,
                1.0446,
                0.9576,
                0.8705,
                0.7835,
                0.6964,
                0.6094,
                0.5223,
                0.4353,
                0.3482,
                0.2612,
                0.1741,
                0.0871],
    "Amortización": ([0] * 13 + [(100/28)] * 28),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}


# Fichas duales TAMAR
TTM26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 16 03 2026",
    "Código": "TTM26",
    "ISIN": "TTM26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "16/03/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0225)**((407/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['16/03/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTJ26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 30 06 2026",
    "Código": "TTJ26",
    "ISIN": "TTJ26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0219)**((511/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/06/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTS26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 15 09 2026",
    "Código": "TTS26",
    "ISIN": "TTS26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "15/09/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0217)**((586/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/09/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTD26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 15 12 2026",
    "Código": "TTD26",
    "ISIN": "TTD26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "15/12/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0214)**((676/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/12/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}

tamar_tem = ((1+((rentafija.inputs['tamar'].tail(10)["TAMAR"].mean()/100)/(365/32)))**(365/32))**(1/12)-1

TTM26v = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 16 03 2026",
    "Código": "TTM26v",
    "ISIN": "TTM26v",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "16/03/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['16/03/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTJ26v = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 30 06 2026",
    "Código": "TTJ26",
    "ISIN": "TTJ26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/06/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTS26v = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 15 09 2026",
    "Código": "TTS26",
    "ISIN": "TTS26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "15/09/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/09/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TTD26v = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos a Tasa Dual Vto 15 12 2026",
    "Código": "TTD26v",
    "ISIN": "TTD26v",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/01/2025",
    "Vencimiento": "15/12/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['15/12/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}

# Fichas ON HARD DOLAR Corporativos
TSC3O = {
    "Nombre Security": "ON Transportadora Gas del Sur SA Clase II Vto 24 07 2031",
    "Código": "TSC3O",
    "ISIN": "USP9308RBA07",
    "Calificación": "BB-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "24/07/2024",
    "Vencimiento": "24/07/2031",
    "Fecha Primer Cupón": "24/01/2025",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "24/1/2025",
    "24/7/2025",
    "24/1/2026",
    "24/7/2026",
    "24/1/2027",
    "24/7/2027",
    "24/1/2028",
    "24/7/2028",
    "24/1/2029",
    "24/7/2029",
    "24/1/2030",
    "24/7/2030",
    "24/1/2031",
    "24/7/2031"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
YCAMO = {
    "Nombre Security": "ON YPF S.A. Tasa 6.95% en USD Vto 21 07 2027 D",
    "Código": "YCAMO",
    "ISIN": "USP989MJBL47",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/12/2017",
    "Vencimiento": "21/07/2027",
    "Fecha Primer Cupón": "21/01/2018",
    "Cupón / Spread": 6.95, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [    "21/01/2018", "21/07/2018", "21/01/2019", "21/07/2019",
    "21/01/2020", "21/07/2020", "21/01/2021", "21/07/2021",
    "21/01/2022", "21/07/2022", "21/01/2023", "21/07/2023",
    "21/01/2024", "21/07/2024", "21/01/2025", "21/07/2025",
    "21/01/2026", "21/07/2026", "21/01/2027", "21/07/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5938%2FYPF%2DHR%2D%20ON%20CLASE%20LIII%20%2D%20%20Aviso%20de%20Resultados%2018%2D07%2D17%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5938&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5938%2FYPF%2DHR%2DON%20Clase%2053%20Adicionales%20%2D%20Suplemento%20de%20precio%2006%2D12%2D17%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5938&p=true&ga=1"""
}
PN38O = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 38 Vto 11 08 2027",
    "Código": "PN38O",
    "ISIN": "AR0554009248",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/02/2025",
    "Vencimiento": "11/08/2027",
    "Fecha Primer Cupón": "11/08/2025",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "11/08/2025",
    "11/02/2026",
    "11/08/2026",
    "11/02/2027",
    "11/08/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "11/02/2025",
    "Precio Call": {"m1 a m10: 1.03, m11 a m20: 1.02, m21 a m30: 1.01"},  # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, en cualquier momento y a su sola opción, de rescatar la totalidad de las Obligaciones Negociables (pero no en parte). El precio de rescate incluirá el capital, los intereses devengados y no pagados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables, conforme al siguiente esquema:
                    Desde la Fecha de Emisión y Liquidación hasta el décimo mes: 103%
                    Desde el mes 11 hasta el mes 20: 102%
                    Desde el mes 21 hasta el día anterior a la Fecha de Vencimiento: 101%""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7291%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2038%2DSuplemento%20de%20Prospecto%2003%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7291&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7291%2FMPMAE%2DRES%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2038%20Aviso%20resultados%2006%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7291&p=true&ga=1"""
}
MGCOO = {
    "Nombre Security": "ON Pampa Energia Clase 23 en USD Vto 16 12 2034",
    "Código": "MGCOO",
    "ISIN": "USP7464EAT30",
    "Calificación": "B",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/12/2024",
    "Vencimiento": "16/12/2034",
    "Fecha Primer Cupón": "16/06/2025",
    "Cupón / Spread": 7.875, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "NASD-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "16/6/2025", "16/12/2025", "16/6/2026", "16/12/2026", "16/6/2027", "16/12/2027",
    "16/6/2028", "16/12/2028", "16/6/2029", "16/12/2029", "16/6/2030", "16/12/2030",
    "16/6/2031", "16/12/2031", "16/6/2032", "16/12/2032", "16/6/2033", "16/12/2033",
    "16/6/2034", "16/12/2034"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "16/12/2024",
    "Precio Call": {"m0 a m59: rescate con prima compensatoria, m66 a m72: 1.03938, m73 a m84: 1.01969, m85 a m96: 1.00984, m97 a m108 en adelante: 1.00"},  # Precio Call
    "Comentarios": """Rescate Optativo con Prima Compensatoria previo al 16/12/2029
    Antes de la Fecha de Primera Recompra, la Sociedad podrá rescatar total o parcialmente las Obligaciones Negociables al mayor de:
    . El valor presente del precio de rescate en la Fecha de Primera Recompra, más los intereses requeridos hasta esa fecha, descontados a la tasa del Tesoro más 
    50 puntos básicos indicados en el Aviso de Resultados.
    . 100% del capital de las Obligaciones Negociables rescatadas.
    En ambos casos, se sumarán los intereses devengados hasta la fecha de rescate.  
    La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables a partir de la Fecha de Primera Recompra, según los siguientes valores, 
    más intereses devengados hasta la fecha de rescate: 16/12/2029: 103.938%, 16/12/2030: 101.969%, 
    16/12/2031: 100.984%, 16/12/2032 y después: 100.000%""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9447%2FPAMPA%20ENERGIA%20HR%20%2D%20ON%20CLASE%2023%20International%20Bond%202024%20%2D%20Aviso%20de%20Resultados%2009%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9447&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9447%2FPAMPA%20ENERGIA%20HR%20%2D%20ON%20CLASE%2023%20International%20Bond%202024%20%2D%20Aviso%20de%20Resultados%2009%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9447&p=true&ga=1"""
}
YM34O = {
    "Nombre Security": "ON YPF S.A. Clase XXXIV Vto 17 01 2034",
    "Código": "YM34O",
    "ISIN": "USP989MJBY67",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2025",
    "Vencimiento": "17/01/2034",
    "Fecha Primer Cupón": "17/07/2025",
    "Cupón / Spread": 8.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "NASD-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "17/7/2025", "17/1/2026", "17/7/2026", "17/1/2027", "17/7/2027", "17/1/2028",
    "17/7/2028", "17/1/2029", "17/7/2029", "17/1/2030", "17/7/2030", "17/1/2031",
    "17/7/2031", "17/1/2032", "17/7/2032", "17/1/2033", "17/7/2033", "17/1/2034"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 13 + [30] + [0] + [30] + [0] + [40]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "17/01/2025",
    "Precio Call": {"m0 a m48: rescate con prima compensatoria, m49 a m52: 1.04125, m53 a m64: 1.02063, m65 en adelante: 1.00"},  # Precio Call
    "Comentarios": """Rescate Optativo con Prima Compensatoria previo al 17/01/2029
    El precio de rescate (expresado como un porcentaje del monto de capital, redondeado a tres decimales y calculado por YPF) será el mayor de:

    1. El valor presente en la fecha de rescate de:
    a) El precio de rescate aplicable en la Primera Fecha de Rescate (17 de enero de 2029).
    b) Todos los pagos de intereses requeridos hasta esa fecha (excluyendo los intereses devengados y no pagados hasta el rescate).
    Estos valores serán descontados semestralmente a la Tasa del Tesoro más 50 puntos básicos, considerando un año de 360 días con meses de 30 días.
    2. 100% del valor nominal de las Obligaciones Negociables rescatadas.

    En ambos casos, se sumarán los intereses devengados e impagos hasta la fecha de rescate.

    A partir de la Primera Fecha de Rescate, YPF podrá rescatar total o parcialmente las Obligaciones Negociables en cualquier momento según el siguiente esquema, más intereses devengados hasta la fecha de rescate:

    Desde el 17 de enero de 2029: 104,125%
    Desde el 17 de enero de 2030: 102,063%
    Desde el 17 de enero de 2031 y en adelante: 100,000%""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9488%2FYPF%20S%2EA%2E%20%2DHR%20ON%20CLASE%20XXXIV%20Aviso%20de%20Resultados%2008%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9488&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9488%2FYPF%20S%2EA%2E%20HR%20ON%20CLASE%20XXXIV%20%2D%20Suplemento%20%2DInternacional%2D%2002%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9488&p=true&ga=1"""
}
TLCMO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 21 Vto 18 07 2031",
    "Código": "TLCMO",
    "ISIN": "USP9028NBT74",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "18/07/2024",
    "Vencimiento": "18/07/2031",
    "Fecha Primer Cupón": "18/01/2025",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "NASD-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["18/01/2025", "18/07/2025", "18/01/2026", "18/07/2026",
    "18/01/2027", "18/07/2027", "18/01/2028", "18/07/2028",
    "18/01/2029", "18/07/2029", "18/01/2030", "18/07/2030",
    "18/01/2031", "18/07/2031"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [33] + [0] + [33] + [0] + [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "18/07/2029",
    "Precio Call": {
    "Antes del 18/07/2029": "Mayor entre 100%/ del capital o el valor presente de los pagos futuros hasta el 18/07/2029, descontado con Tasa del Tesoro + 50 bps.",
    "18/07/2029 - 17/07/2030": "1.04750",
    "18/07/2030 - 17/07/2031": "1.00",
    "Hasta el 18/07/2031 con Fondos de Ofertas de Acciones": "1.09500 (hasta el 35% del capital total)"},
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables antes del 18/07/2029. 
                  El precio de rescate será el mayor entre:
                  1. El 100% del capital de las ON más intereses devengados e impagos.
                  2. El valor presente de los pagos de capital e intereses hasta el 18/07/2029, descontado con la Tasa del Tesoro + 50 bps.

                  A partir del 18/07/2029, los precios de rescate serán:
                  - Del 18/07/2029 al 17/07/2030: 104.750%.
                  - Del 18/07/2030 al 17/07/2031: 100.000%.
                  
                  Además, hasta el 18/07/2031, la Compañía podrá rescatar hasta el 35% del capital con fondos provenientes de Ofertas de Acciones, 
                  a un precio del 109.500%, más intereses devengados e impagos.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9177%2FTELECOM%20ARGENTINA%20Clase%2021%20%2D%20Aviso%20de%20resultados%20versi%C3%B3n%20final%2011%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9177&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9177%2FTELECOM%20ARGENTINA%20%20HR%2D%20Clase%2021%20Adicionales%20%2D%20Suplemento%20de%20Prospecto%20y%20Canje%20%2011%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9177&p=true&ga=1"""
}
RUCDO = {
    "Nombre Security": "ON MSU Energy Vto 05 12 2030",
    "Código": "RUCDO",
    "ISIN": "USP7000QAJ96",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/12/2024",
    "Vencimiento": "05/12/2030",
    "Fecha Primer Cupón": "05/06/2025",
    "Cupón / Spread": 9.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "NASD-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "05/06/2025", "05/12/2025", "05/06/2026", "05/12/2026",
    "05/06/2027", "05/12/2027", "05/06/2028", "05/12/2028",
    "05/06/2029", "05/12/2029", "05/06/2030", "05/12/2030"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [17.50] + [0] + [17.50] + [0] + [65]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "05/12/2024",
    "Precio Call": {"m0 en adelante: ver debajo, m24 en adelante: 1.00 y 1.095 en caso de emisión (por hasta el 35%/ del total)"},
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes del 05/12/2026, al mayor entre:
                    1. El 100% del capital de las ON.
                    2. El valor presente del precio de rescate al 05/12/2026 más pagos de intereses hasta esa fecha, descontado con Tasa del Tesoro + 50 bps.
                  
                  - Desde el 05/12/2026 en adelante, conforme a los precios de rescate establecidos en el Suplemento.

                  - Además, antes del 05/12/2026, la Compañía podrá rescatar hasta el 35% del capital con fondos provenientes de Eventos de Emisión, 
                    a un precio del 109.500%, más intereses devengados e impagos, siempre que al menos el 65% del capital original permanezca en circulación tras el rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9425%2FMSU%20Energy%20SA%20%2D%20Aviso%20de%20Resultados%20New%20Money%20%28Executed%29%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9425&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9425%2FMSU%20%2D%20Notes%202030%20%2D%20Suplemento%20%2D%20New%20Money%20%5BExecute%5D%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9425&p=true&ga=1"""
}
TTCAO = {
    "Nombre Security": "ON Tecpetrol Clase X Vto. 22 01 2033",
    "Código": "TTCAO",
    "ISIN": "USP90187AR99",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/01/2025",
    "Vencimiento": "22/01/2033",
    "Fecha Primer Cupón": "22/07/2025",
    "Cupón / Spread": 7.625, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "NASD-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "22/7/2025", "22/1/2026", "22/7/2026", "22/1/2027", "22/7/2027", "22/1/2028",
    "22/7/2028", "22/1/2029", "22/7/2029", "22/1/2030", "22/7/2030", "22/1/2031",
    "22/7/2031", "22/1/2032", "22/7/2032", "22/1/2033"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33] + [0] + [33] + [0] + [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "22/01/2025",
    "Precio Call": {"m0 a m36: rescate con prima compensatoria, m37 a m48: 1.03813, m49 a m60: 1.01906, m61 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La emisora puede rescatar total o parcialmente las Obligaciones Negociables antes de la "Primera Fecha de Llamado a Rescate". El precio de rescate será el mayor entre:
                    1. El 100%/ del capital de las obligaciones.
                    2. El valor actual del precio de rescate informado más los intereses exigidos hasta esa fecha, descontados a una tasa específica (Tasa del Tesoro + 50 puntos base), y sumando los intereses no pagados hasta la fecha de rescate.
                    Este derecho de rescate está sujeto a las condiciones especificadas en el suplemento de la emisión.
                    La emisora puede rescatar las Obligaciones Negociables en cualquier momento después del 22 de enero de 2028 (la "Primera Fecha de Llamado de Rescate"), total o parcialmente, notificando a los tenedores con entre 10 y 60 días de antelación. Los precios de rescate serán:
                        A partir del 22/1/2028: 103.813%
                        A partir de 22/1/2029: 101.906%
                        A partir de 22/1/2030: 100.00%
                    Además, se deberán pagar los intereses devengados y no pagados hasta la fecha de rescate.
                    La emisora también puede rescatar hasta un 35%/ del monto total de las Obligaciones Negociables (incluidas las adicionales) en cualquier momento hasta la fecha de la Primera Fecha de Llamado de Rescate. Este rescate se realizará a un precio del 107,625% 
                    del monto de capital más los intereses devengados y no pagados hasta la fecha de rescate. 
                    El rescate se financiará con fondos netos en efectivo obtenidos de una o más Ofertas de Acciones, según lo establecido en las condiciones del suplemento.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9501%2FTECPETROL%20HR%2D%20ON%20Clase%2010%20Internacional%20%2D%20Aviso%20de%20Resultados%2016%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9501&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9501%2FTECPETROL%20HR%2D%20ONs%20Clase%2010%20Internacional%20%2D%20Suplemento%2013%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9501&p=true&ga=1"""
}
YMCJO = {
    "Nombre Security": "ON YPF S.A. Clase XVIII Vto 30 09 2033",
    "Código": "YMCJO",
    "ISIN": "USP989MJBT72",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/02/2021",
    "Vencimiento": "30/09/2033",
    "Fecha Primer Cupón": "30/03/2021",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/3/2021", "30/9/2021", "30/3/2022", "30/9/2022", "30/3/2023", "30/9/2023",
    "30/3/2024", "30/9/2024", "30/3/2025", "30/9/2025", "30/3/2026", "30/9/2026",
    "30/3/2027", "30/9/2027", "30/3/2028", "30/9/2028", "30/3/2029", "30/9/2029",
    "30/3/2030", "30/9/2030", "30/3/2031", "30/9/2031", "30/3/2032", "30/9/2032",
    "30/3/2033", "30/9/2033"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 19 + [25] + [0]+ [25] + [0]+ [25] + [0]+ [25]),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
PNXCO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 31 Vto 30 04 2032",
    "Código": "PNXCO",
    "ISIN": "USE7S78BAC65",
    "Calificación": "BB-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2024",
    "Vencimiento": "30/04/2032",
    "Fecha Primer Cupón": "30/10/2024",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/10/2024", "30/4/2025", "30/10/2025", "30/4/2026", "30/10/2026", "30/4/2027",
    "30/10/2027", "30/4/2028", "30/10/2028", "30/4/2029", "30/10/2029", "30/4/2030",
    "30/10/2030", "30/4/2031", "30/10/2031", "30/4/2032"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33.33325] + [0]+ [33.33325] + [0]+ [33.3335]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "30/04/2024",
    "Precio Call": {"m0 a m91: rescate con prima compensatoria, m92 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora puede rescatar total o parcialmente las Obligaciones Negociables antes del 30/01/2032. 
                    El precio de rescate será el mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados de capital e intereses, descontado a la Tasa del Tesoro US + 50 bps.
                    En cualquier momento a partir del 30/01/2032, el rescate se realizará al 100%/ del capital más los intereses devengados.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048%2FPAE%20%2D%20Aviso%20de%20Resultados%20ON%20Clase%2031%2E%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048%2FPAE%2D%20Suplemento%20Local%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048&p=true&ga=1"""
}
PLC4O = {
    "Nombre Security": "ON Pluspetrol S.A. Clase IV Vto 30 05 2032",
    "Código": "PLC4O",
    "ISIN": "USP7924AAA62",
    "Calificación": "B+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/05/2025",
    "Vencimiento": "30/05/2032",
    "Fecha Primer Cupón": "30/11/2025",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/11/2025", "30/05/2026", "30/11/2026", "30/05/2027",
    "30/11/2027", "30/05/2028", "30/11/2028", "30/05/2029",
    "30/11/2029", "30/05/2030", "30/11/2030", "30/05/2031",
    "30/11/2031", "30/05/2032"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True,
    "Tipo de Call": "Rescate total o parcial a opción de la sociedad antes y después del 30/05/2028",
    "Fecha Call": "30/05/2028",  # Primera Fecha de Rescate
    "Precio Call": {
    "Hasta 30/05/2028": "El mayor entre (i) el valor presente de los pagos de capital e intereses restantes descontados semestralmente a Tasa del Tesoro +50 pbs (menos intereses devengados), y (ii) el 100% del capital",
    "30/05/2028 a 29/05/2029": 1.04250,
    "30/05/2029 a 29/05/2030": 1.02125,
    "30/05/2030 en adelante": 1.00},
    "Comentarios": """Con anterioridad al 30/05/2028, la Sociedad podrá rescatar las Obligaciones Negociables total o parcialmente a opción, al mayor entre:
    (1) el valor presente de los pagos restantes de capital e intereses descontados semestralmente a Tasa del Tesoro +50 pbs (menos intereses devengados), y
    (2) el 100% del capital,
    añadiendo en ambos casos los intereses devengados e impagos (más Montos Adicionales, si los hubiera).
    Desde el 30/05/2028 y durante los 12 meses siguientes, la Sociedad podrá realizar rescates programados con los siguientes precios (más intereses devengados e impagos):
    - 2028: 104,250%
    - 2029: 102,125%
    - 2030 en adelante: 100,000%
    Adicionalmente, hasta el 30/05/2028, podrá utilizar el producto neto de Ofertas de Capital para rescatar hasta el 35% del capital a 108,500%, siempre que:
    - Permanezcan en circulación al menos el 65% del monto original.
    - El rescate ocurra dentro de los 90 días posteriores al cierre de la oferta.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/415f278f-6962-46ef-89be-0bd999a4562b""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/1889184d-cdd8-4a9b-bd45-1f847a4a0f6f"""
}
YMCUO = {
    "Nombre Security": "ON YPF S.A. Clase XXIII Vto 17 01 2031",
    "Código": "YMCUO",
    "ISIN": "USP989MJBU46",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2024",
    "Vencimiento": "17/01/2031",
    "Fecha Primer Cupón": "17/07/2024",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/07/2024", "17/01/2025", "17/07/2025", "17/01/2026",
    "17/07/2026", "17/01/2027", "17/07/2027", "17/01/2028",
    "17/07/2028", "17/01/2029", "17/07/2029", "17/01/2030","17/07/2030", "17/01/2031"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "17/10/2030",
    "Precio Call": {"m0 a m80: ver debajo, m81 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables antes de la Fecha de Rescate a la Par (17/10/2030), 
                  pagando el mayor valor entre:
                  1. El 100%/ del capital de las ON.
                  2. Una suma compensatoria calculada por la Compañía.
                  En ambos casos, se sumarán los intereses devengados e impagos.

                  A partir de la Fecha de Rescate a la Par, la Compañía podrá rescatar las ON al 100%/ del capital, 
                  más intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8914%2FYPF%20%2D%20HR%20ON%20Clase%20XXVIII%20%2D%20Aviso%20de%20Resultados%2012%2D01%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8914&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048%2FPAE%2D%20Suplemento%20Local%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9048&p=true&ga=1"""
}
YMC1O = {
    "Nombre Security": "ON YPF S.A. Clase I Vto 30 06 2029",
    "Código": "YMC1O",
    "ISIN": "USP989MJBP50",
    "Calificación": "CCC",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/06/2019",
    "Vencimiento": "27/06/2029",
    "Fecha Primer Cupón": "27/12/2019",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/12/2019", "27/06/2020", "27/12/2020", "27/06/2021",
    "27/12/2021", "27/06/2022", "27/12/2022", "27/06/2023",
    "27/12/2023", "27/06/2024", "27/12/2024", "27/06/2025",
    "27/12/2025", "27/06/2026", "27/12/2026", "27/06/2027",
    "27/12/2027", "27/06/2028", "27/12/2028", "27/06/2029"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de los tres meses previos al vencimiento",
    "Fecha Call": "27/03/2029",
    "Precio Call": {"m1 a m116: 1.00 + prima aplicable, m117 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables Clase I:
                  - Desde la Fecha de Emisión hasta 3 meses antes del Vencimiento, al 100%/ del capital más la Prima de Rescate Aplicable, 
                    más intereses devengados e impagos.
                  - Dentro de los 3 meses previos al Vencimiento, al 100%/ del capital más intereses devengados e impagos.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6749%2FYPF%20%2D%20HR%20ON%20CLASE%201%20EMISOR%20FRECUENTE%20%2DAviso%20de%20Resultados%2024%2D06%2D19%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6749&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6749%2FYPF%20%2D%20HR%20ON%20CLASE%201%20EMISOR%20FRECUENTE%20%2D%20Suplemento%20de%20Precio%2024%2D06%2D19%2EPDF&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6749&p=true&ga=1"""
}
YMCXO = {
    "Nombre Security": "ON YPF S.A. Clase XXXI Vto 11 09 2031",
    "Código": "YMCXO",
    "ISIN": "USP989MJBV29",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/09/2024",
    "Vencimiento": "11/09/2031",
    "Fecha Primer Cupón": "11/03/2025",
    "Cupón / Spread": 8.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "11/03/2025", "11/09/2025", "11/03/2026", "11/09/2026",
    "11/03/2027", "11/09/2027", "11/03/2028", "11/09/2028",
    "11/03/2029", "11/09/2029", "11/03/2030", "11/09/2030",
    "11/03/2031", "11/09/2031"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [20] + [0] + [20] + [0]+ [60]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir de la emisión",
"Fecha Call": "11/09/2027",
"Precio Call": {"m0 a m36": "Rescate con prima compensatoria", "m37 a m48": "1.04375", "m49 a m60": "1.02188",
                "m61 en adelante": "1.00"},
"Comentarios": """YPF puede rescatar total o parcialmente las Obligaciones Negociables en cualquier momento antes del 11/09/2027 
                  al mayor entre el 100%/ del capital o el valor presente del precio de rescate en la Primera Fecha de Rescate 
                  (11/09/2027) más los pagos de intereses hasta esa fecha, descontado con la Tasa del Tesoro + 50 bps.
                  
                  A partir del 11/09/2027, los precios de rescate serán:
                  - Del mes 37 al 48: 104.375%
                  - Del mes 49 al 60: 102.188%
                  - Desde el mes 61 en adelante: 100%
                  
                  En todos los casos, se adicionarán los intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9264%2FYPF%20S%2EA%2E%20%2D%20HR%20Aviso%20de%20Resultados%20ON%20Clase%20XXXI%2D%20Colocaci%C3%B3n%20Internacional%2004%2D09%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9264&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9264%2FYPF%20S%2EA%2E%20%2D%20HR%2D%20ON%20CLASE%20XXXI%20%2DSuplemento%20Prospecto%2030%2D08%2D2024%2DColocaci%C3%B3n%20Internacional%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9264&p=true&ga=1"""
}
ARC1O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 Clase 1 Serie 2021 Vto 01 08 2031",
    "Código": "ARC1O",
    "ISIN": "USP0092MAJ29",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/10/2021",
    "Vencimiento": "01/08/2031",
    "Fecha Primer Cupón": "01/02/2022",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["01/02/2022", "01/05/2022", "01/08/2022", "01/11/2022",
    "01/02/2023", "01/05/2023", "01/08/2023", "01/11/2023",
    "01/02/2024", "01/05/2024", "01/08/2024", "01/11/2024",
    "01/02/2025", "01/05/2025", "01/08/2025", "01/11/2025",
    "01/02/2026", "01/05/2026", "01/08/2026", "01/11/2026",
    "01/02/2027", "01/05/2027", "01/08/2027", "01/11/2027",
    "01/02/2028", "01/05/2028", "01/08/2028", "01/11/2028",
    "01/02/2029", "01/05/2029", "01/08/2029", "01/11/2029",
    "01/02/2030", "01/05/2030", "01/08/2030", "01/11/2030",
    "01/02/2031", "01/05/2031", "01/08/2031"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 16 + [1.5289] + [0] + [0.8945] + [0] + [4.7823] + [2.7319] +
                    [4.2299] + [3.2880] + [5.6388] + [3.4927] + [0] + [5.0618] + [7.1115]
                    + [4.9583] + [6.5846] + [5.5925] + [7.3796] + [5.2657] + [6.8845] + 
                    [5.9087] + [8.1084] + [5.9938] + [4.5636]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir del m52 de la emisión",
"Fecha Call": "01/02/2026",
"Precio Call": {"01/02/2026 - 31/01/2027": "1.04250",
    "01/02/2027 - 31/01/2028": "1.02833",
    "01/02/2028 - 31/01/2029": "1.02125",
    "Desde el 01/02/2029 en adelante": "1.00"},
"Comentarios": """En relación con cualquier rescate opcional al Precio de Rescate:
                  - Antes del 01/02/2026, se aplicará una Prima Compensatoria.
                  - 01/02/2026 - 31/01/2027, el precio de rescate será del 104.250%.
                  - 01/02/2027 - 31/01/2028, el precio de rescate será del 102.833%.
                  - 01/02/2028 - 31/01/2029, el precio de rescate será del 102.125%.
                  - 01/02/2029 en adelante, el precio de rescate será del 100%.

                  En todos los casos, el monto de rescate se calcula sobre el Saldo de Capital de las Obligaciones Negociables Serie 2021.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7731%2FAA2000%20%2DHR%20Serie%202021%20Adicionales%20Aviso%5Fde%5FResultados%2001%2D11%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7731&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7731%2FAA%202000%2DHR%20ON%20CLASE%201%20SERIE%2020231%20Suplemento%5Fde%5FProspecto%2D%20Adicionales%2029%2D10%2D21%5F%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7731&p=true&ga=1"""
}
YFCJO = {
    "Nombre Security": "ON YPF Energia Electrica Clase XVIII Vto. 16 10 2032",
    "Código": "YFCJO",
    "ISIN": "USP9897PAS31",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/10/2024",
    "Vencimiento": "16/10/2032",
    "Fecha Primer Cupón": "16/04/2025",
    "Cupón / Spread": 7.875, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "16/4/2025", "16/10/2025", "16/4/2026", "16/10/2026", "16/4/2027", "16/10/2027",
    "16/4/2028", "16/10/2028", "16/4/2029", "16/10/2029", "16/4/2030", "16/10/2030",
    "16/4/2031", "16/10/2031", "16/4/2032", "16/10/2032"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33] + [0]+ [33] + [0]+ [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
IRCFO = {
    "Nombre Security": "ON IRSA Clase XIV en USD Vto 22 06 2028",
    "Código": "IRCFO",
    "ISIN": "US450047AH86",
    "Calificación": "B",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Other Financial",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/07/2022",
    "Vencimiento": "22/06/2028",
    "Fecha Primer Cupón": "22/12/2022",
    "Cupón / Spread": 8.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["22/12/2022", "22/06/2023", "22/12/2023", "22/06/2024",
    "22/12/2024", "22/06/2025", "22/12/2025", "22/06/2026",
    "22/12/2026", "22/06/2027", "22/12/2027", "22/06/2028"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 3 + [17.50] + [0] + [17.50] + [0]+ [17.50] + [0] + [17.50] + [0] + [30]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "15/04/2024",
    "Precio Call": {"Desde la emisión ver debajo, m36 a m47: 1.04375, m48 a m59: 1.021875, m60 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes del 22/06/2025, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos restantes de capital e intereses descontados con la Tasa del Tesoro + 50 bps.
                  
                  - A partir del 22/06/2025, los precios de rescate serán:
                    - 22/06/2025 al 21/06/2026: 104.375%.
                    - 22/06/2026 al 21/06/2027: 102.1875%.
                    - 22/06/2027 en adelante: 100.000%.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8082%2FIRSA%20INVERSIONES%20Y%20REP%2DHR%20ON%20CLASE%2014%2D%20Aviso%20de%20Resultados%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8082&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8082%2FIRSA%20INVERSIONES%20Y%20REP%2DHR%20ON%20CLASE%2014%20%2DSuplemento%20de%20Canje%2016%2D05%2D22%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8082&p=true&ga=1"""
}
CAC5O = {
    "Nombre Security": "ON CAPEX Clase V Vto 25 08 2028",
    "Código": "CAC5O",
    "ISIN": "USP20058AE63",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Utilities",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "25/08/2023",
    "Vencimiento": "25/08/2028",
    "Fecha Primer Cupón": "25/02/2024",
    "Cupón / Spread": 9.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["25/02/2024", "25/08/2024", "25/02/2025", "25/08/2025",
    "25/02/2026", "25/08/2026", "25/02/2027", "25/08/2027", "25/02/2028", "25/08/2028"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 2 + [12.50] * 8),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "25/08/2023",
    "Precio Call": {"Desde la emisión ver debajo, m18 a m23: 1.04625, m24 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Nuevas Obligaciones Negociables:
                  - Antes del 25/02/2025, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes, descontados con la Tasa del Tesoro + 75 bps, menos los intereses devengados.

                  - Del 25/02/2025 al 24/02/2026 1.04625%.
                  - Del 25/02/2026 en adelante: 1.00%

                  - Además, antes del 25/02/2025, la Compañía podrá rescatar hasta el 35%/ del capital con Fondos de Ofertas de Acciones, 
                    a un precio del 109.250%, más intereses devengados e impagos.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9208%2FCAPEX%20S%2EA%2E%20%2D%20HR%20Finalizaci%C3%B3n%20y%20Resultados%20%2EEXE%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9208&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9208%2FCAPEX%20%2D%20HR%20Suplemento%20de%20suscripcion%20%20ON%20CLASE%20V%20%2D%20oferta%20de%20canje%2024%2D07%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9208&p=true&ga=1"""
}
AEC2O = {
    "Nombre Security": "ON AES Argentina Generacion Clase 2 Vto 30 08 2027",
    "Código": "AEC2O",
    "ISIN": "USP1000CAE41",
    "Calificación": "CCC",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/08/2023",
    "Vencimiento": "30/08/2027",
    "Fecha Primer Cupón": "28/02/2024",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/02/2024", "29/08/2024", "28/02/2025", "28/08/2025",
    "28/02/2026", "28/08/2026", "28/02/2027", "28/08/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [25] * 4),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "30/08/2023",
    "Precio Call": {"desde la emisión ver debajo, m30 a m41: 1.0475, m42 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes del 30/03/2027, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes de capital e intereses, descontados con la Tasa del Tesoro + 50 bps.
                  
                  - A partir del 30/03/2027, la Emisora podrá rescatar las ON al 100%/ del capital, más intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8766%2FAAG%20%2D%20Canje%20Internacional%20%2D%20ONs%20Clase%202%20%2D%20Aviso%20de%20Resultados%2E%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8766&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8766%2FAES%20%2D%20Suplemento%20de%20Oferta%20y%20Canje%20%2D%20EXE%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8766&p=true&ga=1"""
}
PNDCO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 12 Vto 30 04 2027",
    "Código": "PNDCO",
    "ISIN": "USE7S78BAB82",
    "Calificación": "BB-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2021",
    "Vencimiento": "30/04/2027",
    "Fecha Primer Cupón": "30/10/2021",
    "Cupón / Spread": 9.125, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/10/2021", "30/04/2022", "30/10/2022", "30/04/2023",
    "30/10/2023", "30/04/2024", "30/10/2024", "30/04/2025",
    "30/10/2025", "30/04/2026", "30/10/2026", "30/04/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [20] * 5),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "30/04/2021",
    "Precio Call": {"Desde la emisión ver debajo, m71 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes del 30/03/2027, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes de capital e intereses, descontados con la Tasa del Tesoro + 50 bps.
                  
                  - A partir del 30/03/2027, la Emisora podrá rescatar las ON al 100%/ del capital, más intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7487%2FPAE%20%2D%20HR%20%2D%20Aviso%20de%20Resultados%20Clase%2012%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7487&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7487%2FPAE%2DHR%2DSuplemento%20de%20Prospecto%20Clase%2012%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7487&p=true&ga=1"""
}
GNCXO = {
    "Nombre Security": "ON GENNEIA S.A. Clase XXXI Vto 02 09 2027",
    "Código": "GNCXO",
    "ISIN": "USP46756BA25",
    "Calificación": "CCC",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "02/09/2021",
    "Vencimiento": "02/09/2027",
    "Fecha Primer Cupón": "02/03/2022",
    "Cupón / Spread": 8.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["02/03/2022", "02/09/2022", "02/03/2023", "02/09/2023",
    "02/03/2024", "02/09/2024", "02/03/2025", "02/09/2025",
    "02/03/2026", "02/09/2026", "02/03/2027", "02/09/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 2 + [10] * 10),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "02/09/2021",
    "Precio Call": {"Desde la emisión ver debajo, m24 a m35: 1.04375, m36 a m47: 1.02188, m48 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Nuevas Obligaciones Negociables:
                  - Antes del 02/09/2023, al 100%/ del capital más la Prima por Rescate Aplicable, calculada como el mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes, descontados con la Tasa del Tesoro Ajustada + 50 bps, menos los intereses devengados.
                  
                  - A partir del 02/09/2023, los precios de rescate seguirán el siguiente cronograma:
                    - Del 02/09/2023 al 01/09/2024: 104.375%.
                    - Del 02/09/2024 al 01/09/2025: 102.188%.
                    - Desde el 02/09/2025 en adelante: 100.000%.

                  - Además, antes del 02/09/2023, la Emisora podrá rescatar hasta el 35%/ del capital con Fondos de Ofertas de Acciones, 
                    a un precio del 108.750%, más intereses devengados e impagos, siempre que al menos el 65%/ del capital total permanezca en circulación 
                    después del rescate y que este se realice dentro de los 90 días posteriores a la Emisión de Acciones.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7680%2FGENNEIA%2DHR%2DON%20CLASE%20XXXI%20%2Doferta%20de%20canje%2D%20Aviso%20de%20Resultados%2031%2D08%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7680&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7680%2FGENNEIA%2D%20HR%20ON%20CLASE%2031%20%2DOferta%20de%20Canje%20%2DSuplemento%20de%20Prospecto%2003%2D08%2D21%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7680&p=true&ga=1"""
}
MGC9O = {
    "Nombre Security": "ON Pampa Energia S.A. Clase IX Vto 8 12 2026",
    "Código": "MGC9O",
    "ISIN": "USP7464EAH91",
    "Calificación": "B",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/08/2022",
    "Vencimiento": "08/12/2026",
    "Fecha Primer Cupón": "08/12/2022",
    "Cupón / Spread": 9.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["08/12/2022", "08/06/2023", "08/12/2023", "08/06/2024", "08/12/2024",
    "08/06/2025", "08/12/2025", "08/06/2026", "08/12/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [33] + [0] + [33] + [0] + [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "08/08/2022",
    "Precio Call": {"Desde la emisión ver debajo, m20 a m31: 1.045, m32 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Nuevas Obligaciones Negociables:
                  - Antes del 08/12/2024, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes, descontados con la Tasa del Tesoro + 50 bps, menos los intereses devengados.
                  
                  - A partir del 08/12/2024, los precios de rescate seguirán el siguiente cronograma:
                    - Del 08/12/2024 al 07/12/2025: 104.500%.
                    - Desde el 08/12/2025 en adelante: 100.000%.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8142%2FPampa%20Energia%2DHR%20%2DAviso%20de%20Canje%20Clase%209%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8142&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8142%2FPampa%20Energia%2DHR%20%2DSuplemento%20de%20Canje%20Clase%209%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8142&p=true&ga=1"""
}
BYC2O = {
    "Nombre Security": "ON Banco Galicia Clase II subordinadas en dólares Vto 19 07 2026",
    "Código": "BYC2O",
    "ISIN": "USP0R66CAA64",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "19/07/2016",
    "Vencimiento": "19/07/2026",
    "Fecha Primer Cupón": "19/01/2017",
    "Cupón / Spread": [8.25,7.966], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["19/01/2017", "19/07/2017", "19/01/2018", "19/07/2018",
    "19/01/2019", "19/07/2019", "19/01/2020", "19/07/2020",
    "19/01/2021", "19/07/2021", "19/01/2022", "19/07/2022",
    "19/01/2023", "19/07/2023", "19/01/2024", "19/07/2024",
    "19/01/2025", "19/07/2025", "19/01/2026", "19/07/2026"], # Lista de fechas como ejemplo
    "Intereses":[4.1250, 4.1250, 4.1250, 4.1250, 4.1250, 
    4.1250, 4.1250, 4.1250, 4.1250, 4.1250, 
    3.9830, 3.9830, 3.9830, 3.9830, 3.9830, 
    3.9830, 3.9830, 3.9830, 3.9830, 3.9830],
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total a opción del Banco en la Fecha de Reajuste",
    "Fecha Call": "19/07/2021",
    "Precio Call": {"En la fecha de reajuste (19/07/2021): 1.00"}, # Precio Call
    "Comentarios": """El Banco podrá rescatar la totalidad (pero no parcialmente) de las Obligaciones Negociables en la Fecha de Reajuste, sujeto a:
                  El rescate se realizará al 100%/ del capital pendiente de pago, más intereses devengados e impagos hasta la fecha de rescate, así como cualquier Monto Adicional si correspondiera.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5336%2FON%20BANCO%20DE%20GALICIA%20CLASE%20II%2D%20%20Aviso%20de%20Resultado%2014%2D07%2D16%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5336&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5336%2FON%20BANCO%20DE%20GALICIA%20CLASE%202%2DHR%20Suplemento%20de%20Precio%2023%2D06%2D16%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5336&p=true&ga=1"""
}
BACAO = {
    "Nombre Security": "ON BANCO MACRO SA Clase A Vto 04 11 2026",
    "Código": "BACAO",
    "ISIN": "USP1047VAF42",
    "Calificación": "CC-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/11/2016",
    "Vencimiento": "04/11/2026",
    "Fecha Primer Cupón": "04/05/2017",
    "Cupón / Spread": [6.75,6.643], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["04/05/2017", "04/11/2017", "04/05/2018", "04/11/2018",
    "04/05/2019", "04/11/2019", "04/05/2020", "04/11/2020",
    "04/05/2021", "04/11/2021", "04/05/2022", "04/11/2022",
    "04/05/2023", "04/11/2023", "04/05/2024", "04/11/2024",
    "04/05/2025", "04/11/2025", "04/05/2026", "04/11/2026"], # Lista de fechas como ejemplo
    "Intereses":[3.3750, 
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3750,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215,
                 3.3215],
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total a opción del Banco en la Fecha de Reajuste",
    "Fecha Call": "04/11/2021",
    "Precio Call": {"En la fecha de reajuste (04/11/2021): 1.00"}, # Precio Call
    "Comentarios": """El Banco podrá rescatar la totalidad (pero no parcialmente) de las Obligaciones Negociables en la Fecha de Reajuste, sujeto a:
                  El rescate se realizará al 100%/ del capital pendiente de pago, más intereses devengados e impagos hasta la fecha de rescate, así como cualquier Monto Adicional si correspondiera.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5513%2FHR%2DON%20BANCO%20MACRO%20CLASE%20A%20SUBORDINADAS%20%2D%20Aviso%20de%20Resultado%2001%2D11%2D16%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5513&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5513%2FHR%2DON%20BANCO%20MACRO%20CLASE%20A%20SUBORDINADAS%2DSuplemento%2021%2D10%2D16%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F5513&p=true&ga=1"""
}
RCCJO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XVIII Vto 09 10 2027",
    "Código": "RCCJO",
    "ISIN": "USP04559AW36",
    "Calificación": "B+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Staples",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/11/2022",
    "Vencimiento": "09/10/2027",
    "Fecha Primer Cupón": "09/04/2023",
    "Cupón / Spread": 8.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/04/2023", "09/10/2023", "09/04/2024", "09/10/2024",
    "09/04/2025", "09/10/2025", "09/04/2026", "09/10/2026", "09/04/2027", "09/10/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 3 + [14.2857142857143] * 7),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "09/11/2022",
    "Precio Call": {"Desde la emisión ver debajo, m18 a m23: 1.04125, m24 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes del 09/04/2024, al mayor entre:
                    1. El 100% del capital de las ON.
                    2. El valor presente de los pagos programados restantes, descontados con la Tasa del Tesoro + 50 bps, menos los intereses devengados.

                  - Del 09/04/2024 al 08/04/2025 1.04125%.
                  - Del 09/04/2025 en adelante: 1.00%""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8275%2FArcor%2DHR%2DAnuncia%20finalizacion%20y%20resultados%20de%20Oferta%20de%20Canje%20ON%2D%2002%2D11%2D22%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8275&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8275%2FARCOR%20%2DHR%20%20Oferta%20de%20Canje%20%2DSUPLEMENTO%20DE%20PROSPECTO%20Y%20CANJE%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8275&p=true&ga=1"""
}
TLC1O = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase I Vto 18 07 2026",
    "Código": "TLC1O",
    "ISIN": "USP9028NAV30",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "18/07/2019",
    "Vencimiento": "18/07/2026",
    "Fecha Primer Cupón": "18/01/2020",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["18/01/2020", "18/07/2020", "18/01/2021", "18/07/2021",
    "18/01/2022", "18/07/2022", "18/01/2023", "18/07/2023",
    "18/01/2024", "18/07/2024", "18/01/2025", "18/07/2025",
    "18/01/2026", "18/07/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "18/07/2019",
    "Precio Call": {"Desde la emisión ver debajo, m48 a m59: 1.04, m60 a m71: 1.02, m72 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Obligaciones Negociables en los siguientes escenarios:

                  - Antes de la fecha informada en el Aviso de Resultados, al mayor entre:
                    1. El 100%/ del capital de las ON.
                    2. El valor presente de los pagos programados restantes, descontados con la Tasa del Tesoro aplicable más el margen especificado en el Aviso de Resultados.

                  - Del 18/07/2023 al 17/07/2024 1.04%.
                  - Del 18/07/2024 al 17/07/2025 1.02%.
                  - Del 18/07/2025 en adelante 1.00%.
                  
                  Rescate con Fondos de Ofertas de Acciones: Antes de la fecha indicada en el Aviso de Resultados, la Emisora podrá rescatar hasta el **35%** del capital, con fondos netos de ofertas de acciones, al precio informado en el Aviso de Resultados, más intereses devengados. Este rescate está sujeto a:
                    1. Que al menos el 65%/ del valor nominal total de las ON permanezca en circulación después del rescate.
                    2. Que el rescate ocurra dentro de los 90 días posteriores a la oferta de acciones.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6761%2FTELECOM%20ARGENTINA%20%2D%20HR%20ON%20CLASE%201%2D%20Aviso%20de%20Resultados%2011%2D07%2D19%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6761&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6761%2FTELECOM%20ARGENTINA%20%2D%20HR%20ON%20CLASE%201%2D%20Suplemento%20Prospecto%2010%2D07%2D19%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6761&p=true&ga=1"""
}
T642O = {
    "Nombre Security": "ON Tarjeta Naranja S.A.U. Clase 64 Serie II Vto. 31 10 2025",
    "Código": "T642O",
    "ISIN": "T642O",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/04/2025",
    "Vencimiento": "31/10/2025",
    "Fecha Primer Cupón": "31/10/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["31/10/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DRES%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DAviso%20de%20Resultado%2025%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DANU%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DSuplemento%2023%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1"""
}
TLC5O = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 5 Vto 06 08 2025",
    "Código": "TLC5O",
    "ISIN": "USP9028NAZ44",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/08/2020",
    "Vencimiento": "06/08/2025",
    "Fecha Primer Cupón": "06/08/2020",
    "Cupón / Spread": 8.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["6/2/2021", "6/8/2021", "6/2/2022", "6/8/2022",
    "6/2/2023", "6/8/2023", "6/2/2024", "6/8/2024",
    "6/2/2025", "6/8/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33] + [0] + [33] + [0]+ [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "06/08/2020",
    "Precio Call": {"Desde la emisión ver debajo en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Obligaciones Negociables en cualquier momento bajo los siguientes términos:

                  - Antes de la Fecha de Vencimiento: Rescate al 100%/ del capital más intereses devengados e impagos, más la Prima de Rescate Aplicable.
                    - La Prima de Rescate Aplicable se calcula como el excedente entre:
                      1. La suma del valor presente de los pagos de capital e intereses descontados con la Tasa del Tesoro más los puntos básicos indicados en el Aviso de Resultados.
                      2. Menos el 100%/ del capital de las ON.

                  - Con Fondos provenientes de Ofertas de Acciones: Se podrá rescatar hasta el 35%/ del valor nominal total de las Obligaciones Negociables a un precio de 108.500%/ del capital, más intereses devengados hasta la fecha de rescate.
                    - Al menos el 65%/ del valor nominal original deberá permanecer en circulación después del rescate.
                    - El rescate deberá realizarse dentro de los 90 días posteriores al cierre de la Oferta de Acciones.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7131%2FTELECOM%20ARGENTINA%2DHR%20ON%20CLASE%205%2D%2DAviso%20de%20Resultados%20%2004%2D08%2D20%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7131&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7131%2FTELECOM%20ARGENTNA%20%2DHR%20ON%20CLASE%205%2D%20Suplemento%20%20%2D%20Oferta%2007%2D07%2D20%2EPDF&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7131&p=true&ga=1"""
}
MTCGO = {
    "Nombre Security": "ON Mastellone Hnos. Clase G Vto 30 06 2026",
    "Código": "MTCGO",
    "ISIN": "USP6460MAK01",
    "Calificación": "B-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Staples",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/06/2021",
    "Vencimiento": "30/06/2026",
    "Fecha Primer Cupón": "30/09/2021",
    "Cupón / Spread": 10.95, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/09/2021", "30/12/2021", "30/03/2022", "30/06/2022",
    "30/09/2022", "30/12/2022", "30/03/2023", "30/06/2023",
    "30/09/2023", "30/12/2023", "30/03/2024", "30/06/2024",
    "30/09/2024", "30/12/2024", "30/03/2025", "30/06/2025",
    "30/09/2025", "30/12/2025", "30/03/2026", "30/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "30/06/2021",
    "Precio Call": {"Desde la emisión ver debajo, m48 a m59: 1.05475, m60 a m71: 1.02378, m72 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Compañía podrá rescatar total o parcialmente las Nuevas Obligaciones Negociables en los siguientes escenarios:

                  - Antes de los dos años de la Fecha de Emisión, al 100%/ del capital más intereses devengados y una Prima Compensatoria.
                    - La Prima Compensatoria se calcula como el excedente entre:
                      1. La suma del valor presente de los pagos de capital e intereses descontados con el Rendimiento de los Títulos del Tesoro aplicable + 50 puntos básicos.
                      2. Menos el 100%/ del capital de las ON.

                  - A partir de los dos años de la Fecha de Emisión (Primera Fecha de Rescate a Precio Fijo), el rescate se hará a los siguientes precios:
                    - 30/06/2023: 105.475%.
                    - 30/06/2024: 102.738%.
                    - 30/06/2025 en adelante: 100.000%.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7573%2FMASTELLONE%20HNOS%20%2DHR%20Hecho%20Relevante%20anuncio%20de%20Resultados%2029%2D06%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7573&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7573%2FMASTELLONE%20HERMANOS%20%2DHR%20Suplemento%20de%20Precio%20Canje%2001%2D06%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7573&p=true&ga=1"""
}
BACGO = {
    "Nombre Security": "ON Banco Macro SA Clase G Vto 23 06 2029",
    "Código": "BACGO",
    "ISIN": "USP1047VAL10",
    "Calificación": "CCC",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/06/2025",
    "Vencimiento": "23/05/2029",
    "Fecha Primer Cupón": "23/12/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
"23/12/2025",
"23/6/2026",
"23/12/2026",
"23/6/2027",
"23/12/2027",
"23/6/2028",
"23/12/2028",
"23/6/2029"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción del emisor con prima o a la par según fecha",
    "Fecha Call": "23/06/2025",
    "Precio Call": {"Antes del 23/05/2029": "Mayor entre valor presente de flujos descontados a UST +50bps y 100% del capital"}, # Precio Call
    "Comentarios": """El emisor podrá rescatar las ONs total o parcialmente:
- Antes del 23/05/2029: al mayor entre (i) el valor presente de flujos remanentes descontados a la tasa del Tesoro +50pbs y (ii) el 100% del capital, más intereses devengados e impagos y montos adicionales.
- Desde el 23/05/2029: al 100%/ del capital, más intereses devengados e impagos y montos adicionales.""",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
MGC3O = {
    "Nombre Security": "ON Pampa Energia Clase III en USD Vto 15 04 2029",
    "Código": "MGC3O",
    "ISIN": "USP7464EAB22",
    "Calificación": "B-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/07/2019",
    "Vencimiento": "15/04/2029",
    "Fecha Primer Cupón": "15/10/2019",
    "Cupón / Spread": 9.1250, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["15/10/2019", "15/04/2020", "15/10/2020", "15/04/2021",
    "15/10/2021", "15/04/2022", "15/10/2022", "15/04/2023",
    "15/10/2023", "15/04/2024", "15/10/2024", "15/04/2025",
    "15/10/2025", "15/04/2026", "15/10/2026", "15/04/2027",
    "15/10/2027", "15/04/2028", "15/10/2028", "15/04/2029"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m57 (15/04/2024)",
    "Fecha Call": "15/04/2024",
    "Precio Call": {"m57 en m69: 1.04563, m70 en m81: 1.02281, m82 a m93: 1.01521,m94 a m105: 1.00"}, # Precio Call
    "Comentarios": """La Sociedad podrá rescatar total o parcialmente las Obligaciones Negociables:
                  - Antes de la fecha determinada en el Aviso de Resultados, al 100%/ del capital más intereses devengados e impagos, más la Prima de Rescate Aplicable.
                  - Desde la fecha determinada en el Aviso de Resultados en adelante, conforme a los precios de rescate establecidos en el Suplemento.
                  - En caso de ciertos eventos impositivos en Argentina, la Sociedad podrá rescatar la totalidad de las ON al 100% del capital más intereses devengados e impagos, más Montos Adicionales.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6756%2FPAMPA%20ENERGIA%2DHR%2DON%20CLASE%203%2D%20Aviso%20de%20Resultado%2002%2D07%2D19%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6756&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6756%2FPAMPA%20ENERGIA%2DHR%2DON%20CLASE%203%2D%20Suplemento%20de%20Prospecto%2001%2D07%2D19%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F6756&p=true&ga=1"""
}
BYCHO = {
    "Nombre Security": "ON Banco Galicia Clase XVI en dólares Vto 10 10 2028",
    "Código": "BYCHO",
    "ISIN": "USP0R66CAB48",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2024",
    "Vencimiento": "10/10/2028",
    "Fecha Primer Cupón": "10/04/2025",
    "Cupón / Spread": 7.750, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/04/2025", "10/10/2025", "10/04/2026", "10/10/2026",
    "10/04/2027", "10/10/2027", "10/04/2028", "10/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "10/10/2024",
    "Precio Call": {"desde la emisión: ver debajo"}, # Precio Call
    "Comentarios": """El Banco podrá rescatar total o parcialmente las Obligaciones Negociables en cualquier momento antes del vencimiento, 
                  sujeto a la normativa aplicable del BCRA. El precio de rescate será el mayor entre:
                  1. El 100%& del capital de las ON.
                  2. El valor presente de los pagos de capital e intereses descontados a la fecha de rescate con la Tasa del Tesoro más la tasa informada en el Aviso de Resultados, menos los intereses acumulados.
                  
                  En todos los casos, se adicionarán los intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9317%2FBANCO%20DE%20GALICIA%20%2DHR%20ON%20EF%20CLASE%20XVI%20%20%20Internacional%20%2D%20Aviso%20de%20Resultados%2004%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9317&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9317%2FBANCO%20DE%20GALICIA%20%20%2D%20HR%20ON%20EF%20CLASE%20XVI%20Internacional%202024%20Suplemento%2026%2D09%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9317&p=true&ga=1"""
}
PNWCO = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 30 Vto 02 03 2026",
    "Código": "PNWCO",
    "ISIN": "AR0365726709",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/02/2024",
    "Vencimiento": "02/03/2026",
    "Fecha Primer Cupón": "29/08/2024",
    "Cupón / Spread": 5.70, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["29/08/2024", "28/02/2025", "28/08/2025", "28/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "29/02/2024",
    "Precio Call": {"m1 a m8": 1.03, "m9 a m16": 1.02, "m17 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables bajo los siguientes términos:
                  - Desde la emisión hasta el mes 8: 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 9 hasta el mes 16: 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 17 hasta la Fecha de Vencimiento: 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8962%2FMPMAE%2DRES%2DON%20PAN%20AMERICAN%20ENERGY%20CLASE%2030%2D%20Aviso%20de%20Resultados%2027%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8962&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8962%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2030%2DSuplemento%20de%20Prospecto%2026%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8962&p=true&ga=1"
}
IRCPO = {
    "Nombre Security": "ON IRSA Clase XXIV en USD Vto 31 03 2035",
    "Código": "IRCPO",
    "ISIN": "USP58809BU07",
    "Calificación": "B",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/03/2025",
    "Vencimiento": "31/03/2035",
    "Fecha Primer Cupón": "30/09/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["30/09/2025", "31/03/2026", "30/09/2026", "31/03/2027",
    "30/09/2027", "31/03/2028", "30/09/2028", "31/03/2029",
    "30/09/2029", "31/03/2030", "30/09/2030", "31/03/2031",
    "30/09/2031", "31/03/2032", "30/09/2032", "31/03/2033",
    "30/09/2033", "31/03/2034", "30/09/2034", "31/03/2035"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 15 + [33] + [0] + [33] + [0] + [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad desde la emisión",
    "Fecha Call": "31/03/2025",
    "Precio Call": {"m0 a m48": "rescate con prima compensatoria", "m49 a m60": 1.04,
    "m61 a m72": 1.02, "m73 a m84": 1.01, "m85 en adelante": 1.00}, # Precio Call
    "Comentarios": """Con anterioridad al 31 de marzo de 2029 (la “Primera Fecha de Rescate”), 
la Emisora podrá rescatar las Obligaciones Negociables, en su totalidad o en parte, a un precio igual al mayor entre:
(1) el 100%/ del monto de capital pendiente, y 
(2) el valor presente de los pagos de capital e intereses restantes, descontados semestralmente 
a la Tasa del Tesoro aplicable + 50 puntos básicos. En ambos casos se adicionan los intereses devengados y no pagados hasta la fecha de rescate.

La Tasa del Tesoro será determinada por la Emisora en base al informe H.15 publicado por la Reserva Federal de EE.UU., 
usando interpolación si es necesario, o mediante selección del bono más cercano y más negociado en caso de no haber coincidencia exacta.

Desde el 31/03/2029, la Emisora podrá efectuar rescates opcionales programados conforme al siguiente esquema:
- Desde el 31/03/2029: 104,00%
- Desde el 31/03/2030: 102,00%
- Desde el 31/03/2031: 101,00%
- Desde el 31/03/2032 y en adelante: 100,00%""",
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/071d86e4-b806-4609-a28e-ca6968260c87",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/5a8663c3-90bc-46ec-8b12-6eb61108421f"
}
VSCOO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXIII Vto 06 03 2027",
    "Código": "VSCOO",
    "ISIN": "AR0399155156",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/03/2024",
    "Vencimiento": "06/03/2027",
    "Fecha Primer Cupón": "06/09/2024",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["06/09/2024", "06/03/2025", "06/09/2025", 
    "06/03/2026", "06/09/2026", "06/03/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "06/03/2024",
    "Precio Call": {"Desde la emisión en adelante: 1."}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la 
normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o 
una parte de las Obligaciones Negociables que se encuentren en circulación, en 
cualquier momento desde la Fecha de Emisión y Liquidación, al valor nominal con 
más los intereses devengados hasta la fecha de pago del valor de rescate (el “Valor 
del Rescate”).""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8987%2FMPMAE%2DRES%2DON%20VISTA%20ENERGY%20CLASE%20XXIII%20%2D%20Aviso%20de%20Resultados%2004%2D03%2D2024%2E%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8987&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8987%2FMPMAE%2DANU%2DON%20VISTA%20ENERGY%20CLASE%20XXIII%2D%20Suplemento%20Prospecto%20%2029%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8987&p=true&ga=1"""
}
VSCUO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXVIII Vto 07 03 2030",
    "Código": "VSCUO",
    "ISIN": "AR0707929003",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/03/2025",
    "Vencimiento": "07/03/2030",
    "Fecha Primer Cupón": "07/09/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "07/09/2025", "07/03/2026", "07/09/2026", "07/03/2027", "07/09/2027",
    "07/03/2028", "07/09/2028", "07/03/2029", "07/09/2029", "07/03/2030"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "CLEAN",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "07/03/2025",
    "Precio Call": {"m1 en adelante": 1.}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la
normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación, en
cualquier momento desde la Fecha de Emisión y Liquidación, al valor nominal con más los intereses devengados y no pagados, calculados hasta la fecha de pago del
valor de rescate (el “Valor del Rescate”)""",
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/da69033e-eaf3-42d2-a411-d7afb3ca631e#",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/d4f7836b-2501-401d-8cce-a1448601c7e7#"
}
VSCVO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXIX Vto 10 06 2033",
    "Código": "VSCVO",
    "ISIN": "USP9659RAB44",
    "Calificación": "BB-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Nueva York",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/06/2025",
    "Vencimiento": "10/06/2033",
    "Fecha Primer Cupón": "10/12/2025",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["10/12/2025", "10/06/2026", "10/12/2026", "10/06/2027",
    "10/12/2027", "10/06/2028", "10/12/2028", "10/06/2029",
    "10/12/2029", "10/06/2030", "10/12/2030", "10/06/2031",
    "10/12/2031", "10/06/2032", "10/12/2032", "10/06/2033"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33] + [0]+ [33] + [0]+ [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión con cláusula make-whole",
    "Fecha Call": "10/06/2025",
    "Precio Call": {"m1 en adelante": 1.}, # Precio Call
    "Comentarios": """La Sociedad podrá rescatar, a su opción, total o parcialmente, las Obligaciones Negociables antes del 10/06/2028 (“Fecha de Primera Recompra”) al mayor entre:
(1) 100% del capital; y
(2) el valor presente del precio y los intereses hasta la Fecha de Primera Recompra, descontados semestralmente a Tasa del Tesoro +50 pbs (más Montos Adicionales si los hubiera),
añadiendo en ambos casos los intereses devengados e impagos hasta la fecha de rescate.

A partir del 10/06/2028, la Sociedad podrá efectuar rescates programados anuales durante 12 meses con los siguientes precios:
- Desde el 10/06/2028: 104,250%
- Desde el 10/06/2029: 102,125%
- Desde el 10/06/2030 en adelante: 100,000%""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9570%2FMPMAE%2DRES%2DON%20VISTA%20ENERGY%20CLASE%20XXXVIII%2D%20%20Aviso%20de%20Resultados%2005%2D03%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9570&p=true&ga=1",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/79f3b7e6-2753-4d7a-bbff-088c1deedbe1"
}
VSCTO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXVII Vto 10 12 2035",
    "Código": "VSCTO",
    "ISIN": "USP9659RAA60",
    "Calificación": "CCC+",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/12/2024",
    "Vencimiento": "10/12/2035",
    "Fecha Primer Cupón": "10/06/2025",
    "Cupón / Spread": 7.6250, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "10/6/2025", "10/12/2025", "10/6/2026", "10/12/2026", "10/6/2027", "10/12/2027",
    "10/6/2028", "10/12/2028", "10/6/2029", "10/12/2029", "10/6/2030", "10/12/2030",
    "10/6/2031", "10/12/2031", "10/6/2032", "10/12/2032", "10/6/2033", "10/12/2033",
    "10/6/2034", "10/12/2034", "10/6/2035", "10/12/2035"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 17 + [33] + [0]+ [33] + [0]+ [34]),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "10/12/2024",
    "Precio Call": {"m1 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Sociedad también podrá rescatar las Obligaciones Negociables, en forma total pero no parcial, a un precio igual al 100% del monto de capital más los
intereses devengados e impagos y cualesquiera Montos Adicionales ante el acaecimiento de ciertos supuestos específicos impositivos en Argentina.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9439%2FVISTA%20ENERGY%20ARGENTINA%2DHR%20ON%20CLASE%20XXVII%2D%20Aviso%20de%20Resultados%2004%2D12%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9439&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9439%2FVISTA%20ENERGY%20ARGENITNA%20%2DHR%2D%20ON%20%20Clase%20XXVII%20Suplemento%20Prospecto%2026%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9439&p=true&ga=1"""
}
YMCHO = {
    "Nombre Security": "ON YPF S.A. Clase XVI Vto 12 02 2026",
    "Código": "YMCHO",
    "ISIN": "USP989MJBR17",
    "Calificación": "B-",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Legislación": "Estados Unidos",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/02/2021",
    "Vencimiento": "12/02/2026",
    "Fecha Primer Cupón": "12/05/2021",
    "Cupón / Spread": 9., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["12/05/2021", "12/08/2021", "12/11/2021", "12/02/2022",
    "12/05/2022", "12/08/2022", "12/11/2022", "12/02/2023",
    "12/05/2023", "12/08/2023", "12/11/2023", "12/02/2024",
    "12/05/2024", "12/08/2024", "12/11/2024", "12/02/2025",
    "12/05/2025", "12/08/2025", "12/11/2025", "12/02/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [7.6923076923076933] * 13),
    "Quote Price Convention": "CLEAN",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parical a opción de la sociedad a partir de la emisión",
    "Fecha Call": "12/02/2021",
    "Precio Call": {"m1 a m57: ver debajo, m57 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Sociedad podrá rescatar total o parcialmente las Obligaciones Negociables Respaldadas por Exportaciones Clase XVI en los siguientes escenarios:

                - Antes de los 3 meses previos a la fecha de vencimiento, al 100%/ del capital más intereses devengados y una Prima de Rescate Aplicable.
                - La Prima de Rescate Aplicable se calcula como el excedente entre:
                      1. La suma del valor presente de los pagos de capital e intereses descontados con la Tasa del Tesoro Ajustada + 50 puntos básicos.
                      2. Menos el 100%/ del capital de las ON.

                  - Desde los 3 meses previos a la fecha de vencimiento, el rescate se hará a 100%/ del capital más intereses devengados hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7379%2FYPF%20%20Aviso%20de%20Resultados%20%2011%2D02%2D21%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7379&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7379%2FYPF%20%2D%20HR%20Suplemento%20de%20Precio%20%2D%20Oferta%20de%20Canje%20%2D%20emision%20ON%20Clase%2016%2D17%2D18%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7379&p=true&ga=1"""
}
LMS8O = {
    "Nombre Security": "ON Aluar Aluminio Argentino S.A.I.C Serie 8 Vto 21 03 2027",
    "Código": "LMS8O",
    "ISIN": "AR0787528089",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Materials",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/03/2024",
    "Vencimiento": "21/03/2027",
    "Fecha Primer Cupón": "21/09/2024",
    "Cupón / Spread": 6.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "21/09/2024",
    "21/12/2024",
    "21/03/2025",
    "21/06/2025",
    "21/09/2025",
    "21/12/2025",
    "21/03/2026",
    "21/06/2026",
    "21/09/2026",
    "21/12/2026",
    "21/03/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [25] * 4),
    "Quote Price Convention": "DIRTY",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m24 desde la emisión",
    "Fecha Call": "21/03/2026",
    "Precio Call": {"m24 en adelante: 1.01"}, # Precio Call
    "Comentarios": """Las Obligaciones Negociables podrán ser rescatadas, a opción de la Compañía, en todo o en parte, 
                      a partir del mes 24 desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                      - Desde el mes 25 hasta la Fecha de Vencimiento: 101%/ del capital, más intereses devengados e impagos.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9013%2FMPMAE%2DRES%2DON%20ALUAR%20SERIE%208%20Aviso%20de%20Resultados%2019%2D03%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9013&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9013%2FMPMAE%2DANU%2DON%20ALUAR%20SERIE%208%20%20Suplemento%20de%20Prospecto%2012%2D03%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9013&p=true&ga=1"
}
LMS9O = {
    "Nombre Security": "ON Aluar Aluminio Argentino S.A.I.C Serie 9 Vto 13 06 2026",
    "Código": "LMS9O",
    "ISIN": "AR0226237573",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Materials",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/06/2024",
    "Vencimiento": "13/06/2026",
    "Fecha Primer Cupón": "13/12/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "13/12/2024",
    "13/03/2025",
    "13/06/2025",
    "13/09/2025",
    "13/12/2025",
    "13/03/2026",
    "13/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del mes 13 desde la emisión",
    "Fecha Call": "14/06/2025",
    "Precio Call": {"m13 en adelante: 1."}, # Precio Call
    "Comentarios": """Las Obligaciones Negociables podrán ser rescatadas, a opción de la Compañía, en todo o en parte, a partir del mes 13 desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde el mes 13 hasta la Fecha de Vencimiento: Precio de rescate de 100%/ del capital, más intereses devengados e impagos.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9118%2FMPMAE%2DRES%2DON%20ALUAR%20SERIE%209%2D%20aviso%20de%20resultados%2011%2D06%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9118&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9118%2FMPMAE%2DANU%2DON%20ALUAR%20SERIE%209%2E%20Supmento%20Prosopecto%2005%2D06%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9118&p=true&ga=1"
}

# Fichas ON HARD DOLAR MEP Corporativos
PECIO = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Clase XVII Vto 30 01 2028",
    "Código": "PECIO",
    "ISIN": "AR0541458847",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/01/2025",
    "Vencimiento": "30/01/2028",
    "Fecha Primer Cupón": "30/07/2025",
    "Cupón / Spread": 9., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/7/2025",
    "30/1/2026",
    "30/7/2026",
    "30/1/2027",
    "30/7/2027",
    "30/1/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7218%2FMPMAE%2DRES%2DON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%2017%2DAviso%20de%20Resultado%2028%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7218&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9506%2FMPMAE%2DANU%2DON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%2017%2DSuplemento%2022%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9506&p=true&ga=1"""
}
MR35O = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XXXV Vto. 26 08 2027",
    "Código": "MR35O",
    "ISIN": "AR0830476534",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/08/2024",
    "Vencimiento": "28/08/2027",
    "Fecha Primer Cupón": "28/02/2025",
    "Cupón / Spread": 9.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/02/2025",
    "28/08/2025",
    "28/02/2026",
    "28/08/2026",
    "28/02/2027",
    "28/08/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9258%2FMPMAE%2DRES%2DON%20COEMISION%20GEMSA%20Y%20CTR%20CLASES%2035%2036%2037%20Y%2038%2DAviso%20de%20Resultados%2026%2D08%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9258&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9258%2FMPMAE%2DANU%2DON%20COEMISION%20GEMSA%20Y%20CTR%20CLASES%2035%2036%2037%20Y%2038%20%2D%20Suplemento%2009%2D08%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9258&p=true&ga=1"""
}
MRCUO = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XXVIII Vto. 08 03 2026",
    "Código": "MRCUO",
    "ISIN": "AR0336525404",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/03/2024",
    "Vencimiento": "08/03/2026",
    "Fecha Primer Cupón": "08/09/2024",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "08/09/2024",
    "08/03/2025",
    "08/09/2025",
    "08/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100%2FMPMAE%2DRES%2DON%20COEMISION%20GEMSA%2DCTR%20Clase%2032%20y%2033%2DAviso%20de%20Resultado%2028%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100%2FMPMAE%2DANU%2DON%20COEMISION%20GEMSA%2DCTR%20Clases%2032%20y%2033%2DSuplemento%2022%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100&p=true&ga=1"""
}
MRCYO = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XXXII Vto. 30 05 2026",
    "Código": "MRCYO",
    "ISIN": "AR0943273380",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/05/2024",
    "Vencimiento": "30/05/2026",
    "Fecha Primer Cupón": "30/11/2024",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/11/2024",
    "30/05/2025",
    "30/11/2025",
    "30/05/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100%2FMPMAE%2DRES%2DON%20COEMISION%20GEMSA%2DCTR%20Clase%2032%20y%2033%2DAviso%20de%20Resultado%2028%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100%2FMPMAE%2DANU%2DON%20COEMISION%20GEMSA%2DCTR%20Clases%2032%20y%2033%2DSuplemento%2022%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9100&p=true&ga=1"""
}
LDCGO = {
    "Nombre Security": "ON Ledesma S.A.A.I. Clase 15 Vto 04 10 2027",
    "Código": "LDCGO",
    "ISIN": "AR0079775596",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Consumer Staples",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/02/2025",
    "Vencimiento": "04/10/2027",
    "Fecha Primer Cupón": "04/05/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "04/05/2025",
    "04/08/2025",
    "04/11/2025",
    "04/02/2026",
    "04/05/2026",
    "04/08/2026",
    "04/11/2026",
    "04/02/2027",
    "04/05/2027",
    "04/08/2027",
    "04/10/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9520%2FMPMAE%2DRES%2DON%20LEDESMA%20CLASE%2015%2D%20Aviso%20de%20Resultados%2030%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9520&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9520%2FMPMAE%2DANU%2DON%20LEDESMA%20CLASE%2015%2D%20Suplemento%20de%20Prospecto%2023%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9520&p=true&ga=1"""
}
CP36O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXXVI Vto 10 10 2027",
    "Código": "CP36O",
    "ISIN": "AR0015464982",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2024",
    "Vencimiento": "10/10/2027",
    "Fecha Primer Cupón": "10/04/2025",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/04/2025",
    "10/10/2025",
    "10/04/2026",
    "10/10/2026",
    "10/04/2027",
    "10/10/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9319%2FMPMAE%2DRES%2DON%20CIA%20GRAL%20DE%20COMBUSTIBLES%20CLASE%2036%2D%20Aviso%20dr%20Resultados%2008%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9319&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9319%2FMPMAE%2DANU%2D%20ON%20EF%20CIA%20GRAL%20COMBUSTIBLES%20CLASE%2036%20Suplemento%20Prospecto%2003%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9319&p=true&ga=1"""
}
CP37O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXXVII Vto 10 03 2027",
    "Código": "CP37O",
    "ISIN": "AR0172788611",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/03/2025",
    "Vencimiento": "10/03/2027",
    "Fecha Primer Cupón": "10/06/2025",
    "Cupón / Spread": 7.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/06/2025",
    "10/09/2025",
    "10/12/2025",
    "10/03/2026",
    "10/06/2026",
    "10/09/2026",
    "10/12/2026",
    "10/03/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/39111327-d734-4ec0-b540-bad6dcdc5db4#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/6f937fc9-26c1-488e-a2b9-0c51df1cce88#"""
}
T641O = {
    "Nombre Security": "ON Tarjeta Naranja S.A.U. Clase 64 Serie I Vto. 30 04 2027",
    "Código": "T641O",
    "ISIN": "T641O",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/04/2025",
    "Vencimiento": "30/04/2027",
    "Fecha Primer Cupón": "29/07/2025",
    "Cupón / Spread": 7.90, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/07/2025", "29/10/2025", "29/01/2026", "29/04/2026",
    "29/07/2026", "29/10/2026", "29/01/2027", "30/04/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DRES%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DAviso%20de%20Resultado%2025%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DANU%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DSuplemento%2023%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1"""
}
PUC2O = {
    "Nombre Security": "ON Petroleos Sudamericanos S.A. Clase II Vto. 28 08 2027",
    "Código": "PUC2O",
    "ISIN": "AR0069816632",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2025",
    "Vencimiento": "28/08/2027",
    "Fecha Primer Cupón": "28/08/2025",
    "Cupón / Spread": 8.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/08/2025",
    "28/02/2026",
    "28/08/2026",
    "28/02/2027",
    "28/08/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9560%2FMPMAE%2DRES%2DON%20PETROLEOS%20SUDAMERICANOS%20CLASE%202%2DAviso%20de%20Resultados%2026%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9560&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9560%2FMPMAE%2DANU%2DON%20PETROLEOS%20SUDAMERICANOS%20CLASE%202%2DSuplemento%20de%20Prospecto%2020%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9560&p=true&ga=1"""
}
LIC6O = {
    "Nombre Security": "ON Lipsa S.R.L. Clase VI Vto 02 07 2026",
    "Código": "LIC6O",
    "ISIN": "AR0844690534",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Legislación": "Argentina",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "02/07/2024",
    "Vencimiento": "02/07/2026",
    "Fecha Primer Cupón": "02/01/2025",
    "Cupón / Spread": 9., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["02/01/2025", "02/04/2025", "02/07/2025", "02/10/2025",
    "02/01/2026", "02/04/2026", "02/07/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [33] * 2 + [34]),
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9153%2FMPMAE%2DRES%2DON%20LIPSA%20%20Clase%20VI%20%2D%20Aviso%20de%20Resultados%2027%2D06%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9153&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9153%2FMPMAE%2DANU%2DON%20LIPSA%20Clase%20VI%20%2D%20Suplemento%2019%2D06%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9153&p=true&ga=1"""
}
JNC5O = {
    "Nombre Security": "ON Inversora Juramento S.A. Clase V Vto 09 10 2026",
    "Código": "JNC5O",
    "ISIN": "AR0809983775",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/10/2024",
    "Vencimiento": "09/10/2026",
    "Fecha Primer Cupón": "09/01/2025",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/01/2025", "09/04/2025", "09/07/2025", "09/10/2025",
    "09/01/2026", "09/04/2026", "09/07/2026", "09/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9312%2FMPMAE%2DRES%2DON%20INVERSORA%20JURAMENTO%20CLASE%20V%20%20Aviso%20de%20Resultados%20%2D07%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9312&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9312%2FMPMAE%2DANU%2DON%20INVERSORA%20JURAMENTO%20CLASE%205%2DSuplemento%20de%20Prospecto%2001%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9312&p=true&ga=1"""
}
SNSBO = {
    "Nombre Security": "ON San Miguel A.G.I.C.I. Y F. Serie XI Vto. 14 10 2026",
    "Código": "SNSBO",
    "ISIN": "AR0792131879",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/10/2024",
    "Vencimiento": "14/10/2026",
    "Fecha Primer Cupón": "14/04/2025",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["14/04/2025", "14/07/2025", "14/10/2025", "14/01/2026",
    "14/04/2026", "14/07/2026", "14/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9335%2FMPMAE%2DRES%2DON%20SAN%20MIGUEL%20SERIE%2011%2DAviso%20de%20Resultado%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9335&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9335%2FMPMAE%2DANU%2DON%20SAN%20MIGUEL%20SERIE%2011%2DSuplemento%20de%20Prospecto%2002%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9335&p=true&ga=1"""
}
SNSDO = {
    "Nombre Security": "ON San Miguel A.G.I.C.I. Y F. Serie XII Vto. 06 02 2027",
    "Código": "SNSDO",
    "ISIN": "AR0228143829",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/02/2025",
    "Vencimiento": "06/08/2025",
    "Fecha Primer Cupón": "06/02/2027",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["06/08/2025",
    "06/02/2026",
    "06/08/2026",
    "06/02/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9522%2FMPMAE%2DRES%2DON%20SAN%20MIGUEL%20SERIE%2012%2DAviso%20de%20Resultado%2004%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9522&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9522%2FMPMAE%2DANU%2DON%20SAN%20MIGUEL%20SERIE%2012%2D%20Suplemento%2029%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9522&p=true&ga=1"""
}
PECAO = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Clase X Vto 01 03 2027",
    "Código": "PECAO",
    "ISIN": "AR0342949143",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/02/2024",
    "Vencimiento": "01/03/2027",
    "Fecha Primer Cupón": "29/08/2024",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "29/08/2024",
    "28/02/2025",
    "28/08/2025",
    "28/02/2026",
    "28/08/2026",
    "28/02/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8984%2FMPMAE%2DRES%2DON%20PETROLERA%20ACONCAGUA%208%2D9%2D10%2D11%2DAviso%20de%20Resultados%2027%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8984&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8984%2FMPMAE%2DANU%2DON%20PETROLERA%20ACONCAGUA%20CLASES%208%2D9%2D10%2D11%2DSuplemento%2021%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8984&p=true&ga=1"""
}
PECBO = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Clase XI Vto 29 02 2028",
    "Código": "PECBO",
    "ISIN": "AR0781932378",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/02/2024",
    "Vencimiento": "29/02/2028",
    "Fecha Primer Cupón": "29/08/2024",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/08/2024", "28/02/2025", "28/08/2025", "28/02/2026",
    "28/08/2026", "28/02/2027", "28/08/2027", "28/02/2028"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33.33] * 2 + [33.34]),
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8985%2FMPMAE%2DRES%2DON%20PETROLERA%20ACONCAGUA%208%2D9%2D10%2D11%2DAviso%20de%20Resultados%2027%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8985&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8985%2FMPMAE%2DANU%2DON%20PETROLERA%20ACONCAGUA%20CLASES%208%2D9%2D10%2D11%2DSuplemento%2021%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8985&p=true&ga=1"""
}
OZC3O = {
    "Nombre Security": "ON EDEMSA Clase 3 Vto 29 11 2027",
    "Código": "OZC3O",
    "ISIN": "AR0428738048",
    "Calificación": "A2(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "29/11/2027",
    "Fecha Primer Cupón": "29/05/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/05/2025", "29/11/2025", "29/05/2026", "29/11/2026",
    "29/05/2027", "29/11/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412%2FMPMAE%2DRES%2DON%20EDEMSA%20CLASE%203%20Y%204%2DAviso%20de%20Resultado%2028%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412%2FMPMAE%2DANU%2DON%20EDEMSA%20CLASE%203%20Y%204%2DSuplemento%2022%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412&p=true&ga=1"""
}
RZ9BO = {
    "Nombre Security": "ON Rizobacter Argentina SA Serie IX Clase B 28 06 2026",
    "Código": "RZ9BO",
    "ISIN": "AR0069851811",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/06/2024",
    "Vencimiento": "28/06/2026",
    "Fecha Primer Cupón": "28/09/2024",
    "Cupón / Spread": 7.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/09/2024", "28/12/2024", "28/03/2025",
    "28/06/2025", "28/09/2025", "28/12/2025",
    "28/03/2026", "28/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9142%2FMPMAE%2DRES%2DON%20RIZOBACTER%20SERIE%209%2DAviso%20de%20Resultado%2026%2D06%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9142&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9142%2FMPMAE%2DANU%2DON%20RIZOBACTER%20SERIE%209%2DSuplemento%2018%2D06%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9142&p=true&ga=1"""
}
RZABO = {
    "Nombre Security": "ON Rizobacter Argentina SA Serie X Clase B 28 11 2027",
    "Código": "RZABO",
    "ISIN": "AR0272566107",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/11/2024",
    "Vencimiento": "28/11/2027",
    "Fecha Primer Cupón": "28/02/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/02/2025", "28/05/2025", "28/08/2025", "28/11/2025",
    "28/02/2026", "28/05/2026", "28/08/2026", "28/11/2026",
    "28/02/2027", "28/05/2027", "28/08/2027", "28/11/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9424%2FMPMAE%2DRES%2DON%20RIZOBACTER%20SERIE%2010%2DAviso%20de%20Resultados%2025%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9424&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9424%2FMPMAE%2DANU%2DON%20RIZOBACTER%20SERIE%2010%2DSuplemento%2019%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9424&p=true&ga=1"""
}
BYCNO = {
    "Nombre Security": "ON Banco Galicia Clase XXII Vto 10 08 2025",
    "Código": "BYCNO",
    "ISIN": "AR0606975438",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/02/2025",
    "Vencimiento": "10/08/2025",
    "Fecha Primer Cupón": "10/08/2025",
    "Cupón / Spread": 4.15, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9529%2FMPMAE%2DRES%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XXII%20%2D%20Aviso%20de%20Resultados%2006%2D02%2D2025%2EPDF%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9529&p=true&ga=1""",
    "Suplemento Prospecto": """"https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9529%2FMPMAE%2DANU%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XXI%20Prospecto%20Emisor%20Frecuente%20Galicia%2009%2D05%2D24%2EPDF%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9529&p=true&ga=1"""
}
TN63O = {
    "Nombre Security": "ON Tarjeta Naranja S.A.U. Clase 63 Vto. 28 11 2025",
    "Código": "TN63O",
    "ISIN": "AR0355743292",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "26/11/2024",
    "Vencimiento": "28/11/2025",
    "Fecha Primer Cupón": "28/02/2025",
    "Cupón / Spread": 6.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/02/2025", "30/05/2025", "29/08/2025", "28/11/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 2 + [50] * 2),
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9410%2FMPMAE%2DRES%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2063%2DAviso%20de%20Resultado%2021%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9410&p=true&ga=1""",
    "Suplemento Prospecto": """"https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9410%2FMPMAE%2DANU%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2063%2DSuplemento%2014%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9410&p=true&ga=1"""
}
XMC1O = {
    "Nombre Security": "ON Minera Exar Clase 1 Vto 11 11 2027",
    "Código": "XMC1O",
    "ISIN": "AR0778941762",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar MEP",
    "Industria": "Materials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/11/2024",
    "Vencimiento": "11/11/2027",
    "Fecha Primer Cupón": "11/05/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["11/05/2025", "11/11/2025",
    "11/05/2026", "11/11/2026",
    "11/05/2027", "11/11/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [50] * 2),
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9378%2FMPMAE%2DRES%2DON%20MINERA%20EXAR%20CLASE%201%2DAviso%20de%20Resultados%2007%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9378&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9378%2FMPMAE%2DANU%2DON%20MINERA%20EXAR%20CLASE%201%20%2D%20Suplemento%2031%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9378&p=true&ga=1"""
}
GOC4O = {
    "Nombre Security": "ON Generacion del Litoral S.A. Clase IV Vto 28 04 2029",
    "Código": "GOC4O",
    "ISIN": "AR0855924731",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "24/10/2024",
    "Vencimiento": "28/04/2029",
    "Fecha Primer Cupón": "28/10/2025",
    "Cupón / Spread": [4.,10.75], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 12., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/10/2025", "28/11/2025", "28/12/2025", "28/01/2026", "28/02/2026", "28/03/2026",
    "28/04/2026", "28/05/2026", "28/06/2026", "28/07/2026", "28/08/2026", "28/09/2026",
    "28/10/2026", "28/11/2026", "28/12/2026", "28/01/2027", "28/02/2027", "28/03/2027",
    "28/04/2027", "28/05/2027", "28/06/2027", "28/07/2027", "28/08/2027", "28/09/2027",
    "28/10/2027", "28/11/2027", "28/12/2027", "28/01/2028", "28/02/2028", "28/03/2028",
    "28/04/2028", "28/05/2028", "28/06/2028", "28/07/2028", "28/08/2028", "28/09/2028",
    "28/10/2028", "28/11/2028", "28/12/2028", "28/01/2029", "28/02/2029", "28/03/2029",
    "28/04/2029"], # Lista de fechas como ejemplo
    "Intereses":[4.04383561643836, 
 0.913013698630137, 
 0.865890410958904,
 0.876493150684932,
 0.858232876712329,
 0.758684931506849,
 0.821712328767123,
 0.777534246575342,
 0.785191780821918,
 0.742191780821918,
 0.748671232876712,
 0.73041095890411,
 0.689178082191781,
 0.693890410958904,
 0.651626712328767,
 0.652804794520548,
 0.63226198630137,
 0.552520547945205,
 0.591176369863014,
 0.55222602739726,
 0.550090753424658,
 0.512465753424658,
0.509005136986301,
0.488462328767123,
0.452825342465753,
0.447376712328767,
0.410856164383562,
0.40172602739726,
0.378900684931507,
0.333102739726027,
0.33325,
0.30041095890411,
0.287599315068493,
0.256232876712329,
0.241948630136986,
0.219123287671233,
0.189965753424658,
0.173472602739726,
0.145787671232877,
0.127821917808219,
0.104996575342466,
0.0742191780821918,
0.0593458904109589,
],
    "Amortización": ([0] + [2] * 12 + [2.25] * 12 + [2.50] * 17 + [6.50]),
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del mes 12 desde la emisión",
    "Fecha Call": "24/10/2025",
    "Precio Call": {"m12 a m23: 1.01, m24 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad de las Obligaciones Negociables a partir del mes doce (12) desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde el mes 12 hasta el mes 23: Precio de rescate de 101% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 24 hasta la Fecha de Vencimiento: Precio de rescate de 100% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9343%2FMPMAE%2DRES%2DON%20GENERACION%20LITORAL%20CLASE%20IV%2DAviso%20de%20Resultado%2023%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9343&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9343%2FMPMAE%2DANU%2DON%20GENERACION%20LITORAL%20CLASE%20IV%20%2D%20Suplemento%2016%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9343&p=true&ga=1"""
}
YFCLO = {
    "Nombre Security": "ON YPF LUZ Clase XIX Vto. 22 11 2028",
    "Código": "YFCLO",
    "ISIN": "AR0338531962",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/11/2024",
    "Vencimiento": "22/11/2028",
    "Fecha Primer Cupón": "22/08/2025",
    "Cupón / Spread": 6.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "22/08/2025", "22/11/2025", "22/02/2026", "22/05/2026",
    "22/08/2026", "22/11/2026", "22/02/2027", "22/05/2027",
    "22/08/2027", "22/11/2027", "22/02/2028", "22/05/2028",
    "22/08/2028", "22/11/2028"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m12 de la emisión",
    "Fecha Call": "22/11/2027",
    "Precio Call": {"m36 en adelante": 1}, # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la 
totalidad o una parte de las Obligaciones Negociables Clase XX que se encuentren en circulación en cualquier momento, a partir del mes treinta y 
seis (36°) (inclusive) contado desde la Fecha de Emisión y Liquidación, al precio de rescate de capital de 100% (más los Montos Adicionales y 
cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XX).""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9397%2FMPMAE%2DRES%2DON%20EF%20YPF%20ENERGIA%20ELECTRICA%20Clase%20XIX%20y%20XX%2DAviso%20de%20Resultado%2020%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9397&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9397%2FMPMAE%2DANU%2DON%20EF%20YPF%20ENERGIA%20ELECTRICA%20Clase%20XIX%20y%20XX%20Suplemento%2012%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9397&p=true&ga=1"""
}
BFCZO = {
    "Nombre Security": "ON Banco BBVA Argentina S.A. Clase 33 Vto. 27 08 2025",
    "Código": "BFCZO",
    "ISIN": "AR0283170097",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/08/2025",
    "Fecha Primer Cupón": "27/08/2025",
    "Cupón / Spread": 4., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["27/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DRES%2D%20ON%20BANCO%20BBVA%20ARGENTINA%20CLASE%2032%2D33%2D34%2DAviso%20resultado%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DANU%2DON%20BANCO%20BBVA%20%20Clases%2032%2033%20y%2034%20Suplemento%20de%20Prospecto%2018%2E02%2E25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1"
}
GN48O = {
    "Nombre Security": "ON Genneia S.A. Clase XLVIII Vto 05 03 2028",
    "Código": "GN48O",
    "ISIN": "AR0580434501",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/03/2025",
    "Vencimiento": "05/03/2028",
    "Fecha Primer Cupón": "05/08/2025",
    "Cupón / Spread": 6.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
        "05/09/2025", "05/03/2026", "05/09/2026", "05/03/2027",
        "05/09/2027", "05/03/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m33 de la emisión",
    "Fecha Call": "05/12/2027",
    "Precio Call": {"m33 en adelante": 1}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con 
la normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables que se encuentren 
en circulación, en cualquier momento, a partir del mes 33 (inclusive) contado desde la Fecha de Emisión y Liquidación, al valor nominal con más 
los intereses devengados hasta la fecha de pago del valor de rescate (el “Valor del Rescate”).""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EeuMEC9B7ANKv8IFEyizM3IBoFoU0ggNj2w9zMNq1kQSAA",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9565%2FMPMAE%2DANU%2DON%20GENNEIA%20CLASE%20XLVIII%20%20Suplemento%20Prospecto%2021%2D02%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9565&p=true&ga=1"
}
CS38O = {
    "Nombre Security": "ON Cresud S.A.C.I.F y A. Serie XXVI Clase XXXVIII Vto 03 03 2026",
    "Código": "CS38O",
    "ISIN": "ARCRES5600V9",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/07/2022",
    "Vencimiento": "03/03/2026",
    "Fecha Primer Cupón": "03/01/2023",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "03/01/2023",
    "03/07/2023",
    "03/01/2024",
    "03/07/2024",
    "03/01/2025",
    "03/07/2025",
    "03/01/2026",
    "03/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m48 de la emisión",
    "Fecha Call": "03/09/2025",
    "Precio Call": {"m48 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, podremos rescatar a nuestra opción las Obligaciones 
Negociables Clase XLIV, en o desde la fecha en que se cumplan seis meses previos a la Fecha de Vencimiento, a un precio igual 
al 101%/ del valor nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en forma total o 
parcial""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917%2FMPMAE%2DRES%2D%20ON%20CRESUD%20CLASE%20%20XLIII%20y%20XLIV%20Aviso%20de%20Resultados%2011%2D01%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917%2FMPMAE%2DANU%2DON%20CRESUD%20Clase%20XLIII%20y%20Clase%20XLIV%20Suplemento%20Prospecto%2005%2D01%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917&p=true&ga=1"
}
CS44O = {
    "Nombre Security": "ON Cresud S.A.C.I.F y A. Serie 28 Clase XLIV Vto 17 01 2027",
    "Código": "CS44O",
    "ISIN": "AR0941280056",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2024",
    "Vencimiento": "17/01/2027",
    "Fecha Primer Cupón": "17/07/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["17/07/2024",
    "17/01/2025",
    "17/07/2025",
    "17/01/2026",
    "17/07/2026",
    "17/01/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 de la emisión",
    "Fecha Call": "17/07/2027",
    "Precio Call": {"m30 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, podremos rescatar a nuestra opción las Obligaciones 
Negociables Clase XLIV, en o desde la fecha en que se cumplan seis meses previos a la Fecha de Vencimiento, a un precio igual 
al 101%/ del valor nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en forma total o 
parcial.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917%2FMPMAE%2DRES%2D%20ON%20CRESUD%20CLASE%20%20XLIII%20y%20XLIV%20Aviso%20de%20Resultados%2011%2D01%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917%2FMPMAE%2DANU%2DON%20CRESUD%20Clase%20XLIII%20y%20Clase%20XLIV%20Suplemento%20Prospecto%2005%2D01%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8917&p=true&ga=1"
}
CS45O = {
    "Nombre Security": "ON Cresud S.A.C.I.F y A. Serie 29 Clase XLV Vto 22 08 2026",
    "Código": "CS45O",
    "ISIN": "AR0529152206",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/04/2024",
    "Vencimiento": "22/08/2026",
    "Fecha Primer Cupón": "22/10/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "22/10/2024",
    "22/04/2025",
    "22/10/2025",
    "22/04/2026",
    "22/08/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m22 de la emisión",
    "Fecha Call": "22/02/2026",
    "Precio Call": {"m22 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, podremos rescatar a nuestra opción las Obligaciones Negociables 
Clase XLV, en o desde la fecha en que se cumplan seis meses previos a la Fecha de Vencimiento, a un precio igual al 101%/ del valor 
nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en forma total o parcial""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9036%2FMPMAE%2DRES%2DON%20CRESUD%20%20Clase%20XLV%20Aviso%20de%20Resultados%20%2D18%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9036&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9036%2FMPMAE%2DANU%2DON%20ON%20CRESUD%20CLASE%20XLV%20Suplemento%20Prospecto%2016%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9036&p=true&ga=1"
}
CS47O = {
    "Nombre Security": "ON Cresud S.A.C.I.F y A. Clase XLVII Vto 15 11 2028",
    "Código": "CS47O",
    "ISIN": "AR0892513117",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "15/11/2024",
    "Vencimiento": "15/11/2028",
    "Fecha Primer Cupón": "15/05/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["15/05/2025", "15/11/2025", "15/05/2026", "15/11/2026",
    "15/05/2027", "15/11/2027", "15/05/2028", "15/11/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m36 de la emisión",
    "Fecha Call": "15/11/2027",
    "Precio Call": {"m36 en adelante": 1}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, 
podremos rescatar a nuestra opción las Obligaciones Negociables Clase XLVII, en o desde la fecha en que se cumplan doce meses 
previos a la Fecha de Vencimiento, a un precio igual al 100%/ del valor nominal, con más los intereses devengados e impagos y Montos 
Adicionales, si hubiera, en forma total o parcial, previa notificación con al menos 5 días de anticipación, conforme aviso a publicar en 
los términos requeridos por los reglamentos de listado y negociación de los mercados en los que se encuentren listadas las 
Obligaciones Negociables e informándose a la CNV a través de la AIF.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9385%2FMPMAE%2DRES%2DON%20CRESUD%20CLASE%2047%20Aviso%20de%20Resultados%2013%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9385&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9385%2FMPMAE%2DANU%2DON%20CRESUD%20CLASE%2047%2DSuplemento%20de%20Prospecto%2007%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9385&p=true&ga=1"
}
CIC8O = {
    "Nombre Security": "ON CNH Industrial Capital Arg SA Clase 8 Vto. 12 11 2028",
    "Código": "CIC8O",
    "ISIN": "AR0624205800",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Industrials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/11/2024",
    "Vencimiento": "12/11/2028",
    "Fecha Primer Cupón": "12/05/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "12/05/2025", "12/11/2025",
    "12/05/2026", "12/11/2026",
    "12/05/2027", "12/11/2027",
    "12/05/2028", "12/11/2028"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m24 de la emisión",
    "Fecha Call": "12/11/2026",
    "Precio Call": {"m24 en adelante: 1.01"}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la normativa aplicable en dicha 
oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables Clase 8 que se 
encuentren en circulación, en cualquier momento, en o desde la fecha en que se cumplan 24 (veinticuatro)
meses previos a la Fecha de Vencimiento de la Clase 8 a un precio de rescate del 101% del valor nominal de las 
Obligaciones Negociables Clase 8 junto con los intereses devengados y no pagados, en caso de 
corresponder, calculados hasta la fecha de rescate, y Montos Adicionales, si hubiera, previa notificación con 
al menos 15 días de anticipación, mediante la publicación de un aviso en los mercados en los que se 
encuentren listadas las Obligaciones Negociables Clase 8 e informándose a la CNV a través de la AIF.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9380%2FMPMAE%2DRES%2DON%20CNHI%20CLASE%207%2D8%2D%20Aviso%20de%20Resultados%2008%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9380&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9380%2FMPMAE%2DANU%2DON%20CNHI%20CLASE%207%2D8%2DSuplemento%20de%20Prospecto%2001%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9380&p=true&ga=1"
}
CIC9O = {
    "Nombre Security": "ON CNH Industrial Capital Arg SA Clase 9 Vto. 21 05 2027",
    "Código": "CIC9O",
    "ISIN": "AR0073116151",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Industrials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/05/2025",
    "Vencimiento": "21/05/2027",
    "Fecha Primer Cupón": "21/11/2025",
    "Cupón / Spread": 8.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["21/11/2025", "21/05/2026", "21/11/2026", "21/05/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 de la emisión",
    "Fecha Call": "21/11/2026",
    "Precio Call": {"m18 en adelante: 1.01"}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de
conformidad con la normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una
parte de las Obligaciones Negociables que se encuentren en circulación, en cualquier momento, en o
desde la fecha en que se cumplan 12 (doce) meses previos a la Fecha de Vencimiento a un precio de rescate
del 101% del valor nominal de las Obligaciones Negociables junto con los intereses devengados y no
pagados, en caso de corresponder, calculados hasta la fecha de rescate, y Montos Adicionales, si hubiera,
previa notificación con al menos 15 días de anticipación, mediante la publicación de un aviso en los
mercados en los que se encuentren listadas las Obligaciones Negociables e informándose a la CNV a través de la AIF. """,
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/a52b2af3-896f-4a90-bfdc-9d704838e933",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/d0deca6d-fc34-4816-a7e0-0f294943e369"
}
YFCIO = {
    "Nombre Security": "ON YPF LUZ Clase XVII Vto. 13 06 2027",
    "Código": "YFCIO",
    "ISIN": "AR0947502206",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/06/2024",
    "Vencimiento": "13/06/2027",
    "Fecha Primer Cupón": "13/03/2025",
    "Cupón / Spread": 5.90, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["13/03/2025",
    "13/06/2025",
    "13/09/2025",
    "13/12/2025",
    "13/03/2026",
    "13/06/2026",
    "13/09/2026",
    "13/12/2026",
    "13/03/2027",
    "13/06/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 8 + [50] * 2),
    "Quote Price Convention": "DIRTY",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 desde la emisión",
    "Fecha Call": "13/12/2026",
    "Precio Call": {"m30 en adelante: 1.00"}, # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la totalidad o una parte de las Obligaciones Negociables Clase XVII
    que se encuentren en circulación en cualquier momento, a partir del mes treinta (30°) inclusive contado desde la Fecha de Emisión y Liquidación, al precio de rescate de capital de 
    100% (más los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XVII)""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9120%2FMPMAE%2DRES%2D%20ON%20YPF%20ENERGIA%20ELECTRICA%20%20Clase%20XVI%20y%20XVII%20Aviso%20de%20Resultado%2011%2D06%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9120&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9120%2FMPMAE%2DANU%2DON%20YPF%20ENERGIA%20ELECTRICA%20Clase%20XVI%20y%20Clase%20XVII%20%20Suplemento%20de%20Prospecto%2007%2D06%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9120&p=true&ga=1"
}
PN37O = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 37 Vto 13 11 2028",
    "Código": "PN37O",
    "ISIN": "AR0098578880",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/11/2024",
    "Vencimiento": "13/11/2028",
    "Fecha Primer Cupón": "13/05/2025",
    "Cupón / Spread": 6.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["13/05/2025", "13/11/2025", "13/05/2026", "13/11/2026",
    "13/05/2027", "13/11/2027", "13/05/2028", "13/11/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "13/11/2024",
    "Precio Call": {"m1 a m16: 1.03, m17 a m32: 1.02, m32 en adelante: 1.01"}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables bajo los siguientes términos:
                  - Desde la emisión hasta el mes 16: 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 17 hasta el mes 32: 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 33 hasta la Fecha de Vencimiento: 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9387%2FMPMAE%2DRES%2DON%20EF%20PAN%20AMERICA%20ENERGY%20CLASE%2037%2D%20Aviso%20de%20Resultados%2011%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9387&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9387%2FMPMAE%2DANU%2D%20ON%20EF%2D%20PAN%20AMERICA%20ENERGY%20Clase%2037%20Suplemento%20Prospecto%2005%2D11%2D2024HR%29%5FE%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9387&p=true&ga=1"
}
PZCGO = {
    "Nombre Security": "ON Plaza Logistica S.R.L. Clase 15 Vto. 04 06 2028",
    "Código": "PZCGO",
    "ISIN": "AR0560145721",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/12/2024",
    "Vencimiento": "04/06/2028",
    "Fecha Primer Cupón": "04/06/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["04/06/2025", "04/09/2025", "04/12/2025",
    "04/03/2026", "04/06/2026", "04/09/2026", "04/12/2026",
    "04/03/2027", "04/06/2027", "04/09/2027", "04/12/2027",
    "04/03/2028", "04/06/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m36 desde la emisión",
    "Fecha Call": "04/12/2027",
    "Precio Call": {"m36 en adelante": 1.01},
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, Plaza Logística podrá rescatar a su opción, anticipadamente, en forma total o parcial, las Obligaciones 
Negociables, en cualquier momento a partir del sexto mes anterior a la Fecha de Vencimiento de las Obligaciones Negociables, al precio de rescate de capital de 
101%/ sobre el valor nominal, en caso de corresponder, deberá adicionarse los intereses devengados y no pagados calculados hasta la fecha de rescate. """,
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9420%2FMPMAE%2DRES%2DON%20PLAZA%20LOGISTICA%20CLASE%2015%20Aviso%20de%20resultado%2003%2D12%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9420&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9420%2FMPMAE%2DANU%2DON%20PLAZA%20LOGISTICA%20CLASE%2015%20Suplmento%20de%20Precio%2027%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9420&p=true&ga=1"
}
CIC7O = {
    "Nombre Security": "ON CNH Industrial Capital Arg SA Clase 7 Vto. 12 11 2026",
    "Código": "CIC7O",
    "ISIN": "AR0687434818",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Industrials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/11/2024",
    "Vencimiento": "12/11/2026",
    "Fecha Primer Cupón": "12/05/2025",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["12/05/2025",
                        "12/11/2025",
                        "12/05/2026", 
                        "12/11/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de los 12 meses previos a la emisión",
    "Fecha Call": "12/11/2025",
    "Precio Call": {"m12": 1.01},
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la normativa aplicable en dicha 
oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables Clase 7 que se 
encuentren en circulación, en cualquier momento, en o desde la fecha en que se cumplan 12 (doce) meses 
previos a la Fecha de Vencimiento de la Clase 7 a un precio de rescate del 101%/ del valor nominal de las 
Obligaciones Negociables Clase 7 junto con los intereses devengados y no pagados, en caso de 
corresponder, calculados hasta la fecha de rescate, y Montos Adicionales""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9379%2FMPMAE%2DRES%2DON%20CNHI%20CLASE%207%2D8%2D%20Aviso%20de%20Resultados%2008%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9379&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9379%2FMPMAE%2DANU%2DON%20CNHI%20CLASE%207%2D8%2DSuplemento%20de%20Prospecto%2001%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9379&p=true&ga=1"
}
DNC3O = {
    "Nombre Security": "ON EDENOR S.A. Clase 2 Vto. 22 11 2026",
    "Código": "DNC3O",
    "ISIN": "AR0140482933",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/03/2024",
    "Vencimiento": "22/11/2026",
    "Fecha Primer Cupón": "22/05/2024",
    "Cupón / Spread": 9.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["22/05/2024", 
                        "22/11/2024",
                        "22/05/2025",
                        "22/11/2025",
                        "22/05/2026", 
                        "22/11/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "07/03/2024",
    "Precio Call": {"m1 hasta 31/12/2024": 1.012188, "01/01/2025 en adelante": 1.00},
    "Comentarios": """En cualquier momento, con un preaviso no inferior a 10 días hábiles ni superior a 
20 días hábiles a los tenedores de Obligaciones Negociables Clase 3, Edenor podrá 
rescatar, en todo o en parte, de las clases de las Obligaciones Negociables Clase
3. Estos rescates se realizarán: a) un precio equivalente al 101,2188%/ del capital 
pendiente de pago en caso de que la Emisora decida realizar el rescate entre la 
Fecha de Emisión y Liquidación hasta 31 de diciembre de 2024; y b) al 100%/ del 
capital pendiente de pago, en caso de que la Emisora decida realizar el recate luego 
del plazo antes indicado y hasta la Fecha de Vencimiento de la respectiva clase de 
las Obligaciones Negociables; en todos los casos juntos con los intereses 
devengados y no pagados y los Montos Adicionales, si los hubiera, hasta la fecha 
de rescate exclusive. """,
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EfqTQuCQAAVGjP_nnyNAwtkBoFtjOA7wXY1AJT9AioKcHA",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8988%2FMPMAE%2DANU%2DON%20EDENOR%20CLASE%203%20%2D4%20%20Suplemento%2022%2D02%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8988&p=true&ga=1"
}
DNC5O = {
    "Nombre Security": "ON EDENOR S.A. Clase 5 Vto. 05 08 2028",
    "Código": "DNC5O",
    "ISIN": "AR0674196495",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/08/2024",
    "Vencimiento": "05/08/2028",
    "Fecha Primer Cupón": "05/02/2025",
    "Cupón / Spread": 9.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["05/02/2025", 
                        "05/08/2025",
                        "05/02/2026",
                        "05/08/2026",
                        "05/02/2027",
                        "05/08/2027",
                        "05/02/2028",
                        "05/08/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "05/08/2024",
    "Precio Call": {"m1 hasta 31/12/2025": 1.012188, "01/01/2026 en adelante": 1.00},
    "Comentarios": """En cualquier momento, con un preaviso no inferior a 10 días hábiles ni superior a 20 días hábiles a los tenedores de Obligaciones Negociables Clase 5, Edenor podrá rescatar, en todo o en parte, las 
                    Obligaciones Negociables Clase 5. Estos rescates se realizarán: a) un precio equivalente al 101,2188%/ del capital pendiente de pago en caso de que la Emisora decida realizar el rescate entre la Fecha de 
                    Emisión y Liquidación hasta 31 de diciembre de 2025; y b) al 100%/ del capital pendiente de pago, en caso de que la Emisora decida realizar el rescate luego del plazo antes indicado y hasta la Fecha de 
                    Vencimiento de la respectiva clase de las Obligaciones Negociables; en todos los casos juntos con los intereses devengados y no pagados y los Montos Adicionales, si los hubiera, hasta la fecha de rescate exclusive. """,
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9188%2FMPMAE%2DRES%2DON%20EDENOR%20Clase%205%20y%206%20%2D%20Aviso%20de%20Resultados%2001%2D08%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9188&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9188%2FMPMAE%2DANU%2DON%20EDENOR%20CLAS%205%20y%206%20Suplemento%20Prospecto%2026%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9188&p=true&ga=1"
}
MGCNO = {
    "Nombre Security": "ON Pampa Energia S.A. Clase XXII Vto 04 10 2028",
    "Código": "MGCNO",
    "ISIN": "AR0765746752",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/10/2024",
    "Vencimiento": "04/10/2028",
    "Fecha Primer Cupón": "04/04/2025",
    "Cupón / Spread": 5.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["04/04/2025", 
                        "04/10/2025",
                        "04/04/2026",
                        "04/10/2026",
                        "04/04/2027",
                        "04/10/2027",
                        "04/04/2028",
                        "04/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m36 de la emisión",
    "Fecha Call": "04/10/2027",
    "Precio Call": {"m36 en adelante": 1.00},
    "Comentarios": """La Emisora podrá rescatar a su sola opción, de forma total o parcial, las Obligaciones Negociables, en o desde la fecha en que se cumplan 12
                    meses previos a la Fecha de Vencimiento, previa notificación con al menos 10 días hábiles. En caso de rescate de las Obligaciones
                    Negociables, se rescatarán la totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación al valor nominal con más
                    los intereses devengados y cualquier monto adeudado e impago bajo las Obligaciones Negociables hasta la fecha del rescate. En el caso de un
                    rescate parcial, la selección de las Obligaciones Negociables para el rescate será realizada a prorrata entre los tenedores de las Obligaciones Negociables.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9308%2FMPMAE%2DRES%2D%20ON%20PAMPA%20ENERGIA%20CLASE%2022%20Aviso%20de%20Resultados%2002%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9308&p=true&ga=1",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/2fdbf11c-3183-4fc0-8a38-c7488f45c63d#"
}
OLC5O = {
    "Nombre Security": "ON Oleoductos del Valle S.A. Clase 5 Vto 12 06 2028",
    "Código": "OLC5O",
    "ISIN": "OLC5O",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/06/2025",
    "Vencimiento": "12/06/2028",
    "Fecha Primer Cupón": "12/12/2025",
    "Cupón / Spread": 7.89, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["12/12/2025", 
                        "12/06/2026",
                        "12/12/2026",
                        "12/06/2027",
                        "12/12/2027",
                        "12/06/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m33 de la emisión",
    "Fecha Call": "12/03/2028",
    "Precio Call": {"m33 en adelante": 1.00},
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no parcialmente las Obligaciones Negociables, con una 
anticipación no mayor a 90 (noventa) días de la Fecha de Vencimiento. En caso de rescate de las Obligaciones 
Negociables, se rescatarán por un importe equivalente al monto de capital no amortizado de las Obligaciones Negociables, más 
los intereses devengados e impagos sobre aquellos a la fecha de rescate en cuestión, más cualquier monto adeudado e impago bajo las Obligaciones Negociables""",
    "Aviso Resultados": "",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/486cf1ea-7d81-464f-b71c-417e62a0459d"
}
YMCYO = {
    "Nombre Security": "ON YPF S.A. Clase XXXII Vto 10 10 2028",
    "Código": "YMCYO",
    "ISIN": "AR0417757066",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2024",
    "Vencimiento": "10/10/2028",
    "Fecha Primer Cupón": "10/07/2025",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["10/07/2025", "10/10/2025", "10/01/2026", "10/04/2026",
 "10/07/2026", "10/10/2026", "10/01/2027", "10/04/2027",
 "10/07/2027", "10/10/2027", "10/01/2028", "10/04/2028",
 "10/07/2028", "10/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m36 de la emisión",
    "Fecha Call": "10/10/2027",
    "Precio Call": {"m36 a m41": 1.01, "m42 en adelante": 1.00},
    "Comentarios": """La Sociedad tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables Clase XXXIII a partir del mes 36 desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                - Desde el mes 36 hasta el mes 41: Precio de rescate de 101% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXXIII.
                - Desde el mes 42 hasta la Fecha de Vencimiento: Precio de rescate de 100% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXXIII.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DRES%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DANU%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DSuplemento%20de%20Prospecto%2021%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1"
}
YMCZO = {
    "Nombre Security": "ON YPF S.A. Clase XXXIII Vto 10 10 2028",
    "Código": "YMCZO",
    "ISIN": "AR0079616063",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2024",
    "Vencimiento": "10/10/2028",
    "Fecha Primer Cupón": "10/04/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["10/04/2025", "10/10/2025",
    "10/04/2026", "10/10/2026",
    "10/04/2027", "10/10/2027",
    "10/04/2028", "10/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m36 de la emisión",
    "Fecha Call": "10/10/2027",
    "Precio Call": {"m36 a m41": 1.01, "m42 en adelante": 1.00},
    "Comentarios": """La Sociedad tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables Clase XXXIII a partir del mes 36 desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                - Desde el mes 36 hasta el mes 41: Precio de rescate de 101% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXXIII.
                - Desde el mes 42 hasta la Fecha de Vencimiento: Precio de rescate de 100% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXXIII.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DRES%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DANU%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DSuplemento%20de%20Prospecto%2021%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1"
}
GYC5O = {
    "Nombre Security": "ON 360 Energy Solar Clase 5 Vto 05 09 2027",
    "Código": "GYC5O",
    "ISIN": "AR0253143579",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/03/2025",
    "Vencimiento": "05/09/2027",
    "Fecha Primer Cupón": "05/06/2025",
    "Cupón / Spread": 8.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["05/03/2026", "05/06/2026", "05/09/2026", "05/12/2026",
    "05/03/2027", "05/06/2027", "05/09/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m24 de la emisión",
    "Fecha Call": "09/03/2027",
    "Precio Call": {"m24 en adelante": 1}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no parcialmente las Obligaciones 
Negociables, con una anticipación no mayor a ciento ochenta (180) días a la Fecha de Vencimiento. En 
caso de rescate de las Obligaciones Negociables, se rescatarán por un importe equivalente al monto de 
capital no amortizado de las Obligaciones Negociables, más los intereses devengados e impagos sobre 
aquellos a la fecha del rescate en cuestión, más cualquier monto adeudado e impago bajo las Obligaciones 
Negociables.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DRES%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564%2FMPMAE%2DANU%2DON%20360%20ENERGY%20SOLAR%20CLASE%205%2DSuplemento%20de%20Prospecto%2021%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9564&p=true&ga=1"
}
LOC2O = {
    "Nombre Security": "ON Loma Negra C.I.A.S.A. Clase 2 Vto 21 12 2025 D",
    "Código": "LOC2O",
    "ISIN": "ARLOMA560041",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Materials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/06/2023",
    "Vencimiento": "21/12/2025",
    "Fecha Primer Cupón": "21/12/2023",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["21/12/2023", "21/06/2024", "21/12/2024", "21/06/2025", "21/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8650%2FMPMAE%2DRES%2DON%20LOMA%20NEGRA%20Clase%202%20%2D%20Aviso%20de%20Resultados%2015%2D06%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8650&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8650%2FMPMAE%2DANU%2DON%20LOMA%20NEGRA%20CLASE%202%2D%20Prospecto%2001%2E06%2E2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8650&p=true&ga=1"
}
LECEO = {
    "Nombre Security": "ON Albanesi Energia S.A. Clase XIII Vto. 14 08 2026",
    "Código": "LECEO",
    "ISIN": "AR0671196050",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/02/2024",
    "Vencimiento": "14/08/2026",
    "Fecha Primer Cupón": "14/08/2024",
    "Cupón / Spread": 9., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["14/08/2024", "14/02/2025", "14/08/2025",
    "14/02/2026", "14/08/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/06c588ef-7c4f-4706-957f-946ad3f04d44#",
    "Suplemento de Prospecto": ""
}
CRCLO = {
    "Nombre Security": "ON Celulosa Clase 20 Vto 08 02 2026",
    "Código": "CRCLO",
    "ISIN": "AR0697579701",
    "Calificación": "BBB-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/08/2024",
    "Vencimiento": "08/02/2026",
    "Fecha Primer Cupón": "08/11/2024",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["08/11/2024", "08/02/2025", "08/05/2025", "08/08/2025", "08/11/2025", "08/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9192%2FMPMAE%2DRES%2DON%20CELULOSA%20CLASE%2020%20Y%2021%20%2D%20Aviso%20Rdo%2006%2D08%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9192&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9192%2FMPMAE%2DANU%2DON%20CELULOSA%20CLASE%2020%20Y%2021%2DSuplemento%2031%2D07%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9192&p=true&ga=1"
}
CRCJO = {
    "Nombre Security": "ON Celulosa Clase 18 Vto 16 05 2028",
    "Código": "CRCJO",
    "ISIN": "AR0904133144",
    "Calificación": "BBB-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/05/2024",
    "Vencimiento": "16/05/2028",
    "Fecha Primer Cupón": "16/08/2024",
    "Cupón / Spread": 9.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["16/08/2024", "16/11/2024", "16/02/2025", "16/05/2025",
    "16/08/2025", "16/11/2025", "16/02/2026", "16/05/2026",
    "16/08/2026", "16/11/2026", "16/02/2027", "16/05/2027",
    "16/08/2027", "16/11/2027", "16/02/2028", "16/05/2028"], # Lista de fechas como ejemplo
    "Amortización": ([6.25] * 16),
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9069%2FMPMAE%2DANU%2DON%20CELULOSA%20CLASE%2018%20y%2019%2DAviso%20de%20Resultados%2014%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9069&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9069%2FMPMAE%2DANU%2DON%20CELULOSA%20CLASE%2018%20Y%2019%2DSuplemento%2008%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9069&p=true&ga=1"
}
HJCFO = {
    "Nombre Security": "ON John Deere Credit Compañia financiera Clase XIV 21 10 2026",
    "Código": "HJCFO",
    "ISIN": "AR0594233345",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/10/2024",
    "Vencimiento": "21/10/2026",
    "Fecha Primer Cupón": "21/04/2025",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["21/04/2025",
                        "21/10/2025",
                        "21/04/2026",
                        "21/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9337%2FMPMAE%2DRES%2DON%20JOHN%20DEERE%20CREDIT%20CF%20Clase%20XIV%20y%20XV%20%20%2D%20Aviso%20de%20Resultados%2016%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9337&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9337%2FMPMAE%2DANU%2DON%20JOHN%20DEERE%20CREDIT%20CF%20CLASES%2014%2D15%2DSuplemento%20de%20Prospecto%2009%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9337&p=true&ga=1"
}
HJCIO = {
    "Nombre Security": "ON John Deere Credit Compañia financiera Clase XVII 27 05 2027",
    "Código": "HJCIO",
    "ISIN": "AR0861451372",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/05/2025",
    "Vencimiento": "27/05/2027",
    "Fecha Primer Cupón": "27/11/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["27/11/2025",
                        "27/05/2026",
                        "27/11/2026",
                        "27/05/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/b923e10b-70e9-4b68-83c4-100002aae712",
    "Suplemento de Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/1867660e-2f1d-484b-8756-b18c47208ba0"
}
HJCHO = {
    "Nombre Security": "ON John Deere Clase XVI Vto 17 01 2028",
    "Código": "HJCHO",
    "ISIN": "AR0262204990",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2025",
    "Vencimiento": "17/01/2028",
    "Fecha Primer Cupón": "17/07/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["17/07/2025",
                        "17/01/2026",
                        "17/07/2026",
                        "17/01/2027",
                        "17/07/2027",
                        "17/01/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9494%2FMPMAE%2DRES%2DON%20JOHN%20DEERE%20CREDIT%20CF%20CLASE%2016%2DAviso%20de%20Resultados%2015%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9494&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9494%2FMPMAE%2DANU%2DON%20JOHN%20DEERE%20CREDIT%20CF%20CLASE%2016%2DSuplemento%20de%20Prospecto%2008%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9494&p=true&ga=1"
}
HJCGO = {
    "Nombre Security": "ON John Deere Credit Compañia financiera Clase XV 21 10 2028",
    "Código": "HJCGO",
    "ISIN": "AR0756895030",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Agriculture",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/10/2024",
    "Vencimiento": "21/10/2028",
    "Fecha Primer Cupón": "21/04/2025",
    "Cupón / Spread": 6.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["21/04/2025", 
                        "21/10/2025",
                        "21/04/2026",
                        "21/10/2026",
                        "21/04/2027",
                        "21/10/2027",
                        "21/04/2028", 
                        "21/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9338%2FMPMAE%2DRES%2DON%20JOHN%20DEERE%20CREDIT%20CF%20Clase%20XIV%20y%20XV%20%20%2D%20Aviso%20de%20Resultados%2016%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9338&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EaeiZsAjmUlHpWJ1Ih3qkPMBxyS28bErwRIbK90rAjQ3OA"
}
PQCRO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase R Vto 22 10 2028",
    "Código": "PQCRO",
    "ISIN": "AR0530125704",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/10/2024",
    "Vencimiento": "22/10/2028",
    "Fecha Primer Cupón": "22/04/2025",
    "Cupón / Spread": 6.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["22/04/2025", 
                        "22/10/2025",
                        "22/04/2026",
                        "22/10/2026",
                        "22/04/2027",
                        "22/10/2027",
                        "22/04/2028", 
                        "22/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EUc1528ZwQJHshuYWx3UWLYBDk3snIYkWIrZ8dpw0wDEiw",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9342%2FMPMAE%2DANU%2D%20ON%20PETROQUMICA%20COMODORO%20RIVADAVIA%20Clase%20R%20%2D%20Suplemento%20Prospecto%2015%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9342&p=true&ga=1"
}
PECGO = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Clase XV Vto 28 10 2028",
    "Código": "PECGO",
    "ISIN": "AR0922212433",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/10/2024",
    "Vencimiento": "28/10/2028",
    "Fecha Primer Cupón": "28/04/2025",
    "Cupón / Spread": 9., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["28/04/2025", "28/10/2025",
    "28/04/2026", "28/10/2026",
    "28/04/2027", "28/10/2027",
    "28/04/2028", "28/10/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9364%2FMPMAE%2DRES%2DON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%2015%20y%2016%2DAviso%20de%20Resultado%2024%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9364&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9364%2FMPMAE%2DANU%2DON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%2015%20y%2016%2DSuplemento%2017%2D10%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9364&p=true&ga=1"
}
BFCYO = {
    "Nombre Security": "ON Banco BBVA Argentina S.A. Clase 32 Vto. 27 02 2026",
    "Código": "BFCYO",
    "ISIN": "AR0693337336",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/02/2026",
    "Fecha Primer Cupón": "27/02/2026",
    "Cupón / Spread": 3.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DRES%2D%20ON%20BANCO%20BBVA%20ARGENTINA%20CLASE%2032%2D33%2D34%2DAviso%20resultado%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DANU%2DON%20BANCO%20BBVA%20%20Clases%2032%2033%20y%2034%20Suplemento%20de%20Prospecto%2018%2E02%2E25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1"""
}
YFCKO = {
    "Nombre Security": "ON YPF LUZ Clase XIX Vto. 22 11 2026",
    "Código": "YFCKO",
    "ISIN": "AR0015491712",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/11/2024",
    "Vencimiento": "22/11/2026",
    "Fecha Primer Cupón": "22/08/2025",
    "Cupón / Spread": 5.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["22/08/2025", "22/11/2025", "22/02/2026", 
    "22/05/2026", "22/08/2026", "22/11/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9396%2FMPMAE%2DRES%2DON%20EF%20YPF%20ENERGIA%20ELECTRICA%20Clase%20XIX%20y%20XX%2DAviso%20de%20Resultado%2020%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9396&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9396%2FMPMAE%2DANU%2DON%20EF%20YPF%20ENERGIA%20ELECTRICA%20Clase%20XIX%20y%20XX%20Suplemento%2012%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9396&p=true&ga=1"""
}
BVCMO = {
    "Nombre Security": "ON BST S.A. Clase XXI Vto. 05 08 2025",
    "Código": "BVCMO",
    "ISIN": "AR0695591054",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/02/2025",
    "Vencimiento": "05/08/2025",
    "Fecha Primer Cupón": "05/02/2025",
    "Cupón / Spread": 5.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["05/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9468%2FMPMAE%2DRES%2DON%20BANCO%20CMF%20CLASE%2016%2DAviso%20de%20Resultados%2018%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9468&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9468%2FMPMAE%2DANU%2DON%20BANCO%20CMF%20Clase%2016%20Suplemento%20de%20Prospecto%2013%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9468&p=true&ga=1"""
}
BCCIO = {
    "Nombre Security": "ON Banco CMF S.A. Clase 17 Vto 06 08 2025",
    "Código": "BCCIO",
    "ISIN": "AR0204738345",
    "Calificación": "A1(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/02/2025",
    "Vencimiento": "06/08/2025",
    "Fecha Primer Cupón": "06/02/2025",
    "Cupón / Spread": 4.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["06/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9526%2FMPMAE%2DRES%2D%20ON%20BANCO%20CMF%20CLASE%2017%2D18%2DAviso%20de%20Resultados%2004%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9526&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9526%2FMPMAE%2DANU%2D%20ON%20BANCO%20CMF%20%2D%20Clase%2017%20y%2018%20%2D%20Suplemento%20de%20Prospecto%2031%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9526&p=true&ga=1"""
}
BPCKO = {
    "Nombre Security": "ON Banco Supervielle S.A. Clase K Vto 07 08 2025",
    "Código": "BPCKO",
    "ISIN": "AR0469766486",
    "Calificación": "A1(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/02/2025",
    "Vencimiento": "07/08/2025",
    "Fecha Primer Cupón": "07/02/2025",
    "Cupón / Spread": 4.15, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9523%2FMPMAE%2DRES%2DON%20BANCO%20SUPERVIELLE%20CLASES%20K%20Y%20L%2DAviso%20de%20Resultado%2005%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9523&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9523%2FMPMAE%2DANU%2DON%20BANCO%20SUPERVIELLE%20CLASES%20K%20Y%20L%2DProspecto%2022%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9523&p=true&ga=1"""
}
YM35O = {
    "Nombre Security": "ON YPF S.A. Clase XXXV Vto 27 02 2027",
    "Código": "YM35O",
    "ISIN": "AR0929824099",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/02/2027",
    "Fecha Primer Cupón": "27/05/2025",
    "Cupón / Spread": 6.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/05/2025", "27/08/2025", "27/11/2025", "27/02/2026",
    "27/05/2026", "27/08/2026", "27/11/2026", "27/02/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/24530c59-03a1-458d-8f07-6411a502344f""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/a477b504-e5b8-40a1-9bba-195b2d6e0ae1"""
}
ZZC1O = {
    "Nombre Security": "ON Camuzzi Gas Pampeana Clase I Vto 21 02 2027",
    "Código": "ZZC1O",
    "ISIN": "AR0352269929",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/02/2025",
    "Vencimiento": "21/02/2027",
    "Fecha Primer Cupón": "21/08/2025",
    "Cupón / Spread": 7.95, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["21/08/2025", "21/02/2026", "21/08/2026", "21/02/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9541%2FMPMAE%2DRES%2DON%20CAMUZZI%20GAS%20PAMPEANO%20Aviso%20resultados%2018%2E02%2E25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9541&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9541%2FMPMAE%2DANU%2DON%20CAMUZZI%20GAS%20PAMPEANA%20Clase%201%20%20Suplemento%20Prospecto%2012%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9541&p=true&ga=1"""
}
BYCOO = {
    "Nombre Security": "ON Banco Galicia Clase XXIII Vto 28 11 2025",
    "Código": "BYCOO",
    "ISIN": "AR0816136284",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/03/2025",
    "Vencimiento": "28/11/2025",
    "Fecha Primer Cupón": "28/11/2025",
    "Cupón / Spread": 4.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None, # Precio Call
    "Comentarios": None,
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9576%2FMPA3%2DRES%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XXIII%2D%20Aviso%20de%20Resultados%2007%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9576&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9576%2FMPMAE%2DANU%2D%20ON%20EF%2D%20BANCO%20DE%20GALICIA%20CLASE%20XXIII%20%2D%20Suplemento%2026%2D02%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9576&p=true&ga=1"""
}
YM36O = {
    "Nombre Security": "ON YPF S.A. Clase XXXVI Vto 27 08 2025",
    "Código": "YM36O",
    "ISIN": "AR0816136284",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/08/2025",
    "Fecha Primer Cupón": "27/08/2025",
    "Cupón / Spread": 3.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 de la emisión",
    "Fecha Call": "27/08/2026",
    "Precio Call": {"m18 en adelante": 1}, # Precio Call
    "Comentarios": """YPF S.A. tendrá derecho a rescatar anticipadamente, a su sola opción, la totalidad
o una parte de las Obligaciones Negociables Clase XXXV que se encuentren en circulación en cualquier momento, a partir del décimo octavo (18°) mes
(inclusive) contado desde la Fecha de Emisión y Liquidación, a un precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la
fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXXV) de 100%.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/24530c59-03a1-458d-8f07-6411a502344f""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/a477b504-e5b8-40a1-9bba-195b2d6e0ae1"""
}
YM37O = {
    "Nombre Security": "ON YPF S.A. Clase XXXVII Vto 07 05 2027",
    "Código": "YM37O",
    "ISIN": "YM37O",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/05/2025",
    "Vencimiento": "07/05/2027",
    "Fecha Primer Cupón": "07/08/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/08/2025",
                        "07/11/2025",
                        "07/02/2026",
                        "07/05/2026",
                        "07/08/2026",
                        "07/11/2026",
                        "07/02/2027",
                        "07/05/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 de la emisión",
    "Fecha Call": "07/11/2026",
    "Precio Call": {"m18 en adelante": 1}, # Precio Call
    "Comentarios": """YPF S.A. tendrá derecho a rescatar anticipadamente, a su sola opción, la totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación en 
cualquier momento, a partir del décimo octavo (18°) mes (inclusive) contado desde la Fecha de Emisión y Liquidación, a un precio de rescate de capital (más 
los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables) de 100%""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/ab036f36-d81c-4445-8791-82b2aa285f32""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/e2a5679f-b3ec-4c6f-bcab-078b9116995e"""
}
YMCQO = {
    "Nombre Security": "ON YPF S.A. Clase XXV Vto 13 02 2026",
    "Código": "YMCQO",
    "ISIN": "ARYPFS5601W0",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "13/02/2026",
    "Fecha Primer Cupón": "13/12/2023",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["13/12/2023", "13/06/2024", "13/12/2024",
    "13/06/2025", "13/12/2025", "13/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m24 de la emisión",
    "Fecha Call": "13/06/2025",
    "Precio Call": {"m24 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la 
totalidad o una parte de las Obligaciones Negociables Clase XXV que se 
encuentren en circulación en cualquier momento, a partir del mes 24 (inclusive) 
contado desde la Fecha de Emisión y Liquidación, al precio de rescate de 
capital (más los intereses devengados y no pagados calculados hasta la fecha 
de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
Obligaciones Negociables de las Obligaciones Negociables Clase XXV) de 
101%""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8635%2FMPMAE%2DRES%2DON%20YPF%20CLASE%2025%20%2D%20Aviso%20de%20Resultados%2008%2D06%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8635&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8635%2FMPMAE%2DANU%2D%20ON%20EF%20YPF%20CLASE%2025%20%20%2D%20Suplemento%20de%20Precio%2006%2D06%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8635&p=true&ga=1"""
}
YMCVO = {
    "Nombre Security": "ON YPF S.A. Clase XXIX Vto 28 05 2026",
    "Código": "YMCVO",
    "ISIN": "AR0202080054",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/05/2024",
    "Vencimiento": "28/05/2026",
    "Fecha Primer Cupón": "28/11/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/11/2024", "28/2/2025", "28/5/2025", "28/8/2025",
    "28/11/2025", "28/2/2026", "28/5/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 de la emisión",
    "Fecha Call": "28/11/2025",
    "Precio Call": {"m18 en adelante": 1}, # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la 
totalidad o una parte de las Obligaciones Negociables Clase XXIX que se 
encuentren en circulación en cualquier momento, a partir del mes 18 (inclusive) 
contado desde la Fecha de Emisión y Liquidación, al precio de rescate de capital 
(más los intereses devengados y no pagados calculados hasta la fecha de rescate, 
los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones 
Negociables de las Obligaciones Negociables Clase XXIX) de 100%/""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9093%2FMPMAE%2DRES%2DON%20EF%20YPF%20S%2EA%2E%20CLASE%20XXIX%20%2D%20Aviso%20de%20Resultados%2023%2D05%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9093&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9093%2FMPMAE%2DANU%2DON%20EF%20YPF%20S%2EA%2E%20Clase%20XXIX%20%2D%20Suplemento%2020%2D05%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9093&p=true&ga=1"""
}
AERBO = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase XI Vto. 15 12 2026",
    "Código": "AERBO",
    "ISIN": "AR0162186347",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/12/2024",
    "Vencimiento": "15/12/2026",
    "Fecha Primer Cupón": "23/06/2025",
    "Cupón / Spread": 5.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/06/2025", "23/12/2025", "23/06/2026", "15/12/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m21 de la emisión",
    "Fecha Call": "15/09/2026",
    "Precio Call": {"m21 en adelante": 1}, # Precio Call
    "Comentarios": """En cualquier momento, a partir del nonagésimo (90°) día anterior a la Fecha de 
Vencimiento, la Compañía tendrá el derecho, a su sola opción, de rescatar las Obligaciones Negociables en su totalidad (pero no en parte), sin prima de rescate, 
debiendo abonar el capital más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
Obligaciones Negociables. """,
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9463%2FMPMAE%2DRES%2DON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%2011%20%5FAviso%20de%20Resultados%2019%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9463&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9463%2FMPMAE%2DANU%2DON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%2011%20Suplemento%20de%20prospecto%2013%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9463&p=true&ga=1"""
}
EAC3O = {
    "Nombre Security": "ON MSU Green Energy S.A. Serie III Vto. 23 12 2028",
    "Código": "EAC3O",
    "ISIN": "AR0333366083",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/12/2024",
    "Vencimiento": "23/12/2028",
    "Fecha Primer Cupón": "20/06/2025",
    "Cupón / Spread": 8.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["20/06/2025", "20/12/2025",
    "20/06/2026", "20/12/2026",
    "20/06/2027", "20/12/2027",
    "20/06/2028", "20/12/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m12 de la emisión",
    "Fecha Call": "20/12/2025",
    "Precio Call": {"m12 a m24": 1.03, "m25 a m36": 1.02, "m37 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables a partir del mes doce (12) desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde el mes 12 hasta el mes 24: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 25 hasta el mes 36: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 37 hasta la Fecha de Vencimiento: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/72c60a88-b1b3-4b41-8749-5893ce21263d#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/e944279d-dd10-47f8-931d-5387a1d03a32#"""
}
VSCPO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXIV Vto 03 05 2029",
    "Código": "VSCPO",
    "ISIN": "AR0637277028",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/05/2024",
    "Vencimiento": "03/05/2029",
    "Fecha Primer Cupón": "03/11/2024",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "03/11/2024", "03/05/2025", "03/11/2025", "03/05/2026",
    "03/11/2026", "03/05/2027", "03/11/2027", "03/05/2028",
    "03/11/2028", "03/05/2029"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 6 + [25] * 4),
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "03/05/2024",
    "Precio Call": {"desde la emisión en adelante: 1."}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la 
normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación, en 
cualquier momento desde la Fecha de Emisión y Liquidación, al valor nominal con más los intereses devengados hasta la fecha de pago del valor de rescate (el “Valor 
del Rescate”).""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9054%2FMPMAE%2DRES%2DON%20VISTA%20ENERGY%20CLASE%2023Adic%20y%2024%20Aviso%20de%20Resultados%2030%2D04%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9054&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9054%2FMPMAE%2DANU%2D%20ON%20VISTA%20ENERGY%20ARG%20CLASE%2023%20ADIC%20Y%2024%20Suplemento%2024%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9054&p=true&ga=1"""
}
PN36O = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 36 Vto 13 11 2031",
    "Código": "PN36O",
    "ISIN": "AR0677571967",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/11/2024",
    "Vencimiento": "13/11/2031",
    "Fecha Primer Cupón": "13/05/2025",
    "Cupón / Spread": 7.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["13/05/2025", "13/11/2025", "13/05/2026", "13/11/2026",
    "13/05/2027", "13/11/2027", "13/05/2028", "13/11/2028",
    "13/05/2029", "13/11/2029", "13/05/2030", "13/11/2030",
    "13/05/2031", "13/11/2031"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m24",
    "Fecha Call": "13/05/2028",
    "Precio Call": {"m42 a m60: 1.02, m61 en adelante: 1.01"}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables a partir del cuadragésimo segundo mes desde la Fecha de Emisión y Liquidación bajo los siguientes términos:

                  - Desde el mes 42 hasta el mes 60: Precio de rescate de 102% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  
                  - Desde el mes 61 hasta la Fecha de Vencimiento: Precio de rescate de 101% del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9386%2FMPMAE%2DRES%2DON%20EF%20PAN%20AMERICA%20ENERGY%20CLASE%2036%2D%20Aviso%20de%20Resultados%2011%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9386&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9386%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2036%20Suplemento%20Prospecto%2005%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9386&p=true&ga=1"""
}
SIC1O = {
    "Nombre Security": "ON Sidersa Clase 1 Vto. 09 12 2026",
    "Código": "SIC1O",
    "ISIN": "AR0869460326",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Industrials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/12/2024",
    "Vencimiento": "09/12/2026",
    "Fecha Primer Cupón": "09/03/2025",
    "Cupón / Spread": 6.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/03/2025", "09/06/2025", "09/09/2025", "09/12/2025",
    "09/03/2026", "09/06/2026", "09/09/2026", "09/12/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9429%2FMPMAE%2DRES%2DON%20SIDERSA%20CLASE%201%20Aviso%20de%20resultados%2005%2D12%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9429&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9429%2FMPMAE%2DANU%2DON%20SIDERSA%20CLASE%201%20Suplemento%20Prospecto%20%2029%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9429&p=true&ga=1"""
}
PQCSO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A Clase S Vto 17 02 2031",
    "Código": "PQCSO",
    "ISIN": "AR0309447628",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/02/2025",
    "Vencimiento": "17/02/2031",
    "Fecha Primer Cupón": "17/06/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/08/2025", "17/02/2026", "17/08/2026", "17/02/2027",
    "17/08/2027", "17/02/2028", "17/08/2028", "17/02/2029",
    "17/08/2029", "17/02/2030", "17/08/2030", "17/02/2031"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9539%2FMPMAE%2DANU%2DON%20PETROQUMICA%20COMODORO%20RIVADAVIA%20CLASE%20S%2DSuplemento%2006%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9539&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9539%2FMPMAE%2DRES%2DON%20PETROQUIMICA%20COMODORO%20RIVADAVIA%20CLASE%20S%20%2D%20Aviso%20de%20Resultados%2012%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9539&p=true&ga=1"""
}
TLCOO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 23 Vto 28 11 2028",
    "Código": "TLCOO",
    "ISIN": "AR0241562484",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Communications",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/11/2024",
    "Vencimiento": "28/11/2028",
    "Fecha Primer Cupón": "28/05/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/05/2025", "28/11/2025",
    "28/05/2026", "28/11/2026",
    "28/05/2027", "28/11/2027",
    "28/05/2028", "28/11/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9406%2FMPMAE%2DRES%2DON%20TELECOM%20ARGENTINA%20Clase%2023%20%2D%20Aviso%20de%20Resultado%2026%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9406&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9406%2FMPMAE%2DANU%2DON%20TELECOM%20ARGENTINA%20CLASE%2023%20%2D%20Prospecto%20del%20Programa%2029%2D04%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9406&p=true&ga=1"""
}
CACBO = {
    "Nombre Security": "ON Capex S.A. Clase XI Vto. 17 06 2028",
    "Código": "CACBO",
    "ISIN": "CACBO",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Utilities",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/06/2025",
    "Vencimiento": "17/06/2028",
    "Fecha Primer Cupón": "17/09/2025",
    "Cupón / Spread": 7.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/09/2025", "17/12/2025", "17/03/2026", "17/06/2026",
    "17/09/2026", "17/12/2026", "17/03/2027", "17/06/2027",
    "17/09/2027", "17/12/2027", "17/03/2028", "17/06/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 la fecha de emisión",
    "Fecha Call": "17/12/2027",
    "Precio Call": {"m30 en adelante": 1.}, # Precio Call
    "Comentarios": """La Emisora tendrá derecho a rescatar anticipadamente, a su sola opción, la
totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación en cualquier momento, a partir del treintavo (30°) mes (inclusive)
contado desde la Fecha de Emisión y Liquidación, a un precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate,
los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables) de 100%.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D06%2F7566%2FMPA3%2DRES%2DON%20CAPEX%20CLASE%20XI%2DAviso%20de%20Resultado%2012%2D06%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D06%2F7566&p=true&ga=1""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/960a0e50-5a3d-4ab3-80db-5a79a8f42960""",
}
OT42O = {
    "Nombre Security": "ON Oiltanking Ebytem Clase 1 S2 Vto. 17 01 2030",
    "Código": "OT42O",
    "ISIN": "AR0061093123",
    "Calificación": "AA.ar",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/01/2025",
    "Vencimiento": "17/01/2030",
    "Fecha Primer Cupón": "17/10/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/10/2025", "17/01/2026", "17/04/2026", "17/07/2026",
    "17/10/2026", "17/01/2027", "17/04/2027", "17/07/2027",
    "17/10/2027", "17/01/2028", "17/04/2028", "17/07/2028",
    "17/10/2028", "17/01/2029", "17/04/2029", "17/07/2029",
    "17/10/2029", "17/01/2030"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 la fecha de emisión",
    "Fecha Call": "17/07/2027",
    "Precio Call": {"m30 a m33": 1.01, "m34 en adelante": 1.}, # Precio Call
    "Comentarios": """La Compañía tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables Serie IV Clase 1 a partir del mes treinta (30) desde la Fecha de Emisión y Liquidación bajo los siguientes términos:

                  - Desde el mes 30 hasta el mes 33: 101%/
                  - Desde el mes 34 hasta la Fecha de Vencimiento: 100%/ del capital""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9492%2FMPMAE%2DRES%2DON%20OILTANKING%20SERIE%204%2DAviso%20de%20Resultados%2016%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9492&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9492%2FMPMAE%2DANU%2DON%20OILTANKING%20SERIE%204%2DSuplemento%2010%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9492&p=true&ga=1"""
}
MGCLO = {
    "Nombre Security": "ON Pampa Energia S.A. Clase XX Vto 26 03 2026",
    "Código": "MGCLO",
    "ISIN": "AR0755405583",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "26/03/2024",
    "Vencimiento": "26/03/2026",
    "Fecha Primer Cupón": "26/09/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["26/9/2024", "26/3/2025", "26/9/2025", "26/3/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad desde el mes 20 desde la emisión",
    "Fecha Call": "26/05/2026",
    "Precio Call": {"m20 en adelante": 1.00}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar, a su sola opción, en forma total o parcial, las Obligaciones Negociables a partir del mes 20 desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Precio de rescate de 100%/ del capital, más intereses devengados e impagos y cualquier otro monto adeudado bajo las Obligaciones Negociables.
                  - En caso de rescate parcial, la selección se realizará a prorrata entre los tenedores de las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9018%2FMPMAE%2DRES%2D%20ON%20PAMPA%20ENERGIA%20CLASE%2020%20Aviso%20de%20Resultados%2022%2D03%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9018&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9018%2FMPMAE%2DANU%2DON%20PAMPA%20ENERGIA%20CLASE%2020%2D%20Suplemento%20Prospecto%2018%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9018&p=true&ga=1"""
}
TTC7O = {
    "Nombre Security": "ON Tecpetrol S.A. Clase 7 Vto 22 04 2026",
    "Código": "TTC7O",
    "ISIN": "AR0885645611",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/04/2024",
    "Vencimiento": "22/04/2026",
    "Fecha Primer Cupón": "22/10/2024",
    "Cupón / Spread": 5.98, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["22/10/2024", "22/4/2025", "22/10/2025", "22/4/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de los seis meses previos a la Fecha de Vencimiento",
    "Fecha Call": "22/10/2025",
    "Precio Call": {"m18 en adelante": 1.00}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, de forma total o parcial, las Obligaciones Negociables, en o desde la fecha en que 
se cumplan 6 meses previos a la Fecha de Vencimiento. En caso de rescate de las Obligaciones Negociables, se rescatarán la 
totalidad o una parte de las Obligaciones Negociables que se encuentren en circulación al valor nominal con más los intereses 
devengados y cualquier monto adeudado e impago bajo las Obligaciones Negociables hasta la fecha del rescate. En el caso de 
un rescate parcial, la selección de las Obligaciones Negociables para el rescate será realizada a prorrata entre los tenedores de las 
Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035%2FMPMAE%2DRES%2DON%20TECPETROL%20CLASE%207%20%2D%20Aviso%20de%20Resultados%2018%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035%2FMPMAE%2DANU%2DON%20TECPETROL%20Clase%207%2DSuplemento%20de%20Prospecto%2012%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035&p=true&ga=1"""
}
RCCRO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XXVI Vto 09 05 2027",
    "Código": "RCCRO",
    "ISIN": "RCCRO",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Staples",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/05/2025",
    "Vencimiento": "09/05/2027",
    "Fecha Primer Cupón": "09/11/2025",
    "Cupón / Spread": 6.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/11/2025", 
                        "09/05/2026", 
                        "09/11/2026", 
                        "09/05/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de los tres meses previos a la Fecha de Vencimiento",
    "Fecha Call": "09/02/2027",
    "Precio Call": {"m21 en adelante": 1.00}, # Precio Call
    "Comentarios": """En la medida en que las normas vigentes lo permitan, la Emisora podrá rescatar a su sola opción, en su totalidad o parcialmente, las 
Obligaciones Negociables Clase 26, en o desde la fecha en que se cumplan tres meses previos a la Fecha de Vencimiento de la Clase 26, previa notificación con al menos 10 Días Hábiles. En caso de 
rescate de las Obligaciones Negociables Clase 26, se rescatarán la totalidad o una parte de las Obligaciones Negociables que se 
encuentren en circulación al valor nominal con más los intereses devengados y cualquier monto impago bajo las Obligaciones 
Negociables Clase 26 hasta la fecha de rescate.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/8741f15c-c91d-4058-aa2d-19dd92f8b496""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/23e4bb92-87ac-45a8-969a-e27285a085e7"""
}
TTC8O = {
    "Nombre Security": "ON Tecpetrol S.A. Clase 8 Vto 24 10 2027",
    "Código": "TTC8O",
    "ISIN": "AR0166027471",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "24/10/2024",
    "Vencimiento": "24/10/2027",
    "Fecha Primer Cupón": "24/04/2025",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["24/04/2025", "24/10/2025",
    "24/04/2026", "24/10/2026",
    "24/04/2027", "24/10/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "24/10/2024",
    "Precio Call": {"m1 a m12": 1.03, "m13 a m24": 1.02, "m25 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora podrá rescatar total o parcialmente las Obligaciones Negociables Clase 8 bajo los siguientes términos:
                  - Desde la emisión hasta el mes 12: 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 13 hasta el mes 24: 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 25 hasta la Fecha de Vencimiento: 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9347%2FMPMAE%2DRES%2D%20ON%20TECPETROL%20Clase%208%20y%209%20%2D%20Aviso%20de%20Resultados%2022%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9347&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9347%2FMPMAE%2DANU%2DON%20TECPETROL%20Clase%208%20y%20Clase%209%20%2D%20Suplemento%20de%20Prospecto%20%2016%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9347&p=true&ga=1"""
}
PN34O = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 34 Vto 27 09 2027",
    "Código": "PN34O",
    "ISIN": "AR0770773957",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/09/2024",
    "Vencimiento": "27/09/2027",
    "Fecha Primer Cupón": "27/03/2025",
    "Cupón / Spread": 4.97, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "27/03/2025",
    "27/09/2025",
    "27/03/2026",
    "27/09/2026",
    "27/03/2027",
    "27/09/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la emisión",
    "Fecha Call": "27/09/2024",
    "Precio Call": {"m1 a m12": 1.03, "m13 a m24": 1.02, "m25 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables bajo los siguientes términos:
                  - Desde la emisión hasta el mes 12: 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 13 hasta el mes 24: 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 25 hasta la Fecha de Vencimiento: 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EXIcXSfOvgBAokbT0EmjYLMBH4lZqnwKIPC_iirL6FY4_w""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9289%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2034%2DSuplemento%20de%20Prospecto%2020%2D09%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9289&p=true&ga=1"""
}
NBS1O = {
    "Nombre Security": "ON Balanz Capital Serie I Vto. 06 06 2026",
    "Código": "NBS1O",
    "ISIN": "AR0340052312",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Financials",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/06/2024",
    "Vencimiento": "06/06/2026",
    "Fecha Primer Cupón": "06/10/2024",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 3., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "06/10/2024",
    "06/02/2025",
    "06/06/2025",
    "06/10/2025",
    "06/02/2026",
    "06/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "06/06/2024",
    "Precio Call": {"m1 en adelante": 1.0}, # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con la normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte
    de las Obligaciones Negociables Serie I que se encuentren en circulación, en cualquier momento desde la Fecha de Emisión y Liquidación, al 
    valor nominal con más los intereses devengados hasta la fecha de pago del valor de rescate inclusive (el "Valor del Rescate)""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9111%2FMPMAE%2DRES%2D%20ON%20BALANZ%20%20Serie%20I%20%2D%20Aviso%20de%20Resultados%20v04%2D06%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9111&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9111%2FMPMAE%2DANU%2DON%20BALANZ%20SERIE%201%2DSuplemento%20de%20Prospecto%2027%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9111&p=true&ga=1"""
}
IRCLO = {
    "Nombre Security": "ON IRSA S.A. Clase XX Vto 05 06 2026",
    "Código": "IRCLO",
    "ISIN": "AR0200915251",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/06/2024",
    "Vencimiento": "10/06/2026",
    "Fecha Primer Cupón": "10/12/2024",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "10/12/2024",
    "10/6/2025",
    "10/12/2025",
    "10/6/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de los 6 meses previos al vencimiento",
    "Fecha Call": "10/12/2025",
    "Precio Call": {"m18 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, podremos rescatar a nuestra opción las Obligaciones 
Negociables Clase XX, en o desde la fecha en que se cumplan seis (6) meses previos a la Fecha de Vencimiento, a un precio 
igual al 101%/ del valor nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en 
forma total o parcial""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9113%2FMPMAE%2DANU%2DON%20IRSA%20CLASE%20XX%20Y%20XXI%20Aviso%20de%20Suscripcion%2030%2D05%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9113&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9113%2FMPMAE%2DANU%2DON%20IRSA%20CLASE%20XX%20y%20XXI%20%2D%20Suplemento%20de%20prospecto%2030%2D05%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9113&p=true&ga=1"""
}
IRCJO = {
    "Nombre Security": "ON IRSA S.A. Clase XVIII Vto 28 02 2027",
    "Código": "IRCJO",
    "ISIN": "AR0961375257",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2024",
    "Vencimiento": "28/02/2027",
    "Fecha Primer Cupón": "28/08/2024",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
        "28/08/2024", "28/02/2025", "28/08/2025", 
        "28/02/2026", "28/08/2026", "28/02/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 desde la emisión",
    "Fecha Call": "28/08/2026",
    "Precio Call": {"m30 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, 
                    podremos rescatar a nuestra opción las Obligaciones Negociables Clase XVIII, en o desde la fecha en que se cumplan seis (6) meses previos a la Fecha de Vencimiento, 
                    a un precio igual al 101%/ del valor nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en forma total o parcial, previa notificación con al menos 5 días de anticipación""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8972%2FMPMAE%2DRES%2DON%20CLASE%20XVIII%20Y%20XIX%20%20Aviso%20de%20Resultados%2026%2D02%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8972&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8972%2FMPMAE%2DANU%2DON%20IRSA%20Clase%20XVIII%20y%20XIX%20%2D%20Suplemento20%2D02%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8972&p=true&ga=1"""
}
IRCNO = {
    "Nombre Security": "ON IRSA S.A. Clase XXII Vto 24 10 2027",
    "Código": "IRCNO",
    "ISIN": "IRCNO",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/10/2024",
    "Vencimiento": "23/10/2027",
    "Fecha Primer Cupón": "23/07/2025",
    "Cupón / Spread": 5.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/07/2025", "23/01/2026",
    "23/07/2026", "23/01/2027",
    "23/07/2027", "23/10/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 desde la emisión",
    "Fecha Call": "23/04/2027",
    "Precio Call": {"m30 en adelante": 1.01}, # Precio Call
    "Comentarios": """En la medida que la normativa aplicable y vigente lo permita, 
podremos rescatar a nuestra opción las Obligaciones Negociables Clase XXII, en o desde la fecha en que se cumplan 
seis (6) meses previos a la Fecha de Vencimiento, a un precio igual al 101%/ del valor nominal, con más los intereses devengados e impagos y Montos Adicionales, si hubiera, en forma total o parcial.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9345%2FMPMAE%2DRES%2DON%20IRSA%20Clase%20XXII%20y%20XXIII%2D%20Aviso%20de%20Resultados%2021%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9345&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9345%2FIRSA%20%2D%20Suplemento%20de%20Prospecto%20Resumido%20ON%20Clase%20XXII%20y%20XXIII%20%2D%20Firmado%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9345&p=true&ga=1"""
}
MSSFO = {
    "Nombre Security": "ON MSU S.A. Clase XIV Vto 23 07 2027",
    "Código": "MSSFO",
    "ISIN": "AR0820572623",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/07/2024",
    "Vencimiento": "23/07/2027",
    "Fecha Primer Cupón": "23/01/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/01/2025", "23/07/2025",
    "23/01/2026", "23/07/2026",
    "23/01/2027", "23/07/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "23/07/2024",
    "Precio Call": {"m0 en adelante": 1.01}, # Precio Call
    "Comentarios": """En cualquier momento, de acuerdo con las normas vigentes en ese momento y en la medida permitida por dichas normas, la Emisora podrá, a su sola opción, rescatar las Obligaciones Negociables Serie XIV, 
    en su totalidad, pero no parcialmente, a un precio equivalente al 101% del capital pendiente de pago, junto con montos adicionales e intereses devengados y no pagados, excluyendo la fecha de rescate. """,
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9179%2FMPMAE%2DRES%2DON%20MSU%20SERIE%2014%2DAviso%20de%20Resultados%2019%2D07%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9179&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9179%2FMPMAE%2DANU%2DON%20MSU%20SERIE%2014%2D%20Suplemento%2015%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9179&p=true&ga=1"""
}
PLC1O = {
    "Nombre Security": "ON Pluspetrol S.A. Clase I Vto 27 01 2028",
    "Código": "PLC1O",
    "ISIN": "AR0502588418",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/01/2025",
    "Vencimiento": "27/01/2028",
    "Fecha Primer Cupón": "27/10/2025",
    "Cupón / Spread": 6., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/10/2025", 
                        "27/04/2026", 
                        "27/10/2026",
                        "27/04/2027",
                        "27/10/2027", 
                        "27/01/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "27/01/2025",
    "Precio Call": {"m0 a m12": 1.03, "m13 a m24": 1.02, "m25 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables a partir del décimo segundo mes desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde la emisión hasta el mes 12: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 13 hasta el mes 24: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 25 hasta la Fecha de Vencimiento: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504%2FMPMAE%2DRES%2DON%20PLUSPETROL%20%20Clase%201%20y%202%20%20%2D%20Aviso%20de%20Resultados%2023%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504%2FMPMAE%2DANU%2DON%20PLUSPETROL%20CLASE%201%20y%202%2D%20Suplemento%20de%20Prospecto%2017%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504&p=true&ga=1"""
}
PLC2O = {
    "Nombre Security": "ON Pluspetrol S.A. Clase II Vto 27 01 2030",
    "Código": "PLC2O",
    "ISIN": "AR0036431960",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/01/2025",
    "Vencimiento": "27/01/2030",
    "Fecha Primer Cupón": "27/10/2025",
    "Cupón / Spread": 7.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/10/2025", 
                        "27/04/2026", 
                        "27/10/2026",
                        "27/04/2027",
                        "27/10/2027", 
                        "27/04/2028", 
                        "27/10/2028",
                        "27/04/2029", 
                        "27/10/2029", 
                        "27/01/2030"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "27/01/2025",
    "Precio Call": {"m0 a m20": 1.03, "m21 a m40": 1.02, "m41 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables a partir del décimo segundo mes desde la Fecha de Emisión y Liquidación bajo los siguientes términos:

                  - Desde la emisión hasta el mes 20: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  
                  - Desde el mes 21 hasta el mes 40: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.

                  - Desde el mes 41 hasta la Fecha de Vencimiento: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504%2FMPMAE%2DRES%2DON%20PLUSPETROL%20%20Clase%201%20y%202%20%20%2D%20Aviso%20de%20Resultados%2023%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504%2FMPMAE%2DANU%2DON%20PLUSPETROL%20CLASE%201%20y%202%2D%20Suplemento%20de%20Prospecto%2017%2D01%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9504&p=true&ga=1"""
}
PLC3O = {
    "Nombre Security": "ON Pluspetrol S.A. Clase III Vto 30 04 2038",
    "Código": "PLC3O",
    "ISIN": "AR0808016403",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2025",
    "Vencimiento": "30/04/2028",
    "Fecha Primer Cupón": "30/01/2026",
    "Cupón / Spread": 7.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/01/2026", "30/07/2026", "30/01/2027", 
    "30/07/2027", "30/01/2028", "30/04/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True,
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "27/01/2025",
    "Precio Call": {"m0 a m12": 1.03, "m13 a m24": 1.02, "m25 en adelante": 1.01},
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de rescatar las Obligaciones Negociables en su totalidad (pero no en parte), al precio de rescate de capital (más los intereses devengados
y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables) que surge del siguiente detalle:

Desde la emisión hasta el mes 12: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
Desde el mes 13 hasta el mes 24: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
Desde el mes 25 hastas la Fecha de Vencimiento: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/0c944533-444d-462c-a211-69d212678d62""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/0621e3e6-a297-49d5-8691-bc4e6131109e"""
}
PN35O = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 35 Vto 27 09 2029",
    "Código": "PN35O",
    "ISIN": "AR0623274765",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/09/2024",
    "Vencimiento": "27/09/2029",
    "Fecha Primer Cupón": "27/03/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/03/2025", "27/09/2025", "27/03/2026", "27/09/2026",
    "27/03/2027", "27/09/2027", "27/03/2028", "27/09/2028",
    "27/03/2029", "27/09/2029"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m20 de la emisión",
    "Fecha Call": "27/09/2024",
    "Precio Call": {"m0 a m20": 1.03, "m21 a m40": 1.02, "m41 en adelante": 1.01},  # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar la totalidad (pero no en parte) de las Obligaciones Negociables a partir del mes veinte (20) desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde el mes 0 hasta el mes 20: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.               
                  - Desde el mes 21 hasta el mes 40: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.
                  - Desde el mes 41 hasta la Fecha de Vencimiento: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9290%2FMPMAE%2DRES%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2035%2DAviso%20de%20Resultados%2025%2D09%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9290&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9290%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2035%2DSuplemento%20de%20Prospecto%2020%2D09%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9290&p=true&ga=1"""
}
IRCOO = {
    "Nombre Security": "ON IRSA S.A. Clase XXIII Vto 23 10 2029",
    "Código": "IRCOO",
    "ISIN": "AR0084572384",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Consumer Discretionary",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/10/2024",
    "Vencimiento": "23/10/2029",
    "Fecha Primer Cupón": "23/07/2025",
    "Cupón / Spread": 7.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/07/2025", "23/01/2026", "23/07/2026", "23/01/2027", "23/07/2027", 
                        "23/01/2028", "23/07/2028", "23/01/2029", "23/07/2029", "23/10/2029"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir del m48 de la emisión",
    "Fecha Call": "23/10/2028",
    "Precio Call": {"m48 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Sociedad tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables Clase XXIII a partir de los doce (12) meses previos a la Fecha de Vencimiento bajo los siguientes términos:
                  - Desde doce meses antes de la Fecha de Vencimiento: Precio de rescate de 100%/ del capital, más intereses devengados e impagos y Montos Adicionales, si hubiera.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9346%2FMPMAE%2DRES%2DON%20IRSA%20Clase%20XXII%20y%20XXIII%2D%20Aviso%20de%20Resultados%2021%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9346&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9346%2FMPMAE%2DANU%2D%20ON%20IRSA%20Clases%20XXII%20y%20XXIII%20%2D%20Suplemento%20de%20Prospecto%2016%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9346&p=true&ga=1"""
}
TTC9O = {
    "Nombre Security": "ON Tecpetrol S.A. Clase 9 Vto 24 10 2029",
    "Código": "TTC9O",
    "ISIN": "AR0482976963",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "24/10/2024",
    "Vencimiento": "24/10/2029",
    "Fecha Primer Cupón": "24/04/2025",
    "Cupón / Spread": 6.8, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["24/04/2025", "24/10/2025", "24/04/2026", "24/10/2026",
    "24/04/2027", "24/10/2027", "24/04/2028", "24/10/2028",
    "24/04/2029", "24/10/2029"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m12 de la emisión",
    "Fecha Call": "24/10/2025",
    "Precio Call": {"m12 a m24": 1.03, "m25 a m36": 1.02, "m37 en adelante": 1.01}, # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su opción, de rescatar total o parcialmente las Obligaciones Negociables Clase 8 a partir del mes doce (12) desde la Fecha de Emisión y Liquidación bajo los siguientes términos:
                  - Desde el mes 12 hasta el mes 24: Precio de rescate de 103%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 8.
                  - Desde el mes 25 hasta el mes 36: Precio de rescate de 102%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 8.
                  - Desde el mes 37 en adelante: Precio de rescate de 101%/ del capital, más intereses devengados e impagos, Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 8.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9348%2FMPMAE%2DRES%2D%20ON%20TECPETROL%20Clase%208%20y%209%20%2D%20Aviso%20de%20Resultados%2022%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9348&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9348%2FMPMAE%2DANU%2DON%20TECPETROL%20Clase%208%20y%20Clase%209%20%2D%20Suplemento%20de%20Prospecto%20%2016%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9348&p=true&ga=1"""
}
VSCRO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXVI Vto 10 10 2031",
    "Código": "VSCRO",
    "ISIN": "AR0138120560",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Hard Dolar",
    "Industria": "Energy",
    "Moneda": "USD",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2024",
    "Vencimiento": "10/10/2031",
    "Fecha Primer Cupón": "10/04/2025",
    "Cupón / Spread": 7.65, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/04/2025", "10/10/2025", "10/04/2026", "10/10/2026",
    "10/04/2027", "10/10/2027", "10/04/2028", "10/10/2028",
    "10/04/2029", "10/10/2029", "10/04/2030", "10/10/2030",
    "10/04/2031", "10/10/2031"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [33] + [0] + [33] + [0]+ [34]),
    "Quote Price Convention": "DIRTY",
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "10/10/2024",
    "Precio Call": {"desde la emisión hasa m23: 1.03, m24 en adelante: 1"}, # Precio Call
    "Comentarios": """La Sociedad podrá rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables Clase XXVI bajo los siguientes términos:

                  - Desde la Fecha de Emisión y Liquidación hasta el mes 24 (exclusive): 103%/ del capital, más intereses devengados e impagos hasta la fecha de rescate.
                  
                  - Desde el mes 24 hasta la Fecha de Vencimiento: 100%/ del capital, más intereses devengados e impagos hasta la fecha de rescate.""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9318%2FMPMAE%2DRES%2DON%20VISTA%20ENERGY%20ARGENTINA%20Clase%20XXVI%20%20%2D%20Aviso%20de%20Resultados%2008%2D10%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9318&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9318%2FMPMAE%2DANU%2DON%20VISTA%20ENERGY%20ARGENTINA%20Clase%20XXVI%20Suplemento%20Prospecto%2002%2D10%2D2024%2Epdf%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9318&p=true&ga=1"""
}

# Fichas ON BADLAR Corporativos
CWS1P = {
    "Nombre Security": "ON Pyme CNV Garantizada CROWE AR S.A. Serie I Vto 27 04 2023",
    "Código": "CWS1P",
    "ISIN": "ARCROA560013",
    "Calificación": "B+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Food and Beverages",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/09/2021",
    "Vencimiento": "27/09/2024",
    "Fecha Primer Cupón": "27/12/2021",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "27/12/2021", "27/3/2022", "27/06/2022", "27/9/2022", "27/12/2022", "27/3/2023", "27/6/2023", 
    "27/9/2023", "27/12/2023", "27/3/2024", "27/6/2024", "27/9/2024" 
    ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "",
    "Suplemento Prospecto": "",
}
RB57O = {
    "Nombre Security": "ON Rombo Compañia Financiera S.A. Clase 57 Vto 15 09 2025",
    "Código": "RB57O",
    "ISIN": "AR0732842957",
    "Calificación": "ML A-1.ar",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/09/2024",
    "Vencimiento": "13/09/2025",
    "Fecha Primer Cupón": "13/12/2024",
    "Cupón / Spread": 5.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["13/12/2024", "13/03/2025", "13/06/2025", "13/09/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/RB57O/Y/MPMAE-RES-ON%20ROMBO%20CF%20SERIE%2057-58-Aviso%20de%20Resultados%2010-09-24.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/RB57O/Y/MPMAE-ANU-ON%20ROMBO%20CF%20SERIE%2057-58-Suplemento%20de%20Prospecto%2004-09-24.PDF",
}
ICC1O = {
    "Nombre Security": "ON ICBC (Argentina) S.A.U Clase I Vto. 29 08 2025",
    "Código": "ICC1O",
    "ISIN": "AR0936072922",
    "Calificación": "ML A-1.ar",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/08/2024",
    "Vencimiento": "29/08/2025",
    "Fecha Primer Cupón": "29/11/2024",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["29/11/2024", "28/02/2025", "29/05/2025", "29/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/ICC1O/Y/MPMAE-RES-ON%20ICBC%20CLASE%201-Aviso%20de%20Resultados%2027-08-24.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/ICC1O/Y/MPMAE-ANU-ON%20ICBC%20CLASE%201-Suplemento%20de%20Prospecto%2021-08-24.pdf",
}
RCCPO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XXIV Vto 07 10 2025",
    "Código": "RCCPO",
    "ISIN": "AR0409282578",
    "Calificación": "A1+ (arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/10/2024",
    "Vencimiento": "07/10/2025",
    "Fecha Primer Cupón": "07/01/2025",
    "Cupón / Spread": 4.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["07/01/2025", "07/04/2025", "07/07/2025", "07/10/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/RCCPO/Y/MPMAE-RES-ON%20ARCOR%20CLASE%2024%20Aviso%20de%20Resultados%2002-10-2024.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/RCCPO/Y/MPMAE-ANU-ON%20ARCOR%20CLASE%2024%20Suplemento%20Prospecto%2030-09-2024.pdf",
}
DHS9O = {
    "Nombre Security": "ON Credicuotas Consumo S.A. Serie IX Vto 29 09 2025",
    "Código": "DHS9O",
    "ISIN": "AR0642940024",
    "Calificación": "A1(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/09/2024",
    "Vencimiento": "27/09/2025",
    "Fecha Primer Cupón": "27/12/2024",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["27/12/2024", "27/03/2025", "27/06/2025", "27/09/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/DHS9O/Y/MPMAE-RES-ON%20CREDICUOTAS%20CONSUMO%20SERIE%209-Aviso%20de%20Resultados%2025-09-24.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/DHS9O/Y/MPMAE-ANU-ON%20CREDICUOTAS%20CONSUMO%20SERIE%209-Suplemento%20de%20Prospecto%2023-09-24.pdf",
}
BPCHO = {
    "Nombre Security": "ON Banco Supervielle S.A. Clase H Vto 04 08 2025",
    "Código": "BPCHO",
    "ISIN": "AR0561943694",
    "Calificación": "A1(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "02/08/2024",
    "Vencimiento": "02/11/2025",
    "Fecha Primer Cupón": "02/11/2024",
    "Cupón / Spread": 5.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["02/11/2024", "02/02/2025", "02/05/2025", "02/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "",
    "Suplemento Prospecto": "",
}
DNC6O = {
    "Nombre Security": "ON Edenor S.A. Clase 6 Vto 05 08 2025",
    "Código": "DNC6O",
    "ISIN": "AR0310355869",
    "Calificación": "A1(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/08/2024",
    "Vencimiento": "05/08/2025",
    "Fecha Primer Cupón": "05/11/2024",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["05/11/2024", "05/02/2025", "05/05/2025", "05/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/DNC6O/Y/MPMAE-RES-ON%20EDENOR%20Clase%205%20y%206%20-%20Aviso%20de%20Resultados%2001-08-2024.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/DNC6O/Y/MPMAE-ANU-ON%20EDENOR%20CLAS%205%20y%206%20Suplemento%20Prospecto%2026-07-2024.pdf",
}
TYCZO = {
    "Nombre Security": "ON Toyota Cia Financiera de Argentina S.A. Clase 33 Vto 08 06 2026",
    "Código": "TYCZO",
    "ISIN": "AR0282999389",
    "Calificación": "AA+(arg)/A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/12/2024",
    "Vencimiento": "06/06/2026",
    "Fecha Primer Cupón": "06/03/2025",
    "Cupón / Spread": 5.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["06/03/2025", "06/06/2025", "06/09/2025", "06/12/2025",
    "06/03/2026", "06/06/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 3 + [33.33] * 2 + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9428%2FMPMAE%2DRES%2DON%20TOYOTA%20CIA%20FIN%20ARG%20CLASE%2033%2DAviso%20de%20Resultados%2003%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9428&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9428%2FMPMAE%2DANU%2DON%20TOYOTA%20CIA%20FIN%20ARG%20CLASE%2033%2DSuplemento%20de%20Prospecto%2027%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9428&p=true&ga=1",
}
BDCJO = {
    "Nombre Security": "ON BACS Clase XVIII Vto 24 11 2025",
    "Código": "BDCJO",
    "ISIN": "AR0982773126",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/11/2024",
    "Vencimiento": "22/11/2025",
    "Fecha Primer Cupón": "22/02/2025",
    "Cupón / Spread": 5.98, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "22/02/2025", "22/05/2025", "22/08/2025", "22/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9405%2FMPMAE%2DRES%2DON%20BACS%20Clase%20XVIII%20Aviso%20de%20Resultado%2020%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9405&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9405%2FMPMAE%2DANU%2DON%20BACS%20Clase%20XVIII%20%20Suplemento%20de%20Prospecto%2015%2D11%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9405&p=true&ga=1",
}
OZC4O = {
    "Nombre Security": "ON EDEMSA Clase 4 Vto 29 11 2025",
    "Código": "OZC4O",
    "ISIN": "AR0308606349",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "29/11/2025",
    "Fecha Primer Cupón": "28/02/2025",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["28/02/2025", "29/05/2025", "29/08/2025", "29/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412%2FMPMAE%2DRES%2DON%20EDEMSA%20CLASE%203%20Y%204%2DAviso%20de%20Resultado%2028%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412%2FMPMAE%2DANU%2DON%20EDEMSA%20CLASE%203%20Y%204%2DSuplemento%2022%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9412&p=true&ga=1",
}
LN21P = {
    "Nombre Security": "ON Pyme CNV Garantizada Liliana S.R.L. Serie II Clase I Vto 26 03 2026",
    "Código": "LN21P",
    "ISIN": "AR0992777646",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/03/2024",
    "Vencimiento": "27/03/2026",
    "Fecha Primer Cupón": "27/06/2024",
    "Cupón / Spread": -1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["27/06/2024", "27/09/2024", "27/12/2024", "27/03/2025",
    "27/06/2025", "27/09/2025", "27/12/2025", "27/03/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33.33] * 2 + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9019%2FMPMAE%2DANU%2DON%20PYME%20CNV%20GAR%20LILIANA%20SERIE%202%2DProspecto%2020%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9019&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9019%2FMPMAE%2DRES%2DON%20PYME%20CNV%20GAR%20LILIANA%20SERIE%202%2DAviso%20de%20Resultado%2025%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9019&p=true&ga=1",
}
LNS3P = {
    "Nombre Security": "ON Pyme CNV Garantizada Liliana S.R.L. Serie III Vto 30 04 2027",
    "Código": "LNS3P",
    "ISIN": "AR0771617500",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2025",
    "Vencimiento": "30/04/2027",
    "Fecha Primer Cupón": "30/07/2025",
    "Cupón / Spread": 5.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["30/07/2025", "30/10/2025", "30/01/2026", "30/04/2026",
    "30/07/2026", "30/10/2026", "30/01/2027", "30/04/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33] * 2 + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9624%2FMPA3%2DRES%2DON%20PYME%20CNV%20GAR%20LILIANA%20SERIE%20III%2DAviso%20de%20Resultados%2028%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9624&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9624%2FMPA3%2DON%20PYME%20CNV%20GAR%20LILIANA%20SERIE%20III%2DProspecto%2022%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9624&p=true&ga=1",
}
VWCBO = {
    "Nombre Security": "ON Volkswagen Financial Services S.A. Clase 11 Vto 22 10 2025",
    "Código": "VWCBO",
    "ISIN": "AR0763826689",
    "Calificación": "AA+(arg)/A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financial",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/10/2024",
    "Vencimiento": "22/10/2025",
    "Fecha Primer Cupón": "22/01/2025",
    "Cupón / Spread": 5.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZBALE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["22/01/2025", "22/04/2025", "22/07/2025", "22/10/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 2 + [50] * 2),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://www.mae.com.ar/descarga/docs/M/VWCBO/Y/MPMAE-ANU-ON%20VOLKSWAGEN%20FIN%20SERV%20CLASE%2011-Suplemento%20de%20Prospecto%2014-10-24.pdf",
    "Suplemento Prospecto": "https://www.mae.com.ar/descarga/docs/M/VWCBO/Y/MPMAE-ANU-ON%20VOLKSWAGEN%20FIN%20SERV%20CLASE%2011-Suplemento%20de%20Prospecto%2014-10-24.pdf",
}

#  Fichas Soberanos Corporativos
M31L5 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos TAMAR Vto 31 07 2025",
    "Código": "M31L5",
    "ISIN": "M31L5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/04/2025",
    "Vencimiento": "31/07/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['31/07/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
MA26 = {
    "Nombre Security": "Bono del Tesoro Nacional en Pesos TAMAR Vto 30 04 2026",
    "Código": "MA26",
    "ISIN": "MA26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Tasa Fija",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/04/2025",
    "Vencimiento": "30/04/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 4., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE_CAP", # FIJA o VARIABLE o VARIABLE_CAP(para tamar)
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['30/04/2026'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}

# Fichas ON TAMAR Corporativos
HBC8O = {
    "Nombre Security": "ON Banco Hipotecario Clase VIII Vto 20 12 2025",
    "Código": "HBC8O",
    "ISIN": "AR0083266764",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/12/2024",
    "Vencimiento": "20/12/2025",
    "Fecha Primer Cupón": "20/03/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["20/03/2025", 
    "20/06/2025", 
    "20/09/2025",
    "20/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": """Con una antelación no menor a cinco (5) Días Hábiles ni mayor a sesenta (60) Días Hábiles anteriores a la fecha de dicho rescate, el Banco podrá rescatar la totalidad o
    parte de las Obligaciones Negociables a ese momento en circulación en las fechas y en los montos 28 especificados o determinados junto con intereses devengados (si hubiera) a la fecha fijada para el rescate (la que deberá ser una Fecha de 
    Pago de Intereses). El rescate parcial será realizado a pro rata entre los Tenedores de Obligaciones Negociables. En todos los casos de rescate, se garantizará el trato igualitario entre los Inversores Calificados.""",
    "Fecha Call": "20/12/2024",
    "Precio Call": 1.,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EZToLvCltkVNjQ1Ex4qGfVkBFNropAUEtQdudY3HvjJl6g",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EVvq7H3UH2lCsjY9KAfgrzwBiaN_heaaX5gL4oTAe9cqzg",
}
T643O = {
    "Nombre Security": "ON Tarjeta Naranja S.A.U. Clase 64 Serie III Vto. 30 04 2026",
    "Código": "T643O",
    "ISIN": "T643O",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/04/2025",
    "Vencimiento": "30/04/2026",
    "Fecha Primer Cupón": "29/07/2025",
    "Cupón / Spread": 4.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["29/07/2025", "29/10/2025", "29/01/2026", "30/04/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",    
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DRES%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DAviso%20de%20Resultado%2025%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455%2FMPA3%2DANU%2DON%20EF%20TARJETA%20NARANJA%20CLASE%2064%2DSuplemento%2023%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D04%2F7455&p=true&ga=1"""
}
BF34O = {
    "Nombre Security": "ON Banco BBVA Argentina S.A. Clase 34 Vto. 12 09 2025",
    "Código": "BF34O",
    "ISIN": "AR0620901535",
    "Calificación": "AAA(arg)/A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/02/2026",
    "Fecha Primer Cupón": "27/05/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["27/05/2025", "27/08/2025", "27/11/2025", "27/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DRES%2D%20ON%20BANCO%20BBVA%20ARGENTINA%20CLASE%2032%2D33%2D34%2DAviso%20resultado%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553%2FMPMAE%2DANU%2DON%20BANCO%20BBVA%20%20Clases%2032%2033%20y%2034%20Suplemento%20de%20Prospecto%2018%2E02%2E25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9553&p=true&ga=1",
}
MR42O = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XLII Vto. 26 02 2026",
    "Código": "MR42O",
    "ISIN": "AR0252902645",
    "Calificación": "BBB+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "26/02/2025",
    "Vencimiento": "26/02/2026",
    "Fecha Primer Cupón": "26/05/2025",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["26/05/2025", "26/08/2025", "26/11/2025", "26/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://aif2.cnv.gov.ar/presentations/publicview/526d8e83-2a72-4535-ad18-33b62729d8e2",
    "Suplemento Prospecto": "https://aif2.cnv.gov.ar/presentations/publicview/f6624813-fe40-4743-96f3-ebbcc177c18e",
}
PN39O = {
    "Nombre Security": "ON Pan American Energy SL Clase 39 Vto 06 03 2026",
    "Código": "PN39O",
    "ISIN": "AR0833318733",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/03/2025",
    "Vencimiento": "06/03/2026",
    "Fecha Primer Cupón": "07/06/2025",
    "Cupón / Spread": 2.15, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "07/06/2025", 
    "07/09/2025",
    "07/12/2025",
    "06/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": """Rescate total a opción de la Emisora desde la emisión""",
    "Fecha Call": "07/03/2025",
    "Precio Call": {"d0 a d121": 1.0100, "d122 a d242": 1.0075, "d243 en adelante": 1.0050},  # Precio Call
    "Comentarios": """En cualquier momento, la Emisora tendrá el derecho, a su sola opción, de 
rescatar la totalidad de las Obligaciones Negociables (pero no en parte) a los siguientes precios de rescate:

- Desde la Fecha de Emisión y Liquidación hasta el día 121: 101,000%/ del capital.
- Desde el día 122 hasta el día 242: 100,750%/ del capital.
- Desde el día 243 hasta la fecha de vencimiento: 100,500%/ del capital.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9567%2FMPMAE%2DRES%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2039%2DAviso%20de%20Resultados%2006%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9567&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9567%2FMPMAE%2DANU%2DON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2039%2DSuplemento%20de%20Prospecto%2005%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9567&p=true&ga=1",
}
HBC9O = {
    "Nombre Security": "ON Banco Hipotecario Clase IX Vto 21 02 2026",
    "Código": "HBC9O",
    "ISIN": "AR0299083334",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/02/2025",
    "Vencimiento": "21/02/2026",
    "Fecha Primer Cupón": "21/05/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "21/05/2025", 
    "21/08/2025",
    "21/11/2025",
    "21/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": """Con una antelación no menor a cinco (5) Días Hábiles ni mayor a sesenta (60) Días Hábiles anteriores a la fecha de dicho rescate, el Banco podrá rescatar la totalidad o 
parte de las Obligaciones Negociables a ese momento en circulación en las fechas y en los montos 
especificados o determinados junto con intereses devengados (si hubiera) a la fecha fijada para el rescate 
(la que deberá ser una Fecha de Pago de Intereses). El rescate parcial será realizado a pro rata entre los 
Tenedores de Obligaciones Negociables. En todos los casos de rescate, se garantizará el trato igualitario 
entre los inversores. """,
    "Fecha Call": "21/12/2025",
    "Precio Call": 1.,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EZToLvCltkVNjQ1Ex4qGfVkBFNropAUEtQdudY3HvjJl6g",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EVvq7H3UH2lCsjY9KAfgrzwBiaN_heaaX5gL4oTAe9cqzg",
}
BYCLO = {
    "Nombre Security": "ON Banco de Galicia y Buenos Aires S.A.U. Clase XX Vto. 27 12 2025",
    "Código": "BYCLO",
    "ISIN": "AR0371879401",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/12/2024",
    "Vencimiento": "27/12/2025",
    "Fecha Primer Cupón": "27/03/2025",
    "Cupón / Spread": 2.7, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "27/03/2025", 
    "27/06/2025", 
    "27/09/2025",
    "27/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/ETSSB7egi-pEqlj0Vh6mcp8BxQBKKHRY6lK9O03KugJA9g",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7216%2FMPMAE%2DANU%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XX%20Suplemento%2018%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7216&p=true&ga=1",
}
BYCQO = {
    "Nombre Security": "ON Banco de Galicia y Buenos Aires S.A.U. Clase XXV Vto. 30 04 2026",
    "Código": "BYCLO",
    "ISIN": "AR0371879401",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2025",
    "Vencimiento": "30/04/2026",
    "Fecha Primer Cupón": "30/07/2025",
    "Cupón / Spread": 3.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "30/07/2025", 
    "30/10/2025", 
    "30/01/2026",
    "30/04/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618%2FMP%20A3%2D%20RES%2DON%20BANCO%20DE%20GALICIA%20Clases%20XXIV%20y%20XXV%20Aviso%20de%20Resultados%2029%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618%2FMP%20A3%2D%20ON%20BANCO%20DE%20GALICIA%20CLASE%20XXIV%20%2D%20XXV%2D%20Suplemento%2025%2D04%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618&p=true&ga=1",
}
BPCLO = {
    "Nombre Security": "ON Banco Supervielle S.A. Clase K Vto 07 02 2026",
    "Código": "BPCLO",
    "ISIN": "AR0364168663",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/02/2025",
    "Vencimiento": "07/02/2026",
    "Fecha Primer Cupón": "07/05/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["7/5/2025", "7/8/2025", "7/11/2025", "7/2/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7277%2FMPMAE%2DRES%2DON%20BANCO%20SUPERVIELLE%20CLASES%20K%20Y%20L%2DAviso%20de%20Resultados%2005%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7277&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7277%2FMPMAE%2DANU%2DON%20BANCO%20SUPERVIELLE%20CLASES%20K%20Y%20L%2DSuplemento%2030%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7277"
}

BYCMO = {
    "Nombre Security": "ON Banco de Galicia y Buenos Aires S.A.U. Clase XXI Vto. 10 12 2026",
    "Código": "BYCMO",
    "ISIN": "AR0455014024",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/02/2025",
    "Vencimiento": "10/02/2026",
    "Fecha Primer Cupón": "10/05/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["10/5/2025", 
                        "10/8/2025", 
                        "10/11/2025", 
                        "10/2/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7295%2FMPMAE%2DRES%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XXI%20%2D%20Aviso%20de%20Resultados%2006%2D02%2D2025%2EPDF%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7295&p=true&ga=1""",
    "Suplemento de Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7295%2FMPMAE%2DANU%2DON%20BANCO%20DE%20GALICIA%20CLASE%20XXI%20%2D%20Suplemento%20Prospecto%2004%2D02%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D02%2F7295&p=true&ga=1"""
}
PSSWO = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 29 Vto  23 09 2025",
    "Código": "PSSWO",
    "ISIN": "AR0605030706",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/12/2024",
    "Vencimiento": "23/06/2026",
    "Fecha Primer Cupón": "23/03/2025",
    "Cupón / Spread": 3.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "23/03/2025", 
    "23/06/2025", 
    "23/09/2025",
    "23/12/2025",
    "23/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7207%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2029%2D30%2DAviso%20de%20Resultados%2019%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7207&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7207%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2029%2D30%2DSuplemento%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2024%2D12%2F7207&p=true&ga=1",
}
PSSYO = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 32 Vto 28 02 2026",
    "Código": "PSSYO",
    "ISIN": "AR0081898659",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2025",
    "Vencimiento": "28/02/2026",
    "Fecha Primer Cupón": "28/05/2025",
    "Cupón / Spread": 3.2, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "28/05/2025", 
    "28/08/2025", 
    "28/11/2025",
    "28/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DSuplemento%20de%20Prospecto%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
}
RB59O = {
    "Nombre Security": "ON Rombo Compañia Financiera S.A. Clase 59 Vto 01 02 2027",
    "Código": "RB59O",
    "ISIN": "AR0480183265",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/01/2025",
    "Vencimiento": "31/07/2026",
    "Fecha Primer Cupón": "01/05/2025",
    "Cupón / Spread": 3.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "01/05/2025", 
    "31/07/2025", 
    "31/10/2025",
    "31/01/2026",
    "01/05/2026",
    "31/07/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [50] * 2),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/ba01697d-e835-446d-a083-6ec1c1116909#""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110%2FMPMAE%2DANU%2DON%20ROMBO%20CF%20SERIE%2059%2D60%2DSuplemento%20de%20Prospecto%2022%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110&p=true&ga=1""",
}
BCCJO = {
    "Nombre Security": "ON Banco CMF S.A. Clase 18 Vto 06 02 2026",
    "Código": "BCCJO",
    "ISIN": "AR0135022199",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/02/2025",
    "Vencimiento": "06/02/2026",
    "Fecha Primer Cupón": "06/05/2025",
    "Cupón / Spread": 3.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -2, # enteros negativos
    "Días Lag índice hasta inc": -2, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "06/05/2025", 
    "06/08/2025", 
    "06/11/2025",
    "06/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.bancocmf.com.ar/wp-content/uploads/ON-Banco-CMF-Clase-17-y-18-Aviso-de-resultados.pdf""",
    "Suplemento Prospecto": """https://www.bancocmf.com.ar/wp-content/uploads/ON-Banco-CMF-Clase-17-y-18-Suplemento-de-Prospecto.pdf""",
}
BNCUO = {
    "Nombre Security": "ON Banco Santander Argentina S.A. Clase 28 Vto. 21 02 2026",
    "Código": "BNCUO",
    "ISIN": "AR0563570859",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/02/2025",
    "Vencimiento": "21/02/2026",
    "Fecha Primer Cupón": "21/05/2025",
    "Cupón / Spread": 2.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -2, # enteros negativos
    "Días Lag índice hasta inc": -2, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "21/05/2025", 
    "21/08/2025", 
    "21/11/2025",
    "21/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9542%2FMPMAE%2DRES%2DON%20BANCO%20SANTANDER%20%20CLASE%20XXVIII%20%2D%20Aviso%20de%20Resultados%2019%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9542&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9542%2FMPMAE%2DANU%2DON%20BANCO%20SANTANDER%20RIO%20%20Clase%20XXVIII%20%2D%20Suplemento%20de%20Prospecto%2017%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9542&p=true&ga=1""",
}
RCCQO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XXI Vto 25 02 2026",
    "Código": "RCCQO",
    "ISIN": "AR0482583744",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "25/02/2025",
    "Vencimiento": "25/02/2026",
    "Fecha Primer Cupón": "25/05/2025",
    "Cupón / Spread": 2.40, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -2, # enteros negativos
    "Días Lag índice hasta inc": -2, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "25/05/2025", 
    "25/08/2025", 
    "25/11/2025",
    "25/02/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9546%2FMPMAE%2DRES%2DON%20ARCOR%20Clase%2025%20%2D%20Aviso%20de%20Resultados%20%2020%2D02%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9546&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9546&ga=1""",
}
RCCTO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XXVII Vto 09 05 2026",
    "Código": "RCCTO",
    "ISIN": "RCCTO",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/05/2025",
    "Vencimiento": "09/05/2026",
    "Fecha Primer Cupón": "09/08/2025",
    "Cupón / Spread": 2.74, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -2, # enteros negativos
    "Días Lag índice hasta inc": -2, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "09/08/2025", 
    "09/11/2025",
    "09/02/2026",
    "09/05/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035%2FMPMAE%2DRES%2DON%20TECPETROL%20CLASE%207%20%2D%20Aviso%20de%20Resultados%2018%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035%2FMPMAE%2DANU%2DON%20TECPETROL%20Clase%207%2DSuplemento%20de%20Prospecto%2012%2D04%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9035&p=true&ga=1"""
}
RVS1O = {
    "Nombre Security": "ON Club Atletico River Plate Asoc. Civil Serie I Vto. 01 03 2027",
    "Código": "RVS1O",
    "ISIN": "AR0550419177",
    "Calificación": "BS2+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Other",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2025",
    "Vencimiento": "27/02/2027",
    "Fecha Primer Cupón": "27/05/2025",
    "Cupón / Spread": 3.89, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -2, # enteros negativos
    "Días Lag índice hasta inc": -2, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": [
    "27/05/2025", 
    "27/08/2025", 
    "27/11/2025",
    "27/02/2026",
    "27/05/2026",
    "27/08/2026",
    "27/11/2026",
    "27/02/2027",], # Lista de fechas como ejemplo
    "Amortización": ([0] + [25] + [0] + [25] + [0] + [25] + [0] + [25]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.bancocmf.com.ar/wp-content/uploads/ON-Club-River-Plate-Serie-I-Aviso-de-Resultados.pdf""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9546&ga=1""",
}

# Fichas ON DL Corporativos
AER9O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase IX Vto. 19 08 2026",
    "Código": "AER9O",
    "ISIN": "ARAEAR5600C1",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "19/08/2022",
    "Vencimiento": "19/08/2026",
    "Fecha Primer Cupón": "19/11/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "19/02/2026", "19/05/2026", "19/08/2026"], # Lista de fechas como ejemplo
    "Amortización": ([33.33] * 2 + [33.34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescata al 103 del precio hasta sexto mes después de emisión, 102 entre sexto y trigésimo y 101 hasta vencimiento",
    "Fecha Call": "19/08/2022",
    "Precio Call": 1.03,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/AER9O/Y/MPMAE-RES-%20ON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%209%20Adic%20Aviso%20Resultados%2003-07-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TBC4O/Y/MPMAE-ANU-ON%20CT%20BARRAGAN%20Clase%204%20-%20%20Suplemento%20Prosp%20%2019-11-21%20.PDF.pdf"""
}
RZ6BO = {
    "Nombre Security": "ON Rizobacter Argentina S.A. Serie VI Clase B Vto 07 09 24",
    "Código": "RZ6BO",
    "ISIN": "ARRIAR5600D4",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/09/2021",
    "Vencimiento": "07/09/2024",
    "Fecha Primer Cupón": "07/12/2021",
    "Cupón / Spread": 5.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["7/12/2021", "7/3/2022", "7/6/2022", "7/9/2022",
    "7/12/2022", "7/3/2023", "7/6/2023", "7/9/2023",
    "7/12/2023", "7/3/2024", "7/6/2024", "7/9/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False, # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/RZ6BO/Y/MPMAE-RES-ON%20RIZOBACTER%20ARGENTINA%20SERIE%206-Aviso%20de%20Resultado%2031-08-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/RZ6BO/Y/MPMAE-ANU-ON%20RIZOBACTER%20ARGENTINA%20SERIE%206-Suplemento%2027-08-21.pdf"""
}
RZ9AO = {
    "Nombre Security": "ON Rizobacter Argentina S.A. Serie IX Clase A Vto 28 06 26",
    "Código": "RZ9AO",
    "ISIN": "AR0065093756",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/06/2024",
    "Vencimiento": "28/06/2026",
    "Fecha Primer Cupón": "28/09/2024",
    "Cupón / Spread": 5.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/09/2024",
    "28/12/2024",
    "28/03/2025",
    "28/06/2025",
    "28/09/2025",
    "28/12/2025",
    "28/03/2026",
    "28/06/2026"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [25] + [0] + [75]),
    "Callable": False, # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/7f94443a-8692-4fb1-86c0-1acba6797343#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/0fc478d0-77ac-4419-bbb8-ea8f2fb4f138#"""
}
RZAAO = {
    "Nombre Security": "ON Rizobacter Argentina SA Serie X Clase A 28 11 2026",
    "Código": "RZAAO",
    "ISIN": "AR0340557484",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/11/2024",
    "Vencimiento": "28/11/2026",
    "Fecha Primer Cupón": "28/02/2025",
    "Cupón / Spread": 7.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/02/2025",
    "28/05/2025",
    "28/08/2025",
    "28/11/2025",
    "28/02/2026",
    "28/05/2026",
    "28/08/2026",
    "28/11/2026"
], # Lista de fechas como ejemplo
    "Amortización": False,
    "Callable": False, # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/e85c04e4-99ca-4b60-b036-cd2e605cfc51#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/ade3c8f9-719c-4dfc-a487-0cc1fe911096#"""
}
CP31O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXXI Vto 09 06 2026",
    "Código": "CP31O",
    "ISIN": "ARCGCO5600W3",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/06/2023",
    "Vencimiento": "09/06/2026",
    "Fecha Primer Cupón": "09/09/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["9/9/2023", "9/12/2023", "9/3/2024", "9/6/2024",
    "9/9/2024", "9/12/2024", "9/3/2025", "9/6/2025",
    "9/9/2025", "9/12/2025", "9/3/2026", "9/6/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CP31O/Y/MPMAE-RES-ON%20EF%20CIA%20GENERAL%20COMBUSTIBLES%20CLASE%2031%20Y%2032%20Aviso%20Resultados%2007-06-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CP31O/Y/MPMAE-ANU-ON%20EF%20CIA%20GENERAL%20COMBUSTIBLE%20Clase%2031%20y32%20Suplemento%2006-06-2023.pdf"""
}
HJCAO = {
    "Nombre Security": "ON John Deere Clase X Vto 08 03 2026",
    "Código": "HJCAO",
    "ISIN": "AR0996706922",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/03/2024",
    "Vencimiento": "08/03/2026",
    "Fecha Primer Cupón": "08/06/2024",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["8/6/2024", "8/9/2024", "8/12/2024", "8/3/2025",
    "8/6/2025", "8/9/2025", "8/12/2025", "8/3/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/HJCAO/Y/MPMAE-RES-%20ON%20EF%20JOHN%20DEERE%20CREDIT%20CF%20Clase%20X%20Aviso%20de%20Resultados%2005.03.24.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/HJCAO/Y/MPMAE-ANU-ON%20EF%20JOHN%20DEERE%20CREDIT%20CF%20CLASE%2010-Suplemento%20de%20Prospecto%2001-03-24.pdf"""
}
HJCEO = {
    "Nombre Security": "ON John Deere Clase XIII Vto 04 01 2026",
    "Código": "HJCEO",
    "ISIN": "HJCEO",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/07/2024",
    "Vencimiento": "04/01/2026",
    "Fecha Primer Cupón": "04/10/2024",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "4/10/2024",
    "4/1/2025",
    "4/4/2025",
    "4/7/2025",
    "4/10/2025",
    "4/1/2026"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/bfc3b603-5f0e-4611-a7bd-997582d659a0#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/0f367295-f3a8-4617-aee8-c9f0f02801b8#"""
}
LIC3O = {
    "Nombre Security": "ON Lipsa S.R.L. Clase III Vto 23 08 2025",
    "Código": "LIC3O",
    "ISIN": "LIC3O",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/08/2022",
    "Vencimiento": "23/08/2024",
    "Fecha Primer Cupón": "23/11/2022",
    "Cupón / Spread": 2.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "23/11/2022",
    "23/2/2023",
    "23/5/2023",
    "23/8/2023",
    "23/11/2023",
    "23/2/2024",
    "23/5/2024",
    "23/8/2024",
    "25/11/2024",
    "24/2/2025",
    "23/5/2025",
    "25/8/2025"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [33] + [0] + [33] + [0] + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LIC3O/Y/MPMAE-RES-ON%20LIPSA%20SRL%20Clases%202%20Y%203-Aviso%20de%20Resultado%2019-08-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LIC3O/Y/MPMAE-ANU-ON%20LIPSA%20SRL%20CLASE%202%20Y%203%20-%20Suplemento%2010-08-2022.pdf"""
}
LIC5O = {
    "Nombre Security": "ON Lipsa S.R.L. Clase V Vto 14 07 2025",
    "Código": "LIC5O",
    "ISIN": "ARLIPS560079",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/07/2023",
    "Vencimiento": "14/07/2025",
    "Fecha Primer Cupón": "14/10/2023",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["14/10/2023", "14/1/2024", "14/4/2024", "14/7/2024",
    "14/10/2024", "14/1/2025", "14/4/2025", "14/7/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33] + [33] + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LIC5O/Y/MPMAE-RES-ON%20LIPSA%20Clase%20V%20Aviso%20de%20Resultados%2012-07-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LIC5O/Y/MPMAE-ANU-ON%20LIPSA%20Clase%20V%20-%20Suplemento%2006-07-2023.pdf"""
}
LTS1P = {
    "Nombre Security": "ON Pyme CNV Garantizada Latin Lemon S.A. Serie I Vto 21 10 2025",
    "Código": "LTS1P",
    "ISIN": "ARLLEM560016",
    "Calificación": "A(arg) - Avalada",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/10/2022",
    "Vencimiento": "21/10/2025",
    "Fecha Primer Cupón": "21/01/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "21/1/2023",
    "21/4/2023",
    "21/7/2023",
    "21/10/2023",
    "21/1/2024",
    "21/4/2024",
    "21/7/2024",
    "21/10/2024",
    "21/1/2025",
    "21/4/2025",
    "21/7/2025",
    "21/10/2025"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [20] * 5),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LTS1P/Y/MPMAE-RES-ON%20PYME%20CNV%20GAR%20LATIN%20LEMON%20SERIE%201-%20Aviso%20de%20Resultado%2018-10-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LTS1P/Y/MPMAE-ANU-%20ON%20PYME%20CNV%20GAR%20LATIN%20LEMON%20%20SERIE%201%20-%20Prospecto%2012-10-22.pdf"""
}
TLCFO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 14 Vto. 10 02 2028",
    "Código": "TLCFO",
    "ISIN": "ARTECO5600G5",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/02/2023",
    "Vencimiento": "10/02/2028",
    "Fecha Primer Cupón": "10/05/2023",
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/5/2023", "10/8/2023", "10/11/2023", "10/2/2024", "10/5/2024", "10/8/2024", "10/11/2024",
    "10/2/2025", "10/5/2025", "10/8/2025", "10/11/2025", 
    "10/2/2026", "10/5/2026", "10/8/2026", "10/11/2026", 
    "10/2/2027", "10/5/2027", "10/8/2027", "10/11/2027", "10/2/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLCFO/Y/MPMAE-RES-ON%20TELECOM%20ARGENTINA%20%20Clase%2014%20-%20Aviso%20de%20Resultados%2009-02-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLCFO/Y/MPMAE-ANU-ON%20TELECOM%20ARGENTINA%20CLASE%2014-%20Suplemento%20Precio%2007-02-2023.pdf"""
}
TLCGO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 15 Vto. 02 06 2026",
    "Código": "TLCGO",
    "ISIN": "ARTECO5600H3",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "02/06/2023",
    "Vencimiento": "02/06/2026",
    "Fecha Primer Cupón": "02/09/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["2/9/2023", "2/12/2023", "2/3/2024", "2/6/2024", "2/9/2024",
                        "2/12/2024", "2/3/2025", "2/6/2025", "2/9/2025", "2/12/2025",
                        "2/3/2026", "2/6/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLCGO/Y/MPMAE-RES-%20ON%20TELECOM%20ARGENTINA%20CLASE%2015%20Aviso%20de%20Resultados%2001-06-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLCGO/Y/MPMAE-ANU-ON%20TELECOM%20ARGENTINA%20CLASE%2015%20Suplemento%2030-05-23.pdf"""
}
MR36O = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XXXVI Vto. 28 07 2027",
    "Código": "MR36O",
    "ISIN": "MR36O",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/08/2024",
    "Vencimiento": "28/07/2027",
    "Fecha Primer Cupón": "28/11/2024",
    "Cupón / Spread": [6.75,8.75], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/11/2024",
    "28/02/2025",
    "28/05/2025",
    "28/08/2025",
    "28/11/2025",
    "28/02/2026",
    "28/05/2026",
    "28/08/2026",
    "28/11/2026",
    "28/02/2027",
    "28/05/2027",
    "28/08/2027"
], # Lista de fechas como ejemplo
    "Intereses":[1.7014,
 1.7014,
 1.6459,
 1.7014,
 2.2055,
 2.2055,
 2.1336,
 2.2055,
 2.2055,
 2.2055,
 2.1336,
 2.2055 
],
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/b5118335-de48-43b3-8046-61fd96860be6#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/4bd50992-53af-41be-93a4-e17ef346575c#"""
}
MR40O = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XL Vto. 01 11 2031",
    "Código": "MR40O",
    "ISIN": "MR40O",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/11/2024",
    "Vencimiento": "01/11/2031",
    "Fecha Primer Cupón": "01/05/2025",
    "Cupón / Spread": 11., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "1/5/2025",
    "1/11/2025",
    "1/5/2026",
    "1/11/2026",
    "1/5/2027",
    "1/11/2027",
    "1/5/2028",
    "1/11/2028",
    "1/5/2029",
    "1/11/2029",
    "1/5/2030",
    "1/11/2030",
    "1/5/2031",
    "1/11/2031"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 2 + [1.50] * 2 + [2.50] * 2 + [7.50] * 2 + [11] * 5 + [22]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
LUC4O = {
    "Nombre Security": "ON Luz de Tres Picos S.A. Clase 4 Vto 29 09 2026",
    "Código": "LUC4O",
    "ISIN": "ARLUZT560047",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/09/2022",
    "Vencimiento": "29/09/2026",
    "Fecha Primer Cupón": "20/12/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "29/12/2022",
    "29/3/2023",
    "29/6/2023",
    "29/9/2023",
    "29/12/2023",
    "29/3/2024",
    "29/6/2024",
    "29/9/2024",
    "29/12/2024",
    "29/3/2025",
    "29/6/2025",
    "29/9/2025",
    "29/12/2025",
    "29/3/2026",
    "29/6/2026",
    "29/9/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 13 + [33.33] + [33.33] + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LUC4O/Y/MPMAE-RES-LUZ%20DE%20TRES%20PICOS%20Clase%204-%20Aviso%20Resultado%2026-09-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LUC4O/Y/MPMAE-ANU-%20ON%20LUZ%20DE%20TRES%20PICOS%20CLASE%204%20Suplemento%20de%20Prospecto%2022-09-2022.pdf"""
}
PEC7O = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Serie VII Vto 14 09 2027",
    "Código": "PEC7O",
    "ISIN": "ARPAEG5600C2",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/9/2023",
    "Vencimiento": "14/9/2027",
    "Fecha Primer Cupón": "14/12/2023",
    "Cupón / Spread": 3.40, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "14/12/2023",
    "14/3/2024",
    "14/6/2024",
    "14/9/2024",
    "14/12/2024",
    "14/3/2025",
    "14/6/2025",
    "14/9/2025",
    "14/12/2025",
    "14/3/2026",
    "14/6/2026",
    "14/9/2026",
    "14/12/2026",
    "14/3/2027",
    "14/6/2027",
    "14/9/2027"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [100 / 7] * 7),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PEC7O/Y/MPMAE-RES-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASES%20VI%20Y%20VII-Aviso%20de%20Resultados%2012-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PEC7O/Y/MPMAE-ANU-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASES%20VI%20Y%20VII%20-%20Suplemento%2006-09-2023.pdf"""
}
PEC8O = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Clase VIII Vto 01 03 2027",
    "Código": "PEC8O",
    "ISIN": "AR0052799894",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/02/2024",
    "Vencimiento": "01/03/2027",
    "Fecha Primer Cupón": "29/05/2024",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "29/05/2024",
    "29/08/2024",
    "29/11/2024",
    "01/03/2025",
    "29/05/2025",
    "29/08/2025",
    "29/11/2025",
    "01/03/2026",
    "29/05/2026",
    "29/08/2026",
    "29/11/2026",
    "01/03/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [14] * 6 + [16]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8983%2FMPMAE%2DRES%2DON%20PETROLERA%20ACONCAGUA%208%2D9%2D10%2D11%2DAviso%20de%20Resultados%2027%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8983&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8983%2FMPMAE%2DANU%2DON%20PETROLERA%20ACONCAGUA%20CLASES%208%2D9%2D10%2D11%2DSuplemento%2021%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8983&p=true&ga=1"""
}
RMS3P = {
    "Nombre Security": "ON President Petroleum S.A. Clase III Vto 27 12 2025",
    "Código": "RMS3P",
    "ISIN": "ARPREA560036",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/12/2022",
    "Vencimiento": "27/12/2025",
    "Fecha Primer Cupón": "27/03/2023",
    "Cupón / Spread": 4.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1.1782, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "27/03/2023",
    "27/06/2023",
    "27/09/2023",
    "27/12/2023",
    "27/03/2024",
    "27/06/2024",
    "27/09/2024",
    "27/12/2024",
    "27/03/2025",
    "27/06/2025",
    "27/09/2025",
    "27/12/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 6 + [16.66] * 5 + [16.70]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m24 de la emisión",
    "Fecha Call": "27/12/2024",
    "Precio Call": {"m24 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Compañía podrá rescatar las Obligaciones Negociables, en forma total o parcial, en o desde la fecha en que se cumplan doce (12) meses 
                    previos a la Fecha de Vencimiento, a un precio igual al 100% del monto de capital pendiente de pago en virtud de las Obligaciones 
                    Negociables en circulación, pagadero en Pesos al Tipo de Cambio Aplicable, con más los intereses devengados e impagos a dicha fecha 
                    de rescate y Montos Adicionales, si hubiera, previa notificación con al menos cinco (5) Días Hábiles de anticipación, conforme aviso a 
                    publicar en los términos requeridos por los reglamentos de listado y negociación de los mercados en los que se encuentren listadas y/o 
                    negocien las Obligaciones Negociables e informándose, mediante la publicación de un aviso de hecho relevante en la Página Web de la 
                    CNV y en el Boletín Diario de la BCBA. """,
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/c10de4b8-a8df-4382-8a4e-1deb4e817e28#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/b1625cc1-918e-4a4c-a5e0-857a3182a064#"""
}
RMS3Preestructurado = {
    "Nombre Security": "ON President Petroleum S.A. Clase III Vto 27 12 2026 Reestructurado",
    "Código": "RMS3Preestructurado",
    "ISIN": "RMS3Preestructurado",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/01/2025",
    "Vencimiento": "27/12/2026",
    "Fecha Primer Cupón": "27/03/2025",
    "Cupón / Spread": [6.00,8.00], # es un nro flotante
    "Step-up": True, # Es binario True or False
    "Frecuencia de pago de cupón anual": 12., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ['27/01/2025',
                        '27/02/2025',
                        '27/03/2025',
                        '27/04/2025',
                        '27/05/2025',
                        '27/06/2025',
                        '27/07/2025',
                        '27/08/2025',
                        '27/09/2025',
                        '27/10/2025',
                        '27/11/2025', # desde aca paga amort
                        '27/12/2025',
                        '27/01/2026',
                        '27/02/2026',
                        '27/03/2026',
                        '27/04/2026',
                        '27/05/2026',
                        '27/06/2026',
                        '27/07/2026',
                        '27/08/2026',
                        '27/09/2026',
                        '27/10/2026',
                        '27/11/2026',
                        '27/12/2026'], # Lista de fechas como ejemplo, # Lista de fechas como ejemplo
    "Intereses": [
    0.5,
    0.5,
    0.5,
    0.5,
    0.5,
    0.5,
    0.6666667,
    0.6433333,
    0.62,
    0.5966667,
    0.5733333,
    0.55,
    0.5266667,
    0.4983333,
    0.47,
    0.4416667,
    0.4133333,
    0.385,
    0.3566667,
    0.3283333,
    0.3,
    0.2716667,
    0.2433333,
    0.215],
    "Amortización": ([0] * 6 + [4.86027588620083] * 6 + [5.90176357610101] * 11 + [5.91894534568391]),
    "Callable": False, # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": None,
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/c10de4b8-a8df-4382-8a4e-1deb4e817e28#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/b1625cc1-918e-4a4c-a5e0-857a3182a064#"""
}
YFCHO = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase XVI Vto. 13 12 2025",
    "Código": "YFCHO",
    "ISIN": "YFCHO",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "13/06/2024",
    "Vencimiento": "13/12/2025",
    "Fecha Primer Cupón": "13/09/2024",
    "Cupón / Spread": 2.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "13/9/2024",
    "13/12/2024",
    "13/3/2025",
    "13/6/2025",
    "13/9/2025",
    "13/12/2025"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False, # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/41fe8713-1675-4450-bd08-bd681acde734""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/1949a38d-cc89-470c-ac28-065018290a1c"""
}
GN37O = {
    "Nombre Security": "ON Genneia S.A. Clase XXXVII Vto 11 11 2026",
    "Código": "GN37O",
    "ISIN": "AREMGA5600P1",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/11/2022",
    "Vencimiento": "11/11/2026",
    "Fecha Primer Cupón": "11/02/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "11/2/2023",
    "11/5/2023",
    "11/8/2023",
    "11/11/2023",
    "11/2/2024",
    "11/5/2024",
    "11/8/2024",
    "11/11/2024",
    "11/2/2025",
    "11/5/2025",
    "11/8/2025",
    "11/11/2025",
    "11/2/2026",
    "11/5/2026",
    "11/8/2026",
    "11/11/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 13 + [33.33] * 2 + [33.34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m12 de la emisión",
    "Fecha Call": "11/11/2023",
    "Precio Call": {"m12 a m36: 1.02, m37 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento, la Compañía tendrá el derecho, a su sola opción, de 
                    rescatar las Obligaciones Negociables Clase XXXVII en su totalidad (pero no 
                    en parte), al precio de rescate de capital (más los intereses devengados y 
                    no pagados calculados hasta la fecha de rescate, los Montos Adicionales y 
                    cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 
                    XXXVII) que surge del siguiente detalle: 
                    Desde el mes 12 inclusive contado desde la Fecha de  Emisión y Liquidación 
                    hasta el mes 36 exclusive contado desde la Fecha de Emisión y Liquidación: 102%
                    Luego del mes 36 inclusive contado desde la Fecha de Emisión y Liquidación y hasta el 
                    día anterior a la Fecha de 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/GN37O/Y/MPMAE-RES-ON%20GENNEIA%20CLASE%2035%20Adicional%20y%20Clase%2037-%20Aviso%20de%20Resultados%2009-11-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/GN37O/Y/MPMAE-ANU-ON%20EF%20GENNEIA%20reapertura%20CLASE%2035%20y%20Clase%2037%20-%20Suplemento%20de%20Prospecto%2007-11-2022.pdf"""
}
CS40O = {
    "Nombre Security": "ON Cresud Serie 26 Clase 40 Vto 21 12 2026",
    "Código": "CS40O",
    "ISIN": "ARCRES5600X5",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/12/2022",
    "Vencimiento": "21/12/2026",
    "Fecha Primer Cupón": "21/03/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "21/3/2023",
    "21/6/2023",
    "21/9/2023",
    "21/12/2023",
    "21/3/2024",
    "21/6/2024",
    "21/9/2024",
    "21/12/2024",
    "21/3/2025",
    "21/6/2025",
    "21/9/2025",
    "21/12/2025",
    "21/3/2026",
    "21/6/2026",
    "21/9/2026",
    "21/12/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33] + [0] + [33] + [0] + [34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m42 de la emisión",
    "Fecha Call": "21/06/2026",
    "Precio Call": {"m42 en adelante: 1.01"},  # Precio Call
    "Comentarios": """Podremos rescatar a nuestra opción las Obligaciones Negociables Clase XL, en o desde la fecha en que se cumplan 
                    seis meses previos a la Fecha de Vencimiento, a un precio igual al 101% del valor nominal, pagadero en Pesos al Tipo de 
                    Cambio Aplicable, y Montos Adicionales, si hubiera, en forma total o parcial, siempre que ello estuviere permitido por la 
                    normativa cambiaria vigente en ese momento""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CS40O/Y/MPMAE-RES-ON%20CRESUD%20CLASE%2040-Aviso%20de%20Resultados%2016-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CS40O/Y/MPMAE-ANU-ON%20CRESUD%20CLASE%2040-%20Suplemento%20de%20Prospecto%2014-12-22.pdf"""
}
CS46O = {
    "Nombre Security": "ON Cresud Clase XLVI 18 07 2027",
    "Código": "CS46O",
    "ISIN": "AR0792642578",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "18/07/2024",
    "Vencimiento": "18/07/2027",
    "Fecha Primer Cupón": "18/01/2025",
    "Cupón / Spread": 1.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "18/01/2025",
    "18/07/2025",
    "18/01/2026",
    "18/07/2026",
    "18/01/2027",
    "18/07/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "call total o parcial a opción de la sociedad a partir del m33 de la emisión",
    "Fecha Call": "18/04/2027",
    "Precio Call": {"m33 en adelante: 1.01"},  # Precio Call
    "Comentarios": """Podremos rescatar a nuestra opción las Obligaciones Negociables Clase XLVI, en o desde la fecha en que se cumplan tres meses previos 
a la Fecha de Vencimiento, a un precio igual al 101 del valor nominal, con más los intereses devengados e impagos""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9176%2FMPMAE%2DRES%2DON%20CRESUD%20CLASE%20XLVI%20Aviso%20de%20Resultados%2015%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9176&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9176%2FMPMAE%2DANU%2DON%20CRESUD%20CLASE%20XLVI%20Suplemento%20de%20Prospecto%2011%2D07%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9176&p=true&ga=1"""
}
RZ8BO = {
    "Nombre Security": "ON Rizobacter Argentina SA Serie VIII Clase B 10 02 2026",
    "Código": "RZ8BO",
    "ISIN": "ARRIAR5600G7",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Industrials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/2/2023",
    "Vencimiento": "10/2/2026",
    "Fecha Primer Cupón": "10/5/2023",
    "Cupón / Spread": 3.98, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "10/5/2023",
    "10/8/2023",
    "10/11/2023",
    "10/2/2024",
    "10/5/2024",
    "10/8/2024",
    "10/11/2024",
    "10/2/2025",
    "10/5/2025",
    "10/8/2025",
    "10/11/2025",
    "10/2/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [25] + [0] + [75]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "10/02/2023",
    "Precio Call": {"m0 a m12: 1.03, m13 a m18: 1.02, m19 en adelante: 1.01"},  # Precio Call
    "Comentarios": """La Sociedad podrá reembolsar anticipadamente la totalidad o una parte 
                    de las Obligaciones Negociables Serie VIII Clase B. El importe a pagar 
                    a los obligacionistas será el valor de reembolso, que resultará de sumar 
                    al Valor Nominal de Reembolso de las ON Serie VIII Clase B 
                    total o parcial, según el caso con los intereses devengados conforme a las condiciones de 
                    emisión hasta el día de pago del valor de reembolso. 
                    El “Valor Nominal de Reembolso de las ON Serie VIII Clase B” será a 
                    un precio de: a) U$S 1,03 (Dólares uno coma cero tres) por cada U$S 1 
                    (Dólares uno), en caso de que la Emisora decida realizar el reembolso 
                    en el plazo entre la Fecha de Emisión y Liquidación hasta cumplidos los 
                    doce (12) meses; b) U$S 1,02 (Dólares uno coma cero dos) por cada 
                    U$S 1 (Dólares uno) en caso en que la Emisora decida realizar el 
                    reembolso en el plazo que comienza a partir de cumplidos los doce (12)
                    meses desde la Fecha de Emisión y Liquidación hasta cumplidos los 
                    18meses; y c) de U$S 1,01 (Dólares uno coma cero uno) por cada U$S 
                    1 (Dólares uno) en caso de que la Emisora decida realizar el reembolso 
                    en el plazo que comienza a partir de cumplidos los dieciocho (18) meses 
                    desde la Fecha de Emisión y Liquidación hasta la Fecha de Vencimiento 
                    de las ON Serie VIII Clase B.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/RZ8AO/Y/MPMAE-RES-ON%20RIZOBACTER%20SERIE%208-Aviso%20de%20Resultados%2007-02-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/RZ8AO/Y/MPMAE-ANU-ON%20RIZOBACTER%20SERIE%208-%20Suplemento%20de%20%20Prospecto%2003-02-23.pdf"""
}
PNICO = {
    "Nombre Security": "ON Pan American Energy SL Clase 17 Vto 09 02 2032",
    "Código": "PNICO",
    "ISIN": "ARAXIO5600Q1",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/02/2022",
    "Vencimiento": "07/02/2032",
    "Fecha Primer Cupón": "07/05/2022",
    "Cupón / Spread": 4.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "7/5/2022",
    "7/8/2022",
    "7/11/2022",
    "7/2/2023",
    "7/5/2023",
    "7/8/2023",
    "7/11/2023",
    "7/2/2024",
    "7/5/2024",
    "7/8/2024",
    "7/11/2024",
    "7/2/2025",
    "7/5/2025",
    "7/8/2025",
    "7/11/2025",
    "7/2/2026",
    "7/5/2026",
    "7/8/2026",
    "7/11/2026",
    "7/2/2027",
    "7/5/2027",
    "7/8/2027",
    "7/11/2027",
    "7/2/2028",
    "7/5/2028",
    "7/8/2028",
    "7/11/2028",
    "7/2/2029",
    "7/5/2029",
    "7/8/2029",
    "7/11/2029",
    "7/2/2030",
    "7/5/2030",
    "7/8/2030",
    "7/11/2030",
    "7/2/2031",
    "7/5/2031",
    "7/8/2031",
    "7/11/2031",
    "7/2/2032"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 13 + [5] + [0] + [5] + [0] + [5] + [0] + [5] + [0] + [5] + [0] +
                      [5] + [0] + [5] + [0] + [5] + [0] + [10] + [0] + [10] + [0] + [10] + [0] +
                       [10] + [0] + [10] + [0] + [10]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m60 de la fecha de emisión",
    "Fecha Call": "07/02/2027",
    "Precio Call": {"m60 a m80: 1.02, m81 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento a partir del mes sesenta (60) (inclusive) contado desde la 
                    Fecha de Emisión y Liquidación, la Emisora tendrá el derecho, a su sola opción, de 
                    rescatar las Obligaciones Negociables en su totalidad (pero no en parte), al precio de 
                    rescate de capital (más los intereses devengados y no pagados calculados hasta la 
                    fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
                    Obligaciones Negociables) que surge del siguiente detalle:
                        A partir del sexagésimo mes contado desde la Fecha de Emisión y Liquidación hasta el octogésimo mes contado 
                        desde la Fecha de Emisión y Liquidación: 102%
                        A partir del octogésimo primer mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha 
                        de Vencimiento: 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNICO/Y/MPMAE-RES-ON%20EF%20PAE%20CLASE%2017%20-%20Aviso%20de%20Resultados-03-02-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNICO/Y/MPMAE-ANU-ON%20EF%20PAE%20CLASE%2017%20-%20Suplemento%20de%20Precio-01-02-2022.pdf"""
}
MSSBO = {
    "Nombre Security": "ON MSU S.A. Serie XI Vto. 16 11 2026",
    "Código": "MSSBO",
    "ISIN": "ARLEDE5600D8",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/11/2022",
    "Vencimiento": "14/11/2026",
    "Fecha Primer Cupón": "14/02/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "14/2/2023",
    "14/5/2023",
    "14/8/2023",
    "14/11/2023",
    "14/2/2024",
    "14/5/2024",
    "14/8/2024",
    "14/11/2024",
    "14/2/2025",
    "14/5/2025",
    "14/8/2025",
    "14/11/2025",
    "14/2/2026",
    "14/5/2026",
    "14/8/2026",
    "14/11/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33.33] + [0] * 3 + [66.67]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m19 de la fecha de emisión",
    "Fecha Call": "14/06/2024",
    "Precio Call": {"m19 a m30: 1.03, m31 a m40: 1.02, m41 en adelante: 1.01"},  # Precio Call
    "Comentarios": """la Emisora podrá, a su sola opción, rescatar desde el décimo noveno mes (inclusive) de la Fecha de Emisión y Liquidación las Obligaciones Negociables Serie XI en su 
totalidad, pero no parcialmente, al precio de rescate del capital pendiente de pago que surge del 
siguiente detalle (con más los intereses devengados y no pagados calculados hasta la fecha de 
rescate, los montos adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables
Serie XI):
                Desde el décimo noveno mes (19°) (inclusive) de la Fecha de Emisión y Liquidación hasta el trigésimo (30°) 
                mes (inclusive) desde la Fecha de Emisión y Liquidación: 103%
                A partir del trigésimo primer (31°) mes (inclusive) desde la Fecha de Emisión y Liquidación hasta el 
                cuadragésimo (40°) mes (inclusive) desde la Fecha de Emisión y Liquidación: 102%
                Luego del cuadragésimo (40°) mes (exclusive) desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha de Vencimiento de las Obligaciones 
                Negociables Serie XI: 101""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MSSBO/Y/MPMAE-RES-ON%20MSU%20%20Serie%20XI%20y%20XII%20-%20Aviso%20de%20resultados%2010-11-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MSSBO/Y/MPMAE-ANU-ON%20MSU%20Serie%20XI%20y%20XII%20Suplemento%20de%20Prospecto%204-11-22.pdf"""
}
PNJCO = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 18 Vto 07 02 2027",
    "Código": "PNJCO",
    "ISIN": "ARAXIO5600P3",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/02/2022",
    "Vencimiento": "07/02/2027",
    "Fecha Primer Cupón": "07/05/2022",
    "Cupón / Spread": 1.25, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "7/5/2022",
    "7/8/2022",
    "7/11/2022",
    "7/2/2023",
    "7/5/2023",
    "7/8/2023",
    "7/11/2023",
    "7/2/2024",
    "7/5/2024",
    "7/8/2024",
    "7/11/2024",
    "7/2/2025",
    "7/5/2025",
    "7/8/2025",
    "7/11/2025",
    "7/2/2026",
    "7/5/2026",
    "7/8/2026",
    "7/11/2026",
    "7/2/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "07/02/2022",
    "Precio Call": {"m1 a m20: 1.03, m21 a m40: 1.02, m41 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de rescatar las Obligaciones Negociables en su totalidad (pero no en parte), al precio de rescate de 
                capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
                Obligaciones Negociables) que surge del siguiente detalle:
                Desde la Fecha de Emisión y Liquidación hasta elvigésimo mes contado desde la Fecha de Emisión y Liquidación: 103%
                A partir del vigésimo primer mes contado desde la Fecha de Emisión y Liquidación hasta el cuadragésimo mes contado desde la Fecha de Emisión y Liquidación: 102%
                A partir del cuadragésimo primer mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha de Vencimiento: 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNJCO/Y/MPMAE-RES-ON%20EF%20PAE%20CLASE%2018%20-%20Aviso%20de%20Resultados-03-02-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNJCO/Y/MPMAE-ANU-ON%20EF%20PAE%20CLASE%2018%20-%20Suplemento%20de%20Precio-01-02-2022.pdf"""
}
PECHO = {
    "Nombre Security": "ON Petrolera Aconcagua Energia S.A.Clase 16 Vto 28 10 2028",
    "Código": "PECHO",
    "ISIN": "AR0553485654",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/10/2024",
    "Vencimiento": "28/09/2028",
    "Fecha Primer Cupón": "28/01/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/01/2025", "28/04/2025", "28/07/2025", "28/10/2025", "28/01/2026", "28/04/2026", "28/07/2026", 
 "28/10/2026", "28/01/2027", "28/04/2027", "28/07/2027", "28/10/2027", "28/01/2028", "28/04/2028", "28/07/2028", "28/10/2028"], # Lista de fechas como ejemplo
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNJCO/Y/MPMAE-RES-ON%20EF%20PAE%20CLASE%2018%20-%20Aviso%20de%20Resultados-03-02-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNJCO/Y/MPMAE-ANU-ON%20EF%20PAE%20CLASE%2018%20-%20Suplemento%20de%20Precio-01-02-2022.pdf"""
}
PNZCO = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 33 Vto 04 07 2027",
    "Código": "PNZCO",
    "ISIN": "PNZCO",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/07/2024",
    "Vencimiento": "04/07/2027",
    "Fecha Primer Cupón": "04/10/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "4/7/2024",
    "4/10/2024",
    "4/1/2025",
    "4/4/2025",
    "4/7/2025",
    "4/10/2025",
    "4/1/2026",
    "4/4/2026",
    "4/7/2026",
    "4/10/2026",
    "4/1/2027",
    "4/4/2027",
    "4/7/2027"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "04/07/2024",
    "Precio Call": {"m1 a m12: 1.03, m13 a m24: 1.02, m25 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de rescatar las
Obligaciones Negociables en su totalidad (pero no en parte), al precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de
rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables) que surge del siguiente detalle:
Desde la Fecha de Emisión y Liquidación hasta el décimo segundo mes contado desde la Fecha de Emisión y
Liquidación: 103%, 
A partir del décimo tercer mes contado desde la Fecha de Emisión y Liquidación hasta el vigésimo cuarto mes
contado desde la Fecha de Emisión y Liquidación: 102%,
A partir del vigésimo quinto mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha
de Vencimiento: 101%""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/5771420f-5b97-40e4-9d22-6cd6a375a7e5#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/a63f43fa-9ac2-4bd3-9df5-f2869aec9ec6#"""
}
PNFCO = {
    "Nombre Security": "ON Pan American Energy S.L. Clase 14 Vto 12 07 2026",
    "Código": "PNFCO",
    "ISIN": "ARAXIO5600M0",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/7/2021",
    "Vencimiento": "12/7/2026",
    "Fecha Primer Cupón": "12/10/2021",
    "Cupón / Spread": 3.69, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "12/10/2021",
    "12/1/2022",
    "12/4/2022",
    "12/7/2022",
    "12/10/2022",
    "12/1/2023",
    "12/4/2023",
    "12/7/2023",
    "12/10/2023",
    "12/1/2024",
    "12/4/2024",
    "12/7/2024",
    "12/10/2024",
    "12/1/2025",
    "12/4/2025",
    "12/7/2025",
    "12/10/2025",
    "12/1/2026",
    "12/4/2026",
    "12/7/2026"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [20] + [0] + [20] + [0] + [20] + [0] + [20] + [0] + [20]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m60 de la fecha de emisión",
    "Fecha Call": "12/07/2026",
    "Precio Call": {"m60 a m80: 1.02, m81 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento a partir del mes sesenta (60) (inclusive) contado desde la 
                    Fecha de Emisión y Liquidación, la Emisora tendrá el derecho, a su sola opción, de 
                    rescatar las Obligaciones Negociables Clase 13 en su totalidad (pero no en parte), al 
                    precio de rescate de capital (más los intereses devengados y no pagados calculados
                    hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada
                    bajo las Obligaciones Negociables Clase 13) que surge del siguiente detalle:
                        A partir del sexagésimo mes contado desde la Fecha de Emisión y Liquidación hasta el octogésimo mes contado
                        desde la Fecha de Emisión y Liquidación: 102%
                        A partir del octogésimo primer mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior a la 
                        Fecha de Vencimiento de las Obligaciones Negociables Clase 13: 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNFCO/Y/MPMAE-RES-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2013-14-%20Aviso%20de%20Resultados%2007-07-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNFCO/Y/MPMAE-ANU-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2013-14-%20Suplemento%20de%20Prospecto.pdf"""
}
DRS9O = {
    "Nombre Security": "ON Red Surcos S.A Clase IX Vto. 29 09 2025",
    "Código": "DRS9O",
    "ISIN": "ARREDS5600E3",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/09/2022",
    "Vencimiento": "29/09/2025",
    "Fecha Primer Cupón": "29/12/2022",
    "Cupón / Spread": 1.39, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "29/12/2022",
    "29/3/2023",
    "29/6/2023",
    "29/9/2023",
    "29/12/2023",
    "29/3/2024",
    "29/6/2024",
    "29/9/2024",
    "29/12/2024",
    "29/3/2025",
    "29/6/2025",
    "29/9/2025"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [33.33] * 2 + [33.34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m33 de la fecha de emisión",
    "Fecha Call": "29/06/2025",
    "Precio Call": {"m33 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Sociedad podrá reembolsar anticipadamente la totalidad o una 
                    parte de las ON Serie IX VS una vez transcurridos 33 (treinta y tres) meses contados desde la Fecha de Emisión y Liquidación. El 
importe a pagar a los obligacionistas será el valor de reembolso, que resultará de sumar al Valor Nominal de Reembolso de las ON Serie 
IX VS (conforme dicho término se define más adelante)- total o parcial, según el caso – los intereses devengados conforme a las 
condiciones de emisión hasta el día del efectivo pago del valor de reembolso (inclusive). La Sociedad garantizará la igualdad de trato 
entre los tenedores de ON Serie IX VS.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/DRS9O/Y/MPMAE-RES-ON%20RED%20SURCOS%20SERIE%209-%20Aviso%20de%20Resultados%2027-09-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/DRS9O/Y/MPMAE-ANU-ON%20RED%20SURCOS%20SERIE%209-Suplemento%2021-09-22.pdf"""
}
AER5O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase V Vto. 21 02 2032",
    "Código": "AER5O",
    "ISIN": "ARAEAR560090",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/02/2022",
    "Vencimiento": "21/02/2032",
    "Fecha Primer Cupón": "21/05/2022",
    "Cupón / Spread": 5.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "21/5/2022",
    "21/8/2022",
    "21/11/2022",
    "21/2/2023",
    "21/5/2023",
    "21/8/2023",
    "21/11/2023",
    "21/2/2024",
    "21/5/2024",
    "21/8/2024",
    "21/11/2024",
    "21/2/2025",
    "21/5/2025",
    "21/8/2025",
    "21/11/2025",
    "21/2/2026",
    "21/5/2026",
    "21/8/2026",
    "21/11/2026",
    "21/2/2027",
    "21/5/2027",
    "21/8/2027",
    "21/11/2027",
    "21/2/2028",
    "21/5/2028",
    "21/8/2028",
    "21/11/2028",
    "21/2/2029",
    "21/5/2029",
    "21/8/2029",
    "21/11/2029",
    "21/2/2030",
    "21/5/2030",
    "21/8/2030",
    "21/11/2030",
    "21/2/2031",
    "21/5/2031",
    "21/8/2031",
    "21/11/2031",
    "21/2/2032"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 20 + [5] * 20),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m60 de la fecha de emisión",
    "Fecha Call": "21/02/2027",
    "Precio Call": {"m60 a m72: 1.02, m72 a m84: 1.015, m84 a m96: 1.01 y m97 en adelante: 1.00"},  # Precio Call
    "Comentarios": """En cualquier momento a partir del mes sesenta (60) (inclusive) contado desde la Fecha 
                    de Emisión y Liquidación, la Compañía tendrá el derecho, a su sola opción, de rescatar 
                    las Obligaciones Negociables Clase 5 en su totalidad (pero no en parte), al precio de 
                    rescate de capital (más los intereses devengados y no pagados calculados hasta la 
                    fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
                    Obligaciones Negociables) que surge del siguiente detalle
                        A partir del 60° mes contado desde la fecha de Fecha de Emisión y Liquidación hasta el hasta 
                        el 72° mes contado desde la Fecha de Emisión y Liquidación: 102%
                        A partir del 72° mes contado desde la Fecha de Emisión y Liquidación y hasta el 84° mes contado desde la 
                        Fecha de Emisión y Liquidación: 101.5%
                        A partir del 84° mes contado desde la Fecha de Emisión y Liquidación y hasta el 96° mes desde la Fecha de 
                        Emisión y Liquidación: 101%
                        En adelante: 100%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/AER5O/Y/MPMAE-RES-AEROPUERTOS%20ARGENTINA%202000%20CLASE%205%20y%206%20Aviso_de_Resultados%2017-02-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/AER5O/Y/MPMAE-ANU-ON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%205-6-Suplemento%20de%20Prospecto-14-02-22.pdf"""
}
PEC6O = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Serie VI Vto 14 09 2026",
    "Código": "PEC6O",
    "ISIN": "ARPAEG5600B4",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/09/2023",
    "Vencimiento": "14/09/2026",
    "Fecha Primer Cupón": "14/12/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "14/12/2023",
    "14/3/2024",
    "14/6/2024",
    "14/9/2024",
    "14/12/2024",
    "14/3/2025",
    "14/6/2025",
    "14/9/2025",
    "14/12/2025",
    "14/3/2026",
    "14/6/2026",
    "14/9/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [20] * 5),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PEC6O/Y/MPMAE-RES-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASES%20VI%20Y%20VII-Aviso%20de%20Resultados%2012-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PEC6O/Y/MPMAE-ANU-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASES%20VI%20Y%20VII%20-%20Suplemento%2006-09-2023.pdf"""
}
CWC3O = {
    "Nombre Security": "ON Crown Point Energía Clase III Vto. 10 08 2025",
    "Código": "CWC3O",
    "ISIN": "ARCRPO560032",
    "Calificación": "BBB+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/08/2022",
    "Vencimiento": "10/08/2025",
    "Fecha Primer Cupón": "10/11/2022",
    "Cupón / Spread": 4.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "10/11/2022",
    "10/2/2023",
    "10/5/2023",
    "10/8/2023",
    "10/11/2023",
    "10/2/2024",
    "10/5/2024",
    "10/8/2024",
    "10/11/2024",
    "10/2/2025",
    "10/5/2025",
    "10/8/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [14.29] * 6 + [14.26]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CWC3O/Y/MPMAE-RES-ON%20CROWN%20POINT%20ENERGY%20CLASE%20III-Aviso%20Resultado%2008-08-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CWC3O/Y/MPMAE-ANU-ON%20CROWN%20POINT%20ENERGY%20CLASE%20III-Suplemento%2003-08-22.pdf"""
}
MRCBO = {
    "Nombre Security": "ON GEMSA Clase 11 Vto 12 11 2024",
    "Código": "MRCBO",
    "ISIN": "ARGMCT560090",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/11/2021",
    "Vencimiento": "12/11/2024",
    "Fecha Primer Cupón": "12/02/2022",
    "Cupón / Spread": 6.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "12/2/2022",
    "12/5/2022",
    "12/8/2022",
    "12/11/2022",
    "12/2/2023",
    "12/5/2023",
    "12/8/2023",
    "12/11/2023",
    "12/2/2024",
    "12/5/2024",
    "12/8/2024",
    "12/11/2024"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 8 + [25] * 4),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MRCBO/Y/MPMAE-RES-COEMISION%20ON%20GEMSA-CTR%20CLASE%2011-Aviso%20de%20Resultado%2011-11-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MRCBO/Y/MPMAE-ANU-COEMISION%20ON%20GEMSA-CTR%20CLASES%2011%20Y%2012-Suplemento%2005-11-21.pdf"""
}
PNECO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 13 Vto 12 07 2031",
    "Código": "PNECO",
    "ISIN": "ARAXIO5600L2",
    "Calificación": "Aaa(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/07/2021",
    "Vencimiento": "12/07/2031",
    "Fecha Primer Cupón": "12/10/2021",
    "Cupón / Spread": 5.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "12/10/2021", "12/1/2022", "12/4/2022", "12/7/2022", "12/10/2022", 
    "12/1/2023", "12/4/2023", "12/7/2023", "12/10/2023", "12/1/2024", 
    "12/4/2024", "12/7/2024", "12/10/2024", "12/1/2025", "12/4/2025", 
    "12/7/2025", "12/10/2025", "12/1/2026", "12/4/2026", "12/7/2026", 
    "12/10/2026", "12/1/2027", "12/4/2027", "12/7/2027", "12/10/2027", 
    "12/1/2028", "12/4/2028", "12/7/2028", "12/10/2028", "12/1/2029", 
    "12/4/2029", "12/7/2029", "12/10/2029", "12/1/2030", "12/4/2030", 
    "12/7/2030", "12/10/2030", "12/1/2031", "12/4/2031", "12/7/2031"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 13 + [5] + [0] + [5] + [0] + [5] + [0] + [5] + [0] + [5] + [0] + [5]
                      + [0] + [5] + [0] + [5] + [0] + [10] + [0] + [10] + [0] + [10] + [0] + [10]
                       + [0] + [10] + [0] + [10]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNECO/Y/MPMAE-RES-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2013-14-%20Aviso%20de%20Resultados%2007-07-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNECO/Y/MPMAE-ANU-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2013-14-%20Suplemento%20de%20Prospecto.pdf"""
}
PN40O = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 40 Vto 11 10 2026",
    "Código": "PN40O",
    "ISIN": "AR0351070781",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/04/2025",
    "Vencimiento": "11/10/2026",
    "Fecha Primer Cupón": "11/07/2025",
    "Cupón / Spread": 2., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["11/07/2025", "11/10/2025", "11/01/2026",
    "11/04/2026", "11/07/2026", "11/10/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Rescate total a opción de la Emisora desde la emisión",
    "Fecha Call": "11/04/2025",
    "Precio Call": {"m0 a m9": 1.02, "m10 a m15": 1.01, "m16 en adelante": 1.00},  # Precio Call
    "Comentarios": """En cualquier momento, la Emisora tendrá el derecho, a su sola opción, 
de rescatar las Obligaciones Negociables en su totalidad (pero no en parte), al precio de rescate del capital 
más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y 
cualquier otra suma adeudada bajo las Obligaciones Negociables.

Los precios de rescate serán los siguientes:
- Desde la Fecha de Emisión y Liquidación hasta el noveno mes: 102,00%/ del capital.
- Del mes 10 al mes 15: 101,00%/ del capital.
- Desde el mes 16 hasta el día anterior a la Fecha de Vencimiento: 100,00%/ del capital.""",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
TLCHO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 16 Vto 21 07 2025",
    "Código": "TLCHO",
    "ISIN": "ARTECO5600I1",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "21/07/2023",
    "Vencimiento": "21/07/2025",
    "Fecha Primer Cupón": "21/07/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["21/07/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLCHO/Y/MPMAE-RES-ON%20TELECOM%20ARGENTINA%20Clase%2016%20-%20Aviso%20de%20Resultados%2020-07-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLCHO/Y/MPMAE-ANU-ON%20TELECOM%20ARGENTINA%20CLASE%2016%20%20Suplemento%2018.07.23.pdf"""
}
TLCDO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 12 Vto. 09 03 2027",
    "Código": "TLCDO",
    "ISIN": "ARTECO5600E0",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/03/2022",
    "Vencimiento": "09/03/2027",
    "Fecha Primer Cupón": "09/06/2022",
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/06/2022",
                        "09/09/2022",
                        "09/12/2022",
                        "09/03/2023",
                        "09/06/2023",
                        "09/09/2023",
                        "09/12/2023",
                        "09/03/2024",
                        "09/06/2024",
                        "09/09/2024",
                        "09/12/2024",
                        "09/03/2025",
                        "09/06/2025",
                        "09/09/2025",
                        "09/12/2025",
                        "09/03/2026",
                        "09/06/2026",
                        "09/09/2026",
                        "09/12/2026",
                        "09/03/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLCDO/Y/MPMAE-RES-ON%20TELECOM%20ARGENTINA%20Clases%2012%20y%2013%20%20Aviso%20Resultados%2007-03-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLCDO/Y/MPMAE-ANU-%20ON%20TELECOM%20Suplemento%20Clases%2012%20y%2013%2003-03-2022.pdf"""
}
TLCKO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 19 Vto. 17 11 2026",
    "Código": "TLCKO",
    "ISIN": "AR0849737462",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/11/2023",
    "Vencimiento": "17/11/2026",
    "Fecha Primer Cupón": "17/11/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/11/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """"""
}
TLCLO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 19 Vto 06 06 2026",
    "Código": "TLCLO",
    "ISIN": "AR0731472459",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/06/2024",
    "Vencimiento": "06/06/2026",
    "Fecha Primer Cupón": "06/09/2024",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "6/9/2024",
    "6/12/2024",
    "6/3/2025",
    "6/6/2025",
    "6/9/2025",
    "6/12/2025",
    "6/3/2026",
    "6/6/2026"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLCLO/Y/MPMAE-RES-ON%20TELECOM%20ARGENTINA%20Clase%2020%20-%20Aviso%20de%20Resultados%2004-06-2024.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLCLO/Y/MPMAE-ANU-ON%20TELECOM%20ARGENTINA%20%20Clase%2020%20-%20Suplemento%20de%20Prospecto%2031.05.24.pdf"""
}
CS42O = {
    "Nombre Security": "ON Cresud SA Serie XXI Clase XLII Vto 04 05 2026",
    "Código": "CS42O",
    "ISIN": "ARCRES5600Z0",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "04/10/2023",
    "Vencimiento": "04/10/2026",
    "Fecha Primer Cupón": "04/01/2024",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "4/1/2024",
    "4/4/2024",
    "4/7/2024",
    "4/10/2024",
    "4/1/2025",
    "4/4/2025",
    "4/7/2025",
    "4/10/2025",
    "4/1/2026",
    "4/4/2026",
    "4/7/2026",
    "4/10/2026"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [33] + [0] + [33] + [0] + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CS42O/Y/MPMAE-RES-ON%20CRESUD%20CLASE%2041%20Y%2042%20-Aviso%20de%20Resultados%2029-03-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CS42O/Y/MPMAE-ANU-ON%20CRESUD%20Clase%2041%20y%2042%20%20Suplemento%20Prospecto%2027-03-2023.pdf"""
}
RE3BO = {
    "Nombre Security": "ON Refi Pampa S.A. Clase 3 Serie B Vto 06 12 2025",
    "Código": "RE3BO",
    "ISIN": "ARREFI560048",
    "Calificación": "BBB+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/12/2022",
    "Vencimiento": "06/12/2025",
    "Fecha Primer Cupón": "06/03/2023",
    "Cupón / Spread": 3.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "6/3/2023",
    "6/6/2023",
    "6/9/2023",
    "6/12/2023",
    "6/3/2024",
    "6/6/2024",
    "6/9/2024",
    "6/12/2024",
    "6/3/2025",
    "6/6/2025",
    "6/9/2025",
    "6/12/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 8 + [25] * 4),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/RE3BO/Y/MPMAE-ANU-ON%20REFI%20PAMPA%20CLASE%203-Aviso%20de%20Resultados%2001-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/RE3BO/Y/MPMAE-ANU-ON%20REFI%20PAMPA%20CLASE%203-Suplemento%20de%20Prospecto%2028-11-22.pdf"""
}
RFCBO = {
    "Nombre Security": "ON Agrofina S.A. Clase XI Vto 07 12 2025",
    "Código": "RFCBO",
    "ISIN": "ARAGRF5600F8",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "7/12/2022",
    "Vencimiento": "7/12/2025",
    "Fecha Primer Cupón": "7/3/2023",
    "Cupón / Spread": 3.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "7/3/2023",
    "7/6/2023",
    "7/9/2023",
    "7/12/2023",
    "7/3/2024",
    "7/6/2024",
    "7/9/2024",
    "7/12/2024",
    "7/3/2025",
    "7/6/2025",
    "7/9/2025",
    "7/12/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 6 + [16.66] * 5 + [16.70]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/RFCBO/Y/MPMAE-RES-ON%20AGROFINA%2011-Aviso%20de%20Resultados%205-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/RFCBO/Y/MPMAE-ANU-ON%20AGROFINA%2011-Suplemento%20de%20Prospecto%2029-11-22.pdf"""
}
YFCDO = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase XII Vto 29 08 2026",
    "Código": "YFCDO",
    "ISIN": "ARYPFE5600I1",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/08/2022",
    "Vencimiento": "29/08/2026",
    "Fecha Primer Cupón": "29/08/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/08/2022",
                        "29/11/2022",
                        "28/02/2023",
                        "29/05/2023",
                        "29/08/2023",
                        "29/11/2023",
                        "29/02/2024",
                        "29/05/2024",
                        "29/08/2024",
                        "29/11/2024",
                        "28/02/2025",
                        "29/05/2025",
                        "29/08/2025",
                        "29/11/2025",
                        "28/02/2026",
                        "29/05/2026",
                        "29/08/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 12 + [33.33] + [0] + [33.33] + [0] + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YFCFO/Y/MPMAE-RES-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2014-15%20Aviso%20de%20Resultados%2023-02-2024.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YFCFO/Y/MPMAE-ANU-%20ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2014-15%20%20Suplemento%20de%20Prospecto%2019-02-2024.pdf"""
}
PEC1O = {
    "Nombre Security": "ON Petrolera Aconcagua Energia S.A.Clase I Vto 11 10 2025",
    "Código": "PEC1O",
    "ISIN": "ARPAEG560054",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/10/2022",
    "Vencimiento": "11/10/2025",
    "Fecha Primer Cupón": "29/08/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["11/1/2023", "11/4/2023", "11/7/2023", "11/10/2023",
                        "11/1/2024", "11/4/2024", "11/7/2024", "11/10/2024",
                        "11/1/2025", "11/4/2025", "11/7/2025", "11/10/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [14] * 6 + [16]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PEC1O/Y/MPMAE-RES-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%20I-Aviso%20Resultado%2005-10-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PEC1O/Y/MPMAE-ANU-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%20I-Suplemento%2029-09-22.pdf"""
}
YFCAO = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase X Vto 03 02 2032",
    "Código": "YFCAO",
    "ISIN": "ARYPFE5600G5",
    "Calificación": "Bv2(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/02/2023",
    "Vencimiento": "03/02/2032",
    "Fecha Primer Cupón": "03/05/2023",
    "Cupón / Spread": 5.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["3/8/2023", "3/2/2024", "3/8/2024", "3/2/2025", "3/8/2025",
                        "3/2/2026", "3/8/2026", "3/2/2027", "3/8/2027", "3/2/2028",
                        "3/8/2028", "3/2/2029", "3/8/2029", "3/2/2030", "3/8/2030",
                        "3/2/2031", "3/8/2031", "3/2/2032"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 8 + [10] * 10),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YFCAO/Y/MPMAE-RES-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2010.-Aviso%20de%20Resultados-02-02-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YFCAO/Y/MPMAE-ANU-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2010-Suplemento%20Prospecto-28-01-22.pdf"""
}
FOS3O = {
    "Nombre Security": "ON Futuros y Opciones S.A. Serie III Vto 27 04 2026",
    "Código": "FOS3O",
    "ISIN": "ARFUOP560034",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "25/04/2023",
    "Vencimiento": "25/04/2026",
    "Fecha Primer Cupón": "25/07/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["25/12/2025", "25/04/2026"], # Lista de fechas como ejemplo
    "Amortización": ([50] + [50]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YFCAO/Y/MPMAE-RES-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2010.-Aviso%20de%20Resultados-02-02-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YFCAO/Y/MPMAE-ANU-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2010-Suplemento%20Prospecto-28-01-22.pdf"""
}
PQCHO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase H Vto 17 12 2024",
    "Código": "PQCHO",
    "ISIN": "ARPETQ5600E7",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/12/2021",
    "Vencimiento": "17/12/2024",
    "Fecha Primer Cupón": "17/03/2022",
    "Cupón / Spread": 0.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["17/3/2022", "17/6/2022", "17/9/2022", "17/12/2022",
    "17/3/2023", "17/6/2023", "17/9/2023", "17/12/2023", "17/3/2024", "17/6/2024", "17/9/2024", "17/12/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PQCHO/Y/MPMAE-RES-ON%20EF%20PCR%20CLASE%20H-Aviso%20de%20Resultado%2014-12-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PQCHO/Y/MPMAE-ANU-ON%20EF%20PCR%20CLASE%20H-Suplemento%2013-12-21.pdf"""
}
PQCQO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase Q Vto 16 07 2027",
    "Código": "PQCQO",
    "ISIN": "AR0761744397",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/07/2024",
    "Vencimiento": "16/07/2027",
    "Fecha Primer Cupón": "16/10/2024",
    "Cupón / Spread": 1.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "16/10/2024",
    "16/01/2025",
    "16/04/2025",
    "16/07/2025",
    "16/10/2025",
    "16/01/2026",
    "16/04/2026",
    "16/07/2026",
    "16/10/2026",
    "16/01/2027",
    "16/04/2027",
    "16/07/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/mercado-primario/licitaciones/LicitacionesAdjuntosByName/6812/MPMAE-ANU-ON%20EF%20PCR%20CLASE%20Q-Suplemento%2011-07-24.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/mercado-primario/licitaciones/LicitacionesAdjuntosByName/6812/MPMAE-RES-ON%20EF%20PCR%20CLASE%20Q-Aviso%20de%20Resultado%2012-07-24.pdf"""
}
PQCOO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A Clase O Vto 22 07 2027",
    "Código": "PQCOO",
    "ISIN": "ARPETQ5600N8",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "22/09/2023",
    "Vencimiento": "22/09/2027",
    "Fecha Primer Cupón": "22/12/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["22/12/2023", "22/3/2024", "22/6/2024", "22/9/2024", 
    "22/12/2024", "22/3/2025", "22/6/2025", "22/9/2025", 
    "22/12/2025", "22/3/2026", "22/6/2026", "22/9/2026", 
    "22/12/2026", "22/3/2027", "22/6/2027", "22/9/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PQCOO/Y/MPMAE-RES-ON%20EF%20PCR%20CLASE%20O-Aviso%20de%20Resultado%2020-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PQCOO/Y/MPMAE-ANU-ON%20EF%20PCR%20CLASE%20O-Suplemento%2019-09-23.pdf"""
}
PEC2O = {
    "Nombre Security": "ON Petrolera Aconcagua Energia S.A.Clase II Vto 23 01 2026",
    "Código": "PEC2O",
    "ISIN": "ARPAEG560062",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/01/2023",
    "Vencimiento": "23/01/2026",
    "Fecha Primer Cupón": "23/04/2023",
    "Cupón / Spread": 5.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/4/2023", "23/7/2023", "23/10/2023", "23/1/2024",
    "23/4/2024", "23/7/2024", "23/10/2024", "23/1/2025",
    "23/4/2025", "23/7/2025", "23/10/2025", "23/1/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [14] * 6 + [16]) ,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PEC2O/Y/MPMAE-RES-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%202-3-Aviso%20de%20Resultado%2019-1-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PEC2O/Y/MPMAE-ANU-ON%20PETROLERA%20ACONCAGUA%20ENERGIA%20CLASE%201-2-Suplemento%2013-01-23.pdf"""
}
GN35O = {
    "Nombre Security": "ON Genneia S.A. Clase XXXV Vto 23 12 2024",
    "Código": "GN35O",
    "ISIN": "AREMGA5600N6",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/12/2021",
    "Vencimiento": "23/12/2024",
    "Fecha Primer Cupón": "23/03/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/3/2022", "23/6/2022", "23/9/2022", "23/12/2022",
    "23/3/2023", "23/6/2023", "23/9/2023", "23/12/2023",
    "23/3/2024", "23/6/2024", "23/9/2024", "23/12/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/GN35O/Y/MPMAE-RES-SVS%20ON%20EF%20GENNEIA%20CLASE%2035%20Y%2036-Aviso%20de%20Resultado%2021-12-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/GN35O/Y/MPMAE-ANU-SVS%20ON%20EF%20GENNEIA%20%20Clase%2035%20y%2036%20%20Suplemento%20de%20prospecto%2017-12-2021.pdf"""
}
GN42O = {
    "Nombre Security": "ON Genneia S.A. Clase XLII Vto 16 05 2027",
    "Código": "GN42O",
    "ISIN": "AR0329026279",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "16/11/2023",
    "Vencimiento": "16/05/2027",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ['16/11/2023',
                        '16/02/2024',
                        '16/05/2024',
                        '16/08/2024',
                        '16/11/2024',
                        '16/02/2025',
                        '16/05/2025',
                        '16/08/2025',
                        '16/11/2025',
                        '16/02/2026',
                        '16/05/2026',
                        '16/08/2026',
                        '16/11/2026',
                        '16/02/2027',
                        '16/05/2027'], # Lista de fechas como ejemplo
    "Amortización": ([0]*12+[33.3,33.3,33.4]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/GN42O/Y/MPMAE-RES-ON%20SVS%20GENNEIA%20CLASE%2042%20-%20Aviso%20de%20Resultados%2014-11-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/GN42O/Y/MPMAE-ANU-ON%20SVS%20GENNEIA%20CLASE%2042-Suplemento%20de%20Prospecto%2010-11-23.pdf"""
}
PNRCO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 26 Vto 07 08 2028",
    "Código": "PNRCO",
    "ISIN": "ARAXIO5600X7",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/08/2023",
    "Vencimiento": "07/08/2028",
    "Fecha Primer Cupón": "07/11/2023",
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": "A3500", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/11/2023",
                        "07/02/2024",
                        "07/05/2024",
                        "07/08/2024",
                        "07/11/2024",
                        "07/02/2025",
                        "07/05/2025",
                        "07/08/2025",
                        "07/11/2025",
                        "07/02/2026",
                        "07/05/2026",
                        "07/08/2026",
                        "07/11/2026",
                        "07/02/2027",
                        "07/05/2027",
                        "07/08/2027",
                        "07/11/2027",
                        "07/02/2028",
                        "07/05/2028",
                        "07/08/2028"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PNRCO/Y/MPMAE-RES-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2026-Aviso%20de%20Resultados%2003-08-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PNRCO/Y/MPMAE-ANU-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%2026-Suplemento%20de%20Precio%2002-08-23.pdf"""
}
OLC2O = {
    "Nombre Security": "ON Oleoductos del Valle S.A. Clase 2 Vto 09 06 2028",
    "Código": "OLC2O",
    "ISIN": "AROLDV560021",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "09/06/2023",
    "Vencimiento": "09/06/2028",
    "Fecha Primer Cupón": "09/09/2023",
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["09/09/2023",
                        "09/12/2023",
                        "09/03/2024",
                        "09/06/2024",
                        "09/09/2024",
                        "09/12/2024",
                        "09/03/2025",
                        "09/06/2025",
                        "09/09/2025",
                        "09/12/2025",
                        "09/03/2026",
                        "09/06/2026",
                        "09/09/2026",
                        "09/12/2026",
                        "09/03/2027",
                        "09/06/2027",
                        "09/09/2027",
                        "09/12/2027",
                        "09/03/2028",
                        "09/06/2028"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/OLC2O/Y/MPMAE-RES-ON%20OL.%20DEL%20VALLE%20CLASE%201%20AD%20Y%20CLASE%202-Aviso%20de%20Resultados%2007-06-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/OLC2O/Y/MPMAE-ANU-ON%20OL.%20DEL%20VALLE%20CLASE%201%20AD%20Y%20CLASE%202-Suplemento%20de%20Prospecto%2005-06-2023.pdf"""
}
OLC4O = {
    "Nombre Security": "ON Oleoductos del Valle S.A. Clase 4 Vto 14 06 2028",
    "Código": "OLC4O",
    "ISIN": "AR0909041870",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/06/2024",
    "Vencimiento": "14/06/2026",
    "Fecha Primer Cupón": "14/12/2024",
    "Cupón / Spread": 3., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["14/12/2024",
                        "14/03/2025",
                        "14/06/2025",
                        "14/09/2025",
                        "14/12/2025",
                        "14/03/2026",
                        "14/06/2026",
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.macro.com.ar/macrosecurities/DownloadDoc?assetId=1580936569263&labelDescarga=Aviso%20de%20Resultados""",
    "Suplemento Prospecto": """https://www.macro.com.ar/macrosecurities/DownloadDoc?assetId=1580936538992&labelDescarga=Suplemento"""
}
PQCKO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase K Vto 07 12 2026",
    "Código": "PQCKO",
    "ISIN": "ARPETQ5600H0",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/12/2022",
    "Vencimiento": "07/12/2026",
    "Fecha Primer Cupón": "07/03/2023",
    "Cupón / Spread": 0.5, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/03/2023",
                        "07/06/2023", 
                        "07/09/2023", 
                        "07/12/2023",
                        "07/03/2024",
                        "07/06/2024",
                        "07/09/2024",
                        "07/12/2024",
                        "07/03/2025",
                        "07/06/2025",
                        "07/09/2025",
                        "07/12/2025",
                        "07/03/2026",
                        "07/06/2026",
                        "07/09/2026", 
                        "07/12/2026",
                        ], # Lista de fechas como ejemplo
    "Amortización": ([0] * 11 + [33.33] + [0] * 3 + [66.67]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PQCKO/Y/MPMAE-RES-ON%20EF%20PCR%20CLASE%20K-%20Aviso%20de%20Resultado%2005-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PQCKO/Y/MPMAE-ANU-ON%20EF%20PCR%20CLASE%20K-Suplemento%2001-12-22.pdf"""
}
PN7CO = {
    "Nombre Security": "ON Pan American Energy Clase VII Vto 19 11 2025",
    "Código": "PN7CO",
    "ISIN": "ARAXIO5600E7",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "19/11/2020",
    "Vencimiento": "19/11/2025",
    "Fecha Primer Cupón": "19/02/2021",
    "Cupón / Spread": 4.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "19/2/2021",
    "19/5/2021",
    "19/8/2021",
    "19/11/2021",
    "19/2/2022",
    "19/5/2022",
    "19/8/2022",
    "19/11/2022",
    "19/2/2023",
    "19/5/2023",
    "19/8/2023",
    "19/11/2023",
    "19/2/2024",
    "19/5/2024",
    "19/8/2024",
    "19/11/2024",
    "19/2/2025",
    "19/5/2025",
    "19/8/2025",
    "19/11/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "19/11/2020",
    "Precio Call": {"m1 a m20: 1.03, m19 a m40: 1.02 y m41 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de rescatar las Obligaciones Negociables Clase 7 Adicionales en su totalidad (pero no en parte),
                al precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma 
                adeudada bajo las Obligaciones Negociables Clase 7 Adicionales) que surge del siguiente detalle:
                Desde la Fecha de Emisión y Liquidación hasta el 19 de julio de 2022: 103%
                A partir del 20 de julio de 2022 hasta el 19 de marzo de 2024: 102%
                A partir del 20 de marzo de 2024 y hasta el día anterior a la Fecha de Vencimiento. 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PN7CO/Y/MPMAE-RES-ON%20EF%20PAN%20AMERICAN%20ENERGY%20CLASE%207-Aviso%20de%20Resultados%2017-11-20.pdf""",
    "Suplemento Prospecto": """https://www.bancoprovincia.com.ar/CDN/Get/Suple_PAE_7"""
}
YMCMO = {
    "Nombre Security": "ON YPF S.A. Clase XXI Vto 10 01 2026",
    "Código": "YMCMO",
    "ISIN": "ARYPFS5601S8",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/1/2023",
    "Vencimiento": "10/1/2026",
    "Fecha Primer Cupón": "10/4/2023",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "10/4/2023",
    "10/7/2023",
    "10/10/2023",
    "10/1/2024",
    "10/4/2024",
    "10/7/2024",
    "10/10/2024",
    "10/1/2025",
    "10/4/2025",
    "10/7/2025",
    "10/10/2025",
    "10/1/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 desde la fecha de emisión",
    "Fecha Call": "10/7/2024",
    "Precio Call": {"m18 a m23: 1.02, m24 a m29: 1.01 y m30 en adelante: 1.01"},  # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la totalidad o una parte 
de las Obligaciones Negociables Clase XXI que se encuentren en circulación en cualquier 
momento, a partir del mes dieciocho (18) (inclusive) contado desde la Fecha de Emisión y 
Liquidación, al precio de rescate de capital (más los intereses devengados y no pagados 
calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo 
las Obligaciones Negociables de las Obligaciones Negociables Clase XXI) que surge del 
siguiente detalle:
A partir del décimo octavo (18°) mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior al vigésimo cuarto (24°) 
mes contado desde la Fecha de Emisión y Liquidación: 102%
A partir del vigésimo cuarto (24°) mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior al trigésimo (30°) mes 
contado desde la Fecha de Emisión y Liquidación: 101%
A partir del trigésimo (30°) mes contado desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha de Vencimiento de las 
Obligaciones Negociables Clase XXI: 100%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YMCMO/Y/MPMAE-RES-ON%20EF%20YPF%20CLASE%2021-22%20%20-%20Aviso%20de%20Resultados%2006-01-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YMCMO/Y/MPMAE-ANU-ON%20EF%20YPF%20CLASE%20YPF%2021-22%20-%20Suplemento%20de%20Precio%2003-01-2022.pdf"""
}
YMCWO = {
    "Nombre Security": "ON YPF S.A. Clase XXX Vto 01 07 2026",
    "Código": "YMCWO",
    "ISIN": "AR0132676112",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "01/07/2024",
    "Vencimiento": "01/07/2026",
    "Fecha Primer Cupón": "01/10/2024",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "01/10/2024",
    "01/01/2025",
    "01/04/2025",
    "01/07/2025",
    "01/10/2025",
    "01/01/2026",
    "01/04/2026",
    "01/07/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 desde la fecha de emisión",
    "Fecha Call": "01/04/2026",
    "Precio Call": {"m21 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la
                    totalidad o una parte de las Obligaciones Negociables Clase XXX que se encuentren en circulación en cualquier momento, a partir del mes 21 (inclusive)
                    contado desde la Fecha de Emisión y Liquidación, al precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate,
los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXX) de 100%.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/e54068de-9a46-45c3-bfde-37b28fa1f826#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/863d34d7-d00c-409a-8424-bf5a9e5708a3#"""
}
OTS1O = {
    "Nombre Security": "ON Oil Tanking EBYTEM S.A. Serie I Vto 03 03 2026",
    "Código": "OTS1O",
    "ISIN": "AROILT560012",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/03/2023",
    "Vencimiento": "03/03/2026",
    "Fecha Primer Cupón": "03/03/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["03/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad desde la fecha de emisión",
    "Fecha Call": "03/03/2023",
    "Precio Call": {"m1 a m12: 1.03, m13 a m24: 1.02 y m25 en adelante: 1.01"},  # Precio Call
    "Comentarios": """En cualquier momento, la Compañía tendrá el derecho, a su sola opción, de rescatar las Obligaciones Negociables Serie I 
                    en su totalidad (pero no en parte), al precio de rescate de capital (más los intereses devengados y no pagados 
                    calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones 
                    Negociables Serie I) que surge del siguiente detalle: 
                    Desde la Fecha de Emisión y Liquidación hasta el doceavo mes (12º) desde la Fecha de Emisión y liquidación: 103% 
                    Luego del doceavo mes (12º) desde la Fecha de Emisión y Liquidación y hasta el vigésimo cuarto (24º) mes desde la Fecha de Emisión y Liquidación: 102%
                    Luego del vigésimo cuarto (24º) mes desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha de 
                    Vencimiento de las Obligaciones Negociables: 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/OTS1O/Y/MPMAE-RES-ON%20OILTANKING%20SERIE%201-Aviso%20de%20Resultado%2001-03-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/OTS1O/Y/MPMAE-ANU-ON%20OILTANKING%20SERIE%201-Suplemento%2024-02-23.pdf"""
}
VSCKO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XIX Vto 03 03 2028",
    "Código": "VSCKO",
    "ISIN": "AROILG5600J8",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/03/2023",
    "Vencimiento": "03/03/2028",
    "Fecha Primer Cupón": "03/06/2023",
    "Cupón / Spread": 1.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "3/6/2023",
    "3/9/2023",
    "3/12/2023",
    "3/3/2024",
    "3/6/2024",
    "3/9/2024",
    "3/12/2024",
    "3/3/2025",
    "3/6/2025",
    "3/9/2025",
    "3/12/2025",
    "3/3/2026",
    "3/6/2026",
    "3/9/2026",
    "3/12/2026",
    "3/3/2027",
    "3/6/2027",
    "3/9/2027",
    "3/12/2027",
    "3/3/2028"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "03/03/2023",
    "Precio Call": {"m1 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con 
la normativa aplicable en dicha oportunidad, rescatar anticipadamente la 
totalidad o una parte de las Obligaciones Negociables Clase XIX que se 
encuentren en circulación, en cualquier momento desde la Fecha de 
Emisión y Liquidación, al valor nominal con más los intereses devengados
calculados aplicando el Tipo de Cambio Aplicable hasta la fecha de pago 
del valor de rescate(el “Valor del Rescate”).""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCKO/Y/MPMAE-RES-ON%20VISTA%20ENERGY%20CLASE%2019-%20Aviso%20de%20Resultados%2001-03-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCKO/Y/MPAME-ANU-%20ON%20VISTA%20ENERGY%20CLASE%2019%20-%20Suplemento%20de%20Prospecto%2027-02-2023.pdf"""
}
VSCMO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXI Vto 11 08 2028",
    "Código": "VSCMO",
    "ISIN": "AROILG5600L4",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "11/08/2023",
    "Vencimiento": "11/08/2028",
    "Fecha Primer Cupón": "11/11/2023",
    "Cupón / Spread": 0.99, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "11/11/2023",
    "11/2/2024",
    "11/5/2024",
    "11/8/2024",
    "11/11/2024",
    "11/2/2025",
    "11/5/2025",
    "11/8/2025",
    "11/11/2025",
    "11/2/2026",
    "11/5/2026",
    "11/8/2026",
    "11/11/2026",
    "11/2/2027",
    "11/5/2027",
    "11/8/2027",
    "11/11/2027",
    "11/2/2028",
    "11/5/2028",
    "11/8/2028"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m19 desde la fecha de emisión",
    "Fecha Call": "11/03/2025",
    "Precio Call": {"m19 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora no podrá rescatar las Obligaciones Negociables Clase XXI hasta el décimo octavo (18) mes (inclusive) desde la Fecha de Emisión y 
                Liquidación. A partir del décimo noveno (19) mes (inclusive) desde la Fecha de Emisión y Liquidación, la Emisora podrá, en la medida en que sea permitido de 
                conformidad con la normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables 
                Clase XXI que se encuentren en circulación, al valor nominal con más los intereses devengados calculados aplicando el Tipo de Cambio Aplicable hasta la fecha de pago del valor de rescate (el “Valor de Rescate”).""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCMO/Y/MPMAE-RES-ON%20VISTA%20ENERGY%20CLASE%2021-%20Aviso%20de%20Resultados%2009-08-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCMO/Y/MPMAE-ANU-ON%20VISTA%20ENERGY%20%20CLASE%2021-%20Suplemento%20de%20Prospecto%2007-08-23.pdf"""
}
RZ7BO = {
    "Nombre Security": "ON Rizobacter Argentina SA Serie VII Clase B 30 12 2024",
    "Código": "RZ7BO",
    "ISIN": "ARRIAR5600E2",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/12/2021",
    "Vencimiento": "28/12/2024",
    "Fecha Primer Cupón": "28/03/2022",
    "Cupón / Spread": 1.49, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/3/2022",
    "28/6/2022",
    "28/9/2022",
    "28/12/2022",
    "28/3/2023",
    "28/6/2023",
    "28/9/2023",
    "28/12/2023",
    "28/3/2024",
    "28/6/2024",
    "28/9/2024",
    "28/12/2024"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir desde la fecha de emisión",
    "Fecha Call": "28/12/2021",
    "Precio Call": {"m1 a m12: 1.03, m13 a m24: 1.02, m25 en adelante: 1.01"},  # Precio Call
    "Comentarios": """La Sociedad podrá reembolsar anticipadamente la totalidad o una parte de las Obligaciones Negociables Serie VII Clase B. El importe a pagar 
                    a los obligacionistas será el valor de reembolso, que resultará de sumar al Valor Nominal de Reembolso de las ON Serie VII Clase B (conforme 
                    dicho término se define más adelante) - total o parcial, según el caso – los intereses devengados conforme a las condiciones de emisión hasta el día de pago del valor de reembolso.
                    El “Valor Nominal de Reembolso de las ON Serie VII Clase B” será a un precio de: a) U$S 1,03 (Dólares uno coma cero tres) por cada U$S 1 (Dólares uno), en caso de que la Emisora decida realizar el reembolso 
                    en el plazo entre la Fecha de Emisión y Liquidación hasta cumplidos los 12 meses; 
                    b) U$S 1,02 (Dólares uno coma cero dos) por cada U$S 1 (Dólares uno) en caso en que la Emisora decida realizar el reembolso en el plazo que comienza a partir de cumplidos los 12 meses desde la Fecha de Emisión y Liquidación hasta cumplidos los 24 meses; 
                    y c) de U$S 1,01 (Dólares uno coma cero uno) por cada U$S 1 (Dólares uno) en caso 
                    de que la Emisora decida realizar el reembolso en el plazo que comienza a partir de cumplidos los 24 meses desde la Fecha de Emisión y 
                    Liquidación hasta la Fecha de Vencimiento de las ON Serie VII Clase B.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/RZ7BO/Y/MPMAE-RES-ON%20RIZOBACTER%20SERIE%207-Aviso%20de%20Resultado%2022-12-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/RZ7BO/Y/MPMAE-ANU-ON%20RIZOBACTER%20SERIE%207-Suplemento%20de%20Prospecto%2020-12-21.pdf"""
}
VSCBO = {
    "Nombre Security": "ON Vista OIL & Gas Argentina S.A.U Clase XI Vto 27 08 2025",
    "Código": "VSCBO",
    "ISIN": "AROILG5600B5",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/08/2021",
    "Vencimiento": "27/08/2025",
    "Fecha Primer Cupón": "27/11/2021",
    "Cupón / Spread": 3.48, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "27/11/2021",
    "27/2/2022",
    "27/5/2022",
    "27/8/2022",
    "27/11/2022",
    "27/2/2023",
    "27/5/2023",
    "27/8/2023",
    "27/11/2023",
    "27/2/2024",
    "27/5/2024",
    "27/8/2024",
    "27/11/2024",
    "27/2/2025",
    "27/5/2025",
    "27/8/2025"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir desde la fecha de emisión",
    "Fecha Call": "27/08/2021",
    "Precio Call": {"m1 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Sociedad podrá rescatar anticipadamente la totalidad o una parte de las 
                Obligaciones Negociables Clase XI que se encuentren en circulación, en cualquier momento desde la Fecha de Emisión y Liquidación, al valor 
                nominal con más los intereses devengados hasta la fecha de pago del valor de rescate.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCBO/Y/MPMAE-RES-VISTA%20OIL%20Y%20GAS%20ARG%20CLASE%2011-12%20Aviso%20de%20Resultados%2025-08-21-.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCBO/Y/MPMAE-ANU-ON%20VISTA%20OIL%20Y%20GAS%20ARG%20CLASE%2011%20Y%2012%20Suplemento%20Prospecto%2020-08-2021.pdf"""
}
SNS9O = {
    "Nombre Security": "ON San Miguel A.G.I.C.I. Y F. Serie IX Vto. 26 06 2025",
    "Código": "SNS9O",
    "ISIN": "ARSMIG5600F5",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "26/06/2023",
    "Vencimiento": "26/06/2025",
    "Fecha Primer Cupón": "26/09/2023",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["26/9/2023",
                        "26/12/2023",
                        "26/3/2024",
                        "26/6/2024",
                        "26/9/2024",
                        "26/12/2024",
                        "26/3/2025", 
                        "26/6/2025",
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/SNS9O/Y/MPMAE-RES-ON%20SAN%20MIGUEL%20SERIE%209%20ADICIONAL-Aviso%20de%20Resultado%2028-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/SNS9O/Y/MPMAE-ANU-ON%20SAN%20MIGUEL%20SERIE%209-Suplemento%2014-06-23.pdf"""
}
SNAAO = {
    "Nombre Security": "ON San Miguel A.G.I.C.I. Y F. Serie X Clase A Vto. 29 07 2026",
    "Código": "SNAAO",
    "ISIN": "AR0682053886",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/07/2024",
    "Vencimiento": "29/07/2026",
    "Fecha Primer Cupón": "29/10/2024",
    "Cupón / Spread": 7., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/10/2024",
                        "29/01/2025",
                        "29/04/2025",
                        "29/07/2025",
                        "29/10/2025",
                        "29/01/2026",
                        "29/04/2026", 
                        "29/07/2026",], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/SNAAO/Y/MPMAE-RES-ON%20SAN%20MIGUEL%20SERIE%2010%20-%20Aviso%20de%20Resultados%2025-07-2024.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/SNAAO/Y/MPMAE-ANU-ON%20SAN%20MIGUEL%20SERIE%2010-Suplemento%20de%20Prospecto%2019-07-24.pdf"""
}
SNS8O = {
    "Nombre Security": "ON San Miguel Serie VIII Vto. 28 11 2024",
    "Código": "SNS8O",
    "ISIN": "ARSMIG5600E8",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/11/2022",
    "Vencimiento": "28/11/2024",
    "Fecha Primer Cupón": "28/02/2023",
    "Cupón / Spread": 3.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["28/2/2023",
                        "28/5/2023",
                        "28/8/2023",
                        "28/11/2023",
                        "28/2/2024",
                        "28/5/2024",
                        "28/8/2024",
                        "28/11/2024",
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/SNS8O/Y/MPMAE-RES-ON%20SA%20SAN%20MIGUEL%20SERIE%208-%20Aviso%20de%20resultados%2024-11-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/SNS8O/Y/MPMAE-ANU-ON%20SA%20SAN%20MIGUEL%20SERIE%208%20Suplemento%20%2017-11-2022.pdf"""
}
GN44O = {
    "Nombre Security": "ON Genneia S.A. Clase XLIV Vto 09 03 2026",
    "Código": "GN44O",
    "ISIN": "AR0200051115",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/03/2024",
    "Vencimiento": "08/03/2026",
    "Fecha Primer Cupón": "08/06/2024",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["8/6/2024",
    "8/9/2024",
    "8/12/2024",
    "8/3/2025",
    "8/6/2025",
    "8/9/2025",
    "8/12/2025",
    "8/3/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/GN44O/Y/MPMAE-RES-ON%20EF%20Genneia%20Clase%20XLIII%20y%20XLIV-%20Aviso%20de%20Resultados%2006-03-2024.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/GN44O/Y/MPMAE-ANU-ON%20EF%20Genneia%20Clases%20XLIII%20y%20XLIV%20Suplemento%2001-03-2024.pdf"""
}
GN46O = {
    "Nombre Security": "ON Genneia S.A. Clase XLVI Vto 09 03 2026",
    "Código": "GN46O",
    "ISIN": "GN46O",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/06/2024",
    "Vencimiento": "27/06/2026",
    "Fecha Primer Cupón": "27/09/2024",
    "Cupón / Spread": 2., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "27/9/2024",
    "27/12/2024",
    "27/3/2025",
    "27/6/2025",
    "27/9/2025",
    "27/12/2025",
    "27/3/2026",
    "27/6/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/7741e6ad-99e7-401b-9c9e-4e82fb0acc2f#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/24c67dd7-4c52-4caa-81d1-199b51be4448#"""
}
CP33O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXXIII Vto 23 02 2026",
    "Código": "CP33O",
    "ISIN": "AR0065254358",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/02/2024",
    "Vencimiento": "23/02/2026",
    "Fecha Primer Cupón": "23/05/2024",
    "Cupón / Spread": 4., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["23/5/2024",
    "23/8/2024",
    "25/11/2024",
    "24/2/2025",
    "23/5/2025",
    "25/8/2025",
    "23/11/2025",
    "23/2/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CP33O/Y/MPMAE-RES-ON%20EF%20CIA%20GENERAL%20DE%20COMBUSTIBLES%20-Aviso%20Rdos%2021-02-24.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CP33O/Y/MPMAE-ANU-ON%20CIA%20GRAL%20DE%20COMBUSTIBLES%20CLASE%2033%20Y%2034%20Suplemento%2019-02-2024.pdf"""
}
CP35O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXXV Vto 28 02 2026",
    "Código": "CP35O",
    "ISIN": "AR0787207700",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/06/2024",
    "Vencimiento": "28/02/2026",
    "Fecha Primer Cupón": "28/11/2024",
    "Cupón / Spread": 3., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "28/11/2024",
    "28/2/2025",
    "28/5/2025",
    "28/8/2025",
    "28/11/2025",
    "28/2/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/4b3494a3-17c1-4975-bc78-4357d8974249#"""
}
LUC3O = {
    "Nombre Security": "ON Luz de Tres Picos S.A. Clase 3 Vto 05 05 2032",
    "Código": "LUC3O",
    "ISIN": "ARLUZT560039",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/05/2022",
    "Vencimiento": "05/05/2032",
    "Fecha Primer Cupón": "05/08/2022",
    "Cupón / Spread": 5.05, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "05/08/2022",
    "05/11/2022",
    "05/02/2023",
    "05/05/2023",
    "05/08/2023",
    "05/11/2023",
    "05/02/2024",
    "05/05/2024",
    "05/08/2024",
    "05/11/2024",
    "05/02/2025",
    "05/05/2025",
    "05/08/2025",
    "05/11/2025",
    "05/02/2026",
    "05/05/2026"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m6 de emitido",
    "Fecha Call": "05/11/2025",
    "Precio Call": {"m42 al 48":1.02,"m48 en adelante": 1.01},  # Precio Call
    "Comentarios": """Desde el mes 42 inclusive contado desde la Fecha de Emisión y Liquidación, la Compañía tendrá el derecho, a su sola opción, de rescatar
las Obligaciones Negociables Clase 3 en su totalidad (pero no en parte), al precio de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y
cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 3):
Desde el mes 42 inclusive contado desde la Fecha de Emisión y Liquidación hasta el mes 48 exclusive contado desde la Fecha de Emisión y Liquidación: 102%
Luego del mes 48 inclusive contado desde la Fecha de Emisión y Liquidación hasta el día anterior a la Fecha de Emisión y Liquidación: 101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LUC3O/Y/MPMAE-RES-SVS-ON%20LUZ%20DE%20TRES%20PICOS%20CLASE%202%20Y%203%20Aviso%20de%20Resultados%2003-05-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LUC3O/Y/MPMAE-ANU-SVS%20ON%20LUZ%20DE%20TRES%20PICOS%20CLASE%202%20y%203-Suplemento%2029-04-22.pdf"""
}
CIC3O = {
    "Nombre Security": "ON CNH Industrial Capital Arg SA Clase 3 Vto 27 10 2025",
    "Código": "CIC3O",
    "ISIN": "ARCNHI560034",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Industrials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/10/2022",
    "Vencimiento": "27/10/2025",
    "Fecha Primer Cupón": "27/10/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/10/2025"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la fecha de emisión",
    "Fecha Call": "27/10/2022",
    "Precio Call": {"m1 en adelante": 1.01},  # Precio Call
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de rescatar total o parcialmente las Obligaciones Negociables, a un precio
    de rescate del 1.01 del valor nominal de las Obligaciones Negociables junto con los intereses devengados y no pagados calculados hasta la fecha de rescate""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CIC3O/Y/MPMAE-RES-ON%20CNH%20INDUSTRIAL%20CLASE%203-4-Aviso%20de%20Resultados%2025-10-22.pdf""",
    "Suplemento Prospecto": """https://www.byma.com.ar/wp-admin/admin-ajax.php?action=get_sicolp_document&sicolp_document_id=33924&sicolp_document_name=MPMAE-ANU-ON%20CNH%20INDUSTRIAL%20CLASE%203-4-Suplemento%20Prospecto%2019-10-22%20(1).pdf"""
}
CAC3O = {
    "Nombre Security": "ON Capex S.A Clase III Vto. 27 02 2026",
    "Código": "CAC3O",
    "ISIN": "ARCAPX560030",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/2/2023",
    "Vencimiento": "27/2/2026",
    "Fecha Primer Cupón": "27/2/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/2/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m33 de emitido",
    "Fecha Call": "27/11/2025",
    "Precio Call": {"m33 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no aprcialmente, las Oblgiaciones Negociables,
    con una anticipación no mayor a noventa (90) días a la Fecha de Vencimiento. En caso de rescate de las 
    Obligaciones Negociables, se rescatarán por un importe equivalente al monto de capital no amortizado
    de las Oblgiaciones Negociables, más los intereses devengados e impagos sobre aquellos 
    a la fecha de rescate en cuestión, más cualquier monto adeudado e impago bajo las Obligaciones Negociables""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/69f7e44c-5af6-4d34-94f9-989bfbed289c#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/680693bd-9ac8-43f6-b706-5f7c0387e874"""
}
CACAO = {
    "Nombre Security": "ON Capex S.A. Clase X Vto. 05 07 2027",
    "Código": "CACAO",
    "ISIN": "AR0669378199",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/07/2024",
    "Vencimiento": "05/07/2027",
    "Fecha Primer Cupón": "05/07/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["05/07/2027"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m33 de emitido",
    "Fecha Call": "05/04/2027",
    "Precio Call": {"m33 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no parcialmente, las Oblgiaciones Negociables,
    con una anticipación no mayor a noventa (90) días a la Fecha de Vencimiento. En caso de rescate de las 
    Obligaciones Negociables, se rescatarán por un importe equivalente al monto de capital no amortizado
    de las Obligaciones Negociables, más los intereses devengados e impagos sobre aquellos 
    a la fecha de rescate en cuestión, más cualquier monto adeudado e impago bajo las Obligaciones Negociables""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CACAO/Y/MPMAE-RES-ON%20CAPEX%20CLASE%209-10-Aviso%20de%20Resultados%2003-07-24.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CACAO/Y/MPMAE-ANU-ON%20CAPEX%20CLASES%209-10-Suplemento%2001-07-24.pdf"""
}
OLC1O = {
    "Nombre Security": "ON Oleoductos del Valle S.A. Clase I Vto 18 04 2026",
    "Código": "OLC1O",
    "ISIN": "AROLDV560013",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "18/04/2023",
    "Vencimiento": "18/04/2026",
    "Fecha Primer Cupón": "18/04/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["18/04/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m33 de emitido",
    "Fecha Call": "18/01/2026",
    "Precio Call": {"m33 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no 
                    parcialmente las Obligaciones Negociables, con una anticipación no 
                    mayor a 90 días de la Fecha de Vencimiento. En caso de rescate de 
                    las Obligaciones Negociables, se rescatarán por un importe 
                    equivalente al monto de capital no amortizado de las Obligaciones 
                    Negociables, más los intereses devengados e impagos sobre 
                    aquellos a la fecha de rescate en cuestión, más cualquier monto 
                    adeudado e impago bajo las Obligaciones Negociables. """,
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/OLC1O/Y/MPMAE-RES-ON%20OL.%20DEL%20VALLE%20CLASE%201%20AD%20Y%20CLASE%202-Aviso%20de%20Resultados%2007-06-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/OLC1O/Y/MPMAE-ANU-ON%20OL.%20DEL%20VALLE%20CLASE%201%20AD%20Y%20CLASE%202-Suplemento%20de%20Prospecto%2005-06-2023.pdf"""
}
CAC7O = {
    "Nombre Security": "ON Capex S.A. Clase VII Vto. 07 09 2027",
    "Código": "CAC7O",
    "ISIN": "ARCAPX560089",
    "Calificación": "AA(Arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/09/2023",
    "Vencimiento": "07/09/2027",
    "Fecha Primer Cupón": "07/09/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/09/2027"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m42 de emitido",
    "Fecha Call": "07/03/2027",
    "Precio Call": {"m42 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no 
                    parcialmente las Obligaciones Negociables, con una anticipación no 
                    mayor a 180 días de la Fecha de Vencimiento. En caso de rescate de 
                    las Obligaciones Negociables, se rescatarán por un importe 
                    equivalente al monto de capital no amortizado de las Obligaciones 
                    Negociables, más los intereses devengados e impagos sobre 
                    aquellos a la fecha de rescate en cuestión, más cualquier monto 
                    adeudado e impago bajo las Obligaciones Negociables. """,
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CAC7O/Y/MPMAE-RES-ON%20CAPEX%20CLASE%206-7-Aviso%20de%20Resultados%2005-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CAC7O/Y/MPMA-ANU-ON%20CAPEX%20CLASE%206-7-Suplemento%20de%20Prospecto%2001-09-23.pdf"""
}
OLC3O = {
    "Nombre Security": "ON Oleoductos del Valle S.A. Clase III Vto 10 07 2027",
    "Código": "OLC3O",
    "ISIN": "AROLDV560039",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/07/2023",
    "Vencimiento": "10/07/2027",
    "Fecha Primer Cupón": "10/07/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/07/2027"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m45 de emitido",
    "Fecha Call": "10/04/2027",
    "Precio Call": {"m42 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no 
                    parcialmente las Obligaciones Negociables Clase 3, con una 
                    anticipación no mayor a 90 días de la Fecha de Vencimiento. En 
                    caso de rescate de las Obligaciones Negociables, se rescatarán 
                    por un importe equivalente al monto de capital no amortizado de 
                    las Obligaciones Negociables, más los intereses devengados e 
                    impagos sobre aquellos a la fecha de rescate en cuestión, más
                    cualquier monto adeudado e impago bajo las Obligaciones 
                    Negociables""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/OLC3O/Y/MPMAE-RES-ON%20OLEODUCTOS%20DEL%20VALLE%20CLASE%203%20-%20Aviso%20de%20Resultados%2006-07-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/OLC3O/Y/MPMAE-ANU-ON%20OLEODUCTOS%20DEL%20VALLE%20CLASE%203%20-%20Suplemento%20Precio%2004-07-2023.pdf"""
}
MGCEO = {
    "Nombre Security": "ON Pampa Energia S.A. Clase XIII Vto 19 12 2027",
    "Código": "MGCEO",
    "ISIN": "ARPAMP5600G7",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "19/12/2022",
    "Vencimiento": "19/12/2027",
    "Fecha Primer Cupón": "19/12/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["19/12/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m57 de emitido",
    "Fecha Call": "19/09/2027",
    "Precio Call": {"m42 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su 
                    totalidad y no parcialmente las Obligaciones Negociables, 
                    con una anticipación no mayor a 90 días a la Fecha de Vencimiento. 
                    En caso de rescate de las Obligaciones Negociables, se rescatarán por 
                    un importe equivalente al monto de capital no amortizado de las 
                    Obligaciones Negociables, más los intereses devengados e impagos sobre 
                    aquellos a la fecha del rescate en cuestión, más cualquier monto adeudado e impago bajo las 
                    Obligaciones Negociables.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MGCEO/Y/MPMAE-RES-ON%20PAMPA%20ENERGIA%20CLASE%2013%20Y%2014-Aviso%20de%20Resultados%2015-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MGCEO/Y/MPMAE-ANU-ON%20PAMPA%20ENERGIA%20CLASE%2013%20Y%2014-Suplemento%2013-12-22.pdf"""
}
YMCRO = {
    "Nombre Security": "ON YPF S.A. Clase XXVI Vto 12 09 2028",
    "Código": "YMCRO",
    "ISIN": "ARYPFS5601X8",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/09/2023",
    "Vencimiento": "12/09/2028",
    "Fecha Primer Cupón": "12/09/2028",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["12/09/2028"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m42 de emitido",
    "Fecha Call": "12/03/2027",
    "Precio Call": {"m42 a m47: 1.02, m48 a m53: 1.01 y m54 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Sociedad tendrá el derecho de rescatar anticipadamente, a su única opción, la totalidad o una parte 
    de las Obligaciones Negociables Clase XXVI que estén en circulación en cualquier momento, a partir del mes 42 (inclusive) 
    contado desde la Fecha de Emisión y Liquidación. El precio de rescate de capital (más los intereses devengados y no pagados calculados hasta 
    la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase XXVI) será determinado de la siguiente manera:
    Desde el 42° mes contado desde la Fecha de Emisión y Liquidación hasta el día anterior al 48° mes contado desde la Fecha de Emisión y Liquidación: 1.02 del valor nominal.
    Desde el 48° mes contado desde la Fecha de Emisión y Liquidación hasta el día anterior al 54° mes contado desde la Fecha de Emisión: 1.01 del valor nominal.
    Desde el 54° mes contado desde la Fecha de Emisión y hasta el día anterior a la Fecha de Vencimiento de las Obligaciones Negociables Clase XXVI: 1 del valor nominal.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YMCRO/Y/MPMAE-ANU-ON%20YPF%20CLASES%2021%20AD-26-Suplemento%20de%20Prospecto%2004-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/OLC3O/Y/MPMAE-ANU-ON%20OLEODUCTOS%20DEL%20VALLE%20CLASE%203%20-%20Suplemento%20Precio%2004-07-2023.pdf"""
}
VSCIO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XVII Vto 07 12 2026",
    "Código": "VSCIO",
    "ISIN": "AROILG5600H2",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/12/2022",
    "Vencimiento": "06/12/2026",
    "Fecha Primer Cupón": "06/12/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["06/12/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m19 de la emisión",
    "Fecha Call": "06/07/2024",
    "Precio Call": {"m19 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora no podrá rescatar las Obligaciones Negociables Clase XVI hasta el 
                    décimo octavo mes (inclusive) desde la Fecha de Emisión y Liquidación.
                    A partir del décimo noveno mes (inclusive) desde la Fecha de Emisión y 
                    Liquidación, la Emisora podrá, en la medida en que sea permitido de conformidad 
                    con la normativa aplicable en dicha oportunidad, rescatar anticipadamente la 
                    totalidad o una parte de las Obligaciones Negociables Clase XVI que se encuentren 
                    en circulación, al valor nominal con más los intereses devengados hasta la fecha de 
                    pago del valor de rescate""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCIO/Y/MPMAE-RES-ON%20VISTA%20ENERGY%20Clase%20XVI%20y%20XVII-Aviso%20Resultado%2002-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCIO/Y/MPMAE-ANU-ON%20VISTA%20ENERGY%20CLASE%20XVI%20Y%20XVII%20-%20Suplemento%2028-11-2022.pdf"""
}
VSCQO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XXV Vto 08 07 2028",
    "Código": "VSCQO",
    "ISIN": "AR0941463967",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/07/2024",
    "Vencimiento": "08/07/2028",
    "Fecha Primer Cupón": "08/10/2024",
    "Cupón / Spread": 3.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "8/10/2024",
    "8/1/2025",
    "8/4/2025",
    "8/7/2025",
    "8/10/2025",
    "8/1/2026",
    "8/4/2026",
    "8/7/2026",
    "8/10/2026",
    "8/1/2027",
    "8/4/2027",
    "8/7/2027",
    "8/10/2027",
    "8/1/2028",
    "8/4/2028",
    "8/7/2028"
], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m14 de la emisión",
    "Fecha Call": "08/09/2025",
    "Precio Call": {"m14 en adelante: 1.00"},  # Precio Call
    "Comentarios": """A partir del décimo cuarto (14) mes (inclusive) desde la Fecha de Emisión y Liquidación, la Emisora podrá, en la medida en que sea permitido de
conformidad con la normativa aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables
Clase XXV que se encuentren en circulación, al valor nominal con más los intereses devengados hasta la fecha de pago del valor de rescate (el “Valor
de Rescate”), calculados aplicando el Tipo de Cambio Aplicable.""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/473ae42e-f577-40cd-bb23-44e6a53abd2d#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/57189b20-861b-4be9-8f55-72a6a6425fd7#"""
}
LMS6O = {
    "Nombre Security": "ON Aluar Aluminio Argentino S.A.I.C. Serie 6 Vto 27 08 2028",
    "Código": "LMS6O",
    "ISIN": "ARALUA560047",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Materials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/04/2023",
    "Vencimiento": "27/04/2028",
    "Fecha Primer Cupón": "27/04/2028",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/04/2028"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m24 de la emisión",
    "Fecha Call": "27/04/2025",
    "Precio Call": {"m24 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora tendrá el derecho, a su sola opción, de rescatar las 
                    Obligaciones Negociables Serie 5, total o parcialmente, al precio de 
                    rescate de capital (más los intereses devengados y no pagados calculados 
                    a la fecha de rescate, de ser aplicable, los Montos Adicionales y cualquier 
                    otra suma adeudada bajo las Obligaciones Negociables Serie 5) conforme
                    surge del siguiente detalle:
            • A partir del mes 24 (veinticuatro) exclusive, a contar desde la Fecha de Emisión y Liquidación y hasta el día anterior a la Fecha de 
            Vencimiento de la Serie 5 a un precio de rescate del 1.00 del valor nominal de las Obligaciones Negociables Serie 5 junto con los intereses 
            devengados y no pagados calculados a la fecha de rescate, de ser aplicable.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LMS6O/Y/MPMAE-ANU-RES%20ON%20ALUAR%20SERIE%205%20y%206%20Aviso_de_Resultados%2025-04-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LMS6O/Y/MPMAE-ANU-ON%20ALUAR%20SERIE%205%20Y%206-Suplemento%2019-04-23.pdf"""
}
VSCJO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XVIII Vto 03 03 2027",
    "Código": "VSCJO",
    "ISIN": "AROILG5600I0",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/03/2023",
    "Vencimiento": "03/03/2027",
    "Fecha Primer Cupón": "03/03/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["03/03/2027"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "03/03/2023",
    "Precio Call": {"m1 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora podrá, en la medida en que sea permitido de conformidad con 
                    la normativa aplicable en dicha oportunidad, rescatar anticipadamente la 
                    totalidad o una parte de las Obligaciones Negociables Clase XVIII que se 
                    encuentren en circulación, en cualquier momento desde la Fecha de 
                    Emisión y Liquidación, al valor nominal con más los intereses devengados
                    calculados aplicando el Tipo de Cambio Aplicable hasta la fecha de pago 
                    del valor de rescate (el “Valor del Rescate”). El Valor de Rescate se pagará 
                    en un plazo no menor a cinco (5) días y no mayor a treinta (30) días desde 
                    la publicación del aviso correspondiente (la “Fecha del Rescate”).""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCJO/Y/MPMAE-RES-ON%20VISTA%20ENERGY%20CLASE%2018%20Vista%20-%20Aviso%20de%20Resultados%2001-03-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCJO/Y/MPMAE-ANU-ON%20VISTA%20ENERGY%20CLASE%2018-%20%20Suplemento%20de%20Prospecto%2027-02-2023.pdf"""
}
TBC9O = {
    "Nombre Security": "ON Central Termica Barragan S.A. Clase 9 Vto 03 04 2026",
    "Código": "TBC9O",
    "ISIN": "ARCTBA560073",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "03/04/2023",
    "Vencimiento": "03/04/2026",
    "Fecha Primer Cupón": "03/04/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["03/04/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m33 de la emisión",
    "Fecha Call": "03/01/2026",
    "Precio Call": {"m33 en adelante: 1.00"},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no parcialmente, 
                    las Obligaciones Negociables, con una anticipación no mayor a 90 días a la 
                    Fecha de Vencimiento. En caso de rescate de las Obligaciones Negociables, se 
                    rescatarán por un importe equivalente al monto de capital no amortizado de 
                    las Obligaciones Negociables, más los intereses devengados e impagos sobre 
                    aquellos a la fecha del rescate en cuestión, más cualquier monto adeudado e 
                    impago bajo las Obligaciones Negociables""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TBC9O/Y/MPMAE-RES-ON%20CT%20BARRAGAN%20CLASE%208%20REAPERTURA%20y%209-Aviso%20de%20Resultados-%2030-03-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TBC9O/Y/MPMAE-ANU-ON%20CT%20BARRAGAN%20CLASE%209-Suplemento%20de%20Prospecto-28-03-23.pdf"""
}
GN41O = {
    "Nombre Security": "ON Genneia S.A. Clase XLI Vto. 14 07 2026",
    "Código": "GN41O",
    "ISIN": "AREMGA5600T3",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/07/2023",
    "Vencimiento": "14/07/2026",
    "Fecha Primer Cupón": "14/07/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["14/07/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m30 de emitido",
    "Fecha Call": "14/01/2026",
    "Precio Call": {"m30 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Compañía tendrá el derecho, a su sola opción, de rescatar las 
                    Obligaciones Negociables Clase XLI en su totalidad (pero no en parte) que 
                    se encuentren en circulación, en cualquier momento a partir del mes 
                    treinta (30) (inclusive) contado desde la Fecha de Emisión y Liquidación, al 
                    valor nominal (más los intereses devengados y no pagados calculados 
                    hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma 
                    adeudada bajo las Obligaciones Negociables Clase XLI)""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/GN41O/Y/MPMAE-RES-ON%20GENNEIA%20CLASE%2039-40-41-Aviso%20de%20Resultados%2012-07-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/GN41O/Y/MPMAE-ANU-ON%20GENNEIA%20XXXIX%20-%20XL%20-XLI%20Suplemento%20de%20Prospecto%2010-07-2023.pdf"""
}
CAC6O = {
    "Nombre Security": "ON Capex S.A. Clase VI Vto. 07 09 2026",
    "Código": "CAC6O",
    "ISIN": "ARCAPX560071",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/09/2023",
    "Vencimiento": "07/09/2026",
    "Fecha Primer Cupón": "07/09/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/09/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m30 de emitido",
    "Fecha Call": "07/03/2026",
    "Precio Call": {"m30 en adelante": 1.00},  # Precio Call
    "Comentarios": """La Emisora podrá rescatar a su sola opción, en su totalidad y no aprcialmente, las Oblgiaciones Negociables,
    con una anticipación no mayor a ciento ochenta (180) días a la Fecha de Vencimiento de las Obligaciones Negociables
    Clase VI y/o a la Fecha de Vencimiento de las Obligaciones Negociables Clase VII. En caso de rescate de las 
    Obligaciones Negociables, se rescatarán por un importe equivalente al monto de capital no amortizado
    de las Oblgiaciones Negociables, más los intereses devengados e impagos sobre aquellos 
    a la fecha de rescate en cuestión, más cualquier monto adeudado e impago bajo las Obligaciones Negociables""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CAC6O/Y/MPMAE-RES-ON%20CAPEX%20CLASE%206-7-Aviso%20de%20Resultados%2005-09-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CAC6O/Y/MPMA-ANU-ON%20CAPEX%20CLASE%206-7-Suplemento%20de%20Prospecto%2001-09-23.pdf"""
}
LMS4O = {
    "Nombre Security": "ON Aluar Aluminio Argentino S.A.I.C. Serie 4 Vto 07 09 2025",
    "Código": "LMS4O",
    "ISIN": "ARALUA560039",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Materials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/09/2022",
    "Vencimiento": "06/09/2025",
    "Fecha Primer Cupón": "06/09/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["06/09/2025"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir de la emisión",
    "Fecha Call": "06/09/2022",
    "Precio Call": {"m1 al 12":1.03,"m13 al 24": 1.02, "m25 en adelante": 1.01},  # Precio Call
    "Comentarios": """En cualquier momento la Emisora tendrá el derecho, a su sola opción, de 
                    rescatar las Obligaciones Negociables, total o parcialmente, al precio de rescate de capital
                    (más los intereses devengados y no pagados calculados 
                    a la fecha de rescate, de ser aplicable, los Montos Adicionales y cualquier 
                    otra suma adeudada bajo las Obligaciones Negociables) que surge del 
                    siguiente detalle:
                     Desde la Fecha de Emisión y Liquidación hasta el duodécimo 
                    mes desde la Fecha de Emisión y Liquidación: a un precio de 
                    rescate del 103% del valor nominal de las Obligaciones 
                    Negociables junto con los intereses devengados y no pagados 
                    calculados a la fecha de rescate, de ser aplicable.
                     A partir del décimo tercer mes a contar desde la Fecha de 
                    Emisión y Liquidación y hasta el vigésimo cuarto mes desde la 
                    Fecha de Emisión: a un precio de rescate del 102% del valor 
                    nominal de las Obligaciones Negociables junto con los intereses 
                    devengados y no pagados calculados a la fecha de rescate, de ser 
                    aplicable.
                     A partir del vigésimo quinto mes a contar desde la Fecha de 
                    Emisión y Liquidación y hasta el día anterior a la Fecha de 
                    Vencimiento a un precio de rescate del 101% del valor nominal 
                    de las Obligaciones Negociables junto con los intereses 
                    devengados y no pagados calculados a la fecha de rescate, de ser 
                    aplicable.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/LMS4O/Y/ALUAR%20ALUMINIO%20ARGENTINO%20-%20HR%20Aviso%20de%20Resultados%2006-09-2022.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/LMS4O/Y/ALUAR%20ALUMINIO%20ARGENTINA%20HR-Suplemento%20Prosp%20de%20Canje%20%20ON%20SERIE%203.pdf"""
}
PZCAO = {
    "Nombre Security": "ON Plaza Logistica S.R.L. Clase 10 Vto. 27 07 2026",
    "Código": "PZCAO",
    "ISIN": "ARPLAZ560094",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/07/2023",
    "Vencimiento": "27/07/2026",
    "Fecha Primer Cupón": "27/07/2026",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/07/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m33",
    "Fecha Call": "06/09/2022",
    "Precio Call": {"m33 en adelante": 1},  # Precio Call
    "Comentarios": """Las Obligaciones Negociables, podrán ser rescatadas al solo arbitrio de la Sociedad, 
                    en cualquier momento a partir del tercer mes anterior a la Fecha de Vencimiento 
                    de las Obligaciones Negociables, en forma total o parcial. Los rescates podrán 
                    realizarse previa notificación con al menos cinco (5) días de anticipación, conforme 
                    aviso a publicar en los términos requeridos por los reglamentos de listado y 
                    negociación de los mercados en los que se encuentren listadas las Obligaciones 
                    Negociables e informándose a la CNV a través de la AIF""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PZCAO/Y/MPMAE-RES-ON%20PLAZA%20LOGISTICA%20CLASE%2010%20Aviso%20de%20Resultados%2026-07-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PZCAO/Y/MPMAE-ANU-ON%20PLAZA%20LOGISTICA%20CLASE%2010%20Suplemento%20de%20Precio%2024-07-2023.pdf"""
}
AE10O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase 10 Vto. 07 07 2025",
    "Código": "AE10O",
    "ISIN": "ARAEAR5600D9",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/07/2023",
    "Vencimiento": "05/07/2025",
    "Fecha Primer Cupón": "05/07/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["05/07/2025"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad a partir del m18 de emitido",
    "Fecha Call": "05/01/2025",
    "Precio Call": {"m18 en adelante": 1.00},  # Precio Call
    "Comentarios": """En cualquier momento, a partir del décimo-octavo (18°) mes desde la Fecha de Emisión y 
                    Liquidación, la Compañía tendrá el derecho, a su sola opción, de rescatar las Obligaciones 
                    Negociables Clase 10 en su totalidad (pero no en parte), sin prima de rescate, debiendo abonar el 
                    capital más los intereses devengados y no pagados calculados hasta la fecha de rescate, los 
                    Montos Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables Clase 10""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/AE10O/Y/MPMAE-RES-%20ON%20AEROPUERTOS%20ARGENTINA%202000%20Clase%2010%20Aviso%20Resultados%2003-07-2023.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/AE10O/Y/MPMAE-ANU-ON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%2010%20Suplemento%2028-06-2023.pdf"""
}
AER7O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase VII Vto. 08 07 2025",
    "Código": "AER7O",
    "ISIN": "ARAEAR5600B3",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/07/2022",
    "Vencimiento": "08/07/2025",
    "Fecha Primer Cupón": "08/07/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["08/07/2025"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total a opción de la sociedad desde la emisión",
    "Fecha Call": "08/07/2022",
    "Precio Call": {"m0 a m18: 1.03, m19 a m24: 1.02 en m25 adelante": 1.00},  # Precio Call
    "Comentarios": """EEn cualquier momento, la Compañía tendrá el derecho, a su sola opción, de rescatar las 
Obligaciones Negociables en su totalidad (pero no en parte), al precio de rescate de capital 
(más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos 
Adicionales y cualquier otra suma adeudada bajo las Obligaciones Negociables) que surge 
del siguiente detalle:
Plazo Precio
Desde la Fecha de Emisión y Liquidación hasta el
doceavo mes desde la Fecha de Emisión y Liquidación inclusive. 103%
Luego del doceavo mes desde la Fecha de Emisión 
y Liquidación hasta el vigésimo cuarto mes desde la Fecha
de Emisión y Liquidación inclusive. 102%
Luego del vigésimo cuarto mes desde la Fecha de Emisión y
Liquidación y hasta el día anterior a la 
Fecha de Vencimiento inclusive. 101%
""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/7446e296-76ad-44be-9228-c84107b2ea6b#""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/c7cce38f-2b93-4f3e-ac66-3616d4486bff#"""
}
PEC4O = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Serie IV Vto. 14 04 2026",
    "Código": "PEC4O",
    "ISIN": "ARPAEG5600A6",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/04/2023",
    "Vencimiento": "14/04/2026",
    "Fecha Primer Cupón": "14/07/2023",
    "Cupón / Spread": 3.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["14/7/2023", "14/10/2023", "14/1/2024", "14/4/2024", "14/7/2024", 
                        "14/10/2024", "14/1/2025", "14/4/2025", "14/7/2025", "14/10/2025", 
                        "14/1/2026", "14/4/2026"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [14] * 6 + [16]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PEC4O/Y/MPMAE-RES-ON%20PETROLERA%20ACONCAGUA%20CLASE%204%20Y%205-Aviso%20de%20Resultado%2012-04-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PEC4O/Y/MPMAE-ANU-ON%20PETROLERA%20ACONCAGUA%20CLASE%204%20Y%205-Suplemento%2005-04-23.pdf"""
}
YFCFO = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase XIV Vto 27 02 2027",
    "Código": "YFCFO",
    "ISIN": "AR0976739711",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2024",
    "Vencimiento": "27/02/2027",
    "Fecha Primer Cupón": "27/05/2024",
    "Cupón / Spread": 3.00, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/5/2024", "27/8/2024", "27/11/2024", "27/2/2025", "27/5/2025", 
                        "27/8/2025", "27/11/2025", "27/2/2026", "27/5/2026", "27/8/2026", 
                        "27/11/2026", "27/2/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [50] + [0] + [50]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YFCFO/Y/MPMAE-RES-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2014-15%20Aviso%20de%20Resultados%2023-02-2024.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YFCFO/Y/MPMAE-ANU-%20ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%2014-15%20%20Suplemento%20de%20Prospecto%2019-02-2024.pdf"""
}
CP28O = {
    "Nombre Security": "ON Compañia General de Combustibles S.A. Clase XXVIII Vto 07 09 2026",
    "Código": "CP28O",
    "ISIN": "ARCGCO5600T9",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "07/09/2022",
    "Vencimiento": "07/09/2026",
    "Fecha Primer Cupón": "07/09/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["07/09/2022",
                        "07/12/2022",
                        "07/03/2023",
                        "07/06/2023", 
                        "07/09/2023", 
                        "07/12/2023",
                        "07/03/2024",
                        "07/06/2024",
                        "07/09/2024",
                        "07/12/2024",
                        "07/03/2025",
                        "07/06/2025",
                        "07/09/2025",
                        "07/12/2025",
                        "07/03/2026",
                        "07/06/2026",
                        "07/09/2026" 
                        ], # Lista de fechas como ejemplo
    "Amortización": ([0] * 14 + [33.33] + [33.33] + [33.34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m6 de emitido",
    "Fecha Call": "07/09/2022",
    "Precio Call": {"m18 al 24":1.02,"m24 al m30": 1.01, "m30 en adelante": 1},  # Precio Call
    "Comentarios": """En cualquier momento, la Compañía tendrá el derecho, a su sola opción, de rescatar 
    las Obligaciones Negociables Clase 28 en su totalidad (pero no en parte), al precio 
    de rescate de capital (más los intereses devengados y no pagados calculados hasta la fecha de rescate, los Montos Adicionales y cualquier otra suma adeudada bajo las 
                    Obligaciones Negociables Clase 28) que surge del siguiente detalle: 
                    Plazo Precio
                    Desde la Fecha de Emisión y  Liquidación hasta el sexto mes desde la 
                    Fecha de Emisión y Liquidación. 102%
                    Luego del sexto mes desde la Fecha de Emisión y Liquidación y hasta el día 
                    anterior a la Fecha de Vencimiento de las Obligaciones Negociables Clase 28.
                    101%""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/CP28O/Y/MPMAE-RES-ON%20CIA%20GRAL%20COMBUSTIBLES%20CLASE%2028%20-%20Aviso_de_Resultados%2005-09-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/CP28O/Y/MPMAE-ANU-ON%20EF%20CIA%20GRAL%20COMBUSTIBLES%20Suplemento%20Prospecto%2031-08-22.pdf"""
}
FOS2O = {
    "Nombre Security": "ON Futuros y Opciones.com S.A Serie II Vto 25 07 2025",
    "Código": "FOS2O",
    "ISIN": "ARFUOP560026",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "25/07/2022",
    "Vencimiento": "25/07/2025",
    "Fecha Primer Cupón": "25/10/2022",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["25/10/2022",
    "25/1/2023",
    "25/4/2023",
    "25/7/2023",
    "25/10/2023",
    "25/1/2024",
    "25/4/2024",
    "25/7/2024",
    "25/10/2024",
    "25/1/2025",
    "25/4/2025",
    "25/7/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m6 de emitido",
    "Fecha Call": "25/01/2023",
    "Precio Call": {"m6: 1.00"},  # Precio Call
    "Comentarios": """Podremos rescatar a nuestra opción las Obligaciones Negociables Serie II, en o desde la fecha en que se cumplan seis meses previos a 
la Fecha de Vencimiento, a un precio igual al 100% del valor nominal, con más los intereses devengados e impagos y Montos 
Adicionales, si hubiera, en forma total o parcial, previa notificación con al menos 5 días de anticipación, conforme aviso a publicar en los 
términos requeridos por los reglamentos de listado y negociación de los mercados en los que se encuentren listadas las Obligaciones 
Negociables Serie II e informándose, mediante la publicación de un hecho relevante a través de la AIF. 
En todos los casos de rescate, se garantizará el trato igualitario entre los tenedores de las Obligaciones Negociables Serie II. El rescate 
parcial será realizado a pro rata entre los tenedores de las Obligaciones Negociables Serie II.
""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/FOS2O/Y/MPMAE-RES-ON%20FUTUROS%20Y%20OPCIONES%20SERIE%202-%20Aviso%20de%20Resultados%2021-07-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/FOS2O/Y/MPMAE-ANU-ON%20FUTUROS%20Y%20OPCIONES%20SERIE%202%20-%20Suplemento%20de%20Prospecto%2019-07-22.pdf"""
}
GN39O = {
    "Nombre Security": "ON Genneia S.A. Clase XXXIX Vto 14 07 2028",
    "Código": "GN39O",
    "ISIN": "AREMGA5600R7",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/07/2023",
    "Vencimiento": "14/07/2028",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 2., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
        "14/10/2023", "14/01/2024", "14/04/2024", "14/07/2024", 
        "14/10/2024", "14/01/2025", "14/04/2025", "14/07/2025", 
        "14/10/2025", "14/01/2026", "14/04/2026", "14/07/2026", 
        "14/10/2026", "14/01/2027", "14/04/2027", "14/07/2027", 
        "14/10/2027", "14/01/2028", "14/04/2028", "14/07/2028"
    ],
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate opcional total a partir del mes 54 desde la emisión",
    "Fecha Call": "14/01/2028",
    "Precio Call": 100,  # Precio Call
    "Comentarios": """100 del valor nominal más intereses devengados y sumas adicionales""",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8688%2FMPMAE%2DRES%2DON%20GENNEIA%20CLASE%2039%2D40%2D41%2DAviso%20de%20Resultados%2012%2D07%2D23%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8688&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8688%2FMPMAE%2DANU%2DON%20GENNEIA%20XXXIX%20%2D%20XL%20%2DXLI%20Suplemento%20de%20Prospecto%2010%2D07%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8688&p=true&ga=1"""
}
YMCTO = {
    "Nombre Security": "ON YPF S.A. Clase XXVII Vto 10 10 2026",
    "Código": "YMCTO",
    "ISIN": "AR0688075032",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "10/10/2023",
    "Vencimiento": "10/10/2026",
    "Fecha Primer Cupón": "10/01/2024",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["10/1/2024",
    "10/4/2024",
    "10/7/2024",
    "10/10/2024",
    "10/1/2025",
    "10/4/2025",
    "10/7/2025",
    "10/10/2025",
    "10/1/2026",
    "10/4/2026",
    "10/7/2026",
    "10/10/2026"
    ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m30 de emitido",
    "Fecha Call": "10/04/2026",
    "Precio Call": {1},  # Precio Call
    "Comentarios": """La Sociedad tendrá derecho a rescatar anticipadamente, a su sola opción, la totalidad o una parte 
                    de las Obligaciones Negociables Clase XXVII que se encuentren en circulación en cualquier 
                    momento, a partir del mes treinta (30°) (inclusive) contado desde la Fecha de Emisión y 
                    Liquidación, al precio de rescate de capital de 100% (más los Montos Adicionales y cualquier 
                    otra suma adeudada bajo las Obligaciones Negociables Clase XXVII).""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YMCTO/Y/MPMAE-RES-ON%20YPF%20CLASE%2027-%20Aviso%20de%20Resultados%2006-10-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YMCTO/Y/MPMAE-ANU-ON%20YPF%20CLASE%2027-%20Suplemento%20de%20Prospecto%2003-10-23.pdf""",
}
VSCHO = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase XVI Vto 06 06 2026",
    "Código": "VSCHO",
    "ISIN": "AROILG5600G4",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "06/12/2022",
    "Vencimiento": "06/06/2026",
    "Fecha Primer Cupón": "06/03/2023",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["6/3/2023", "6/6/2023", "6/9/2023", "6/12/2023",
    "6/3/2024", "6/6/2024", "6/9/2024", "6/12/2024",
    "6/3/2025", "6/6/2025", "6/9/2025", "6/12/2025",
    "6/3/2026", "6/6/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m19 de emitido",
    "Fecha Call": "07/09/2022",
    "Precio Call": {1},  # Precio Call
    "Comentarios": """La Emisora no podrá rescatar las Obligaciones Negociables Clase XVI hasta el décimo octavo mes (inclusive) desde la Fecha de Emisión y Liquidación. 
    A partir del décimo noveno mes (inclusive) desde la Fecha de Emisión y Liquidación, la Emisora podrá, en la medida en que sea permitido de conformidad con la normativa
    aplicable en dicha oportunidad, rescatar anticipadamente la totalidad o una parte de las Obligaciones Negociables Clase XVI que se encuentren en circulación, al valor 
    nominal con más los intereses devengados hasta la fecha de pago del valor de rescate. El valor de rescate se pagará en un plazo no mayor a treinta (30) días desde 
    la publicación del aviso correspondiente. En todos los casos de rescate, se garantizará el trato igualitario entre los tenedores de las Obligaciones Negociables Clase XVI.
    El reembolso parcial será realizado a prorrata entre los tenedores de las Obligaciones Negociables Clase XVI. Para más información ver “De la Oferta y la Negociación 
    Rescate anticipado a opción de la Sociedad” del Prospecto.""",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/VSCHO/Y/MPMAE-RES-ON%20VISTA%20ENERGY%20Clase%20XVI%20y%20XVII-Aviso%20Resultado%2002-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/VSCHO/Y/MPMAE-ANU-ON%20VISTA%20ENERGY%20CLASE%20XVI%20Y%20XVII%20-%20Suplemento%2028-11-2022.pdf"""
}
CAC4O = {
    "Nombre Security": "ON Capex S.A. Clase IV Vto. 27 02 2027",
    "Código": "CAC4O",
    "ISIN": "ARCAPX560048",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "27/02/2023",
    "Vencimiento": "27/02/2027",
    "Fecha Primer Cupón": "27/02/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": "A3500", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["27/02/2027"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Ulitmos 90 días antes del vencimiento",
    "Fecha Call": "29/11/2026",
    "Precio Call": 1,  # Precio Call
    "Comentarios": """ """,
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/900e5f73-70b2-4d05-b0a4-a1f8c82a7681""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/6c8c9918-70b8-49ff-98ea-eef870f54637"""
}
BPO27 = {
    "Nombre Security": "BONO PARA LA RECONSTRUCCIÓN DE UNA ARGENTINA LIBRE – SERIE 1 - VENCIMIENTO 31 DE OCTUBRE DE 2027",
    "Código": "BPO27",
    "ISIN": "BPO27",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos USD Ley Local",
    "Moneda": "USB",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/01/2024",
    "Vencimiento": "31/10/2027",
    "Fecha Primer Cupón": "31/10/2024",
    "Cupón / Spread": 5., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Personalizado", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360, # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["31/10/2024",
                        "30/4/2025",
                        "31/10/2025",
                        "30/4/2026",
                        "31/10/2026",
                        "30/4/2027",
                        "31/10/2027"], # Lista de fechas como ejemplo
    "Amortización": [0,
                    0,
                    0,
                    0,
                    0,
                    50.0000,
                    50.0000],
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Stripeable put a partir del 1 de marzo en 4 especies   O27 1A (.20) callable desde 30/04/25, BPO27 1B (.20) callable desde 30/04/26, BPO27 1C (.30) callable desde 30/04/27, BPO27 1D (.30)",
    "Fecha Call": "Cualquier momento ",
    "Precio Call": 1,  # Precio Call
    "Comentarios": """ """,
}

# CORPORATIVOS TASA FIJA
BFCWO = {
    "Nombre Security": "ON Banco BBVA Argentina S.A. Clase 30 Vto. 12 09 2025",
    "Código": "BFCWO",
    "ISIN": "AR0091380680",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Tasa Fija",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "12/12/2024",
    "Vencimiento": "12/09/2025",
    "Fecha Primer Cupón": "12/09/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0275)**((270/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["12/09/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9436%2FMPMAE%2DRES%2DON%20BANCO%20BBVA%20ARGENTINA%20CLASES%2030%20y%2031%2DAviso%20de%20Resultado%2009%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9436&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9436%2FMPMAE%2DANU%2DON%20BANCO%20BBVA%20ARGENTINA%20CLASES%2030%20y%2031%2DSuplemento%2005%2D12%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9436&p=true&ga=1"
}
BYCPO = {
    "Nombre Security": "ON Banco de Galicia y Buenos Aires S.A.U. Clase XXIV Vto. 30 10 2025",
    "Código": "BYCPO",
    "ISIN": "AR0250310551",
    "Calificación": "A1+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Tasa Fija",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "30/04/2025",
    "Vencimiento": "30/10/2025",
    "Fecha Primer Cupón": "30/10/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -7, # enteros negativos
    "Días Lag índice hasta inc": -7, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0265)**((180/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["30/10/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618%2FMP%20A3%2D%20RES%2DON%20BANCO%20DE%20GALICIA%20Clases%20XXIV%20y%20XXV%20Aviso%20de%20Resultados%2029%2D04%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618%2FMP%20A3%2D%20ON%20BANCO%20DE%20GALICIA%20CLASE%20XXIV%20%2D%20XXV%2D%20Suplemento%2025%2D04%2D2025%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9618&p=true&ga=1"
}
PSSVO = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 29 Vto  23 09 2025",
    "Código": "PSSVO",
    "ISIN": "AR0474860753",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Tasa Fija",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "23/12/2024",
    "Vencimiento": "23/09/2025",
    "Fecha Primer Cupón": "23/09/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.0274)**(9), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["23/09/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DSuplemento%20de%20Prospecto%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1"
}
PSSZO = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 33 Vto 28 02 2026",
    "Código": "PSSZO",
    "ISIN": "AR0311189234",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Tasa Fija",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2025",
    "Vencimiento": "28/08/2025",
    "Fecha Primer Cupón": "28/08/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 1., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": (1+0.025)**(6), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["28/08/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
    "Suplemento de Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DSuplemento%20de%20Prospecto%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1"
}
FTL2O = {
    "Nombre Security": "ON FCA Compañía Financiera S.A. Clase 20 Serie II Vto 02 03 2026",
    "Código": "FTL2O",
    "ISIN": "AR0992338902",
    "Calificación": "AA(Arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Tasa Fija",
    "Industria": "Financial",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "01/03/2026",
    "Fecha Primer Cupón": "01/03/2025",
    "Cupón / Spread": 33.60, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ["1/3/2025", "29/5/2025", "29/8/2025", "29/11/2025", "1/3/2026"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 2 + [33] * 2 + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DRES%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%20%2DAviso%20de%20Resultado%2028%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DANU%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%2DSuplemento%2025%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1"""
}

# UVA
TLCJO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 18 Vto 17 11 2027",
    "Código": "TLCJO",
    "ISIN": "AR0041103448",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/11/2023",
    "Vencimiento": "17/11/2027",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["17/02/2024", "17/05/2024", "17/08/2024", "17/11/2024",
                        "17/02/2025", "17/05/2025", "17/08/2025", "17/11/2025",
                        "17/02/2026", "17/05/2026", "17/08/2026", "17/11/2026",
                        "17/02/2027", "17/05/2027", "17/08/2027", "17/11/2027"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873%2FMPMAE%2DADE%2D%20ON%20TELECOM%20ARGENTINA%20CLASE%2018%20%2D%20Aviso%20Rectificatorio%20%20de%20Resultados%2021%2D11%2D23%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873%2FMPMAE%2DANU%2DON%20TELECOM%20CLASE%2018%20Suplemento%2014%2D11%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873&p=true&ga=1"""
}
PZCDO = {
    "Nombre Security": "ON Plaza Logistica S.R.L. Clase 12 Vto. 08 03 2026",
    "Código": "PZCDO",
    "ISIN": "AR0571799615",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/03/2024",
    "Vencimiento": "08/03/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["08/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir del m21 de la emisión",
    "Fecha Call": "08/12/2025",
    "Precio Call": {"m14 en adelante: 1.01"},  # Precio Call
    "Comentarios": """ Plaza Logística podrá rescatar total o parcialmente anticipadamente, 
a su opción, las Obligaciones Negociables Clase 12, en cualquier momento a partir del tercer mes anterior a la Fecha de Vencimiento 
de las Obligaciones Negociables Clase 12, en forma total o parcial, al precio de rescate de capital de 101% sobre el valor nominal, 
y si bien las Obligaciones Negociables Clase 12 no devengaran intereses, en caso de corresponder, deberá adicionarse los intereses 
devengados y no pagados calculados hasta la fecha de rescate.""",
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990%2FMPMAE%2DRES%2D%20ON%20PLAZA%20LOGISTICA%20CLASE%2012%20Aviso%20de%20Resultado%2006%2D03%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990%2FMPMAE%2DANU%2DON%20PLAZA%20LOGISTICA%20CLASE%2012%2DSuplemento%2029%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990&p=true&ga=1"""
}
FTL1O = {
    "Nombre Security": "ON FCA Compañía Financiera S.A. Clase 20 Serie I Vto 29 05 2027",
    "Código": "FTL1O",
    "ISIN": "AR0469905985",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "29/05/2027",
    "Fecha Primer Cupón": "01/03/2025",
    "Cupón / Spread": 8.84, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "01/03/2025", "29/05/2025", "29/08/2025", "29/11/2025",
    "01/03/2026", "29/05/2026", "29/08/2026", "29/11/2026",
    "01/03/2027", "29/05/2027"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 5 + [20] * 5),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DRES%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%20%2DAviso%20de%20Resultado%2028%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DANU%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%2DSuplemento%2025%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1"""
}
RB60O = {
    "Nombre Security": "ON Rombo Compañia Financiera S.A. Clase 60 Vto 31 01 2027",
    "Código": "RB60O",
    "ISIN": "AR0377743502",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/01/2025",
    "Vencimiento": "31/01/2027",
    "Fecha Primer Cupón": "01/05/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "01/05/2025", 
    "31/07/2025", 
    "31/10/2025",
    "31/01/2026",
    "01/05/2026",
    "31/07/2026",
    "31/10/2026",
    "31/01/2027"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 4 + [25] * 4),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/ba01697d-e835-446d-a083-6ec1c1116909#""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110%2FMPMAE%2DANU%2DON%20ROMBO%20CF%20SERIE%2059%2D60%2DSuplemento%20de%20Prospecto%2022%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110&p=true&ga=1"""
}
RCCIO = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XVII Vto 20 10 2025",
    "Código": "RCCIO",
    "ISIN": "ARARCS5600C7",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/10/2021",
    "Vencimiento": "20/10/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0.98, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["20/01/2022", "20/04/2022", "20/07/2022", "20/10/2022",
    "20/01/2023", "20/04/2023", "20/07/2023", "20/10/2023",
    "20/01/2024", "20/04/2024", "20/07/2024", "20/10/2024",
    "20/01/2025", "20/04/2025", "20/07/2025", "20/10/2025"], # Lista de fechas como ejemplo
    "Amortización":  None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7719%2FMPMAE%2DRES%2DON%20ARCOR%20CLASE%2016%20Y%2017%20Aviso%20de%20Resultados%2015%2D10%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7719&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EbzC0e-hxSBOoNnjTcAwZM4B3EM9sX856lLcLoMNH9eAbw"""
}
PSSXO = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 31 Vto 28 02 2027",
    "Código": "PSSXO",
    "ISIN": "AR0593873687",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2025",
    "Vencimiento": "28/02/2027",
    "Fecha Primer Cupón": "28/05/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "28/05/2025", 
    "28/08/2025", 
    "28/11/2025",
    "28/02/2026",
    "28/05/2026", 
    "28/08/2026", 
    "28/11/2026",
    "28/02/2027",
    ], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33.33] + [33.33] + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DSuplemento%20de%20Prospecto%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
}

# UVA PROYECTADO
RCCIOj = {
    "Nombre Security": "ON ARCOR S.A.I.C Clase XVII Vto 20 10 2025",
    "Código": "RCCIOj",
    "ISIN": "ARARCS5600C7",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Consumer Staples",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/10/2021",
    "Vencimiento": "20/10/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0.98, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["20/01/2022", "20/04/2022", "20/07/2022", "20/10/2022",
    "20/01/2023", "20/04/2023", "20/07/2023", "20/10/2023",
    "20/01/2024", "20/04/2024", "20/07/2024", "20/10/2024",
    "20/01/2025", "20/04/2025", "20/07/2025", "20/10/2025"], # Lista de fechas como ejemplo
    "Amortización":  None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7719%2FMPMAE%2DRES%2DON%20ARCOR%20CLASE%2016%20Y%2017%20Aviso%20de%20Resultados%2015%2D10%2D2021%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F7719&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/:b:/s/mae-archivos-publicos/EbzC0e-hxSBOoNnjTcAwZM4B3EM9sX856lLcLoMNH9eAbw"""
}
PSSXOj = {
    "Nombre Security": "ON PSA Finance Argentina Cia Financiera Serie 31 Vto  28 02 2027",
    "Código": "PSSXOj",
    "ISIN": "AR0593873687",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "28/02/2025",
    "Vencimiento": "28/02/2027",
    "Fecha Primer Cupón": "28/05/2025",
    "Cupón / Spread": 8., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "28/05/2025", 
    "28/08/2025", 
    "28/11/2025",
    "28/02/2026",
    "28/05/2026", 
    "28/08/2026", 
    "28/11/2026",
    "28/02/2027",
    ], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33.33] + [33.33] + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": "",  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DRES%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DAviso%20de%20Resultados%2027%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561%2FMPMAE%2DANU%2DON%20PSA%20FINANCE%20CLASES%2031%2D32%2D33%2DSuplemento%20de%20Prospecto%2024%2D02%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9561&p=true&ga=1",
}
TLCJOj = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 18 Vto 17 11 2027",
    "Código": "TLCJOj",
    "ISIN": "AR0041103448",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "17/11/2023",
    "Vencimiento": "17/11/2027",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 1., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["17/02/2024", "17/05/2024", "17/08/2024", "17/11/2024",
                        "17/02/2025", "17/05/2025", "17/08/2025", "17/11/2025",
                        "17/02/2026", "17/05/2026", "17/08/2026", "17/11/2026",
                        "17/02/2027", "17/05/2027", "17/08/2027", "17/11/2027"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 5 + [20] * 5),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873%2FMPMAE%2DADE%2D%20ON%20TELECOM%20ARGENTINA%20CLASE%2018%20%2D%20Aviso%20Rectificatorio%20%20de%20Resultados%2021%2D11%2D23%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873%2FMPMAE%2DANU%2DON%20TELECOM%20CLASE%2018%20Suplemento%2014%2D11%2D2023%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8873&p=true&ga=1"""
}
FTL1Oj = {
    "Nombre Security": "ON FCA Compañía Financiera S.A. Clase 20 Serie I Vto 29 05 2027",
    "Código": "FTL1Oj",
    "ISIN": "AR0469905985",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "29/11/2024",
    "Vencimiento": "29/05/2027",
    "Fecha Primer Cupón": "01/03/2025",
    "Cupón / Spread": 8.84, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "01/03/2025", "29/05/2025", "29/08/2025", "29/11/2025",
    "01/03/2026", "29/05/2026", "29/08/2026", "29/11/2026",
    "01/03/2027", "29/05/2027"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 5 + [20] * 5),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DRES%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%20%2DAviso%20de%20Resultado%2028%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421%2FMPMAE%2DANU%2DON%20FCA%20CIA%20FINANCIERA%20CLASE%2020%2DSuplemento%2025%2D11%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F9421&p=true&ga=1"""
}
PZCDOj = {
    "Nombre Security": "ON Plaza Logistica S.R.L. Clase 12 Vto. 08 03 2026",
    "Código": "PZCDOj",
    "ISIN": "AR0571799615",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "08/03/2024",
    "Vencimiento": "08/03/2026",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": ["08/03/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call parcial o total a opción de la sociedad a partir del m21 de la emisión",
    "Fecha Call": "08/12/2025",
    "Precio Call": {"m14 en adelante: 1.01"},  # Precio Call
    "Comentarios": """ Plaza Logística podrá rescatar total o parcialmente anticipadamente, 
a su opción, las Obligaciones Negociables Clase 12, en cualquier momento a partir del tercer mes anterior a la Fecha de Vencimiento 
de las Obligaciones Negociables Clase 12, en forma total o parcial, al precio de rescate de capital de 101% sobre el valor nominal, 
y si bien las Obligaciones Negociables Clase 12 no devengaran intereses, en caso de corresponder, deberá adicionarse los intereses 
devengados y no pagados calculados hasta la fecha de rescate.""",
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990%2FMPMAE%2DRES%2D%20ON%20PLAZA%20LOGISTICA%20CLASE%2012%20Aviso%20de%20Resultado%2006%2D03%2D2024%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990&p=true&ga=1""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_ON/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990%2FMPMAE%2DANU%2DON%20PLAZA%20LOGISTICA%20CLASE%2012%2DSuplemento%2029%2D02%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FON%2FEmisionesON%2F8990&p=true&ga=1"""
}
RB60Oj = {
    "Nombre Security": "ON Rombo Compañia Financiera S.A. Clase 60 Vto 31 01 2027",
    "Código": "RB60Oj",
    "ISIN": "RB60Oj",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo UVA",
    "Industria": "Financials",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "31/01/2025",
    "Vencimiento": "31/01/2027",
    "Fecha Primer Cupón": "01/05/2025",
    "Cupón / Spread": 7.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "UVA PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -5, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -5,
    "Fechas de cupón": [
    "01/05/2025", 
    "31/07/2025", 
    "31/10/2025",
    "31/01/2026",
    "01/05/2026",
    "31/07/2026",
    "31/10/2026",
    "31/01/2027"], # Lista de fechas como ejemplo
    "Amortización":  ([0] * 4 + [25] * 4),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "UVA -5",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/ba01697d-e835-446d-a083-6ec1c1116909#""",
    "Suplemento Prospecto": """https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110%2FMPMAE%2DANU%2DON%20ROMBO%20CF%20SERIE%2059%2D60%2DSuplemento%20de%20Prospecto%2022%2D01%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FDocumentos%20compartidos%2FLicitaciones%2F2025%2D01%2F7110&p=true&ga=1"""
}

# SUBSOB BADLAR
BDC28 = {
    "Nombre Security": "Titulos de Deuda CABA Clase XXIII Vto 22 02 2028",
    "Código": "BDC28",
    "ISIN": "ARCBAS3201J5",
    "Calificación": "AA(arg)/PE",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2, # <- mismo orden hasta aca
    "Emisión": "22/11/2017",
    "Vencimiento":	"22/02/2028",
    "Cupón / Spread":	3.75, # <- a mano
    "Step-up": False, # si es True ingresar a mano la tira de Intereses
    "Frecuencia de pago de cupón anual": 4,
    "Convención fechas de pago": "Regular",
    "Convención de devengamiento":	"Actual",
    "Convención Base":	365,
    "Tipo de Amortización":	"BULLET",
    "Tipo Tasa Interés": "VARIABLE", # <- 2do bloque meismo orden
    "Index": "BADLAR",
    "Días Lag índice desde inc": -8,
    "Días Lag índice hasta inc": -8,
    "Valor Nominal": 100.,
    "Quote Price Convention": 'DIRTY',
    "Ajuste sobre Capital": None,
    "Factor Capitalización": 1.,
    "Días lag Ajuste base": None,
    "Días lag Ajuste": None,
    "Fechas de cupón": ['22/05/2018',
                        '22/08/2018',
                        '22/11/2018',
                        '22/02/2019',
                        '22/05/2019',
                        '22/08/2019',
                        '22/11/2019',
                        '22/02/2020',
                        '22/05/2020',
                        '22/08/2020',
                        '22/11/2020',
                        '22/02/2021',
                        '22/05/2021',
                        '22/08/2021',
                        '22/11/2021',
                        '22/02/2022',
                        '22/05/2022',
                        '22/08/2022',
                        '22/11/2022',
                        '22/02/2023',
                        '22/05/2023',
                        '22/08/2023',
                        '22/11/2023',
                        '22/02/2024',
                        '22/05/2024',
                        '22/08/2024',
                        '22/11/2024',
                        '22/02/2025',
                        '22/05/2025',
                        '22/08/2025',
                        '22/11/2025',
                        '22/02/2026',
                        '22/05/2026',
                        '22/08/2026',
                        '22/11/2026',
                        '22/02/2027',
                        '22/05/2027',
                        '22/08/2027',
                        '22/11/2027',
                        '22/02/2028']
    }
PMJ26 = {
    "Nombre Security": "Título de Deuda de la Provincia de Mendoza Clase I Vto 20 06 2026",
    "Código": "PMJ26",
    "ISIN": "AR0093201793",
    "Calificación": "A3(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/03/2025",
    "Vencimiento": "20/06/2026",
    "Fecha Primer Cupón": "20/06/2025",
    "Cupón / Spread": 4.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar, Tamar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -7, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -7,
    "Fechas de cupón": [
    "20/06/2025",
    "20/09/2025",
    "20/12/2025",
    "20/03/2026",
    "20/06/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total o parcial a partir del m12 desde la emisión",
    "Fecha Call": "20/03/2026",
    "Precio Call": "m12 en adelante: 1.00",  # Precio Call
    "Comentarios": """La Provincia podrá rescatar a su sola opción, en forma total o parcial, los respectivos Títulos de Deuda, en 
cualquier momento previo a la fecha de vencimiento de dichos respectivos Títulos de Deuda, según 
corresponda, pero siempre luego de transcurridos doce (12) meses desde la Fecha de Emisión y Liquidación 
de los respectivos Títulos de Deuda, notificando tal circunstancia a los tenedores mediante un aviso a ser 
publicado por la Provincia en el Boletín Diario de la BCBA, en el Boletín Diario de A3 Mercados y en el micro 
sitio web de colocaciones de A3 Mercados con no menos de treinta (30) días ni más de sesenta (60) días 
corridos de anticipación a dicho rescate.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586%2FMPA3%2DRES%2DTITULOS%20DE%20DEUDA%20PROV%2E%20MENDOZA%20CLASE%201%20Y%202%2DAviso%20de%20Resultados%2018%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586%2FMPA3%2DANU%2DTITULOS%20DE%20DEUDA%20PROV%2E%20MENDOZA%20CLASE%201%20Y%202%2DProspecto%2014%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586&p=true&ga=1"
}
PMD26 = {
    "Nombre Security": "Título de Deuda de la Provincia de Mendoza Clase II Vto 20 12 2026",
    "Código": "PMD26",
    "ISIN": "AR0769321784",
    "Calificación": "A3(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "20/03/2025",
    "Vencimiento": "20/12/2026",
    "Fecha Primer Cupón": "20/06/2025",
    "Cupón / Spread": 5.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "TAMAR", # Badlar, Tamar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -7, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -7,
    "Fechas de cupón": [
    "20/06/2025",
    "20/09/2025",
    "20/12/2025",
    "20/03/2026",
    "20/06/2026",
    "20/09/2026",
    "20/12/2026"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total o parcial a partir del m12 desde la emisión",
    "Fecha Call": "20/03/2026",
    "Precio Call": "m12 en adelante: 1.00",  # Precio Call
    "Comentarios": """La Provincia podrá rescatar a su sola opción, en forma total o parcial, los respectivos Títulos de Deuda, en 
cualquier momento previo a la fecha de vencimiento de dichos respectivos Títulos de Deuda, según 
corresponda, pero siempre luego de transcurridos doce (12) meses desde la Fecha de Emisión y Liquidación 
de los respectivos Títulos de Deuda, notificando tal circunstancia a los tenedores mediante un aviso a ser 
publicado por la Provincia en el Boletín Diario de la BCBA, en el Boletín Diario de A3 Mercados y en el micro 
sitio web de colocaciones de A3 Mercados con no menos de treinta (30) días ni más de sesenta (60) días 
corridos de anticipación a dicho rescate.""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586%2FMPA3%2DRES%2DTITULOS%20DE%20DEUDA%20PROV%2E%20MENDOZA%20CLASE%201%20Y%202%2DAviso%20de%20Resultados%2018%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586%2FMPA3%2DANU%2DTITULOS%20DE%20DEUDA%20PROV%2E%20MENDOZA%20CLASE%201%20Y%202%2DProspecto%2014%2D03%2D25%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9586&p=true&ga=1"
}

# SUBSOB UVA/CER
PMD25 = {
    "Nombre Security": "Título de Deuda de la Provincia de Mendoza 2025 Vto 14 12 2025",
    "Código": "PMD25",
    "ISIN": "AR0093201793",
    "Calificación": "A3(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/03/2024",
    "Vencimiento": "14/12/2025",
    "Fecha Primer Cupón": "14/12/2025",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "BULLET", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["14/12/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total o parcial a partir del m12 desde la emisión",
    "Fecha Call": "14/03/2025",
    "Precio Call": "m12 en adelante: 1.00",  # Precio Call
    "Comentarios": """La Provincia podrá rescatar a su sola opción, en forma total o parcial, los Títulos de Deuda, en cualquier momento previo a 
la respectiva Fecha de Vencimiento de los Títulos de Deuda, pero siempre luego de transcurridos doce (12) meses desde la 
Fecha de Emisión y Liquidación de los Títulos de Deuda""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004%2FMPMAE%2DRES%2DTP%20TITULOS%20DEUDA%20CER%20MENDOZA%20CLASES%201%2D2%20y%20VTO%202025%2DAviso%20de%20Resultados%2012%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004%2FMPMAE%2DANU%2DTP%20TITULOS%20DEUDA%20CER%20MENDOZA%20CLASES%201%2D2%20y%20VTO%202025%2DProspecto%2011%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004&p=true&ga=1"
}
PMM27 = {
    "Nombre Security": "Título de Deuda de la Provincia de Mendoza 2027 Vto 14 12 2027",
    "Código": "PMM27",
    "ISIN": "AR0970492929",
    "Calificación": "A3(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "14/03/2024",
    "Vencimiento": "14/03/2027",
    "Fecha Primer Cupón": "14/03/2027",
    "Cupón / Spread": 0., # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "ISMA-30", # Actual, ISMA-30, NASD-30
    "Convención Base": 360., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": [
    "14/06/2024", "14/09/2024", "14/12/2024", "14/03/2025",
    "14/06/2025", "14/09/2025", "14/12/2025", "14/03/2026",
    "14/06/2026", "14/09/2026", "14/12/2026", "14/03/2027"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [33.33] + [33.33] + [33.34]),
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Rescate total o parcial a partir del m12 desde la emisión",
    "Fecha Call": "14/03/2025",
    "Precio Call": "m12 en adelante: 1.00",  # Precio Call
    "Comentarios": """La Provincia podrá rescatar a su sola opción, en forma total o parcial, los Títulos de Deuda, en cualquier momento previo a 
la respectiva Fecha de Vencimiento de los Títulos de Deuda, pero siempre luego de transcurridos doce (12) meses desde la 
Fecha de Emisión y Liquidación de los Títulos de Deuda""",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004%2FMPMAE%2DRES%2DTP%20TITULOS%20DEUDA%20CER%20MENDOZA%20CLASES%201%2D2%20y%20VTO%202025%2DAviso%20de%20Resultados%2012%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004%2FMPMAE%2DANU%2DTP%20TITULOS%20DEUDA%20CER%20MENDOZA%20CLASES%201%2D2%20y%20VTO%202025%2DProspecto%2011%2D03%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9004&p=true&ga=1"
}
COY27 = {
    "Nombre Security": "Titulo de Deuda de la Provincia de Cordoba Clase 2 Vto 04 05 2027",
    "Código": "COY27",
    "ISIN": "AR0401732018",
    "Calificación": "A.ar(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "24/05/2024",
    "Vencimiento": "24/05/2027",
    "Fecha Primer Cupón": "24/11/2024",
    "Cupón / Spread": 4.50, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10., # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10.,
    "Fechas de cupón": [
    "24/11/2024",
    "24/05/2025",
    "24/11/2025",
    "24/05/2026",
    "24/11/2026",
    "24/05/2027"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [25] + [75]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9090%2FMPMAE%2DRES%2DTP%20TITULOS%20DE%20DEUDA%20PROVINCIA%20DE%20CORDOBA%20CLASES%20%201%2D2%2DAviso%20de%20Resultados%2022%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9090&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9090%2FMPMAE%2DANU%2DTP%20TITULOS%20DE%20DEUDA%20PROVINCIA%20DE%20CORDOBA%20CLASES%20%201%2D2%2DSuplemento%20de%20Prospecto%2020%2D05%2D24%2Epdf&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9090&p=true&ga=1"
}
COD7P = {
    "Nombre Security": "Titulo de Deuda de la Provincia de Cordoba Clase 3  Vto 05 12 2027",
    "Código": "COD7P",
    "ISIN": "COD7P",
    "Calificación": "A.ar(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "05/12/2024",
    "Vencimiento": "05/12/2027",
    "Fecha Primer Cupón": "05/06/2025",
    "Cupón / Spread": 9.75, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "FIJA", # FIJA o VARIABLE
    "Index": None, # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": 0, # enteros negativos
    "Días Lag índice hasta inc": 0, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10., # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10.,
    "Fechas de cupón": [
    "05/06/2025",
    "05/12/2025",
    "05/06/2026",
    "05/12/2026",
    "05/06/2027",
    "05/12/2027"
], # Lista de fechas como ejemplo
    "Amortización": ([0] * 4 + [25] + [75]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9417%2FMPMAE%2D3%2EPDF&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9417&p=true&ga=1",
    "Suplemento Prospecto": "https://mercadoabierto.sharepoint.com/sites/mae-archivos-publicos/Emisiones_TP/Forms/AllItems.aspx?id=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9417%2FMPMAE%2D2%2EPDF&parent=%2Fsites%2Fmae%2Darchivos%2Dpublicos%2FEmisiones%5FTP%2FEmisionesTP%2F9417&p=true&ga=1"
}
SFN27 = {
    "Nombre Security": "Título de Deuda de la Provincia de Santa Fe 2027 Vto 25 11 2027",
    "Código": "SFN27",
    "ISIN": "AR0810026069",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1., # debe ser un entero
    "Emisión": "25/11/2024",
    "Vencimiento": "25/11/2027",
    "Fecha Primer Cupón": "25/12/2025",
    "Cupón / Spread": 6.40, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 4., # entero ej semianual = 2, trimestral = 4
    "Convención fechas de pago": "Regular", # "Regular" o "Presonalizado"
    "Convención de devengamiento": "Actual", # Actual, ISMA-30, NASD-30
    "Convención Base": 365., # 365 o 360
    "Tipo de Amortización": "AMORTIZABLE", # AMORTIZBALE O BULLET
    "Tipo Tasa Interés": "VARIABLE", # FIJA o VARIABLE
    "Index": "BADLAR", # Badlar o el que sea hasta ahora solo se implementó badlar
    "Días Lag índice desde inc": -10, # enteros negativos
    "Días Lag índice hasta inc": -10, # enteros negativos
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None, # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": None, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": None,
    "Fechas de cupón": ["25/02/2025",
                        "25/05/2025",
                        "25/08/2025",
                        "25/11/2025",
                        "25/02/2026",
                        "25/05/2026",
                        "25/08/2026",
                        "25/11/2026",
                        "25/02/2027",
                        "25/05/2027",
                        "25/08/2027",
                        "25/11/2027"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 7 + [33.33] + [0] + [33.33] + [0] + [33.34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "",
    "Suplemento Prospecto": ""
}

##### Definiciones de bonos #####

# CORPORATIVOS TASA FIJA
FTL2O = rentafija.Bono(FTL2O)
BFCWO = rentafija.Bono(BFCWO)
BYCPO = rentafija.Bono(BYCPO)
PSSVO = rentafija.Bono(PSSVO)
PSSZO = rentafija.Bono(PSSZO)

# CORPORATIVOS BADLAR
CWS1P = rentafija.Bono(CWS1P)
VWCBO = rentafija.Bono(VWCBO)
RB57O = rentafija.Bono(RB57O)
ICC1O = rentafija.Bono(ICC1O)
RCCPO = rentafija.Bono(RCCPO)
DHS9O = rentafija.Bono(DHS9O)
BPCHO = rentafija.Bono(BPCHO)
TYCZO = rentafija.Bono(TYCZO)
DNC6O = rentafija.Bono(DNC6O)
BDCJO = rentafija.Bono(BDCJO)
OZC4O = rentafija.Bono(OZC4O)
LN21P = rentafija.Bono(LN21P)

# SOBERANOS TAMAR
M31L5 = rentafija.Bono(M31L5)

# CORPORATIVOS TAMAR
HBC8O = rentafija.Bono(HBC8O)
T643O = rentafija.Bono(T643O)
HBC9O = rentafija.Bono(HBC9O)
BYCLO = rentafija.Bono(BYCLO)
BYCQO = rentafija.Bono(BYCQO)
PSSWO = rentafija.Bono(PSSWO)
RB59O = rentafija.Bono(RB59O)
BCCJO = rentafija.Bono(BCCJO)
BNCUO = rentafija.Bono(BNCUO)
BPCLO = rentafija.Bono(BPCLO)
BYCMO = rentafija.Bono(BYCMO)
RCCQO = rentafija.Bono(RCCQO)
RCCTO = rentafija.Bono(RCCTO)
RVS1O = rentafija.Bono(RVS1O)
BF34O = rentafija.Bono(BF34O)
MR42O = rentafija.Bono(MR42O)
PSSYO = rentafija.Bono(PSSYO)
PN39O = rentafija.Bono(PN39O)
LNS3P = rentafija.Bono(LNS3P)

# CORPORATIVOS UVA
TLCJO = rentafija.Bono(TLCJO)
TLCJOj = rentafija.Bono(TLCJOj)
PZCDO = rentafija.Bono(PZCDO)
PZCDOj = rentafija.Bono(PZCDOj)
FTL1O = rentafija.Bono(FTL1O)
FTL1Oj = rentafija.Bono(FTL1Oj)
RB60O = rentafija.Bono(RB60O)
RB60Oj = rentafija.Bono(RB60Oj)
RCCIO = rentafija.Bono(RCCIO)
RCCIOj = rentafija.Bono(RCCIOj)
PSSXO = rentafija.Bono(PSSXO)
PSSXOj = rentafija.Bono(PSSXOj)

# CORPORATIVOS DOLAR LINKED
TLCKO = rentafija.Bono(TLCKO)
PNRCO = rentafija.Bono(PNRCO)
FOS2O = rentafija.Bono(FOS2O)
TLCDO = rentafija.Bono(TLCDO)
SNS8O = rentafija.Bono(SNS8O)
SNS9O = rentafija.Bono(SNS9O)
OLC1O = rentafija.Bono(OLC1O)
GN39O = rentafija.Bono(GN39O)
GN41O = rentafija.Bono(GN41O)
CAC3O = rentafija.Bono(CAC3O)
CAC6O = rentafija.Bono(CAC6O)
AER5O = rentafija.Bono(AER5O)
GN37O = rentafija.Bono(GN37O)
CS40O = rentafija.Bono(CS40O)
LMS4O = rentafija.Bono(LMS4O)
PZCAO = rentafija.Bono(PZCAO)
AER7O = rentafija.Bono(AER7O)
OTS1O = rentafija.Bono(OTS1O)
PNFCO = rentafija.Bono(PNFCO)
AE10O = rentafija.Bono(AE10O)
LTS1P = rentafija.Bono(LTS1P)
CS42O = rentafija.Bono(CS42O)
RFCBO = rentafija.Bono(RFCBO)
CP33O = rentafija.Bono(CP33O)
RE3BO = rentafija.Bono(RE3BO)
PNJCO = rentafija.Bono(PNJCO)
PNZCO = rentafija.Bono(PNZCO)
TBC9O = rentafija.Bono(TBC9O)
YMCMO = rentafija.Bono(YMCMO)
YMCWO = rentafija.Bono(YMCWO)
RMS3P = rentafija.Bono(RMS3P)
RMS3Preestructurado = rentafija.Bono(RMS3Preestructurado)
VSCKO = rentafija.Bono(VSCKO)
MGCEO = rentafija.Bono(MGCEO)
PNICO = rentafija.Bono(PNICO)
CAC4O = rentafija.Bono(CAC4O)
CAC7O = rentafija.Bono(CAC7O)
PN7CO = rentafija.Bono(PN7CO)
OLC2O = rentafija.Bono(OLC2O)
CIC3O = rentafija.Bono(CIC3O)
TLCLO = rentafija.Bono(TLCLO)
RZ7BO = rentafija.Bono(RZ7BO)
TLCHO = rentafija.Bono(TLCHO)
MR36O = rentafija.Bono(MR36O)
MR40O = rentafija.Bono(MR40O)
VSCMO = rentafija.Bono(VSCMO)
GN44O = rentafija.Bono(GN44O)
AER9O = rentafija.Bono(AER9O)
MSSBO = rentafija.Bono(MSSBO)
VSCJO = rentafija.Bono(VSCJO)
SNAAO = rentafija.Bono(SNAAO)
VSCIO = rentafija.Bono(VSCIO)
CWC3O = rentafija.Bono(CWC3O)
MRCBO = rentafija.Bono(MRCBO)
YFCDO = rentafija.Bono(YFCDO)
PQCKO = rentafija.Bono(PQCKO)
CP28O = rentafija.Bono(CP28O)
TLCFO = rentafija.Bono(TLCFO)
TLCGO = rentafija.Bono(TLCGO)
OLC3O = rentafija.Bono(OLC3O)
RZ9AO = rentafija.Bono(RZ9AO)
YFCHO = rentafija.Bono(YFCHO)
VSCQO = rentafija.Bono(VSCQO)
RZ8BO = rentafija.Bono(RZ8BO)
LMS6O = rentafija.Bono(LMS6O)
DRS9O = rentafija.Bono(DRS9O)
VSCHO = rentafija.Bono(VSCHO)
YMCTO = rentafija.Bono(YMCTO)
PEC7O = rentafija.Bono(PEC7O)
LUC4O = rentafija.Bono(LUC4O)
PEC6O = rentafija.Bono(PEC6O)
PEC8O = rentafija.Bono(PEC8O)
PNECO = rentafija.Bono(PNECO)
PN40O = rentafija.Bono(PN40O)
LUC3O = rentafija.Bono(LUC3O)
PEC4O = rentafija.Bono(PEC4O)
YFCFO = rentafija.Bono(YFCFO)
OLC4O = rentafija.Bono(OLC4O)
YMCRO = rentafija.Bono(YMCRO)
GN46O = rentafija.Bono(GN46O)
GN42O = rentafija.Bono(GN42O)
CACAO = rentafija.Bono(CACAO)
PQCQO = rentafija.Bono(PQCQO)
HJCEO = rentafija.Bono(HJCEO)
VSCBO = rentafija.Bono(VSCBO)
YFCAO = rentafija.Bono(YFCAO)
FOS3O = rentafija.Bono(FOS3O)
PEC1O = rentafija.Bono(PEC1O)
PQCHO = rentafija.Bono(PQCHO)
CP35O = rentafija.Bono(CP35O)
GN35O = rentafija.Bono(GN35O)
LIC5O = rentafija.Bono(LIC5O)
LIC3O = rentafija.Bono(LIC3O)
HJCAO = rentafija.Bono(HJCAO)
PQCOO = rentafija.Bono(PQCOO)
PEC2O = rentafija.Bono(PEC2O)
CP31O = rentafija.Bono(CP31O)
RZ6BO = rentafija.Bono(RZ6BO)
PECHO = rentafija.Bono(PECHO)
RZAAO = rentafija.Bono(RZAAO)
CS46O = rentafija.Bono(CS46O)

# CORPORATIVOS HARD DOLAR
TSC3O = rentafija.Bono(TSC3O)
MGC3O = rentafija.Bono(MGC3O)
T642O = rentafija.Bono(T642O)
YMCJO = rentafija.Bono(YMCJO)
YM34O = rentafija.Bono(YM34O)
ARC1O = rentafija.Bono(ARC1O)
MGC9O = rentafija.Bono(MGC9O)
GNCXO = rentafija.Bono(GNCXO)
TLC1O = rentafija.Bono(TLC1O)
TLC5O = rentafija.Bono(TLC5O)
YFCJO = rentafija.Bono(YFCJO)
PNDCO = rentafija.Bono(PNDCO)
AEC2O = rentafija.Bono(AEC2O)
BYC2O = rentafija.Bono(BYC2O)
TTCAO = rentafija.Bono(TTCAO)
VSCTO = rentafija.Bono(VSCTO)
BYCHO = rentafija.Bono(BYCHO)
BYCOO = rentafija.Bono(BYCOO)
PN38O = rentafija.Bono(PN38O)
YCAMO = rentafija.Bono(YCAMO)
CAC5O = rentafija.Bono(CAC5O)
BACAO = rentafija.Bono(BACAO)
MTCGO = rentafija.Bono(MTCGO)
YMCHO = rentafija.Bono(YMCHO)
PNXCO = rentafija.Bono(PNXCO)
PLC4O = rentafija.Bono(PLC4O)
YMCXO = rentafija.Bono(YMCXO)
IRCFO = rentafija.Bono(IRCFO)
YMCUO = rentafija.Bono(YMCUO)
YMC1O = rentafija.Bono(YMC1O)
MGCOO = rentafija.Bono(MGCOO)
RUCDO = rentafija.Bono(RUCDO)
TLCMO = rentafija.Bono(TLCMO)
LMS8O = rentafija.Bono(LMS8O)
LMS9O = rentafija.Bono(LMS9O)
IRCPO = rentafija.Bono(IRCPO)
VSCOO = rentafija.Bono(VSCOO)
VSCUO = rentafija.Bono(VSCUO)
VSCVO = rentafija.Bono(VSCVO)

# CORPORATIVOS HARD DOLAR MEP
PECBO = rentafija.Bono(PECBO)
BPCKO = rentafija.Bono(BPCKO)
BVCMO = rentafija.Bono(BVCMO)
BCCIO = rentafija.Bono(BCCIO)
OZC3O = rentafija.Bono(OZC3O)
PECIO = rentafija.Bono(PECIO)
PN36O = rentafija.Bono(PN36O)
VSCRO = rentafija.Bono(VSCRO)
PLC1O = rentafija.Bono(PLC1O)
PLC2O = rentafija.Bono(PLC2O)
PLC3O = rentafija.Bono(PLC3O)
OT42O = rentafija.Bono(OT42O)
PQCSO = rentafija.Bono(PQCSO)
TTC9O = rentafija.Bono(TTC9O)
IRCOO = rentafija.Bono(IRCOO)
PN35O = rentafija.Bono(PN35O)
VSCPO = rentafija.Bono(VSCPO)
LOC2O = rentafija.Bono(LOC2O)
GOC4O = rentafija.Bono(GOC4O)
EAC3O = rentafija.Bono(EAC3O)
YFCLO = rentafija.Bono(YFCLO)
TLCOO = rentafija.Bono(TLCOO)
CACBO = rentafija.Bono(CACBO)
YM35O = rentafija.Bono(YM35O)
YM36O = rentafija.Bono(YM36O)
YM37O = rentafija.Bono(YM37O)
BFCYO = rentafija.Bono(BFCYO)
PUC2O = rentafija.Bono(PUC2O)
BFCZO = rentafija.Bono(BFCZO)
T641O = rentafija.Bono(T641O)
GN48O = rentafija.Bono(GN48O)
ZZC1O = rentafija.Bono(ZZC1O)
GYC5O = rentafija.Bono(GYC5O)
BYCNO = rentafija.Bono(BYCNO)
YMCVO = rentafija.Bono(YMCVO)
CS47O = rentafija.Bono(CS47O)
PNWCO = rentafija.Bono(PNWCO)
PN37O = rentafija.Bono(PN37O)
CIC8O = rentafija.Bono(CIC8O)
CIC9O = rentafija.Bono(CIC9O)
CS38O = rentafija.Bono(CS38O)
CRCLO = rentafija.Bono(CRCLO)
PECGO = rentafija.Bono(PECGO)
TN63O = rentafija.Bono(TN63O)
NBS1O = rentafija.Bono(NBS1O)
PQCRO = rentafija.Bono(PQCRO)
HJCGO = rentafija.Bono(HJCGO)
YMCYO = rentafija.Bono(YMCYO)
YMCZO = rentafija.Bono(YMCZO)
MGCNO = rentafija.Bono(MGCNO)
OLC5O = rentafija.Bono(OLC5O)
DNC5O = rentafija.Bono(DNC5O)
PZCGO = rentafija.Bono(PZCGO)
HJCHO = rentafija.Bono(HJCHO)
MRCYO = rentafija.Bono(MRCYO)
MRCUO = rentafija.Bono(MRCUO)
CRCJO = rentafija.Bono(CRCJO)
RZABO = rentafija.Bono(RZABO)
RZ9BO = rentafija.Bono(RZ9BO)
LECEO = rentafija.Bono(LECEO)
XMC1O = rentafija.Bono(XMC1O)
MSSFO = rentafija.Bono(MSSFO)
MGCLO = rentafija.Bono(MGCLO)
RCCRO = rentafija.Bono(RCCRO)
TTC7O = rentafija.Bono(TTC7O)
TTC8O = rentafija.Bono(TTC8O)
IRCNO = rentafija.Bono(IRCNO)
PN34O = rentafija.Bono(PN34O)
LDCGO = rentafija.Bono(LDCGO)
CP36O = rentafija.Bono(CP36O)
CP37O = rentafija.Bono(CP37O)
MR35O = rentafija.Bono(MR35O)
YFCIO = rentafija.Bono(YFCIO)
PECAO = rentafija.Bono(PECAO)
IRCJO = rentafija.Bono(IRCJO)
IRCLO = rentafija.Bono(IRCLO)
SNSDO = rentafija.Bono(SNSDO)
HJCFO = rentafija.Bono(HJCFO)
HJCIO = rentafija.Bono(HJCIO)
CS44O = rentafija.Bono(CS44O)
YMCQO = rentafija.Bono(YMCQO)
DNC3O = rentafija.Bono(DNC3O)
CIC7O = rentafija.Bono(CIC7O)
SIC1O = rentafija.Bono(SIC1O)
SNSBO = rentafija.Bono(SNSBO)
JNC5O = rentafija.Bono(JNC5O)
CS45O = rentafija.Bono(CS45O)
AERBO = rentafija.Bono(AERBO)
YFCKO = rentafija.Bono(YFCKO)
LIC6O = rentafija.Bono(LIC6O)

# SOBS
S10L5 = rentafija.Bono(S10L5)
S31L5 = rentafija.Bono(S31L5)
S15G5 = rentafija.Bono(S15G5)
S29G5 = rentafija.Bono(S29G5)
S12S5 = rentafija.Bono(S12S5)
S30S5 = rentafija.Bono(S30S5)
T17O5 = rentafija.Bono(T17O5)
S31O5 = rentafija.Bono(S31O5)
S10N5 = rentafija.Bono(S10N5)
S28N5 = rentafija.Bono(S28N5)
T15D5 = rentafija.Bono(T15D5)
T30E6 = rentafija.Bono(T30E6)
T13F6 = rentafija.Bono(T13F6)
S29Y6 = rentafija.Bono(S29Y6)
T30J6 = rentafija.Bono(T30J6)
TTM26 = rentafija.Bono(TTM26)
TTJ26 = rentafija.Bono(TTJ26)
TO26 = rentafija.Bono(TO26)
TTS26 = rentafija.Bono(TTS26)
TTD26 = rentafija.Bono(TTD26)
TTM26v = rentafija.Bono(TTM26v)
TTJ26v = rentafija.Bono(TTJ26v)
TTS26v = rentafija.Bono(TTS26v)
TTD26v = rentafija.Bono(TTD26v)
T15E7 = rentafija.Bono(T15E7)
TY30P = rentafija.Bono(TY30P)
TZXO5 = rentafija.Bono(TZXO5)
TZXD5 = rentafija.Bono(TZXD5)
TZXM6 = rentafija.Bono(TZXM6)
TZX26 = rentafija.Bono(TZX26)
TZXO6 = rentafija.Bono(TZXO6)
TZXD6 = rentafija.Bono(TZXD6)
TZXM7 = rentafija.Bono(TZXM7)
TZX27 = rentafija.Bono(TZX27)
TZXD7 = rentafija.Bono(TZXD7)
TZX28 = rentafija.Bono(TZX28)
TX25j = rentafija.Bono(TX25j)
TX26j = rentafija.Bono(TX26j)
TZX26j = rentafija.Bono(TZX26j)
TZX27j = rentafija.Bono(TZX27j)
TZXM7j = rentafija.Bono(TZXM7j)
TZXO5j = rentafija.Bono(TZXO5j)
TZXD5j = rentafija.Bono(TZXD5j)
TZXM6j = rentafija.Bono(TZXM6j)
TZXD6j = rentafija.Bono(TZXD6j)
TZXD7j = rentafija.Bono(TZXD7j)
TZX28j = rentafija.Bono(TZX28j)
TG25 = rentafija.Bono(TG25)
TX25 = rentafija.Bono(TX25)
TX26 = rentafija.Bono(TX26)
TX28 = rentafija.Bono(TX28)
DICP = rentafija.Bono(DICP)
PARP = rentafija.Bono(PARP)
CUAP = rentafija.Bono(CUAP)
TZV25 = rentafija.Bono(TZV25)
TZVD5 = rentafija.Bono(TZVD5)
D16E6 = rentafija.Bono(D16E6)
TZV26 = rentafija.Bono(TZV26)
TZV27 = rentafija.Bono(TZV27)

GD29 = rentafija.Bono(GD29)
GD30 = rentafija.Bono(GD30)
GD35 = rentafija.Bono(GD35)
GD38 = rentafija.Bono(GD38)
GD41 = rentafija.Bono(GD41)
GD46 = rentafija.Bono(GD46)
AL29 = rentafija.Bono(AL29)
AL30 = rentafija.Bono(AL30)
AL35 = rentafija.Bono(AL35)
AE38 = rentafija.Bono(AE38)
AL41 = rentafija.Bono(AL41)

# SUBSOB BADLAR
BDC28 = rentafija.Bono(BDC28)
PMJ26 = rentafija.Bono(PMJ26)
PMD26 = rentafija.Bono(PMD26)

# SUBSOB CER/UVA
PMD25 = rentafija.Bono(PMD25)
PMM27 = rentafija.Bono(PMM27)
COY27 = rentafija.Bono(COY27)
COD7P = rentafija.Bono(COD7P)
SFN27 = rentafija.Bono(SFN27)

todos_los_bonos = [S31L5, S15G5, S29G5, S12S5, 
    S30S5, T17O5, S31O5, S10N5, S28N5, T15D5, T30E6, T13F6, T30J6, T15E7, TG25, TX25, TX26, TZXO5, TZXD5,  
    TZXM6, TZXO6, TZX26, TZXD6, TZXM7, TZX27, TZXD7, TX28, DICP, PARP, CUAP, TTM26, TTJ26, TTS26, TTD26,
    TX25j, TX26j, TZXD5j, TZXM6j, TZX26j, TZXD6j, TZX27j, TZXD7j, TZX28j, TZXM7j
]

# Precios BYMA


