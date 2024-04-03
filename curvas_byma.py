#%%
#import rentafija
from bymaapi import *
from utils import *
from especies import *



#%%
dl_48hs_prices_df
# dl_48hs_prices_df['price'] = dl_48hs_prices_df['price'].fillna(850)

for index, row in dl_48hs_prices_df.iterrows():
    codigo_bono = row['codigo']
    precio = row['price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        dl_48hs_prices_df.at[index, 'tirea'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(bono.tirea,bono.dias_remanentes, 365)
        dl_48hs_prices_df.at[index, 'tna'] = tna


        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        dl_48hs_prices_df.at[index, 'paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        dl_48hs_prices_df.at[index, 'duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        dl_48hs_prices_df.at[index, 'tirea'] = None
        dl_48hs_prices_df.at[index, 'tna'] = None
        dl_48hs_prices_df.at[index, 'paridad'] = None
        dl_48hs_prices_df.at[index, 'duration'] = None

# %%

#%%
cer_48hs_prices_df
#cer_48hs_prices_df['price'] = cer_48hs_prices_df['price'].fillna(2)

for index, row in cer_48hs_prices_df.iterrows():
    codigo_bono = row['codigo']
    precio = row['price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        cer_48hs_prices_df.at[index, 'tirea'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(bono.tirea,bono.dias_remanentes, 365)
        cer_48hs_prices_df.at[index, 'tna'] = tna


        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}.paridad"
        paridad = eval(comando_paridad)
        cer_48hs_prices_df.at[index, 'paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        cer_48hs_prices_df.at[index, 'duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        cer_48hs_prices_df.at[index, 'tirea'] = None
        cer_48hs_prices_df.at[index, 'tna'] = None
        cer_48hs_prices_df.at[index, 'paridad'] = None
        cer_48hs_prices_df.at[index, 'duration'] = None

#%%
        
cerproyectado_48hs_prices_df = cer_48hs_prices_df
#cerproyectado_48hs_prices_df['price'] = cer_48hs_prices_df['price'].fillna(2)

for index, row in cerproyectado_48hs_prices_df.iterrows():
    codigo_bono = row['codigo']
    precio = row['price'] /100
    try:
        # Construir y ejecutar el comando para calcular la TIREA
        comando_tirea = f"{codigo_bono}j.calcula_tirea({precio})"
        tirea = eval(comando_tirea)
        cerproyectado_48hs_prices_df.at[index, 'tirea'] = tirea

        # Obtener la paridad del bono
        bono = eval(codigo_bono)
        tna = tna_a_tir(tirea,bono.dias_remanentes, 365)
        cerproyectado_48hs_prices_df.at[index, 'tna'] = tna


        # Obtener la paridad del bono
        comando_paridad = f"{codigo_bono}j.paridad"
        paridad = eval(comando_paridad)
        cerproyectado_48hs_prices_df.at[index, 'paridad'] = paridad

        # Obtener la duration del bono
        comando_duration = f"{codigo_bono}j.calcula_duration({codigo_bono}.tirea)"
        duration = eval(comando_duration)
        cerproyectado_48hs_prices_df.at[index, 'duration'] = duration

    except Exception as e:
        print(f"Error al procesar {codigo_bono}: {e}")
        cerproyectado_48hs_prices_df.at[index, 'tirea'] = None
        cerproyectado_48hs_prices_df.at[index, 'tna'] = None
        cerproyectado_48hs_prices_df.at[index, 'paridad'] = None
        cerproyectado_48hs_prices_df.at[index, 'duration'] = None

# %%
