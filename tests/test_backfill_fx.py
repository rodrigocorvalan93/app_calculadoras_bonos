"""backend.tools.backfill_fx: completar CCL/MEP/canje hacia atrás sin pisar lo
que grabó la app (fechas anteriores, huecos opcionales), con dry-run, respaldo
y el mismo camino de escritura del autosave (historico_writer.escribir_fx)."""
from __future__ import annotations

import os
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services import espejo, fx_hist, historico_writer as hw
from backend.tools import backfill_fx as bf


def _payload(dias, base, paso=1.0, solo=None):
    out = []
    for i, d in enumerate(dias):
        v = base + i * paso
        it = {"casa": "x", "fecha": d.isoformat(), "compra": v - 2, "venta": v + 2}
        if solo == "compra":
            it.pop("venta")
        out.append(it)
    return out


def test_parsear_argentinadatos_promedio_habiles_y_canje() -> None:
    lun, mar, sab = date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 8)
    ccl = _payload([lun, mar, sab], 1500.0) + [{"fecha": "basura", "compra": 1}, {"fecha": lun.isoformat()}, "x"]
    mep = [{"fecha": lun.isoformat(), "compra": 1450.0, "venta": 1454.0},
           {"fecha": mar.isoformat(), "compra": 1460.0},                       # sólo un lado
           {"fecha": sab.isoformat(), "compra": 1.0, "venta": 1.0}]
    df = bf.parsear_argentinadatos(ccl, mep)
    assert df["fecha_hoy"].tolist() == [lun, mar]                              # sábado afuera, basura afuera
    assert df.iloc[0]["ccl"] == 1500.0 and df.iloc[0]["mep"] == 1452.0        # promedio compra/venta
    assert df.iloc[1]["mep"] == 1460.0                                         # un solo lado: ese
    assert df.iloc[0]["canje"] == pytest.approx(1500.0 / 1452.0 - 1)
    # sin MEP ese día → canje None
    df2 = bf.parsear_argentinadatos(_payload([lun], 1500.0), [])
    assert df2.iloc[0]["mep"] is None or pd.isna(df2.iloc[0]["mep"])
    assert df2.iloc[0]["canje"] is None or pd.isna(df2.iloc[0]["canje"])


def test_importar_csv_es_ar(tmp_path) -> None:
    p = tmp_path / "fx.csv"
    p.write_text("Fecha;CCL;MEP\n03/08/2026;1.500,50;1.452,25\n2026-08-04;1510;1460\n08/08/2026;1;1\nbasura;;\n",
                 encoding="utf-8")
    df = bf.importar_csv(str(p))
    assert df["fecha_hoy"].tolist() == [date(2026, 8, 3), date(2026, 8, 4)]   # 08/08 es sábado
    assert df.iloc[0]["ccl"] == 1500.5 and df.iloc[0]["mep"] == 1452.25
    assert df.iloc[0]["canje"] == pytest.approx(1500.5 / 1452.25 - 1)


def _habiles(desde: date, n: int):
    out, d = [], desde
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture()
def hist_app(tmp_path, monkeypatch):
    """Historial FX que grabó la APP: 3 días hábiles (con un hueco en el medio),
    con caución y todo, escrito por el mismo _guardar_fx del autosave."""
    from backend.services import cauciones, dolares, fx as fx_svc

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    dias = _habiles(date(2026, 9, 7), 4)
    app_dias = [dias[0], dias[2], dias[3]]                       # dias[1] es un hueco
    monkeypatch.setattr(dolares, "official_fx", lambda: {"last": 1350.0})
    monkeypatch.setattr(cauciones, "hist_row", lambda moneda="PESOS": (
        {"plazo_d": 1, "tna": 31.0, "vwap": 30.9, "monto": 5e9} if moneda == "PESOS" else None))
    for i, d in enumerate(app_dias):
        monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs", i=i: SimpleNamespace(
            ccl=1600.0 + i, usb=1560.0 + i, canje=(1600.0 + i) / (1560.0 + i) - 1, ccl_base="GD30"))
        monkeypatch.setattr(hw, "_now", lambda d=d: pd.Timestamp(d).to_pydatetime().replace(hour=17, minute=1))
        assert hw._guardar_fx(str(tmp_path))["filas"] == i + 1
    fx_hist.refresh()
    yield {"dir": tmp_path, "dias": dias, "app_dias": app_dias}
    fx_hist.refresh()


def _externo(dias, base=1500.0):
    return bf.parsear_argentinadatos(_payload(dias, base), _payload(dias, base - 40.0))


