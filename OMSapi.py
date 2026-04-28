#%% """Funciones de bajo nivel para autenticación y peticiones HTTP."""
from typing import Any, Dict
import requests

import OMSsettings as cfg


def login(username: str, password: str) -> requests.Session:
    """Devuelve una sesión autenticada."""
    s = requests.Session()
    
    # Aumentar pool de conexiones para soportar bulk fetch paralelo
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=2,
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    r = s.post(
        f"{cfg.BASE_URL}j_spring_security_check",
        data={"j_username": username, "j_password": password},
        timeout=10,
    )
    r.raise_for_status()
    print("✔ Sesión iniciada en XOMS")
    return s


def fetch_json(session: requests.Session, path: str, **params) -> Dict[str, Any]:
    r = session.get(f"{cfg.BASE_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()
