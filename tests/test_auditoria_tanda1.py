"""Regresiones de la auditoría externa (15/09/2026), tanda 1: cada test expresa
la garantía que el código incumplía. Fxx = hallazgo del informe."""
from __future__ import annotations

import asyncio
import math
import os
import stat
import time
from datetime import date

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, marketdata_store as mds, oms, pricing


@pytest.fixture()
def store_tmp(tmp_path, monkeypatch):
    """Store de usuarios temporal con superuser bootstrapeado (muro apagado)."""
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield tmp_path / "store.json"
    auth.refresh()


# ── F04 · guardado del store sin os.fchmod (Windows < 3.13) ──────────────────
def test_f04_guardado_sin_fchmod(store_tmp, monkeypatch) -> None:
    monkeypatch.delattr(os, "fchmod", raising=False)
    auth.create_user("winuser", "clave-larga-123", "basico")
    auth.refresh()                                   # relee del disco
    assert auth.get_user("winuser") and auth.verify_password("winuser", "clave-larga-123")
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(store_tmp).st_mode) == 0o600


# ── F05 · un guardado fallido no deja el cambio vivo en memoria ──────────────
def test_f05_guardado_fallido_no_deja_permisos(store_tmp, monkeypatch) -> None:
    auth.create_user("bob", "clave-larga-123", "basico")
    assert auth.role_of("bob") == "basico"

    def boom(data):
        raise OSError("disco lleno")

    monkeypatch.setattr(auth, "_save_locked", boom)
    with pytest.raises(OSError):
        auth.update_user("bob", role="premium")
    assert auth.role_of("bob") == "basico"           # memoria = disco
    with pytest.raises(OSError):
        auth.set_password("bob", "otra-clave-larga")
    assert auth.verify_password("bob", "clave-larga-123")


# ── F09 · NaN / inf del feed no entran al store ni valen como referencia ─────
def test_f09_store_descarta_no_finitos() -> None:
    assert mds._md_value({"price": "nan"}) is None and mds._md_value([{"price": "inf"}]) is None
    assert mds._md_value(float("nan")) is None and mds._md_value(70.5) == 70.5
    assert mds._depth_levels([{"price": "nan", "size": 1}, {"price": 100, "size": "inf"}]) == \
        [{"price": 100.0, "size": None}]
    st = mds.MarketDataStore()
    s = st.update_from_md("X", {"LA": {"price": "nan", "size": 10}, "CL": [{"price": "inf"}],
                                "BI": [{"price": "nan", "size": 1}, {"price": 99.0, "size": 5}]})
    assert s.last is None and s.close is None and s.bid is None
    assert s.bids == [{"price": 99.0, "size": 5.0}]
    # persistido con NaN (json acepta el token) → repuesto limpio
    st2 = mds.MarketDataStore()
    n = st2.restore({"Y": {"symbol": "Y", "last": float("nan"), "close": 100.0, "updated_at": 1.0,
                           "bids": [{"price": float("nan"), "size": 1}], "offers": [{"price": 101.0, "size": 2}]}})
    y = st2.get("Y")
    assert n == 1 and y.last is None and y.close == 100.0 and y.bids is None
    assert y.offers == [{"price": 101.0, "size": 2}]


def test_f09_validate_sin_referencia_con_nan() -> None:
    nan = float("nan")
    oms.kill_switch(False)
    assert oms.validate("AL30", "buy", 100, 100.0, "C1", 100.0) is None        # sano: pasa
    # Limit con referencia NaN = sin referencia → exige confirmación (o rechaza la banda con theo)
    r = oms.validate("AL30", "buy", 100, 100000.0, "C1", nan)
    assert r is not None and "referencia" in r.lower()
    assert oms.validate("AL30", "buy", 100, 100000.0, "C1", nan, theo_ref=100.0) is not None
    # Market con referencia NaN: antes notional = NaN → tope evadido
    cap = settings.oms_max_notional
    r = oms.validate("AL30", "buy", cap * 10, None, "C1", nan, ordtype="market", confirmed=True)
    assert r is not None and "tope" in r.lower()
    assert oms.validate("AL30", "buy", cap * 10, None, "C1", nan, ordtype="market") is not None
    # cantidad / precio no finitos
    assert oms.validate("AL30", "buy", nan, 100.0, "C1", 100.0) is not None
    assert oms.validate("AL30", "buy", 100, nan, "C1", 100.0) is not None
    assert oms.validate("AL30", "buy", 100, float("inf"), "C1", 100.0) is not None


