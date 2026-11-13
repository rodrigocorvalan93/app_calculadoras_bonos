"""`backend.tools.onedrive`: el pre-flight del .bat que baja a la PC los
archivos del código que OneDrive dejó "sólo en la nube" (Archivos a petición)
y corta con un mensaje claro cuando OneDrive no los entrega — Pablo, 13/10:
`OSError: [Errno 22] Invalid argument` en `importlib … get_data` al importar
`bna_fx.py`, un archivo nuevo del repo que llegó por OneDrive como marcador.

Los atributos de Windows no existen en Linux / macOS: se parchea
`_atributos` (lo que el listado devuelve por entrada) y `_leer` (la bajada)
para ejercitar la rama Windows en cualquier runner."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from backend.tools import onedrive

ROOT = Path(__file__).resolve().parents[1]
NUBE_TAG = 0x9000601A                      # un tag de la familia IO_REPARSE_TAG_CLOUD*
RECALL = onedrive.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | 0x20   # + ARCHIVE


_ATTRIB_REAL = onedrive._attrib
_VERSIONADOS_REAL = onedrive.archivos_versionados


@pytest.fixture(autouse=True)
def _sin_git_ni_attrib(monkeypatch):
    """Ningún test corre `git ls-files` ni `attrib` de verdad: sin git el
    pre-flight cae a la heurística (el que quiera git patchea
    `archivos_versionados`) y cada attrib queda grabado en `onedrive._CMDS`."""
    monkeypatch.setattr(onedrive, "archivos_versionados", lambda root: None)
    cmds: list[list[str]] = []
    monkeypatch.setattr(onedrive, "_CMDS", cmds, raising=False)

    def attrib(flags, patron, recursivo, run=None):
        cmds.append([*flags, str(patron)] + (["/S", "/D"] if recursivo else []))
        return True, ""

    monkeypatch.setattr(onedrive, "_attrib", attrib)


def _arbol(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    (root / "backend" / "services").mkdir(parents=True)
    (root / "backend" / "templates").mkdir()
    (root / ".git" / "objects").mkdir(parents=True)
    (root / "__pycache__").mkdir()
    (root / "backend" / "services" / "bna_fx.py").write_bytes(b"x" * 3000)
    (root / "backend" / "services" / "fx.py").write_bytes(b"y" * 10)
    (root / "backend" / "templates" / "base.html").write_bytes(b"<html>")
    (root / "rentafija.py").write_bytes(b"z")
    (root / ".git" / "objects" / "aa").write_bytes(b"blob")
    (root / "__pycache__" / "m.pyc").write_bytes(b"pyc")
    return root


def _atributos_fake(sin_contenido: set[str], nube: bool = True):
    """`_atributos(entry)`: los nombres de `sin_contenido` quedan como
    marcadores RECALL_ON_DATA_ACCESS; todo lleva tag de nube si `nube`."""
    def f(entry):
        attrs = RECALL if entry.name in sin_contenido else 0x20
        if entry.is_dir(follow_symlinks=False):
            attrs = onedrive.FILE_ATTRIBUTE_DIRECTORY
        return attrs, (NUBE_TAG if nube else 0), entry.stat(follow_symlinks=False).st_size
    return f


def test_bits_de_marcador_y_de_nube() -> None:
    assert onedrive.sin_contenido(onedrive.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    assert onedrive.sin_contenido(onedrive.FILE_ATTRIBUTE_OFFLINE | 0x20)
    assert onedrive.sin_contenido(onedrive.FILE_ATTRIBUTE_RECALL_ON_OPEN)
    assert not onedrive.sin_contenido(0x20)                                      # ARCHIVE a secas
    assert not onedrive.sin_contenido(onedrive.FILE_ATTRIBUTE_PINNED | 0x20)     # bajado y fijado
    for tag in (0x9000001A, 0x9000101A, 0x9000601A, 0x9000F01A):
        assert onedrive.es_nube(tag), hex(tag)
    assert not onedrive.es_nube(0)
    assert not onedrive.es_nube(0xA000000C)                                      # symlink
    assert not onedrive.es_nube(0xA0000003)                                      # junction


def test_escanear_junta_los_pendientes_y_salta_git_y_pycache(tmp_path, monkeypatch) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py", "base.html", "aa", "m.pyc"}))
    esc = onedrive.escanear(root)
    assert esc.nube
    assert esc.total == 4                                                        # sin .git ni __pycache__
    assert [a.path.name for a in esc.pendientes] == ["bna_fx.py", "base.html"]   # por ruta: services < templates
    assert esc.pendientes[0].size == 3000 and esc.pendientes[0].sin_contenido and esc.pendientes[0].nube
    assert not esc.errores and not esc.root_fijado


def test_escanear_carpeta_comun_no_es_nube(tmp_path, monkeypatch) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set(), nube=False))
    esc = onedrive.escanear(root, raices=[])
    assert not esc.nube and not esc.pendientes and esc.total == 4


def test_nube_sin_tag_por_atributos_de_pin_o_por_raiz_de_onedrive(tmp_path, monkeypatch) -> None:
    """Windows le puede esconder el reparse point / tag a un proceso común
    (marcadores "disfrazados"): la carpeta sigue siendo de nube si alguna
    entrada lleva PINNED / UNPINNED / RECALL (los pone sólo el motor) o si
    cuelga de una raíz de sincronización (SharePoint no está en %OneDrive%)."""
    root = _arbol(tmp_path)
    base = _atributos_fake(set(), nube=False)

    def con_pin(entry):
        attrs, tag, size = base(entry)
        if entry.name == "fx.py":
            attrs |= onedrive.FILE_ATTRIBUTE_UNPINNED                    # "liberar espacio" de antes
        return attrs, tag, size

    monkeypatch.setattr(onedrive, "_atributos", con_pin)
    assert onedrive.escanear(root, raices=[]).nube
    monkeypatch.setattr(onedrive, "_atributos", base)
    assert not onedrive.escanear(root, raices=[]).nube
    assert onedrive.escanear(root, raices=[str(tmp_path)]).nube          # abajo de la raíz
    assert onedrive.escanear(root, raices=[str(root)]).nube              # es la raíz
    assert not onedrive.escanear(root, raices=[str(tmp_path / "otra")]).nube
    # bajo_raiz: sin distinguir mayúsculas ni barra final; 'app2' no es 'app'
    assert onedrive.bajo_raiz(Path("C:\\Users\\p\\DELTA SA\\Inversiones - Documentos\\Codes\\app"),
                              ["c:\\users\\P\\delta sa\\Inversiones - Documentos\\"])
    assert not onedrive.bajo_raiz(Path("C:\\Users\\p\\OneDrive2\\app"), ["C:\\Users\\p\\OneDrive"])
    assert not onedrive.bajo_raiz(root, [])
    # fuera de Windows no hay registro ni ctypes: listas vacías / False, sin tirar
    monkeypatch.setattr(onedrive, "_PLATFORM", "linux")
    monkeypatch.delenv("OneDrive", raising=False)
    assert onedrive.raices_onedrive() == [] and onedrive.exponer_marcadores() is False
    monkeypatch.setenv("OneDrive", "C:\\Users\\p\\OneDrive")
    assert onedrive.raices_onedrive() == ["C:\\Users\\p\\OneDrive"]


def test_escanear_sigue_si_un_listado_falla(tmp_path, monkeypatch) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    real = os.scandir

    def scandir(d):
        if str(d).endswith("templates"):
            raise PermissionError(13, "denegado")
        return real(d)

    monkeypatch.setattr(onedrive.os, "scandir", scandir)
    esc = onedrive.escanear(root)
    assert esc.total == 3 and len(esc.errores) == 1 and esc.errores[0][0].name == "templates"


def test_hidratar_lee_y_reporta_lo_que_onedrive_no_entrega(tmp_path, monkeypatch) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py", "fx.py"}))
    esc = onedrive.escanear(root)
    leidos: list[str] = []
    real = onedrive._leer

    def leer(p: Path) -> None:
        leidos.append(p.name)
        if p.name == "bna_fx.py":
            raise OSError(22, "Invalid argument")                               # EINVAL del CRT
        real(p)

    monkeypatch.setattr(onedrive, "_leer", leer)
    avisos: list[str] = []
    fallos = onedrive.hidratar(esc.pendientes, avisar=avisos.append)
    assert leidos == ["bna_fx.py", "fx.py"]                                      # no corta en el primero
    assert [a.path.name for a, _ in fallos] == ["bna_fx.py"]
    assert fallos[0][1].errno == 22
    assert avisos[0].startswith("x ") and "Invalid argument" in avisos[0] and avisos[1].endswith("ok")


def test_fijar_usa_attrib_sobre_la_raiz_y_recursivo(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(onedrive, "_attrib", _ATTRIB_REAL)          # acá se prueba el attrib de verdad
    llamadas: list[tuple] = []

    kws: list[dict] = []

    def run(argv, **kw):
        llamadas.append((tuple(argv), kw.get("cwd")))
        kws.append(kw)
        return subprocess.CompletedProcess(argv, 0, "", "")

    ok, det = onedrive.fijar(tmp_path, run=run)
    assert ok and det == ""
    # attrib habla en OEM (cp850) y una ruta con ü tiraba UnicodeDecodeError con
    # el cp1252 estricto de Popen: 'replace' nunca tira; 'oem' sólo en Windows.
    # La suite corre en los tres runners: se fija la plataforma en cada rama
    # (en el runner de Windows la primera llamada ya salía con 'oem').
    assert all(k["errors"] == "replace" for k in kws)
    plat_real = onedrive._PLATFORM
    try:
        onedrive._PLATFORM = "linux"
        kws.clear(); onedrive.fijar(tmp_path, run=run)
        assert all(k["encoding"] == "utf-8" for k in kws)
        onedrive._PLATFORM = "win32"
        kws.clear(); onedrive.fijar(tmp_path, run=run)
        assert all(k["encoding"] == "oem" for k in kws)
    finally:
        onedrive._PLATFORM = plat_real

    def run_revienta(argv, **kw):
        raise UnicodeDecodeError("charmap", b"\x81", 0, 1, "no")        # ValueError, no OSError

    ok, det = onedrive.fijar(tmp_path, run=run_revienta)
    assert not ok and "charmap" in det
    # -U: un archivo que OneDrive ya marcó "sólo en la nube" lleva UNPINNED y
    # ese estado propio le gana al pin de la carpeta; \* porque /S sólo
    # recorre lo que matchea el patrón. El recursivo va PRIMERO: si lo corta
    # un timeout / Ctrl+C la raíz queda sin pin y el próximo arranque reintenta.
    assert llamadas[0] == (("attrib", "-U", "+P", str(tmp_path / "*"), "/S", "/D"), None)
    assert llamadas[1] == (("attrib", "-U", "+P", str(tmp_path)), None)

    def run_timeout(argv, **kw):
        if "/S" in argv:
            raise subprocess.TimeoutExpired(argv, 300)
        pytest.fail("con el recursivo cortado no se fija la raíz")

    ok, det = onedrive.fijar(tmp_path, run=run_timeout)
    assert not ok and "300" in det

    def run_mal(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", "Acceso denegado")

    ok, det = onedrive.fijar(tmp_path, run=run_mal)
    assert not ok and "Acceso denegado" in det

    def run_sin_attrib(argv, **kw):
        raise FileNotFoundError(2, "attrib")

    ok, det = onedrive.fijar(tmp_path, run=run_sin_attrib)
    assert not ok and "attrib" in det


_VERSIONADOS = {"backend/services/bna_fx.py", "backend/services/fx.py", "backend/templates/base.html",
                "rentafija.py"}


def _con_vecinos(tmp_path: Path) -> Path:
    """El clon del desk: al lado del código, un proyecto vecino con datasets y
    exportaciones sueltas en la raíz (470 MB de 562 archivos en la PC del
    desk, con el repo pesando 9,5 MB)."""
    root = _arbol(tmp_path)
    (root / "proyecto_cauciones_ml").mkdir()
    (root / "proyecto_cauciones_ml" / "dataset.parquet").write_bytes(b"d" * 4000)
    (root / "proyecto_cauciones_ml" / "extractor.py").write_bytes(b"e")
    (root / "export viejo.xlsx").write_bytes(b"x" * 2000)
    return root


def test_main_baja_y_fija_solo_lo_que_git_versiona(tmp_path, monkeypatch, capsys) -> None:
    """11/11: se baja sólo lo que git versiona y el pin «Mantener siempre en
    este dispositivo» va por carpetas acotadas (backend/, tests/, .git/…) y
    por los archivos de la raíz que git versiona — nunca la raíz entera (eso
    hacía bajar 470 MB de vecinos en cada PC). Lo vecino se informa y queda
    en la nube."""
    root = _con_vecinos(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos",
                        _atributos_fake({"bna_fx.py", "dataset.parquet", "extractor.py", "export viejo.xlsx"}))
    monkeypatch.setattr(onedrive, "archivos_versionados",
                        lambda r: {os.path.normcase(str(Path(v))) for v in _VERSIONADOS})
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    monkeypatch.setattr(onedrive, "fijar", lambda r, run=None: pytest.fail("la raíz entera no se fija"))
    fij: list = []
    monkeypatch.setattr(onedrive, "fijar_parcial",
                        lambda r, c, pt, run=None: (fij.append((r, list(c), list(pt))), (True, ""))[1])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert leidos == ["bna_fx.py"]                                     # ni el dataset ni el xlsx suelto
    assert "1 de 7 archivos del código" in out and "bna_fx.py" in out
    assert "3 archivos de la carpeta no son del código" in out and "git no los versiona" in out
    assert "proyecto_cauciones_ml 2" in out and "quedan en la nube" in out
    assert fij == [(root, [root / ".git", root / "backend"], ["rentafija.py"])]
    assert "sólo para el código" in out and "queda a petición" in out


def test_main_sin_git_cae_a_la_heuristica(tmp_path, monkeypatch, capsys) -> None:
    """Sin git en el PATH (o `.git` sin bajar): por sufijo y tamaño, fuera de
    los proyectos vecinos; el pin de la raíz va por sufijos."""
    root = _con_vecinos(tmp_path)
    (root / "grande.py").write_bytes(b"g")
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    sin = {"bna_fx.py", "dataset.parquet", "extractor.py", "export viejo.xlsx", "grande.py"}
    attrs = _atributos_fake(sin)

    def con_tamanio(entry):
        a, t, size = attrs(entry)
        return a, t, (30 << 20) if entry.name == "grande.py" else size

    monkeypatch.setattr(onedrive, "_atributos", con_tamanio)
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert sorted(leidos) == ["bna_fx.py", "export viejo.xlsx"]       # el .py de 30 MB y el vecino, no
    assert "no parecen código" in out
    cmds = onedrive._CMDS
    assert ["-U", "+P", str(root / "backend" / "*"), "/S", "/D"] in cmds
    assert ["-U", "+P", str(root / "*.py")] in cmds and not any("proyecto" in c[2] for c in cmds)
    assert not any(c[2] == str(root) for c in cmds)                    # la raíz, nunca


def test_main_migra_el_pin_entero_del_codigo(tmp_path, monkeypatch, capsys) -> None:
    """Una PC con la raíz fijada por el pre-flight de hasta el 11/11: se saca
    el pin de la carpeta entera (attrib -P, sin liberar espacio) y se pone el
    selectivo; en el arranque siguiente, con lo selectivo ya fijado, nada."""
    root = _con_vecinos(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_atributos_de",
                        lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG) if p == root else (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert "dejo de forzar la bajada de la carpeta entera" in out and "Liberar espacio" in out
    cmds = onedrive._CMDS
    assert cmds[0] == ["-P", str(root / "*"), "/S", "/D"] and cmds[1] == ["-P", str(root)]
    assert ["-U", "+P", str(root / "backend" / "*"), "/S", "/D"] in cmds[2:]
    # raíz sin pin y lo selectivo fijado: no se toca nada
    cmds.clear()
    monkeypatch.setattr(onedrive, "_atributos_de",
                        lambda p: (0x10, NUBE_TAG) if p == root else (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert not cmds and "código completo" in capsys.readouterr().out


def test_main_todo_baja_y_fija_la_carpeta_entera(tmp_path, monkeypatch, capsys) -> None:
    """`--todo` = lo de antes: todo lo pendiente y la raíz entera."""
    root = _con_vecinos(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py", "dataset.parquet"}))
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    # la raíz: sin pin antes de fijar, con pin después (attrib pone el atributo al toque)
    estados = iter([(0x10, NUBE_TAG), (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG)])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: next(estados))
    assert onedrive.main(["--carpeta", str(root), "--todo"]) == 0
    out = capsys.readouterr().out
    assert sorted(leidos) == ["bna_fx.py", "dataset.parquet"] and fijadas == [root]
    assert "2 de 7 archivos" in out and "Mantener siempre en este dispositivo" in out


def test_main_sale_4_si_onedrive_no_entrega_y_no_fija(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py"}))

    def leer(p: Path) -> None:
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(onedrive, "_leer", leer)
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("no se fija con archivos sin bajar"))
    assert onedrive.main(["--carpeta", str(root)]) == onedrive.EXIT_SIN_BAJAR == 4
    out = capsys.readouterr().out
    assert "Invalid argument" in out and "OneDrive no los entreg" in out and "no puede arrancar" in out


def test_main_listar_informa_sin_tocar(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py"}))
    monkeypatch.setattr(onedrive, "_leer", lambda p: pytest.fail("--listar no baja"))
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("--listar no fija"))
    assert onedrive.main(["--carpeta", str(root), "--listar"]) == 4
    assert "bna_fx.py" in capsys.readouterr().out


def test_main_todo_local_fija_una_vez_y_despues_calla(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_leer", lambda p: pytest.fail("nada que bajar"))
    fij: list = []
    monkeypatch.setattr(onedrive, "fijar_parcial",
                        lambda r, c, pt, run=None: (fij.append(r), (True, ""))[1])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert fij == [root] and "código completo" in capsys.readouterr().out
    # lo selectivo ya fijado (attrib +P de la vez anterior): no se vuelve a correr attrib
    monkeypatch.setattr(onedrive, "_atributos_de",
                        lambda p: (0x10, NUBE_TAG) if p == root else (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert fij == [root] and "código completo" in capsys.readouterr().out
    # --sin-pin tampoco
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root), "--sin-pin"]) == 0
    assert fij == [root]


def test_main_carpeta_comun_y_otras_plataformas_silencio(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set(), nube=False))
    monkeypatch.setattr(onedrive, "raices_onedrive", lambda: [])        # el runner puede tener %OneDrive%
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("fuera de OneDrive no se fija"))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert capsys.readouterr().out == ""
    for plat in ("darwin", "linux"):
        monkeypatch.setattr(onedrive, "_PLATFORM", plat)
        monkeypatch.setattr(onedrive, "escanear", lambda *a, **k: pytest.fail("no se escanea fuera de Windows"))
        assert onedrive.main(["--carpeta", str(root)]) == 0


def test_el_bat_corre_el_preflight_antes_de_https_y_explica_el_error() -> None:
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    i_one, i_https, i_uvi = (bat.index("backend.tools.onedrive"), bat.index("backend.tools.https_local"),
                             bat.index("-m uvicorn backend.main:app"))
    assert i_one < i_https < i_uvi                   # https_local ya importa medio backend
    assert i_one < bat.index("pip install -r")       # y pip lee requirements.txt: tambien puede ser marcador
    # exit 4 (archivos sin bajar) tiene su mensaje; cualquier otro error, el generico
    i_datos = bat.index("backend.tools.onedrive --datos")
    assert "if errorlevel 4 if not errorlevel 5 (" in bat[i_one:i_datos]
    assert "if errorlevel 1 (" in bat[i_one:i_datos] and "exit /b 4" in bat[i_one:i_datos]
    assert "Errno 22" in bat[i_one:i_datos]
    assert "Mantener siempre en este dispositivo" in bat[i_one:i_datos]
    assert bat.isascii()


def test_el_bat_fija_y_baja_las_carpetas_de_datos_sin_cortar_el_arranque() -> None:
    """04/11: el paso `--datos` (Delta Bases / Carteras / CAFCI) va DESPUÉS del
    del código y ANTES de pip, y con errorlevel 4 sólo AVISA (la app sabe
    correr sin bases): nunca `exit /b`. El backfill lo corre también."""
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    i_one, i_datos = bat.index("backend.tools.onedrive\n"), bat.index("backend.tools.onedrive --datos")
    assert i_one < i_datos < bat.index("pip install -r")
    bloque = bat[i_datos:bat.index("REM --- 3) dependencias")]
    assert "if errorlevel 4 if not errorlevel 5 (" in bloque and "[AVISO]" in bloque
    assert "exit /b" not in bloque and "pause" not in bloque
    bf = (ROOT / "backfill_historico.bat").read_text(encoding="utf-8")
    assert "backend.tools.onedrive --datos --quiet" in bf and bf.isascii()
    assert "exit /b" not in bf[bf.index("--datos --quiet"):bf.index(":menu")]


def _arbol_datos(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """La biblioteca de OneDrive de una PC nueva: Delta Bases (con Carteras y
    cierres adentro) y Precios Cafci al lado, todo como marcadores."""
    lib = tmp_path / "Inversiones - Documentos"
    bases, cart = lib / "Delta Bases", lib / "Delta Bases" / "Carteras"
    cierres, cafci = bases / "cierres" / "2024", lib / "Equipo RF" / "Precios Cafci"
    for d in (cart, cierres, cafci):
        d.mkdir(parents=True)
    for n in ("Delta - historico_byma_px_tasas.xlsx", "Delta - historico_byma_px_tasas.parquet",
              "Delta - historico_byma_px_tasas.parquet.src.json", "Delta - historico_fx.xlsx",
              "Delta - Especies.xlsx", "bna_fx (1).json", "base_manifest.json"):
        (bases / n).write_bytes(b"x" * 100)
    for n in ("Delta_Composicion.xlsx", "Delta_PN.xlsx"):
        (cart / n).write_bytes(b"c" * 50)
    for n in ("2024-07-04.parquet", "2024-07-05.parquet"):
        (cierres / n).write_bytes(b"p" * 10)
    for n in ("20250901.xlsx", "20250902.xlsx", "20250903.xlsx", "20250904.xlsx"):
        (cafci / n).write_bytes(b"v" * 20)
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(bases))
    monkeypatch.setenv("DELTA_BASES_DIR", str(cart))
    monkeypatch.setenv("DELTA_CAFCI_DIR", str(cafci))
    # un secrets.txt VACÍO y existente: OMSsecrets sólo salta candidatos que
    # no son archivo, así que con uno inexistente caía al secrets.txt real de
    # la raíz / CWD de una PC del desk (y sus carpetas entraban al test)
    vacio = tmp_path / "secrets-vacio.txt"
    vacio.write_text("", encoding="utf-8")
    monkeypatch.setenv("SECRETS_FILE", str(vacio))
    for v in ("DELTA_CAFCI_PATH", "DELTA_ESPECIES_PATH", "DELTA_COMPOSICION_PATH", "DELTA_PN_PATH",
              "GALILEO_COMPOSICION_PATH", "GALILEO_PN_PATH", "DELTA_FONDOS_PATH", "DELTA_HISTORICO_PATH"):
        monkeypatch.delenv(v, raising=False)
    return bases, cart, cafci


_TODOS_DATOS = {"Delta - historico_byma_px_tasas.xlsx", "Delta - historico_byma_px_tasas.parquet",
                "Delta - historico_byma_px_tasas.parquet.src.json", "Delta - historico_fx.xlsx",
                "Delta - Especies.xlsx", "bna_fx (1).json", "base_manifest.json", "Delta_Composicion.xlsx",
                "Delta_PN.xlsx", "2024-07-04.parquet", "2024-07-05.parquet",
                "20250901.xlsx", "20250902.xlsx", "20250903.xlsx", "20250904.xlsx"}
_ESENCIALES_ESPERADOS = {"Delta - historico_byma_px_tasas.xlsx", "Delta - historico_byma_px_tasas.parquet",
                         "Delta - historico_byma_px_tasas.parquet.src.json", "Delta - historico_fx.xlsx",
                         "Delta - Especies.xlsx", "base_manifest.json", "Delta_Composicion.xlsx", "Delta_PN.xlsx",
                         "20250904.xlsx", "20250903.xlsx", "20250902.xlsx"}


def _modo_datos(monkeypatch, sin_contenido: set[str]) -> tuple[list[str], list[Path]]:
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(sin_contenido))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    monkeypatch.setattr(onedrive, "raices_onedrive", lambda: [])
    monkeypatch.setattr(onedrive, "exponer_marcadores", lambda: False)
    leidos: list[str] = []
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    monkeypatch.delenv("ONEDRIVE_PIN_DATOS", raising=False)
    return leidos, fijadas


def test_datos_fija_solo_lo_que_la_app_lee_y_baja_lo_esencial(tmp_path, monkeypatch, capsys) -> None:
    """`--datos` (04/11, selectivo desde el 11/11): se bajan YA los archivos
    que el arranque necesita (composición, PN, Especies, bases px/tasas +
    espejo + firma, FX, manifiesto, los 3 vectores CAFCI más nuevos) y el pin
    "Mantener siempre en este dispositivo" va SÓLO a lo que la app lee: los
    archivos de la raíz de Delta Bases, `cierres/` entera y los archivos de
    Carteras — no la carpeta entera (27 GB en la PC del desk) ni la de CAFCI
    (7 GB de historia; queda a petición). Nada se clasifica como basura ni
    se borra: es la biblioteca compartida."""
    bases, cart, cafci = _arbol_datos(tmp_path, monkeypatch)
    leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)
    assert onedrive.main(["--datos"]) == 0
    out = capsys.readouterr().out
    assert set(leidos) == _ESENCIALES_ESPERADOS
    assert fijadas == [(bases / "cierres").resolve()]                   # la única carpeta entera
    b = bases.resolve()
    assert onedrive._CMDS == [["-U", "+P", str(b / "*")], ["-U", "+P", str(b / "Carteras" / "*")]]
    assert not any("Cafci" in c[2] for c in onedrive._CMDS)
    assert (bases / "bna_fx (1).json").exists()                        # ni basura ni borrado
    assert "sólo para lo que la app lee" in out and "archivos de la raíz · archivos de Carteras · cierres" in out
    assert "queda a petición" in out and "sólo si la app los lee" in out
    assert "Delta Bases:" in out and "DELTA_CAFCI_DIR:" in out


def test_datos_pin_datos_0_no_fija_nada_y_destraba_el_pin_viejo(tmp_path, monkeypatch, capsys) -> None:
    """`ONEDRIVE_PIN_DATOS=0` en secrets.txt: ningún pin (se baja lo esencial
    y el resto a petición); una raíz fijada por el pre-flight viejo se
    destraba (attrib -P, sin liberar espacio)."""
    bases, cart, cafci = _arbol_datos(tmp_path, monkeypatch)
    leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)
    monkeypatch.setenv("ONEDRIVE_PIN_DATOS", "0")
    assert onedrive.main(["--datos"]) == 0
    assert set(leidos) == _ESENCIALES_ESPERADOS and not fijadas and not onedrive._CMDS
    assert "quedan en la nube y se bajan" in capsys.readouterr().out
    # la raíz figura fijada: se destraba
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--datos"]) == 0
    out = capsys.readouterr().out
    b, c = bases.resolve(), cafci.resolve()
    assert onedrive._CMDS == [["-P", str(b / "*"), "/S", "/D"], ["-P", str(b)],
                              ["-P", str(c / "*"), "/S", "/D"], ["-P", str(c)]]
    assert "dejo de forzar la bajada de la carpeta entera" in out and "Liberar espacio" in out
    assert not fijadas


def test_datos_pin_datos_todo_fija_las_carpetas_enteras(tmp_path, monkeypatch, capsys) -> None:
    """`ONEDRIVE_PIN_DATOS=todo` (o `--todo`): lo de hasta el 11/11, la
    biblioteca entera local en esa PC."""
    bases, cart, cafci = _arbol_datos(tmp_path, monkeypatch)
    leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)
    monkeypatch.setenv("ONEDRIVE_PIN_DATOS", "todo")
    assert onedrive.main(["--datos"]) == 0
    out = capsys.readouterr().out
    assert set(fijadas) == {bases.resolve(), cafci.resolve()} and not onedrive._CMDS
    assert "ONEDRIVE_PIN_DATOS=todo" in out and "segundo plano" in out
    fijadas.clear()
    monkeypatch.delenv("ONEDRIVE_PIN_DATOS")
    assert onedrive.main(["--datos", "--todo"]) == 0
    assert set(fijadas) == {bases.resolve(), cafci.resolve()}


def test_carpetas_datos_detalle_anida_carteras_en_delta_bases(tmp_path, monkeypatch) -> None:
    bases, cart, cafci = _arbol_datos(tmp_path, monkeypatch)
    det = onedrive.carpetas_datos_detalle()
    assert [(l, r) for l, r, _h in det] == onedrive.carpetas_datos()
    por_label = {l: (r, h) for l, r, h in det}
    assert por_label["Delta Bases"] == (bases.resolve(), [cart.resolve()])
    assert por_label["DELTA_CAFCI_DIR"] == (cafci.resolve(), [])
    # el plan de pin: raíz + Carteras por archivos, cierres entera; CAFCI sin pin
    plan = onedrive.plan_pin("Delta Bases", bases.resolve(), [cart.resolve()])
    assert plan == ([(bases / "cierres").resolve()], ["*", os.path.join("Carteras", "*")])
    assert onedrive.plan_pin("DELTA_CAFCI_DIR", cafci.resolve(), []) is None
    assert onedrive.es_carpeta_cafci("DELTA_COMPOSICION_PATH", cafci.resolve()) is False   # pocos xlsx
    for i in range(10):
        (cafci / f"2025100{i}.xlsx").write_bytes(b"v")
    assert onedrive.es_carpeta_cafci("otra", cafci.resolve()) is True   # por contenido


def test_datos_avisa_y_sale_4_sin_cortar_si_onedrive_no_entrega(tmp_path, monkeypatch, capsys) -> None:
    _arbol_datos(tmp_path, monkeypatch)
    _leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)

    def leer(p: Path) -> None:
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(onedrive, "_leer", leer)
    assert onedrive.main(["--datos"]) == onedrive.EXIT_SIN_BAJAR
    out = capsys.readouterr().out
    assert fijadas                                                      # el pin igual queda puesto
    assert "esenciales siguen sin contenido" in out and "La app arranca igual" in out


def test_datos_listar_informa_sin_tocar_y_sin_carpetas_calla(tmp_path, monkeypatch, capsys) -> None:
    _arbol_datos(tmp_path, monkeypatch)
    leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)
    assert onedrive.main(["--datos", "--listar"]) == onedrive.EXIT_SIN_BAJAR
    out = capsys.readouterr().out
    assert not leidos and not fijadas
    assert "esenciales para el arranque" in out and "Delta_Composicion.xlsx" in out and "SIN fijar" in out
    # todo bajado: sin pendientes, sin pin repetido si ya está fijada
    leidos, fijadas = _modo_datos(monkeypatch, set())
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--datos"]) == 0
    out = capsys.readouterr().out
    assert not leidos and not fijadas and "datos completos" in out
    # la raíz fijada entera (pre-flight viejo) se destraba; lo selectivo ya está (PINNED): no se repite
    assert [c[0] for c in onedrive._CMDS] == ["-P", "-P", "-P", "-P"] and "dejo de forzar" in out
    # sin carpetas de datos en secrets.txt: nada que hacer
    for v in ("DELTA_HISTORICO_DIR", "DELTA_BASES_DIR", "DELTA_CAFCI_DIR"):
        monkeypatch.delenv(v)
    assert onedrive.main(["--datos"]) == 0
    assert "sin carpetas de datos" in capsys.readouterr().out


def test_escanear_sin_clasificar_basura_no_separa_nada(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Delta Bases"
    (root / "data").mkdir(parents=True)
    (root / "bcra_data_backup-PC.json").write_bytes(b"j")
    (root / "data" / "market_snapshot-PC-1.json").write_bytes(b"s")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "raices_onedrive", lambda: [])
    con = onedrive.escanear(root)
    sin = onedrive.escanear(root, clasificar_basura=False)
    assert len(con.basura) == 2 and con.total == 0
    assert not sin.basura and sin.total == 2


def test_certs_y_data_entran_al_chequeo(tmp_path, monkeypatch) -> None:
    """certs/ y data/ viven adentro del clon sincronizado y se leen (https_local,
    pizarra / preferencias compartidas): un cert "sólo en la nube" haría
    regenerar la CA. .git y __pycache__ siguen afuera. Un market_snapshot.json
    reciente en data/ (PC con la versión anterior) no es basura todavía."""
    root = _arbol(tmp_path)
    (root / "certs").mkdir()
    (root / "certs" / "oms-local-ca.crt").write_bytes(b"cert")
    (root / "data").mkdir()
    (root / "data" / "market_snapshot.json").write_bytes(b"{}")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"oms-local-ca.crt", "aa"}))
    esc = onedrive.escanear(root, raices=[])
    assert esc.total == 6 and [a.path.name for a in esc.pendientes] == ["oms-local-ca.crt"]
    assert "certs" not in onedrive.EXCLUIR and "data" not in onedrive.EXCLUIR and ".git" in onedrive.EXCLUIR


def test_main_quiet_calla_el_progreso_pero_no_los_fallos(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py", "fx.py"}))
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (True, ""))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    monkeypatch.setattr(onedrive, "_leer", lambda p: None)
    assert onedrive.main(["--carpeta", str(root), "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "bajándolos" in out and " ok" not in out                    # cabecera sí, progreso por archivo no

    def leer(p: Path) -> None:
        if p.name == "fx.py":
            raise OSError(22, "Invalid argument")

    monkeypatch.setattr(onedrive, "_leer", leer)
    assert onedrive.main(["--carpeta", str(root), "--quiet"]) == 4
    out = capsys.readouterr().out
    assert "x " in out and "fx.py" in out and "bna_fx.py ($" not in out


def test_main_avisa_si_attrib_falla_o_el_pin_no_se_ve(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    monkeypatch.setattr(onedrive, "fijar_parcial", lambda r, c, pt, run=None: (False, "backend: Acceso denegado"))
    assert onedrive.main(["--carpeta", str(root)]) == 0                 # fijar es best-effort
    out = capsys.readouterr().out
    assert "no pude fijar" in out and "Acceso denegado" in out and "Mantener siempre en este dispositivo" in out
    # --todo: attrib devolvió 0 pero la raíz no muestra PINNED (el tmp de Linux nunca lo tiene)
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (True, ""))
    assert onedrive.main(["--carpeta", str(root), "--todo"]) == 0
    out = capsys.readouterr().out
    assert "todavía no figura fijada" in out and "carpeta marcada" not in out
    # y con el pin visible, el mensaje normal
    estados = iter([(0x10, NUBE_TAG), (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG)])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: next(estados))
    assert onedrive.main(["--carpeta", str(root), "--todo"]) == 0
    assert "carpeta marcada" in capsys.readouterr().out


def test_say_cae_a_ascii_si_la_consola_no_puede(monkeypatch, capsys) -> None:
    import builtins
    real = builtins.print
    intentos: list[str] = []

    def print_cp(msg, *a, **k):
        intentos.append(msg)
        if any(ord(c) > 127 for c in msg):
            raise UnicodeEncodeError("cp1252", msg, 0, 1, "no")
        real(msg, *a, **k)

    monkeypatch.setattr(builtins, "print", print_cp)
    onedrive._say("[onedrive] bajándolos… ok")
    assert len(intentos) == 2 and capsys.readouterr().out == "[onedrive] baj?ndolos? ok\n"


def test_backfill_bat_corre_el_mismo_chequeo() -> None:
    bat = (ROOT / "backfill_historico.bat").read_text(encoding="utf-8")
    assert "backend.tools.onedrive --quiet" in bat and "exit /b 4" in bat
    assert bat.index("backend.tools.onedrive") < bat.index(":menu") and bat.isascii()


def test_main_sale_4_si_no_pudo_listar_una_carpeta_de_la_nube(tmp_path, monkeypatch, capsys) -> None:
    """Lo que hay adentro de una carpeta que no se pudo listar no se chequeó
    ni se bajó: en una carpeta de nube es lo mismo que un archivo sin contenido."""
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("no se fija con carpetas sin listar"))
    real = os.scandir

    def scandir(d):
        if str(d).endswith("services"):
            raise PermissionError(13, "denegado")
        return real(d)

    monkeypatch.setattr(onedrive.os, "scandir", scandir)
    assert onedrive.main(["--carpeta", str(root)]) == 4
    out = capsys.readouterr().out
    assert "no pude listar" in out and "services" in out and "no se bajó" in out
    # en una carpeta común (fuera de OneDrive) el listado fallido sólo se informa
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set(), nube=False))
    monkeypatch.setattr(onedrive, "raices_onedrive", lambda: [])
    assert onedrive.main(["--carpeta", str(root)]) == 0


# ── restos de cachés por máquina (15/10) ─────────────────────────────────────
# El desk vio `data/` con ~6 GB de `market_snapshot-DAM-NB-CIO-<n>.json` y este
# chequeo bajándolos enteros (6.522 de 8.449 archivos "sólo en la nube"): cada
# PC reescribía el snapshot del store adentro del clon y OneDrive dejaba la
# versión perdedora como copia en conflicto. Se borran sin bajarlos.
DIA = 86400.0


def test_basura_de_clasifica_solo_restos_de_caches_por_maquina() -> None:
    b = onedrive.basura_de
    # copias en conflicto de OneDrive (nombre de la PC, con o sin contador) y copias a mano
    assert b("data", "market_snapshot-DAM-NB-CIO-191.json", 0) == ("market_snapshot.json", "copia en conflicto")
    assert b("data", "market_snapshot-DAM-NB-CIO.json", None) == ("market_snapshot.json", "copia en conflicto")
    assert b("data", "MARKET_SNAPSHOT-PC.JSON", 0) == ("market_snapshot.json", "copia en conflicto")
    assert b("data", "bna_fx (1).json", 0)[1] == "copia en conflicto"
    assert b("data", "riesgo_pais-NOTEBOOK-RC.json", 0)[1] == "copia en conflicto"
    assert b("", "cer_completo.generated-DAM-NB-CIO.csv", 0)[1] == "copia en conflicto"
    assert b("", "bcra_data_backup-DAM-NB-CIO-3.json", 0) == ("bcra_data_backup.json", "copia en conflicto")
    # temporales de los escritores (y sus copias): sólo con edad (puede ser una escritura en curso)
    assert b("data", "market_snapshot.json.tmp", 3600)[1] == "temporal"
    assert b("data", "bna_fx.json.4242.tmp", 3600)[1] == "temporal"
    assert b("data", "market_snapshot.json-DAM-NB-CIO.tmp", 3600)[1] == "temporal"
    assert b("data", "market_snapshot.json.tmp", 30) is None
    assert b("data", "market_snapshot.json.tmp", None) is None
    # el original: sólo si nadie lo escribió en una semana; el de bcra (versionado) nunca
    assert b("data", "market_snapshot.json", 8 * DIA) == ("market_snapshot.json", "original viejo")
    assert b("data", "market_snapshot.json", 1 * DIA) is None
    assert b("", "cer_completo.generated.csv", 30 * DIA)[1] == "original viejo"
    assert b("", "bcra_data_backup.json", 365 * DIA) is None
    # lo compartido a propósito y cualquier otro archivo: nunca
    for nombre in ("pizarra.json", "pizarra-DAM-NB-CIO.json", "escenario_prefs.json", "alertas.json",
                   "market_snapshots.json", "market_snapshot.json.bak", "bna_fx.jsonl", "notas.txt"):
        assert b("data", nombre, 365 * DIA) is None, nombre
    # sólo en su carpeta: un market_snapshot de la raíz o de backend/ no es nuestro
    assert b("", "market_snapshot-PC.json", 0) is None
    assert b("backend", "market_snapshot-PC.json", 0) is None
    assert b("data", "bcra_data_backup-PC.json", 0) is None


def _con_basura(tmp_path: Path) -> Path:
    root = _arbol(tmp_path)
    data = root / "data"
    data.mkdir()
    for n in range(1, 4):
        (data / f"market_snapshot-DAM-NB-CIO-{n}.json").write_bytes(b"s" * 2000)
    (data / "market_snapshot.json").write_bytes(b"{}")            # original viejo (se envejece abajo)
    (data / "bna_fx.json.77.tmp").write_bytes(b"t")               # temporal huérfano viejo
    (data / "riesgo_pais.json.88.tmp").write_bytes(b"t")          # temporal reciente: se respeta
    (data / "pizarra.json").write_bytes(b"{}")                    # compartido a propósito
    (data / "pizarra-DAM-NB-CIO.json").write_bytes(b"{}")         # copia de algo que NO es caché
    (root / "bcra_data_backup.json").write_bytes(b"{}")           # versionado
    (root / "bcra_data_backup-DAM-NB-CIO.json").write_bytes(b"b" * 500)
    viejo = time.time() - 30 * DIA
    for p in (data / "market_snapshot.json", data / "bna_fx.json.77.tmp", root / "bcra_data_backup.json"):
        os.utime(p, (viejo, viejo))
    return root


def test_escanear_separa_la_basura_sin_contarla_ni_bajarla(tmp_path, monkeypatch) -> None:
    root = _con_basura(tmp_path)
    # todo lo de data/ "sólo en la nube", como en la PC del desk
    sin = {p.name for p in (root / "data").iterdir()} | {"bcra_data_backup-DAM-NB-CIO.json", "bna_fx.py"}
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(sin))
    esc = onedrive.escanear(root, raices=[])
    basura = sorted((a.path.name, a.motivo) for a in esc.basura)
    assert basura == [("bcra_data_backup-DAM-NB-CIO.json", "copia en conflicto"),
                      ("bna_fx.json.77.tmp", "temporal"),
                      ("market_snapshot-DAM-NB-CIO-1.json", "copia en conflicto"),
                      ("market_snapshot-DAM-NB-CIO-2.json", "copia en conflicto"),
                      ("market_snapshot-DAM-NB-CIO-3.json", "copia en conflicto"),
                      ("market_snapshot.json", "original viejo")]
    pend = sorted(a.path.name for a in esc.pendientes)
    assert pend == ["bna_fx.py", "pizarra-DAM-NB-CIO.json", "pizarra.json", "riesgo_pais.json.88.tmp"]
    assert esc.total == 4 + 3 + 1                                 # código + data/ legítimo + bcra versionado
    assert [o for o, _n, _b in onedrive.por_origen(esc.basura)][0] == "market_snapshot.json"


def test_main_borra_la_basura_sin_bajarla_y_despues_fija(tmp_path, monkeypatch, capsys) -> None:
    root = _con_basura(tmp_path)
    sin = {p.name for p in (root / "data").iterdir()}
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(sin))
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    fij: list = []
    monkeypatch.setattr(onedrive, "fijar_parcial",
                        lambda r, c, pt, run=None: (fij.append((r, list(c))), (True, ""))[1])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    # la basura NO se lee (no se baja): sólo lo legítimo (data/ se baja aunque git no lo versione)
    assert sorted(leidos) == ["pizarra-DAM-NB-CIO.json", "pizarra.json", "riesgo_pais.json.88.tmp"]
    quedan = sorted(p.name for p in (root / "data").iterdir())
    assert quedan == ["pizarra-DAM-NB-CIO.json", "pizarra.json", "riesgo_pais.json.88.tmp"]
    assert (root / "bcra_data_backup.json").exists() and not (root / "bcra_data_backup-DAM-NB-CIO.json").exists()
    assert "borré 6 restos" in out and "market_snapshot.json 4" in out and "sin bajarlos" in out
    assert "%LOCALAPPDATA%\\bonos" in out and fij == [(root, [root / ".git", root / "backend", root / "data"])]
    # segundo arranque: nada que borrar, nada que decir de eso
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_atributos_de",
                        lambda p: (0x10, NUBE_TAG) if p == root else (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert "borré" not in capsys.readouterr().out


def test_main_no_fija_si_quedo_basura_sin_borrar(tmp_path, monkeypatch, capsys) -> None:
    """OneDrive cerrado: borrar un marcador puede fallar. No se baja, y la
    carpeta no se fija (con el pin OneDrive bajaría esos GB en segundo plano)."""
    root = _con_basura(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_leer", lambda p: pytest.fail("nada que bajar"))
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("no se fija con basura sin borrar"))
    real = os.remove

    def remove(p):
        if "market_snapshot" in str(p):
            raise OSError(22, "Invalid argument")
        real(p)

    monkeypatch.setattr(onedrive.os, "remove", remove)
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert "borré 2 restos" in out and "4 no se pudieron borrar" in out and "no se fija todavía" in out
    assert (root / "data" / "market_snapshot-DAM-NB-CIO-1.json").exists()


def test_main_listar_muestra_la_basura_sin_borrarla(tmp_path, monkeypatch, capsys) -> None:
    root = _con_basura(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "borrar_basura", lambda *a, **k: pytest.fail("--listar no borra"))
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("--listar no fija"))
    assert onedrive.main(["--carpeta", str(root), "--listar"]) == 0
    out = capsys.readouterr().out
    assert "6 restos de cachés por PC para borrar" in out and "market_snapshot-DAM-NB-CIO-2.json" in out
    assert "copia en conflicto" in out and "original viejo" in out
    assert (root / "data" / "market_snapshot-DAM-NB-CIO-1.json").exists()


def test_main_con_muchos_pendientes_resume_por_carpeta(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    (root / "static").mkdir()
    nombres = set()
    for i in range(55):
        (root / "static" / f"f{i:03}.js").write_bytes(b"j" * 100)
        nombres.add(f"f{i:03}.js")
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(nombres | {"bna_fx.py"}))
    monkeypatch.setattr(onedrive, "_leer", lambda p: None)
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (True, ""))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert "56 de 59 archivos" in out
    assert "static: 55 archivos" in out and "backend: 1 archivos" in out
    assert "… 56/56" in out and " ok" not in out                       # sin una línea por archivo
    assert out.count("[onedrive]   …") <= 11


def test_hidratar_informa_el_progreso() -> None:
    a = [onedrive.Archivo(Path("x"), 0, 0, 10), onedrive.Archivo(Path("y"), 0, 0, 5)]
    vistos: list[tuple] = []
    import backend.tools.onedrive as od
    real = od._leer
    try:
        od._leer = lambda p: None
        assert od.hidratar(a, progreso=lambda i, b: vistos.append((i, b))) == []
    finally:
        od._leer = real
    assert vistos == [(1, 10), (2, 15)]


def test_ctrl_c_a_mitad_de_la_bajada_sale_limpio_y_no_fija(tmp_path, monkeypatch, capsys) -> None:
    """15/10: el desk cortó con Ctrl+C mientras bajaba miles de copias y quedó
    un traceback de KeyboardInterrupt. Ahora: mensaje, exit 0 (cmd pregunta
    igual si terminar el .bat) y sin fijar la carpeta."""
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py", "fx.py"}))

    def leer(p: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(onedrive, "_leer", leer)
    monkeypatch.setattr(onedrive, "fijar", lambda *a, **k: pytest.fail("cortado: no se fija"))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert "cortado con Ctrl+C" in out and "Traceback" not in out


def test_caches_de_python_se_borran_solo_con_el_prefijo_activo(tmp_path, monkeypatch, capsys) -> None:
    """15/10: cada PC compilaba sus .pyc en __pycache__ adentro del clon y
    OneDrive los repartía (un set por versión de Python, copias en conflicto).
    Con PYTHONPYCACHEPREFIX (lo ponen los launchers) los de adentro ya no se
    usan y se borran; sin el prefijo volverían a aparecer, así que no se tocan."""
    root = _arbol(tmp_path)                                          # trae __pycache__/m.pyc en la raíz
    svc_cache = root / "backend" / "services" / "__pycache__"
    svc_cache.mkdir()
    (svc_cache / "fx.cpython-314.pyc").write_bytes(b"p" * 100)
    (svc_cache / "fx.cpython-314-DAM-NB-CIO.pyc").write_bytes(b"p" * 100)   # copia en conflicto
    (root / ".pytest_cache" / "v").mkdir(parents=True)
    (root / ".pytest_cache" / "v" / "lastfailed").write_bytes(b"{}")
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (True, ""))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    esc = onedrive.escanear(root, raices=[])
    assert sorted(str(p.relative_to(root)) for p in esc.caches_py) == sorted(
        [".pytest_cache", "__pycache__", os.path.join("backend", "services", "__pycache__")])
    # sin prefijo (launcher viejo / python a mano): no se tocan
    monkeypatch.setattr(onedrive, "prefijo_pycache", lambda: None)
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert (root / "__pycache__" / "m.pyc").exists() and "caché de Python" not in capsys.readouterr().out
    # --listar sólo informa
    monkeypatch.setattr(onedrive, "prefijo_pycache", lambda: "C:\\Users\\p\\AppData\\Local\\bonos\\pycache")
    onedrive.main(["--carpeta", str(root), "--listar"])
    assert "3 carpetas de caché de Python" in capsys.readouterr().out and svc_cache.exists()
    # con el prefijo: se borran (los .py nunca)
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert not (root / "__pycache__").exists() and not svc_cache.exists() and not (root / ".pytest_cache").exists()
    assert "borré 3 carpetas de caché de Python del código (4 archivos" in out
    assert (root / "backend" / "services" / "fx.py").exists() and (root / ".git" / "objects" / "aa").exists()


def test_los_launchers_ponen_los_pyc_fuera_del_clon() -> None:
    for nombre in ("run_backend (CORRER APP).bat", "backfill_historico.bat"):
        bat = (ROOT / nombre).read_text(encoding="utf-8")
        i = bat.index('set "PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\\bonos\\pycache"')
        assert i < bat.index("backend.tools.onedrive"), nombre             # antes del primer python del backend
        assert bat.isascii(), nombre
    cmd = (ROOT / "correr_app.command").read_text(encoding="utf-8")
    assert cmd.index("export PYTHONPYCACHEPREFIX=") < cmd.index('"$PY" -m')


def test_fijar_parcial_y_desfijar_arman_los_attrib(tmp_path, monkeypatch) -> None:
    """`fijar_parcial`: cada carpeta entera (recursivo + la carpeta, como
    `fijar`) y cada patrón de archivos sin /S; la raíz nunca. `desfijar`:
    `-P` recursivo y después la raíz; si el recursivo falla, la raíz sigue
    fijada (se reintenta)."""
    monkeypatch.setattr(onedrive, "_attrib", _ATTRIB_REAL)
    llamadas: list[list[str]] = []

    def run(argv, **kw):
        llamadas.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    ok, det = onedrive.fijar_parcial(tmp_path, [tmp_path / "cierres"], ["*", "Carteras/*"], run=run)
    assert ok and det == ""
    assert llamadas == [["attrib", "-U", "+P", str(tmp_path / "cierres" / "*"), "/S", "/D"],
                        ["attrib", "-U", "+P", str(tmp_path / "cierres")],
                        ["attrib", "-U", "+P", str(tmp_path / "*")],
                        ["attrib", "-U", "+P", str(tmp_path / "Carteras/*")]]
    assert not any(a[-1] == str(tmp_path) for a in llamadas)
    llamadas.clear()
    assert onedrive.desfijar(tmp_path, run=run) == (True, "")
    assert llamadas == [["attrib", "-P", str(tmp_path / "*"), "/S", "/D"], ["attrib", "-P", str(tmp_path)]]

    def run_mal(argv, **kw):
        if "/S" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "Acceso denegado")
        pytest.fail("con el recursivo fallido no se toca la raíz")

    ok, det = onedrive.desfijar(tmp_path, run=run_mal)
    assert not ok and "Acceso denegado" in det

    def run_mal_s(argv, **kw):                      # falla sólo el recursivo: los patrones siguen (best-effort)
        return subprocess.CompletedProcess(argv, 1 if "/S" in argv else 0, "", "Acceso denegado")

    llamadas.clear()
    ok, det = onedrive.fijar_parcial(tmp_path, [tmp_path / "cierres"], ["*"], run=run_mal_s)
    assert not ok and det == "cierres: Acceso denegado"


def test_seleccion_codigo_git_vs_heuristica(tmp_path, monkeypatch) -> None:
    """Pura: con git, lo versionado + certs/ data/ + los locales del
    arranque; sin git, sufijo + ≤ 20 MB + fuera de los vecinos. Y los
    objetivos del pin."""
    root = _con_vecinos(tmp_path)
    (root / "certs").mkdir(); (root / "certs" / "ca.crt").write_bytes(b"c")
    (root / "secrets.txt").write_bytes(b"s")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(
        {"bna_fx.py", "dataset.parquet", "extractor.py", "export viejo.xlsx", "ca.crt", "secrets.txt"}))
    esc = onedrive.escanear(root)
    ver = {os.path.normcase(str(Path(v))) for v in _VERSIONADOS}
    sel = onedrive.seleccion_codigo(esc, root, versionados=ver)
    assert sel.fuente == "git"
    assert sorted(a.path.name for a in sel.necesarios) == ["bna_fx.py", "ca.crt", "secrets.txt"]
    assert sorted(a.path.name for a in sel.omitidos) == ["dataset.parquet", "export viejo.xlsx", "extractor.py"]
    assert sel.carpetas_pin == [root / ".git", root / "backend", root / "certs"]
    assert sel.patrones_pin == ["rentafija.py", "secrets.txt"]
    sel = onedrive.seleccion_codigo(esc, root, versionados=None)
    assert sel.fuente == "heurística"
    assert sorted(a.path.name for a in sel.necesarios) == ["bna_fx.py", "ca.crt", "export viejo.xlsx", "secrets.txt"]
    assert sorted(a.path.name for a in sel.omitidos) == ["dataset.parquet", "extractor.py"]
    assert sel.patrones_pin == list(onedrive._PATRONES_RAIZ_SIN_GIT)


def test_archivos_versionados_sin_git_o_sin_repo(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(onedrive, "archivos_versionados", _VERSIONADOS_REAL)
    assert onedrive.archivos_versionados(tmp_path) is None             # sin .git
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(onedrive.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError(2, "git")))
    assert onedrive.archivos_versionados(tmp_path) is None             # sin git en el PATH
    salida = subprocess.CompletedProcess([], 0, b"backend/x.py\0rentafija.py\0", b"")
    monkeypatch.setattr(onedrive.subprocess, "run", lambda *a, **k: salida)
    assert onedrive.archivos_versionados(tmp_path) == {os.path.normcase(os.path.join("backend", "x.py")),
                                                       "rentafija.py"}
    # el repo de verdad: lo que git versiona acá
    monkeypatch.undo()
    ver = onedrive.archivos_versionados(ROOT)
    assert ver is None or os.path.normcase(os.path.join("backend", "tools", "onedrive.py")) in ver
