"""
api.py
======

Autenticación y descarga *paralela* de market-data desde la API XOMS.

Todas las funciones arrojan `requests.HTTPError` ante errores HTTP ≥ 400.
"""

from __future__ import annotations

import concurrent.futures as fut
from typing import Any, Iterable, Mapping

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.latinsecurities.matrizoms.com.ar/"
ENTRADAS_POR_DEFECTO = "LA,BI,OF,CL,EV"


# --------------------------------------------------------------------------- #
# Sesión con reintentos
# --------------------------------------------------------------------------- #


def _crear_sesion_con_reintentos() -> requests.Session:
    """Devuelve una sesión `requests` con *retry* automático (códigos 502-504)."""
    politica = Retry(
        total=3,
        backoff_factor=0.4,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
    )
    ses = requests.Session()
    ses.mount("https://", HTTPAdapter(max_retries=politica))
    return ses


def iniciar_sesion(usuario: str, contraseña: str) -> requests.Session:
    """
    Inicia sesión en la API y entrega una sesión autenticada lista para usar.
    """
    ses = _crear_sesion_con_reintentos()
    resp = ses.post(
        f"{BASE_URL}j_spring_security_check",
        data={"j_username": usuario, "j_password": contraseña},
        timeout=8,
    )
    resp.raise_for_status()
    return ses


# --------------------------------------------------------------------------- #
# Descarga paralela de market-data
# --------------------------------------------------------------------------- #


def _descargar_uno(
    ses: requests.Session,
    símbolo: str,
    mercado_id: str,
    entradas: str,
    profundidad: int,
) -> dict[str, Any]:
    """Descarga market-data para un símbolo."""
    url = (
        f"{BASE_URL}rest/marketdata/get?marketId={mercado_id}"
        f"&symbol={requests.utils.quote(símbolo)}&entries={entradas}&depth={profundidad}"
    )
    r = ses.get(url, timeout=5)
    r.raise_for_status()
    payload = r.json()

    if payload.get("status") == "ERROR":
        raise RuntimeError(f"API error {símbolo}: {payload}")

    datos: dict[str, Any] = payload["marketData"]
    datos["symbol"] = símbolo
    return datos


def mercado_masivo(
    ses: requests.Session,
    símbolos: Iterable[str],
    *,
    mercado_id: str = "ROFX",
    entradas: str = ENTRADAS_POR_DEFECTO,
    profundidad: int = 3,
    hilos: int | None = None,
) -> pd.DataFrame:
    """
    Descarga market-data para muchos símbolos en paralelo.

    Retorna un DataFrame indexado por `symbol`.
    """
    with fut.ThreadPoolExecutor(max_workers=hilos) as executor:
        mapa = {
            executor.submit(
                _descargar_uno, ses, s, mercado_id, entradas, profundidad
            ): s
            for s in símbolos
        }
        salida: list[Mapping[str, Any]] = []
        for futu in fut.as_completed(mapa):
            try:
                salida.append(futu.result())
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️  {mapa[futu]}: {exc}")

    return pd.DataFrame(salida).set_index("symbol")
