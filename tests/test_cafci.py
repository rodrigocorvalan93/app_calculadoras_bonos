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


def test_autodiscovery_layout_real(tmp_path) -> None:
    """Layout real del equipo: 'Equipo RF\\Precios Cafci' es una rama VECINA de
    'Delta Bases' (un nivel más abajo), no una subcarpeta. Discovery depth-2 la
    encuentra desde DELTA_HISTORICO_DIR sin setear DELTA_CAFCI_*."""
    saved = {k: os.environ.get(k) for k in _CAFCI_ENV}
    for k in _CAFCI_ENV:
        os.environ.pop(k, None)
    try:
        docs = tmp_path / "Inversiones - Documentos"
        (docs / "Delta Bases" / "Carteras").mkdir(parents=True)
        (docs / "Codes" / "app").mkdir(parents=True)              # ruido
        cafci_dir = docs / "Equipo RF" / "Precios Cafci"
        cafci_dir.mkdir(parents=True)
        (cafci_dir / "20260608.xlsx").write_bytes(b"")
        # Igual que el secrets.txt real: histórico apunta a 'Delta Bases'.
        os.environ["DELTA_HISTORICO_DIR"] = str(docs / "Delta Bases")
        got = cafci._resolve_path()
        assert got == str(cafci_dir / "20260608.xlsx")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _write_cafci_xlsx(path, *, valid: bool) -> None:
    """Escribe un .xlsx tipo CAFCI (hojas fx…/vector… con datos) si valid, o
    una planilla cualquiera (sin esas hojas) si no."""
    pd = pytest.importorskip("pandas")
    with pd.ExcelWriter(path) as xw:
        if valid:
            pd.DataFrame([["USD", 1520.0], ["USB", 1466.0]]).to_excel(
                xw, sheet_name="fx20260608", header=False, index=False)
            pd.DataFrame([{"ISIN": "ARP1", "BYMA": "AL30", "CAFCI": "1", "Valuación": "ARS",
                           "Cdo.": 941.3, "TIR [%]": 7.23, "TNA [%]": 7.49,
                           "Mod. Duration": 1.9}]).to_excel(
                xw, sheet_name="vector20260608", index=False)
        else:
            pd.DataFrame([{"Concepto": "x", "Valor": 1}]).to_excel(
                xw, sheet_name="Resumen", index=False)


def test_prefiere_canonico_sobre_planilla(tmp_path) -> None:
    """Carpeta con el vector real ('20260608.xlsx') y una planilla con la misma
    fecha ('20260608_Planilla_Diaria.xlsx'): carga el vector, no la planilla."""
    saved = {k: os.environ.get(k) for k in _CAFCI_ENV}
    saved_cache = cafci._cache
    for k in _CAFCI_ENV:
        os.environ.pop(k, None)
    try:
        _write_cafci_xlsx(tmp_path / "20260608.xlsx", valid=True)
        _write_cafci_xlsx(tmp_path / "20260608_Planilla_Diaria.xlsx", valid=False)
        os.environ["DELTA_CAFCI_DIR"] = str(tmp_path)
        c = cafci.refresh()
        assert c["loaded"] and c["n"] == 1
        assert os.path.basename(c["path"]) == "20260608.xlsx"
    finally:
        cafci._cache = saved_cache
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_saltea_archivo_sin_hojas_cafci(tmp_path) -> None:
    """Si el candidato de mayor prioridad NO es un vector CAFCI, prueba el
    siguiente. Acá el canónico '20260608.xlsx' es una planilla y el válido está
    decorado → igual lo encuentra."""
    saved = {k: os.environ.get(k) for k in _CAFCI_ENV}
    saved_cache = cafci._cache
    for k in _CAFCI_ENV:
        os.environ.pop(k, None)
    try:
        _write_cafci_xlsx(tmp_path / "20260608.xlsx", valid=False)            # canónico pero NO cafci
        _write_cafci_xlsx(tmp_path / "20260608_vector_cafci.xlsx", valid=True)
        os.environ["DELTA_CAFCI_DIR"] = str(tmp_path)
        c = cafci.refresh()
        assert c["loaded"] and c["n"] == 1
        assert os.path.basename(c["path"]) == "20260608_vector_cafci.xlsx"
    finally:
        cafci._cache = saved_cache
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
