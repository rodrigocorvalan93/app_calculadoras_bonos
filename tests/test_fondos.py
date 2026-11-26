"""Pestaña Fondos (sólo superuser): servicio sobre una carpeta "Delta Bases"
sintética + rutas por HTTP + gating.

Los archivos de la fixture tienen el MISMO formato que los que el proceso de
la mañana deja en la biblioteca compartida (`Text/Esco`, `Text/Fondos`,
`Fondos/*.xlsx`) con números inventados y determinísticos: tres fondos (uno
con clase emblema distinta de la de más patrimonio, uno en dólares sin
benchmark, uno Galileo), benchmark en días corridos con relleno a futuro, e
índices de nivel y de tasa.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth
from backend.services import fondos as fsvc
from backend.services import fondos_attr as fattr
from backend.services import fondos_calc as fc

D0, D1 = "2025-01-02", "2026-11-25"
R_RENTA_B, R_RENTA_E, R_AHORRO, R_USD, R_GAL = 0.0010, 0.0011, 0.0008, 0.0002, 0.0012
R_BM_RENTA, R_BM_AHORRO = 0.0006, 0.0007           # por día CORRIDO


def _ruedas() -> np.ndarray:
    return np.array(pd.bdate_range(D0, D1).values, dtype="datetime64[D]")


def _armar_bases(base) -> None:
    (base / "Text" / "Esco").mkdir(parents=True)
    (base / "Text" / "Fondos").mkdir(parents=True)
    (base / "Fondos").mkdir()
    dias = _ruedas()
    n = np.arange(len(dias))
    filas = []

    def clase(cod, fondo, corto, mon, cl, r, v0, pn0, desde=0):
        for i in n[desde:]:
            filas.append((cod, fondo, corto, mon, str(dias[i]), round(v0 * (1 + r) ** (i - desde), 8),
                          round(pn0 * (1 + r) ** (i - desde), 2), cl))

    clase(369, "DELTA RENTA", "RENTA", "Pesos", "B", R_RENTA_B, 100.0, 9_000_000_000.0)
    clase(369, "DELTA RENTA", "RENTA", "Pesos", "E", R_RENTA_E, 50.0, 1_000_000_000.0)
    clase(369, "DELTA RENTA", "RENTA", "Pesos", "A", R_RENTA_B - 0.00002, 10.0, 500_000_000.0, desde=300)
    clase(473, "DELTA AHORRO PLUS", "AHORRO PLUS", "Pesos", "B", R_AHORRO, 20.0, 5_000_000_000.0)
    clase(709, "DELTA RENTA DÓLARES", "RENTA DOLARES", "Dolares", "B", R_USD, 1.0, 4_000_000.0)
    clase(446, "GALILEO ARGENTINA", "GA", "Pesos", "B", R_GAL, 7.0, 2_000_000_000.0)
    pd.DataFrame(filas, columns=["CodigoFondo", "Fondo", "NombreCortoFondo", "Moneda", "Fecha",
                                 "ValorCuotaparte", "PatrimonioNeto", "Clase"]
                 ).to_csv(base / "Text" / "Esco" / "Delta_VCP.txt", index=False)

    (base / "Text" / "Esco" / "Delta_Fondos.txt").write_text(
        "CodFondo,NumFondo,CodCAFCI,Nombre,NombreCorto,CodTpFondo,Clasif,Apertura,Moneda\n"
        "4,4,369,DELTA RENTA,RENTA,RF,2,Instrumento,ARS\n"
        "13,13,473,DELTA AHORRO PLUS,AHORRO PLUS,RF,2,Instrumento,ARS\n"
        "22,22,709,hoy ,RENTA DOLARES,MI,3,Instrumento,USD\n"
        "51,48,446,GALILEO ARGENTINA ,GA,MI,3,Instrumento,ARS\n", encoding="utf-8")

    # benchmark: días CORRIDOS, con relleno a futuro (var 0) como el archivo real
    cal = np.arange(np.datetime64(D0) - 5, np.datetime64(D1) + 21)
    k = np.clip((cal - np.datetime64(D0)).astype(int), 0, int((np.datetime64(D1) - np.datetime64(D0)).astype(int)))
    lineas = ["fund_code;Date;Category;benchmark_name;benchmark_category;benchmark_var;benchmark_value"]
    for cod, nombre, r in ((369, "Badlar Privada + 200 bps", R_BM_RENTA), (473, "75% Badlar + 25% A3500", R_BM_AHORRO)):
        for f, kk in zip(cal, k):
            lineas.append(f"{cod};{f};2. Benchmarks;{nombre};Badlar;0.0;{1000.0 * (1 + r) ** int(kk)!r}")
    for f in cal:
        lineas.append(f"709;{f};2. Benchmarks;Sin Benchmark;Sin Benchmark;0.0;1.0")
    (base / "Text" / "Fondos" / "Delta_Benchmarks.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    # índices: A3500 y CER como nivel, Badlar como tasa (% TNA) — días corridos
    li = ["year;month;day;A3500;CER;Badlar_Privada;Merval;ETF S&P 500"]
    for j, f in enumerate(cal):
        y, m, dd = str(f).split("-")
        li.append(f"{int(y)};{int(m)};{int(dd)};{1000.0 * 1.0005 ** j!r};{500.0 * 1.0009 ** j!r};36.5;"
                  f"{2_000_000.0 * 1.001 ** j!r};{90_000.0 * 1.0004 ** j!r}")
    (base / "Text" / "Fondos" / "Delta_Indices.txt").write_text("\n".join(li) + "\n", encoding="utf-8")

    # suscripciones y rescates de Ahorro Plus (ESCO 13) desde antes de la serie
    syr = ["CodFondo,Solicitud_Tipo,FechaConcertacion,Importe,% PN",
           "13,S,2024-12-30,1000000.0,0.0", "13,S,2026-11-20,300000000.0,0.05", "13,R,2026-11-20,100000000.0,0.02",
           "13,S,2026-11-22,50000000.0,0.01",          # domingo: cae en la rueda siguiente
           "13,R,2026-11-25,20000000.0,0.004", "99,S,2026-11-25,1.0,0.0"]
    (base / "Text" / "Fondos" / "Delta_SyR_Fondos.txt").write_text("\n".join(syr) + "\n", encoding="utf-8")

    pd.DataFrame({"fund_code": [369, 473], "name": ["DELTA RENTA", "DELTA AHORRO PLUS"],
                  "benchmark_name": ["Badlar Privada + 200 bps", "75% Badlar + 25% A3500"],
                  "benchmark_A3500": ["0", "0,25"], "benchmark_badlarprivada": ["1", "0,75"],
                  "benchmark_spread": ["0,02", "0"]}).to_excel(base / "Fondos" / "Tabla_Benchmarks.xlsx", index=False)
    with pd.ExcelWriter(base / "Fondos" / "Carteras_Diarias_Params.xlsx") as xw:
        pd.DataFrame({"x": [1]}).to_excel(xw, sheet_name="Otra", index=False)
        pd.DataFrame({"CodFondo": [4, 13], "fund_code": [369, 473], "name": ["DELTA RENTA", "DELTA AHORRO PLUS"],
                      "sheet_name": ["Tasa", "CER"], "Clase_Emblema": ["E", "B"]}
                     ).to_excel(xw, sheet_name="Clasif", index=False)
    with pd.ExcelWriter(base / "Fondos" / "Tabla_Fondos_Grupo Latin.xlsx") as xw:
        pd.DataFrame({"Código Clase_CAFCI": [1, 2, 3], "Código Fondo_CAFCI": [369, 369, 473],
                      "Fondo_Name": ["DELTA RENTA", "DELTA RENTA", "DELTA AHORRO PLUS"],
                      "Clase": ["B", "Clase E Ley Nº 27.743", "B"], "Management Fee": ["2,75", "0,85", 1.5]}
                     ).to_excel(xw, sheet_name="Clases_Grupo Latin", index=False)


@pytest.fixture()
def bases(tmp_path, monkeypatch):
    base = tmp_path / "Delta Bases"
    _armar_bases(base)
    monkeypatch.setenv("FONDOS_BASES_DIR", str(base))
    monkeypatch.setenv("FONDOS_PREFS_PATH", str(tmp_path / "fondos_prefs.json"))
    monkeypatch.setenv("FONDOS_ATTR_CACHE", str(tmp_path / "cache_attr"))
    fsvc.reset()
    fattr.reset()
    fsvc._prefs_memo.update({"sig": None, "data": None})
    d = fsvc.cargar_ahora()
    assert d is not None, fsvc.estado()
    from backend.routes import fondos as rf
    rf._memo.clear()
    yield d
    fsvc.reset()
    fattr.reset()
    rf._memo.clear()


# ── servicio ─────────────────────────────────────────────────────────────────
def test_carga_el_modelo_desde_los_archivos(bases):
    d = bases
    assert set(d.fondos) == {369, 473, 709, 446}
    assert d.avisos == []
    renta = d.fondos[369]
    assert (renta.cod, renta.tipo, renta.moneda, renta.familia, renta.grupo) == (4, "RF", "ARS", "Delta", "Tasa")
    # la clase principal es la EMBLEMA de la casa (E), no la de más patrimonio (B)
    assert d.clases[renta.principal].clase == "E" and len(renta.cols) == 3
    assert d.clases[d.fondos[473].principal].clase == "B"
    # nombre sucio del maestro ("hoy ") → gana el de la serie; Galileo por nombre
    assert d.fondos[709].nombre == "DELTA RENTA DÓLARES" and d.fondos[709].moneda == "USD"
    assert d.fondos[446].familia == "Galileo" and d.fondos[446].cod == 51
    # benchmark: el plano ("Sin Benchmark") no entra; el relleno a futuro no corre la última rueda
    assert set(d.bench) == {369, 473} and d.bench_nombre[369] == "Badlar Privada + 200 bps"
    assert str(d.fechas[-1]) == D1 and len(d.fechas) == len(_ruedas())
    assert set(d.indices) == {"a3500", "cer", "badlar", "merval", "spy"}
    assert fsvc._clave_col("ETF S&amp;P 500") == fsvc._clave_col("ETF S&P 500") == "etfsp500"
    assert d.pesos_bm[473] == {"a3500": 0.25, "badlar": 0.75} and d.pesos_bm[369]["spread"] == 0.02
    assert d.fees[(369, "B")] == pytest.approx(0.0275) and d.fees[(369, "E")] == pytest.approx(0.0085)
    assert set(d.syr) == {473}
    est = fsvc.estado()
    assert est["cargado"] and est["fondos"] == 4 and est["hasta"] == D1 and est["error"] is None


def test_tablero_retornos_referencia_y_exceso(bases):
    d = bases
    filas = {r["cafci"]: r for r in fsvc.tablero(d)}
    assert list(filas)[0] in (369, 473)                     # renta fija antes que renta mixta
    r = filas[369]
    assert r["clase"] == "E" and r["fecha"] == D1 and r["bm"] == "Badlar Privada + 200 bps"
    assert r["per"]["d1"]["f"] == pytest.approx(R_RENTA_E)
    # 25/11/2026 es miércoles: un día corrido de benchmark
    assert r["per"]["d1"]["b"] == pytest.approx(R_BM_RENTA)
    assert r["per"]["d1"]["x"] == pytest.approx(R_RENTA_E - R_BM_RENTA)
    # 7 días corridos = 5 ruedas del fondo y 7 días de benchmark
    assert r["per"]["d7"]["f"] == pytest.approx((1 + R_RENTA_E) ** 5 - 1)
    assert r["per"]["d7"]["b"] == pytest.approx((1 + R_BM_RENTA) ** 7 - 1)
    ytd_ruedas = int(np.sum(_ruedas() > np.datetime64("2025-12-31")))
    assert r["per"]["ytd"]["f"] == pytest.approx((1 + R_RENTA_E) ** ytd_ruedas - 1)
    assert r["pn"] == pytest.approx(d.pn_fondo(369)[-1]) and r["pn"] > 10_000_000_000
    # sin benchmark: retorno propio, sin referencia ni exceso
    u = filas[709]
    assert u["bm"] is None and u["per"]["ytd"]["b"] is None and u["per"]["ytd"]["x"] is None
    assert u["per"]["d1"]["f"] == pytest.approx(R_USD, rel=1e-4)     # el archivo trae 8 decimales


def test_referencias_indices_tasa_y_otro_fondo(bases):
    d = bases
    assert [k for k, _ in fsvc.referencias(d)] == ["a3500", "cer", "badlar", "merval", "spy"]
    r = fsvc.fila_tablero(d, d.fondos[709], "a3500")
    assert r["bm"] == "Dólar A3500" and r["per"]["d1"]["b"] == pytest.approx(0.0005)
    # una TASA (36,5 % TNA) se compara como índice que devenga TNA / 365 por día corrido
    r = fsvc.fila_tablero(d, d.fondos[709], "badlar")
    assert r["per"]["d1"]["b"] == pytest.approx(0.001) and r["per"]["d7"]["b"] == pytest.approx(1.001 ** 7 - 1)
    # contra otro fondo (su clase principal) o una clase puntual
    r = fsvc.fila_tablero(d, d.fondos[473], "f:369")
    assert r["bm"] == "RENTA E" and r["per"]["d1"]["x"] == pytest.approx(R_AHORRO - R_RENTA_E)
    assert fsvc.serie_referencia(d, 473, "f:369:B")[1] == "RENTA B"
    assert fsvc.serie_referencia(d, 473, "f:1")[0] is None
    assert fsvc.serie_referencia(d, 709, "bm") == (None, "Sin benchmark")


def test_detalle_ventana_honorario_meses_clases_y_flujos(bases):
    d = bases
    det = fsvc.detalle(d, 369, None, "bm", "d30")
    v = det["ventana"]
    i1 = len(d.fechas) - 1
    i0 = fc.corte_periodo(d.fechas, i1, "d30")
    assert (v["desde"], v["hasta"], v["ruedas"]) == (str(d.fechas[i0]), D1, i1 - i0)
    assert v["f"] == pytest.approx((1 + R_RENTA_E) ** (i1 - i0) - 1)
    assert v["b"] == pytest.approx((1 + R_BM_RENTA) ** v["dias"] - 1)
    assert v["x"] == pytest.approx(v["f"] - v["b"])
    # bruto de honorarios: la cuotaparte es neta del 0,85 % anual de la clase E
    assert v["fee"] == pytest.approx(0.0085)
    assert v["f_bruto"] == pytest.approx((1 + v["f"]) * (1 + 0.0085 / 365) ** v["dias"] - 1)
    assert v["x_bruto"] == pytest.approx(v["f_bruto"] - v["b"])
    # serie del gráfico: base 100, un punto por rueda de la ventana
    s = det["serie"]
    assert len(s["x"]) == len(s["f"]) == len(s["b"]) == len(s["dd"]) == i1 - i0 + 1
    assert s["f"][0] == 100.0 and s["b"][0] == 100.0 and s["x_exc"][0] == 0.0
    assert s["f"][-1] == pytest.approx(100 * (1 + v["f"]), abs=1e-3)
    assert max(abs(x) for x in s["dd"]) == 0.0              # la cuotaparte sólo sube: sin caída
    # meses: 13, el último en curso; clases ordenadas por patrimonio
    assert len(det["meses"]) == 13 and det["meses"][-1]["mes"] == "2026-11" and det["meses"][0]["mes"] == "2025-11"
    assert [c["clase"] for c in det["clases"]] == ["B", "E", "A"]
    assert [c["elegida"] for c in det["clases"]] == [False, True, False]
    assert det["clases"][0]["fee"] == pytest.approx(0.0275) and det["clases"][2]["fee"] is None
    # riesgo con retornos constantes: sin volatilidad ni caída
    assert det["riesgo"]["vol"] == pytest.approx(0.0, abs=1e-9) and det["riesgo"]["max_dd"] == pytest.approx(0.0, abs=1e-12)
    # clase pedida a mano; la clase A nació adentro de la ventana máxima
    det_a = fsvc.detalle(d, 369, "A", "bm", "max")
    assert det_a["clase"] == "A" and det_a["ventana"]["desde"] == str(d.fechas[300])
    assert fsvc.detalle(d, 12345) is None


def test_flujos_reales_de_esco_y_estimados(bases):
    d = bases
    i1 = len(d.fechas) - 1
    i0 = fc.corte_periodo(d.fechas, i1, "d7")              # base: miércoles 18/11
    fl = fsvc.flujos(d, 473, i0, i1)
    assert fl["fuente"] == "syr"
    # el movimiento del domingo 22 entra en la rueda del lunes 23; el del fondo 99 no es de nadie
    assert fl["total_susc"] == pytest.approx(350_000_000.0) and fl["total_resc"] == pytest.approx(120_000_000.0)
    assert fl["total_neto"] == pytest.approx(230_000_000.0)
    assert len(fl["x"]) == len(fl["pn"]) == len(fl["neto"]) == i1 - i0 + 1
    assert fl["neto"][0] == 0.0 and sum(fl["neto"]) == pytest.approx(230_000_000.0)
    # sin archivo de ESCO para el fondo: estimación patrimonio − rendimiento (acá ≈ 0)
    est = fsvc.flujos(d, 369, i0, i1)
    assert est["fuente"] == "estimado" and abs(est["total_neto"]) < 1e-3 * est["pn_fin"]
    # el archivo de ESCO atrasado (termina antes que la ventana) no se usa: total parcial
    fs, su, re = d.syr[473]
    viejo = fs <= np.datetime64("2026-11-01")
    d.syr[473] = (fs[viejo], su[viejo], re[viejo])
    assert fsvc.flujos(d, 473, i0, i1)["fuente"] == "estimado"


def test_muestreo_de_la_serie_del_grafico(bases, monkeypatch):
    assert fsvc._muestreo(10).tolist() == list(range(10))
    m = fsvc._muestreo(5000, 800)
    assert len(m) <= 800 and m[0] == 0 and m[-1] == 4999 and np.all(np.diff(m) > 0)
    assert fsvc._lista(np.array([1.23456789, np.nan, np.inf]), 2) == [1.23, None, None]
    # con la ventana más larga que el tope: menos puntos, mismos extremos y el flujo no pierde plata
    monkeypatch.setattr(fsvc, "MAX_PUNTOS", 50)
    d = bases
    det = fsvc.detalle(d, 473, None, "bm", "max")
    assert len(det["serie"]["x"]) <= 50 and det["serie"]["f"][0] == 100.0
    assert det["serie"]["f"][-1] == pytest.approx(100 * (1 + det["ventana"]["f"]), abs=1e-3)
    fl = det["flujos"]
    assert len(fl["x"]) == len(fl["neto"]) <= 50
    assert sum(v for v in fl["neto"] if v is not None) == pytest.approx(fl["total_neto"], abs=1.0)


def test_seguidos_por_usuario(bases, tmp_path):
    assert fsvc.seguidos("ana") == list(fsvc.SEGUIDOS_DEFAULT)
    assert 446 not in fsvc.seguir("ana", 446)               # estaba por defecto → se quita
    assert fsvc.seguir("ana", 1234, on=True)[-1] == 1234
    assert fsvc.seguir("ana", 1234, on=True).count(1234) == 1
    assert fsvc.seguidos("otro") == list(fsvc.SEGUIDOS_DEFAULT)
    data = json.loads((tmp_path / "fondos_prefs.json").read_text(encoding="utf-8"))
    assert 1234 in data["users"]["ana"]["seguidos"]
    # archivo ilegible: no se pisa con sólo la entrada del que guarda
    (tmp_path / "fondos_prefs.json").write_text("{roto", encoding="utf-8")
    with pytest.raises(OSError):
        fsvc.seguir("ana", 369)
    assert (tmp_path / "fondos_prefs.json").read_text(encoding="utf-8") == "{roto"
    assert fsvc.seguidos("ana") == list(fsvc.SEGUIDOS_DEFAULT)


def test_sin_archivos_deja_el_motivo_y_un_extra_roto_no_voltea_la_carga(tmp_path, monkeypatch):
    vacio = tmp_path / "vacia"
    vacio.mkdir()
    monkeypatch.setenv("FONDOS_BASES_DIR", str(vacio))
    fsvc.reset()
    assert fsvc.cargar_ahora() is None
    assert "Delta_VCP.txt" in fsvc.estado()["error"]
    base = tmp_path / "Delta Bases"
    _armar_bases(base)
    (base / "Text" / "Fondos" / "Delta_Benchmarks.txt").write_text("cualquier;cosa\n1;2\n", encoding="utf-8")
    monkeypatch.setenv("FONDOS_BASES_DIR", str(base))
    d = fsvc.cargar_ahora()
    assert d is not None and d.bench == {} and len(d.fondos) == 4
    assert any("Delta_Benchmarks.txt" in a for a in d.avisos)
    fsvc.reset()


def test_recarga_sola_cuando_cambia_un_archivo(bases, tmp_path, monkeypatch):
    d = bases
    v0 = d.version
    # nada cambió: el re-chequeo de firmas no arma otra versión
    fsvc._tarea()
    assert fsvc._estado["datos"].version == v0 and fsvc.asegurar() is fsvc._estado["datos"]
    # el proceso de la mañana regenera la cuotaparte (una rueda más)
    p = tmp_path / "Delta Bases" / "Text" / "Esco" / "Delta_VCP.txt"
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("473,DELTA AHORRO PLUS,AHORRO PLUS,Pesos,2026-11-26,99.0,5000000000.0,B\n")
    fsvc._tarea()
    d2 = fsvc._estado["datos"]
    assert d2.version == v0 + 1 and str(d2.fechas[-1]) == "2026-11-26"


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_http_pagina_tablero_detalle_y_csv(bases):
    async with _client() as ac:
        pg = await ac.get("/fondos")
        assert pg.status_code == 200 and "Fondos — performance vs benchmark" in pg.text
        assert ">Fondos<" in pg.text and 'value="cer"' in pg.text       # nav + referencias del selector
        t = await ac.get("/fondos/tablero")
        assert t.status_code == 200
        for txt in ("RENTA", "AHORRO PLUS", "RENTA DOLARES", "GA", "25/11/2026", "Badlar Privada + 200 bps"):
            assert txt in t.text
        assert t.text.count("<tr data-cafci=") == 4 and 'data-fam="Galileo"' in t.text
        assert 'data-cafci="369" data-seg="1"' in t.text                 # seguido por defecto
        # marcador de «mis fondos»: de los dos con benchmark, Renta le gana y Ahorro Plus no (Renta Dólares y Galileo no tienen)
        assert "Mis fondos vs referencia" in t.text and "<b>MTD</b> 1 de 2 arriba" in t.text and "<b>YTD</b> 1 de 2 arriba" in t.text
        x = await ac.get("/fondos/tablero", params={"ver": "x", "vs": "a3500"})
        assert x.status_code == 200 and "Dólar A3500" in x.text and " pp" in x.text
        assert (await ac.get("/fondos/tablero", params={"ver": "zzz", "vs": "<script>"})).status_code == 200

        det = await ac.get("/fondos/detalle", params={"f": 369})
        assert det.status_code == 200
        for txt in ("DELTA RENTA", "Clase E", "Renta fija", "Badlar Privada + 200 bps", "Bruto de honorarios",
                    "Tracking error", "nov-26", "data-fondos-chart", "application/json", "/fondos/serie.csv?f=369"):
            assert txt in det.text, txt
        assert det.text.count("data-fondos-chart") == 4
        d30 = await ac.get("/fondos/detalle", params={"f": 473, "clase": "B", "vs": "f:369", "rango": "d30"})
        assert d30.status_code == 200 and "RENTA E" in d30.text and "suscripciones y rescates de ESCO" in d30.text
        a_mano = await ac.get("/fondos/detalle", params={"f": 473, "desde": "2026-10-01", "hasta": "2026-10-30"})
        assert "30/09/2026" in a_mano.text and "30/10/2026" in a_mano.text
        nada = await ac.get("/fondos/detalle", params={"f": 99999})
        assert nada.status_code == 200 and "No encontré ese fondo" in nada.text
        assert (await ac.get("/fondos/detalle", params={"f": 369, "desde": "no-es-fecha", "rango": "??"})).status_code == 200

        csv = await ac.get("/fondos/serie.csv", params={"f": 473, "desde": "2026-11-20"})
        assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
        lineas = csv.content.decode("utf-8-sig").strip().split("\r\n")
        assert lineas[0].startswith("Fecha;Cuotaparte;Patrimonio clase;Retorno diario %;75% Badlar + 25% A3500")
        assert [x.split(";")[0] for x in lineas[1:]] == ["19/11/2026", "20/11/2026", "23/11/2026", "24/11/2026", "25/11/2026"]
        assert lineas[-1].split(";")[3] == "0,0800"                       # 0,08 % diario, coma decimal
        assert (await ac.get("/fondos/serie.csv", params={"f": 1})).status_code == 404


@pytest.mark.asyncio
async def test_http_seguir_alterna_y_refresca(bases):
    async with _client() as ac:
        r = await ac.post("/fondos/seguir", data={"f": 446})
        assert r.status_code == 204 and r.headers["HX-Trigger"] == "fondos-refresh"
        assert 'data-cafci="446" data-seg="0"' in (await ac.get("/fondos/tablero")).text
        await ac.post("/fondos/seguir", data={"f": 446})
        assert 'data-cafci="446" data-seg="1"' in (await ac.get("/fondos/tablero")).text


@pytest.mark.asyncio
async def test_http_sin_datos_muestra_la_causa(tmp_path, monkeypatch):
    vacio = tmp_path / "vacia"
    vacio.mkdir()
    monkeypatch.setenv("FONDOS_BASES_DIR", str(vacio))
    fsvc.reset()
    fsvc.cargar_ahora()
    async with _client() as ac:
        assert (await ac.get("/fondos")).status_code == 200
        t = await ac.get("/fondos/tablero")
        assert t.status_code == 200 and "Delta_VCP.txt" in t.text and "data-cafci" not in t.text
        assert (await ac.get("/fondos/detalle", params={"f": 369})).status_code == 200
    fsvc.reset()


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


async def _login(ac: AsyncClient, user: str = "su_test", pwd: str = "clave-de-test-2026!"):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


@pytest.mark.asyncio
async def test_fondos_solo_superuser(bases, auth_on):
    async with _client() as su:
        await _login(su)
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
        assert ">Fondos<" in (await su.get("/yas")).text            # el superuser la ve en la nav
        assert (await su.get("/fondos")).status_code == 200
        assert "AHORRO PLUS" in (await su.get("/fondos/tablero")).text
        # la ★ es por usuario: queda bajo el nombre del superuser
        await su.post("/fondos/seguir", data={"f": 446})
        assert 446 not in fsvc.seguidos("su_test") and 446 in fsvc.seguidos("prem")
    async with _client() as ac:
        await _login(ac, "prem", "clave123")
        for url in ("/fondos", "/fondos/tablero", "/fondos/detalle?f=369", "/fondos/serie.csv?f=369"):
            assert (await ac.get(url)).status_code == 403, url
        assert (await ac.post("/fondos/seguir", data={"f": 369})).status_code == 403
        assert (await ac.post("/fondos/releer")).status_code == 403
        y = await ac.get("/yas")
        assert y.status_code == 200 and ">Fondos<" not in y.text     # ni el link
        # /salud: el ítem de Fondos (patrimonios de la casa) no existe para otros roles
        assert "Fondos (cuotapartes y benchmarks)" not in (await ac.get("/salud")).text
    async with _client() as su:
        await _login(su)
        s = await su.get("/salud")
        assert "Fondos (cuotapartes y benchmarks)" in s.text and "4 fondos · cuotaparte al 2026-11-25" in s.text
    async with _client() as anon:
        r = await anon.get("/fondos", follow_redirects=False)
        assert r.status_code in (302, 303, 307, 401)


def test_salud_fondos_sin_abrir_avisos_y_atraso(bases, monkeypatch):
    from backend.services import salud
    it = salud._fondos()
    assert it["estado"] == "ok" and it["solo"] == "superuser" and it["accion"]["href"] == "/fondos"
    assert "Delta_VCP.txt al 2026-11-25" in it["detalle"] and it["texto"] == "4 fondos · cuotaparte al 2026-11-25"
    # la atribución sin carpeta de carteras es un aviso del mismo ítem
    fattr._estado["error"] = "No encuentro la carpeta Carteras"
    assert salud._fondos()["estado"] == "warn" and "Carteras" in salud._fondos()["detalle"]
    fattr._estado["error"] = None
    # un extra que no se pudo leer → aviso con el archivo
    bases.avisos.append("Delta_Indices.txt: sólo en la nube")
    it = salud._fondos()
    assert it["estado"] == "warn" and "1 aviso(s)" in it["texto"] and "Delta_Indices.txt: sólo en la nube" in it["detalle"]
    bases.avisos.clear()
    # cuotaparte vieja
    monkeypatch.setattr(fsvc, "estado", lambda: {"cargado": True, "fondos": 4, "hasta": "2026-11-25", "atraso_dias": 9,
                                                 "fuentes": [], "avisos": []})
    assert salud._fondos()["estado"] == "warn" and "atrasada" in salud._fondos()["texto"]
    # nadie abrió la pestaña en esta instancia: sin ítem (y sin tocar disco); con error de carga, se ve
    monkeypatch.setattr(fsvc, "estado", lambda: {"cargado": False, "error": None})
    assert salud._fondos() is None
    monkeypatch.setattr(fsvc, "estado", lambda: {"cargado": False, "error": "No encuentro Delta_VCP.txt"})
    assert salud._fondos()["estado"] == "err"


def test_precarga_solo_una_vez_y_apagable(bases, monkeypatch):
    llamadas = []
    monkeypatch.setattr(fsvc, "asegurar", lambda: llamadas.append(1))
    monkeypatch.setenv("FONDOS_PRECARGA", "1")
    fsvc.precargar()                                  # ya hay datos: nada
    assert llamadas == []
    fsvc.reset()
    fsvc.precargar()                                  # sin datos: dispara la carga
    assert llamadas == [1]
    fsvc._estado["error"] = "No encuentro Delta_VCP.txt"
    fsvc.precargar()                                  # ya falló: no insiste desde Inicio (la pestaña reintenta)
    monkeypatch.setenv("FONDOS_PRECARGA", "0")
    fsvc._estado["error"] = None
    fsvc.precargar()
    assert llamadas == [1]


def test_un_extra_ilegible_se_reintenta_aunque_no_cambie_la_firma(bases, tmp_path):
    """Bajar un marcador de OneDrive no cambia mtime ni tamaño: con avisos, el re-chequeo vuelve a leer."""
    v0 = bases.version
    bases.avisos.append("Delta_Indices.txt: sólo en la nube")
    fsvc._tarea()
    d2 = fsvc._estado["datos"]
    assert d2.version == v0 + 1 and d2.avisos == []
