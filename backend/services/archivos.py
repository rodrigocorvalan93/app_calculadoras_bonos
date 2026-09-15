"""Helpers chicos de archivos de estado (JSON de alertas, preferencias…).

`apartar_corrupto`: un archivo que no se pudo parsear se RENOMBRA a
`<nombre>.corrupto-<AAAAMMDD-HHMMSS>` antes de que el módulo arranque vacío.
Sin esto, el siguiente guardado pisaba el archivo ilegible y se perdía lo que
había adentro (evidencia incluida). Nunca borra nada.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("backend.archivos")


def apartar_corrupto(p: Path, motivo: str = "") -> Optional[Path]:
    """Mueve `p` a `p.corrupto-<ts>` (si existe). Devuelve el destino o None."""
    try:
        p = Path(p)
        if not p.is_file():
            return None
        dst = p.with_name(f"{p.name}.corrupto-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        n = 1
        while dst.exists():
            n += 1
            dst = p.with_name(f"{p.name}.corrupto-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{n}")
        p.replace(dst)
        logger.warning("[archivos] %s ilegible (%s) → apartado como %s", p.name, motivo or "?", dst.name)
        return dst
    except OSError as exc:
        logger.warning("[archivos] no pude apartar %s: %s", p, exc)
        return None
