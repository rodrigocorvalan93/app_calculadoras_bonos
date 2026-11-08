"""Qué hay de nuevo — los últimos cambios de la app, para TODOS los usuarios
(`/novedades`, link en el pie con la versión).

Fuente: el `git log` del clon. Los títulos de los PRs mergeados a main ya son
un changelog en es-AR ("YAS: layout compacto…", "Excel =OMS.CASHFLOW…"): no
hay un archivo que mantener a mano. Se lee UNA vez, en un thread de fondo al
arrancar (nunca en un request) y queda en memoria; `consola._git_disponible`
evita el stub de Apple en una Mac sin Command Line Tools. Sin git o sin
`.git` (zip bajado a mano) la lista queda vacía y la página dice por qué."""
from __future__ import annotations

import logging
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from backend import consola

logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parents[2]
MAX_ITEMS = 60
_RE_PR = re.compile(r"\s*\(#(\d+)\)\s*$")
_lock = threading.Lock()
_items: List[Dict[str, Any]] = []
_version = ""
_estado = {"cargado": False, "motivo": "todavía no se leyó"}


def _leer_git(n: int = MAX_ITEMS) -> List[str]:
    """Líneas `sha<US>fecha<US>título` del log; OSError si git no está."""
    if not consola._git_disponible():
        raise OSError("git no disponible (macOS sin Command Line Tools)")
    r = subprocess.run(["git", "-C", str(_ROOT), "log", f"-{int(n)}", "--format=%h%x1f%cs%x1f%s", "HEAD"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5.0)
    if r.returncode != 0:
        raise OSError((r.stderr or "git log falló").strip()[:200])
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def _parsear(lineas: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in lineas:
        partes = ln.split("\x1f")
        if len(partes) < 3:
            continue
        sha, fecha, titulo = partes[0].strip(), partes[1].strip(), partes[2].strip()
        m = _RE_PR.search(titulo)
        pr = int(m.group(1)) if m else None
        if m:
            titulo = titulo[:m.start()].rstrip()
        try:
            fecha_fmt = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            fecha_fmt = fecha
        out.append({"sha": sha, "fecha": fecha, "fecha_fmt": fecha_fmt, "titulo": titulo, "pr": pr})
    return out


def cargar() -> None:
    """Lee el log y la versión. Nunca tira: un fallo deja el motivo."""
    global _items, _version
    try:
        items = _parsear(_leer_git())
        ver = consola.version()
        with _lock:
            _items = items
            _version = ver
            _estado.update(cargado=True, motivo="")
    except Exception as exc:  # noqa: BLE001
        with _lock:
            if not _items:                       # lo ya leído sigue valiendo
                _estado.update(cargado=False, motivo=f"{type(exc).__name__}: {exc}"[:200])
        logger.info("[novedades] sin historial de git: %s", exc)


def iniciar() -> None:
    """Thread daemon: el `git log` (decenas de ms, más en OneDrive) no va en el arranque."""
    threading.Thread(target=cargar, name="novedades", daemon=True).start()


def items() -> List[Dict[str, Any]]:
    with _lock:
        return list(_items)


def version() -> str:
    """'rama @ sha7 · AAAA-MM-DD' (la del banner) o '' si no se pudo leer."""
    with _lock:
        return _version


def estado() -> Dict[str, Any]:
    with _lock:
        return dict(_estado, n=len(_items))
