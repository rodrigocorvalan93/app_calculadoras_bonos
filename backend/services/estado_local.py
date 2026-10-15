"""Estado POR MÁQUINA fuera de la carpeta sincronizada por OneDrive (15/10).

En las PCs del desk el clon vive en la biblioteca de SharePoint que sincroniza
OneDrive. Tres cachés que cada instancia reescribe sola cada pocos minutos
vivían en `data/` adentro de ese clon:

    market_snapshot.json   store del mercado (~2 MB) — cada 5 min
    riesgo_pais.json       historia del riesgo país  — cada 30 min
    bna_fx.json            dólar BNA para el add-in  — cada hora

Con dos o más PCs corriendo la app, OneDrive veía el mismo archivo cambiado
en varias máquinas entre sincronizaciones y dejaba la versión perdedora como
copia en conflicto con el nombre de la PC (`market_snapshot-DAM-NB-CIO-191.json`):
miles de copias, ~6 GB en `data/`, que el chequeo de arranque
(`backend/tools/onedrive.py`) después bajaba enteras a cada PC. Ese estado es
de ESTA máquina (lo que vio su feed, lo que bajó su poller): no tiene por qué
viajar. Ahora vive en la misma carpeta local que el journal del histórico y
el cache de símbolos rechazados:

    %LOCALAPPDATA%\\bonos\\           (Windows)
    ~/.local/share/bonos/            (Mac / Linux)

`BONOS_LOCAL_DIR` cambia la carpeta (la suite la apunta a un tmp) y cada
servicio conserva su override de archivo (`MARKET_SNAPSHOT_PATH`,
`RIESGO_PAIS_PATH`, `BNA_FX_PATH`).

Migración sin pérdida: `ruta_lectura` lee el archivo viejo de `data/` UNA vez
si todavía no hay copia local (primer arranque con esta versión: la app abre
poblada como siempre); la primera escritura ya va a la carpeta local y desde
ahí se lee esa. El viejo queda quieto y el chequeo de arranque lo borra
cuando nadie lo escribió en una semana (una PC con la versión anterior
todavía corriendo lo sigue tocando hasta que reinicia).

Lo que SÍ se comparte a propósito queda en `data/`: pizarra y preferencias de
escenario (por usuario, escritas cuando el usuario cambia algo) y alertas (las
edita el superuser y además cada instancia las marca disparadas al cruzar:
escritura rara; una copia en conflicto de ellas puede traer un cambio del
usuario, por eso el chequeo de arranque NO las limpia).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = REPO_ROOT / "data"
ENV_DIR = "BONOS_LOCAL_DIR"


def dir_local() -> Path:
    """Carpeta local por máquina (no la crea: lo hace quien escribe)."""
    d = (os.getenv(ENV_DIR) or "").strip()
    if d:
        return Path(os.path.expanduser(d))
    base = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "bonos"


def ruta(nombre: str, env: str) -> Path:
    """Dónde se ESCRIBE `nombre`: el override `env` si está, si no la carpeta local."""
    v = (os.getenv(env) or "").strip()
    return Path(os.path.expanduser(v)) if v else dir_local() / nombre


def ruta_lectura(nombre: str, env: str) -> Path:
    """Dónde se LEE `nombre`: la ruta de escritura; si todavía no existe y no
    hay override, el archivo viejo de `data/` (migración: un `stat`, no baja
    nada de OneDrive hasta que alguien lo lee)."""
    p = ruta(nombre, env)
    if (os.getenv(env) or "").strip():
        return p
    try:
        if p.exists():
            return p
        viejo = LEGACY_DIR / nombre
        if viejo.exists():
            return viejo
    except OSError:
        pass
    return p
