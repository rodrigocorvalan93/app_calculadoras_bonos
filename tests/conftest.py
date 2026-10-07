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
# el cache local de símbolos rechazados por el broker (primary_ws) no se toca
# desde la suite: un test que lo necesite lo apunta a un tmp_path
os.environ.setdefault("PRIMARY_REJECTED_CACHE", "0")
# Journal LOCAL por máquina (historico_writer.journal_dir: px_tasas_*, marcas
# sin_rueda, memoria de la base `base_vista.json`): la suite nunca toca el
# real — un tmp nuevo por corrida (los tests que lo necesitan aislado por test
# lo apuntan a su tmp_path).
os.environ.setdefault("HISTORICO_JOURNAL_DIR", tempfile.mkdtemp(prefix="bonos_test_journal_"))
# Riesgo país (Inicio): la suite nunca sale a ArgentinaDatos ni toca el
# data/riesgo_pais.json real — poller apagado y archivo en un tmp.
os.environ.setdefault("RIESGO_PAIS", "0")
os.environ.setdefault("RIESGO_PAIS_PATH", os.path.join(tempfile.gettempdir(), "bonos_test_riesgo_pais.json"))
# Pizarra de Inicio (cuadros por usuario): nunca el data/pizarra.json real.
os.environ.setdefault("PIZARRA_PATH", os.path.join(tempfile.mkdtemp(prefix="bonos_test_pizarra_"), "pizarra.json"))
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-fixed-for-suite-0123456789")
os.environ.setdefault("APP_USERS_PATH", os.path.join(tempfile.gettempdir(), "bonos_test_auth_store.json"))
# Bootstrap del superuser de la suite: valores SINTÉTICOS (nunca una cuenta
# real — el repo se comparte y el historial de git no se limpia).
os.environ.setdefault("APP_SUPERUSER_USER", "su_test")
os.environ.setdefault("APP_SUPERUSER_PASSWORD", "clave-de-test-2026!")
os.environ.setdefault("APP_SUPERUSER_EMAIL", "su_test@example.com")


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
