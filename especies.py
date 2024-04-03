#%% Bonos:
import rentafija
from utils import *

#%% Overrides
# ------Override A3500 hoy ------:
# Fecha específica y dato que desea modificar
# Modificar el valor para esa fecha específica en la columna 'tca3500'
fecha_especifica_override = '2024-03-27'
a3500_override = 857.50
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
S31E5 = {
    "Nombre Security": "S31E5 (lecap Enero 25)",
    "Código": "S31E5",
    "ISIN": "S31E5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Letras Zero Cupón (Ledes y Letes)",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "25/03/2024",
    "Vencimiento": "31/01/2025",
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
    "Factor Capitalización": (1+0.055)**((306/360)*12), # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": 0, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": 0,
    "Fechas de cupón": ['31/01/2025'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
X20Y4 = {
    "Nombre Security": "X20Y4 (lecer mayo)",
    "Código": "X20Y4",
    "ISIN": "AR0125910452",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/01/2024",
    "Vencimiento": "20/05/2024",
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
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['20/05/2024'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
X20Y4j = {
    "Nombre Security": "X20Y4 (lecer mayo)",
    "Código": "X20Y4j",
    "ISIN": "AR0125910452",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/01/2024",
    "Vencimiento": "20/05/2024",
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
    "Ajuste sobre Capital": "CER PROYECTADO", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 1., # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ['20/05/2024'], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PBY24 = {
    "Nombre Security": "Título de Deuda de la Provincia de Buenos Aires Vto 16 05 2024",
    "Código": "PBY24",
    "ISIN": "ARPBUE320BB9",
    "Calificación": "CCC",
    "País": "Argentina",
    "Clasificación": "Sub-soberano",
    "Industria": "Soberano ARS",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2, # <- mismo orden hasta aca
    "Emisión": "16/05/2022",
    "Vencimiento":	"16/05/2024",
    "Cupón / Spread":	6.5, # <- a mano
    "Step-up": False, # si es True ingresar a mano la tira de Intereses
    "Frecuencia de pago de cupón anual": 4,
    "Convención fechas de pago": "Regular",
    "Convención de devengamiento":	"Actual",
    "Convención Base":	365,
    "Tipo de Amortización":	"BULLET",
    "Tipo Tasa Interés": "VARIABLE", # <- 2do bloque meismo orden
    "Index": "BADLAR",
    "Días Lag índice desde inc": -10,
    "Días Lag índice hasta inc": -10,
    "Valor Nominal": 100.,
    "Quote Price Convention": "DIRTY",
    "Ajuste sobre Capital": None,
    "Factor Capitalización": 1.,
    "Días lag Ajuste base": None,
    "Días lag Ajuste": None,
    "Fechas de cupón": ["16/05/2022","16/08/2022","16/11/2022","16/02/2023",
                        "16/05/2023","16/08/2023","16/11/2023","16/02/2024",
                        "16/05/2024"]
    }
TV24 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 30 04 2024",
    "Código": "tv24",
    "ISIN": "ARARGE320C18",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/04/2022",
    "Vencimiento": "30/04/2024",
    "Fecha Primer Cupón": "30/10/2022",
    "Cupón / Spread": 0.4, # es un nro flotante
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/10/2022", "30/04/2023", "30/10/2023", "30/04/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T2V4 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 30 09 2024",
    "Código": "t2v4",
    "ISIN": "ARARGE320DR8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "19/05/2023",
    "Vencimiento": "30/09/2024",
    "Fecha Primer Cupón": "30/09/2023",
    "Cupón / Spread": 0.5, # es un nro flotante
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "30/09/2023", "30/03/2024", "30/09/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TV25 = {
    "Nombre Security": "Bono del Tesoro Vinculado al Dólar Vto 31 03 2025",
    "Código": "tv25",
    "ISIN": "ARARGE320EC8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dolar Linked",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/09/2023",
    "Vencimiento": "31/03/2025",
    "Fecha Primer Cupón": "31/03/2024",
    "Cupón / Spread": 0.5, # es un nro flotante
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": [
    "31/03/2024", "30/09/2024", "31/03/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}

TDA24 = {
    "Nombre Security": "Bono Soberano Dual abril 2024 al DollarLinked",
    "Código": "tda24",
    "ISIN": "ARARGE320DO5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "28/04/2023",
    "Vencimiento": "30/04/2024",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2, # entero ej semianual = 2, trimestral = 4
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/04/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
"""
TDA24_C = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "TDA24_C",
    "ISIN": "ARARGE320DO5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "28/04/2023",
    "Vencimiento": "30/04/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 3.25, # es un nro flotante
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
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 220.8733, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/04/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}"""
TDJ24 = {
    "Nombre Security": "Bono Soberano Dual junio 2024 al DollarLinked",
    "Código": "tdj24",
    "ISIN": "ARARGE320EB0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/09/2023",
    "Vencimiento": "30/06/2024",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2, # entero ej semianual = 2, trimestral = 4
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/06/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDJ24_C = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "TDJ24_C",
    "ISIN": "ARARGE320EB0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "18/09/2023",
    "Vencimiento": "30/06/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 3.25, # es un nro flotante
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
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 349.975, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/06/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDG24 = {
    "Nombre Security": "Bono Soberano Dual agosto 2024 al DollarLinked",
    "Código": "tdg24",
    "ISIN": "ARARGE320DW8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "30/08/2024",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2, # entero ej semianual = 2, trimestral = 4
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["30/08/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDG24_C = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "TDG24_C",
    "ISIN": "ARARGE320DW8",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "30/08/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 3.25, # es un nro flotante
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
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 244.3333, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["30/08/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDN24 = {
    "Nombre Security": "Bono Soberano Dual noviembre 2024 al DollarLinked",
    "Código": "TDN24",
    "ISIN": "ARARGE320DX6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "29/11/2024",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 2, # entero ej semianual = 2, trimestral = 4
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["29/11/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDN24_C = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "TDN24_C",
    "ISIN": "ARARGE320DX6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "29/11/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 3.25, # es un nro flotante
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
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 244.3333, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["29/11/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDE25 = {
    "Nombre Security": "Bono Soberano Dual enero 2025 al DollarLinked",
    "Código": "TDE25",
    "ISIN": "ARARGE320DY4",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "31/01/2025",
    "Cupón / Spread": 0, # es un nro flotante
    "Step-up": False, # Es binario True or False
    "Frecuencia de pago de cupón anual": 0, # entero ej semianual = 2, trimestral = 4
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
    "Días lag Ajuste base": -3, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["31/01/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TDE25_C = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "TDE25_C",
    "ISIN": "ARARGE320DY4",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberanos Dual",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "31/01/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 3.25, # es un nro flotante
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
    "Valor Nominal": 100,
    "Ajuste sobre Capital": "CER", # None, "CER", "CER PROYECTADO", "A3500, "A3500 PROYECTADO"
    "Factor Capitalización": 244.3333, # Factor de ajuste, por defecto 1
    "Días lag Ajuste base": -10, # Usualmente es -10 con CER o -5 con UVA
    "Días lag Ajuste": -10,
    "Fechas de cupón": ["31/01/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T2X4 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "T2X4",
    "ISIN": "ARARGE320AI3",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "26/02/2021",
    "Vencimiento": "26/07/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 1.55, # es un nro flotante
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
    "Fechas de cupón": [
    "26/07/2021",
    "26/01/2022",
    "26/07/2022",
    "26/01/2023",
    "26/07/2023",
    "26/01/2024",
    "26/07/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T2X4j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 1.55% Vto 26 07 24",
    "Código": "T2X4j",
    "ISIN": "ARARGE320AI3",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "26/02/2021",
    "Vencimiento": "26/07/2024",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 1.55, # es un nro flotante
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
    "Fechas de cupón": [
    "26/07/2021",
    "26/01/2022",
    "26/07/2022",
    "26/01/2023",
    "26/07/2023",
    "26/01/2024",
    "26/07/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T3X4j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 3,75 Vto. 14 04 2024",
    "Código": "T3X4j",
    "ISIN": "ARARGE320DG1",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/04/2024",
    "Fecha Primer Cupón": "14/10/2023",
    "Cupón / Spread": 3.75, # es un nro flotante
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
    "Fechas de cupón": [
    "14/10/2023",
    "14/04/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T3X4 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 3,75 Vto. 14 04 2024",
    "Código": "T3X4",
    "ISIN": "ARARGE320DG1",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/04/2024",
    "Fecha Primer Cupón": "14/10/2023",
    "Cupón / Spread": 3.75, # es un nro flotante
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
    "Fechas de cupón": [
    "14/10/2023",
    "14/04/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T6X4 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 3.75% Vto 20 05 2024",
    "Código": "T6X4",
    "ISIN": "ARARGE320E65",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/08/2023",
    "Vencimiento": "20/05/2024",
    "Fecha Primer Cupón": "20/11/2023",
    "Cupón / Spread": 3.75, # es un nro flotante
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
    "Fechas de cupón": [
    "20/11/2023",
    "20/05/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T6X4j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 3.75% Vto 20 05 2024",
    "Código": "T6X4j",
    "ISIN": "ARARGE320E65",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/08/2023",
    "Vencimiento": "20/05/2024",
    "Fecha Primer Cupón": "20/11/2023",
    "Cupón / Spread": 3.75, # es un nro flotante
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
    "Fechas de cupón": [
    "20/11/2023",
    "20/05/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T7X4 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4% Vto 19 08 2024*",
    "Código": "T7X4",
    "ISIN": "ARARGE320E73",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/08/2023",
    "Vencimiento": "19/08/2024",
    "Fecha Primer Cupón": "19/02/2024",
    "Cupón / Spread": 4., # es un nro flotante
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
    "Fechas de cupón": [
    "19/02/2024",
    "19/08/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T4X4 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4% Vto. 14 10 2024",
    "Código": "T4X4",
    "ISIN": "ARARGE320DH9",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/10/2024",
    "Fecha Primer Cupón": "14/10/2023",
    "Cupón / Spread": 4., # es un nro flotante
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
    "Fechas de cupón": [
    "14/10/2023",
    "14/04/2024",
    "14/10/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T5X4 = {
    "Nombre Security": "Bono del Tesoro en Pesos Ajustado por CER Vto. 13 12 2024",
    "Código": "T5X4",
    "ISIN": "ARARGE320DV0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "13/12/2024",
    "Fecha Primer Cupón": "13/12/2023",
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": [
    "13/12/2023",
    "13/06/2024",
    "13/12/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T2X5 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4,25% Vto. 14 02 2025",
    "Código": "T2X5",
    "ISIN": "ARARGE320DI7",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/02/2025",
    "Fecha Primer Cupón": "14/08/2023",
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": [
    "14/08/2023",
    "14/02/2024",
    "14/08/2024",
    "14/02/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T7X4j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4% Vto 19 08 2024*",
    "Código": "T7X4j",
    "ISIN": "ARARGE320E73",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/08/2023",
    "Vencimiento": "19/08/2024",
    "Fecha Primer Cupón": "19/02/2024",
    "Cupón / Spread": 4., # es un nro flotante
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
    "Fechas de cupón": [
    "19/02/2024",
    "19/08/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T4X4j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4% Vto. 14 10 2024",
    "Código": "T4X4j",
    "ISIN": "ARARGE320DH9",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/10/2024",
    "Fecha Primer Cupón": "14/10/2023",
    "Cupón / Spread": 4., # es un nro flotante
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
    "Fechas de cupón": [
    "14/10/2023",
    "14/04/2024",
    "14/10/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T5X4j = {
    "Nombre Security": "Bono del Tesoro en Pesos Ajustado por CER Vto. 13 12 2024",
    "Código": "T5X4j",
    "ISIN": "ARARGE320DV0",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "13/06/2023",
    "Vencimiento": "13/12/2024",
    "Fecha Primer Cupón": "13/12/2023",
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": [
    "13/12/2023",
    "13/06/2024",
    "13/12/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T2X5j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4,25% Vto. 14 02 2025",
    "Código": "T2X5j",
    "ISIN": "ARARGE320DI7",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "14/03/2023",
    "Vencimiento": "14/02/2025",
    "Fecha Primer Cupón": "14/08/2023",
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": [
    "14/08/2023",
    "14/02/2024",
    "14/08/2024",
    "14/02/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TC25 = {
    "Nombre Security": "BONCER 2025 Vto 27 04 2025",
    "Código": "TC25",
    "ISIN": "ARARGE4505U2",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "27/04/2018",
    "Vencimiento": "27/04/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 4., # es un nro flotante
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
    "Fechas de cupón": [
    "27/10/2018",
    "27/04/2019",
    "27/10/2019",
    "27/04/2020",
    "27/10/2020",
    "27/04/2021",
    "27/10/2021",
    "27/04/2022",
    "27/10/2022",
    "27/04/2023",
    "27/10/2023",
    "27/04/2024",
    "27/10/2024",
    "27/04/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
T4X5 = {
    "Nombre Security": "BONCER 25 Sostenible 4.25% 23 05 2025*",
    "Código": "T4X5",
    "ISIN": "T4X5*",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "23/11/2023",
    "Vencimiento": "23/05/2025",
    "Fecha Primer Cupón": None,
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": [
    "23/05/2024",
    "23/11/2024",
    "23/05/2025"], # Lista de fechas como ejemplo
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
T3X5 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER 4,5% Vto. 18 06 2025",
    "Código": "T3X5",
    "ISIN": "ARARGE320DU2",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "31/05/2023",
    "Vencimiento": "18/06/2025",
    "Fecha Primer Cupón": "18/06/2025",
    "Cupón / Spread": 4.5, # es un nro flotante
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
    "Fechas de cupón": ["18/06/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX25 = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 30 06 2025",
    "Código": "TZX25",
    "ISIN": "TZX25",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "28/02/2024",
    "Vencimiento": "30/06/2025",
    "Fecha Primer Cupón": "30/06/2025",
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
    "Fechas de cupón": ["30/06/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZX25j = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2025",
    "Código": "TZX25j",
    "ISIN": "TZX25j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "28/02/2024",
    "Vencimiento": "30/06/2025",
    "Fecha Primer Cupón": "30/06/2025",
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
    "Fechas de cupón": ["30/06/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None  # Precio Call
}
TZXD5 = {
    "Nombre Security": "Bonos del Tesoro Nacional en Pesos 0 cupon con Ajuste CER Vto 15 12 2025",
    "Código": "TZXD5",
    "ISIN": "TZXD5",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZXD5j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
TZX26 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 30 06 2026",
    "Código": "TZX26",
    "ISIN": "TZX26",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZX26j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
TZXD6 = {
    "Nombre Security": "Bonos del Tesoro en Pesos Ajustado por CER Cero Cupon Vto. 15 12 2026",
    "Código": "TZXD6",
    "ISIN": "TZXD6",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZXD6j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZX27",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZX27j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZXD7",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZXD7j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZX28",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "ISIN": "TZX28j",
    "Calificación": "CCC-",
    "País": "Argentina",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación Proyectado",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
# Fichas ON DL Corporativos
TBC4O = {
    "Nombre Security": "ON Central Termica Barragan S.A. Clase 4 Vto 26 11 2024",
    "Código": "TBC4O",
    "ISIN": "ARCTBA560032",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "26/11/2021",
    "Vencimiento": "26/11/2024",
    "Fecha Primer Cupón": "26/02/2022",
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
    "26/11/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "90 días antes de la fecha de vencimiento",
    "Fecha Call": "28/08/2024",
    "Precio Call": 1,  # Precio Call
    "Comentarios": "Rescata VT",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TBC4O/Y/MPMAE-RES-ON%20CT%20BARRAGAN%20CLASE%204%20-%20Aviso%20de%20Resultados%20-%2025-11-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TBC4O/Y/MPMAE-ANU-ON%20CT%20BARRAGAN%20Clase%204%20-%20%20Suplemento%20Prosp%20%2019-11-21%20.PDF.pdf"""
}
AER9O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase IX Vto. 19 08 2026",
    "Código": "AER9O",
    "ISIN": "ARAEAR5600C1",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
TLC9O = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 9 Vto. 07 06 2024",
    "Código": "TLC9O",
    "ISIN": "ARTECO5600B6",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "07/06/2021",
    "Vencimiento": "07/06/2024",
    "Fecha Primer Cupón": "07/09/2021",
    "Cupón / Spread": 2.75, # es un nro flotante
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
    "7/6/2021", "7/9/2021", "7/12/2021", "7/3/2022", "7/6/2022", "7/9/2022", "7/12/2022", "7/3/2023", 
    "7/6/2023", "7/9/2023", "7/12/2023", "7/3/2024", "7/6/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TLC9O/Y/MPMA-RES-ON%20TELECOM%20ARGENTINA%20Clase%209%20-%20Aviso%20de%20Resultados%2003-06-2021.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TLC9O/Y/MPMAE-ANU-ON%20TELECOM%20CLASE%209-%20%20Suplemento%20Prospecto%2001-06-2021.pdf"""
}
AER6O = {
    "Nombre Security": "ON Aeropuertos Argentina 2000 S.A. Clase VI Vto. 21 02 2025",
    "Código": "AER6O",
    "ISIN": "ARAEAR5600A5",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "21/02/2022",
    "Vencimiento": "21/02/2025",
    "Fecha Primer Cupón": "21/05/2022",
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
    "Fechas de cupón": ["21/5/2022", "21/8/2022", "21/11/2022", "21/2/2023",
    "21/5/2023", "21/8/2023", "21/11/2023", "21/2/2024", "21/5/2024", "21/8/2024", "21/11/2024", "21/2/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/AER6O/Y/MPMAE-RES-AEROPUERTOS%20ARGENTINA%202000%20CLASE%205%20y%206%20Aviso_de_Resultados%2017-02-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/AER6O/Y/MPMAE-ANU-ON%20AEROPUERTOS%20ARGENTINA%202000%20CLASE%205-6-Suplemento%20de%20Prospecto-14-02-22.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
LIC5O = {
    "Nombre Security": "ON Lipsa S.R.L. Clase V Vto 14 07 2025",
    "Código": "LIC5O",
    "ISIN": "ARLIPS560079",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
MRCMO = {
    "Nombre Security": "ON Generacion Mediterranea S.A Clase XXI Vto. 17 04 2025",
    "Código": "AER6O",
    "ISIN": "ARGMCT5600K6",
    "Calificación": "A-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "17/04/2023",
    "Vencimiento": "17/04/2025",
    "Fecha Primer Cupón": "17/07/2022",
    "Cupón / Spread": 5.50, # es un nro flotante
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
    "Fechas de cupón": ["17/7/2023", "17/10/2023", "17/1/2024", "17/4/2024",
    "17/7/2024", "17/10/2024", "17/1/2025", "17/4/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "Base promedio A3500 ultimos 3 días habilies y lo mismo de pago",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MRCMO/Y/MPMAE-RES-ON%20GEMSA-CTR%20CLASES%2020-21-Aviso%20de%20Resultados%2013-04-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MRCMO/Y/MPMAE-ANU-ON%20GEMSA-CTR%20CLASES%2020-21%20-Suplemento%2005-04-23.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
LUC4O = {
    "Nombre Security": "ON Luz de Tres Picos S.A. Clase 4 Vto 29 09 2026",
    "Código": "LUC4O",
    "ISIN": "ARLUZT560047",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PEC6O = {
    "Nombre Security": "ON Petrolera Aconcagua Energía S.A. Serie VI Vto 14 09 2026",
    "Código": "PEC6O",
    "ISIN": "ARPAEG5600B4",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PNECO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 13 Vto 12 07 2031",
    "Código": "PNECO",
    "ISIN": "ARAXIO5600L2",
    "Calificación": "Aaa(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
VSC7O = {
    "Nombre Security": "ON Vista Oil & Gas Argentina S.A.U. Clase VII Vto 10 03 2024",
    "Código": "VSC7O",
    "ISIN": "AROILG560074",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "10/03/2021",
    "Vencimiento": "10/03/2024",
    "Fecha Primer Cupón": "10/06/2021",
    "Cupón / Spread": 4.25, # es un nro flotante
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
    "Fechas de cupón": ["10/6/2021", "10/9/2021", "10/12/2021", "10/3/2022", "10/6/2022", "10/9/2022",
                        "10/12/2022", "10/3/2023", "10/6/2023", "10/9/2023", "10/12/2023", "10/3/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Desde su fecha de emisión",
    "Fecha Call": "05/03/2021",
    "Precio Call": 1,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": "",
    "Suplemento Prospecto": ""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
TBC6O = {
    "Nombre Security": "ON Central Termica Barragan Ensenada S.A. Clase 6 Vto 16 05 2025",
    "Código": "TBC6O",
    "ISIN": "ARCTBA560040",
    "Calificación": "A+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "16/05/2022",
    "Vencimiento": "16/05/2025",
    "Fecha Primer Cupón": "16/05/2025",
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
    "16/05/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True, # Es binario True or False
    "Tipo de Call": "Ulitmos 90 días antes del vencimiento",
    "Fecha Call": "15/02/2025",
    "Precio Call": 1,  # Precio Call
    "Comentarios": """ """,
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/TBC6O/Y/MPMAE-RES-ON%20CT%20BARRAGAN%20CLASE%206%20-%20Aviso%20de%20Resultados%2012-05-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/TBC6O/Y/MPMAE-ANU-ON%20CT%20BARRAGAN%20CLASE%206%20-%20Suplemento%20de%20Prospecto%2010-05-22.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
YFCDO = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase XII Vto 29 08 2026",
    "Código": "YFCDO",
    "ISIN": "ARYPFE5600I1",
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
ATS1O = {
    "Nombre Security": "ON Agrality S.A. Serie I Vto 12 05 2025",
    "Código": "ATS1O",
    "ISIN": "ARAGTY560015",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "11/05/2023",
    "Vencimiento": "11/05/2025",
    "Fecha Primer Cupón": "11/09/2023",
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
    "Fechas de cupón": ["11/8/2023", "11/11/2023", "11/2/2024", "11/5/2024",
                        "11/8/2024", "11/11/2024", "11/2/2025", "11/5/2025"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 5 + [33] + [33] + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/25065cdf-67be-429d-a59b-1c87588f2790""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/b4342083-3dca-4c3b-8b86-98cc4ab50ece"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
MRCJO = {
    "Nombre Security": "ON GEM S.A.  y CTR S.A. Clase XVIII Vto. 07 11 2024",
    "Código": "MRCJO",
    "ISIN": "ARGMCT5600H2",
    "Calificación": "A(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Utilities",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "07/11/2022",
    "Vencimiento": "07/11/2024",
    "Fecha Primer Cupón": "07/02/2023",
    "Cupón / Spread": 3.75, # es un nro flotante
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
    "Fechas de cupón": ["7/2/2023", "7/5/2023", "7/8/2023", "7/11/2023",
                        "7/2/2024", "7/5/2024", "7/8/2024", "7/11/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MRCJO/Y/MPMAE-RES-ON%20COEMISION%20GEMSA-CTR%20CLASES%2017-18-19-Aviso%20de%20Resultado%2003-11-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MRCJO/Y/MPMAE-ANU-ON%20COEMISION%20GEMSA-CTR%20CLASES%2017-18-19-Suplemento%2028-10-22.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PQCNO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase N Vto 16 05 2025",
    "Código": "PQCNO",
    "ISIN": "ARPETQ5600M0",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "16/05/2023",
    "Vencimiento": "16/05/2025",
    "Fecha Primer Cupón": "16/08/2023",
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
    "Fechas de cupón": ["16/05/2025"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "None",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PQCNO/Y/MPMAE-RES-ON%20EF%20PCR%20CLASES%20K%20ADIC-%20M%20Y%20N-Aviso%20de%20Resultado%2011-05-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PQCNO/Y/MPMAE-ANU-ON%20EF%20PCR%20CLASES%20K%20ADIC%20-%20M%20Y%20N-%20Suplemento%2009-05-23.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PNRCO = {
    "Nombre Security": "ON Pan American Energy S.L. Suc Argentina Clase 26 Vto 07 08 2028",
    "Código": "PNRCO",
    "ISIN": "ARAXIO5600X7",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Communications",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
PQCKO = {
    "Nombre Security": "ON Petroquimica Comodoro Rivadavia S.A. Clase K Vto 07 12 2026",
    "Código": "PQCKO",
    "ISIN": "ARPETQ5600H0",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Fechas de cupón": ["07/12/2022",
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
                        "07/09/2026", 
                        "07/12/2026"
                        ], # Lista de fechas como ejemplo
    "Amortización": ([0] * 12 + [33.33] + [0] * 3 + [66.67]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/PQCKO/Y/MPMAE-RES-ON%20EF%20PCR%20CLASE%20K-%20Aviso%20de%20Resultado%2005-12-22.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/PQCKO/Y/MPMAE-ANU-ON%20EF%20PCR%20CLASE%20K-Suplemento%2001-12-22.pdf"""
}
YMCOO = {
    "Nombre Security": "ON YPF S.A. Clase XXIII Vto 25 04 2025",
    "Código": "YMCOO",
    "ISIN": "ARYPFS5601U4",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "25/04/2023",
    "Vencimiento": "25/04/2025",
    "Fecha Primer Cupón": "25/04/2025",
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
    "Fechas de cupón": ["25/04/2025"
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YMCOO/Y/MPMAE-ANU-ON%20YPF%20CLASES%2022%20AD-23-24-Aviso%20de%20Resultados%2021-04-23.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YMCOO/Y/MPMAE-ANU-ON%20YPF%20CLASES%2022%20AD-23-24-Suplemento%20de%20Prospecto%2018-04-23.pdf"""
}
MAC4O = {
    "Nombre Security": "ON Molinos Agro S.A. Clase IV Vto 03 09 2024",
    "Código": "MAC4O",
    "ISIN": "ARRIAR5600D4",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Agriculture",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "03/09/2021",
    "Vencimiento": "03/09/2024",
    "Fecha Primer Cupón": "03/12/2024",
    "Cupón / Spread": 2.49, # es un nro flotante
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
    "Fechas de cupón": ["3/12/2021", "3/3/2022", "3/6/2022", "3/9/2022", "3/12/2022",
    "3/3/2023", "3/6/2023", "3/9/2023", "3/12/2023", "3/3/2024", "3/6/2024", "3/9/2024"], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/MAC4O/Y/MPMAE-RES-ON%20MOLINOS%20AGRO%20Clase%20III%20y%20IV-Aviso%20de%20Resultados%2001-09-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/MAC4O/Y/MPMAE-ANU-ON%20MOLINOS%20AGRO%20Clase%20III%20y%20IV%20-%20Suplemento%20de%20Precio%2030-08-2021.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
YFC9O = {
    "Nombre Security": "ON YPF Energia Electrica S.A. Clase IX Vto 30 08 2024",
    "Código": "YFC9O",
    "ISIN": "ARYPFE5600F7",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "30/08/2021",
    "Vencimiento": "30/08/2024",
    "Fecha Primer Cupón": "30/11/2021",
    "Cupón / Spread": 3.50, # es un nro flotante
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
    "Fechas de cupón": ["30/11/2021", "28/2/2022", "30/5/2022", "30/8/2022", "30/11/2022", 
                        "28/2/2023", "30/5/2023", "30/8/2023", "30/11/2023", "29/2/2024",
                        "30/5/2024", "30/8/2024"], # Lista de fechas como ejemplo
    "Amortización": ([0] * 9 + [33] + [33] + [34]),
    "Callable": False , # Es binario True or False
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,  # Precio Call
    "Comentarios": "",
    "Aviso Resultados": """https://www.mae.com.ar/descarga/docs/M/YFC9O/Y/MPMAE-RES-ON%20YPF%20ENERGIA%20CLASE%20VIII%20y%20IX-Aviso%20de%20resultado%2025-08-21.pdf""",
    "Suplemento Prospecto": """https://www.mae.com.ar/descarga/docs/M/YFC9O/Y/MPMAE-ANU-ON%20YPF%20ENERGIA%20ELECTRICA%20CLASE%209%20Adic-Suplemento%20Prospecto-28-01-22.pdf"""
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
YMCTO = {
    "Nombre Security": "ON YPF S.A. Clase XXVII Vto 10 10 2026",
    "Código": "YMCTO",
    "ISIN": "AR0688075032",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Calificación": "AA+(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
YMCMO = {
    "Nombre Security": "ON YPF S.A. Clase XXI Vto 10 01 2026",
    "Código": "YMCMO",
    "ISIN": "ARYPFS5601S8",
    "Calificación": "AAA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
    "Emisión": "10/01/2023",
    "Vencimiento": "10/01/2026",
    "Fecha Primer Cupón": "10/04/2023",
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
    "Fechas de cupón": ["10/04/2023",
                        "10/07/2023",
                        "10/10/2023",
                        "10/01/2024",
                        "10/04/2024",
                        "10/07/2024",
                        "10/10/2024",
                        "10/01/2025",
                        "10/04/2025",
                        "10/07/2025",
                        "10/10/2025",
                        "10/01/2026",
                        ], # Lista de fechas como ejemplo
    "Amortización": None,
    "Callable": True , # Es binario True or False
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m18 de emitido",
    "Fecha Call": "10/07/2024",
    "Precio Call": {"m18 al 24":1.02,"m24 al m30": 1.01, "m30 en adelante": 1},  # Precio Call
    "Comentarios": """Callable a partir del mes 18 de emitido, Es el promedio aritmético simple de los últimos tres (3) Días Hábiles previos a la Fecha de
                    Cálculo del tipo de cambio de referencia de Pesos por Dólar Estadounidenses informado por el
                    BCRA mediante la Comunicación "A" 3500 (Mayorista) (o la regulación que la sucediere o
                    modificare en el tiempo) en base al procedimiento de encuesta de cambio establecido en la
                    misma, truncado a cuatro decimales. En el supuesto que (x) el BCRA dejare de efectuar dicha
                    determinación y publicación, el Tipo de Cambio Aplicable será calculado de acuerdo al promedio
                    aritmético simple de los últimos tres (3) Días Hábiles previos a la Fecha de Cálculo del tipo de
                    10""",
    "Aviso Resultados": """https://aif2.cnv.gov.ar/presentations/publicview/62edb04e-c954-4424-b6b3-ea201d46890a""",
    "Suplemento Prospecto": """https://aif2.cnv.gov.ar/presentations/publicview/74d7d749-675c-42b8-a5de-8bb28a011bd9"""
}
CAC4O = {
    "Nombre Security": "ON Capex S.A. Clase IV Vto. 27 02 2027",
    "Código": "CAC4O",
    "ISIN": "ARCAPX560048",
    "Calificación": "AA-(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Plazo habitual de liquidación: t +": 2., # debe ser un entero
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
    "Tipo de Call": "Stripeable put a partir del 1 de marzo en 4 especies BPO27 1A (.20) callable desde 30/04/25, BPO27 1B (.20) callable desde 30/04/26, BPO27 1C (.30) callable desde 30/04/27, BPO27 1D (.30)",
    "Fecha Call": "Cualquier momento ",
    "Precio Call": 1,  # Precio Call
    "Comentarios": """ """,
}

##### Definiciones de bonos #####

# CORPORATIVOS DOLAR LINKED
TLCKO = rentafija.Bono(TLCKO)
CWS1P = rentafija.Bono(CWS1P)
PNRCO = rentafija.Bono(PNRCO)
TLCDO = rentafija.Bono(TLCDO)
TBC4O = rentafija.Bono(TBC4O)
YMCOO = rentafija.Bono(YMCOO)
YMCMO = rentafija.Bono(YMCMO)
CAC4O = rentafija.Bono(CAC4O)
OLC2O = rentafija.Bono(OLC2O)
TLCHO = rentafija.Bono(TLCHO)
TBC6O = rentafija.Bono(TBC6O)
AER9O = rentafija.Bono(AER9O)
TLC9O = rentafija.Bono(TLC9O)
VSC7O = rentafija.Bono(VSC7O)
YFCDO = rentafija.Bono(YFCDO)
PQCKO = rentafija.Bono(PQCKO)
CP28O = rentafija.Bono(CP28O)
TLCFO = rentafija.Bono(TLCFO)
TLCGO = rentafija.Bono(TLCGO)
VSCHO = rentafija.Bono(VSCHO)
YMCTO = rentafija.Bono(YMCTO)
MAC4O = rentafija.Bono(MAC4O)
YFC9O = rentafija.Bono(YFC9O)
LUC4O = rentafija.Bono(LUC4O)
PEC6O = rentafija.Bono(PEC6O)
PNECO = rentafija.Bono(PNECO)
PEC4O = rentafija.Bono(PEC4O)
YFCFO = rentafija.Bono(YFCFO)
MRCJO = rentafija.Bono(MRCJO)
ATS1O = rentafija.Bono(ATS1O)
YFCAO = rentafija.Bono(YFCAO)
FOS3O = rentafija.Bono(FOS3O)
PEC1O = rentafija.Bono(PEC1O)
PQCHO = rentafija.Bono(PQCHO)
GN35O = rentafija.Bono(GN35O)
AER6O = rentafija.Bono(AER6O)
MRCMO = rentafija.Bono(MRCMO)
LIC5O = rentafija.Bono(LIC5O)
HJCAO = rentafija.Bono(HJCAO)
PQCOO = rentafija.Bono(PQCOO)
PQCNO = rentafija.Bono(PQCNO)
PEC2O = rentafija.Bono(PEC2O)
CP31O = rentafija.Bono(CP31O)
RZ6BO = rentafija.Bono(RZ6BO)

# SOBS
S31E5 = rentafija.Bono(S31E5)
T3X4 = rentafija.Bono(T3X4)
X20Y4 = rentafija.Bono(X20Y4)
T6X4 = rentafija.Bono(T6X4)
T2X4 = rentafija.Bono(T2X4)
T7X4 = rentafija.Bono(T7X4)
T4X4 = rentafija.Bono(T4X4)
T5X4 = rentafija.Bono(T5X4)
T2X5 = rentafija.Bono(T2X5)
TZX25 = rentafija.Bono(TZX25)
TZXD5 = rentafija.Bono(TZXD5)
TZX26 = rentafija.Bono(TZX26)
TZXD6 = rentafija.Bono(TZXD6)
TZX27 = rentafija.Bono(TZX27)
TZXD7 = rentafija.Bono(TZXD7)
TZX28 = rentafija.Bono(TZX28)
T3X4j = rentafija.Bono(T3X4j)
T6X4j = rentafija.Bono(T6X4j)
X20Y4j = rentafija.Bono(X20Y4j)
T2X4j = rentafija.Bono(T2X4j)
T7X4j = rentafija.Bono(T7X4j)
T4X4j = rentafija.Bono(T4X4j)
T5X4j = rentafija.Bono(T5X4j)
T2X5j = rentafija.Bono(T2X5j)
TX26j = rentafija.Bono(TX26j)
TZX26j = rentafija.Bono(TZX26j)
TZX27j = rentafija.Bono(TZX27j)
TZX25j = rentafija.Bono(TZX25j)
TZXD5j = rentafija.Bono(TZXD5j)
TZXD6j = rentafija.Bono(TZXD6j)
TZXD7j = rentafija.Bono(TZXD7j)
TZX28j = rentafija.Bono(TZX28j)
TC25 = rentafija.Bono(TC25)
T4X5 = rentafija.Bono(T4X5)
TG25 = rentafija.Bono(TG25)
TX25 = rentafija.Bono(TX25)
T3X5 = rentafija.Bono(T3X5)
TX26 = rentafija.Bono(TX26)
TX28 = rentafija.Bono(TX28)
DICP = rentafija.Bono(DICP)
PARP = rentafija.Bono(PARP)
CUAP = rentafija.Bono(CUAP)
TV24 = rentafija.Bono(TV24)
T2V4 = rentafija.Bono(T2V4)
TV25 = rentafija.Bono(TV25)
TDA24 = rentafija.Bono(TDA24)
#TDA24_C = rentafija.Bono(TDA24_C)
TDJ24 = rentafija.Bono(TDJ24)
TDJ24_C = rentafija.Bono(TDJ24_C)
TDG24 = rentafija.Bono(TDG24)
TDG24_C = rentafija.Bono(TDG24_C)
TDN24 = rentafija.Bono(TDN24)
TDN24_C = rentafija.Bono(TDN24_C)
TDE25 = rentafija.Bono(TDE25)
TDE25_C = rentafija.Bono(TDE25_C)
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

# SUBSOB
BDC28 = rentafija.Bono(BDC28)

todos_los_bonos = [S31E5,
    T3X4, X20Y4, T6X4, T2X4, T7X4, T4X4,
    T5X4, T2X5, TC25, T4X5, TG25, TX25, T3X5, TX26, TZX25, TZXD5, TZX26, TZXD6, TZX27, TZXD7, TX28,
    DICP, PARP, CUAP, TV24, T2V4, TV25, TDA24, TDJ24, TDJ24_C, TDG24_C, TDN24_C, TDE25_C, 
    TDG24, TDN24, TDE25, T3X4j, X20Y4j, T6X4j, T2X4j, T7X4j, T4X4j, T5X4j, T2X5j, TX26j, TZX25j, TZXD5j, TZX26j, TZXD6j, TZX27j, TZXD7j, TZX28j,
]

# Precios BYMA