# ── F02 · kill-switch activado durante la preparación: la orden NO sale ──────
def test_f02_kill_durante_resolve_no_envia(monkeypatch) -> None:
    from backend.services import instruments, primary_ws

    enviados = []

    class _WS:
        async def get_json_checked(self, path, params):
            enviados.append((path, params))
            return {"status": "OK", "order": {"clientId": "1"}}

    async def _resolve(code, symbol):
        oms.kill_switch(True)                         # el freno entra en plena preparación
        return {"checked": False, "exists": True, "candidates": []}

    monkeypatch.setattr(instruments, "resolve", _resolve)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.kill_switch(False)
    oms.set_live(True)
    try:
        res = asyncio.run(oms.place({"code": "AL30", "symbol": "MERV - XMEV - AL30 - 24hs", "side": "buy",
                                     "qty": 100.0, "price": 941.0, "account": "C1", "ordtype": "limit"}))
        assert res["status"] == "RECHAZADA" and not enviados
        assert any(a["event"] == "rechazada_kill" and a.get("etapa") == "pre_envio" for a in oms.audit_tail(5))
    finally:
        oms.kill_switch(False)
        oms.set_live(None)


# ── F10 · la huella del índice cambia con la PROYECCIÓN (CER/UVA/floaters) ──
def test_f10_huella_incluye_proyeccion(monkeypatch) -> None:
    import rentafija

    monkeypatch.setattr(pricing, "_last_series_value", lambda *a: ("2026-09-15", 100.0))
    idx = pd.to_datetime(["2026-09-15", "2027-09-15"])
    for kind, key, col in (("cer", "cer_proyectado", "CER"), ("uva", "uva_proyectado", "UVA")):
        monkeypatch.setitem(rentafija.inputs, key, pd.DataFrame({col: [100.0, 110.0]}, index=idx))
        pricing._index_val_cache.clear()
        f1 = pricing._index_fingerprint(kind)
        pricing._index_val_cache.clear()
        assert pricing._index_fingerprint(kind) == f1                      # estable sin cambios
        monkeypatch.setitem(rentafija.inputs, key, pd.DataFrame({col: [100.0, 150.0]}, index=idx))
        pricing._index_val_cache.clear()
        assert pricing._index_fingerprint(kind) != f1, kind                 # proyección nueva → key nueva
    # floaters: mismo benchmark, otra proyección → huella distinta
    monkeypatch.setattr(pricing, "_bench_pct", lambda col: 30.0)
    monkeypatch.setitem(rentafija.inputs, "tamar_proyectado", pd.DataFrame({"TAMAR": [30.0, 30.0]}, index=idx))
    pricing._index_val_cache.clear()
    t1 = pricing._index_fingerprint("tamar")
    monkeypatch.setitem(rentafija.inputs, "tamar_proyectado", pd.DataFrame({"TAMAR": [30.0, 28.0]}, index=idx))
    pricing._index_val_cache.clear()
    assert pricing._index_fingerprint("tamar") != t1
    pricing._index_val_cache.clear()


# ── F14 · los locks de las búsquedas de Mercado quedan acotados ──────────────
@pytest.mark.asyncio
async def test_f14_locks_acotados(monkeypatch) -> None:
    from backend.routes import curves as cr

    async def vacio(*a, **k):
        return [], {}

    monkeypatch.setattr(cr, "_rows_for", vacio)
    monkeypatch.setattr(cr, "_ROWS_CACHE", {})
    monkeypatch.setattr(cr, "_ROWS_LOCKS", {})
    for i in range(1000):
        await cr._rows_en_seq("lecap", "24hs", True, "native", "byma", f"busqueda-{i}", 0)
    assert len(cr._ROWS_LOCKS) <= cr._ROWS_MAX and len(cr._ROWS_CACHE) <= cr._ROWS_MAX


# ── F07 / F08 · historia: base sólo-parquet y corrección a mano en el Excel ─
def _base_inicial(tmp_path, d1: date):
    from backend.services import historico_writer as hw
    from tests.test_historico_writer import _rows_df

    xlsx = str(tmp_path / hw.HIST_FILENAME)
    assert hw.append_and_save(_rows_df(d1), xlsx, incluir_journal=False)["total_rows"] == 2
    return hw, _rows_df, xlsx, xlsx.replace(".xlsx", ".parquet")


def test_f07_base_solo_parquet_conserva_historia(tmp_path) -> None:
    hw, _rows_df, xlsx, pq = _base_inicial(tmp_path, date(2026, 7, 7))
    os.remove(xlsx)                                   # quedó sólo el espejo
    r = hw.append_and_save(_rows_df(date(2026, 7, 8)), xlsx, incluir_journal=False)
    assert r["total_rows"] == 4 and os.path.isfile(xlsx)
    back = pd.read_parquet(pq)
    assert sorted(pd.to_datetime(back["fecha_hoy"]).dt.date.unique()) == [date(2026, 7, 7), date(2026, 7, 8)]
    # espejo ilegible y sin xlsx: NO se pisa
    os.remove(xlsx)
    with open(pq, "wb") as fh:
        fh.write(b"basura")
    with pytest.raises(RuntimeError):
        hw.append_and_save(_rows_df(date(2026, 7, 9)), xlsx, incluir_journal=False)
    assert open(pq, "rb").read() == b"basura"


