"""Chip "cierre" de la topbar + banner + captura headless.

`historico_writer.estado_cierre()`: ¿la base histórica compartida tiene el
último cierre esperado? Calendario hábil con feriados AR, días marcados "sin
rueda", journal local, ventana de reintentos del autosave y cache por mtime
del parquet (el chip sondea 1×/min por pestaña: ~µs por llamada)."""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import historico_writer as hw

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _ba(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    monkeypatch.setenv("HISTORICO_JOURNAL_DIR", str(tmp_path / "journal"))
    monkeypatch.setattr(settings, "historico_autosave", True)
    monkeypatch.setattr(settings, "historico_base_writer", True)
    monkeypatch.setattr(settings, "historico_autosave_hhmm", "17:01")
    monkeypatch.setattr(hw, "_autosave", None)
    hw._fechas_cache = ()
    yield tmp_path
    hw._fechas_cache = ()


def _base(tmp_path, *dias: date) -> str:
    """Espejo parquet con esas fechas (lo único que lee el estado)."""
    pq = str(tmp_path / hw.HIST_FILENAME).replace(".xlsx", ".parquet")
    pd.DataFrame({"fecha_hoy": list(dias), "Código": ["X"] * len(dias)}).to_parquet(pq, index=False)
    hw._fechas_cache = ()
    return pq


def _journal(tmp_path, d: date) -> None:
    j = tmp_path / "journal"
    j.mkdir(exist_ok=True)
    pd.DataFrame({"fecha_hoy": [d]}).to_parquet(j / f"px_tasas_{d:%Y%m%d}.parquet", index=False)


def test_estados_del_cierre(env, monkeypatch) -> None:
    # base hasta el viernes 28/08/2026; lunes 31 a la mañana → al día (esperado = viernes)
    _base(env, date(2026, 8, 28))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 10, 0))
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["esperado"] == "2026-08-28" and e["texto"] == "✓ cierre 28/08"
    assert "dejá la app abierta" in e["detalle"] and e["atraso"] == 0
    # 17:30: pasó la hora, hoy no está, ventana de reintentos → pendiente
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 17, 30))
    e = hw.estado_cierre()
    assert e["estado"] == "pendiente" and e["esperado"] == "2026-08-31"
    # 19:00: fuera de la ventana → falta (atraso 1)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 19, 0))
    e = hw.estado_cierre()
    assert e["estado"] == "falta" and e["atraso"] == 1 and e["texto"] == "⚠ falta cierre 31/08"
    assert "app estaba cerrada" in e["detalle"] and e["esperado_fmt"] == "31/08/2026"
    # el journal local tiene hoy → capturado (pendiente de consolidar)
    _journal(env, date(2026, 8, 31))
    e = hw.estado_cierre()
    assert e["estado"] == "capturado" and e["hoy_en_journal"] is True
    # la base ya tiene hoy → ok con la hora del archivo
    _base(env, date(2026, 8, 28), date(2026, 8, 31))
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["texto"].startswith("✓ cierre hoy ") and e["hoy_en_base"] is True
    # martes 1/9 a la mañana con base hasta el jueves 27/8 → falta viernes + lunes (atraso 2)
    os.remove(env / "journal" / "px_tasas_20260831.parquet")        # sin journal del lunes
    _base(env, date(2026, 8, 27))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 1, 9, 0))
    e = hw.estado_cierre()
    assert e["estado"] == "falta" and e["esperado"] == "2026-08-31" and e["atraso"] == 2
    assert e["texto"] == "⚠ falta cierre 31/08 (+1)"


def test_feriados_y_sin_rueda_no_cuentan(env, monkeypatch) -> None:
    # 17/08/2026 (lunes) es feriado AR: el martes 18 a la mañana el esperado es el viernes 14
    _base(env, date(2026, 8, 14))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 18, 10, 0))
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["esperado"] == "2026-08-14"
    # día hábil sin rueda marcado por el autosave (feriado no listado): tampoco se reclama
    _base(env, date(2026, 8, 28))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 19, 0))
    assert hw.estado_cierre()["estado"] == "falta"
    hw._marcar_sin_rueda(date(2026, 8, 31))
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["esperado"] == "2026-08-28"
    # save_today lo marca solo cuando saltea por mínimo de operados
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": pd.DataFrame(
        {"symbol": ["s"], "Código": ["X"], "Last Price": [1.0], "Price Source": ["CL"],
         "Price Date": [None], "fecha_hoy": [date(2026, 9, 1)]}))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 1, 17, 1))
    res = hw.save_today()
    assert "feriado" in (res["skipped"] or "") and date(2026, 9, 1) in hw._sin_rueda_days()
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 1, 19, 0))
    assert hw.estado_cierre()["estado"] == "ok"        # el 1/9 no se reclama


