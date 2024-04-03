# Imports
from datetime import timedelta,datetime,date
import numpy as np
from pandas.tseries.offsets import BDay, MonthEnd
import holidays
import pandas as pd
import requests
import json
import os
import io
from urllib.error import URLError
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

#Last version
def tir_a_tna(tir,dias,base):
    return ((1 + tir) ** (dias/base) - 1)*(base/dias)

def tna_a_tir(tna,dias,base):
    return (1 + tna/(base/dias)) ** (base / dias) - 1

'''
from decimal import Decimal

def tir_a_tna(tir, dias, base):
    dias_decimal = Decimal(dias)
    base_decimal = Decimal(base)
    return ((1 + tir) ** (dias_decimal/base_decimal) - 1) * (base_decimal/dias_decimal)

def tna_a_tir(tna, dias, base):
    # Convierte los argumentos a Decimal si no lo son
    tna_decimal = Decimal(tna)
    dias_decimal = Decimal(dias)
    base_decimal = Decimal(base)

    return (1 + tna_decimal / (base_decimal / dias_decimal)) ** (base_decimal / dias_decimal) - 1
'''

fondos_cnv = {
            "Acciones": 505,
            "Ahorro": 506,
            "Ahorro Plus": 606,
            "Cohen Pesos": 583,
            "Crecimiento": 722,
            "CRF DOL": 1025,
            "FEDERAL I": 605,
            "Gestion I": 624,
            "Gestion II": 625,
            "Gestion III": 749,
            "Gestion IV": 533,
            "Gestion IX": 1089,
            "Gestion Pyme": 1263,
            "Gestion V": 815,
            "Gestión VI": 816,
            "Gestion VII": 962,
            "RETORNO REAL": 963,
            "Gestion X": 1090,
            "Gestion XI": 1228,
            "Internacional": 532,
            "Latinoamerica": 504,
            "Moneda": 534,
            "Multimercado I": 607,
            "MULTIMERCADO II": 998,
            "Patrimonio I": 996,
            "Performance": 748,
            "Pesos": 536,
            "PLUS": 616,
            "Pyme": 589,
            "PYMES": 598,
            "Recursos": 535,
            "Renta": 503,
            "Renta Dolares": 849,
            "DOLARES PLUS": 997,
            "Select": 531
            }

# Función para obtener el número CNV basado en el nombre del fondo
def obtener_cnv(fondo):
    return fondos_cnv.get(fondo, "Fondo no encontrado")