def test_f08_excel_corregido_gana_al_espejo(tmp_path) -> None:
    from backend.services import historico_byma as hb

    hw, _rows_df, xlsx, pq = _base_inicial(tmp_path, date(2026, 7, 7))
    df = pd.read_excel(xlsx)
    df["Last Price"] = 555.0
    df.to_excel(xlsx, index=False)                    # corrección a mano
    now = time.time()
    os.utime(pq, (now - 30, now - 30))
    os.utime(xlsx, (now, now))                        # Excel 30 s más nuevo: antes perdía (gracia 60 s)
    prev = hw._leer_base(xlsx, pd)
    assert set(prev["Last Price"]) == {555.0}
    assert hb._pick_source(xlsx)[1] == "xlsx"
    # Tanda 4 (R06): ya no hay 2 s de gracia. Con el espejo 1 s más viejo que
    # el Excel corregido sigue mandando el Excel; el espejo vuelve a valer
    # recién cuando lleva la FIRMA de ese Excel (lo que hace el writer /
    # _regen_parquet después de escribir los dos).
    from backend.services import espejo
    os.utime(pq, (now - 1, now - 1))
    assert hb._pick_source(xlsx)[1] == "xlsx"
    espejo.marcar_espejo(pq, xlsx)
    assert hb._pick_source(xlsx)[1] == "parquet"
    # OneDrive trae un Excel editado en otra máquina con mtime VIEJO (preservado)
    # pero distinto contenido: la firma (mtime + tamaño) no coincide → Excel.
    df["Last Price"] = 777.0
    df.to_excel(xlsx, index=False)
    os.utime(xlsx, (now - 120, now - 120))
    assert hb._pick_source(xlsx)[1] == "xlsx"
    assert set(hw._leer_base(xlsx, pd)["Last Price"]) == {777.0}


# ── F16 · entradas inválidas → 400 con explicación, no 500 ──────────────────
@pytest.mark.asyncio
async def test_f16_excel_calc_body_no_dict(store_tmp, monkeypatch) -> None:
    from backend.main import app

    monkeypatch.setattr(settings, "auth_enabled", True)
    auth.create_user("mesa9", "clave-larga-123", "basico")
    tok = auth.set_excel_access("mesa9", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        for body in ([1], "x", None, {"items": "x"}):
            r = await ac.post("/excel/v1/calc", json=body, headers={"X-OMS-Token": tok})
            assert r.status_code == 400, body


def test_f16_adhoc_aritmetica_invalida() -> None:
    from backend.services import adhoc

    for txt in ("{'Código':'AUDIT','Cupón': 'a'-1}", "{'Código':'AUDIT','Cupón': -'x'}",
                "{'Código':'AUDIT','Cupón': [1]*'b'}"):
        with pytest.raises(ValueError):
            adhoc.parse_ficha(txt)


# ── F15 · TLS: sin reintento inseguro salvo opt-in explícito ────────────────
def test_f15_tls_sin_reintento_inseguro(monkeypatch) -> None:
    import requests
    from types import SimpleNamespace
    from backend.services import byma_paneles as bp

    seen = []

    def post(*a, **kw):
        seen.append(kw.get("verify", True))
        raise requests.exceptions.SSLError("certificado no confiable (sintético)")

    assert bp._fetch_panel(SimpleNamespace(post=post), bp._EPS["cedears"]) is None
    assert seen == [True]
    monkeypatch.setattr(settings, "byma_paneles_tls_inseguro", True)
    seen.clear()
    assert bp._fetch_panel(SimpleNamespace(post=post), bp._EPS["cedears"]) is None
    assert seen == [True, False]


# ── JSON de estado corrupto: se aparta con evidencia, no se pisa ─────────────
def test_alertas_y_prefs_corruptos_se_apartan(tmp_path, monkeypatch) -> None:
    from backend.services import alertas, escenario_prefs

    p = tmp_path / "alertas.json"
    p.write_text("{basura", encoding="utf-8")
    monkeypatch.setenv("ALERTAS_PATH", str(p))
    assert alertas._load() == []
    apartados = list(tmp_path.glob("alertas.json.corrupto-*"))
    assert len(apartados) == 1 and apartados[0].read_text(encoding="utf-8") == "{basura"
    alertas._write([])                                # el próximo guardado no toca la evidencia
    assert apartados[0].is_file() and p.is_file()

    q = tmp_path / "prefs.json"
    q.write_text("[1,", encoding="utf-8")
    monkeypatch.setenv("ESCENARIO_PREFS_PATH", str(q))
    assert escenario_prefs._load_all()["presets"] == {}
    assert len(list(tmp_path.glob("prefs.json.corrupto-*"))) == 1 and not q.exists()


# ── F19 · el módulo legacy de CAFCI manda timeout ───────────────────────────
def test_f19_cafciapi_con_timeout(monkeypatch) -> None:
    import cafciapi

    class _Stop(Exception):
        pass

    seen = {}

    def fake_get(url, **kw):
        seen.update(kw)
        raise _Stop()

    monkeypatch.setenv("CAFCI_TOKEN", "token-de-test")
    monkeypatch.setattr(cafciapi.requests, "get", fake_get)
    with pytest.raises(_Stop):
        cafciapi.get_daily_report()
    assert seen.get("timeout") == cafciapi._TIMEOUT and all(math.isfinite(x) for x in seen["timeout"])
