# %%
# Librerías
import sys
import os
import glob
from pathlib import Path
import pandas as pd
import numpy as np
import copy
from decimal import *
import datetime
import json #Para almacenar la data del Informe de Gestión
import warnings
warnings.filterwarnings("ignore")
pd.set_option('display.max_columns', None)
pd.options.display.float_format = '{:.2f}'.format

# Directorios
path = Path(os.getcwd())
ruta_general = path.parent.parent
ruta_bases = glob.glob(os.path.join(ruta_general, 'Delta Bases'))[0]

# Archivo
df_raw = pd.read_excel(ruta_bases + '\\Delta - historico_byma_px_tasas.xlsx')

# %%
# Resultado

def formateo_excel(df_input):
    df = df_input.drop_duplicates()
    df = df.dropna(subset=['Last Price', 'TIREA', 'TNA', 'TEM', 'Paridad', 'Duration'])
    df['Proy'] = np.where(df['Código'].str.endswith('j'), 1, 0)
    for col in ['TIREA', 'TNA', 'TEM']:
        df[col].replace('nan%', '', inplace=True)
    return df

df_last = formateo_excel(df_raw)
