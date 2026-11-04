"""Marcadores de OneDrive en los DATOS (04/11): `services.nube`, el writer
que NO aparta como `.corrupto-` un archivo que es marcador sin bajar, el
warning único de CAFCI y `services.datos_nube` (chequeo del arranque,
tarjeta de /admin y recarga sola cuando OneDrive baja lo esencial).

Los atributos de Windows no existen en Linux / macOS: se parchea la
plataforma y los stats / atributos para ejercitar esa rama en cualquier
runner (mismo patrón que tests/test_onedrive.py)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services import nube
from backend.tools import onedrive

NUBE_TAG = 0x9000601A
RECALL = nube.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | 0x20


# ── nube ─────────────────────────────────────────────────────────────────────
def test_nube_fuera_de_windows_todo_false(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(nube, "_PLATFORM", "linux")           # el runner de CI puede ser Windows de verdad
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    assert nube.es_marcador(str(f)) is False
    assert nube.es_error_de_nube(OSError(22, "Invalid argument")) is False
    assert nube.ilegible_por_nube(str(f), OSError(22, "Invalid argument")) is False


def test_nube_en_windows_detecta_marcador_y_errores(tmp_path, monkeypatch) -> None:
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    monkeypatch.setattr(nube, "_PLATFORM", "win32")
    assert nube.es_error_de_nube(OSError(22, "Invalid argument"))
    assert nube.es_error_de_nube(OSError("Could not open Parquet input source 'x': Error reading bytes from file"))
    assert not nube.es_error_de_nube(ValueError("zip"))
    assert not nube.es_error_de_nube(OSError(13, "Permission denied"))
    assert nube.ilegible_por_nube(str(f), OSError(22, "Invalid argument"))      # por el error, archivo presente
    assert not nube.ilegible_por_nube(str(tmp_path / "no-existe"), OSError(22, "Invalid argument"))
    monkeypatch.setattr(nube.os, "stat", lambda p: SimpleNamespace(st_file_attributes=RECALL))
    assert nube.es_marcador(str(f)) and nube.ilegible_por_nube(str(f))
    assert "Mantener siempre en este dispositivo" in nube.remedio(str(f)) and "a.xlsx" in nube.remedio(str(f))


# ── writer: un marcador NUNCA se aparta como corrupto ────────────────────────
def _parquet_base(path: Path):
    import pandas as pd
    from datetime import date
    df = pd.DataFrame({"symbol": ["MERV - XMEV - AL30 - 24hs"], "Código": ["AL30"], "Last Price": [70.0],
                       "fecha_hoy": [date(2026, 10, 5)]})
    df.to_parquet(path, index=False)
    return df


def test_apartar_si_corrupto_no_toca_un_marcador(tmp_path, monkeypatch) -> None:
    from backend.services import historico_writer as hw
    xlsx = tmp_path / "Delta - historico_byma_px_tasas.xlsx"
    xlsx.write_bytes(b"no soy un zip")
    monkeypatch.setattr(nube, "es_marcador", lambda p: True)
    hw._apartar_si_corrupto(str(xlsx))
    assert xlsx.exists() and not list(tmp_path.glob("*.corrupto-*"))
    monkeypatch.setattr(nube, "es_marcador", lambda p: False)
    hw._apartar_si_corrupto(str(xlsx))
    assert not xlsx.exists() and list(tmp_path.glob("*.corrupto-*"))        # corrupto de verdad: se aparta


def test_leer_base_con_excel_marcador_no_aparta_ni_sigue_del_espejo(tmp_path, monkeypatch) -> None:
    """Excel ilegible + espejo NO fiel: antes se apartaba el Excel y se seguía
    del parquet (perdiendo lo que el Excel tuviera de más). Si el Excel es un
    marcador de OneDrive: RuntimeError, nada se renombra, no se guarda."""
    import pandas as pd
    from backend.services import historico_writer as hw
    xlsx = tmp_path / "Delta - historico_byma_px_tasas.xlsx"
    pq = tmp_path / "Delta - historico_byma_px_tasas.parquet"
    _parquet_base(pq)
    xlsx.write_bytes(b"marcador")
    os.utime(xlsx, (2_000_000_000, 2_000_000_000))                       # Excel más nuevo: espejo no fiel
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda p, e=None: True)
    with pytest.raises(RuntimeError, match="No guardo"):
        hw._leer_base(str(xlsx), pd)
    assert xlsx.exists() and not list(tmp_path.glob("*.corrupto-*"))
    # corrupto de verdad (no marcador): el camino de siempre — aparta y sigue del espejo
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda p, e=None: False)
    prev = hw._leer_base(str(xlsx), pd)
    assert len(prev) == 1 and not xlsx.exists() and list(tmp_path.glob("*.corrupto-*"))


def test_leer_fx_previo_con_excel_marcador_no_aparta(tmp_path, monkeypatch) -> None:
    import pandas as pd
    from backend.services import historico_writer as hw
    xlsx, pq = tmp_path / "Delta - historico_fx.xlsx", tmp_path / "Delta - historico_fx.parquet"
    pd.DataFrame({"fecha": ["2026-10-05"], "ccl": [1500.0]}).to_parquet(pq, index=False)
    xlsx.write_bytes(b"marcador")
    os.utime(xlsx, (2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda p, e=None: True)
    with pytest.raises(RuntimeError, match="No guardo el historial FX"):
        hw._leer_fx_previo(str(xlsx), str(pq), pd)
    assert xlsx.exists() and not list(tmp_path.glob("*.corrupto-*"))
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda p, e=None: False)
    prev = hw._leer_fx_previo(str(xlsx), str(pq), pd)
    assert len(prev) == 1 and not xlsx.exists()


def test_append_acciones_con_parquet_marcador_no_aparta_ni_pisa(tmp_path, monkeypatch) -> None:
    import pandas as pd
    from backend.services import historico_writer as hw
    pq = tmp_path / "Delta - historico_acciones.parquet"
    pq.write_bytes(b"marcador")
    monkeypatch.setattr(hw.time, "sleep", lambda s: None)
    monkeypatch.setattr(nube, "ilegible_por_nube", lambda p, e=None: True)
    hoy = pd.DataFrame({"fecha_hoy": ["2026-11-04"], "ticker": ["GGAL"], "close": [1.0]})
    with pytest.raises(RuntimeError, match="No guardo las acciones"):
        hw.append_acciones(hoy, str(pq))
    assert pq.read_bytes() == b"marcador" and not list(tmp_path.glob("*.corrupto-*"))


# ── cafci: un warning, no cientos ────────────────────────────────────────────
def test_cafci_un_solo_warning_por_lote_ilegible(tmp_path, monkeypatch, caplog) -> None:
    from backend.services import cafci
    paths = [str(tmp_path / f"2025090{i}.xlsx") for i in (3, 2, 1)]
    for p in paths:
        Path(p).write_bytes(b"x")
    monkeypatch.setattr(cafci, "_resolve_candidates", lambda: paths)

    def rompe(path):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(cafci, "_parse_cafci", rompe)
    monkeypatch.setattr(nube, "_PLATFORM", "linux")           # fuera de Windows: mensaje genérico
    with caplog.at_level(logging.WARNING, logger="backend.services.cafci"):
        caplog.clear()
        out = cafci._load()
    avisos = [r for r in caplog.records if r.name.endswith("cafci")]
    assert len(avisos) == 1 and "3 archivo(s)" in avisos[0].getMessage()
    assert not out["loaded"] and "ninguno tiene las hojas" in out["error"]
    # en Windows, mismo lote = marcadores de OneDrive: lo dice con el remedio
    monkeypatch.setattr(nube, "_PLATFORM", "win32")
    with caplog.at_level(logging.WARNING, logger="backend.services.cafci"):
        caplog.clear()
        out = cafci._load()
    avisos = [r for r in caplog.records if r.name.endswith("cafci")]
    assert len(avisos) == 1 and "sólo en la nube" in avisos[0].getMessage()
    assert "Archivos a petición" in out["error"] and "Mantener siempre" in out["error"]


# ── datos_nube ───────────────────────────────────────────────────────────────
def _atributos_fake(sin_contenido: set[str]):
    def f(entry):
        attrs = RECALL if entry.name in sin_contenido else 0x20
        if entry.is_dir(follow_symlinks=False):
            attrs = onedrive.FILE_ATTRIBUTE_DIRECTORY
        return attrs, NUBE_TAG, entry.stat(follow_symlinks=False).st_size
    return f


def test_datos_nube_fuera_de_windows_inactivo(monkeypatch) -> None:
    from backend.services import datos_nube
    monkeypatch.setattr(onedrive, "_PLATFORM", "darwin")
    assert datos_nube.escanear()["activo"] is False
    assert datos_nube.status()["activo"] is False and "error" not in datos_nube.status()


def test_datos_nube_avisa_una_vez_y_recarga_cuando_bajan(tmp_path, monkeypatch, caplog) -> None:
    from backend.services import datos_nube
    bases = tmp_path / "Delta Bases"
    cart = bases / "Carteras"
    cart.mkdir(parents=True)
    (cart / "Delta_Composicion.xlsx").write_bytes(b"c")
    (cart / "Delta_PN.xlsx").write_bytes(b"p")
    (bases / "cierres").mkdir()
    (bases / "cierres" / "2024-07-04.parquet").write_bytes(b"q")
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(bases))
    monkeypatch.setenv("DELTA_BASES_DIR", str(cart))
    monkeypatch.delenv("DELTA_CAFCI_DIR", raising=False)
    monkeypatch.setattr(onedrive, "_PLATFORM", "win32")
    monkeypatch.setattr(onedrive, "raices_onedrive", lambda: [])
    monkeypatch.setattr(onedrive, "exponer_marcadores", lambda: False)
    monkeypatch.setattr(onedrive, "_atributos_de", lambda p: (0x10, NUBE_TAG))
    sin = {"Delta_Composicion.xlsx", "2024-07-04.parquet"}
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake(sin))
    monkeypatch.setattr(datos_nube.threading.Thread, "start", lambda self: None)   # el vigilante se prueba a mano
    with caplog.at_level(logging.INFO, logger="backend.datos_nube"):
        caplog.clear()
        st = datos_nube.chequear_arranque()
    assert st["activo"] and st["pendientes"] == 2 and st["esenciales"] == 1
    avisos = [r for r in caplog.records if r.name == "backend.datos_nube"]
    assert len(avisos) == 1 and avisos[0].levelno == logging.WARNING
    assert "2 archivos de datos" in avisos[0].getMessage() and "Delta Bases: 2 de 3 (1 esenciales)" in avisos[0].getMessage()
    s = datos_nube.status()
    assert s["esenciales sin bajar"] == 1 and "Delta_Composicion.xlsx" in s["error"] and "SIN fijar" in s["carpetas"]
    # OneDrive bajó la composición (la partición sigue en la nube: no es esencial) → recarga
    llamados: list[str] = []
    monkeypatch.setattr(datos_nube, "_recargas",
                        lambda: [(n, lambda n=n: llamados.append(n)) for n in ("posiciones", "especies", "cafci")])
    monkeypatch.setattr(onedrive, "_atributos", _atributos_fake({"2024-07-04.parquet"}))
    monkeypatch.setattr(datos_nube, "_CADA_S", 0.01)
    datos_nube._vigilar()
    assert llamados == ["posiciones", "especies", "cafci"] and datos_nube._recargado
    assert datos_nube.escanear()["esenciales"] == 0
    assert "error" not in datos_nube.status()
    # kill-switch
    monkeypatch.setenv("DATOS_NUBE", "0")
    assert datos_nube.escanear()["activo"] is False


def test_datos_nube_recargas_reales_son_llamables() -> None:
    """Las recargas apuntan a funciones que existen (delta_especies.refresh no
    tenía ningún caller)."""
    from backend.services import datos_nube
    nombres = [n for n, fn in datos_nube._recargas() if callable(fn)]
    assert nombres == ["posiciones", "especies", "cafci", "historico", "fx", "acciones", "writer"]


@pytest.mark.asyncio
async def test_admin_salud_muestra_la_tarjeta_de_datos_onedrive(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/admin/salud")
    assert r.status_code == 200 and "Archivos de datos (OneDrive)" in r.text
