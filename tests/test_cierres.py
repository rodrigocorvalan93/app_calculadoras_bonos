"""Cierre COMPLETO por rueda (cierres/AAAA/AAAA-MM-DD.parquet): filas desde el
store con métricas de los bonos, partición keep-last + journal, recaptura,
matriz numpy (at/serie/ret/vector_ref), backfill desde la base px/tasas y la
integración con el 5D % de Mercado (historico_byma.ref_5d)."""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backend.config import settings
from backend.services import cierres, historico_byma, historico_writer as hw, marketdata_store

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _ruedas(n: int, fin: date = date(2026, 9, 11)) -> list:
    out, d = [], fin
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.setenv("HISTORICO_JOURNAL_DIR", str(tmp_path / "journal"))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    cierres.refresh()
    yield tmp_path
    cierres.refresh()


def _seed_store():
    store = marketdata_store.get_store()
    ahora = datetime.now(_TZ)
    hoy_ms = str(int(ahora.timestamp() * 1000))
    ayer_ms = str(int((ahora - timedelta(days=1)).timestamp() * 1000))
    store.update_from_md("MERV - XMEV - GGAL - 24hs", {"LA": {"price": 5100.0, "size": 10, "date": hoy_ms},
                                                        "CL": {"price": 5050.0}, "EV": 2.5e9, "NV": 5e5})
    store.update_from_md("MERV - XMEV - TX26 - 24hs", {"LA": {"price": 1500.0, "size": 10, "date": hoy_ms},
                                                        "CL": {"price": 1490.0}, "BI": [{"price": 1499.0, "size": 100}],
                                                        "OF": [{"price": 1501.0, "size": 200}], "OP": 1495.0, "HI": 1505.0, "LO": 1488.0})
    store.update_from_md("MERV - XMEV - TX26 - CI", {"LA": {"price": 1498.0, "size": 1, "date": hoy_ms}})
    store.update_from_md("MERV - XMEV - YPFD - 24hs", {"LA": {"price": 41000.0, "size": 1, "date": ayer_ms}, "CL": {"price": 40900.0}})
    store.update_from_md("MERV - XMEV - I.MERVAL - 24hs", {"IV": {"price": 2_100_000.0, "date": hoy_ms}})
    store.update_from_md("DLR/ENE26", {"LA": {"price": 1520.5, "size": 5, "date": hoy_ms}, "CL": {"price": 1518.0}})
    return ahora.date()


def _df_bonos(hoy: date) -> pd.DataFrame:
    ts = str(int(datetime.now(_TZ).timestamp() * 1000))
    return pd.DataFrame({
        "symbol": ["MERV - XMEV - TX26 - 24hs", "MERV - XMEV - TX26 - 24hs"],
        "Código": ["TX26j", "TX26"], "Last Price": [1500.0, 1500.0], "Close Price": [1490.0, 1490.0],
        "Variación %": [0.0067, 0.0067], "TIREA": [0.30, 0.321], "TNA": [0.27, 0.28], "TEM": [0.022, 0.0235],
        "Paridad": [0.97, 0.98], "Duration": [0.55, 0.6], "Price Source": ["LA", "LA"], "Price Date": [ts, ts],
        "fecha_hoy": [hoy, hoy],
    })


# ── filas + partición + journal ──────────────────────────────────────────
def test_build_rows_particion_keep_last_y_journal(env, monkeypatch) -> None:
    hoy = _seed_store()
    rows = {r["symbol"]: r for r in hw.build_cierre_rows(_df_bonos(hoy))}
    tx = rows["MERV - XMEV - TX26 - 24hs"]
    assert tx["code"] == "TX26" and tx["plazo"] == "24hs" and tx["opero"] is True
    assert tx["tirea"] == 0.321 and tx["codigo_calc"] == "TX26"        # la base gana sobre la 'j'
    assert tx["bid"] == 1499.0 and tx["offer_size"] == 200 and tx["high"] == 1505.0
    assert rows["MERV - XMEV - TX26 - CI"]["plazo"] == "CI"
    assert rows["MERV - XMEV - YPFD - 24hs"]["opero"] is False           # último de ayer
    assert rows["MERV - XMEV - I.MERVAL - 24hs"]["code"] == "I.MERVAL" and rows["MERV - XMEV - I.MERVAL - 24hs"]["opero"]
    assert rows["DLR/ENE26"]["code"] == "DLR/ENE26" and rows["DLR/ENE26"]["plazo"] == ""
    assert rows["MERV - XMEV - GGAL - 24hs"]["tirea"] is None            # acción: sin métricas
    # guard de operados: pocos → no escribe; force → escribe
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 10_000)
    assert hw._guardar_cierre(str(env), _df_bonos(hoy)) is None
    assert not os.path.isdir(env / "cierres")
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 3)
    res = hw._guardar_cierre(str(env), _df_bonos(hoy))
    assert res and res["opero"] >= 5 and os.path.isfile(res["path"])
    assert res["path"] == hw.cierre_path(str(env), hoy)
    assert os.path.isfile(env / "journal" / f"cierre_{hoy:%Y%m%d}.parquet")
    df = pd.read_parquet(res["path"])
    assert df["symbol"].is_unique and float(df.set_index("symbol").at["MERV - XMEV - GGAL - 24hs", "last"]) == 5100.0
    # keep-last: la recaptura pisa la partición con el print tardío
    store = marketdata_store.get_store()
    store.update_from_md("MERV - XMEV - GGAL - 24hs", {"LA": {"price": 5200.0, "size": 1,
                                                        "date": str(int(datetime.now(_TZ).timestamp() * 1000))}})
    res2 = hw._guardar_cierre(str(env), _df_bonos(hoy))
    df2 = pd.read_parquet(res2["path"])
    assert df2["symbol"].is_unique and float(df2.set_index("symbol").at["MERV - XMEV - GGAL - 24hs", "last"]) == 5200.0
    # el lector lo ve (hoy es la única rueda)
    m = cierres.ensure_loaded()
    assert m is not None and m.fechas == [hoy.isoformat()]
    assert cierres.at("MERV - XMEV - GGAL - 24hs", hoy.isoformat()) == 5200.0
    assert "1 ruedas" in cierres.status_texto()
    # estado() de admin lo muestra
    assert "cierre_completo" in hw.estado()


