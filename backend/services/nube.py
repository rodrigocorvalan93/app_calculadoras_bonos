"""Marcadores de OneDrive ("sólo en la nube") en los archivos de datos.

Con Archivos a petición un archivo de la biblioteca compartida (Delta Bases,
Carteras, CAFCI) puede existir en disco SÓLO como marcador: `os.stat`,
`isfile`, `listdir` y hasta `zipfile.is_zipfile` lo ven como un archivo
normal (nombre, tamaño y mtime reales), pero el PRIMER `ReadFile` le pide el
contenido al motor de OneDrive y, si no lo entrega (cerrado, pausado, sin
sesión, sin red), falla con ERROR_CLOUD_FILE_* que el CRT traduce a EINVAL:
`OSError: [Errno 22] Invalid argument` en Python, "Error reading bytes from
file" en pyarrow. Un marcador NUNCA es un archivo corrupto: el writer no lo
aparta ni lo regenera (04/11: la PC nueva de un superuser con la biblioteca
entera sin bajar). Stdlib puro, sin efectos; fuera de Windows todo es False.
"""
from __future__ import annotations

import errno
import os
import sys
from typing import Any, Optional

# Los mismos bits que backend/tools/onedrive.py (el pre-flight del .bat).
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
SIN_CONTENIDO = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

_PLATFORM = sys.platform          # parcheable en los tests


def es_windows() -> bool:
    return _PLATFORM.startswith("win")


def es_marcador(path: Optional[str]) -> bool:
    """True si `path` existe sólo como marcador de OneDrive (sin contenido
    local). Un stat (µs); nunca abre el archivo. Fuera de Windows: False."""
    if not path or not es_windows():
        return False
    try:
        attrs = int(getattr(os.stat(path), "st_file_attributes", 0))
    except OSError:
        return False
    return bool(attrs & SIN_CONTENIDO)


def es_error_de_nube(exc: Optional[BaseException]) -> bool:
    """El error que deja un marcador sin bajar: EINVAL del CRT de Windows o el
    "Error reading bytes from file" de pyarrow (OSError sin errno)."""
    if exc is None or not es_windows():
        return False
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EINVAL:
        return True
    txt = str(exc)
    return "Invalid argument" in txt or "Error reading bytes from file" in txt


def ilegible_por_nube(path: Optional[str], exc: Optional[BaseException] = None) -> bool:
    """¿La lectura de `path` falló porque es un marcador de OneDrive sin
    bajar? Vale el atributo del archivo o la firma del error."""
    return es_marcador(path) or (es_error_de_nube(exc) and bool(path) and os.path.exists(str(path)))


def remedio(path: Any = "") -> str:
    """Qué hacer, para logs y mensajes de la UI."""
    nombre = os.path.basename(str(path)) if path else "el archivo"
    return (f"{nombre} está 'sólo en la nube' (Archivos a petición de OneDrive) y OneDrive no lo "
            "entregó: abrí OneDrive (sesión iniciada, sin pausa), botón derecho sobre la carpeta "
            "'Delta Bases' > \"Mantener siempre en este dispositivo\", o volvé a correr el .bat de "
            "la app (baja y fija las carpetas de datos)")
