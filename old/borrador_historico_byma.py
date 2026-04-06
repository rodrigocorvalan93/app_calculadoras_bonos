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
ruta_general = path.parent.parent.parent
ruta_bases = os.path.join(ruta_general, 'Delta Bases')

# Archivo
df_raw = pd.read_excel(ruta_bases + '\\Delta - historico_byma_px_tasas.xlsx')
especies = pd.read_excel(ruta_bases + '\\Delta - Especies.xlsx', sheet_name='Base RF', header=3)

# %%
# Resultado

def calcular_evolucion_duration(df_input):
    df = df_input.merge(especies[['Cod_Delta', 'Ajuste']], left_on='Código', right_on='Cod_Delta', how='left')
    df['Duration'] = df['Duration'].round(2)
    df = df.loc[df['Proy']==0]
    df = df.sort_values(['Código', 'fecha_hoy'])
    df['Var_Precio_Diaria'] = df.groupby('Código')['Last Price'].pct_change()
    df['Var_Precio_Diaria'].fillna(0, inplace=True)

    # Calcular evolución por duration
    bins = np.arange(0, 2.51, 0.083333).tolist() + [np.inf]
    labels = [f"{round(bins[i],1)} - {round(bins[i+1],1)}" if bins[i+1] != np.inf else "2+" for i in range(len(bins)-1)]
    df['duration_bin'] = pd.cut(df['Duration'], bins=bins, labels=labels, right=False)
    df_group = df.groupby(['fecha_hoy', 'Ajuste', 'duration_bin'])[['TIREA', 'TEM', 'Var_Precio_Diaria']].mean().reset_index()
    
    # Calculamos índice de precio
    df_group = df_group.sort_values(['Ajuste', 'duration_bin', 'fecha_hoy'])
    df_group['Indice_Precio'] = df_group.groupby(['Ajuste', 'duration_bin'])['Var_Precio_Diaria'].transform(lambda x: (1 + x).cumprod())
    tickers_usados = df.groupby(['fecha_hoy', 'Ajuste', 'duration_bin'])['Código'].apply(lambda x: ', '.join(sorted(set(x)))).reset_index(name='Bonos usados')
    df_group = df_group.merge(tickers_usados, on=['fecha_hoy', 'Ajuste', 'duration_bin'], how='left')
    df_group.dropna(subset=['TIREA', 'TEM', 'Var_Precio_Diaria'], inplace=True)
    return df, df_group

df_last, df_group = calcular_evolucion_duration(df_raw)
df_group.to_excel(ruta_bases + '\\Delta - historico_byma_duration.xlsx', index=False)
