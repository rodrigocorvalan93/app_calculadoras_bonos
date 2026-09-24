"""Cierre perdido + feed caído al cierre (backend/services/historico_writer).

- `_fecha_dato`: ISO sin zona = hora BA; 00:00Z = sello de fecha (CL.date).
- `reconstruir_cierre`: desde los cierres del feed (CL con fecha durante la
  rueda siguiente) y desde la base (Close Price de la rueda siguiente), guards
  (feed que ya pasó de D+1, evidencia de rueda → sin_rueda), filas RC, journal
  del día, fila FX y partición de cierres (opero para RC).
- `huecos_base` / `estado_cierre` (huecos, reconstruible) / `reconstruir_faltantes`.
- `save_today` con el feed muerto: no guarda, avisa (banner + mail 1×/día) y
  reintenta cada 5 min; feriado listado → skip explícito.
- Endpoint POST /historicos/reconstruir-cierre: sólo superuser.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import historico_writer as hw
from backend.services import marketdata_store
from tests.test_historico_writer import _client, auth_on  # noqa: F401 — fixture + helper

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# D = miércoles 23/09/2026 (rueda perdida); D-1 = 22/09, D+1 = 24/09, D+2 = 25/09.
D = date(2026, 9, 23)
D_ANT = date(2026, 9, 22)
D_SIG = date(2026, 9, 24)
SETTLE_D = "24/09/2026"


def _ba(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


def _epoch_ms(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1000))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Carpeta de bases + journal aislados, store de market data NUEVO (los
    otros tests dejan cierres de hoy en el global), autosave sin estado,
    writer, mínimo de operados bajo (3 bonos reales alcanzan)."""
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    monkeypatch.setenv("HISTORICO_JOURNAL_DIR", str(tmp_path / "journal"))
    monkeypatch.setattr(marketdata_store, "_store", marketdata_store.MarketDataStore())
    monkeypatch.setattr(settings, "historico_autosave", True)
    monkeypatch.setattr(settings, "historico_base_writer", True)
    monkeypatch.setattr(settings, "historico_reconstruir", True)
    monkeypatch.setattr(settings, "historico_autosave_hhmm", "17:01")
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 3)
    monkeypatch.setattr(hw, "_autosave", None)
    monkeypatch.setattr(hw, "_ultima_reconstruccion", None)
    hw._fechas_cache = ()
    yield tmp_path
    hw._fechas_cache = ()
    from backend.services import cierres, historico_byma
    historico_byma.refresh()
    cierres.refresh()


def _codigos_calculables(n: int = 3) -> list:
    """Códigos reales de las curvas que pricean a 100 liquidando el 24/09/2026."""
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    out = []
    for key in ("lecap", "cer", "globales", "bonares"):
        for c in curves.build_curve_codes().get(key) or []:
            if c.endswith("j") or c in out:
                continue
            if hw._metricas_a_fecha(c, 100.0, SETTLE_D) is not None:
                out.append(c)
            if len(out) >= n:
                return out
    raise AssertionError("no encontré códigos calculables en las curvas")


def _pesos_de_hard_dollar() -> str | None:
    """Especie en PESOS de un hard-dollar de las curvas (BPCVO / GYC5O / AL30…):
    su fila reconstruida necesita el FX de los cierres."""
    from backend.services import curves, pricing
    for codes in curves.build_curve_codes().values():
        for c in codes or []:
            meta = pricing.bond_meta(c) or {}
            if meta.get("moneda") in ("USD", "USB") and c[-1:] not in ("C", "D") and not c.endswith("j"):
                nat = pricing.native_dollar_code(c)
                if nat and hw._metricas_a_fecha(nat, 60.0, SETTLE_D) is not None:
                    return c
    return None


