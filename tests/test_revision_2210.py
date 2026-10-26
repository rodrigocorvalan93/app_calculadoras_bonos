"""Revisión de eficiencia 22/10 — lo chico que no vuelve.

- La key del memo de filas de Curvas (book=False) NO lleva el snapshot MAE:
  el poller MAE invalidaba todas las filas cada ~20 s sin que cambiara nada.
- `_ROW_MEMO` al tope poda la mitad más vieja en vez de vaciarse entero.
- `MarketStore.to_persist` da el MISMO JSON sin el `asdict` recursivo.
- `#be-chart` opta al skip de swaps idénticos (`data-skip-same`).
- `calcular_CER_diario_proyectado` vectorizado tarda ms, no segundos.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from backend.routes import curves as rc
from backend.services import marketdata_store as mds_

ROOT = Path(__file__).resolve().parents[1]


def test_podar_row_memo_deja_la_mitad_mas_nueva() -> None:
    rc._ROW_MEMO.clear()
    for i in range(10):
        rc._ROW_MEMO[("k", i)] = (i, {"code": str(i)})
    rc._ROW_MEMO[("k", 2)] = (99, {"code": "2b"})          # reasignar NO la mueve: sigue vieja
    rc._podar_row_memo()
    assert set(rc._ROW_MEMO) == {("k", i) for i in range(5, 10)}
    rc._ROW_MEMO.clear()


@pytest.mark.asyncio
async def test_key_de_curvas_no_lleva_el_snapshot_mae(monkeypatch) -> None:
    """book=False (Curvas / Inicio): `mae_ts` None en la key; book=True (Mercado)
    sigue llevándolo porque la fila incluye `row["mae"]`."""
    from backend.services import bond_universe, mae as mae_svc
    bond_universe.ensure_loaded()
    monkeypatch.setattr(mae_svc, "snapshot_ts", lambda: 12345.0)
    rc._ROW_MEMO.clear()
    rows, _ = await rc._rows_for("lecap", "24hs", False, "native", book=False)
    assert rows and all(r["_rk"][0][4] is None for r in rows), rows[0]["_rk"]
    rows, _ = await rc._rows_for("lecap", "24hs", False, "native", book=True)
    assert rows and all(r["_rk"][0][4] == 12345.0 for r in rows)
    rc._ROW_MEMO.clear()


def test_to_persist_sin_asdict_da_el_mismo_json() -> None:
    store = mds_.MarketDataStore()
    store.update_from_md("MERV - XMEV - TX26 - 24hs",
                         {"LA": {"price": 101.5, "size": 1000, "date": "2026-10-22T14:00:00"},
                          "BI": [{"price": 101.4, "size": 10}, {"price": 101.3, "size": 20}],
                          "OF": [{"price": 101.6, "size": 5}], "CL": {"price": 100.0}})
    nuevo = store.to_persist()
    viejo = {sym: asdict(snap) for sym, snap in store._data.items()}
    assert json.dumps(nuevo, sort_keys=True) == json.dumps(viejo, sort_keys=True)
    # y la copia no comparte el dict de atributos con el snapshot vivo
    nuevo["MERV - XMEV - TX26 - 24hs"]["last"] = -1
    assert store.get("MERV - XMEV - TX26 - 24hs").last == 101.5


def test_be_chart_opta_al_skip_de_swaps_identicos() -> None:
    tpl = (ROOT / "backend/templates/breakeven.html").read_text(encoding="utf-8")
    i = tpl.index('id="be-chart"')
    assert "data-skip-same" in tpl[i:i + 200]


def test_cer_proyectado_tarda_milisegundos() -> None:
    import pandas as pd
    import indices
    meses = pd.date_range("2024-01-01", periods=36, freq="MS")
    df = pd.DataFrame({"inflacionmom": [2.0 + (i % 5) * 0.3 for i in range(len(meses))]}, index=meses)
    t0 = time.perf_counter()
    out = indices.calcular_CER_diario_proyectado(df, 500.0, "2024-01-31")
    dt = time.perf_counter() - t0
    assert len(out) > 1000 and dt < 0.5, dt      # el loop viejo: ~1,8 s por 300 días
