"""Rutas Delta multiplataforma: el secrets.txt escrito para Windows tiene que
resolver en macOS sin editarlo, mapeando a la carpeta OneDrive local:

  Windows: ~\\DELTA ASSET MANAGEMENT S.A\\Inversiones - Documentos\\Delta Bases\\Carteras
  macOS:   ~/Library/CloudStorage/OneDrive-SharedLibraries-DELTAASSETMANAGEMENTS.A/
           Inversiones - Documentos/Delta Bases/Carteras

Y en Windows nada cambia: si la expansión directa existe, se usa tal cual.
"""
from __future__ import annotations

import os

import pytest

from backend.services import deltapaths

# Los strings EXACTOS del secrets.txt del equipo (estilo Windows).
_WIN_BASES = r"~\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Delta Bases\Carteras"
_WIN_HISTORICO = r"~\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Delta Bases"
_WIN_CAFCI = r"%USERPROFILE%\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Equipo RF\Precios Cafci"

_TENANT_DIR = "OneDrive-SharedLibraries-DELTAASSETMANAGEMENTS.A"


@pytest.fixture()
def mac_home(tmp_path, monkeypatch):
    """HOME apuntando a un layout estilo macOS con el OneDrive del equipo."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    for var in ("DELTA_BASES_DIR", "DELTA_HISTORICO_DIR", "DELTA_HISTORICO_PATH",
                "DELTA_CAFCI_DIR", "DELTA_CAFCI_PATH", "DELTA_COMPOSICION_PATH",
                "DELTA_PN_PATH", "DELTA_FONDOS_PATH", "DELTA_ESPECIES_PATH"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "Library" / "CloudStorage" / _TENANT_DIR / "Inversiones - Documentos"
    (root / "Delta Bases" / "Carteras").mkdir(parents=True)
    (root / "Equipo RF" / "Precios Cafci").mkdir(parents=True)
    return tmp_path


def test_bases_dir_windows_style_resolves_on_mac(mac_home) -> None:
    got = deltapaths.expand(_WIN_BASES, want="dir")
    assert got is not None and os.path.isdir(got)
    assert got.endswith(os.path.join("Inversiones - Documentos", "Delta Bases", "Carteras"))
    assert _TENANT_DIR in got


def test_userprofile_style_resolves_on_mac(mac_home) -> None:
    got = deltapaths.expand(_WIN_CAFCI, want="dir")
    assert got is not None and os.path.isdir(got)
    assert got.endswith(os.path.join("Equipo RF", "Precios Cafci"))


def test_direct_existing_path_wins_without_scanning(mac_home, tmp_path) -> None:
    # Una ruta que YA existe (caso Windows / posix bien configurado) vuelve
    # tal cual — el remapeo OneDrive ni se intenta.
    plain = tmp_path / "carpeta local"
    plain.mkdir()
    assert deltapaths.expand(str(plain), want="dir") == str(plain)


def test_unresolvable_path_returns_direct_expansion(mac_home) -> None:
    # Sin match: devuelve la expansión directa (no None) para que el caller
    # falle con su chequeo/mensaje de siempre.
    got = deltapaths.expand(r"~\Otra Empresa\No Existe\Nada", want="dir")
    assert got is not None
    assert not os.path.isdir(got)


def test_positions_finds_composicion_via_onedrive(mac_home, monkeypatch) -> None:
    # End-to-end del caso real: DELTA_BASES_DIR estilo Windows en la env y
    # Delta_Composicion.xlsx viviendo en el OneDrive de la Mac.
    from backend.services import positions

    carteras = (mac_home / "Library" / "CloudStorage" / _TENANT_DIR /
                "Inversiones - Documentos" / "Delta Bases" / "Carteras")
    (carteras / "Delta_Composicion.xlsx").write_bytes(b"stub")
    monkeypatch.setenv("DELTA_BASES_DIR", _WIN_BASES)
    got = positions._resolve("Delta_Composicion.xlsx", "DELTA_COMPOSICION_PATH")
    assert got == str(carteras / "Delta_Composicion.xlsx")


def test_historico_dir_resolves_on_mac(mac_home, monkeypatch) -> None:
    # Destino de guardado de bymaapi.py: DELTA_HISTORICO_DIR estilo Windows
    # remapea a la carpeta 'Delta Bases' del OneDrive local.
    monkeypatch.setenv("DELTA_HISTORICO_DIR", _WIN_HISTORICO)
    got = deltapaths.historico_dir()
    assert got is not None and os.path.isdir(got)
    assert got.endswith(os.path.join("Inversiones - Documentos", "Delta Bases"))
    assert _TENANT_DIR in got


def test_historico_dir_falls_back_to_bases_parent(mac_home, monkeypatch) -> None:
    # Sólo DELTA_BASES_DIR (Carteras) configurada → el padre remapeado.
    monkeypatch.setenv("DELTA_BASES_DIR", _WIN_BASES)
    got = deltapaths.historico_dir()
    assert got is not None
    assert got.endswith(os.path.join("Inversiones - Documentos", "Delta Bases"))


def test_historico_dir_none_without_env(mac_home) -> None:
    assert deltapaths.historico_dir() is None


def test_historico_derives_parent_from_remapped_bases(mac_home, monkeypatch) -> None:
    # DELTA_BASES_DIR (Carteras) remapeada → el histórico se busca en el padre
    # remapeado (Delta Bases), igual que en Windows.
    from backend.services import historico_byma

    bases = (mac_home / "Library" / "CloudStorage" / _TENANT_DIR /
             "Inversiones - Documentos" / "Delta Bases")
    (bases / "Delta - historico_byma_px_tasas.xlsx").write_bytes(b"stub")
    monkeypatch.setenv("DELTA_BASES_DIR", _WIN_BASES)
    got = historico_byma._resolve_path()
    assert got == str(bases / "Delta - historico_byma_px_tasas.xlsx")