def test_planificar_solo_antes_de_la_app_y_huecos(hist_app) -> None:
    dias, app_dias = hist_app["dias"], hist_app["app_dias"]
    previos = _habiles(date(2026, 8, 24), 8)                    # 2 semanas antes
    ext = _externo(previos + dias + [dias[-1] + timedelta(days=3)])   # antes + rango de la app + después
    previo = bf._leer_previo(str(hist_app["dir"] / hw.FX_FILENAME), str(hist_app["dir"] / hw.FX_FILENAME.replace(".xlsx", ".parquet")), escribir=False)
    plan = bf.planificar(ext, previo)
    assert plan["primera_app"] == app_dias[0] and plan["n_app"] == 3
    assert plan["nuevas"]["fecha_hoy"].tolist() == previos                  # sólo anteriores
    assert plan["empalme"]["fecha_ext"] == previos[-1] and plan["empalme"]["fecha_app"] == app_dias[0]
    assert plan["empalme"]["ccl_app"] == 1600.0
    plan2 = bf.planificar(ext, previo, huecos=True)
    assert plan2["huecos"] == 1 and plan2["nuevas"]["fecha_hoy"].tolist() == previos + [dias[1]]
    for d in app_dias:                                                       # jamás una fecha que la app ya tiene
        assert d not in set(plan2["nuevas"]["fecha_hoy"])
    plan3 = bf.planificar(ext, previo, desde=previos[4], hasta=previos[6])
    assert plan3["nuevas"]["fecha_hoy"].tolist() == previos[4:7]
    assert bf.planificar(ext, None)["nuevas"]["fecha_hoy"].tolist() == ext["fecha_hoy"].tolist()


def test_dry_run_no_toca_nada(hist_app, capsys) -> None:
    xlsx = hist_app["dir"] / hw.FX_FILENAME
    pq = hist_app["dir"] / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    antes = (xlsx.read_bytes(), pq.read_bytes(), sorted(os.listdir(hist_app["dir"])))
    ext = _externo(_habiles(date(2026, 8, 24), 5))
    plan = bf.aplicar(str(hist_app["dir"]), ext, "argentinadatos", dry_run=True)
    bf._print_plan(plan, "argentinadatos")
    out = capsys.readouterr().out
    assert plan["insertadas"] == 5 and plan["dry_run"] and "backups" not in plan
    assert "entrarían 5 fechas" in out and "dry-run: no se escribió nada" in out and "empalme:" in out
    assert f"historial: {xlsx}" in out and "todavía no existe" not in out   # muestra QUÉ archivo tocaría
    assert (xlsx.read_bytes(), pq.read_bytes(), sorted(os.listdir(hist_app["dir"]))) == antes


