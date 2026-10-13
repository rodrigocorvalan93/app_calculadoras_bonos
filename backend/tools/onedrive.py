"""Archivos a petición de OneDrive: bajar el código a ESTA PC antes de arrancar.

Pablo, 13/10: la app murió al importar `backend/services/bna_fx.py` con

    File "<frozen importlib._bootstrap_external>", line 951, in get_data
    OSError: [Errno 22] Invalid argument

El archivo era NUEVO (#242, 07/10) y la carpeta del código vive en la
biblioteca de SharePoint que sincroniza OneDrive: en las otras máquinas del
equipo un archivo nuevo llega como marcador "sólo en la nube" (Archivos a
petición, `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`) y el contenido se baja
recién cuando alguien lo abre. Si en ese momento el motor de sincronización
no puede entregarlo (OneDrive cerrado, pausado, sin sesión, sin red),
`ReadFile` falla con un error de la familia ERROR_CLOUD_FILE_* que el runtime
de C de Windows traduce a EINVAL (22): el `read()` de Python lo ve como
"Invalid argument" y no dice más. Lo mismo le puede pasar a cualquier
template, .js o .json que la app abre recién cuando lo necesita.

El .bat corre esta herramienta ANTES de uvicorn (y antes de https_local, que
ya importa medio backend):

  1. recorre la carpeta del proyecto (sin .git, __pycache__, data, certs, …;
     `os.scandir` con `follow_symlinks=False`: los atributos salen del
     listado, sin un syscall por archivo) y junta los archivos que todavía no
     tienen contenido local;
  2. los LEE enteros — eso le pide la bajada al motor de OneDrive — y, si la
     carpeta está sincronizada por la nube (reparse tag de OneDrive en algún
     archivo), la deja marcada "Siempre mantener en este dispositivo"
     (`attrib +P /S /D`, lo mismo que el botón derecho) para que lo que
     llegue con los próximos git pull venga ya bajado;
  3. si alguno NO se pudo bajar, sale con código 4 y el .bat explica qué
     hacer (abrir OneDrive, esperar que sincronice, volver a arrancar) en vez
     de dejar un traceback de importlib.

En Mac / Linux no hay nada que hacer (los clones viven fuera de OneDrive y
no existen los marcadores): sale 0 al instante.

    python -m backend.tools.onedrive            # bajar + fijar (lo que corre el .bat)
    python -m backend.tools.onedrive --listar   # sólo informar, no toca nada
    python -m backend.tools.onedrive --sin-pin  # bajar sin fijar la carpeta
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

# Constante (no `sys.platform` inline): los tests ejercitan la rama Windows en
# cualquier runner parcheándola.
_PLATFORM = sys.platform

# winnt.h — de estos el módulo `stat` sólo expone FILE_ATTRIBUTE_OFFLINE.
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_PINNED = 0x00080000
FILE_ATTRIBUTE_UNPINNED = 0x00100000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
# Un marcador SIN contenido local lleva alguno de estos tres (el de OneDrive
# "sólo en la nube" es RECALL_ON_DATA_ACCESS; OFFLINE / RECALL_ON_OPEN son los
# de otros proveedores y de las versiones viejas del cliente).
SIN_CONTENIDO = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

# Reparse tag de los archivos de un proveedor de nube (IsReparseTagCloud):
# 0x9000x01A — OneDrive lo deja también en los archivos ya bajados, así que
# sirve para saber si la carpeta está sincronizada aunque todo esté local.
IO_REPARSE_TAG_CLOUD = 0x9000001A
IO_REPARSE_TAG_CLOUD_MASK = 0x0000F000

# Carpetas que no hacen falta para correr la app (o que no deben tocarse):
# .git es grande y consola.version() lo lee a mano sin tirar; data/ y certs/
# son locales de cada máquina; los venv nunca van adentro del repo.
EXCLUIR = frozenset({".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                     ".venv", "venv", "node_modules", "certs", "data", ".claude"})

_MB = 1 << 20
EXIT_SIN_BAJAR = 4           # distinto del 3 = "la app ya está corriendo" de main.py


@dataclass
class Archivo:
    path: Path
    attrs: int
    tag: int
    size: int

    @property
    def sin_contenido(self) -> bool:
        return sin_contenido(self.attrs)

    @property
    def nube(self) -> bool:
        return es_nube(self.tag)


@dataclass
class Escaneo:
    root: Path
    total: int = 0                                   # archivos vistos (sin EXCLUIR)
    pendientes: List[Archivo] = field(default_factory=list)
    nube: bool = False                               # algún archivo / carpeta con tag de nube
    root_fijado: bool = False                        # la carpeta raíz ya está "siempre en este dispositivo"
    errores: List[Tuple[Path, OSError]] = field(default_factory=list)   # listados que fallaron


def es_windows() -> bool:
    return _PLATFORM.startswith("win")


def sin_contenido(attrs: int) -> bool:
    return bool(attrs & SIN_CONTENIDO)


def es_nube(tag: int) -> bool:
    return bool(tag) and (tag & ~IO_REPARSE_TAG_CLOUD_MASK) == IO_REPARSE_TAG_CLOUD


def _atributos(entry: "os.DirEntry[str]") -> Tuple[int, int, int]:
    """(st_file_attributes, st_reparse_tag, st_size) de una entrada del
    listado, sin seguir el reparse point (en Windows sale del FindFirstFile:
    cero syscalls extra; con follow_symlinks=True un marcador de OneDrive
    obligaría a un stat real por archivo). Fuera de Windows los atributos
    no existen → 0."""
    st = entry.stat(follow_symlinks=False)
    return (getattr(st, "st_file_attributes", 0) or 0,
            getattr(st, "st_reparse_tag", 0) or 0,
            int(getattr(st, "st_size", 0) or 0))


def _atributos_de(path: Path) -> Tuple[int, int]:
    """(attrs, tag) de una ruta (la raíz). Nunca tira."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0
    return (getattr(st, "st_file_attributes", 0) or 0, getattr(st, "st_reparse_tag", 0) or 0)


