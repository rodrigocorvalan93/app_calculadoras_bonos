"""`backend.tools.repo_sano` (12/11): el clon vuelve a ser el repo al arrancar.

Dos PCs del desk arrancaron con un `especies.py` que OneDrive dejó a medias
(NameError: S13N6) y una copia en conflicto `especies-DAM-NB-RC.py` al lado:
la app quedó sin universo. Los tests arman un repo git REAL en tmp (git está
en los tres runners de CI) y corren la herramienta contra él."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from backend.tools import repo_sano as rs

ROOT = Path(__file__).resolve().parents[1]

ESPECIES_OK = '''import rentafija

S13N6 = {"Código": "S13N6", "Vencimiento": "13/11/2026"}
TX28 = {"Código": "TX28", "Vencimiento": "09/11/2028"}
S13N6 = rentafija.Bono(S13N6)
TX28 = rentafija.Bono(TX28)
BONOS = [S13N6, TX28]
'''
ESPECIES_ROTO = ESPECIES_OK.replace('S13N6 = {"Código": "S13N6", "Vencimiento": "13/11/2026"}\n', "")


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return r.stdout


@pytest.fixture
def clon(tmp_path: Path, monkeypatch) -> Path:
    """Un clon chico: especies.py, rentafija.py, un .bat, bcra_data_backup.json
    y una carpeta backend/, todo commiteado en la rama `trabajo`."""
    root = tmp_path / "clon"
    (root / "backend").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "trabajo")
    (root / "especies.py").write_text(ESPECIES_OK, encoding="utf-8")
    (root / "rentafija.py").write_text("class Bono:\n    pass\n", encoding="utf-8")
    (root / "run_backend (CORRER APP).bat").write_text("@echo off\r\n", encoding="utf-8")
    (root / "bcra_data_backup.json").write_text("{}", encoding="utf-8")
    (root / "backend" / "main.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "inicial")
    monkeypatch.setenv("BONOS_LOCAL_DIR", str(tmp_path / "local"))
    monkeypatch.delenv("REPO_SANO", raising=False)
    monkeypatch.delenv("REPO_AUTOPULL", raising=False)
    monkeypatch.setenv("SECRETS_FILE", str(tmp_path / "secrets-vacio.txt"))
    (tmp_path / "secrets-vacio.txt").write_text("", encoding="utf-8")
    return root


def test_chequear_especies_detecta_lo_que_rompe_el_import(tmp_path: Path) -> None:
    p = tmp_path / "especies.py"
    p.write_text(ESPECIES_OK, encoding="utf-8")
    assert rs.chequear_especies(p) == []
    p.write_text(ESPECIES_ROTO, encoding="utf-8")
    probs = rs.chequear_especies(p)
    assert len(probs) == 1 and "rentafija.Bono(S13N6) sin la ficha S13N6" in probs[0] and "línea 4" in probs[0]
    p.write_text(ESPECIES_OK + "OTRA = [S13N6, NOEXISTE]\n", encoding="utf-8")
    assert rs.chequear_especies(p) == ["línea 8: NOEXISTE en la lista no está definido"]
    p.write_text("S13N6 = {\n", encoding="utf-8")
    assert rs.chequear_especies(p)[0].startswith("sintaxis:")
    # el especies.py de verdad del repo está sano (es lo que importa la app)
    assert rs.chequear_especies(ROOT / "especies.py") == []


def test_restaura_lo_versionado_salvo_especies_y_lo_que_escribe_la_app(clon: Path, capsys) -> None:
    (clon / "rentafija.py").write_text("class Bono:\n    roto\n", encoding="utf-8")     # OneDrive a medias
    (clon / "backend" / "main.py").unlink()                                             # faltante
    (clon / "bcra_data_backup.json").write_text('{"a3500": 1}', encoding="utf-8")       # la app lo reescribe
    (clon / "especies.py").write_text(ESPECIES_OK + "NUEVO = {}\n", encoding="utf-8")    # ficha a mano, sano
    (clon / "secrets.txt").write_text("clave", encoding="utf-8")                        # no versionado
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert (clon / "rentafija.py").read_text(encoding="utf-8") == "class Bono:\n    pass\n"
    assert (clon / "backend" / "main.py").exists()
    assert (clon / "bcra_data_backup.json").read_text(encoding="utf-8") == '{"a3500": 1}'
    assert (clon / "especies.py").read_text(encoding="utf-8").endswith("NUEVO = {}\n")
    assert (clon / "secrets.txt").exists()
    assert "2 archivo(s) del código volvieron a ser los del repo (rama trabajo)" in out
    assert "rentafija.py" in out and "backend/main.py" in out
    assert "especies.py tiene cambios locales: se respeta" in out and "especies.py sano" in out
    # segundo arranque: nada que decir del código
    assert rs.main(["--carpeta", str(clon)]) == 0
    assert "volvieron" not in capsys.readouterr().out


def test_especies_roto_sale_4_y_restaurar_guarda_copia(clon: Path, tmp_path: Path, capsys) -> None:
    (clon / "especies.py").write_text(ESPECIES_ROTO, encoding="utf-8")
    assert rs.main(["--carpeta", str(clon)]) == rs.EXIT_ESPECIES_ROTO == 4
    out = capsys.readouterr().out
    assert "especies.py de esta PC está ROTO" in out and "Bono(S13N6) sin la ficha" in out
    assert "--restaurar-especies" in out and "difiere del repo" in out
    assert (clon / "especies.py").read_text(encoding="utf-8") == ESPECIES_ROTO    # no se restaura solo
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 0
    out = capsys.readouterr().out
    assert (clon / "especies.py").read_text(encoding="utf-8") == ESPECIES_OK
    guardados = list((tmp_path / "local" / "conflictos").glob("especies-roto-*.py"))
    assert len(guardados) == 1 and guardados[0].read_text(encoding="utf-8") == ESPECIES_ROTO
    assert "quedó guardado" in out and "restaurado desde el repo" in out
    # ya restaurado: nada que hacer
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 0
    assert "ya es el del repo" in capsys.readouterr().out


def test_especies_roto_en_el_repo_no_se_puede_restaurar(clon: Path, capsys) -> None:
    (clon / "especies.py").write_text(ESPECIES_ROTO, encoding="utf-8")
    _git(clon, "commit", "-qam", "roto en el repo")
    assert rs.main(["--carpeta", str(clon)]) == 4
    assert "es el del repo: hay que corregirlo en git" in capsys.readouterr().out


def test_copias_en_conflicto_de_onedrive(clon: Path, capsys) -> None:
    """`especies-DAM-NB-RC.py` idéntica al repo se borra; una con contenido
    distinto se deja y se avisa (puede tener fichas de otra PC); `--listar`
    no borra nada."""
    (clon / "especies-DAM-NB-RC.py").write_text(ESPECIES_OK, encoding="utf-8")
    (clon / "rentafija (conflicted copy 2026-11-12).py").write_text("class Bono:\n    otra\n", encoding="utf-8")
    (clon / "rentafija-PC2.py").write_text("class Bono:\n    pass\n", encoding="utf-8")
    (clon / "suelto-PC.py").write_text("x", encoding="utf-8")                           # sin original versionado
    assert rs.main(["--carpeta", str(clon), "--listar"]) == 0
    out = capsys.readouterr().out
    assert (clon / "especies-DAM-NB-RC.py").exists() and "se borra al arrancar" in out
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert not (clon / "especies-DAM-NB-RC.py").exists() and not (clon / "rentafija-PC2.py").exists()
    assert (clon / "rentafija (conflicted copy 2026-11-12).py").exists() and (clon / "suelto-PC.py").exists()
    assert "borré especies-DAM-NB-RC.py" in out and "idéntica a especies.py" in out
    assert "rentafija (conflicted copy 2026-11-12).py: copia en conflicto de OneDrive de rentafija.py con contenido DISTINTO" in out
    assert "suelto-PC.py" not in out


def test_listar_no_toca_nada(clon: Path, capsys) -> None:
    (clon / "rentafija.py").write_text("roto", encoding="utf-8")
    assert rs.main(["--carpeta", str(clon), "--listar"]) == 0
    assert (clon / "rentafija.py").read_text(encoding="utf-8") == "roto"
    assert "1 archivo(s) versionados difieren del repo" in capsys.readouterr().out


def test_sin_git_o_apagado_silencio(tmp_path: Path, clon: Path, monkeypatch, capsys) -> None:
    sin = tmp_path / "sin-git"
    sin.mkdir()
    assert rs.main(["--carpeta", str(sin)]) == 0 and capsys.readouterr().out == ""
    (clon / "rentafija.py").write_text("roto", encoding="utf-8")
    monkeypatch.setenv("REPO_SANO", "0")
    assert rs.main(["--carpeta", str(clon)]) == 0 and capsys.readouterr().out == ""
    assert (clon / "rentafija.py").read_text(encoding="utf-8") == "roto"
    monkeypatch.delenv("REPO_SANO")
    # git que no contesta: silencio y 0, nunca frena la app
    monkeypatch.setattr(rs, "git_disponible", lambda root: True)
    monkeypatch.setattr(rs, "_git", lambda *a, **k: (-1, b"", "FileNotFoundError: git"))
    assert rs.main(["--carpeta", str(clon)]) == 0
    assert "git status falló" in capsys.readouterr().out
    # una excepción propia tampoco
    monkeypatch.setattr(rs, "estado", lambda root: (_ for _ in ()).throw(RuntimeError("boom")))
    assert rs.main(["--carpeta", str(clon)]) == 0
    assert "sigo igual" in capsys.readouterr().out


def test_autopull_solo_fast_forward_y_sin_especies_tocado(clon: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    remoto = tmp_path / "remoto.git"
    _git(clon, "clone", "-q", "--bare", str(clon), str(remoto))
    _git(clon, "remote", "add", "origin", str(remoto))
    # el remoto avanza
    otro = tmp_path / "otro"
    _git(clon, "clone", "-q", str(remoto), str(otro))
    (otro / "backend" / "main.py").write_text("x = 2\n", encoding="utf-8")
    _git(otro, "commit", "-qam", "avanza")
    _git(otro, "push", "-q", "origin", "trabajo")
    monkeypatch.setenv("REPO_AUTOPULL", "1")
    assert rs.main(["--carpeta", str(clon)]) == 0
    assert "rama trabajo al día con origin" in capsys.readouterr().out
    assert (clon / "backend" / "main.py").read_text(encoding="utf-8") == "x = 2\n"
    # con especies.py editado a mano no se trae nada
    (clon / "especies.py").write_text(ESPECIES_OK + "NUEVO = {}\n", encoding="utf-8")
    (otro / "backend" / "main.py").write_text("x = 3\n", encoding="utf-8")
    _git(otro, "commit", "-qam", "avanza 2")
    _git(otro, "push", "-q", "origin", "trabajo")
    assert rs.main(["--carpeta", str(clon)]) == 0
    assert "no traigo la rama" in capsys.readouterr().out
    assert (clon / "backend" / "main.py").read_text(encoding="utf-8") == "x = 2\n"
    # divergente: aviso, nunca reset
    (clon / "especies.py").write_text(ESPECIES_OK, encoding="utf-8")
    (clon / "rentafija.py").write_text("class Bono:\n    pass\n# local\n", encoding="utf-8")
    _git(clon, "commit", "-qam", "local")
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert "no avanza en fast-forward" in out and "git reset --keep origin/trabajo" in out


def test_el_bat_corre_repo_sano_y_pregunta_antes_de_restaurar_especies() -> None:
    """El paso va DESPUÉS del pre-flight de OneDrive del código (los archivos
    ya están bajados) y ANTES del de datos / pip; con errorlevel 4 pregunta
    (choice, default N a los 60 s) y recién con S restaura."""
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    i_one, i_repo = bat.index("backend.tools.onedrive\n"), bat.index("backend.tools.repo_sano\n")
    assert i_one < i_repo < bat.index("backend.tools.onedrive --datos") < bat.index("pip install -r")
    bloque = bat[i_repo:bat.index("backend.tools.onedrive --datos")]
    assert "if errorlevel 4 if not errorlevel 5 (" in bloque
    assert "choice /C SN /N /T 60 /D N" in bloque and "repo_sano --restaurar-especies" in bloque
    assert bloque.index("choice") < bloque.index("--restaurar-especies")
    bf = (ROOT / "backfill_historico.bat").read_text(encoding="utf-8")
    assert "backend.tools.repo_sano --quiet" in bf and bf.isascii()


# ── Revisión adversarial 12/11 ───────────────────────────────────────────────
def test_el_lanzador_que_corre_el_paso_no_se_restaura(clon: Path, capsys) -> None:
    """cmd.exe relee el .bat que está ejecutando por offset de bytes: si
    `git checkout` lo reemplaza a mitad del arranque, el resto corre basura.
    Se avisa y se deja; `--listar` tampoco lo cuenta entre los restaurables."""
    bat = clon / "run_backend (CORRER APP).bat"
    bat.write_bytes(b"@echo off\r\nREM distinto\r\n")          # bytes: en Windows write_text dobla el \r
    (clon / "rentafija.py").write_text("roto", encoding="utf-8")
    assert rs.main(["--carpeta", str(clon), "--listar"]) == 0
    out = capsys.readouterr().out
    assert "1 archivo(s) versionados difieren" in out and "rentafija.py" in out
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert bat.read_bytes() == b"@echo off\r\nREM distinto\r\n"
    assert (clon / "rentafija.py").read_text(encoding="utf-8") == "class Bono:\n    pass\n"
    assert "run_backend (CORRER APP).bat difiere del repo: no se toca mientras corre" in out
    assert rs.es_lanzador("backfill_historico.bat") and rs.es_lanzador("correr_app.command")
    assert not rs.es_lanzador("deploy/instalar.bat") and not rs.es_lanzador("rentafija.py")


def test_restaurar_rechequea_y_el_del_repo_roto_sale_4(clon: Path, capsys) -> None:
    (clon / "especies.py").write_text(ESPECIES_ROTO, encoding="utf-8")
    _git(clon, "commit", "-qam", "roto en el repo")
    (clon / "especies.py").write_text(ESPECIES_ROTO + "# local\n", encoding="utf-8")
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == rs.EXIT_ESPECIES_ROTO
    out = capsys.readouterr().out
    assert "restaurado desde el repo" in out and "el especies.py del repo también está ROTO" in out
    assert (clon / "especies.py").read_text(encoding="utf-8") == ESPECIES_ROTO


def test_restaurar_que_no_pudo_sale_1_nunca_0(clon: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    """En modo --restaurar-especies el .bat espera el resultado: una
    excepción propia, un git status caído o una copia que no se pudo guardar
    devuelven 1 (el .bat avisa), no el 0 'sigo igual' del chequeo."""
    (clon / "especies.py").write_text(ESPECIES_ROTO, encoding="utf-8")
    (tmp_path / "archivo-no-carpeta").write_text("x", encoding="utf-8")
    monkeypatch.setenv("BONOS_LOCAL_DIR", str(tmp_path / "archivo-no-carpeta"))
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 1
    out = capsys.readouterr().out
    assert "no pude guardar la copia" in out and "no lo toco" in out
    assert (clon / "especies.py").read_text(encoding="utf-8") == ESPECIES_ROTO
    monkeypatch.setattr(rs, "estado", lambda root: (_ for _ in ()).throw(RuntimeError("boom")))
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 1
    assert "no pude restaurar especies.py (RuntimeError: boom)" in capsys.readouterr().out
    monkeypatch.setattr(rs, "estado", lambda root: rs.Estado(error="git caído"))
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 1
    assert "no puedo restaurar especies.py" in capsys.readouterr().out
    assert rs.main(["--carpeta", str(clon)]) == 0                       # el chequeo normal sigue igual


def test_especies_faltante_sale_4_y_se_repone(clon: Path, capsys) -> None:
    (clon / "especies.py").unlink()
    assert rs.main(["--carpeta", str(clon)]) == rs.EXIT_ESPECIES_ROTO
    out = capsys.readouterr().out
    assert "especies.py FALTA en esta PC" in out and "--restaurar-especies" in out
    assert rs.main(["--carpeta", str(clon), "--restaurar-especies"]) == 0
    assert (clon / "especies.py").read_text(encoding="utf-8") == ESPECIES_OK


def test_chequear_especies_lee_bytes_bom_y_cortado(tmp_path: Path) -> None:
    p = tmp_path / "especies.py"
    p.write_bytes(b"\xef\xbb\xbf" + ESPECIES_OK.encode("utf-8"))               # BOM: el import lo acepta
    assert rs.chequear_especies(p) == []
    p.write_bytes(b'import rentafija\nX = {"C\xc3')                             # cortado a mitad de un carácter
    probs = rs.chequear_especies(p)
    assert len(probs) == 1 and probs[0].startswith("sintaxis:")
    p.write_bytes(b"import rentafija\nX = 1\x00\n")                             # bytes nulos
    assert rs.chequear_especies(p)[0].startswith("sintaxis:")


def test_chequear_especies_junta_nombres_como_el_import(tmp_path: Path) -> None:
    """Fichas definidas adentro de un if / try / for, por tupla, con walrus o
    traídas por `from utils import *` (módulo hermano) NO son falsos
    positivos; un `import *` que no se puede resolver no acusa a nadie."""
    p = tmp_path / "especies.py"
    (tmp_path / "utils.py").write_text("import os\nDEL_UTILS = {}\n_privado = {}\ndef f():\n    pass\n",
                                       encoding="utf-8")
    p.write_text('''from utils import *
import rentafija
if True:
    EN_IF = {}
try:
    EN_TRY = {}
except Exception:
    EN_EXC = {}
for N in [1]:
    pass
A, B = {}, {}
C: dict = {}
if (W := {}):
    pass
with open(__file__) as FH:
    pass
EN_IF = rentafija.Bono(EN_IF)
EN_TRY = rentafija.Bono(EN_TRY)
EN_EXC = rentafija.Bono(EN_EXC)
A = rentafija.Bono(A)
B = rentafija.Bono(B)
C = rentafija.Bono(C)
W = rentafija.Bono(W)
DEL_UTILS = rentafija.Bono(DEL_UTILS)
LISTA = [EN_IF, A, B, C, W, N, FH, DEL_UTILS, f, os]
MAL = rentafija.Bono(_privado)
''', encoding="utf-8")
    assert rs.chequear_especies(p) == ["línea 26: rentafija.Bono(_privado) sin la ficha _privado definida antes"]
    p.write_text("from noexiste import *\nimport rentafija\nX = rentafija.Bono(X)\nL = [X, Y]\n", encoding="utf-8")
    assert rs.chequear_especies(p) == []                                        # no se sabe qué trae


def test_lo_staged_sin_commit_no_aborta_el_checkout(clon: Path, capsys) -> None:
    (clon / "rentafija.py").write_text("roto", encoding="utf-8")
    (clon / "nuevo.py").write_text("n = 1\n", encoding="utf-8")
    _git(clon, "add", "nuevo.py")
    _git(clon, "mv", "backend/main.py", "backend/main2.py")
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert (clon / "rentafija.py").read_text(encoding="utf-8") == "class Bono:\n    pass\n"
    assert (clon / "nuevo.py").exists() and (clon / "backend" / "main2.py").exists()
    assert "1 archivo(s) del código volvieron" in out and "no pude restaurar" not in out


def test_autopull_repone_lo_que_la_app_escribe_si_el_pull_lo_trae(clon: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    remoto = tmp_path / "remoto.git"
    _git(clon, "clone", "-q", "--bare", str(clon), str(remoto))
    _git(clon, "remote", "add", "origin", str(remoto))
    otro = tmp_path / "otro"
    _git(clon, "clone", "-q", str(remoto), str(otro))
    (otro / "bcra_data_backup.json").write_text('{"a3500": 2}', encoding="utf-8")
    _git(otro, "commit", "-qam", "backup nuevo")
    _git(otro, "push", "-q", "origin", "trabajo")
    (clon / "bcra_data_backup.json").write_text('{"a3500": 1}', encoding="utf-8")   # la app lo reescribió
    monkeypatch.setenv("REPO_AUTOPULL", "1")
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert "bcra_data_backup.json repuesto del repo" in out and "rama trabajo al día con origin" in out
    assert (clon / "bcra_data_backup.json").read_text(encoding="utf-8") == '{"a3500": 2}'


def test_copia_que_no_se_pudo_comparar_se_deja_con_aviso(clon: Path, monkeypatch, capsys) -> None:
    (clon / "especies-DAM-NB-RC.py").write_text(ESPECIES_OK, encoding="utf-8")
    git_real = rs._git

    def git_sin_hash(root, *args, **kw):
        if args and args[0] == "hash-object":
            return -1, b"", "TimeoutExpired"
        return git_real(root, *args, **kw)

    monkeypatch.setattr(rs, "_git", git_sin_hash)
    assert rs.main(["--carpeta", str(clon)]) == 0
    out = capsys.readouterr().out
    assert (clon / "especies-DAM-NB-RC.py").exists()
    assert "no pude compararla" in out and "DISTINTO" not in out


def test_el_bat_solo_restaura_con_la_s() -> None:
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    bloque = bat[bat.index("choice /C SN"):bat.index("--restaurar-especies")]
    assert "if not errorlevel 1 (" in bloque and "if errorlevel 2 (" in bloque
    assert bloque.index("if not errorlevel 1") < bloque.index("if errorlevel 2")
    assert bloque.count("exit /b 4") == 2
