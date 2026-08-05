"""Break-even Fisher — matemática + endpoint."""
from __future__ import annotations

import pytest

from backend.services.breakeven import compute_fisher


def _row(code, dur, tirea):
    return {"code": code, "duration": dur, "tirea": tirea}


def test_fisher_math() -> None:
    # nominal plana 40% — real 8% → BE = 1.40/1.08 − 1 ≈ 29.63%
    lecap = [_row("S1", 0.5, 0.40), _row("S2", 2.0, 0.40)]
    cer = [_row("TX1", 1.0, 0.08)]
    out = compute_fisher(cer, lecap)
    r = out["rows"][0]
    assert abs(r["be_anual"] - (1.40 / 1.08 - 1.0)) < 1e-12
    assert abs(r["be_tem"] - ((1.0 + r["be_anual"]) ** (30 / 360) - 1.0)) < 1e-12
    assert not r["extrapolado"]
    assert out["resumen"]["n"] == 1


def test_fisher_interpola_y_extrapola() -> None:
    lecap = [_row("S1", 1.0, 0.30), _row("S2", 3.0, 0.50)]   # pendiente +10%/año
    cer = [_row("C1", 2.0, 0.05),    # interpola → nominal 40%
           _row("C2", 6.0, 0.05)]    # fuera de rango → clamp 50% + extrapolado
    out = compute_fisher(cer, lecap)
    by = {r["code"]: r for r in out["rows"]}
    assert abs(by["C1"]["tirea_nom"] - 0.40) < 1e-12 and not by["C1"]["extrapolado"]
    assert abs(by["C2"]["tirea_nom"] - 0.50) < 1e-12 and by["C2"]["extrapolado"]


def test_fisher_mes_ref_en_filas() -> None:
    from datetime import date
    lecap = [_row("S1", 0.2, 0.40), _row("S2", 1.0, 0.40)]
    cer = [{**_row("TZXO6", 0.37, 0.08), "vencimiento": date(2026, 10, 31), "lag": -10}]
    out = compute_fisher(cer, lecap)
    assert out["rows"][0]["mes_ref"] == "sep-26"


def test_fisher_filtra_basura() -> None:
    lecap = [_row("S1", 1.0, 0.40)]
    cer = [_row("C1", 1.0, 0.08), _row("C2", None, 0.08), _row("C3", 1.0, None),
           _row("C4", -1.0, 0.08), _row("C5", 1.0, 9.0)]   # NaN/None/dur<=0/absurda
    out = compute_fisher(cer, lecap)
    assert out["n_cer"] == 1 and len(out["rows"]) == 1


@pytest.mark.asyncio
async def test_breakeven_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        p = await ac.get("/breakeven")
        t = await ac.get("/breakeven/table")
    assert p.status_code == 200 and "Break-even" in p.text
    assert "md-update from:body" in p.text          # panel live
    assert t.status_code == 200


def test_mes_referencia_metodologia_indec() -> None:
    """fix = vto + lag hábiles; CER del día D devenga: mes−1 si D≥16, mes−2 si D≤15.
    Ej. del usuario: dato de mayo sale ~11/6 → corre en el CER del 16/6 al 15/7."""
    from datetime import date

    from backend.services.breakeven import mes_referencia

    assert mes_referencia(date(2026, 10, 31), -10) == "sep-26"   # TZXO6: fix 19/10
    assert mes_referencia(date(2026, 7, 31), -10) == "jun-26"    # fix 17/7 (≥16)
    assert mes_referencia(date(2026, 7, 24), -10) == "may-26"    # fix ~10/7 (≤15)
    assert mes_referencia(date(2026, 2, 13), -10) == "dic-25"    # cruce de año
    assert mes_referencia(None) is None


