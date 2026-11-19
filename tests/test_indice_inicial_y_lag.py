"""YAS · índice aplicado e índice inicial (NZC3O, 19/11).

El card "UVA aplicable" mostraba el último UVA publicado mientras el
cashflow ajustaba con el de la liquidación corrida por el lag de la ficha
(-5 ruedas): no coincidían y no se veía contra qué UVA inicial. Además un
UVA con lag 0 (como lo valúa 1816) y liquidación 24 hs pedía un UVA que la
serie observada (cortada en hoy) todavía no tiene → KeyError.
"""
import os

os.environ.setdefault("AUTH_ENABLED", "0")
os.environ.setdefault("APP_HOST", "127.0.0.1")

import httpx
import pytest

import rentafija
from backend.main import app
from backend.services import pricing

CODE = "NZC3O"


def _uva():
    return rentafija.inputs["UVA"]


def _settle_en_serie():
    """Una liquidación hábil cuyo UVA (también con lag -5) está observado."""
    return rentafija.n_dias_laborales(_uva().index[-1], 0)


def test_card_muestra_el_uva_de_la_liquidacion_con_lag_y_el_inicial():
    settle = _settle_en_serie()
    m = pricing.compute_metrics(CODE, "tir", 8.0, settle=settle.strftime("%d/%m/%Y"))
    assert m["error"] is None, m["error"]
    obj = pricing._bond_obj_copy(CODE)
    lag, lag_base = int(obj.dias_lag_ajuste), int(obj.dias_lag_ajuste_base)
    ia = m["index_applied"]
    f_apl = rentafija.n_dias_laborales(settle, lag)
    assert ia["kind"] == "UVA" and ia["fecha"] == f_apl and ia["lag"] == lag
    assert ia["value"] == pytest.approx(float(_uva().loc[f_apl, "UVA"]))
    # el aplicado es el que ajusta los flujos futuros del cashflow
    assert m["cashflows"][-1]["ajuste"] == pytest.approx(ia["value"])
    # índice inicial = el de la emisión con el lag base de la ficha
    f_base = rentafija.n_dias_laborales(obj.emision, lag_base)
    assert ia["base_fecha"] == f_base and ia["base_label"] == "UVA inicial"
    assert ia["base"] == pytest.approx(float(_uva().loc[f_base, "UVA"]))
    # el último publicado sigue disponible (tooltip)
    assert ia["ultimo_fecha"] == _uva().index[-1]


def test_uva_lag_cero_con_liquidacion_despues_del_ultimo_publicado():
    ultimo = _uva().index[-1]
    settle = rentafija.n_dias_laborales(ultimo, 1)
    assert settle not in _uva().index
    obj = pricing._bond_obj_copy(CODE)
    obj.dias_lag_ajuste = obj.dias_lag_ajuste_base = 0
    m = pricing.compute_metrics(CODE, "tir", 8.0, settle=settle.strftime("%d/%m/%Y"), obj_override=obj)
    assert m["error"] is None, m["error"]          # antes: KeyError
    ia = m["index_applied"]
    # sin publicar: último UVA publicado × crecimiento del CER (lo de 1816),
    # no el último a secas ni la UVA proyectada (CER × 2,5217)
    cer = rentafija.inputs["cer_proyectado"]
    esperado = round(float(_uva().loc[ultimo, "UVA"]) * float(cer.loc[settle, "CER"])
                     / float(cer.loc[ultimo, "CER"]), 2)
    assert esperado > float(_uva().loc[ultimo, "UVA"])
    assert ia["fecha"] == settle and ia["lag"] == 0 and ia["estimado"] is True
    assert ia["value"] == pytest.approx(esperado)
    assert m["cashflows"][-1]["ajuste"] == pytest.approx(esperado)
    assert rentafija.uva_sin_publicar(settle) == pytest.approx(esperado)
    assert ia["base_fecha"] == rentafija.n_dias_laborales(obj.emision, 0)
    # con la fecha EN la serie observada el valor es el observado (camino de siempre)
    obj2 = pricing._bond_obj_copy(CODE)
    obj2.dias_lag_ajuste = obj2.dias_lag_ajuste_base = 0
    s2 = _settle_en_serie()
    m2 = pricing.compute_metrics(CODE, "tir", 8.0, settle=s2.strftime("%d/%m/%Y"), obj_override=obj2)
    assert m2["index_applied"]["value"] == pytest.approx(float(_uva().loc[s2, "UVA"]))
    assert m2["index_applied"]["estimado"] is False


def test_uva_sin_publicar_reproduce_el_de_1816():
    """NZC3O liq. 20/11/2026 (1816: 2.205,17), con el UVA publicado hasta el
    18/11 (2.201,98) y el CER del 18 y el 20 de la serie del repo."""
    import datetime as dt

    import pandas as pd
    d18, d20 = dt.date(2026, 11, 18), dt.date(2026, 11, 20)
    cer = rentafija.inputs["cer_proyectado"]
    if d18 not in cer.index or d20 not in cer.index:
        pytest.skip("la serie de CER del repo no llega al 20/11/2026")
    uva = pd.DataFrame({"UVA": [2194.78, 2201.98]}, index=pd.Index([dt.date(2026, 11, 13), d18]))
    viejo = rentafija.inputs["UVA"]
    rentafija.inputs["UVA"] = uva
    try:
        v = rentafija.uva_sin_publicar(d20)
    finally:
        rentafija.inputs["UVA"] = viejo
    assert v == pytest.approx(2205.17, abs=0.02)      # el último a secas daba 2.201,98


def test_cer_tambien_muestra_aplicado_e_inicial():
    code = next(c for c in ("TZX27", "TZXD7", "TX28", "TZX28") if pricing.bond_meta(c))
    m = pricing.compute_metrics(code, "tir", 8.0, settle="19/08/2026")
    assert m["error"] is None, m["error"]
    ia = m["index_applied"]
    assert ia["kind"] == "CER" and ia["base_label"] == "CER inicial" and ia["base"] > 0
    assert ia["lag"] == int(pricing._bond_obj_copy(code).dias_lag_ajuste)


@pytest.mark.asyncio
async def test_http_yas_muestra_uva_aplicable_e_inicial():
    settle = _settle_en_serie().strftime("%d/%m/%Y")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/yas/recompute", data={"code": CODE, "mode": "tir", "value": "8", "settle": settle})
    assert r.status_code == 200
    assert "UVA aplicable" in r.text and "UVA inicial" in r.text and "· lag " in r.text
    assert "estimado" not in r.text           # fecha publicada: no se marca
