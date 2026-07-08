"""Autoguardado del histórico px/tasas al cierre (backend/services/historico_writer).

Cubre: scheduling (next_fire), parser de fechas del feed, append con el
dedup de bymaapi (Excel + Parquet), guards de calendario/actividad, el
guardado end-to-end con refresh del histórico, y el gating superuser del
endpoint manual.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, historico_byma, historico_writer as hw

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _ba(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


def _epoch_ms(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1000))


def _rows_df(fecha: date, *, source: str = "LA", ts: str | None = None) -> pd.DataFrame:
    ts = ts if ts is not None else _epoch_ms(datetime.now(_TZ))
    return pd.DataFrame({
        "symbol": ["MERV - XMEV - T30E6 - 24hs", "MERV - XMEV - S31L6j - 24hs"],
        "Código": ["T30E6", "S31L6j"],
        "Last Price": [101.5, 99.8],
        "Close Price": [100.0, 99.0],
        "Variación %": [0.015, 0.008],
        "TIREA": [0.321, 0.315],
        "TNA": [0.28, 0.274],
        "TEM": [0.0235, 0.023],
        "Paridad": [0.98, 0.97],
        "Duration": [0.6, 0.9],
        "Price Source": [source, source],
        "Price Date": [ts, ts],
        "fecha_hoy": [fecha, fecha],
    })


# ── scheduling ──────────────────────────────────────────────────────────────
def test_next_fire_today_and_tomorrow() -> None:
    antes = _ba(2026, 7, 8, 16, 0)
    assert hw.next_fire(antes, "17:01") == _ba(2026, 7, 8, 17, 1)
    despues = _ba(2026, 7, 8, 17, 30)
    assert hw.next_fire(despues, "17:01") == _ba(2026, 7, 9, 17, 1)
    # HH:MM inválida cae al default 17:01 en vez de reventar el daemon.
    assert hw.next_fire(antes, "no-es-hora").hour == 17


def test_fecha_dato_parser() -> None:
    hoy = datetime.now(_TZ)
    assert hw._fecha_dato(_epoch_ms(hoy)) == hoy.date()
    assert hw._fecha_dato("2026-07-08T14:30:00-03:00") == date(2026, 7, 8)
    assert hw._fecha_dato(None) is None
    assert hw._fecha_dato("basura") is None


def test_operados_hoy_cuenta_solo_la_de_hoy() -> None:
    hoy = datetime.now(_TZ)
    ayer = _epoch_ms(hoy - timedelta(days=1))
    df = pd.concat([
        _rows_df(hoy.date()),                                   # LA de hoy → cuentan (2)
        _rows_df(hoy.date(), source="CL", ts=""),               # cierres → no cuentan
        _rows_df(hoy.date(), ts=ayer),                          # LA de ayer (pegajoso) → no
    ], ignore_index=True)
    assert hw.operados_hoy(df) == 2


# ── append con dedup (Excel + Parquet) ──────────────────────────────────────
def test_append_and_save_dedup_and_mirror(tmp_path) -> None:
    xlsx = str(tmp_path / hw.HIST_FILENAME)
    d1, d2 = date(2026, 7, 7), date(2026, 7, 8)

    r1 = hw.append_and_save(_rows_df(d1), xlsx)
    assert r1["total_rows"] == 2 and r1["parquet"]

    # mismo día re-guardado con otro precio → REEMPLAZA (keep last), no duplica
    df_bis = _rows_df(d1)
    df_bis["Last Price"] = [111.0, 112.0]
    assert hw.append_and_save(df_bis, xlsx)["total_rows"] == 2
    back = pd.read_excel(xlsx)
    assert sorted(back["Last Price"]) == [111.0, 112.0]

    # día nuevo → se agrega; Proy por sufijo j; parquet espejo igual al Excel
    assert hw.append_and_save(_rows_df(d2), xlsx)["total_rows"] == 4
    back = pd.read_excel(xlsx)
    assert sorted(back["Proy"].tolist()) == [0, 0, 1, 1]
    assert len(pd.read_parquet(str(tmp_path / hw.HIST_FILENAME).replace(".xlsx", ".parquet"))) == 4


# ── save_today: guards + end-to-end ─────────────────────────────────────────
@pytest.fixture()
def hist_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    return tmp_path


def test_save_today_skips_weekend(hist_env, monkeypatch) -> None:
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 7, 11, 17, 1))   # sábado
    res = hw.save_today()
    assert res["ok"] is False and "fin de semana" in res["skipped"]


def test_save_today_skips_feriado_por_min_operados(hist_env, monkeypatch) -> None:
    lunes = _ba(2026, 7, 13, 17, 1)
    monkeypatch.setattr(hw, "_now", lambda: lunes)
    # feriado: el store sólo tiene cierres pegajosos (nada operó hoy)
    monkeypatch.setattr(hw, "build_rows",
                        lambda plazo="24hs": _rows_df(lunes.date(), source="CL", ts=""))
    res = hw.save_today()
    assert res["ok"] is False and "feriado" in (res["skipped"] or "")


def test_save_today_end_to_end_y_refresh(hist_env, monkeypatch) -> None:
    hoy = datetime.now(_TZ)
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": _rows_df(hoy.date()))
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 1)
    res = hw.save_today()
    assert res["ok"] is True and res["rows"] == 2 and res["operados"] == 2
    # el refresh dejó el histórico cargado con la fecha nueva (lo ven Qué pasó/Históricos)
    meta = historico_byma.meta()
    assert meta["loaded"] is True and meta["dmax"] == hoy.date().isoformat()
    # segunda pasada del autosave el mismo día → skip (ya guardado, vía parquet)
    res2 = hw.save_today()
    assert res2["ok"] is False and "ya tiene filas de hoy" in res2["skipped"]
    historico_byma.refresh()   # deja el cache global limpio para otros tests


def test_build_rows_desde_store_vivo() -> None:
    # Con un precio sembrado para un código real de las curvas, build_rows
    # produce la fila con las métricas calculadas de verdad.
    from backend.services import curves, marketdata_store, pricing
    from backend.services import symbols as syms

    code = None
    for key in ("lecap", "cer", "globales"):
        for cand in (curves.build_curve_codes().get(key) or [])[:8]:
            if pricing.metrics_for_market_price(cand, 100.0) is not None:
                code = cand
                break
        if code:
            break
    assert code, "no encontré un código calculable en las curvas"
    sym = syms.md_symbol(code, "24hs")
    marketdata_store.get_store().update_from_md(sym, {
        "LA": {"price": 100.0, "date": _epoch_ms(datetime.now(_TZ))},
        "CL": {"price": 99.0},
    })
    df = hw.build_rows()
    fila = df[df["Código"] == code]
    assert len(fila) == 1
    assert fila.iloc[0]["Price Source"] == "LA"
    assert fila.iloc[0]["TIREA"] == fila.iloc[0]["TIREA"]      # no NaN
    assert fila.iloc[0]["fecha_hoy"] == datetime.now(_TZ).date()


# ── endpoint manual: sólo superuser ─────────────────────────────────────────
@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    b = auth.ensure_bootstrapped()
    assert b["created"]
    yield
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_guardar_base_solo_superuser(auth_on, monkeypatch) -> None:
    monkeypatch.setattr(hw, "save_today", lambda force=False: {
        "ok": True, "rows": 5, "operados": 5, "total_rows": 100,
        "xlsx": "x.xlsx", "parquet": "x.parquet", "skipped": None, "error": None})
    async with _client() as ac:
        # sin sesión → al login
        r = await ac.post("/historicos/guardar-base")
        assert r.status_code in (302, 401)
    async with _client() as su:
        r = await su.post("/login", data={"username": "rodricor93", "password": "Rc_874562",
                                          "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123",
                                                "role": "basico", "email": ""})
        assert r.status_code < 400, r.text[:200]
        # superuser → guarda
        r = await su.post("/historicos/guardar-base")
        assert r.status_code == 200 and "Base guardada" in r.text
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123",
                                          "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await ac.post("/historicos/guardar-base")
        assert r.status_code == 403                      # básico: sección de superuser
