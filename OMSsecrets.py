# -*- coding: utf-8 -*-
"""OMSsecrets.py — Loader de configuración sensible desde secrets.txt

Carga un archivo plano KEY=VALUE y popula os.environ, SIN pisar variables
que ya existan en el entorno real (útil en deploy: env vars del servidor
siempre tienen prioridad).

Uso típico (al inicio de OMSweb_app.py, antes de cualquier os.getenv):

    import OMSsecrets
    OMSsecrets.load()

Prioridad de resolución del archivo:
    1. Env var SECRETS_FILE (path explícito).
    2. secrets.txt en el mismo directorio que este módulo (junto al código).
    3. secrets.txt en el CWD (directorio desde donde se corre streamlit).

Si no se encuentra, retorna silenciosamente (las env vars del sistema
deberían estar definidas para producción).

Formato soportado:
    # Comentarios con '#'
    KEY=VALUE          → os.environ["KEY"] = "VALUE"
    KEY = VALUE        → espacios OK
    KEY="VALUE"        → comillas dobles removidas
    KEY='VALUE'        → comillas simples removidas
    KEY=               → valor vacío → NO setea (evita pisar con "")
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

_WIN_VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")

_SECRETS_FILENAME = "secrets.txt"

# Cache del resultado del último load()
_last_load: Dict[str, str] = {}


def _candidate_paths() -> List[str]:
    """Lista de paths candidatos, en orden de prioridad."""
    paths: List[str] = []

    # 1) Override explícito
    env_override = os.getenv("SECRETS_FILE")
    if env_override:
        paths.append(env_override)

    # 2) Junto al módulo (standard para instalación local)
    module_dir = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(module_dir, _SECRETS_FILENAME))

    # 3) CWD (útil si se corre desde otra carpeta)
    cwd = os.getcwd()
    if cwd != module_dir:
        paths.append(os.path.join(cwd, _SECRETS_FILENAME))

    return paths


def _resolve_secrets_path() -> Optional[str]:
    for p in _candidate_paths():
        if p and os.path.isfile(p):
            return p
    return None


def _parse_line(raw: str) -> Optional[tuple]:
    """Parsea una línea. Retorna (key, value) o None si se saltea.

    - Líneas vacías o que empiezan con '#' → None
    - KEY sin '=' → None
    - Valor vacío (KEY=) → None (para no pisar env real con '')

    Expansión: si el valor contiene `%VAR%`, `$VAR`, `${VAR}` o `~`, se
    expande con os.path.expandvars / expanduser (útil para paths
    portables tipo `%USERPROFILE%\\Carpeta\\...`).
    """
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None

    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()

    if not key:
        return None

    # Quitar comillas envolventes si las hay (idempotente)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]

    # Valor vacío → skip (respetamos la env var real si existe)
    if value == "":
        return None

    # Expandir vars del entorno y ~/  →  paths portables entre PCs.
    # Manual para %VAR% (porque os.path.expandvars en Linux solo entiende $VAR).
    if "%" in value:
        value = _WIN_VAR_RE.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if "$" in value or value.startswith("~"):
        value = os.path.expandvars(value)
        value = os.path.expanduser(value)

    return key, value


def load(path: Optional[str] = None, override: bool = False, verbose: bool = False) -> Dict[str, str]:
    """Carga secrets.txt a os.environ.

    Args:
        path: Ruta explícita al archivo. Si None, usa _resolve_secrets_path().
        override: Si True, pisa env vars existentes. Default False → env real gana.
        verbose: Si True, imprime qué se cargó (útil en debug, NO muestra valores).

    Returns:
        Dict con las variables que efectivamente se aplicaron a os.environ.
    """
    global _last_load

    resolved = path or _resolve_secrets_path()
    if resolved is None:
        if verbose:
            print("[OMSsecrets] No se encontró secrets.txt — usando sólo env vars del sistema.")
        _last_load = {}
        return _last_load

    applied: Dict[str, str] = {}
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            for raw_line in f:
                parsed = _parse_line(raw_line)
                if parsed is None:
                    continue
                key, value = parsed

                if override or key not in os.environ:
                    os.environ[key] = value
                    applied[key] = value
    except Exception as e:
        # No queremos que un secrets.txt mal formado rompa el arranque de la app.
        if verbose:
            print(f"[OMSsecrets] Error leyendo {resolved}: {e}")
        _last_load = {}
        return _last_load

    if verbose:
        print(f"[OMSsecrets] Cargadas {len(applied)} variables desde {resolved}")
        for k in applied:
            print(f"  → {k} (len={len(applied[k])})")  # no imprime valor

    _last_load = applied
    return applied


def status() -> Dict[str, any]:
    """Info de diagnóstico para mostrar en la UI (sin exponer valores).

    Útil para un sidebar que diga:
        "Secrets: cargados desde /path/to/secrets.txt — 5 variables"
    """
    resolved = _resolve_secrets_path()
    return {
        "path": resolved,
        "found": resolved is not None,
        "loaded_keys": sorted(_last_load.keys()),
        "n_loaded": len(_last_load),
    }


# ──────────────────────────────────────────────────────────────────────
# Auto-load en import (conveniente para uso típico)
# ──────────────────────────────────────────────────────────────────────

# Si definís OMS_SECRETS_NO_AUTOLOAD=1 en el env, evitás el auto-load.
# Esto es útil si querés llamarlo manualmente con parámetros específicos
# (por ejemplo, en un test).
if os.getenv("OMS_SECRETS_NO_AUTOLOAD") != "1":
    load(verbose=False)