def _df_base(fecha: date, filas: list, *, source: str = "LA") -> pd.DataFrame:
    """Filas con el esquema de la base: [(code, last, close), …]."""
    from backend.services import symbols as syms
    ts = _epoch_ms(datetime(fecha.year, fecha.month, fecha.day, 16, 30, tzinfo=_TZ))
    return pd.DataFrame({
        "symbol": [syms.md_symbol(c, "24hs") for c, _, _ in filas],
        "Código": [c for c, _, _ in filas],
        "Last Price": [last for _, last, _ in filas],
        "Close Price": [cl for _, _, cl in filas],
        "Variación %": [None] * len(filas),
        "TIREA": [0.3] * len(filas), "TNA": [0.27] * len(filas), "TEM": [0.022] * len(filas),
        "Paridad": [0.98] * len(filas), "Duration": [0.7] * len(filas),
        "Price Source": [source] * len(filas), "Price Date": [ts] * len(filas),
        "fecha_hoy": [fecha] * len(filas),
    })


def _sembrar_cierres(codes: list, dia: date, precio: float = 101.0, hora: int = 17) -> None:
    """CL (cierre previo) fechado `dia` para cada código, como lo manda el
    feed durante la rueda siguiente."""
    from backend.services import symbols as syms
    st = marketdata_store.get_store()
    ts = _epoch_ms(datetime(dia.year, dia.month, dia.day, hora, 5, tzinfo=_TZ))
    for i, c in enumerate(codes):
        st.update_from_md(syms.md_symbol(c, "24hs"), {"CL": {"price": precio + i, "date": ts}})


def _base_parquet(env) -> pd.DataFrame:
    return pd.read_parquet(str(env / hw.HIST_FILENAME).replace(".xlsx", ".parquet"))


# ── parser de fechas del feed ───────────────────────────────────────────────
def test_fecha_dato_sello_de_fecha_y_naive_como_ba() -> None:
    # epoch del cierre (17:05 BA) → ese día; epoch de las 00:00Z → sello de FECHA
    # (no las 21:00 BA del día anterior); ISO sin zona → hora BA, no la del sistema
    assert hw._fecha_dato(_epoch_ms(_ba(2026, 9, 23, 17, 5))) == D
    assert hw._fecha_dato(str(int(datetime(2026, 9, 23, tzinfo=ZoneInfo("UTC")).timestamp() * 1000))) == D
    assert hw._fecha_dato("2026-09-23T00:00:00Z") == D
    assert hw._fecha_dato("2026-09-23") == D
    assert hw._fecha_dato("2026-09-23T14:30:00") == D
    assert hw._fecha_dato("2026-09-23T14:30:00-03:00") == D
    assert hw._fecha_dato("2026-09-24T02:00:00Z") == D          # 23:00 BA del 23
    assert hw._fecha_dato("2026-09-23T03:00:00Z") == D          # 00:00 BA del 23
    assert hw._fecha_dato("") is None and hw._fecha_dato("x") is None


def test_write_journal_por_dia(env) -> None:
    df = _df_base(D, [("T30E6", 100.0, 99.0)])
    p = hw.write_journal(df, D)
    assert os.path.basename(p) == "px_tasas_20260923.parquet" and os.path.isfile(p)
    assert list(hw._journal_days()) == [D]