def test_estado_cacheado_por_mtime_y_sin_base(env, monkeypatch) -> None:
    _base(env, date(2026, 8, 28))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 10, 0))
    llamadas = []
    real = hw._fechas_base
    monkeypatch.setattr(hw, "_fechas_base", lambda p: (llamadas.append(p), real(p))[1])
    hw.estado_cierre(); hw.estado_cierre(); hw.estado_cierre()
    assert len(llamadas) == 1                          # stat por llamada, lectura una vez
    _base(env, date(2026, 8, 28), date(2026, 8, 31))   # archivo nuevo → relee
    hw.estado_cierre()
    assert len(llamadas) == 2
    # estado() (admin) reusa el mismo cálculo y mantiene sus claves de siempre
    e = hw.estado()
    assert e["ok"] is True and e["ultima_fecha"] == "2026-08-31" and e["cierre"].startswith("✓")
    # sin carpeta de bases: sin_base, chip vacío
    monkeypatch.delenv("DELTA_HISTORICO_DIR")
    assert hw.estado_cierre()["estado"] == "sin_base"


@pytest.mark.asyncio
async def test_http_chip_y_banner(env, monkeypatch) -> None:
    from backend.main import app

    _base(env, date(2026, 8, 28))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 19, 0))     # falta hoy
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/cierre/chip")
        assert r.status_code == 200
        assert 'class="cierre-chip" data-state="falta"' in r.text and "⚠ falta cierre 31/08" in r.text
        # banner oob para el superuser (auth off = superuser) con "Guardar ahora" (es el cierre de HOY)
        assert 'id="cierre-banner" hx-swap-oob="true"' in r.text and "Guardar ahora" in r.text
        assert "31/08/2026" in r.text
        # al día → chip ok y banner vacío
        _base(env, date(2026, 8, 28), date(2026, 8, 31))
        r = await ac.get("/cierre/chip")
        assert 'data-state="ok"' in r.text and "Guardar ahora" not in r.text
        # la página lo lleva en la topbar (slot htmx) y el banner vacío
        page = await ac.get("/yas")
        assert 'id="cierre-chip"' in page.text and 'hx-get="/cierre/chip"' in page.text
        assert 'id="cierre-banner"' in page.text
        # sin carpeta de bases: chip vacío, sin banner
        monkeypatch.delenv("DELTA_HISTORICO_DIR")
        r = await ac.get("/cierre/chip")
        assert "cierre-chip" not in r.text and "Guardar ahora" not in r.text


def test_captura_headless_precheck_y_operados(env, monkeypatch) -> None:
    from backend.services import bond_universe, curves, marketdata_store, symbols as syms
    from backend.tools import cierre

    # fin de semana: sale sin conectarse ni pedir credenciales
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 5, 17, 5))
    assert asyncio.run(cierre.capturar())["skipped"] == "fin de semana"
    # base ya con hoy: idem
    _base(env, date(2026, 8, 31))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 8, 31, 17, 5))
    assert asyncio.run(cierre.capturar())["skipped"] == "la base ya tiene filas de hoy"
    # sin credenciales → error claro (no explota)
    _base(env, date(2026, 8, 28))
    monkeypatch.setattr(settings, "primary_user", "")
    assert "PRIMARY_USER" in asyncio.run(cierre.capturar())["error"]
    # operados_en_store: cuenta sólo bonos con last_ts de HOY
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes()["cer"][:3]
    st = marketdata_store.get_store()
    hoy_ms = str(int(_ba(2026, 8, 31, 15, 0).timestamp() * 1000))
    ayer_ms = str(int(_ba(2026, 8, 28, 15, 0).timestamp() * 1000))
    st.update_from_md(syms.md_symbol(codes[0], "24hs"), {"LA": {"price": 100.0, "date": hoy_ms}})
    st.update_from_md(syms.md_symbol(codes[1], "24hs"), {"LA": {"price": 100.0, "date": hoy_ms}})
    st.update_from_md(syms.md_symbol(codes[2], "24hs"), {"LA": {"price": 100.0, "date": ayer_ms}})
    assert hw.operados_en_store() >= 2
    assert os.path.basename(cierre.__file__) == "cierre.py"
