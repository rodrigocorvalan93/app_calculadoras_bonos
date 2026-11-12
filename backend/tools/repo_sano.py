"""Clon sano al arrancar: lo que OneDrive rompió vuelve a ser lo del repo.

El clon del desk vive en la biblioteca de SharePoint que sincroniza OneDrive
(`git pull` desde UNA PC, OneDrive reparte los archivos). Cuando dos PCs
guardan el mismo archivo a la vez, OneDrive deja UNA versión en su lugar y la
otra al lado con el nombre de la máquina (`especies-DAM-NB-RC.py`); una
sincronización cortada deja un archivo a medias. El 12/11 dos PCs arrancaron
con un `especies.py` al que le faltaba un bloque de ficha (`NameError:
S13N6`) y la app quedó sin universo de bonos: 500 en todo.

Corre en el .bat DESPUÉS del pre-flight de OneDrive (los archivos ya están
bajados) y ANTES de pip / uvicorn, con la biblioteca estándar sola:

  1. `git status` del clon: los archivos VERSIONADOS que difieren del repo
     (HEAD) se restauran con `git checkout` — menos los PROTEGIDOS:
     `especies.py` (lo edita el desk a mano: fichas nuevas), lo que la app
     reescribe a propósito (`bcra_data_backup.json`, `bymaprices.xlsx`) y
     los LANZADORES (`.bat` / `.command`: cmd.exe relee el .bat que está
     corriendo por offset de bytes — reescribirlo a mitad de camino lo
     deja ejecutando basura; se avisa y se arregla al cerrar). Lo que no
     está versionado (secrets.txt, certs/, data/) no se toca. Lo que está
     en el índice pero no en HEAD (`git add` / `git mv` sin commit) tampoco.
  2. copias en conflicto de OneDrive de un archivo versionado
     (`<nombre>-<PC>.<ext>`, `<nombre> (conflicted copy …).<ext>`): si son
     byte a byte iguales a lo del repo se borran (no hay nada que perder);
     si difieren, o no se pudieron comparar, se avisa y se dejan (pueden
     tener fichas cargadas a mano).
  3. `especies.py` se chequea ANTES de importarlo (AST, sin ejecutar nada):
     sintaxis, y que cada `rentafija.Bono(X)` y cada nombre de la lista
     final tengan su diccionario (definido arriba, también adentro de un
     if / for / try, por tupla, o traído por `from utils import *`). Roto o
     FALTANTE → sale con `EXIT_ESPECIES_ROTO` (4) y el .bat ofrece
     `--restaurar-especies`: el archivo roto se guarda en la carpeta local
     de la máquina (`%LOCALAPPDATA%\\bonos\\conflictos`) y se repone el del
     repo; después se vuelve a chequear (el del repo también puede estar
     roto: ahí hay que corregirlo en git). Nunca se restaura solo: puede
     tener trabajo del desk.

`REPO_AUTOPULL=1` (secrets.txt) suma un `git fetch` + fast-forward de la
rama actual cuando el clon quedó limpio (lo que la app reescribe y el pull
también trae se repone antes: la app lo vuelve a escribir); apagado por
default porque el `.git` también viaja por OneDrive y dos PCs trayendo a la
vez se pisan. `REPO_SANO=0` apaga todo. Sin git en el PATH, sin `.git` o
fuera de Windows / Mac: silencio y exit 0 — este paso nunca frena la app por
un problema propio (sólo `--restaurar-especies` devuelve 1 si no pudo).

    python -m backend.tools.repo_sano               # lo que corre el .bat
    python -m backend.tools.repo_sano --listar      # sólo informar
    python -m backend.tools.repo_sano --restaurar-especies
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set, Tuple

EXIT_ESPECIES_ROTO = 4            # el .bat pregunta si restaurar
PROTEGIDOS = frozenset({"especies.py"})                       # lo edita el desk a mano
ESCRIBE_LA_APP = frozenset({"bcra_data_backup.json", "bymaprices.xlsx"})   # reescritos a propósito
_SUFIJOS_LANZADOR = (".bat", ".cmd", ".command")              # el proceso que corre este paso
_RE_COPIA = re.compile(r"^(?P<stem>.+?)(?:-[A-Za-z0-9_.-]+| \(conflicted copy[^)]*\)| \([0-9]+\))$")
_PLATFORM = sys.platform


def _say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def dir_conflictos() -> Path:
    """Carpeta LOCAL de la máquina para lo que se aparta (nunca adentro del
    clon sincronizado): la misma de `estado_local` / el journal."""
    base = os.getenv("BONOS_LOCAL_DIR")
    if not base:
        if _PLATFORM.startswith("win"):
            base = os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "bonos")
        else:
            base = os.path.join(os.path.expanduser("~"), ".local", "share", "bonos")
    return Path(base) / "conflictos"


# ── git ──────────────────────────────────────────────────────────────────────
def _git(root: Path, *args: str, timeout: float = 60.0,
         run: Callable[..., "subprocess.CompletedProcess[bytes]"] = subprocess.run) -> Tuple[int, bytes, str]:
    """(returncode, stdout, stderr) de `git -C root …`; (-1, b"", motivo) si
    git no está o no contesta. Bytes: las rutas pueden traer cualquier cosa."""
    try:
        r = run(["git", "-C", str(root), *args], capture_output=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — sin git / timeout
        return -1, b"", f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout or b"", (r.stderr or b"").decode("utf-8", "replace").strip()


def git_disponible(root: Path) -> bool:
    if not (root / ".git").exists():
        return False
    if _PLATFORM == "darwin":
        # sin Command Line Tools /usr/bin/git es un stub que abre un diálogo
        rc, _o, _e = _git(root, "--version", timeout=5.0) if _xcode_ok() else (-1, b"", "")
        return rc == 0
    rc, _o, _e = _git(root, "--version", timeout=10.0)
    return rc == 0


def _xcode_ok() -> bool:
    try:
        return subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=2.0).returncode == 0
    except Exception:  # noqa: BLE001
        return False


@dataclass
class Estado:
    rama: str = ""
    modificados: List[str] = field(default_factory=list)      # versionados que difieren de HEAD
    borrados: List[str] = field(default_factory=list)         # versionados que faltan
    sin_versionar: List[str] = field(default_factory=list)    # `??`
    error: str = ""


def estado(root: Path) -> Estado:
    """`git status --porcelain -z`: qué difiere del repo. `-z` por las rutas
    con espacios ("run_backend (CORRER APP).bat"). Lo que está en el índice
    pero no en HEAD (`A` / `R` / `C`: un `git add` o `git mv` sin commit) se
    ignora: `git checkout HEAD --` no lo conoce y abortaría el lote entero."""
    est = Estado()
    rc, out, err = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if rc != 0:
        est.error = err or f"git status devolvió {rc}"
        return est
    rc, rama, _e = _git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=10.0)
    est.rama = rama.decode("utf-8", "replace").strip() if rc == 0 else ""
    partes = out.split(b"\0")
    i = 0
    while i < len(partes):
        p = partes[i]
        i += 1
        if len(p) < 4:
            continue
        xy, ruta = p[:2].decode("ascii", "replace"), p[3:].decode("utf-8", "replace")
        if xy[0] in "RC":                     # rename / copy: la ruta vieja viene en el campo siguiente
            i += 1
        if xy == "??":
            est.sin_versionar.append(ruta)
        elif xy[0] in "ARC":
            continue                          # en el índice, no en HEAD
        elif "D" in xy:
            est.borrados.append(ruta)
        else:
            est.modificados.append(ruta)
    return est


def _nombre(ruta: str) -> Tuple[bool, str]:
    """(está en la raíz, nombre de archivo)."""
    p = ruta.replace("\\", "/")
    return "/" not in p, p.rsplit("/", 1)[-1]


def es_lanzador(ruta: str) -> bool:
    """Un .bat / .command de la raíz: el que puede estar corriendo este
    paso. cmd.exe relee el archivo por offset de bytes en cada línea."""
    raiz, nombre = _nombre(ruta)
    return raiz and nombre.lower().endswith(_SUFIJOS_LANZADOR)


def restaurables(est: Estado) -> List[str]:
    """Versionados a restaurar: todo lo modificado / borrado menos los
    protegidos, lo que la app reescribe y los lanzadores (sólo en la raíz)."""
    out = []
    for ruta in est.modificados + est.borrados:
        raiz, nombre = _nombre(ruta)
        if raiz and (nombre in PROTEGIDOS or nombre in ESCRIBE_LA_APP or es_lanzador(ruta)):
            continue
        out.append(ruta)
    return out


def restaurar(root: Path, rutas: Iterable[str]) -> Tuple[bool, str]:
    """`git checkout HEAD -- rutas` (también repone los borrados y descarta lo
    staged). Con `restore` haría falta git ≥ 2.23; checkout anda en todos."""
    rutas = list(rutas)
    if not rutas:
        return True, ""
    rc, _o, err = _git(root, "checkout", "HEAD", "--", *rutas, timeout=120.0)
    return rc == 0, err


def versionados(root: Path) -> set:
    rc, out, _e = _git(root, "ls-files", "-z")
    if rc != 0:
        return set()
    return {p.decode("utf-8", "replace") for p in out.split(b"\0") if p}


def copias_en_conflicto(est: Estado, tracked: set) -> List[Tuple[str, str]]:
    """[(copia, original versionado)] entre los sin versionar: `x-PC.py` /
    `x (conflicted copy …).py` / `x (1).py` cuyo `x.py` está en el repo."""
    out = []
    for ruta in est.sin_versionar:
        p = ruta.replace("\\", "/")
        carpeta, nombre = (p.rsplit("/", 1) + [""])[:2] if "/" in p else ("", p)
        stem, punto, ext = nombre.rpartition(".")
        if not punto:
            continue
        m = _RE_COPIA.match(stem)
        if not m:
            continue
        original = (carpeta + "/" if carpeta else "") + m.group("stem") + "." + ext
        if original in tracked:
            out.append((ruta, original))
    return out


def igual_al_repo(root: Path, copia: str, original: str) -> Optional[bool]:
    """¿La copia es byte a byte lo que el repo tiene en `original`? None si
    no se pudo saber (no se borra)."""
    rc1, h1, _e = _git(root, "hash-object", "--", str(root / copia), timeout=60.0)
    rc2, h2, _e = _git(root, "rev-parse", f"HEAD:{original}", timeout=10.0)
    if rc1 != 0 or rc2 != 0 or not h1.strip() or not h2.strip():
        return None
    return h1.strip() == h2.strip()


# ── especies.py ──────────────────────────────────────────────────────────────
def _destinos(t: ast.AST) -> List[str]:
    """Nombres que liga un target: `X`, `(A, B)`, `[A, *B]`."""
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [n for e in t.elts for n in _destinos(e)]
    if isinstance(t, ast.Starred):
        return _destinos(t.value)
    return []


def _publicos_de(path_mod: Path) -> Optional[Set[str]]:
    """Nombres públicos que `from M import *` trae de un módulo hermano
    (ligados en cualquier parte del archivo); None si no se puede leer."""
    try:
        tree = ast.parse(path_mod.read_bytes())
    except Exception:  # noqa: BLE001 — no está / no parsea
        return None
    out: Set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                out.update(_destinos(t))
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            out.update(_destinos(n.target))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update((a.asname or a.name).split(".")[0] for a in n.names if a.name != "*")
    return {n for n in out if not n.startswith("_")}


def chequear_especies(path: Path) -> List[str]:
    """Problemas de `especies.py` que harían fallar el import, sin ejecutarlo:
    sintaxis, `rentafija.Bono(X)` con X sin diccionario, nombres de la lista
    final sin definir. [] = sano. Un NameError de éstos deja la app sin
    universo de bonos (12/11). Se lee en BYTES (mismo BOM / coding cookie
    que el import; un archivo cortado a mitad de un carácter es "sintaxis",
    no una excepción). Los nombres se juntan como lo haría el import: a
    nivel módulo, también adentro de if / for / while / try / with, por
    tupla, walrus, y los públicos de un `from M import *` hermano; si ese
    módulo no se puede leer, no se acusa a nadie (no se sabe qué trae)."""
    try:
        src = path.read_bytes()
    except OSError as e:
        return [f"no se pudo leer: {e}"]
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError) as e:        # ValueError: bytes nulos / decode
        return [f"sintaxis: línea {getattr(e, 'lineno', None) or '?'}: {getattr(e, 'msg', e)}"]
    definidos: Set[str] = set()
    problemas: List[str] = []
    desconocidos = False                          # un `import *` que no se pudo resolver

    def valor(v: ast.AST, lineno: int) -> None:
        if desconocidos:
            return
        if isinstance(v, ast.Call) and (getattr(v.func, "attr", "") == "Bono" or getattr(v.func, "id", "") == "Bono"):
            for arg in v.args:
                if isinstance(arg, ast.Name) and arg.id not in definidos:
                    problemas.append(f"línea {lineno}: rentafija.Bono({arg.id}) sin la ficha {arg.id} definida antes")
        elif isinstance(v, (ast.List, ast.Tuple)):
            for e in v.elts:
                if isinstance(e, ast.Name) and e.id not in definidos:
                    problemas.append(f"línea {e.lineno}: {e.id} en la lista no está definido")

    def visitar(stmts: Iterable[ast.stmt]) -> None:
        nonlocal desconocidos
        for node in stmts:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.name == "*":
                        mod = getattr(node, "module", None)
                        pub = _publicos_de(path.parent / (mod.replace(".", "/") + ".py")) if mod else None
                        if pub is None:
                            desconocidos = True
                        else:
                            definidos.update(pub)
                    else:
                        definidos.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definidos.add(node.name)
            elif isinstance(node, ast.Assign):
                valor(node.value, node.lineno)
                for t in node.targets:
                    definidos.update(_destinos(t))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if node.value is not None:
                    valor(node.value, node.lineno)
                definidos.update(_destinos(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                definidos.update(_destinos(node.target))
                visitar(node.body)
                visitar(node.orelse)
            elif isinstance(node, (ast.If, ast.While)):
                visitar(node.body)
                visitar(node.orelse)
            elif isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                visitar(node.body)
                for h in node.handlers:
                    visitar(h.body)
                visitar(node.orelse)
                visitar(node.finalbody)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for it in node.items:
                    if it.optional_vars is not None:
                        definidos.update(_destinos(it.optional_vars))
                visitar(node.body)
            for sub in ast.walk(node):            # walrus en cualquier lado del statement
                if isinstance(sub, ast.NamedExpr):
                    definidos.update(_destinos(sub.target))

    visitar(tree.body)
    return problemas


def apartar(path: Path, destino_dir: Path, ahora: Optional[dt.datetime] = None) -> Path:
    """Copia `path` a la carpeta local con fecha en el nombre y devuelve la
    ruta (lo roto no se pierde: el desk puede rescatar fichas a mano)."""
    ahora = ahora or dt.datetime.now()
    destino_dir.mkdir(parents=True, exist_ok=True)
    dest = destino_dir / f"{path.stem}-roto-{ahora:%Y%m%d-%H%M%S}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


# ── main ─────────────────────────────────────────────────────────────────────
def _cargar_secrets(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        import OMSsecrets                                   # noqa: WPS433 — stdlib, raíz del repo
        OMSsecrets.load()
    except Exception:  # noqa: BLE001 — sin secrets.txt: defaults
        pass


def main(argv: Optional[List[str]] = None) -> int:
    restaurando = "--restaurar-especies" in (argv if argv is not None else sys.argv[1:])
    try:
        return _main(argv)
    except KeyboardInterrupt:
        return 0
    except Exception as e:  # noqa: BLE001 — nunca frena la app por un problema propio…
        if restaurando:                           # …salvo que el .bat esté esperando el resultado
            _say(f"[repo] ! no pude restaurar especies.py ({type(e).__name__}: {e}); queda como está")
            return 1
        _say(f"[repo] ! el chequeo del clon falló ({type(e).__name__}: {e}); sigo igual")
        return 0


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deja el clon como el repo: restaura lo versionado que "
                                             "OneDrive cambió (salvo especies.py) y chequea especies.py")
    ap.add_argument("--listar", action="store_true", help="sólo informar, sin tocar nada")
    ap.add_argument("--carpeta", default="", help="raíz del clon (default: la del proyecto)")
    ap.add_argument("--restaurar-especies", action="store_true",
                    help="reponer especies.py desde el repo (el actual se guarda en la carpeta local)")
    ap.add_argument("--quiet", action="store_true", help="sólo problemas")
    args = ap.parse_args(argv)
    root = Path(args.carpeta).resolve() if args.carpeta else default_root()
    say = (lambda m: None) if args.quiet else _say   # noqa: E731
    _cargar_secrets(root)
    if (os.getenv("REPO_SANO") or "1").strip() == "0":
        return 0
    if not git_disponible(root):
        if args.restaurar_especies:
            _say("[repo] ! sin git no puedo restaurar especies.py")
            return 1
        return 0                                          # sin git / sin .git: nada que comparar
    est = estado(root)
    if est.error:
        _say(f"[repo] ! git status falló ({est.error}); "
             + ("no puedo restaurar especies.py" if args.restaurar_especies else "sigo igual"))
        return 1 if args.restaurar_especies else 0

    especies = root / "especies.py"
    if args.restaurar_especies:
        return _restaurar_especies(root, especies, est, say)

    # 1) versionados que difieren del repo (menos protegidos, lo que la app escribe y los lanzadores)
    rutas = restaurables(est)
    if rutas:
        if args.listar:
            _say(f"[repo] {len(rutas)} archivo(s) versionados difieren del repo (rama {est.rama}):")
            for r in rutas:
                _say(f"[repo]   {r}{' (falta)' if r in est.borrados else ''}")
        else:
            ok, err = restaurar(root, rutas)
            if ok:
                _say(f"[repo] {len(rutas)} archivo(s) del código volvieron a ser los del repo (rama {est.rama}): "
                     + ", ".join(rutas[:8]) + (" …" if len(rutas) > 8 else "")
                     + " — eran versiones que OneDrive dejó distintas")
            else:
                _say(f"[repo] ! no pude restaurar {len(rutas)} archivo(s) ({err}); a mano: git checkout -- <archivo>")
    protegidos_tocados = [r for r in est.modificados if r in PROTEGIDOS]
    if protegidos_tocados:
        say(f"[repo] {', '.join(protegidos_tocados)} tiene cambios locales: se respeta (lo edita el desk)")
    lanzadores = [r for r in est.modificados + est.borrados if es_lanzador(r)]
    if lanzadores:
        _say(f"[repo] ! {', '.join(lanzadores)} difiere del repo: no se toca mientras corre (cmd seguiría "
             "leyendo el archivo nuevo desde el mismo byte). Al cerrar esta ventana, a mano: "
             "git checkout -- \"<archivo>\"")

    # 2) copias en conflicto de OneDrive de archivos versionados
    copias = copias_en_conflicto(est, versionados(root))
    for copia, original in copias:
        iguales = igual_al_repo(root, copia, original)
        if iguales is None:
            _say(f"[repo] ! {copia}: copia en conflicto de OneDrive de {original}; no pude compararla con el "
                 "repo (git no contestó o el archivo no se pudo leer) — se deja, revisarla a mano")
        elif iguales and not args.listar:
            try:
                (root / copia).unlink()
                say(f"[repo] borré {copia}: copia en conflicto de OneDrive idéntica a {original} del repo")
            except OSError as e:
                _say(f"[repo] ! no pude borrar {copia} ({e})")
        elif iguales:
            _say(f"[repo] {copia}: copia en conflicto de OneDrive idéntica a {original} (se borra al arrancar)")
        else:
            _say(f"[repo] ! {copia}: copia en conflicto de OneDrive de {original} con contenido DISTINTO — "
                 "revisarla a mano (puede tener fichas cargadas en otra PC) y borrarla")

    # 3) especies.py importable
    if "especies.py" in est.borrados:
        _say("[repo] x especies.py FALTA en esta PC (OneDrive lo borró o todavía no lo trajo); la app "
             "arrancaría sin universo de bonos.")
        _say("[repo]   difiere del repo: reponerlo con python -m backend.tools.repo_sano --restaurar-especies")
        return EXIT_ESPECIES_ROTO
    if especies.exists():
        problemas = chequear_especies(especies)
        if problemas:
            _say(f"[repo] x especies.py de esta PC está ROTO ({len(problemas)} problema(s)); la app arrancaría "
                 "sin universo de bonos:")
            for p in problemas[:10]:
                _say(f"[repo]   {p}")
            if "especies.py" in est.modificados:
                _say("[repo]   difiere del repo: es una versión que OneDrive dejó a medias o una edición a mano. "
                     "Restaurar desde el repo: python -m backend.tools.repo_sano --restaurar-especies "
                     "(el actual se guarda en la carpeta local)")
            else:
                _say("[repo]   es el del repo: hay que corregirlo en git (no se puede restaurar)")
            return EXIT_ESPECIES_ROTO
        say("[repo] especies.py sano")

    # 4) opcional: traer la rama (sólo con el clon limpio)
    if (os.getenv("REPO_AUTOPULL") or "0").strip() == "1" and not args.listar:
        _autopull(root, est, say)
    return 0


def _restaurar_especies(root: Path, especies: Path, est: Estado, say: Callable[[str], None]) -> int:
    """`--restaurar-especies`: guarda el actual en la carpeta local, repone
    el del repo y lo vuelve a chequear. 0 = quedó sano; 1 = no pude;
    EXIT_ESPECIES_ROTO = el del repo también está roto (corregirlo en git)."""
    if "especies.py" in est.modificados + est.borrados:
        if especies.exists():
            try:
                guardado = apartar(especies, dir_conflictos())
            except OSError as e:
                _say(f"[repo] ! no pude guardar la copia del especies.py actual en {dir_conflictos()} ({e}); "
                     "no lo toco")
                return 1
            _say(f"[repo] el especies.py actual quedó guardado en {guardado}")
        ok, err = restaurar(root, ["especies.py"])
        if not ok:
            _say(f"[repo] ! no pude restaurar especies.py ({err})")
            return 1
        _say("[repo] especies.py restaurado desde el repo")
    else:
        say("[repo] especies.py ya es el del repo")
    problemas = chequear_especies(especies) if especies.exists() else ["no existe"]
    if problemas:
        _say(f"[repo] x el especies.py del repo también está ROTO ({problemas[0]}): hay que corregirlo en git; "
             "la app arrancaría sin universo de bonos")
        return EXIT_ESPECIES_ROTO
    return 0


def _autopull(root: Path, est: Estado, say: Callable[[str], None]) -> None:
    if [r for r in est.modificados if r in PROTEGIDOS]:
        say("[repo] autopull: especies.py con cambios locales, no traigo la rama")
        return
    if not est.rama or est.rama == "HEAD":
        return
    rc, _o, err = _git(root, "fetch", "origin", est.rama, timeout=120.0)
    if rc != 0:
        _say(f"[repo] ! autopull: fetch falló ({err})")
        return
    # lo que la app reescribe (bcra_data_backup.json…) y el pull también trae
    # bloquearía el merge ("would be overwritten"): se repone del repo antes —
    # la app lo vuelve a escribir en el próximo indices.main()
    rc, out, _e = _git(root, "diff", "--name-only", "-z", "HEAD", f"origin/{est.rama}", timeout=60.0)
    entrantes = {p.decode("utf-8", "replace") for p in out.split(b"\0") if p} if rc == 0 else set()
    sucios = [r for r in est.modificados if _nombre(r)[0] and _nombre(r)[1] in ESCRIBE_LA_APP and r in entrantes]
    if sucios:
        ok, err = restaurar(root, sucios)
        if not ok:
            _say(f"[repo] ! autopull: no pude reponer {', '.join(sucios)} ({err}); no traigo la rama")
            return
        say(f"[repo] autopull: {', '.join(sucios)} repuesto del repo (la app lo reescribe)")
    rc, _o, err = _git(root, "merge", "--ff-only", f"origin/{est.rama}", timeout=120.0)
    if rc == 0:
        say(f"[repo] rama {est.rama} al día con origin")
    elif "overwritten" in err:
        archivos = [ln.strip() for ln in err.splitlines() if ln.startswith("\t")]
        _say(f"[repo] ! autopull: cambios locales en {', '.join(archivos) or 'archivos'} frenan la rama; a mano: "
             f"git checkout -- <archivo> && git merge --ff-only origin/{est.rama}")
    else:
        _say(f"[repo] ! autopull: la rama {est.rama} no avanza en fast-forward ({err.splitlines()[-1] if err else rc}); "
             "a mano: git fetch origin && git reset --keep origin/" + est.rama)


if __name__ == "__main__":
    raise SystemExit(main())