# ── reconstrucción desde los cierres del feed (rueda D+1) ───────────────────
def test_reconstruir_desde_el_feed(env, monkeypatch) -> None:
    from backend.services import fx as fx_svc
    from backend.services import symbols as syms

    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))      # D+1 a la mañana
    # el feed de D+1 trae el CL de D para los 3 bonos + la canasta líquida (FX de cierres)
    _sembrar_cierres(codes, D)
    st = marketdata_store.get_store()
    base = fx_svc.fx_bases()[0]
    ts_d = _epoch_ms(_ba(2026, 9, 23, 17, 5))
    st.update_from_md(syms.md_symbol(base, "24hs"), {"CL": {"price": 80_000.0, "date": ts_d}})
    st.update_from_md(syms.md_symbol(base + "C", "24hs"), {"CL": {"price": 55.0, "date": ts_d}})
    st.update_from_md(syms.md_symbol(base + "D", "24hs"), {"CL": {"price": 54.0, "date": ts_d}})
    pesos = _pesos_de_hard_dollar()
    if pesos:
        st.update_from_md(syms.md_symbol(pesos, "24hs"), {"CL": {"price": 60.0 * 80_000.0 / 55.0, "date": ts_d}})

    fx = fx_svc.compute_fx_cierres()
    assert abs(fx.ccl - 80_000.0 / 55.0) < 1e-9 and abs(fx.usb - 80_000.0 / 54.0) < 1e-9
    c = hw.cierres_en_store(D)
    assert c["en_dia"] >= 3 and c["posteriores"] == 0 and c["liquidos_en_dia"] == 3

    # antes: el chip reclama D y sabe que se reconstruye desde el feed
    e = hw.estado_cierre()
    assert e["estado"] == "falta" and e["esperado"] == D.isoformat() and e["reconstruible"] == "feed"
    assert "cierres del feed" in e["detalle"]

    res = hw.reconstruir_cierre(D)
    assert res["ok"] is True and res["fuente"] == "feed" and res["rows"] >= 3, res
    back = _base_parquet(env)
    back["fecha_hoy"] = pd.to_datetime(back["fecha_hoy"]).dt.date
    d = back[back["fecha_hoy"] == D].set_index("Código")
    for i, code in enumerate(codes):
        fila = d.loc[code]
        assert fila["Price Source"] == "RC" and fila["Last Price"] == 101.0 + i
        assert fila["Close Price"] == 100.0 + i                       # último de D-1
        assert abs(fila["Variación %"] - ((101.0 + i) / (100.0 + i) - 1.0)) < 1e-12
        assert fila["TIREA"] == fila["TIREA"] and fila["Duration"] > 0   # calculadas de verdad
        assert str(fila["Price Date"]) == ts_d
    if pesos:
        assert pesos in d.index and d.loc[pesos]["TIREA"] == d.loc[pesos]["TIREA"]
        assert res["sin_fx"] == 0
    # la TIR quedó calculada a la liquidación del hábil siguiente de D (24/09),
    # igual que la tabla de Curvas ese día
    from backend.services import pricing
    m = pricing.compute_metrics(code=codes[0], mode="precio", value=101.0, settle=SETTLE_D,
                                include_cashflows=False)
    assert abs(d.loc[codes[0]]["TIREA"] - m["tirea"]) < 1e-12
    # journal del día reconstruido, fila FX del día y partición de cierres (opero por RC)
    assert os.path.isfile(res["journal"]) and res["journal"].endswith("px_tasas_20260923.parquet")
    fxq = pd.read_parquet(str(env / hw.FX_FILENAME).replace(".xlsx", ".parquet"))
    fxq["fecha_hoy"] = pd.to_datetime(fxq["fecha_hoy"]).dt.date
    fila_fx = fxq[fxq["fecha_hoy"] == D].iloc[0]
    assert abs(fila_fx["ccl"] - 80_000.0 / 55.0) < 1e-9 and fila_fx["ccl_base"] == base
    part = pd.read_parquet(hw.cierre_path(str(env), D))
    assert bool(part[part["code"] == codes[0]].iloc[0]["opero"]) is True
    # después: al día, sin huecos; repetir es no-op (la base ya lo tiene)
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["huecos"] == [] and e["reconstruccion"]["ok"] is True
    assert "ya tiene" in hw.reconstruir_cierre(D)["skipped"]


def test_feed_que_ya_paso_de_la_rueda_siguiente_no_sirve(env, monkeypatch) -> None:
    codes = _codigos_calculables(3)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))      # D+2
    _sembrar_cierres(codes, D_SIG)                                          # CL ya del 24/09
    c = hw.cierres_en_store(D)
    assert c["en_dia"] == 0 and c["posteriores"] == 3
    res = hw.reconstruir_cierre(D)
    assert res["ok"] is False and "no hay de dónde" in res["error"] and "3 ya posteriores" in res["error"]
    assert not (env / hw.HIST_FILENAME).exists() and hw._journal_days() == {}


