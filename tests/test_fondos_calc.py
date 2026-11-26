"""Fondos · motor numérico (`services.fondos_calc`): períodos, retornos,
riesgo, flujos y benchmark compuesto. Todo con series sintéticas."""
from __future__ import annotations

import numpy as np
import pytest

from backend.services import fondos_calc as fc


def _ruedas(desde: str, hasta: str) -> np.ndarray:
    cal = np.arange(np.datetime64(desde), np.datetime64(hasta) + np.timedelta64(1, "D"))
    return cal[np.is_busday(cal)]


def test_cortes_de_periodo_usan_la_ultima_rueda_anterior() -> None:
    f = _ruedas("2026-01-01", "2026-11-20")
    i = len(f) - 1                                   # viernes 20/11/2026
    assert str(f[fc.corte_periodo(f, i, "d1")]) == "2026-11-19"
    assert str(f[fc.corte_periodo(f, i, "mtd")]) == "2026-10-30"     # 31/10 es sábado
    assert str(f[fc.corte_periodo(f, i, "ytd")]) == "2025-12-31" or fc.corte_periodo(f, i, "ytd") == -1
    assert str(f[fc.corte_periodo(f, i, "d7")]) == "2026-11-13"
    assert str(f[fc.corte_periodo(f, i, "d30")]) == "2026-10-21"
    # sin historia suficiente: no hay base
    assert fc.corte_periodo(f, 0, "d1") == -1
    assert fc.corte_periodo(f, 3, "d365") == -1
    with pytest.raises(ValueError):
        fc.corte_periodo(f, i, "siglo")


def test_retornos_por_periodo_y_anualizacion() -> None:
    f = _ruedas("2025-12-01", "2026-11-20")
    # 0,1 % por rueda exacto
    y = 100.0 * 1.001 ** np.arange(len(f))
    i = len(f) - 1
    r = fc.retornos_periodos(f, y, i)
    assert r["d1"] == pytest.approx(0.001)
    n_mtd = i - fc.corte_periodo(f, i, "mtd")
    assert r["mtd"] == pytest.approx(1.001 ** n_mtd - 1)
    assert r["ytd"] == pytest.approx(1.001 ** (i - fc.idx_hasta(f, "2025-12-31")) - 1)
    assert r["d365"] is None and r["d730"] is None          # la serie arranca en dic-25
    # antes del inicio de la serie no hay retorno
    y2 = y.copy(); y2[:50] = np.nan
    assert fc.retorno(y2, 10, i) is None
    assert fc.tna(0.02, 30) == pytest.approx(0.02 * 365 / 30)
    assert fc.anualizar(0.02, 30) == pytest.approx(1.02 ** (365 / 30) - 1)
    assert fc.tna(None, 30) is None and fc.anualizar(0.1, 0) is None


def test_riesgo_contra_benchmark() -> None:
    rng = np.random.default_rng(7)
    f = _ruedas("2025-01-01", "2026-11-20")
    rb = rng.normal(0.0005, 0.01, len(f))
    rf = 1.2 * rb + rng.normal(0.0002, 0.002, len(f))        # beta 1,2 + alfa
    b = 100 * np.cumprod(1 + rb)
    y = 100 * np.cumprod(1 + rf)
    i1 = len(f) - 1
    m = fc.riesgo(f, y, b, 0, i1)
    assert m["n"] == i1
    assert m["beta"] == pytest.approx(1.2, abs=0.05)
    assert m["corr"] > 0.95
    assert m["vol"] == pytest.approx(np.std(rf[1:], ddof=1) * np.sqrt(252))
    assert m["te"] == pytest.approx(np.std(rf[1:] - rb[1:], ddof=1) * np.sqrt(252))
    assert m["ir"] == pytest.approx(m["exceso_anual"] / m["te"])
    assert 0 <= m["hit"] <= 1 and m["max_dd"] <= m["dd_actual"] <= 0
    assert m["mejor"] >= m["peor"]
    # sin benchmark: sólo lo propio
    s = fc.riesgo(f, y, None, 0, i1)
    assert s["vol"] == pytest.approx(m["vol"]) and s["te"] is None and s["beta"] is None
    # ventana vacía o de un punto
    assert fc.riesgo(f, y, b, 5, 5)["vol"] is None


def test_maxima_caida() -> None:
    f = _ruedas("2026-01-01", "2026-01-12")
    y = np.array([100, 110, 99, 104.5, 121, 108.9, 115][: len(f)], dtype=float)
    m = fc.riesgo(f[: len(y)], y, None, 0, len(y) - 1)
    assert m["max_dd"] == pytest.approx(99 / 110 - 1)
    assert m["dd_actual"] == pytest.approx(115 / 121 - 1)


def test_mensuales_y_base100() -> None:
    f = _ruedas("2026-08-17", "2026-11-20")
    y = 100.0 * 1.002 ** np.arange(len(f))
    i = len(f) - 1
    ms = fc.mensuales(f, y, i, meses=13)
    assert [m for m, _ in ms] == ["2026-08", "2026-09", "2026-10", "2026-11"]
    total = np.prod([1 + r for _, r in ms]) - 1
    assert total == pytest.approx(y[i] / y[0] - 1)              # los meses componen el total
    assert [m for m, _ in fc.mensuales(f, y, i, meses=2)] == ["2026-10", "2026-11"]
    b = fc.base100(y, 10, 20)
    assert b[0] == pytest.approx(100.0) and b[-1] == pytest.approx(100 * 1.002 ** 10)
    y2 = y.copy(); y2[:12] = np.nan
    b2 = fc.base100(y2, 10, 20)
    assert np.isnan(b2[0]) and b2[2] == pytest.approx(100.0)   # rebasa en el primer dato


