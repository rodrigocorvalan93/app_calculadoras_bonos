#%% 
import requests
import json
import pandas as pd
import rentafija
from especies import *

url_api = "https://api.eco.xoms.com.ar/"

# URL de la página de inicio de sesión (podría ser diferente de la URL del formulario)
login_url = "https://api.eco.xoms.com.ar/auth/login"  # Asumiendo que esta es la URL de la página de login

# URL a la que el formulario envía sus datos
form_action_url = "https://api.eco.xoms.com.ar/j_spring_security_check"  # Ajusta según la acción del formulario

# Tus credenciales
credentials = {
    "j_username": "20373762939",
    "j_password": "8eMnT0fU_"
}

# Crear una sesión para mantener las cookies
session = requests.Session()

# Envía la solicitud de inicio de sesión
response = session.post(form_action_url, data=credentials)

# Verifica si la autenticación fue exitosa
if response.ok:
    print("Autenticación exitosa")
    # Ahora puedes usar la sesión para hacer solicitudes autenticadas
    # response = session.get('URL de algún recurso protegido')
else:
    print("Autenticación fallida", response.status_code, response.text)

# Opcional: revisa el contenido de la respuesta para verificar el éxito
# print(response.text)

# Posiciones comitente 93481:
posicion_json = session.get("https://api.eco.xoms.com.ar/rest/risk/position/getPositions/93481").text

posicion_dict = json.loads(posicion_json)

# Extraer todas las posiciones detalladas
posicion = [
    {**position, "symbolReference": position["instrument"]["symbolReference"]}  # Agregar el symbolReference
    for position in posicion_dict["positions"]
]

# Crear DataFrame
posicion_df = pd.DataFrame(posicion)

# Eliminar la columna anidada "instrument" ya que extraemos "symbolReference"
posicion_df.drop(columns=["instrument"], inplace=True)


# Cuenta numero 93481

saldo_json = session.get("https://api.eco.xoms.com.ar/rest/risk/accountReport/93481").text

# Convertir JSON a diccionario
saldo_dict = json.loads(saldo_json)

# Extraer balances detallados de las monedas
saldo = []
for t, report in saldo_dict["accountData"]["detailedAccountReports"].items():
    for currency, details in report["currencyBalance"]["detailedCurrencyBalance"].items():
        saldo.append({
            "Plazo": t,
            "currency": currency,
            "consumed": details["consumed"],
            "available": details["available"],
            "settlementDate": report["settlementDate"]
        })

# Crear DataFrame
saldo_df = pd.DataFrame(saldo)