# ── reconstrucción desde la base (Close Price de la rueda siguiente) ───────
def test_reconstruir_desde_la_base(env, monkeypatch) -> None:
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    hw.append_and_save(_df_base(D_SIG, [(c, 105.0 + i, 103.0 + i) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))      # D+2: el feed ya no sirve
    assert hw.huecos_base() == [D]
    e = hw.estado_cierre()
    assert e["estado"] == "ok" and e["huecos"] == [D.isoformat()] and e["hueco_reconstruible"] == "base"
    assert "hueco el 23/09" in e["detalle"]

    res = hw.reconstruir_cierre(D)
    assert res["ok"] is True and res["fuente"] == "base" and res["rows"] == 3, res
    back = _base_parquet(env)
    back["fecha_hoy"] = pd.to_datetime(back["fecha_hoy"]).dt.date
    d = back[back["fecha_hoy"] == D].set_index("Código")
    for i, code in enumerate(codes):
        fila = d.loc[code]
        assert fila["Last Price"] == 103.0 + i and fila["Price Source"] == "RC"
        assert pd.isna(fila["Price Date"]) and fila["Close Price"] == 100.0 + i
    assert sorted(set(back["fecha_hoy"])) == [D_ANT, D, D_SIG]
    assert hw.huecos_base() == [] and hw.estado_cierre()["huecos"] == []


def test_sin_rueda_por_evidencia(env, monkeypatch) -> None:
    """La rueda siguiente trae como cierre previo EXACTAMENTE el último de la
    rueda anterior → en el medio no hubo rueda (feriado no listado): se marca
    sin_rueda y el chip deja de reclamar el día."""
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    hw.append_and_save(_df_base(D_SIG, [(c, 105.0 + i, 100.0 + i) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    assert hw.huecos_base() == [D]
    res = hw.reconstruir_cierre(D)
    assert res["ok"] is False and res["sin_rueda"] is True and "sin rueda" in res["skipped"]
    assert D in hw._sin_rueda_days() and hw.huecos_base() == []
    assert hw.estado_cierre()["huecos"] == []


def test_reconstruir_en_maquina_secundaria_solo_journal(env, monkeypatch) -> None:
    """base_writer=0: la reconstrucción journalea local y no toca la base
    compartida; la segunda vez no recalcula (ya está en el journal); el botón
    (force) escribe la base igual."""
    codes = _codigos_calculables(3)
    monkeypatch.setattr(settings, "historico_base_writer", False)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    _sembrar_cierres(codes, D)
    res = hw.reconstruir_cierre(D)
    assert res["ok"] is True and "sólo journal local" in res["skipped"] and res["rows"] >= 3
    assert list(hw._journal_days()) == [D] and not (env / hw.HIST_FILENAME).exists()
    res2 = hw.reconstruir_cierre(D)
    assert res2["ok"] is True and "ya está en el journal" in res2["skipped"]
    res3 = hw.reconstruir_cierre(D, force=True)
    assert res3["ok"] is True and not res3["skipped"] and (env / hw.HIST_FILENAME).exists()


def test_reconstruir_faltantes_y_boton(env, monkeypatch) -> None:
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    hw.append_and_save(_df_base(D_SIG, [(c, 105.0 + i, 103.0 + i) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    # apagada por config → no toca nada (el botón, con force, sí)
    monkeypatch.setattr(settings, "historico_reconstruir", False)
    assert hw.reconstruir_faltantes()["skipped"] == "historico_reconstruir=0"
    monkeypatch.setattr(settings, "historico_reconstruir", True)
    r = hw.reconstruir_faltantes()
    assert r["huecos"] == [D.isoformat()] and r["reconstruidos"] == [D.isoformat()] and r["pendientes"] == []
    assert hw.reconstruir_faltantes()["huecos"] == []


@pytest.mark.asyncio
async def test_http_banner_hueco_y_reconstruir(env, monkeypatch) -> None:
    from backend.main import app

    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    hw.append_and_save(_df_base(D_SIG, [(c, 105.0 + i, 103.0 + i) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/cierre/chip")
        assert 'data-state="ok"' in r.text and "hueco el 23/09/2026" in r.text
        assert 'hx-post="/historicos/reconstruir-cierre"' in r.text and "Reconstruir 23/09" in r.text
        assert '"dia": "2026-09-23"' in r.text
        r = await ac.post("/historicos/reconstruir-cierre", data={"dia": "2026-09-23"})
        assert r.status_code == 200 and "reconstruido desde la rueda siguiente" in r.text and "3 filas RC" in r.text
        r = await ac.get("/cierre/chip")
        assert "Reconstruir" not in r.text and "hueco" not in r.text
        r = await ac.post("/historicos/reconstruir-cierre", data={"dia": "no-es-fecha"})
        assert r.status_code == 400
        r = await ac.post("/historicos/reconstruir-cierre")           # sin día: todos los huecos
        assert r.status_code == 200 and "no tiene huecos" in r.text


@pytest.mark.asyncio
async def test_reconstruir_cierre_solo_superuser(auth_on, monkeypatch) -> None:  # noqa: F811
    llamadas = []
    monkeypatch.setattr(hw, "reconstruir_cierre", lambda dia, force=False: llamadas.append(dia) or {
        "ok": True, "dia": dia.isoformat(), "dia_fmt": dia.strftime("%d/%m/%Y"), "fuente": "feed",
        "rows": 400, "total_rows": 9000, "sin_fx": 0, "skipped": None, "error": None})
    async with _client() as ac:
        r = await ac.post("/historicos/reconstruir-cierre", data={"dia": "2026-09-23"})
        assert r.status_code in (302, 401)                            # sin sesión → al login
    async with _client() as su:
        r = await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!",
                                          "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123",
                                                "role": "basico", "email": ""})
        assert r.status_code < 400, r.text[:200]
        r = await su.post("/historicos/reconstruir-cierre", data={"dia": "2026-09-23"})
        assert r.status_code == 200 and "23/09/2026 reconstruido desde los cierres del feed" in r.text
        assert llamadas == [D]
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123", "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await ac.post("/historicos/reconstruir-cierre", data={"dia": "2026-09-23"})
        assert r.status_code == 403 and llamadas == [D]


# ── autosave con el feed caído ──────────────────────────────────────────────
def test_feed_estado_sin_broker_es_vivo(monkeypatch) -> None:
    monkeypatch.setattr(settings, "primary_user", "")
    assert hw._feed_estado() == (True, "")
    # broker configurado y WS sin conectar → muerto (nunca logueó / sesión caída)
    monkeypatch.setattr(settings, "primary_user", "usuario-de-test")
    vivo, motivo = hw._feed_estado()
    assert vivo is False and "desconectado" in motivo
    assert hw._intervalo_reintento({"feed_muerto": motivo}) == 300.0
    assert hw._intervalo_reintento({"error": "xlsx lockeado"}) == 600.0


@pytest.mark.asyncio
async def test_save_today_con_feed_caido_avisa_y_reintenta(env, monkeypatch) -> None:
    from backend.main import app

    hoy = D_SIG                                                             # jueves 24/09/2026
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 1))
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": _df_base(hoy, [("T30E6", 101.5, 100.0)]))
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 1)
    monkeypatch.setattr(hw, "_feed_estado", lambda: (False, "WS del broker desconectado"))
    res = hw.save_today()
    assert res["ok"] is False and res["retry"] is True and res["feed_muerto"] == "WS del broker desconectado"
    assert "feed caído" in res["skipped"] and res["dia"] == hoy.isoformat()
    assert hw._journal_days() == {} and not (env / hw.HIST_FILENAME).exists()   # nada guardado
    assert hw._intervalo_reintento(res) == 300.0
    # el estado del cierre lo cuenta: chip "pendiente · feed caído" + banner del superuser
    hw._autosave = SimpleNamespace(last_result=res)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 6))
    e = hw.estado_cierre()
    assert e["estado"] == "pendiente" and e["texto"] == "⏳ cierre pendiente · feed caído"
    assert e["feed_muerto"] == "WS del broker desconectado" and e["hasta"] == "18:36" and e["reintento_min"] == 5
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/cierre/chip")
        assert "Feed caído al cierre" in r.text and "Guardar igual" in r.text and "cada 5 min" in r.text
        # fuera de la ventana → falta, con el motivo real (no "¿estaba cerrada?")
        monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 19, 0))
        e = hw.estado_cierre()
        assert e["estado"] == "falta" and "feed estaba caído" in e["detalle"]
        r = await ac.get("/cierre/chip")
        assert "el feed estaba caído" in r.text and "Guardar ahora" in r.text
    # a la mañana siguiente el esperado sigue siendo el 24 → el motivo se mantiene;
    # pasadas las 17:01 del 25 el esperado es el 25 y el intento de ayer ya no aplica
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    e = hw.estado_cierre()
    assert e["estado"] == "falta" and e["esperado"] == "2026-09-24" and e["feed_muerto"]
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 19, 0))
    e = hw.estado_cierre()
    assert e["esperado"] == "2026-09-25" and e["feed_muerto"] is None and "app estaba cerrada" in e["detalle"]
    # el feed vuelve → guarda normal
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 11))
    monkeypatch.setattr(hw, "_feed_estado", lambda: (True, ""))
    res = hw.save_today()
    assert res["ok"] is True and res["rows"] == 1
    # `force` (botón "Guardar igual") ignora el guard del feed
    monkeypatch.setattr(hw, "_feed_estado", lambda: (False, "WS del broker desconectado"))
    assert hw.save_today(force=True)["ok"] is True


