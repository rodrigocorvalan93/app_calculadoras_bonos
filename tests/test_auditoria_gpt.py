"""Auditoría externa de eficiencia (30/09, commit fcc335f) — regresiones de la
tanda 1: el trabajo por TICK que se repetía por cliente ahora se comparte.

- /mercado/rows: un render + un gzip por (query, since, seq) para N clientes.
- /excel/v1/snapshot: los bytes gzip se memoizan con el JSON (1 compresión por
  build) y se sirven con Content-Encoding si el cliente acepta.
- /excel/v1/hist: memo (JSON + gzip) por (serie, días, versión de la carga).
- Curvas: el HTML de cada fila se cachea; un tick re-renderiza sólo la suya.
- marketdata_store: copy-on-write del snapshot (una referencia vieja queda
  consistente).
- Posiciones: el link ↻ Cartera y la memoria del último fondo.
"""
from __future__ import annotations

import asyncio
import gzip

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, marketdata_store as mds, pricing, symbols as syms


def _seed(codes, px=100.0):
    store = mds.get_store()
    for i, c in enumerate(codes):
        m = pricing.bond_meta(c) or {}
        p = 90.0 if m.get("moneda") in ("USB", "USD") else px
        for pl in ("24hs", "CI"):
            store.update_from_md(syms.md_symbol(c, pl), {
                "LA": {"price": p, "size": 100, "date": "2026-09-30T14:00:00-03:00"},
                "BI": [{"price": p - 0.1, "size": 1000}], "OF": [{"price": p + 0.1, "size": 1000}],
                "CL": {"price": p - 0.3, "date": "2026-09-29"}, "EV": 1e6 + i, "NV": 1e4 + i})
    return store


@pytest.mark.asyncio
async def test_delta_de_mercado_un_render_y_un_gzip_para_n_clientes(monkeypatch) -> None:
    from backend.main import app
    from backend.routes import curves as rc

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])[:6]
    assert len(codes) >= 3
    store = _seed(codes)
    rc._DELTA_MEMO.clear()
    renders = []
    real = rc._render

    def espia(request, template, **ctx):
        if template == "partials/mercado_rows.html":
            renders.append(len(ctx.get("rows") or []))
        return real(request, template, **ctx)

    monkeypatch.setattr(rc, "_render", espia)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        seq0, _rows, _meta, order = await rc._rows_en_seq("cer", "24hs", True, "native", "byma", "", 0)
        since = store.seq()
        for c in codes[:2]:                                       # tick en 2 bonos
            store.update_from_md(syms.md_symbol(c, "24hs"), {"NV": 77777})
        url = f"/mercado/rows?curve=cer&plazo=24hs&since={since}&order={order}"
        rs = await asyncio.gather(*(ac.get(url) for _ in range(24)))
        assert all(r.status_code == 200 for r in rs)
        assert all(r.headers.get("x-rows") == "2" and "x-full" not in r.headers for r in rs)
        assert len({r.content for r in rs}) == 1 and rs[0].content        # mismo cuerpo para todos
        assert renders == [2]                                             # UN render de 2 filas
        # gzip memoizado: el que acepta gzip recibe los bytes comprimidos, el que no, el HTML
        rg = await ac.get(url, headers={"Accept-Encoding": "gzip"})
        rp = await ac.get(url, headers={"Accept-Encoding": "identity"})
        assert renders == [2]                                             # sigue siendo uno
        assert rp.content == rs[0].content and rp.headers.get("content-encoding") is None
        assert rg.content == rp.content                                   # httpx descomprime
        assert rg.headers.get("vary") == "Accept-Encoding" or rp.content == rg.content
        # otro tick → otra key (nuevo render), el memo no sirve HTML viejo
        since2 = store.seq()
        store.update_from_md(syms.md_symbol(codes[2], "24hs"), {"NV": 88888})
        r2 = await ac.get(f"/mercado/rows?curve=cer&plazo=24hs&since={since2}&order={order}")
        assert r2.headers.get("x-rows") == "1" and renders == [2, 1]


def test_snapshot_excel_memoiza_el_gzip() -> None:
    from backend.routes import excel

    bond_universe.ensure_loaded()
    _seed(curves.build_curve_codes().get("cer", [])[:4])
    excel._cache.clear()
    body, gz = excel._snapshot_entry("")
    assert body[:1] == b"{" and gz is not None and gzip.decompress(gz) == body
    body2, gz2 = excel._snapshot_entry("")
    assert body2 is body and gz2 is gz                                    # misma entrada: sin recomprimir
    assert excel._snapshot_bytes("") is body                              # compat


