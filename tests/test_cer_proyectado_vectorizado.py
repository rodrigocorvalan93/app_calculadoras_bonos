"""`indices.calcular_CER_diario_proyectado` vectorizado (22/10): mismo
resultado que el loop día por día de siempre (copiado acá como referencia),
bit a bit, sobre la serie real de inflación del backup y sobre casos borde
(mes sin dato, inicio el 15/16, febrero bisiesto)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.tseries.offsets import MonthEnd

import indices


def _referencia_loop(df_inflamom, cer_inicial, fecha_inicial):
    """La implementación anterior, tal cual (referencia)."""
    df_inflamom = df_inflamom.copy()
    df_inflamom.index = pd.to_datetime(df_inflamom.index)
    fecha_inicial = pd.to_datetime(fecha_inicial)
    rango_fechas = pd.date_range(start=fecha_inicial, end=df_inflamom.index.max() + MonthEnd(1), freq="D")
    df_cer = pd.DataFrame(index=rango_fechas, columns=["CER"], dtype=float)
    df_cer.iloc[0, 0] = cer_inicial
    for fecha in rango_fechas[1:]:
        j_1 = (fecha - pd.DateOffset(months=1)).to_period("M")
        j_2 = (fecha - pd.DateOffset(months=2)).to_period("M")
        k = fecha.to_period("M").days_in_month
        k_1 = (fecha - pd.DateOffset(months=1)).to_period("M").days_in_month
        if fecha.day <= 15:
            mask = df_inflamom.index.to_period("M") == j_2
        else:
            mask = df_inflamom.index.to_period("M") == j_1
        inflacion_mom = 0.0 if not mask.any() else df_inflamom.loc[mask, "inflacionmom"].iloc[0]
        F_t = (1 + inflacion_mom / 100.0) ** (1.0 / (k_1 if fecha.day <= 15 else k))
        df_cer.loc[fecha, "CER"] = df_cer.loc[fecha - pd.DateOffset(days=1), "CER"] * F_t
    df_cer.index = df_cer.index.date
    return df_cer


def _inflamom(meses: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([m for m, _ in meses])
    return pd.DataFrame({"inflacionmom": [v for _, v in meses]}, index=idx)


@pytest.mark.parametrize("fecha_inicial", ["2026-01-15", "2026-01-16", "2026-02-28", "2026-03-01"])
def test_igual_al_loop_bit_a_bit(fecha_inicial) -> None:
    df = _inflamom([("2025-11-01", 2.4), ("2025-12-01", 2.7), ("2026-01-01", 2.2), ("2026-02-01", 2.9),
                    ("2026-04-01", 1.9)])          # marzo sin dato → cuenta 0, como antes
    nuevo = indices.calcular_CER_diario_proyectado(df, 523.456789, fecha_inicial)
    viejo = _referencia_loop(df, 523.456789, fecha_inicial)
    assert list(nuevo.index) == list(viejo.index)
    assert nuevo["CER"].dtype == np.float64
    assert np.array_equal(nuevo["CER"].to_numpy(), viejo["CER"].to_numpy())   # bit a bit


def test_primera_fila_del_mes_manda_y_febrero_bisiesto() -> None:
    df = _inflamom([("2027-12-01", 3.0), ("2028-01-01", 2.0), ("2028-01-20", 9.0), ("2028-02-01", 1.0)])
    nuevo = indices.calcular_CER_diario_proyectado(df, 100.0, "2028-01-31")
    viejo = _referencia_loop(df, 100.0, "2028-01-31")
    assert np.array_equal(nuevo["CER"].to_numpy(), viejo["CER"].to_numpy())
    # 16/02 → 29/02 (bisiesto): factor diario de la inflación de enero prorrateada por 29 días
    import datetime as dt
    f = nuevo.loc[dt.date(2028, 2, 20), "CER"] / nuevo.loc[dt.date(2028, 2, 19), "CER"]
    assert f == (1 + 2.0 / 100.0) ** (1.0 / 29)


def test_con_la_serie_real_del_backup_si_esta() -> None:
    """Sobre lo que indices.main() deja en rentafija.inputs (backup BCRA): la
    serie de inflación combinada real, el CER real, ~300 días proyectados."""
    import rentafija
    inputs = rentafija.inputs
    proy = inputs.get("cer_proyectado")
    cer = inputs.get("CER")
    if proy is None or cer is None or not len(cer):
        pytest.skip("sin backup de índices cargado")
    infl = inputs.get("inflamom")
    if infl is None or "inflacionmom" not in getattr(infl, "columns", []):
        pytest.skip("la serie de inflación no está expuesta en inputs")
    nuevo = indices.calcular_CER_diario_proyectado(infl, cer["CER"].iloc[-1], cer.index[-1])
    viejo = _referencia_loop(infl, cer["CER"].iloc[-1], cer.index[-1])
    assert np.array_equal(nuevo["CER"].to_numpy(), viejo["CER"].to_numpy())


def test_vacio_sigue_tirando() -> None:
    with pytest.raises(ValueError):
        indices.calcular_CER_diario_proyectado(pd.DataFrame(), 1.0, "2026-01-01")