def test_recaptura(env, monkeypatch) -> None:
    hoy = _seed_store()
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 3)
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": _df_bonos(hoy))
    r = hw.recapturar_cierre()
    assert r["ok"] and r["filas"] >= 6 and os.path.isfile(r["path"])
    assert r.get("acciones_filas", 0) >= 1                              # GGAL operó → parquet de acciones
    assert os.path.isfile(env / hw.ACCIONES_FILENAME)
    # fin de semana → skip
    monkeypatch.setattr(hw, "_now", lambda: datetime(2026, 9, 12, 17, 35, tzinfo=_TZ))
    assert hw.recapturar_cierre()["skipped"] == "fin de semana"
    # base_writer=0 → sólo journal (sin partición nueva)
    monkeypatch.setattr(hw, "_now", lambda: datetime.now(_TZ))
    monkeypatch.setattr(settings, "historico_base_writer", False)
    os.remove(r["path"])
    r2 = hw.recapturar_cierre()
    assert r2["ok"] and r2["path"] is None and not os.path.isfile(r["path"])


def test_autosave_recaptura_programada(env, monkeypatch) -> None:
    llamadas = []
    monkeypatch.setattr(hw, "recapturar_cierre", lambda: llamadas.append(1) or {"ok": True, "filas": 1, "opero": 1})
    monkeypatch.setattr(settings, "historico_recaptura_min", 30)

    async def go():
        a = hw.HistoricoAutosave("17:01")
        loop = asyncio.get_running_loop()
        # disparo hace 40 min → objetivo (disparo + 30) ya pasó → corre ahora
        await a._recaptura(loop, hw._now() - timedelta(minutes=40), True)
        await a._recaptura(loop, hw._now() - timedelta(minutes=40), False)     # sin guardado → no
        monkeypatch.setattr(settings, "historico_recaptura_min", 0)
        await a._recaptura(loop, hw._now() - timedelta(minutes=40), True)      # apagada → no
        return a.last_recaptura
    last = asyncio.run(go())
    assert llamadas == [1] and last["ok"]


# ── matriz y consultas ───────────────────────────────────────────────────
def _escribir(env, fecha: date, filas: list) -> None:
    df = pd.DataFrame(filas)
    for col in ("symbol", "code", "plazo"):
        df[col] = df[col].astype("string")
    hw.escribir_particion(df, str(env), fecha)


def _fila(fecha, sym, code, plazo, last, opero=True, **k):
    return {"fecha_hoy": fecha, "symbol": sym, "code": code, "plazo": plazo, "last": last,
            "close": last * 0.99, "opero": opero, **k}