@pytest.mark.asyncio
async def test_breakeven_chart_y_columna() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        p = await ac.get("/breakeven")
        t = await ac.get("/breakeven/table")
        ch = await ac.get("/breakeven/chart")
        ch_an = await ac.get("/breakeven/chart", params={"be-metric": "anual"})
    assert p.status_code == 200 and 'name="be-metric"' in p.text and 'id="be-chart"' in p.text
    assert t.status_code == 200
    assert ("Infla. hasta" in t.text) == ("be-tbl" in t.text)   # columna sólo con filas
    # Gráfico SVG server-side, MISMO estilo que el sendero de deva de Futuros:
    # misma clase de svg (fut-chart) y mismas clases fc-* (barras/grid/prom).
    assert ch.status_code == 200 and ch_an.status_code == 200
    for frag in ('class="fut-chart"', "fc-grid"):
        assert (frag in ch.text) or "Sin break-evens" in ch.text
    if "fc-bar" in ch.text:                     # con datos: barras + línea prom
        assert "fc-blabel" in ch.text and "fc-xlabel" in ch.text
        assert ("fc-avg" in ch.text) == ("prom " in ch.text)


def test_fisher_marca_definidos_y_los_excluye_del_resumen() -> None:
    """El caso X31L6: si la serie CER publicada ya cubre el fix del bono
    (vto + lag), su BE está DETERMINADO → flag `definido` y fuera del
    promedio/gráfico por default. `incluir` explícito lo puede re-sumar."""
    from datetime import date
    lecap = [_row("S1", 0.02, 0.40), _row("S2", 1.0, 0.40)]
    cer = [{**_row("X31L6", 0.04, 0.08), "vencimiento": date(2026, 7, 31), "lag": -10},
           {**_row("TZXO6", 0.30, 0.07), "vencimiento": date(2026, 10, 31), "lag": -10}]
    # serie CER publicada hasta el 15/8 (salió el IPC de junio) → el fix de
    # X31L6 (~17/7) está cubierto; el de TZXO6 (19/10) no.
    out = compute_fisher(cer, lecap, cer_conocido_hasta=date(2026, 8, 15))
    by = {r["code"]: r for r in out["rows"]}
    assert by["X31L6"]["definido"] and not by["X31L6"]["incluido"]
    assert not by["TZXO6"]["definido"] and by["TZXO6"]["incluido"]
    assert out["n_definidos"] == 1
    assert out["resumen"]["n"] == 1                       # sólo TZXO6 promedia
    # el usuario lo re-tilda → entra; y puede destildar el otro
    out2 = compute_fisher(cer, lecap, cer_conocido_hasta=date(2026, 8, 15),
                          incluir={"X31L6"})
    by2 = {r["code"]: r for r in out2["rows"]}
    assert by2["X31L6"]["incluido"] and not by2["TZXO6"]["incluido"]
    assert out2["resumen"]["n"] == 1
    # sin fecha de serie (BCRA caído): nadie se marca definido
    out3 = compute_fisher(cer, lecap, cer_conocido_hasta=None)
    assert out3["n_definidos"] == 0 and out3["resumen"]["n"] == 2


@pytest.mark.asyncio
async def test_breakeven_tildes_en_endpoint() -> None:
    """La tabla trae checkbox por bono + incl_set (el estado viaja en cada
    refresh); con incl explícito el server respeta la selección."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        t = await ac.get("/breakeven/table")
        assert t.status_code == 200
        if "be-tbl" in t.text:                            # sólo si hay filas (feed)
            assert 'name="incl"' in t.text and 'name="incl_set"' in t.text
        t2 = await ac.get("/breakeven/table", params={"incl_set": "1", "incl": ["TX26"]})
        assert t2.status_code == 200


def test_fisher_empareja_por_vencimiento() -> None:
    """TZXO6 (31/10) se compara contra la letra que vence el 30/10, no contra
    la interpolación; sin letra cercana (±45d) cae a interpolación."""
    from datetime import date
    lecap = [{**_row("S30O6", 0.38, 0.42), "vencimiento": date(2026, 10, 30)},
             {**_row("S31L6", 0.15, 0.35), "vencimiento": date(2026, 7, 31)}]
    cer = [{**_row("TZXO6", 0.37, 0.08), "vencimiento": date(2026, 10, 31), "lag": -10},
           {**_row("TX29", 2.8, 0.07), "vencimiento": date(2029, 6, 30), "lag": -10}]
    out = compute_fisher(cer, lecap)
    by = {r["code"]: r for r in out["rows"]}
    assert by["TZXO6"]["par"] == "S30O6" and abs(by["TZXO6"]["tirea_nom"] - 0.42) < 1e-12
    assert by["TX29"]["par"] is None                      # lejos de toda letra → interp/clamp
