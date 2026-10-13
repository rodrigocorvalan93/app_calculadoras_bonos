"""Históricos · Base (13/10): ver y bajar los archivos de Delta Bases.

`services/base_export` + rutas `/historicos/base` (pestaña lazy),
`/historicos/base/archivo` (xlsx / parquet tal cual), `/historicos/base/cierre`
(una partición, parquet o CSV) y `/historicos/base.csv` (la base filtrada en
CSV es-AR). Base armada por el writer (xlsx + espejo + firma) en un tmp."""
from __future__ import annotations

import statistics
import time
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import base_export, cierres, fx_hist, historico_byma
from backend.services import historico_writer as hw


def _rows_df(fecha: date, px: float = 101.5) -> pd.DataFrame:
    ts = str(int(datetime(fecha.year, fecha.month, fecha.day, 16, 59).timestamp() * 1000))
    return pd.DataFrame({
        "symbol": ["MERV - XMEV - T30E6 - 24hs", "MERV - XMEV - AL30D - 24hs"],
        "Código": ["T30E6", "AL30D"],
        "Last Price": [px, 68.25],
        "Close Price": [100.0, 68.0],
        "Variación %": [0.015, 0.0037],
        "TIREA": [0.321, 0.1055],
        "TNA": [0.28, 0.10],
        "TEM": [0.0235, 0.0083],
        "Paridad": [0.98, 0.70],
        "Duration": [0.6, 2.4],
        "Price Source": ["LA", "CL"],
        "Price Date": [ts, ts],
        "fecha_hoy": [fecha, fecha],
    })