@pytest.mark.asyncio
async def test_snapshot_y_hist_de_excel_sirven_gzip_si_el_cliente_acepta(monkeypatch) -> None:
    from backend.main import app
    from backend.routes import excel
    from backend.services import historico as historico_svc

    bond_universe.ensure_loaded()
    excel._cache.clear()
    excel._HIST_MEMO.clear()
    builds = []
    real = historico_svc.series_points

    def espia(key, days=None, **kw):
        builds.append((key, days))
        return real(key, days=days, **kw)

    monkeypatch.setattr(historico_svc, "series_points", espia)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        rg = await ac.get("/excel/v1/snapshot", headers={"Accept-Encoding": "gzip"})
        ri = await ac.get("/excel/v1/snapshot", headers={"Accept-Encoding": "identity"})
        assert rg.status_code == 200 and rg.json()["seq"] == ri.json()["seq"]
        assert ri.headers.get("content-encoding") is None
        assert rg.headers.get("content-encoding") == "gzip" or len(rg.content) < 1024
        # hist: un build por (serie, días, versión); gzip para el que acepta
        # (el snapshot también lee series macro: se cuenta desde acá)
        del builds[:]
        h1 = await ac.get("/excel/v1/hist/a3500", headers={"Accept-Encoding": "gzip"})
        h2 = await ac.get("/excel/v1/hist/a3500", headers={"Accept-Encoding": "identity"})
        h3 = await ac.get("/excel/v1/hist/a3500?days=30")
        assert h1.status_code == 200 and h1.json() == h2.json() and h1.json()["serie"]
        assert builds == [(h1.json()["serie"], None), (h1.json()["serie"], 30)]
        assert h2.headers.get("content-encoding") is None
        assert h3.status_code == 200 and len(h3.json()["points"]) <= len(h1.json()["points"])


