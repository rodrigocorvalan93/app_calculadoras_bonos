"""Descuento a la fecha de PAGO hábil (no a la fecha nominal del cupón).

Caso del desk (23/09/2026): TX26 a 746,90 con liquidación 24/09/2026 daba
3,6691 % en la app y 3,59 % en 1816. El único flujo remanente tiene fecha de
cupón 09/11/2026 (lunes, feriado nacional por la visita papal) y se paga el
10/11/2026: la app descontaba 46 días y 1816 47. Ahora rentafija descuenta a
`cashflow_cpn['FechaPago']` (TIR, precio, duration, convexidad, TR); los
montos y el filtro por liquidación siguen por fecha de cupón; en bullets los
días remanentes y la TNA plazo-remanente cuentan hasta el pago hábil."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings

SETTLE = "24/09/2026"
S0 = dt.date(2026, 9, 24)


def test_feriado_visita_papal_en_el_calendario() -> None:
    import pandas as pd
    from dias_habiles import n_dias_laborales, siguiente_dia_habil_ar

    assert siguiente_dia_habil_ar(pd.Timestamp("2026-11-09")) == dt.date(2026, 11, 10)
    assert siguiente_dia_habil_ar(pd.Timestamp("2026-11-06")) == dt.date(2026, 11, 10)   # bancario + feriado
    assert siguiente_dia_habil_ar(pd.Timestamp("2026-11-10")) == dt.date(2026, 11, 10)
    assert n_dias_laborales(dt.date(2026, 11, 5), 1) == dt.date(2026, 11, 10)


def _obj(code: str):
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    obj = pricing._bond_obj_copy(code)
    if obj is None:
        pytest.skip(f"{code} no está en el universo")
    return obj


def _yf(fechas, desde):
    return np.array([(f - desde).days / 365.0 for f in fechas], dtype=float)


def test_tx26_descuenta_al_pago_habil_como_1816() -> None:
    obj = _obj("TX26")
    obj.calcula_tirea(746.90 / 100.0, SETTLE)              # precio DIRTY como fracción del VN
    cf = obj.cashflow_cpn
    assert list(cf["Fechas"]) == [dt.date(2026, 11, 9)]
    assert list(cf["FechaPago"]) == [dt.date(2026, 11, 10)]
    total, precio = float(cf["Total"].iloc[0]), float(obj.precio)
    assert obj.dias_al_pago == 47 == (dt.date(2026, 11, 10) - S0).days
    con_47 = (total / precio) ** (365.0 / 47) - 1.0
    con_46 = (total / precio) ** (365.0 / 46) - 1.0
    assert obj.tirea == pytest.approx(con_47, abs=1e-6)
    assert abs(obj.tirea - con_46) > 5e-4                    # antes: 46 días → +8 pb
    # con los flujos de la pantalla del desk (750,2996 por 100 VN) es el 3,59 % de 1816
    assert (7.502996 / 7.469) ** (365.0 / 47) - 1.0 == pytest.approx(0.035897, abs=5e-7)
    assert obj.calcula_duration(obj.tirea, SETTLE) == pytest.approx(47 / 365, abs=1e-12)
    assert obj.calcula_precio(obj.tirea, SETTLE) == pytest.approx(precio, rel=1e-6)   # ida y vuelta
    # TX26 tiene 12 cupones (ISMA-30): sus días remanentes siguen siendo los del devengamiento
    assert obj.dias_remanentes == 45


def test_precio_y_tir_usan_fechapago_en_varios_bonos() -> None:
    """Ida y vuelta precio→TIR con el MISMO eje temporal, y el VP recalculado a
    mano sobre FechaPago coincide; sobre la fecha de cupón difiere cuando algún
    flujo cae en fin de semana / feriado."""
    probados = 0
    for code in ("GD30", "AL30", "TX26", "TO26", "S31L6", "TZXO6", "TTM26"):
        from backend.services import bond_universe, pricing

        bond_universe.ensure_loaded()
        obj = pricing._bond_obj_copy(code)
        if obj is None:
            continue
        try:
            px = obj.calcula_precio(0.30, SETTLE)
            obj.calcula_tirea(px, SETTLE)
        except Exception:  # noqa: BLE001 — ficha sin flujos a esa fecha
            continue
        assert obj.tirea == pytest.approx(0.30, abs=1e-6), code
        cf = obj.cashflow_cpn[obj.cashflow_cpn["Fechas"] > obj.fecha_settlement]
        tot = cf["Total"].to_numpy(dtype=float)
        pv_pago = float(np.sum(tot * (1.30) ** (-_yf(cf["FechaPago"], obj.fecha_settlement))))
        pv_cpn = float(np.sum(tot * (1.30) ** (-_yf(cf["Fechas"], obj.fecha_settlement))))
        # calcula_precio redondea el clean a 8 decimales antes de la ida y vuelta
        assert obj.precio == pytest.approx(pv_pago, rel=1e-6), code
        corridos = any(p != c for p, c in zip(cf["FechaPago"], cf["Fechas"]))
        assert (pv_cpn != pytest.approx(pv_pago, rel=1e-6)) == corridos, code
        assert all(p >= c for p, c in zip(cf["FechaPago"], cf["Fechas"])), code
        probados += 1
    assert probados >= 3


def test_bullet_dias_remanentes_y_tna_hasta_el_pago_habil() -> None:
    """Un bullet (cupones == 1) cuyo vencimiento cae en fin de semana / feriado:
    días remanentes = hasta el pago hábil y la TNA días/365 anualiza sobre ese
    plazo, así TNA = (Total/P − 1) × 365/días exactamente."""
    from dias_habiles import siguiente_dia_habil_ar
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    elegido = None
    for code in sorted(bond_universe.all_codes() if hasattr(bond_universe, "all_codes") else bond_universe.codes()):
        meta = pricing.bond_meta(code) or {}
        venc = meta.get("vencimiento")
        venc = venc.date() if hasattr(venc, "date") else venc
        if not isinstance(venc, dt.date) or venc <= dt.date(2026, 10, 1):
            continue
        obj = pricing._bond_obj_copy(code)
        if obj is None or getattr(obj, "cupones", None) != 1 or getattr(obj, "moneda", "") != "ARS":
            continue
        if siguiente_dia_habil_ar(venc) != venc:
            elegido = (code, obj, venc)
            break
    if elegido is None:
        pytest.skip("sin bullets ARS con vencimiento en fin de semana / feriado")
    code, obj, venc = elegido
    px = obj.calcula_precio(0.30, SETTLE)
    obj.calcula_tirea(px, SETTLE)
    pago = siguiente_dia_habil_ar(venc)
    dias = (pago - S0).days
    assert obj.dias_remanentes == dias == obj.dias_al_pago and dias > (venc - S0).days
    tna, label = pricing.tna_from_tirea(obj, obj.tirea)
    total = float(obj.cashflow_cpn["Total"].iloc[-1])
    if label.endswith("/365") and label.split("/")[0].isdigit():
        assert label == f"{dias}/365"
        assert tna == pytest.approx((total / obj.precio - 1.0) * 365.0 / dias, rel=1e-6), code


@pytest.mark.asyncio
async def test_metricas_de_la_app_y_endpoint_excel(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.services import auth, bond_universe, pricing

    bond_universe.ensure_loaded()
    m = pricing.compute_metrics("TX26", "precio", 746.90, settle=SETTLE, include_cashflows=True)
    assert not m.get("error")
    obj = _obj("TX26")
    obj.calcula_tirea(7.469, SETTLE)
    assert m["tirea"] == pytest.approx(obj.tirea, abs=1e-6)
    assert m["duration"] == pytest.approx(47 / 365, abs=1e-9)
    assert m["cashflows"][0]["fecha_cpn"] == dt.date(2026, 11, 9)
    assert m["cashflows"][0]["fecha_pmt"] == dt.date(2026, 11, 10)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_pago", "clave123", "basico")
        tok = auth.set_excel_access("mesa_pago", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post("/excel/v1/calc", headers={"X-OMS-Token": tok}, json={"items": [
                {"code": "TX26", "modo": "precio", "valor": 746.90, "settle": SETTLE}]})
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert res["tirea"] == pytest.approx(m["tirea"]) and res["duration"] == pytest.approx(47 / 365, abs=1e-9)
    finally:
        auth.refresh()