@pytest.fixture()
def bases(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    xlsx = str(tmp_path / hw.HIST_FILENAME)
    dias = [date(2026, 10, 5) + timedelta(days=i) for i in range(5)]   # lunes a viernes
    for i, d in enumerate(dias):
        hw.append_and_save(_rows_df(d, 100.0 + i), xlsx)
    fx = pd.DataFrame({"fecha_hoy": dias, "ccl": [1400.0 + i for i in range(5)],
                       "mep": [1390.0 + i for i in range(5)], "canje": [0.007] * 5,
                       "oficial_a3500": [1300.0] * 5, "ccl_base": ["AL30"] * 5})
    fx.to_parquet(tmp_path / "Delta - historico_fx.parquet", index=False)
    for i, d in enumerate(dias):
        df = pd.DataFrame([{"fecha_hoy": d, "symbol": "MERV - XMEV - AL30D - 24hs", "code": "AL30D", "plazo": "24hs",
                            "last": 68.0 + i / 10, "close": 67.9 + i / 10, "opero": True, "tirea": 0.105},
                           {"fecha_hoy": d, "symbol": "MERV - XMEV - AL30C - 24hs", "code": "AL30C", "plazo": "24hs",
                            "last": 66.5 + i / 10, "close": 66.4 + i / 10, "opero": True, "tirea": None}])
        for col in ("symbol", "code", "plazo"):
            df[col] = df[col].astype("string")
        hw.escribir_particion(df, str(tmp_path), d)
    pd.DataFrame({"fecha_hoy": dias, "ticker": ["GGAL"] * 5, "ultimo": [5000.0] * 5}).to_parquet(
        tmp_path / hw.ACCIONES_FILENAME, index=False)
    base_export.invalidar()
    fx_hist.refresh()
    cierres.refresh()
    historico_byma.refresh()
    from backend.routes import historico as rh
    rh._BASE_CACHE.clear()
    yield tmp_path, dias
    base_export.invalidar()
    fx_hist.refresh()
    cierres.refresh()
    historico_byma.refresh()
    rh._BASE_CACHE.clear()


# ── servicio ─────────────────────────────────────────────────────────────────
def test_archivos_describe_los_cuatro_origenes(bases) -> None:
    tmp, dias = bases
    a = base_export.archivos()
    assert a["configurado"] and a["hist_dir"] == str(tmp)
    px = a["px"]
    assert px["xlsx"]["existe"] and px["parquet"]["existe"] and px["espejo_fiel"]
    assert px["ruedas"] == 5 and px["filas"] == 10 and px["reales"] == 10
    assert px["desde"] == "05/10/2026" and px["hasta"] == "09/10/2026"
    assert px["xlsx"]["bytes"] > 0 and "/10/2026" in px["xlsx"]["mtime"]
    assert a["fx"]["n"] == 5 and a["fx"]["parquet"]["existe"] and not a["fx"]["xlsx"]["existe"]
    ci = a["cierres"]
    assert ci["n"] == 5 and ci["desde"] == "05/10/2026" and ci["hasta"] == "09/10/2026" and ci["bytes"] > 0
    assert ci["fechas"][0] == "2026-10-09"                       # más nuevas primero
    assert a["acciones"]["existe"]
    assert base_export.fmt_bytes(15 * 1024 ** 2 + 300000) == "15,3 MB" and base_export.fmt_bytes(512) == "512 B"


def test_archivo_y_particion_descargables_solo_por_clave_cerrada(bases) -> None:
    tmp, dias = bases
    path, nombre, media = base_export.archivo_descargable("px_xlsx")
    assert path == str(tmp / hw.HIST_FILENAME) and nombre == hw.HIST_FILENAME and "spreadsheet" in media
    assert base_export.archivo_descargable("px_parquet")[0].endswith(".parquet")
    assert base_export.archivo_descargable("fx_xlsx") is None            # no existe el xlsx de FX
    assert base_export.archivo_descargable("fx_parquet") is not None
    assert base_export.archivo_descargable("../secrets.txt") is None
    assert base_export.archivo_descargable("") is None
    p, n = base_export.particion_descargable("2026-10-07")
    assert p == hw.cierre_path(str(tmp), date(2026, 10, 7)) and n == "2026-10-07.parquet"
    assert base_export.particion_descargable("2026-10-11") is None      # sábado: no hay
    assert base_export.particion_descargable("../2026-10-07") is None


def test_vista_filtra_por_codigo_y_rango_y_formatea_es_ar(bases) -> None:
    v = base_export.vista()
    assert v["ok"] and v["filas_base"] == 10 and v["total"] == 10 and v["n"] == 10
    assert v["desde_base"] == "05/10/2026" and v["hasta_base"] == "09/10/2026"
    assert v["codigos"] == ["AL30D", "T30E6"]
    assert v["columnas"] == [c for c in base_export.COLUMNAS if c not in ("Pata", "FX")]   # base sin patas
    f0 = v["filas"][0]                                            # más nueva primero
    assert f0["fecha_hoy"] == "09/10/2026" and f0["Código"] in ("AL30D", "T30E6")
    v = base_export.vista("t30e6", "2026-10-06", "2026-10-08", n=2)
    assert v["total"] == 3 and v["n"] == 2
    assert [f["fecha_hoy"] for f in v["filas"]] == ["08/10/2026", "07/10/2026"]
    f = v["filas"][0]
    assert f["Código"] == "T30E6" and f["Last Price"] == "103,00" and f["TIREA"] == "32,10%"
    assert f["Variación %"] == "1,50%" and f["Price Source"] == "LA" and f["Price Date"].startswith("08/10 ")
    assert base_export.vista("ZZZZ")["total"] == 0


def test_csv_base_es_ar_con_bom_y_filtro(bases) -> None:
    texto, n = base_export.csv_base("AL30D", "2026-10-08", None)
    assert n == 2 and texto.startswith("﻿")
    lineas = texto.lstrip("﻿").split("\r\n")
    assert lineas[0].split(";")[:3] == ["fecha_hoy", "Código", "symbol"]
    assert lineas[1].startswith("08/10/2026;AL30D;MERV - XMEV - AL30D - 24hs;68,25;68;")   # %.10g: 68.0 → 68
    assert "0,1055" in lineas[1]
    assert base_export.nombre_csv("base_px_tasas", "al30d", "2026-10-08", None) == "base_px_tasas_AL30D_2026-10-08.csv"
    assert base_export.nombre_csv("base_px_tasas") == "base_px_tasas.csv"
    todo, n2 = base_export.csv_base()
    assert n2 == 10 and todo.count("\r\n") == 11
    # un texto con punto (Price Date ISO con fracción) no se toca: sólo el decimal entre dígitos
    import pandas as pd
    df = pd.DataFrame({"fecha_hoy": pd.to_datetime(["2026-10-08"]), "Código": pd.Categorical(["X.1"]),
                       "Last Price": [1.5], "Price Date": ["2026-10-08T16:59:00.123"]})
    s = base_export._to_csv_es_ar(df)
    assert s.split("\r\n")[1] == "08/10/2026;X.1;1,5;2026-10-08T16:59:00.123"


def test_frame_se_lee_una_vez_por_firma(bases, monkeypatch) -> None:
    tmp, dias = bases
    llamadas = []
    real = base_export._leer_frame
    monkeypatch.setattr(base_export, "_leer_frame", lambda x: (llamadas.append(x), real(x))[1])
    base_export.invalidar()
    base_export.vista()
    base_export.vista("T30E6")
    assert len(llamadas) == 1
    hw.append_and_save(_rows_df(date(2026, 10, 13), 150.0), str(tmp / hw.HIST_FILENAME))   # nueva rueda → nueva firma
    assert base_export.vista()["filas_base"] == 12 and len(llamadas) == 2


# ── HTTP ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_http_pestana_base_lazy_vista_y_cache(bases) -> None:
    from backend.main import app
    from backend.routes import historico as rh
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/historicos")
        assert page.status_code == 200
        i = page.text.index('id="hist-base"')
        frag = page.text[i:i + 400]
        assert 'hx-get="/historicos/base"' in frag and 'hx-trigger="reveal"' in frag and '"timeout":90000' in frag
        assert "baseLoaded" in page.text and "Base (ver / bajar)" in page.text

        r = await ac.get("/historicos/base")
        assert r.status_code == 200
        assert "Archivos en Delta Bases" in r.text and "5 ruedas" in r.text and "espejo fiel ✓" in r.text
        assert "/historicos/base/archivo?que=px_xlsx" in r.text and "?que=px_parquet" in r.text
        assert "?que=fx_parquet" in r.text and "?que=fx_xlsx" not in r.text and "?que=acciones" in r.text
        assert 'id="base-tbl"' in r.text and "T30E6" in r.text and "AL30D" in r.text
        assert '<option value="2026-10-09">09/10/2026</option>' in r.text
        assert len(rh._BASE_CACHE) == 1
        r2 = await ac.get("/historicos/base")
        assert r2.text == r.text and len(rh._BASE_CACHE) == 1

        r = await ac.get("/historicos/base?codigo=t30e6&desde=2026-10-07&n=50")
        assert r.status_code == 200 and "AL30D" not in r.text.split('id="base-tbl"')[1]
        assert "El filtro deja 3 filas" in r.text and 'href="/historicos/base.csv?codigo=T30E6&amp;desde=2026-10-07"' in r.text
        r = await ac.get("/historicos/base?codigo=zzz")
        assert r.status_code == 200 and "No hay filas para ese filtro" in r.text


@pytest.mark.asyncio
async def test_http_descargas_tal_cual_sin_gzip_y_claves_cerradas(bases) -> None:
    from backend.main import app
    tmp, dias = bases
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/base/archivo?que=px_xlsx", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.content == (tmp / hw.HIST_FILENAME).read_bytes()
        assert r.headers["content-encoding"] == "identity"               # el gzip del middleware no lo tocó
        assert 'filename="Delta - historico_byma_px_tasas.xlsx"' in r.headers["content-disposition"]
        assert "spreadsheet" in r.headers["content-type"]
        r = await ac.get("/historicos/base/archivo?que=px_parquet")
        assert r.status_code == 200 and r.content[:4] == b"PAR1"
        assert (await ac.get("/historicos/base/archivo?que=fx_xlsx")).status_code == 404
        assert (await ac.get("/historicos/base/archivo?que=..%2Fsecrets.txt")).status_code == 404
        assert (await ac.get("/historicos/base/archivo")).status_code == 404

        r = await ac.get("/historicos/base/cierre?fecha=2026-10-07", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and r.content == open(hw.cierre_path(str(tmp), date(2026, 10, 7)), "rb").read()
        assert 'filename="2026-10-07.parquet"' in r.headers["content-disposition"]
        r = await ac.get("/historicos/base/cierre?fecha=2026-10-07&fmt=csv")
        assert r.status_code == 200 and r.text.startswith("﻿") and "MERV - XMEV - AL30C - 24hs" in r.text
        assert 'filename="2026-10-07.csv"' in r.headers["content-disposition"] and "text/csv" in r.headers["content-type"]
        assert (await ac.get("/historicos/base/cierre?fecha=2026-10-11")).status_code == 404
        assert (await ac.get("/historicos/base/cierre?fecha=hoy")).status_code == 404

        r = await ac.get("/historicos/base.csv?codigo=AL30D&desde=2026-10-08", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and r.headers["x-filas"] == "2" and r.headers["content-encoding"] == "identity"
        assert 'filename="base_px_tasas_AL30D_2026-10-08.csv"' in r.headers["content-disposition"]
        assert r.text.count("\r\n") == 3 and ";68,25;" in r.text


@pytest.mark.asyncio
async def test_http_csv_codigo_con_control_no_llega_al_header(bases) -> None:
    """`?codigo=` entra al nombre del CSV → al `Content-Disposition`. Un CR/LF
    ahí es un header ilegal: ASGITransport no valida, pero uvicorn (h11 y
    httptools) tira "Invalid HTTP header value" y el cliente se queda sin
    respuesta. Se limpia antes de usarlo (y `_descarga_headers` también)."""
    from backend.main import app
    from backend.routes import historico as rh
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for url in ("/historicos/base.csv?codigo=AL30D%0d%0aX-Injected:%201",
                    "/historicos/base.csv?codigo=AL30D%0d%0a%0d%0a%3Chtml%3E", "/historicos/base.csv?codigo=AL30D%00"):
            r = await ac.get(url)
            assert r.status_code == 200
            cd = r.headers["content-disposition"]
            assert "\r" not in cd and "\n" not in cd and "\x00" not in cd and "%0D" not in cd and "%0A" not in cd
            assert "x-injected" not in r.headers
        # el código sigue funcionando como filtro (y conserva el espacio: "AEROAR 31" existe)
        r = await ac.get("/historicos/base.csv?codigo=AL30D%0d%0a&desde=2026-10-08")
        assert r.headers["x-filas"] == "2" and 'filename="base_px_tasas_AL30D_2026-10-08.csv"' in r.headers["content-disposition"]
        r = await ac.get("/historicos/base?codigo=AL30D%0d%0aX")
        assert r.status_code == 200 and "AL30DX" in r.text
    assert rh._codigo_qs("aeroar 31\r\n") == "AEROAR 31"
    cd = rh._descarga_headers('x"\r\ny.csv')["Content-Disposition"]
    assert "\r" not in cd and "\n" not in cd and cd.startswith('attachment; filename="xy.csv"; filename*=UTF-8\'\'x%22%0D%0Ay.csv')


@pytest.mark.asyncio
async def test_http_base_sin_carpeta_configurada_avisa(bases, monkeypatch) -> None:
    from backend.main import app
    from backend.routes import historico as rh
    monkeypatch.delenv("DELTA_HISTORICO_DIR", raising=False)
    rh._BASE_CACHE.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/base")
        assert r.status_code == 200 and "No hay carpeta de bases configurada" in r.text
        assert (await ac.get("/historicos/base/archivo?que=px_xlsx")).status_code == 404


@pytest.mark.asyncio
async def test_http_base_warm_bajo_50ms(bases) -> None:
    """Pestaña cacheada por (parámetros, firmas): el warm es un lookup + dos
    stats de firma en el executor."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.get("/historicos/base")
        ts = []
        for _ in range(60):
            t0 = time.perf_counter()
            r = await ac.get("/historicos/base")
            ts.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200
    ts.sort()
    p95 = ts[int(len(ts) * 0.95) - 1]
    assert p95 < 50, f"p50 {statistics.median(ts):.1f} p95 {p95:.1f} ms"