@pytest.mark.asyncio
async def test_curvas_rerenderiza_solo_las_filas_que_cambiaron() -> None:
    from backend.main import app
    from backend.routes import curves as rc

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])
    store = _seed(codes)
    rc._CROW_MEMO.clear()
    rc._CROW_STATS.update(render=0, hit=0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r1 = await ac.get("/curves/table?curve=cer&plazo=24hs")
        assert r1.status_code == 200 and "<tbody>" in r1.text
        n = r1.text.count("<tr>") - 1                                     # menos el header
        assert n > 0
        primera = dict(rc._CROW_STATS)
        assert primera["render"] >= n and primera["hit"] == 0
        # mismo estado → todo del memo (otra key del seq-cache: ?leg= distinto no, mismo query
        # pega el seq-cache; forzamos con un tick en un bono de OTRA curva)
        otro = curves.build_curve_codes().get("lecap", [])[0]
        store.update_from_md(syms.md_symbol(otro, "24hs"), {"NV": 5})
        r2 = await ac.get("/curves/table?curve=cer&plazo=24hs")
        assert r2.status_code == 200 and r2.text == r1.text
        assert rc._CROW_STATS["render"] == primera["render"] and rc._CROW_STATS["hit"] >= n
        # tick en UN bono de la curva → se re-renderiza sólo esa fila
        store.update_from_md(syms.md_symbol(codes[0], "24hs"), {"LA": {"price": 101.0, "size": 5}})
        antes = dict(rc._CROW_STATS)
        r3 = await ac.get("/curves/table?curve=cer&plazo=24hs")
        assert r3.status_code == 200 and r3.text != r2.text
        assert rc._CROW_STATS["render"] - antes["render"] == 1
        assert rc._CROW_STATS["hit"] - antes["hit"] == n - 1


def test_store_snapshot_copy_on_write() -> None:
    store = mds.MarketDataStore()
    s1 = store.update_from_md("X - 24hs", {"LA": {"price": 90.0}, "BI": [{"price": 89.0, "size": 1}]})
    s2 = store.update_from_md("X - 24hs", {"LA": {"price": 91.0}})
    assert s1 is not s2 and store.get("X - 24hs") is s2
    assert (s1.last, s1.seq) == (90.0, 1) and (s2.last, s2.seq) == (91.0, 2)     # la referencia vieja no cambió
    assert s2.bid == 89.0 and s2.bids == s1.bids                                  # lo sticky se hereda


@pytest.mark.asyncio
async def test_posiciones_conserva_el_fondo_elegido() -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones")
        assert r.status_code == 200
        # ↻ Cartera arma el href con el fondo/plazo seleccionados AHORA (Alpine), no con los de la carga
        assert 'x-model="fondo"' in r.text and 'x-model="plazo"' in r.text
        assert ":href=\"'/posiciones?refresh=1' + (fondo ? '&fondo=' + encodeURIComponent(fondo) : '')" in r.text
        # y recuerda el último fondo mirado (localStorage) al entrar sin ?fondo=
        assert 'localStorage.getItem(KEY)' in r.text and '"pos_fondo"' in r.text


def test_auth_los_lectores_no_esperan_el_disco(monkeypatch) -> None:
    """Copy-on-write del store de auth: un guardado lento (OneDrive / antivirus)
    ya no frena `_store()` — el middleware lo llama en CADA request — y el
    cambio se publica recién cuando es durable (si el disco falla, nada
    cambia en memoria)."""
    import threading
    import time

    from backend.services import auth

    real_save = auth._save_locked
    lento = threading.Event()

    def save_lento(data):
        lento.set()
        time.sleep(0.4)                      # disco lento con el cambio en curso
        real_save(data)

    monkeypatch.setattr(auth, "_save_locked", save_lento)
    antes = list(auth._store()["role_tabs"]["basico"])
    nuevas = [t for t in antes if t != "nueva"] if "nueva" in antes else antes + ["nueva"]
    t = threading.Thread(target=auth.set_role_tabs, args=("basico", nuevas))
    t.start()
    assert lento.wait(2.0)
    # mientras escribe: leer es instantáneo y todavía se ve lo viejo (aún no durable)
    t0 = time.perf_counter()
    visto = list(auth._store()["role_tabs"]["basico"])
    assert (time.perf_counter() - t0) < 0.05
    assert visto == antes
    t.join(5.0)
    assert not t.is_alive() and list(auth._store()["role_tabs"]["basico"]) == nuevas
    # disco roto → la mutación falla y la memoria queda como estaba
    monkeypatch.setattr(auth, "_save_locked", lambda data: (_ for _ in ()).throw(OSError("disco lleno")))
    with pytest.raises(OSError):
        auth.set_role_tabs("basico", antes)
    assert list(auth._store()["role_tabs"]["basico"]) == nuevas
    monkeypatch.setattr(auth, "_save_locked", real_save)
    auth.set_role_tabs("basico", antes)
    assert list(auth._store()["role_tabs"]["basico"]) == antes


def test_cierres_una_particion_ilegible_no_deja_una_matriz_parcial_pegajosa(tmp_path, monkeypatch) -> None:
    """Una partición que falla UNA vez (lock de OneDrive) no publica una matriz
    sin ese día como si estuviera completa: se conserva la íntegra anterior y
    se reintenta; y corregir una partición VIEJA invalida la matriz (mtime de
    la carpeta en la firma)."""
    import os
    from datetime import date

    import pandas as pd
    from backend.services import cierres, historico_writer as hw

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)

    def part(d, last):
        df = pd.DataFrame([{"fecha_hoy": d, "symbol": "MERV - XMEV - TX26 - 24hs", "code": "TX26", "plazo": "24hs",
                            "last": last, "close": last - 1, "opero": True, "tirea": 0.3}])
        for col in ("symbol", "code", "plazo"):
            df[col] = df[col].astype("string")
        return hw.escribir_particion(df, str(tmp_path), d)

    d1, d2, d3 = date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)
    p1 = part(d1, 100.0)
    part(d2, 101.0)
    cierres.refresh()
    m = cierres.ensure_loaded()
    assert m is not None and m.fechas == ["2026-09-23", "2026-09-24"]
    # llega el 25 pero el 24 no se puede leer (una vez)
    p3 = part(d3, 102.0)
    real = pd.read_parquet
    fallar = {"n": 0}

    def read_falla(path, *a, **k):
        if str(path).endswith("2026-09-24.parquet") and fallar["n"] < 1:
            fallar["n"] += 1
            raise OSError("lock")
        return real(path, *a, **k)

    monkeypatch.setattr(pd, "read_parquet", read_falla)
    m2 = cierres.ensure_loaded()
    assert m2 is m and m2.fechas == ["2026-09-23", "2026-09-24"]          # la íntegra anterior, no una sin el 24
    assert cierres._cache["completa"] is True
    # dentro del backoff sigue la anterior; pasado el backoff, reintenta y ahora carga los 3
    assert cierres.ensure_loaded() is m
    cierres._cache["retry_at"] = 0.0
    m3 = cierres.ensure_loaded()
    assert m3 is not m and m3.fechas == ["2026-09-23", "2026-09-24", "2026-09-25"]
    assert cierres._cache["completa"] is True and fallar["n"] == 1
    # corregir una partición VIEJA (reescribirla) cambia la firma aunque la última no cambie
    sig_antes = cierres.signature()
    os.utime(os.path.dirname(p1), None)
    part(d1, 150.0)
    assert cierres.signature() != sig_antes
    m4 = cierres.ensure_loaded()
    assert m4 is not m3 and float(m4.mat["last"][0, 0]) == 150.0
    assert p3.endswith("2026-09-25.parquet")
    cierres.refresh()