def _es_dir(entry: "os.DirEntry[str]") -> bool:
    """Carpeta real (no symlink ni junction: evita loops). Un marcador de
    OneDrive es reparse point pero NO symlink, así que `is_dir(False)` lo ve."""
    try:
        if entry.is_symlink():
            return False
        es_junction = getattr(entry, "is_junction", None)
        if es_junction is not None and es_junction():
            return False
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def escanear(root: Path, excluir: Iterable[str] = EXCLUIR) -> Escaneo:
    """Recorre `root` (sin las carpetas de `excluir`, por nombre, a cualquier
    nivel) y junta los archivos sin contenido local. Un listado que falla
    (permisos, OneDrive a medio sincronizar) queda en `errores` y se sigue."""
    excl = frozenset(excluir)
    esc = Escaneo(root=root)
    attrs, tag = _atributos_de(root)
    esc.root_fijado = bool(attrs & FILE_ATTRIBUTE_PINNED)
    esc.nube = es_nube(tag)
    pila = [root]
    while pila:
        d = pila.pop()
        try:
            with os.scandir(d) as it:
                entradas = list(it)
        except OSError as e:
            esc.errores.append((d, e))
            continue
        for entry in entradas:
            if entry.name in excl:
                continue
            try:
                attrs, tag, size = _atributos(entry)
            except OSError as e:
                esc.errores.append((Path(entry.path), e))
                continue
            if es_nube(tag):
                esc.nube = True
            if _es_dir(entry):
                pila.append(Path(entry.path))
                continue
            esc.total += 1
            if sin_contenido(attrs):
                esc.pendientes.append(Archivo(Path(entry.path), attrs, tag, size))
    esc.pendientes.sort(key=lambda a: str(a.path).lower())
    return esc


def _leer(path: Path) -> None:
    """Lee el archivo entero: con OneDrive corriendo, eso dispara la bajada
    (el open solo no alcanza — el contenido llega con el ReadFile)."""
    with open(path, "rb") as f:
        while f.read(4 * _MB):
            pass