def test_save_today_feriado_del_calendario(env, monkeypatch) -> None:
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 12, 8, 17, 1))     # martes, Inmaculada
    monkeypatch.setattr(hw, "_feed_estado", lambda: (False, "WS del broker desconectado"))
    res = hw.save_today()
    assert res["skipped"] == "feriado (calendario AR)" and not res.get("retry")


def test_aviso_feed_muerto_mail_una_vez_por_dia(env, monkeypatch) -> None:
    from backend.services import mailer

    enviados = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "default_recipient", lambda: "ops@test")
    monkeypatch.setattr(mailer, "send", lambda to, subject, body, attachments=None:
                        enviados.append((to, subject, body)) or (True, "ok"))
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 1))
    res = {"feed_muerto": "WS del broker desconectado", "retry": True, "skipped": "feed caído"}
    ok, detalle = hw.avisar_feed_muerto_mail(res, "17:01")
    assert ok and enviados[0][0] == "ops@test" and "feed caído" in enviados[0][1]
    assert "18:36" in enviados[0][2] and "5 min" in enviados[0][2]

    async def go():
        a = hw.HistoricoAutosave("17:01")
        loop = asyncio.get_running_loop()
        await a._avisar_feed_muerto(loop, res)
        await a._avisar_feed_muerto(loop, res)          # mismo día → no repite
        return a
    asyncio.run(go())
    assert len(enviados) == 2                           # el directo de arriba + 1 del daemon
    # sin SMTP → (False, motivo), nunca lanza
    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    assert hw.avisar_feed_muerto_mail(res)[0] is False


