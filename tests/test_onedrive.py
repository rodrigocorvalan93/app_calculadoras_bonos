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
from pathlib import Path

import pytest

from backend.tools import onedrive

ROOT = Path(__file__).resolve().parents[1]
NUBE_TAG = 0x9000601A                      # un tag de la familia IO_REPARSE_TAG_CLOUD*
RECALL = onedrive.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | 0x20   # + ARCHIVE


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


def test_fijar_usa_attrib_sobre_la_raiz_y_recursivo(tmp_path) -> None:
    llamadas: list[tuple] = []

    def run(argv, **kw):
        llamadas.append((tuple(argv), kw.get("cwd")))
        return subprocess.CompletedProcess(argv, 0, "", "")

    ok, det = onedrive.fijar(tmp_path, run=run)
    assert ok and det == ""
    # -U: un archivo que OneDrive ya marcó "sólo en la nube" lleva UNPINNED y
    # ese estado propio le gana al pin de la carpeta; \* porque /S sólo
    # recorre lo que matchea el patrón
    assert llamadas[0] == (("attrib", "-U", "+P", str(tmp_path)), None)
    assert llamadas[1] == (("attrib", "-U", "+P", str(tmp_path / "*"), "/S", "/D"), None)

    def run_mal(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", "Acceso denegado")

    ok, det = onedrive.fijar(tmp_path, run=run_mal)
    assert not ok and "Acceso denegado" in det

    def run_sin_attrib(argv, **kw):
        raise FileNotFoundError(2, "attrib")

    ok, det = onedrive.fijar(tmp_path, run=run_sin_attrib)
    assert not ok and "attrib" in det


def test_main_baja_fija_y_sale_0(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py"}))
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert leidos == ["bna_fx.py"] and fijadas == [root]
    assert "1 de 4 archivos" in out and "bna_fx.py" in out and "Siempre mantener en este dispositivo" in out


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
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert fijadas == [root] and "código completo" in capsys.readouterr().out
    # raíz ya fijada (attrib +P de la vez anterior): no se vuelve a correr attrib
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    assert fijadas == [root] and "carpeta fijada" in capsys.readouterr().out
    # --sin-pin tampoco
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    assert onedrive.main(["--carpeta", str(root), "--sin-pin"]) == 0
    assert fijadas == [root]


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
    assert "if errorlevel 1" in bat[i_one:i_https] and "exit /b 4" in bat[i_one:i_https]
    assert "Siempre mantener en este dispositivo" in bat[i_one:i_https]
    assert bat.isascii()