def hidratar(pendientes: Iterable[Archivo],
             avisar: Optional[Callable[[str], None]] = None) -> List[Tuple[Archivo, OSError]]:
    """Baja cada pendiente leyéndolo. Devuelve los que no se pudieron leer
    (OneDrive cerrado / pausado / sin red → [Errno 22] en Windows)."""
    fallos: List[Tuple[Archivo, OSError]] = []
    for a in pendientes:
        try:
            _leer(a.path)
        except OSError as e:
            fallos.append((a, e))
            if avisar:
                avisar(f"x {a.path}: {e}")
        else:
            if avisar:
                avisar(f"  {a.path} ({_kb(a.size)}) ok")
    return fallos


def fijar(root: Path, run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run) -> Tuple[bool, str]:
    """"Siempre mantener en este dispositivo" para la carpeta y todo lo de
    adentro: `attrib +P` sobre la raíz (las entradas nuevas heredan el
    estado) y `attrib +P /S /D` desde adentro (todo lo que ya existe, .git
    incluido). attrib viene con Windows; no pide admin y no toca mtimes."""
    try:
        r1 = run(["attrib", "+P", str(root)], capture_output=True, text=True, timeout=60)
        r2 = run(["attrib", "+P", "/S", "/D"], cwd=str(root), capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r1.returncode == 0 and r2.returncode == 0:
        return True, ""
    det = ((r1.stderr or "") + (r1.stdout or "") + (r2.stderr or "") + (r2.stdout or "")).strip()
    return False, det or f"attrib devolvió {r1.returncode} / {r2.returncode}"


def _kb(n: int) -> str:
    return f"{n / 1024:,.0f} KB".replace(",", ".") if n >= 1024 else f"{n} B"


def _say(msg: str) -> None:
    """print que no muere si stdout está redirigido a un cp1252 pobre."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Bajar a esta PC los archivos del código que OneDrive "
                                             "dejó 'sólo en la nube' (Archivos a petición)")
    ap.add_argument("--listar", action="store_true", help="sólo informar, sin bajar ni fijar")
    ap.add_argument("--sin-pin", action="store_true", help="bajar sin marcar la carpeta "
                                                           "'Siempre mantener en este dispositivo'")
    ap.add_argument("--carpeta", default="", help="carpeta a revisar (default: la raíz del proyecto)")
    ap.add_argument("--quiet", action="store_true", help="sólo problemas")
    args = ap.parse_args(argv)

    if not es_windows():
        return 0                                     # sin marcadores fuera de Windows

    root = Path(args.carpeta).resolve() if args.carpeta else default_root()
    esc = escanear(root)
    say = (lambda m: None) if args.quiet else _say   # noqa: E731

    if not esc.nube and not esc.pendientes:
        return 0                                     # carpeta común (fuera de OneDrive): silencio
    for d, e in esc.errores:
        _say(f"[onedrive] ! no pude listar {d}: {e}")

    if not esc.pendientes:
        say(f"[onedrive] código completo en esta PC ({esc.total} archivos"
            f"{', carpeta fijada' if esc.root_fijado else ''})")
    else:
        if args.listar:
            _say(f"[onedrive] {len(esc.pendientes)} de {esc.total} archivos están 'sólo en la nube':")
            for a in esc.pendientes:
                _say(f"[onedrive]   {a.path} ({_kb(a.size)})")
            return EXIT_SIN_BAJAR
        total_kb = sum(a.size for a in esc.pendientes)
        _say(f"[onedrive] {len(esc.pendientes)} de {esc.total} archivos del código están 'sólo en la nube' "
             f"(Archivos a petición de OneDrive, {_kb(total_kb)}): bajándolos…")
        fallos = hidratar(esc.pendientes, avisar=lambda m: _say(f"[onedrive] {m}"))
        if fallos:
            _say(f"[onedrive] {len(fallos)} archivo(s) siguen sin contenido: OneDrive no los entregó "
                 "(cerrado, pausado, sin sesión o sin red). La app no puede arrancar así.")
            return EXIT_SIN_BAJAR

    if esc.nube and not esc.root_fijado and not args.sin_pin and not args.listar:
        ok, det = fijar(root)
        if ok:
            say("[onedrive] carpeta marcada \"Siempre mantener en este dispositivo\" (attrib +P): "
                "lo que llegue con los próximos git pull viene ya bajado")
        else:
            _say(f"[onedrive] ! no pude fijar la carpeta con attrib ({det}); a mano: botón derecho "
                 "sobre la carpeta del código > \"Siempre mantener en este dispositivo\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