def test_matriz_consultas_y_vector_ref(env, monkeypatch) -> None:
    dias = _ruedas(8)
    G, T, TC = "MERV - XMEV - GGAL - 24hs", "MERV - XMEV - TX26 - 24hs", "MERV - XMEV - TX26 - CI"
    for i, d in enumerate(dias):
        filas = [_fila(d, T, "TX26", "24hs", 1500.0 + i, tirea=0.30 + i / 100), _fila(d, TC, "TX26", "CI", 1498.0 + i)]
        if i != 3:                                                       # GGAL sin dato el 4º día
            filas.append(_fila(d, G, "GGAL", "24hs", 100.0 + i, opero=(i != 5)))
        _escribir(env, d, filas)
    m = cierres.ensure_loaded()
    assert m is not None and len(m.fechas) == 8 and len(m.simbolos) == 3
    st = cierres.status()
    assert st["loaded"] and st["n_particiones"] == 8 and st["dmin"] == dias[0].isoformat()
    assert cierres.at(G, dias[2].isoformat()) == 102.0 and cierres.at(G, dias[3].isoformat()) is None
    assert cierres.at(T, dias[0].isoformat(), "tirea") == pytest.approx(0.30)
    f, v = cierres.serie(G)
    assert len(f) == 7 and dias[3].isoformat() not in f and v[-1] == 107.0
    f2, v2 = cierres.serie(G, n=3, solo_opero=True)
    assert [x for x in v2] == [104.0, 106.0, 107.0]                     # el 6º día (i=5) no operó
    # ret a 5 ruedas con ancla = última rueda: 5ª anterior con dato
    r = cierres.ret(T, 5, hoy=dias[-1])
    assert r["desde"] == dias[2].isoformat() and r["hasta"] == dias[-1].isoformat()
    assert r["ret"] == pytest.approx(1507.0 / 1502.0 - 1)
    rg = cierres.ret(G, 5, hoy=dias[-1])                                 # salta el hueco: 5 con dato hacia atrás
    assert rg["desde"] == dias[1].isoformat() and rg["px0"] == 101.0
    assert cierres.ret(G, 20, hoy=dias[-1]) is None                      # no hay 20 ruedas
    # vector_ref: sólo plazo 24hs, claves por código, misma semántica que ref_5d
    vec = cierres.vector_ref(5, hoy=dias[-1])
    assert set(vec) == {"TX26", "GGAL"}
    assert vec["TX26"] == (1502.0, dias[2]) and vec["GGAL"] == (101.0, dias[1])
    assert cierres.vector_ref(5, hoy=dias[-1], plazo="CI") == {"TX26": (1500.0, dias[2])}
    # ancla en sábado → viernes (la última rueda): no cuenta el cierre del ancla
    sab = dias[-1] + timedelta(days=(5 - dias[-1].weekday()) % 7 or 7)
    assert cierres.vector_ref(5, hoy=sab)["TX26"] == vec["TX26"]
    # nueva partición → cambia la firma → recarga sola
    d9 = dias[-1] + timedelta(days=3)
    _escribir(env, d9, [_fila(d9, T, "TX26", "24hs", 1510.0)])
    assert len(cierres.ensure_loaded().fechas) == 9 and cierres.at(T, d9.isoformat()) == 1510.0
    # ref_5d de Mercado: la base sigue mandando para los códigos calc (TX26j) y
    # el cierre completo gana donde existe; los símbolos sin base (GGAL) entran
    base_dates = [d.isoformat() for d in dias]
    historico_byma._cache = {"loaded": True, "ver": "t", "by_code": {
        "TX26j": {"base": "TX26", "dates": base_dates, "vals": {"Last Price": [9000.0] * 8}},
        "S31L6": {"base": "S31L6", "dates": base_dates, "vals": {"Last Price": [50.0 + i for i in range(8)]}},
    }}
    historico_byma._ref5d_cache = None
    try:
        out = historico_byma.ref_5d(hoy=d9, ruedas=5)
        assert out["TX26j"] == (1503.0, dias[3]) and out["TX26"] == (1503.0, dias[3])   # cierres gana
        assert out["S31L6"] == (53.0, dias[3])                          # sólo en la base: queda
        assert out["GGAL"] == (102.0, dias[2])                          # sólo en cierres: entra
    finally:
        historico_byma._cache = None
        historico_byma._ref5d_cache = None


# ── backfill desde la base px/tasas ──────────────────────────────────────
def test_importar_base(env, monkeypatch) -> None:
    dias = _ruedas(3)
    ts_ok = "1757600000000"
    rows = []
    for d in dias:
        for cod, tir in (("TX26j", 0.30), ("TX26", 0.32), ("S31L6", 0.35)):
            sym = f"MERV - XMEV - {cod.rstrip('j')} - 24hs"
            rows.append({"symbol": sym, "Código": cod, "Last Price": 100.0 + dias.index(d), "Close Price": 99.0,
                         "Variación %": 0.01, "TIREA": tir, "TNA": 0.28, "TEM": 0.023, "Paridad": 0.98,
                         "Duration": 0.6, "Price Source": "LA" if cod != "S31L6" else "CL",
                         "Price Date": ts_ok if cod != "S31L6" else "", "fecha_hoy": d})
    pd.DataFrame(rows).to_parquet(env / (os.path.splitext(hw.HIST_FILENAME)[0] + ".parquet"), index=False)
    monkeypatch.setattr(settings, "historico_base_writer", False)
    assert cierres.importar_base()["skipped"] == "base_writer=0"
    monkeypatch.setattr(settings, "historico_base_writer", True)
    r = cierres.importar_base()
    assert r["importadas"] == 3
    m = cierres.ensure_loaded()
    assert len(m.fechas) == 3 and set(m.codes) == {"TX26", "S31L6"}
    df = pd.read_parquet(hw.cierre_path(str(env), dias[0]))
    tx = df.set_index("symbol").loc["MERV - XMEV - TX26 - 24hs"]
    assert tx["codigo_calc"] == "TX26" and float(tx["tirea"]) == 0.32     # la base gana sobre la 'j'
    assert bool(tx["opero"]) is False                                       # Price Date de otro día
    assert cierres.importar_base()["importadas"] == 0                       # idempotente
    # prime(): con particiones no re-importa y deja la matriz cargada
    cierres.refresh()
    cierres.prime()
    assert cierres.status()["loaded"]
