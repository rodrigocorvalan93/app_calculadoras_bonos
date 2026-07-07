"""Rutas de secrets.txt portables entre Windows y macOS/Linux.

El secrets.txt del equipo trae las carpetas Delta en estilo Windows:

    DELTA_BASES_DIR=~\\DELTA ASSET MANAGEMENT S.A\\Inversiones - Documentos\\Delta Bases\\Carteras
    DELTA_CAFCI_DIR=%USERPROFILE%\\DELTA ASSET MANAGEMENT S.A\\...\\Precios Cafci

En Windows, OMSsecrets ya las expande al cargar y existen tal cual. En una
Mac, ni `~\\...` (expanduser no entiende backslash) ni `%USERPROFILE%` se
expanden, y aunque se expandieran la carpeta vive en otro lado: OneDrive
sincroniza las bibliotecas compartidas bajo

    ~/Library/CloudStorage/OneDrive-SharedLibraries-<Org sin espacios>/<cola idéntica>

donde la "cola" (p. ej. `Inversiones - Documentos/Delta Bases/Carteras`) es
la MISMA que en Windows a partir de la carpeta del tenant.

`expand()` resuelve eso sin tocar secrets.txt: expande como siempre y, si el
resultado no existe (y no estamos en Windows), busca la cola de carpetas más
larga que exista bajo las raíces OneDrive locales. Si nada matchea devuelve
la expansión directa — el caller conserva su chequeo isdir/isfile y sus
mensajes de error de siempre. En Windows NUNCA se escanea: la ruta existe
directo y el comportamiento es idéntico al histórico.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

_WIN_VAR_RE = re.compile(r"%([^%]+)%")

# Sufijo mínimo (en componentes) para aceptar un match bajo una raíz OneDrive:
# con 1 solo componente ("Carteras") el riesgo de matchear una carpeta
# homónima ajena es alto; la cola real más corta del equipo tiene 2
# ("Inversiones - Documentos/Delta Bases").
_MIN_TAIL = 2


def _expand_direct(raw: str) -> str:
    """Expansión clásica multiplataforma: %VAR% (con USERPROFILE/HOME cayendo
    al home real si la env no existe), $VAR/${VAR} y ~ (con / o \\)."""
    home = os.path.expanduser("~")

    def _sub(m: "re.Match[str]") -> str:
        val = os.environ.get(m.group(1))
        if val:
            return val
        if m.group(1).upper() in ("USERPROFILE", "HOMEPATH", "HOME"):
            return home
        return m.group(0)

    s = _WIN_VAR_RE.sub(_sub, raw)
    s = os.path.expandvars(s)
    # expanduser posix no entiende '~\...' (backslash no es separador ahí).
    if s == "~" or s[:2] in ("~/", "~\\"):
        s = home + s[1:]
    else:
        s = os.path.expanduser(s)
    return s


def _exists(p: str, want: str) -> bool:
    if want == "file":
        return os.path.isfile(p)
    if want == "dir":
        return os.path.isdir(p)
    return os.path.exists(p)


def _parts(expanded: str) -> List[str]:
    """Componentes de la ruta, tolerante a ambos separadores. Descarta drive
    (C:), '~' suelto y variables sin expandir (%USERPROFILE%) — lo que queda
    es la cola de carpetas 'real' que existe igual en todas las plataformas."""
    out: List[str] = []
    for part in re.split(r"[\\/]+", expanded):
        part = part.strip()
        if not part or part == "~" or "%" in part:
            continue
        if re.fullmatch(r"[A-Za-z]:", part):
            continue
        out.append(part)
    return out


def _onedrive_roots() -> List[Path]:
    """Raíces locales donde OneDrive materializa los árboles sincronizados.
    macOS: ~/Library/CloudStorage/<OneDrive-...>. Fallbacks: ~/OneDrive* y ~."""
    home = Path.home()
    roots: List[Path] = []
    cloud = home / "Library" / "CloudStorage"
    try:
        if cloud.is_dir():
            roots.extend(sorted(p for p in cloud.iterdir() if p.is_dir()))
    except OSError:
        pass
    try:
        roots.extend(sorted(p for p in home.glob("OneDrive*") if p.is_dir()))
    except OSError:
        pass
    roots.append(home)
    return roots


def _search_onedrive(parts: List[str], want: str) -> Optional[str]:
    """La cola de `parts` más larga que exista bajo alguna raíz OneDrive.
    Prioridad: sufijo más largo primero (match más específico gana); dentro
    del mismo largo, el orden estable de `_onedrive_roots`."""
    roots = _onedrive_roots()
    for start in range(len(parts)):
        tail = parts[start:]
        if start > 0 and len(tail) < _MIN_TAIL:
            break
        for root in roots:
            cand = str(root.joinpath(*tail))
            if _exists(cand, want):
                return cand
    return None


def expand(raw: Optional[str], want: str = "dir") -> Optional[str]:
    """Ruta de secrets.txt → ruta usable en ESTA máquina.

    1) Expansión directa (~, %VAR%, $VAR). Si existe, esa es la respuesta —
       en Windows siempre corta acá (comportamiento histórico intacto).
    2) En macOS/Linux, si no existe: busca la misma cola de carpetas bajo
       las raíces OneDrive locales (CloudStorage / ~/OneDrive* / ~).
    3) Sin match: devuelve la expansión directa igual que antes, para que el
       caller falle con el mismo chequeo y mensaje de siempre.

    `want`: "dir" | "file" | "any" — qué debe ser la ruta para considerarla
    encontrada (los callers chequean después de todos modos)."""
    if not raw:
        return raw
    direct = _expand_direct(raw)
    if _exists(direct, want) or os.name == "nt":
        return direct
    parts = _parts(direct)
    if parts:
        hit = _search_onedrive(parts, want)
        if hit:
            return hit
    return direct
