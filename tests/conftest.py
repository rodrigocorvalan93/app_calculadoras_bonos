"""Make the repo root importable so `import especies / rentafija` resolves.

También configura el entorno de auth ANTES de que se importe el backend:
- store en un archivo temporal (no toca el auth_store.json real),
- secret de sesión fijo (así importar la app no escribe nada),
- superuser sembrado desde env,
- AUTH_ENABLED=0 por defecto → la suite existente sigue sin muro de login.
  Los tests de auth lo prenden con monkeypatch (settings.auth_enabled = True).
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("AUTH_ENABLED", "0")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-fixed-for-suite-0123456789")
os.environ.setdefault("APP_USERS_PATH", os.path.join(tempfile.gettempdir(), "bonos_test_auth_store.json"))
os.environ.setdefault("APP_SUPERUSER_USER", "rodricor93")
os.environ.setdefault("APP_SUPERUSER_PASSWORD", "Rc_874562")
os.environ.setdefault("APP_SUPERUSER_EMAIL", "rodrigocorvalan93@gmail.com")


import pytest


@pytest.fixture(autouse=True)
def _seq_fresca_por_test():
    """Los paneles seq_cached comparten el render mientras la seq del store no
    avance; en tests la seq está CONGELADA (sin feed) y una respuesta cacheada
    en un test cruzaría al siguiente (TTL 2 s). Avanzar la seq por test aísla
    el cache — mismo mecanismo que un tick real, sin tocar producción."""
    from backend.services import marketdata_store
    st = marketdata_store.get_store()
    with st._lock:
        st._updates += 1
    yield