def test_aplicar_no_pisa_a_la_app_respalda_y_firma(hist_app, monkeypatch) -> None:
    d = hist_app["dir"]
    xlsx, pq = d / hw.FX_FILENAME, d / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    app_antes = pd.read_parquet(pq)
    previos = _habiles(date(2026, 8, 24), 8)
    ext = _externo(previos + hist_app["dias"])                  # trae también las fechas de la app con OTROS valores
    plan = bf.aplicar(str(d), ext, "argentinadatos", huecos=True)
    assert plan["insertadas"] == 9 and len(plan["backups"]) == 2
    assert all(os.path.isfile(b) for b in plan["backups"])
    assert pd.read_parquet(plan["backups"][1]).equals(app_antes)            # el respaldo es el archivo previo
    back = pd.read_parquet(pq)
    back["fecha_hoy"] = pd.to_datetime(back["fecha_hoy"]).dt.date
    assert len(back) == 12 and back["fecha_hoy"].is_monotonic_increasing and not back["fecha_hoy"].duplicated().any()
    # las filas de la app quedaron EXACTAMENTE igual (incluida la caución)
    for _, r in app_antes.iterrows():
        f = pd.Timestamp(r["fecha_hoy"]).date()
        n = back[back["fecha_hoy"] == f].iloc[0]
        assert n["ccl"] == r["ccl"] and n["mep"] == r["mep"] and n["ccl_base"] == "GD30"
        assert n["caucion_tna"] == 31.0 and n["oficial_a3500"] == 1350.0
    # las externas: valores de la fuente, canje = ccl/mep − 1, trazabilidad, sin caución
    e = back[back["fecha_hoy"] == previos[0]].iloc[0]
    assert e["ccl"] == 1500.0 and e["mep"] == 1460.0 and e["canje"] == pytest.approx(1500.0 / 1460.0 - 1)
    assert e["ccl_base"] == "ext:argentinadatos" and pd.isna(e["caucion_tna"]) and pd.isna(e["oficial_a3500"])
    hueco = back[back["fecha_hoy"] == hist_app["dias"][1]].iloc[0]
    assert hueco["ccl_base"] == "ext:argentinadatos"
    assert list(back.columns[:6]) == ["fecha_hoy", "ccl", "mep", "canje", "oficial_a3500", "ccl_base"]
    # el espejo quedó firmado (la app lo lee del parquet) y la pestaña ve la serie completa
    assert espejo.espejo_valido(str(pq), str(xlsx))
    fx_hist.refresh()
    st = fx_hist.status()
    assert st["n"] == 12 and st["series"]["ccl"]["n"] == 12 and st["series"]["caucion_tna"]["n"] == 3
    assert st["dmin"] == previos[0].isoformat()
    # ...y de acá en más la app sigue grabando encima sin perder nada
    from backend.services import cauciones, dolares, fx as fx_svc
    nuevo = hist_app["dias"][-1] + timedelta(days=1)
    monkeypatch.setattr(dolares, "official_fx", lambda: {"last": 1351.0})
    monkeypatch.setattr(cauciones, "hist_row", lambda moneda="PESOS": None)
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": SimpleNamespace(ccl=1610.0, usb=1570.0, canje=1610.0 / 1570.0 - 1, ccl_base="GD30"))
    monkeypatch.setattr(hw, "_now", lambda: pd.Timestamp(nuevo).to_pydatetime().replace(hour=17, minute=1))
    assert hw._guardar_fx(str(d))["filas"] == 13
    back2 = pd.read_parquet(pq)
    assert back2.iloc[0]["ccl_base"] == "ext:argentinadatos" and back2.iloc[-1]["ccl"] == 1610.0
    # segunda corrida del backfill: no hay nada nuevo → no escribe ni respalda
    plan2 = bf.aplicar(str(d), ext, "argentinadatos", huecos=True)
    assert plan2["insertadas"] == 0 and "backups" not in plan2


def test_sin_historial_previo_crea_el_archivo(tmp_path) -> None:
    ext = _externo(_habiles(date(2026, 8, 24), 3))
    plan = bf.aplicar(str(tmp_path), ext, "csv")
    assert plan["insertadas"] == 3 and plan["primera_app"] is None and plan["backups"] == []
    back = pd.read_parquet(tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet"))
    assert len(back) == 3 and set(back["ccl_base"]) == {"ext:csv"}
    assert (tmp_path / hw.FX_FILENAME).exists()


def test_main_argentinadatos_con_red_simulada(tmp_path, monkeypatch, capsys) -> None:
    import requests

    dias = _habiles(date(2026, 8, 24), 4)

    class _Resp:
        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    class _Session:
        headers: dict = {}

        def get(self, url, **kw):
            assert url.startswith(bf._AD_BASE) and kw.get("timeout")
            return _Resp(_payload(dias, 1500.0) if url.endswith("contadoconliqui") else _payload(dias, 1460.0))

    monkeypatch.setattr(requests, "Session", _Session)
    assert bf.main(["--argentinadatos", "--destino", str(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "entrarían 4 fechas" in out and "dry-run" in out and not (tmp_path / hw.FX_FILENAME).exists()
    assert f"carpeta: {tmp_path}" in out and "todavía no existe: se crea" in out   # dónde escribiría
    assert bf.main(["--argentinadatos", "--destino", str(tmp_path)]) == 0
    assert (tmp_path / hw.FX_FILENAME).exists()
    assert bf.main(["--destino", str(tmp_path)]) == 2                       # sin fuente: ayuda
    assert bf.main(["--csv", "no-existe.csv", "--destino", str(tmp_path)]) == 1


def test_historial_ilegible_aborta(tmp_path) -> None:
    (tmp_path / hw.FX_FILENAME).write_bytes(b"xlsx corrupto (sintetico)")
    pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    pq.write_bytes(b"parquet corrupto (sintetico)")
    ext = _externo(_habiles(date(2026, 8, 24), 3))
    with pytest.raises(RuntimeError):
        bf.aplicar(str(tmp_path), ext, "csv", dry_run=True)
    with pytest.raises(RuntimeError):
        bf.aplicar(str(tmp_path), ext, "csv")
    assert (tmp_path / hw.FX_FILENAME).read_bytes() == b"xlsx corrupto (sintetico)"
    assert pq.read_bytes() == b"parquet corrupto (sintetico)"