def test_flujos_netos_separa_suscripciones_del_rendimiento() -> None:
    vcp = np.array([1.00, 1.01, 1.0201, 1.0201])
    pn = np.array([1000.0, 1010.0, 1520.1, 1420.1])           # +500 el día 2, −100 el día 3
    fl = fc.flujos_netos(pn, vcp)
    assert np.isnan(fl[0])
    assert fl[1] == pytest.approx(0.0, abs=1e-9)
    assert fl[2] == pytest.approx(500.0)
    assert fl[3] == pytest.approx(-100.0)


def test_benchmark_tasa_devenga_por_dia_calendario_con_spread() -> None:
    cal = np.arange(np.datetime64("2026-11-02"), np.datetime64("2026-11-10"))     # 8 días, con fin de semana
    f = fc.a_fechas(["2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"])
    tasa = np.array([36.5, 36.5, 36.5, 73.0, 73.0, 73.0, 73.0])
    var = fc.benchmark_var_calendario(cal, {}, {"badlar": (f, tasa, 1.0)}, spread=0.0365)
    # 36,5 % TNA = 0,1 % por día; el spread suma 0,01 % por día; sábado y domingo devengan
    assert var[0] == pytest.approx(0.001 + 0.0001)
    assert var[2] == pytest.approx(0.002 + 0.0001)             # 04/11: tasa nueva
    assert var[5] == pytest.approx(0.002 + 0.0001) and var[6] == pytest.approx(0.002 + 0.0001)   # 07 y 08/11
    idx = fc.indice_desde_var(var)
    assert idx[-1] == pytest.approx(np.prod(1 + var))
    # peso 0,75 → 75 % de la tasa
    v75 = fc.benchmark_var_calendario(cal, {}, {"badlar": (f, tasa, 0.75)})
    assert v75[0] == pytest.approx(0.00075)


def test_benchmark_compuesto_de_niveles_y_hueco() -> None:
    cal = np.arange(np.datetime64("2026-11-02"), np.datetime64("2026-11-07"))     # lun-vie
    fa = fc.a_fechas(["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"])
    a = np.array([100.0, 101.0, 101.0, 102.01, 103.0301])     # +1 %, 0, +1 %, +1 %
    c = np.array([200.0, 200.0, 204.0, 204.0, 204.0])         # 0, +2 %, 0, 0
    var = fc.benchmark_var_calendario(cal, {"a3500": (fa, a, 0.5), "cer": (fa, c, 0.5)}, {})
    assert np.isnan(var[0])                                   # el primer día no tiene variación
    assert var[1:] == pytest.approx([0.005, 0.01, 0.005, 0.005])
    idx = fc.indice_desde_var(var)
    assert idx[0] == pytest.approx(1.0) and idx[-1] == pytest.approx(1.005 * 1.01 * 1.005 * 1.005)
    # falta un componente (serie más corta que 10 días de gracia no aplica: acá falta del todo)
    var2 = fc.benchmark_var_calendario(cal, {"a3500": (fa, a, 0.5), "spy": (fc.a_fechas([]), np.array([]), 0.5)}, {})
    assert np.isnan(var2).all() and np.isnan(fc.indice_desde_var(var2)).all()
    # un hueco interior corta el índice: no se encadena a través del día sin dato
    v3 = np.array([np.nan, 0.01, np.nan, 0.01])
    i3 = fc.indice_desde_var(v3)
    assert i3[0] == pytest.approx(1.0) and i3[1] == pytest.approx(1.01) and np.isnan(i3[2:]).all()
    # una serie que dejó de actualizarse hace más de 10 días no se estira
    lejos = np.arange(np.datetime64("2026-11-02"), np.datetime64("2026-11-25"))
    y = fc._a_calendario(fa, a, lejos)
    assert np.isfinite(y[13]) and np.isnan(y[-1])


def test_encadenar_empalma_el_historico_con_el_calculado() -> None:
    viejo = np.array([1.0, 1.1, 1.21, np.nan, np.nan])
    nuevo = np.array([np.nan, 50.0, 55.0, 60.5, 66.55])       # mismas variaciones, otra base
    e = fc.encadenar(viejo, nuevo)
    assert e[:3] == pytest.approx([1.0, 1.1, 1.21])
    assert e[3] == pytest.approx(1.21 * 1.1) and e[4] == pytest.approx(1.21 * 1.21)
    # sin dato del nuevo en el empalme: queda sólo el viejo
    sin = fc.encadenar(viejo, np.array([np.nan, np.nan, np.nan, 3.0, 3.3]))
    assert np.isnan(sin[3:]).all()
    # sin histórico: manda el nuevo
    assert fc.encadenar(np.full(5, np.nan), nuevo)[4] == pytest.approx(66.55)


def test_percentil_contra_pares() -> None:
    assert fc.percentil(0.10, [0.10, 0.05, 0.12, None, 0.01]) == (2, 4, pytest.approx(100 * 2 / 3))
    assert fc.percentil(0.12, [0.10, 0.05, 0.12]) == (1, 3, pytest.approx(100.0))
    assert fc.percentil(None, [0.1, 0.2]) is None and fc.percentil(0.1, [0.1]) is None
