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
  2. los LEE enteros — eso le pide la bajada al motor de OneDrive (un
     `attrib +P` solo es un pedido asincrónico: no garantiza nada cuando
     vuelve) — y, si la carpeta está sincronizada por la nube, la deja
     marcada "Mantener siempre en este dispositivo" (`attrib -U +P`, lo
     mismo que el botón derecho) para que lo que llegue con los próximos git
     pull venga ya bajado y Storage Sense (Windows 11 22H2: "sólo en la
     nube" lo que no se abrió en 30 días) no lo vuelva a vaciar;
  3. si alguno NO se pudo bajar, sale con código 4 y el .bat explica qué
     hacer (abrir OneDrive, esperar que sincronice, volver a arrancar) en vez
     de dejar un traceback de importlib.

Antes de bajar nada BORRA los restos de los cachés por máquina que hasta el
15/10 cada PC reescribía adentro de la carpeta (`CACHES_POR_MAQUINA`: el
snapshot del store cada 5 min, BNA, riesgo país, el dump CER): OneDrive dejaba
la versión perdedora como copia en conflicto con el nombre de la PC
(`data/market_snapshot-DAM-NB-CIO-191.json`, miles, ~6 GB) y este chequeo las
bajaba enteras en cada PC. Borrar un marcador "sólo en la nube" no lo
descarga; ese estado ahora vive en %LOCALAPPDATA%\\bonos
(`backend.services.estado_local`). Con muchos pendientes el progreso sale
resumido por carpeta (no una línea por archivo).

"Sincronizada por la nube" se decide por tres caminos, porque Windows puede
mostrarle los marcadores "disfrazados" a un proceso común (sin el bit de
reparse point ni el tag): el tag de nube (0x9000x01A) en alguna entrada del
listado — para verlo se pide `RtlSetProcessPlaceholderCompatibilityMode(2)`
al arrancar —, los atributos que sólo pone el motor de nube
(RECALL_ON_DATA_ACCESS / PINNED / UNPINNED, visibles aun disfrazados) o la
carpeta bajo una raíz de sincronización de OneDrive (variables `OneDrive*`
y el registro `HKCU\\Software\\Microsoft\\OneDrive\\Accounts`: ahí están
también las bibliotecas de SharePoint, que NO cuelgan de %OneDrive%).

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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

# Constante (no `sys.platform` inline): los tests ejercitan la rama Windows en
# cualquier runner parcheándola.
_PLATFORM = sys.platform

# winnt.h — de estos el módulo `stat` sólo expone DIRECTORY y OFFLINE.
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

# Atributos que SÓLO pone el motor de archivos en la nube (el estado de pin
# lo deja OneDrive en cada archivo): verlos en alguna entrada = carpeta
# sincronizada, aunque el proceso vea los marcadores disfrazados.
DE_NUBE = SIN_CONTENIDO | FILE_ATTRIBUTE_PINNED | FILE_ATTRIBUTE_UNPINNED

# Reparse tag de los archivos de un proveedor de nube (RtlIsCloudFilesPlaceholder):
# 0x9000x01A — OneDrive lo deja también en los archivos ya bajados, así que
# sirve para saber si la carpeta está sincronizada aunque todo esté local.
IO_REPARSE_TAG_CLOUD = 0x9000001A
IO_REPARSE_TAG_CLOUD_MASK = 0x0000F000

# ntdll.RtlSetProcessPlaceholderCompatibilityMode (Windows 10 1803+):
# 2 = PHCM_EXPOSE_PLACEHOLDERS — el proceso ve el bit de reparse point y el
# tag de los marcadores (por default a una app "común" se los esconden).
PHCM_EXPOSE_PLACEHOLDERS = 2

# Variables que Windows deja con la raíz de cada OneDrive (personal / empresa).
# Las bibliotecas de SharePoint sincronizadas NO cuelgan de ahí: viven en
# %USERPROFILE%\<Tenant>\<Biblioteca> y sólo figuran en el registro.
_ENV_RAICES = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
_REG_ACCOUNTS = r"Software\Microsoft\OneDrive\Accounts"

# Carpetas que no hacen falta para correr la app (o que no deben tocarse):
# .git es grande y consola.version() lo lee a mano sin tirar; los venv nunca
# van adentro del repo. certs/ y data/ SÍ entran: viven adentro del clon (o
# sea, sincronizados) y https_local / las preferencias compartidas (pizarra,
# escenario, alertas) los leen — un cert "sólo en la nube" haría regenerar la
# CA. Los cachés por máquina ya no viven en data/ (CACHES_POR_MAQUINA).
EXCLUIR = frozenset({".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                     ".venv", "venv", "node_modules", ".claude"})

_MB = 1 << 20
EXIT_SIN_BAJAR = 4           # distinto del 3 = "la app ya está corriendo" de main.py

# Cachés POR MÁQUINA que hasta el 15/10 cada PC reescribía adentro de esta
# carpeta: OneDrive veía el mismo archivo cambiado en dos máquinas y dejaba la
# perdedora al lado con el nombre de la PC ("market_snapshot-DAM-NB-CIO-191.json").
# Desde el 15/10 viven en la carpeta local (backend.services.estado_local); acá
# se borran, sin bajarlas, las copias en conflicto y los temporales huérfanos,
# y el original cuando nadie lo escribió en `ORIGINAL_VIEJO_DIAS` (una PC con
# la versión anterior todavía corriendo lo sigue tocando hasta que reinicia).
# (carpeta relativa a la raíz — "" = la raíz —, archivo original, ¿se borra el
# original viejo?). bcra_data_backup.json está versionado en git: sólo sus copias.
CACHES_POR_MAQUINA = (
    ("data", "market_snapshot.json", True),
    ("data", "riesgo_pais.json", True),
    ("data", "bna_fx.json", True),
    ("", "cer_completo.generated.csv", True),
    ("", "bcra_data_backup.json", False),
)
ORIGINAL_VIEJO_DIAS = 7
TMP_MIN_EDAD_S = 600         # un .tmp más nuevo puede ser una escritura en curso de una PC vieja
DETALLE_MAX = 40             # más pendientes que esto: progreso resumido, no una línea por archivo


@dataclass
class Archivo:
    path: Path
    attrs: int
    tag: int
    size: int
    origen: str = ""         # basura: el caché al que pertenece ("market_snapshot.json")
    motivo: str = ""         # basura: "copia en conflicto" / "temporal" / "original viejo"

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
    basura: List[Archivo] = field(default_factory=list)  # restos de cachés por máquina (no se bajan)


def es_windows() -> bool:
    return _PLATFORM.startswith("win")


def sin_contenido(attrs: int) -> bool:
    return bool(attrs & SIN_CONTENIDO)


def es_nube(tag: int) -> bool:
    return bool(tag) and (tag & ~IO_REPARSE_TAG_CLOUD_MASK) == IO_REPARSE_TAG_CLOUD


def de_nube(attrs: int) -> bool:
    return bool(attrs & DE_NUBE)


def basura_de(carpeta_rel: str, nombre: str, edad_s: Optional[float]) -> Optional[Tuple[str, str]]:
    """(original, motivo) si `nombre` —en `carpeta_rel`, relativa a la raíz:
    "data" o "" — es un resto de un caché por máquina; None si no (o si no
    se puede decidir sin la edad). Sin distinguir mayúsculas, como Windows.

    - copia en conflicto: `<stem>` + "-", " " o "(" + lo que sea + `<ext>`
      ("market_snapshot-DAM-NB-CIO-191.json", "bna_fx (1).json");
    - temporal: `<original>…tmp` con más de `TMP_MIN_EDAD_S` (los `.tmp` /
      `.<pid>.tmp` de los escritores y sus propias copias en conflicto);
    - original viejo: el original mismo, si se puede borrar y nadie lo tocó
      en `ORIGINAL_VIEJO_DIAS`."""
    low = nombre.lower()
    for carpeta, original, borrar_original in CACHES_POR_MAQUINA:
        if carpeta != carpeta_rel:
            continue
        orig = original.lower()
        stem, ext = os.path.splitext(orig)
        if low == orig:
            if borrar_original and edad_s is not None and edad_s > ORIGINAL_VIEJO_DIAS * 86400:
                return original, "original viejo"
            return None
        if low.startswith(orig) and low.endswith(".tmp"):
            if edad_s is not None and edad_s > TMP_MIN_EDAD_S:
                return original, "temporal"
            return None
        if (low.startswith(stem) and low.endswith(ext) and len(low) > len(orig)
                and low[len(stem)] in "- ("):
            return original, "copia en conflicto"
    return None


def _candidato(carpeta_rel: str, nombre: str) -> bool:
    """¿Vale la pena mirar la edad? Prefijo de algún caché de esa carpeta."""
    low = nombre.lower()
    return any(c == carpeta_rel and low.startswith(os.path.splitext(o.lower())[0])
               for c, o, _b in CACHES_POR_MAQUINA)


_CARPETAS_CACHE = frozenset(c for c, _o, _b in CACHES_POR_MAQUINA)


def exponer_marcadores() -> bool:
    """Pide ver los marcadores sin disfraz (reparse point + tag) para ESTE
    proceso. Sólo Windows ≥ 1803; si ntdll no lo tiene o falla, False y se
    sigue con los atributos (RECALL_ON_DATA_ACCESS se ve igual)."""
    if not es_windows():
        return False
    try:
        import ctypes
        fn = ctypes.windll.ntdll.RtlSetProcessPlaceholderCompatibilityMode   # type: ignore[attr-defined]
        fn.restype = ctypes.c_byte
        fn.argtypes = [ctypes.c_byte]
        return fn(PHCM_EXPOSE_PLACEHOLDERS) >= 0
    except Exception:  # noqa: BLE001 — AttributeError / OSError / ValueError
        return False


def raices_onedrive() -> List[str]:
    """Raíces de sincronización de esta cuenta de Windows: variables
    OneDrive* + registro (UserFolder de cada cuenta, bibliotecas de SharePoint
    en `Tenants\\<tenant>` — los NOMBRES de los valores son las carpetas — y
    `ScopeIdToMountPointPathCache`). Vacío fuera de Windows; nunca tira."""
    raices: List[str] = []
    for var in _ENV_RAICES:
        v = (os.environ.get(var) or "").strip()
        if v:
            raices.append(v)
    if not es_windows():
        return raices
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return raices
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_ACCOUNTS) as cuentas:
            for i in range(64):
                try:
                    nombre = winreg.EnumKey(cuentas, i)
                except OSError:
                    break
                with winreg.OpenKey(cuentas, nombre) as cuenta:
                    try:
                        v, _t = winreg.QueryValueEx(cuenta, "UserFolder")
                        if isinstance(v, str) and v.strip():
                            raices.append(v.strip())
                    except OSError:
                        pass
                    for sub, modo in (("Tenants", "nombres"), ("ScopeIdToMountPointPathCache", "datos")):
                        try:
                            with winreg.OpenKey(cuenta, sub) as k:
                                raices.extend(_valores_reg(winreg, k, modo))
                        except OSError:
                            pass
    except OSError:
        pass
    return raices


def _valores_reg(winreg, key, modo: str) -> List[str]:
    """`Tenants` tiene UNA subclave por tenant cuyos valores se llaman como
    las carpetas locales (modo 'nombres'); `ScopeIdToMountPointPathCache`
    tiene los paths como DATOS (modo 'datos')."""
    out: List[str] = []
    claves = [key]
    if modo == "nombres":
        claves = []
        for i in range(64):
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            try:
                claves.append(winreg.OpenKey(key, sub))
            except OSError:
                pass
    for k in claves:
        try:
            for i in range(256):
                try:
                    nombre, dato, _t = winreg.EnumValue(k, i)
                except OSError:
                    break
                v = nombre if modo == "nombres" else dato
                if isinstance(v, str) and len(v) > 3 and v[1:3] == ":\\":
                    out.append(v.strip())
        finally:
            if k is not key:
                try:
                    k.Close()
                except Exception:  # noqa: BLE001
                    pass
    return out


def bajo_raiz(root: Path, raices: Iterable[str]) -> bool:
    """¿`root` está adentro (o es) alguna raíz? Comparación por texto con las
    reglas de Windows (`ntpath`: sin distinguir mayúsculas ni `/` de `\\`),
    para que el test corra en cualquier runner."""
    import ntpath
    r = ntpath.normcase(ntpath.normpath(str(root))).rstrip("\\")
    for raiz in raices:
        z = ntpath.normcase(ntpath.normpath(raiz)).rstrip("\\")
        if z and (r == z or r.startswith(z + "\\")):
            return True
    return False


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


def _mtime(entry: "os.DirEntry[str]") -> Optional[float]:
    """mtime de la entrada (en Windows sale del mismo listado: `DirEntry.stat`
    queda cacheado). None si no se puede."""
    try:
        return float(entry.stat(follow_symlinks=False).st_mtime)
    except OSError:
        return None


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


def escanear(root: Path, excluir: Iterable[str] = EXCLUIR,
             raices: Optional[Iterable[str]] = None, ahora: Optional[float] = None) -> Escaneo:
    """Recorre `root` (sin las carpetas de `excluir`, por nombre, a cualquier
    nivel) y junta los archivos sin contenido local. `nube` = tag de nube o
    atributo de nube en alguna entrada, o `root` bajo una raíz de OneDrive
    (`raices`; default `raices_onedrive()`). Un listado que falla (permisos,
    OneDrive a medio sincronizar) queda en `errores` y se sigue. Los restos
    de cachés por máquina (`basura_de`, sólo en la raíz y en `data/`) van a
    `basura` — ni a `pendientes` ni a `total` — tengan contenido o no."""
    excl = frozenset(excluir)
    ahora = time.time() if ahora is None else ahora
    esc = Escaneo(root=root)
    attrs, tag = _atributos_de(root)
    esc.root_fijado = bool(attrs & FILE_ATTRIBUTE_PINNED)
    esc.nube = es_nube(tag) or de_nube(attrs) or bajo_raiz(root, raices_onedrive() if raices is None else raices)
    pila = [root]
    while pila:
        d = pila.pop()
        try:
            with os.scandir(d) as it:
                entradas = list(it)
        except OSError as e:
            esc.errores.append((d, e))
            continue
        # carpeta relativa a la raíz, sólo para la raíz y sus hijas directas
        rel = "" if d == root else (d.name if d.parent == root else None)
        rel = rel if rel in _CARPETAS_CACHE else None
        for entry in entradas:
            if entry.name in excl:
                continue
            try:
                attrs, tag, size = _atributos(entry)
            except OSError as e:
                esc.errores.append((Path(entry.path), e))
                continue
            if es_nube(tag) or de_nube(attrs):
                esc.nube = True
            if _es_dir(entry):
                pila.append(Path(entry.path))
                continue
            if rel is not None and _candidato(rel, entry.name):
                mt = _mtime(entry)
                b = basura_de(rel, entry.name, None if mt is None else ahora - mt)
                if b is not None:
                    esc.basura.append(Archivo(Path(entry.path), attrs, tag, size, origen=b[0], motivo=b[1]))
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
             avisar: Optional[Callable[[str], None]] = None,
             progreso: Optional[Callable[[int, int], None]] = None) -> List[Tuple[Archivo, OSError]]:
    """Baja cada pendiente leyéndolo. Devuelve los que no se pudieron leer
    (OneDrive cerrado / pausado / sin red → [Errno 22] en Windows).
    `progreso(i, bytes)` después de cada archivo (i desde 1)."""
    fallos: List[Tuple[Archivo, OSError]] = []
    hechos = 0
    for i, a in enumerate(pendientes, 1):
        try:
            _leer(a.path)
        except OSError as e:
            fallos.append((a, e))
            if avisar:
                avisar(f"x {a.path}: {e}")
        else:
            hechos += a.size
            if avisar:
                avisar(f"  {a.path} ({_kb(a.size)}) ok")
        if progreso:
            progreso(i, hechos)
    return fallos


def borrar_basura(basura: Iterable[Archivo]) -> Tuple[int, int, List[Tuple[Archivo, OSError]]]:
    """Borra los restos de cachés por máquina. Un marcador "sólo en la nube"
    se borra sin bajarlo (y el borrado viaja a SharePoint y a las otras PCs).
    Devuelve (borrados, bytes, fallos); uno que ya no está (lo borró otra PC
    y llegó la sincronización) no cuenta como fallo."""
    n = b = 0
    fallos: List[Tuple[Archivo, OSError]] = []
    for a in basura:
        try:
            os.remove(a.path)
        except FileNotFoundError:
            continue
        except OSError as e:
            fallos.append((a, e))
            continue
        n += 1
        b += a.size
    return n, b, fallos


def por_carpeta(archivos: Iterable[Archivo], root: Path) -> List[Tuple[str, int, int]]:
    """[(carpeta de primer nivel, archivos, bytes)] de mayor a menor peso;
    "(raíz)" para los archivos sueltos de la raíz."""
    acc: dict = {}
    for a in archivos:
        try:
            partes = a.path.relative_to(root).parts
        except ValueError:
            partes = a.path.parts
        clave = partes[0] if len(partes) > 1 else "(raíz)"
        n, b = acc.get(clave, (0, 0))
        acc[clave] = (n + 1, b + a.size)
    return sorted(((k, n, b) for k, (n, b) in acc.items()), key=lambda t: (-t[2], t[0]))


def por_origen(basura: Iterable[Archivo]) -> List[Tuple[str, int, int]]:
    """[(caché, archivos, bytes)] de mayor a menor peso."""
    acc: dict = {}
    for a in basura:
        n, b = acc.get(a.origen, (0, 0))
        acc[a.origen] = (n + 1, b + a.size)
    return sorted(((k, n, b) for k, (n, b) in acc.items()), key=lambda t: (-t[2], t[0]))


def fijar(root: Path, run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run) -> Tuple[bool, str]:
    """"Mantener siempre en este dispositivo" para la carpeta y todo lo de
    adentro: `attrib -U +P` sobre la raíz (lo NUEVO que cree el motor
    adentro hereda el pin) y `attrib -U +P <raíz>\\* /S /D` (todo lo que ya
    existe, .git incluido; `/S` sólo recorre lo que matchea el patrón, por
    eso el `\\*`). El `-U` importa: un archivo que OneDrive ya marcó "sólo en
    la nube" (Liberar espacio / Storage Sense) lleva UNPINNED y ese estado
    propio le gana al pin de la carpeta. attrib viene con Windows; no pide
    admin y sólo cambia el ChangeTime de NTFS, que git no mira."""
    # attrib escribe sus mensajes en el code page OEM (cp850: "No se restablece
    # el archivo oculto - …\.git", uno por ruta) y Popen(text=True) a secas los
    # decodifica con el ANSI (cp1252) en modo estricto: una ruta con ü / É
    # tiraba UnicodeDecodeError (ValueError, no OSError) y el .bat leía exit 1
    # con todo ya bajado. `oem` sólo existe en Windows; `replace` nunca tira.
    texto = dict(capture_output=True, text=True, errors="replace",
                 encoding="oem" if es_windows() else "utf-8")
    try:
        r1 = run(["attrib", "-U", "+P", str(root)], timeout=60, **texto)
        r2 = run(["attrib", "-U", "+P", str(root / "*"), "/S", "/D"], timeout=300, **texto)
    except Exception as e:  # noqa: BLE001 — paso best-effort: nunca aborta el arranque
        return False, str(e)
    if r1.returncode == 0 and r2.returncode == 0:
        return True, ""
    det = ((r1.stderr or "") + (r1.stdout or "") + (r2.stderr or "") + (r2.stdout or "")).strip()
    return False, det or f"attrib devolvió {r1.returncode} / {r2.returncode}"


def _kb(n: int) -> str:
    return f"{n / 1024:,.0f} KB".replace(",", ".") if n >= 1024 else f"{n} B"


def _tam(n: int) -> str:
    """Tamaño legible es-AR: B / KB / MB / GB."""
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB".replace(".", ",")
    if n >= _MB:
        return f"{n / _MB:.1f} MB".replace(".", ",")
    return _kb(n)


def _n(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _say(msg: str) -> None:
    """print que no muere si stdout está redirigido a un cp1252 pobre."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Optional[List[str]] = None) -> int:
    """Lo que corre el .bat. Un Ctrl+C a mitad de la bajada o del borrado
    (15/10: el desk lo cortó con miles de copias bajando) sale sin
    traceback y con 0: cmd igual pregunta "¿Desea terminar el trabajo por
    lotes?" y, si se sigue, la app arranca; lo que faltó lo baja OneDrive
    cuando la app lo lea, la carpeta no se fija y el próximo arranque retoma."""
    try:
        return _main(argv)
    except KeyboardInterrupt:
        _say("[onedrive] cortado con Ctrl+C: sigo sin bajar el resto (OneDrive lo baja cuando la app "
             "lo lea; el próximo arranque retoma)")
        return 0


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Bajar a esta PC los archivos del código que OneDrive "
                                             "dejó 'sólo en la nube' (Archivos a petición)")
    ap.add_argument("--listar", action="store_true", help="sólo informar, sin bajar ni fijar")
    ap.add_argument("--sin-pin", action="store_true", help="bajar sin marcar la carpeta "
                                                           "'Mantener siempre en este dispositivo'")
    ap.add_argument("--carpeta", default="", help="carpeta a revisar (default: la raíz del proyecto)")
    ap.add_argument("--quiet", action="store_true", help="sólo problemas")
    args = ap.parse_args(argv)

    if not es_windows():
        return 0                                     # sin marcadores fuera de Windows

    root = Path(args.carpeta).resolve() if args.carpeta else default_root()
    exponer_marcadores()                             # ver tags y reparse points sin disfraz
    esc = escanear(root)
    say = (lambda m: None) if args.quiet else _say   # noqa: E731

    if not esc.nube and not esc.pendientes:
        return 0                                     # carpeta común (fuera de OneDrive): silencio
    for d, e in esc.errores:
        _say(f"[onedrive] ! no pude listar {d}: {e}")

    basura_pendiente = False                         # quedaron restos sin borrar: no se fija (bajaría todo)
    if esc.basura:
        detalle = " · ".join(f"{o} {_n(n)} ({_tam(b)})" for o, n, b in por_origen(esc.basura))
        if args.listar:
            _say(f"[onedrive] {_n(len(esc.basura))} restos de cachés por PC para borrar "
                 f"({_tam(sum(a.size for a in esc.basura))}): {detalle}")
            for a in esc.basura:
                _say(f"[onedrive]   {a.path} ({_kb(a.size)}, {a.motivo})")
        else:
            if len(esc.basura) > DETALLE_MAX:
                # cada borrado de un marcador pasa por OneDrive: con miles, un rato
                _say(f"[onedrive] borrando {_n(len(esc.basura))} restos de cachés por PC "
                     f"({_tam(sum(a.size for a in esc.basura))}) sin bajarlos…")
            n, b, fallos_b = borrar_basura(esc.basura)
            if n:
                _say(f"[onedrive] borré {_n(n)} restos de cachés por PC ({_tam(b)}, sin bajarlos): {detalle}. "
                     "Eran copias en conflicto que OneDrive dejaba porque cada PC guardaba su estado "
                     "adentro de esta carpeta; ahora ese estado vive en %LOCALAPPDATA%\\bonos. "
                     "Quedan en la papelera de la biblioteca de SharePoint; si OneDrive pregunta por "
                     "los archivos borrados, no hace falta restaurarlos.")
            if fallos_b:
                basura_pendiente = True
                a0, e0 = fallos_b[0]
                _say(f"[onedrive] ! {_n(len(fallos_b))} no se pudieron borrar (p. ej. {a0.path.name}: {e0}); "
                     "no se bajan, la carpeta no se fija todavía (OneDrive los bajaría) y se reintenta "
                     "en el próximo arranque")

    if not esc.pendientes:
        say(f"[onedrive] código completo en esta PC ({esc.total} archivos"
            f"{', carpeta fijada' if esc.root_fijado else ''})")
    else:
        if args.listar:
            _say(f"[onedrive] {len(esc.pendientes)} de {esc.total} archivos están 'sólo en la nube':")
            for a in esc.pendientes:
                _say(f"[onedrive]   {a.path} ({_kb(a.size)})")
            return EXIT_SIN_BAJAR
        total_b = sum(a.size for a in esc.pendientes)
        n_pend = len(esc.pendientes)
        _say(f"[onedrive] {_n(n_pend)} de {_n(esc.total)} archivos del código están 'sólo en la nube' "
             f"(Archivos a petición de OneDrive, {_tam(total_b)}): bajándolos…")
        # progreso = `say` (--quiet lo calla); un fallo se ve siempre. Con
        # muchos pendientes: resumen por carpeta y avance cada ~10 %, no una
        # línea por archivo (una carpeta con miles se volvía ilegible).
        detalle = n_pend <= DETALLE_MAX
        progreso = None
        if not detalle:
            for carpeta, n, b in por_carpeta(esc.pendientes, root)[:8]:
                say(f"[onedrive]   {carpeta}: {_n(n)} archivos, {_tam(b)}")
            paso = max(1, -(-n_pend // 10))              # ~10 líneas de avance

            def progreso(i: int, hechos: int) -> None:
                if i % paso == 0 or i == n_pend:
                    say(f"[onedrive]   … {_n(i)}/{_n(n_pend)} ({_tam(hechos)} de {_tam(total_b)})")

        def avisar(m: str) -> None:
            if m.startswith("x "):
                _say(f"[onedrive] {m}")                  # un fallo, siempre
            elif detalle:
                say(f"[onedrive] {m}")                   # "… ok" por archivo, sólo con pocos

        fallos = hidratar(esc.pendientes, avisar=avisar, progreso=progreso)
        if fallos:
            _say(f"[onedrive] {len(fallos)} archivo(s) siguen sin contenido: OneDrive no los entregó "
                 "(cerrado, pausado, sin sesión o sin red). La app no puede arrancar así.")
            return EXIT_SIN_BAJAR
    if esc.nube and esc.errores:
        # una carpeta de la nube que no se pudo listar: lo de adentro no se
        # chequeó ni se bajó — mismo trato que un archivo sin contenido
        _say(f"[onedrive] {len(esc.errores)} carpeta(s) no se pudieron listar: lo que tienen adentro "
             "no se bajó. La app no puede arrancar así.")
        return EXIT_SIN_BAJAR

    if esc.nube and not esc.root_fijado and not args.sin_pin and not args.listar and not basura_pendiente:
        ok, det = fijar(root)
        if ok and not (_atributos_de(root)[0] & FILE_ATTRIBUTE_PINNED):
            # attrib devolvió 0 pero la raíz no muestra el pin: se vuelve a
            # intentar en el próximo arranque (root_fijado sigue en False).
            _say("[onedrive] ! attrib corrió pero la carpeta todavía no figura fijada; "
                 "se reintenta en el próximo arranque")
        elif ok:
            say("[onedrive] carpeta marcada \"Mantener siempre en este dispositivo\" (attrib -U +P): "
                "lo que llegue con los próximos git pull viene ya bajado")
        else:
            _say(f"[onedrive] ! no pude fijar la carpeta con attrib ({det}); a mano: botón derecho "
                 "sobre la carpeta del código > \"Mantener siempre en este dispositivo\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