def _particion_tx26(d, last):
    import pandas as pd
    df = pd.DataFrame([{"fecha_hoy": d, "symbol": "MERV - XMEV - TX26 - 24hs", "code": "TX26", "plazo": "24hs",
                        "last": last, "close": last - 1, "opero": True, "tirea": 0.3}])
    for col in ("symbol", "code", "plazo"):
        df[col] = df[col].astype("string")
    return df


def test_cierres_firma_memoizada_y_recarga_single_flight(tmp_path, monkeypatch) -> None:
    """`signature()` (la llaman las rutas de Históricos en cada request) no
    relista el árbol de particiones mientras las carpetas por año no cambien;
    una partición nueva lo invalida al instante; y N threads con la firma
    vencida hacen UNA sola lectura de las particiones (single-flight)."""
    import threading
    import time as _t
    from datetime import date

    import pandas as pd
    from backend.services import cierres, historico_writer as hw

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    cierres.refresh()
    hw.escribir_particion(_particion_tx26(date(2026, 9, 23), 100.0), str(tmp_path), date(2026, 9, 23))
    hw.escribir_particion(_particion_tx26(date(2026, 9, 24), 101.0), str(tmp_path), date(2026, 9, 24))
    listados = {"n": 0}
    real_part = cierres.particiones

    def espia(*a, **k):
        listados["n"] += 1
        return real_part(*a, **k)

    monkeypatch.setattr(cierres, "particiones", espia)
    s1 = cierres.signature()
    assert s1[0] == 2 and listados["n"] == 1
    for _ in range(50):
        assert cierres.signature() == s1
    assert listados["n"] == 1                                      # memo: ningún listado más
    hw.escribir_particion(_particion_tx26(date(2026, 9, 25), 102.0), str(tmp_path), date(2026, 9, 25))
    s2 = cierres.signature()
    assert s2 != s1 and s2[0] == 3 and listados["n"] == 2            # el rename tocó la carpeta del año
    # single-flight: 4 threads con la matriz vencida → 3 lecturas (una por partición), una sola matriz
    real_read = pd.read_parquet
    lecturas = {"n": 0}

    def lenta(path, *a, **k):
        lecturas["n"] += 1
        _t.sleep(0.05)
        return real_read(path, *a, **k)

    monkeypatch.setattr(pd, "read_parquet", lenta)
    cierres.refresh()
    res = []
    hilos = [threading.Thread(target=lambda: res.append(cierres.ensure_loaded())) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert lecturas["n"] == 3
    assert res[0] is not None and all(m is res[0] for m in res)
    assert res[0].fechas == ["2026-09-23", "2026-09-24", "2026-09-25"]
    cierres.refresh()


def test_particion_con_temporal_unico_y_catchup_del_cierre_completo(tmp_path, monkeypatch) -> None:
    """Dos escritores simultáneos de la MISMA partición no se pisan el temporal
    (nombre único por escritor) y una escritura fallida no deja `.tmp`
    huérfanos; el journal local del cierre completo repone una partición que
    falta (catch-up al arrancar, writer; respeta `sin_rueda` y base_writer=0)
    y se poda con el resto del journal."""
    import os
    import threading
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    import pandas as pd
    from backend.config import settings
    from backend.services import cierres, historico_writer as hw

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    monkeypatch.setenv("HISTORICO_JOURNAL_DIR", str(tmp_path / "journal"))
    monkeypatch.setattr(settings, "historico_base_writer", True)
    monkeypatch.setattr(hw, "_LOCK_ESPERAS", (0.05, 0.1))
    cierres.refresh()
    assert hw._tmp_de("x.parquet") != hw._tmp_de("x.parquet")
    d = date(2026, 9, 25)
    errores = []

    def escribir(last):
        try:
            hw.escribir_particion(_particion_tx26(d, last), str(tmp_path), d)
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=escribir, args=(100.0 + i,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert not errores
    ydir = os.path.dirname(hw.cierre_path(str(tmp_path), d))
    assert sorted(os.listdir(ydir)) == ["2026-09-25.parquet"]                 # ni .tmp ni parciales
    assert float(pd.read_parquet(hw.cierre_path(str(tmp_path), d))["last"].iloc[0]) in {100.0, 101.0, 102.0, 103.0}
    monkeypatch.setattr(hw, "_LOCK_ESPERAS", ())

    class Rompe:
        def to_parquet(self, path, *a, **k):
            open(path, "wb").close()
            raise OSError("disco lleno")

    with pytest.raises(OSError):
        hw.escribir_particion(Rompe(), str(tmp_path), date(2026, 9, 26))
    assert sorted(os.listdir(ydir)) == ["2026-09-25.parquet"]                 # el temporal se limpió
    # catch-up: un cierre completo journaleado sin partición compartida se repone desde el journal
    d0 = date(2026, 9, 24)
    hw.write_cierre_journal(_particion_tx26(d0, 90.0), d0)
    assert not os.path.isfile(hw.cierre_path(str(tmp_path), d0))
    assert hw.consolidar_cierres_journal() == {"consolidados": 1, "dias": ["2026-09-24"], "errores": {}}
    assert float(pd.read_parquet(hw.cierre_path(str(tmp_path), d0))["last"].iloc[0]) == 90.0
    assert hw.consolidar_cierres_journal() is None                             # nada pendiente → no-op
    d9 = date(2026, 9, 22)                                                     # marcado sin rueda: se respeta
    hw.write_cierre_journal(_particion_tx26(d9, 80.0), d9)
    open(hw._sin_rueda_path(d9), "w").close()
    assert hw.consolidar_cierres_journal() is None
    assert not os.path.isfile(hw.cierre_path(str(tmp_path), d9))
    monkeypatch.setattr(settings, "historico_base_writer", False)             # no-writer: no toca lo compartido
    d8 = date(2026, 9, 21)
    hw.write_cierre_journal(_particion_tx26(d8, 70.0), d8)
    assert hw.consolidar_cierres_journal() is None
    assert not os.path.isfile(hw.cierre_path(str(tmp_path), d8))
    # poda: el cierre completo más viejo que 90 días se va con el resto del journal
    viejo = date(2026, 1, 5)
    hw.write_cierre_journal(_particion_tx26(viejo, 1.0), viejo)
    monkeypatch.setattr(hw, "_now", lambda: datetime(2026, 9, 25, 17, 5, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")))
    hw._prune_journal()
    dias = hw._cierre_journal_days()
    assert viejo not in dias and d0 in dias and d8 in dias
    cierres.refresh()


@pytest.mark.asyncio
async def test_breakeven_un_ctx_por_tick_para_tabla_y_chart(monkeypatch) -> None:
    """Tabla y chart de Breakeven disparan juntos en cada md-update: UN solo
    armado de CER + LECAP + Fisher por (plazo, tildes, seq); un tick nuevo o
    tildes distintos son otra key."""
    from backend.main import app
    from backend.routes import breakeven as rb
    from backend.services import breakeven as be_svc

    bond_universe.ensure_loaded()
    tbl = curves.build_curve_codes()
    cer, lecap = tbl.get("cer", [])[:4], tbl.get("lecap", [])[:4]
    assert cer and lecap
    store = _seed(cer + lecap)
    rb._CTX_MEMO.clear()
    rb._CTX_INFLIGHT.clear()
    llamadas = []
    real = be_svc.compute_fisher

    def espia(*a, **k):
        llamadas.append(1)
        return real(*a, **k)

    monkeypatch.setattr(be_svc, "compute_fisher", espia)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        store.update_from_md(syms.md_symbol(cer[0], "24hs"), {"NV": 12345})
        rs = await asyncio.gather(ac.get("/breakeven/table?plazo=24hs"), ac.get("/breakeven/chart?plazo=24hs"),
                                  ac.get("/breakeven/table?plazo=24hs"))
        assert all(r.status_code == 200 for r in rs)
        assert len(llamadas) == 1                                          # tabla + chart + tabla: un despeje
        store.update_from_md(syms.md_symbol(cer[0], "24hs"), {"NV": 12346})   # tick → otra key
        r = await ac.get("/breakeven/chart?plazo=24hs")
        assert r.status_code == 200 and len(llamadas) == 2
        r1 = await ac.get(f"/breakeven/table?plazo=24hs&incl={cer[0]}&incl_set=1")   # tildes: otra key…
        r2 = await ac.get(f"/breakeven/chart?plazo=24hs&incl={cer[0]}&incl_set=1")   # …compartida entre los dos
        assert r1.status_code == 200 and r2.status_code == 200 and len(llamadas) == 3
