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


def test_main_baja_fija_y_sale_0(tmp_path, monkeypatch, capsys) -> None:
    root = _arbol(tmp_path)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"bna_fx.py"}))
    leidos: list[str] = []
    monkeypatch.setattr(onedrive, "_leer", lambda p: leidos.append(p.name))
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    # la raíz: sin pin antes de fijar, con pin después (attrib pone el atributo al toque)
    estados = iter([(0x10, NUBE_TAG), (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG)])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: next(estados))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert leidos == ["bna_fx.py"] and fijadas == [root]
    assert "1 de 4 archivos" in out and "bna_fx.py" in out and "Mantener siempre en este dispositivo" in out


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
    return leidos, fijadas


def test_datos_fija_las_carpetas_y_baja_solo_lo_esencial(tmp_path, monkeypatch, capsys) -> None:
    """`--datos` (04/11): Delta Bases (Carteras y cierres adentro: UNA carpeta)
    y Precios Cafci se fijan "Mantener siempre en este dispositivo" y se bajan
    YA los archivos que el arranque necesita (composición, PN, Especies, bases
    px/tasas + espejo + firma, FX, manifiesto, los 3 vectores CAFCI más
    nuevos); las particiones de cierres, la historia CAFCI y un json suelto
    los baja OneDrive en segundo plano. Nada se clasifica como basura ni se
    borra: es la biblioteca compartida."""
    bases, cart, cafci = _arbol_datos(tmp_path, monkeypatch)
    leidos, fijadas = _modo_datos(monkeypatch, _TODOS_DATOS)
    assert onedrive.main(["--datos"]) == 0
    out = capsys.readouterr().out
    assert set(leidos) == _ESENCIALES_ESPERADOS
    assert set(fijadas) == {bases.resolve(), cafci.resolve()}          # Carteras va adentro de Delta Bases
    assert (bases / "bna_fx (1).json").exists()                        # ni basura ni borrado
    assert "Mantener siempre en este dispositivo" in out and "segundo plano" in out
    assert "Delta Bases:" in out and "DELTA_CAFCI_DIR:" in out


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
    assert not leidos and not fijadas and "datos completos" in capsys.readouterr().out
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
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (False, "Acceso denegado"))
    assert onedrive.main(["--carpeta", str(root)]) == 0                 # fijar es best-effort
    out = capsys.readouterr().out
    assert "no pude fijar" in out and "Acceso denegado" in out and "Mantener siempre en este dispositivo" in out
    # attrib devolvió 0 pero la raíz no muestra PINNED (el tmp de Linux nunca lo tiene)
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (True, ""))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    assert "todavía no figura fijada" in out and "carpeta marcada" not in out
    # y con el pin visible, el mensaje normal
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG) if "x" in str(p) else (0, 0))
    estados = iter([(0x10, NUBE_TAG), (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG)])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: next(estados))
    assert onedrive.main(["--carpeta", str(root)]) == 0
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
    fijadas: list[Path] = []
    monkeypatch.setattr(onedrive, "fijar", lambda root, run=None: (fijadas.append(root), (True, ""))[1])
    estados = iter([(0x10, NUBE_TAG), (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG)])
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: next(estados))
    assert onedrive.main(["--carpeta", str(root)]) == 0
    out = capsys.readouterr().out
    # la basura NO se lee (no se baja): sólo lo legítimo
    assert sorted(leidos) == ["pizarra-DAM-NB-CIO.json", "pizarra.json", "riesgo_pais.json.88.tmp"]
    quedan = sorted(p.name for p in (root / "data").iterdir())
    assert quedan == ["pizarra-DAM-NB-CIO.json", "pizarra.json", "riesgo_pais.json.88.tmp"]
    assert (root / "bcra_data_backup.json").exists() and not (root / "bcra_data_backup-DAM-NB-CIO.json").exists()
    assert "borré 6 restos" in out and "market_snapshot.json 4" in out and "sin bajarlos" in out
    assert "%LOCALAPPDATA%\\bonos" in out and fijadas == [root]
    # segundo arranque: nada que borrar, nada que decir de eso
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(set()))
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (onedrive.FILE_ATTRIBUTE_PINNED | 0x10, NUBE_TAG))
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
