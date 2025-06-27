#%%
import requests
import pandas as pd

def flatten_records(data):
    """Convierte una lista de diccionarios anidados en un DataFrame plano."""
    return pd.json_normalize(data)

def get_daily_report(cafci_token):
    """Obtiene el reporte diario de CAFCI y lo devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/reports/daily"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()['records']) if response.status_code == 200 else response.text

def get_historic_report(cafci_token, date):
    """Obtiene el reporte histórico de CAFCI para una fecha específica (YYYY-MM-DD) y lo devuelve como DataFrame plano."""
    url = f"https://cloud.cafci.org.ar/api/reports/historic?date={date}"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()['records']) if response.status_code == 200 else response.text

def get_closing_prices(cafci_token, date:str):
    """Obtiene el vector de precios de cierre de los fondos y lo devuelve como DataFrame plano."""
    url = f"https://cloud.cafci.org.ar/api/vectores/cafci_closing_prices?date={date}"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def busca_precio_get_closing_prices(cafci_token, codigo: str, date:str):
    url = f"https://cloud.cafci.org.ar/api/vectores/cafci_closing_prices?date={date}"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    datos_por_codigo = {}
    for item in response.json()['records']['precios']:
        datos_por_codigo[item['codigo']] = item
    preciobuscado = datos_por_codigo.get(codigo)
    return preciobuscado


def get_historic_prices(cafci_token):
    """Obtiene los precios históricos de los fondos y los devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/cafci_historic_prices"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def get_valuation_cashflows(cafci_token):
    """Obtiene el flujo de fondos utilizado en la valuación y lo devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/valuation_cashflows"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

def get_valuation_variables(cafci_token):
    """Obtiene las variables utilizadas en la valuación y las devuelve como DataFrame plano."""
    url = "https://cloud.cafci.org.ar/api/vectores/variables"
    headers = {"Authorization": cafci_token}
    response = requests.get(url, headers=headers)
    return flatten_records(response.json()) if response.status_code == 200 else response.text

# Ejemplo de uso
if __name__ == "__main__":
    cafci_token = 'Bearer eyJleHBpcmVzX2luIjozMTUzNjAwMCwiYWxnIjoiSFMyNTYifQ.eyJyZXNvdXJjZXMiOiJyZXBvcnRzIHZlY3RvcmVzIiwidXNlcl9pZCI6MjgxfQ.wpDWRapZXFfYgfTLPjCdIiK_f-61-gACawUA30QM9Cw'
    print(get_daily_report(cafci_token))
