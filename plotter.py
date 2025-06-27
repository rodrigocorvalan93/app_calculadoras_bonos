
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


def nss_model(x, beta0, beta1, beta2, beta3, tau1, tau2):
    """
    Modelo Nelson-Siegel-Svensson (NSS).

    y(x) = beta0 + beta1 * NS1(x,tau1) + beta2 * NS2(x,tau1) + beta3 * NS3(x,tau2)

    Donde:
      NS1(x,tau) = (1 - exp(-x/tau)) / (x/tau)
      NS2(x,tau) = NS1(x,tau) - exp(-x/tau)
      NS3(x,tau) = (1 - exp(-x/tau)) / (x/tau) - exp(-x/tau)
    
    Se cuidan los casos en que x=0 para evitar divisiones por cero.
    """
    x = np.array(x)
    factor1 = np.where(x == 0, 1.0, (1 - np.exp(-x/tau1)) / (x/tau1))
    factor2 = np.where(x == 0, 0.0, ((1 - np.exp(-x/tau1)) / (x/tau1) - np.exp(-x/tau1)))
    factor3 = np.where(x == 0, 0.0, ((1 - np.exp(-x/tau2)) / (x/tau2) - np.exp(-x/tau2)))
    return beta0 + beta1 * factor1 + beta2 * factor2 + beta3 * factor3

def graficar_duration_tem_nss(df, threshold_factor=2.0):
    """
    Ajusta el modelo Nelson-Siegel-Svensson (NSS) a la relación entre Duration y TEM
    ignorando outliers, y genera el gráfico.

    Se requieren las siguientes columnas en el DataFrame:
      - 'Duration'
      - 'TEM' (formato string con '%' al final, ej. "2.62%")
      - 'TIREA' (formato similar a TEM)
      - 'Código'

    Parámetros:
      - df: DataFrame con los datos.
      - threshold_factor: Factor multiplicativo de la desviación estándar de los residuales
                          para detectar outliers (por defecto 2.0).
    """
    # 1. Filtrar filas con valores NA en las columnas clave.
    df = df.dropna(subset=['Duration', 'TEM', 'TIREA', 'Código']).copy()
    
    # 2. Convertir columnas de porcentaje a valores numéricos.
    df['TEM_num'] = df['TEM'].astype(str).str.replace('%', '', regex=False).astype(float)
    df['TIREA_num'] = df['TIREA'].astype(str).str.replace('%', '', regex=False).astype(float)
    
    # 3. Extraer las variables de interés.
    X = df['Duration'].values
    y = df['TEM_num'].values

    # Parámetros iniciales para el ajuste: se puede ajustar según el caso.
    initial_guess = [np.mean(y), 0, 0, 0, 1.0, 1.0]
    
    # Ajuste inicial usando todos los datos.
    try:
        popt, _ = curve_fit(nss_model, X, y, p0=initial_guess, maxfev=10000)
    except Exception as e:
        print("Error en el ajuste inicial:", e)
        return

    # 4. Calcular residuales y detectar outliers.
    y_fit_all = nss_model(X, *popt)
    residuals = y - y_fit_all
    std_res = np.std(residuals)
    threshold = threshold_factor * std_res

    # Crear máscaras para datos "limpios" y outliers.
    mask_clean = np.abs(residuals) <= threshold
    mask_outliers = np.abs(residuals) > threshold

    # Datos sin outliers.
    X_clean = X[mask_clean]
    y_clean = y[mask_clean]
    df_clean = df.iloc[mask_clean]

    # Datos de outliers (si existen).
    X_outliers = X[mask_outliers]
    y_outliers = y[mask_outliers]
    df_outliers = df.iloc[mask_outliers]
    
    # 5. Reajustar el modelo NSS usando solo los datos sin outliers.
    try:
        popt_clean, _ = curve_fit(nss_model, X_clean, y_clean, p0=popt, maxfev=10000)
    except Exception as e:
        print("Error en el ajuste con datos limpios:", e)
        return

    # Preparar cadena con la ecuación del modelo ajustado.
    beta0, beta1, beta2, beta3, tau1, tau2 = popt_clean
    eq_str = (f"y = {beta0:.4f} + {beta1:.4f}*NS1(x,{tau1:.4f}) + "
              f"{beta2:.4f}*NS2(x,{tau1:.4f}) + {beta3:.4f}*NS3(x,{tau2:.4f})")
    
    # Generar valores para graficar la curva ajustada.
    X_reg = np.linspace(X.min(), X.max(), 100)
    y_reg = nss_model(X_reg, *popt_clean)
    
    # 6. Graficar
    plt.figure(figsize=(10, 6))
    
    # Datos sin outliers (usados en el ajuste).
    plt.scatter(X_clean, y_clean, color='blue', label='Datos usados en ajuste')
    for i, row in df_clean.iterrows():
        etiqueta = f"{row['Código']}\nTIR: {row['TIREA']}\nTEM: {row['TEM']}"
        plt.annotate(etiqueta,
                     (row['Duration'], row['TEM_num']),
                     textcoords="offset points",
                     xytext=(5, 5),
                     ha='left',
                     fontsize=7.5)
    
    # Marcar los outliers (si existen) con otro marcador.
    if len(X_outliers) > 0:
        plt.scatter(X_outliers, y_outliers, color='red', marker='x', s=100, label='Outliers excluidos')
        for i, row in df_outliers.iterrows():
            etiqueta = f"{row['Código']}\nTIR: {row['TIREA']}\nTEM: {row['TEM']}"
            plt.annotate(etiqueta,
                         (row['Duration'], row['TEM_num']),
                         textcoords="offset points",
                         xytext=(5, 5),
                         ha='left',
                         fontsize=7.5,
                         color='red')
    
    # Graficar la curva ajustada con los datos sin outliers.
    plt.plot(X_reg, y_reg, color='deepskyblue', label=f"Ajuste NSS (sin outliers)\n{eq_str}")
    
    plt.xlabel("Duration")
    plt.ylabel("TEM (%)")
    plt.title("Ajuste Nelson-Siegel-Svensson (ignorando outliers)")
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=9)
    plt.grid(True)
    plt.show()

# Ejemplo de uso:
# Suponiendo que tienes el DataFrame 'lecap_24_hs_prices_df' ya cargado:
# graficar_duration_tem_nss(lecap_24_hs_prices_df, threshold_factor=2.0)
