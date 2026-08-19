"""_get_paced de bymaapi.py — el regulador anti-429 del barrido de precios.

El REST del broker corta ráfagas con HTTP 429 (visto en producción: ~400
requests del barrido → 429 a casi todo → la base llena de NaN). El wrapper
tiene que (a) espaciar los requests entre TODOS los threads (turnstile
global), (b) reintentar ante 429 respetando Retry-After, (c) agotados los
reintentos devolver el último Response para que el caller reporte el status.

Importar bymaapi entero tarda ~27 s (carga índices + universo), así que se
extrae SOLO _get_paced del fuente vía ast (mismo patrón que
test_bymaapi_guardar) con time/config inyectados — sin red ni sleeps reales.
"""
from __future__ import annotations

import ast
import threading
from pathlib import Path
from types import SimpleNamespace

import requests

_REPO = Path(__file__).resolve().parent.parent


class _FakeTime:
    """Reloj falso: sleep avanza el reloj y queda registrado (sin esperar)."""

    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(round(s, 6))
        self.t += s


class _FakeSession:
    """Devuelve respuestas enlatadas en orden y registra cada GET."""

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(self, url, params=None):
        self.calls.append(url)
        return self.responses.pop(0)


def _resp(status: int, retry_after=None) -> SimpleNamespace:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return SimpleNamespace(status_code=status, headers=headers)


def _paced(fake_time: _FakeTime, interval: float = 0.25, retries: int = 4):
    """Extrae _get_paced del fuente real con time/config inyectados."""
    tree = ast.parse((_REPO / "bymaapi.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "_get_paced")
    ns = {"time": fake_time, "requests": requests,
          "REQ_MIN_INTERVAL": interval, "REQ_RETRIES_429": retries,
          "_REQ_BACKOFF_BASE": 0.5, "_REQ_MAX_WAIT": 30.0,
          "_req_lock": threading.Lock(), "_req_ultimo": [0.0]}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "bymaapi.py", "exec"), ns)  # noqa: S102
    return ns["_get_paced"]


def test_429_reintenta_y_respeta_retry_after():
    ft = _FakeTime()
    get_paced = _paced(ft)
    ses = _FakeSession([_resp(429, retry_after="2"), _resp(200)])
    r = get_paced(ses, "http://x/md")
    assert r.status_code == 200 and len(ses.calls) == 2
    assert 2.0 in ft.sleeps                      # esperó el Retry-After del server


def test_pacing_espacia_requests_consecutivos():
    ft = _FakeTime()
    get_paced = _paced(ft, interval=0.5)
    ses = _FakeSession([_resp(200), _resp(200)])
    get_paced(ses, "http://x/1")
    get_paced(ses, "http://x/2")                 # inmediato → tiene que esperar el turno
    assert any(abs(s - 0.5) < 1e-6 for s in ft.sleeps)


def test_429_agotado_devuelve_el_ultimo_response():
    ft = _FakeTime()
    get_paced = _paced(ft, retries=3)
    ses = _FakeSession([_resp(429)] * 4)         # 1 intento + 3 reintentos
    r = get_paced(ses, "http://x/md")
    assert r.status_code == 429 and len(ses.calls) == 4
    # backoff exponencial creciente entre reintentos (sin Retry-After)
    esperas = [s for s in ft.sleeps if s not in (0.25,)]
    assert esperas == sorted(esperas)


def test_default_sin_limite_no_duerme():
    """BYMA_REQ_INTERVAL sin setear (default 0) = levantar todo a fondo:
    ningún sleep en el camino feliz — el pacing es 100 % opt-in."""
    ft = _FakeTime()
    get_paced = _paced(ft, interval=0.0)
    ses = _FakeSession([_resp(200), _resp(200), _resp(200)])
    for i in range(3):
        get_paced(ses, f"http://x/{i}")
    assert ft.sleeps == []


def test_sin_limite_429_usa_piso_de_backoff():
    """Aun a fondo, un 429 sin Retry-After NO se reintenta en caliente: espera
    el piso (_REQ_BACKOFF_BASE) — sin esto, interval 0 ⇒ backoff 0 ⇒ 4
    reintentos instantáneos que el server vuelve a rechazar."""
    ft = _FakeTime()
    get_paced = _paced(ft, interval=0.0)
    ses = _FakeSession([_resp(429), _resp(200)])
    r = get_paced(ses, "http://x/md")
    assert r.status_code == 200 and ft.sleeps == [0.5]


def test_retry_after_no_numerico_no_explota():
    ft = _FakeTime()
    get_paced = _paced(ft)
    # Retry-After como fecha HTTP (formato válido por spec) → cae al backoff
    ses = _FakeSession([_resp(429, retry_after="Wed, 19 Aug 2026 16:00:00 GMT"), _resp(200)])
    r = get_paced(ses, "http://x/md")
    assert r.status_code == 200 and len(ses.calls) == 2
