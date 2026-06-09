"""CAFCI — búsqueda server-side y endpoints (cache sintético; el Excel no está en CI)."""
from __future__ import annotations

import os

import pytest

from backend.services import cafci

_FAKE = {
    "loaded": True, "error": None, "path": "x", "fecha": "20260605",
    "fx": {"USD": 1515.71, "USB": 1458.69},
    "rows": [
        {"isin": "ARP1", "byma": "AL30", "cafci": "123", "moneda": "USD", "cdo": 70.5,
         "var_cdo": 0.5, "mod_dur": 3.2, "tir": 6.97, "tna": 6.5, "spread": 3.1, "zspread": 2.9,
         "_key": "arp1 al30 123"},
        {"isin": "ARP2", "byma": "GD30", "cafci": "456", "moneda": "USD", "cdo": 71.0,
         "var_cdo": -0.2, "mod_dur": 3.5, "tir": 7.1, "tna": 6.6, "spread": 3.0, "zspread": None,
         "_key": "arp2 gd30 456"},
    ],
    "n": 2,
}


_CAFCI_ENV = ("DELTA_CAFCI_PATH", "DELTA_CAFCI_DIR", "DELTA_BASES_DIR",
              "DELTA_HISTORICO_DIR", "DELTA_HISTORICO_PATH", "DELTA_ESPECIES_PATH")


def test_resolve_dir_tolera_nombres(tmp_path) -> None:
    """DELTA_CAFCI_DIR toma el .xlsx con la fecha más nueva, sin importar el
    nombrado, e ignora lock files ~$ y archivos no-excel."""
    saved = {k: os.environ.get(k) for k in _CAFCI_ENV}
    for k in _CAFCI_ENV:
        os.environ.pop(k, None)
    try:
        d = tmp_path / "Precios Cafci"
        d.mkdir()
        for fn in ("20260603.xlsx", "CAFCI 20260605.xlsx", "vector_20260604.xlsx",
                   "~$20260605.xlsx", "notas.txt"):
            (d / fn).write_bytes(b"")
        os.environ["DELTA_CAFCI_DIR"] = str(d)
        got = cafci._resolve_path()
        assert got and os.path.basename(got) == "CAFCI 20260605.xlsx"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_autodiscovery_junto_a_bases_delta(tmp_path) -> None:
    """Sin DELTA_CAFCI_*: descubre 'Precios Cafci' vecina de DELTA_BASES_DIR."""
    saved = {k: os.environ.get(k) for k in _CAFCI_ENV}
    for k in _CAFCI_ENV:
        os.environ.pop(k, None)
    try:
        equipo = tmp_path / "Equipo RF"
        (equipo / "Carteras").mkdir(parents=True)
        cafci_dir = equipo / "Precios Cafci"
        cafci_dir.mkdir()
        (cafci_dir / "20260605.xlsx").write_bytes(b"")
        # Sólo está configurado Carteras (DELTA_BASES_DIR); CAFCI es hermana.
        os.environ["DELTA_BASES_DIR"] = str(equipo / "Carteras")
        got = cafci._resolve_path()
        assert got == str(cafci_dir / "20260605.xlsx")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_search() -> None:
    saved = cafci._cache
    cafci._cache = dict(_FAKE)
    try:
        rows, total = cafci.search("al30")
        assert total == 1 and rows[0]["byma"] == "AL30"
        assert cafci.search("")[1] == 2                  # sin query → todo
        assert cafci.search("ARP2")[1] == 1              # por ISIN
        assert cafci.search("xyz")[1] == 0
        rows, _ = cafci.search("a", limit=1)
        assert len(rows) == 1                            # respeta el tope
    finally:
        cafci._cache = saved


@pytest.mark.asyncio
async def test_cafci_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    saved = cafci._cache
    cafci._cache = dict(_FAKE)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            p = await ac.get("/cafci")
            t = await ac.get("/cafci/table?q=al30")
        assert p.status_code == 200 and "CAFCI" in p.text
        assert t.status_code == 200 and "AL30" in t.text
    finally:
        cafci._cache = saved