def test_reconstruir_al_arrancar_espera_el_feed(env, monkeypatch) -> None:
    """Daemon al boot: hay hueco → espera los cierres del feed (poll) y
    reconstruye; sin hueco no espera nada."""
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    monkeypatch.setattr(settings, "primary_user", "usuario-de-test")
    monkeypatch.setattr(hw, "_ESPERA_SNAPSHOT_S", 5.0)
    polls = []
    real = hw.cierres_en_store

    def contar(dia, plazo="24hs"):
        polls.append(dia)
        if len(polls) == 2:                              # el snapshot "llega" en el 2º poll
            _sembrar_cierres(codes, D)
        return real(dia, plazo)
    monkeypatch.setattr(hw, "cierres_en_store", contar)

    async def go():
        a = hw.HistoricoAutosave("17:01")
        loop = asyncio.get_running_loop()
        # acortar el sleep entre polls
        orig_wait_for = asyncio.wait_for

        async def rapido(coro, timeout):
            return await orig_wait_for(coro, timeout=min(timeout, 0.05))
        monkeypatch.setattr(hw.asyncio, "wait_for", rapido)
        await a._reconstruir_al_arrancar(loop)
        return a.last_reconstruccion
    r = asyncio.run(go())
    assert r and r["reconstruidos"] == [D.isoformat()] and len(polls) >= 2
    assert hw.huecos_base() == []
