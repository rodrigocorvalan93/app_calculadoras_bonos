"""Históricos → Series diarias (archivo FX/caución del cierre): servicio con
cache por mtime, Δ contra el último día CON dato, escala del canje, y el
partial con toggle línea/barras + tabla HP estilo Bloomberg."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import fx_hist


@pytest.fixture()
def archivo_fx(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    df = pd.DataFrame({
        "fecha_hoy": [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3),
                      date(2026, 9, 4), date(2026, 9, 7)],
        "ccl": [1470.0, 1475.0, 1480.0, 1478.0, 1481.0],
        "mep": [1460.0, 1466.0, 1471.0, 1470.0, 1472.0],
        "canje": [0.00685, 0.00614, 0.00612, 0.00544, 0.00611],
        "oficial_a3500": [1350.0, 1351.0, 1352.5, 1353.0, 1355.0],
        "ccl_base": ["GD30"] * 5,
        "caucion_plazo_d": [1, 1, None, 3, 1],
        "caucion_tna": [30.0, 31.0, None, 29.5, 31.5],
        "caucion_tna_vwap": [30.2, 31.1, None, 29.8, 31.2],
        "caucion_monto": [3.1e12, 3.3e12, None, 2.8e12, 3.4e12],
        "caucion_usd_plazo_d": [None] * 5,
        "caucion_usd_tna": [None] * 5,
        "caucion_usd_tna_vwap": [None] * 5,
        "caucion_usd_monto": [None] * 5,
    })
    df.to_parquet(tmp_path / "Delta - historico_fx.parquet", index=False)
    fx_hist.refresh()
    yield tmp_path
    fx_hist.refresh()


def test_series_list_solo_columnas_con_dato(archivo_fx) -> None:
    keys = [s["key"] for s in fx_hist.series_list()]
    assert "caucion_tna_vwap" in keys and "ccl" in keys and "canje" in keys
    assert "caucion_usd_tna" not in keys          # columna toda vacía → no se ofrece


def test_series_rows_saltea_dias_sin_dato_y_escala(archivo_fx) -> None:
    d = fx_hist.series_rows("caucion_tna_vwap", 0)
    fechas = [r["fecha"] for r in d["rows"]]
    assert "2026-09-03" not in fechas             # día sin caución no aparece
    r4 = next(r for r in d["rows"] if r["fecha"] == "2026-09-04")
    assert r4["var"] == pytest.approx(29.8 - 31.1)   # Δ contra el ÚLTIMO con dato
    assert r4["plazo"] == 3                          # viernes → quedó registrado el 3D
    canje = fx_hist.series_rows("canje", 0)["rows"][0]
    assert canje["valor"] == pytest.approx(0.685)    # fracción guardada → %
    # ventana: recorta al final pero la Δ de la primera visible sigue siendo real
    corto = fx_hist.series_rows("caucion_tna_vwap", 2)["rows"]
    assert len(corto) == 2 and corto[0]["var"] is not None


@pytest.mark.asyncio
async def test_http_series_diarias_linea_barras_y_hp(archivo_fx) -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/series-diarias",
                         params={"serie": "caucion_tna_vwap", "chart": "linea", "dias": "90"})
        assert r.status_code == 200
        assert "<svg" in r.text and "<path" in r.text          # modo línea
        assert "Tabla histórica (HP)" in r.text and "hp-series-tbl" in r.text
        assert "31,20%" in r.text                              # último VWAP es-AR
        assert ">3D<" in r.text                                # plazo del viernes
        b = await ac.get("/historicos/series-diarias",
                         params={"serie": "ccl", "chart": "barras", "dias": "todo"})
        assert b.status_code == 200 and "<rect" in b.text      # modo barras
        assert "<path" not in b.text                           # sin línea en barras
        # la página muestra el tab nuevo con su carga lazy
        page = await ac.get("/historicos")
        assert "Series diarias (FX + caución)" in page.text
        assert 'id="hist-series"' in page.text
