#%%
import os
import requests
import pandas as pd

import OMSsecrets  # noqa: F401 — auto-carga secrets.txt a os.environ

_CAFCI_TOKEN_ENV = "CAFCI_TOKEN"


def _resolve_token(cafci_token=None):
    """Devuelve el token a usar.

    Prioridad: argumento explícito > os.environ["CAFCI_TOKEN"] (vía secrets.txt).
    El valor debe incluir el prefijo "Bearer ".
    """
    token = cafci_token or os.getenv(_CAFCI_TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"Falta el token de CAFCI. Definí {_CAFCI_TOKEN_ENV} en secrets.txt "
            f'(formato: {_CAFCI_TOKEN_ENV}=Bearer eyJ...) o pasalo como argumento.'
        )
    return token


def flatten_records(data):
    """Convierte una lista de diccionarios anidados en un DataFrame plano."""
    return pd.json_normalize(data)

def get_daily_report(cafci_token=None):
    """Obtiene el reporte diario de CAFCI y lo devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/reports/daily"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()['records']) if response.status_code == 200 else response.text

def get_historic_report(cafci_token=None, date=None):
    """Obtiene el reporte histórico de CAFCI para una fecha específica (YYYY-MM-DD) y lo devuelve como DataFrame plano."""
    url = f"https://cloud.cafci.org.ar/api/reports/historic?date={date}"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()['records']) if response.status_code == 200 else response.text

def get_closing_prices(cafci_token=None, date: str = None):
    """Obtiene el vector de precios de cierre de los fondos y lo devuelve como DataFrame plano."""
    url = f"https://cloud.cafci.org.ar/api/vectores/cafci_closing_prices?date={date}"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def busca_precio_get_closing_prices(codigo: str, date: str, cafci_token=None):
    url = f"https://cloud.cafci.org.ar/api/vectores/cafci_closing_prices?date={date}"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    datos_por_codigo = {}
    for item in response.json()['records']['precios']:
        datos_por_codigo[item['codigo']] = item
    preciobuscado = datos_por_codigo.get(codigo)
    return preciobuscado


def get_historic_prices(cafci_token=None):
    """Obtiene los precios históricos de los fondos y los devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/cafci_historic_prices"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def get_valuation_cashflows(cafci_token=None):
    """Obtiene el flujo de fondos utilizado en la valuación y lo devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/valuation_cashflows"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def get_valuation_variables(cafci_token=None):
    """Obtiene las variables utilizadas en la valuación y las devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/variables"
    headers = {"Authorization": _resolve_token(cafci_token)}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

# Ejemplo de uso
if __name__ == "__main__":
    reportediario = get_daily_report()
    print(reportediario)

    fondosabuscarrodri = [
    "Fima Renta Fija Dólares - Clase C",
    "Fima Premium Dólares - Clase A",
    "Delta Ahorro Plus - Clase A",
    "Delta Acciones - Clase A",
    "Delta Gestion VI - Clase A",
    "Delta Retorno Real - Clase A",
    "Delta Latinoamerica - Clase A",
    "Delta Renta - Clase A",
    "Delta Renta Dolares - Clase D"]

    filtro = reportediario[reportediario['nombreDeLaClaseDeFondo'].isin(fondosabuscarrodri)][['nombreDeLaClaseDeFondo', 'fecha', 'vcp','moneda']]
    filtro['vcp'] = pd.to_numeric(filtro['vcp']) / 1000
    filtro['vcp'] = filtro['vcp'].apply(lambda x: f"{x:,.6f}".replace(",", "X").replace(".", ",").replace("X", "."))
