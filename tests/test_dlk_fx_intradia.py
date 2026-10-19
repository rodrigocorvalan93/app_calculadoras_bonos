"""DLK intradía: valuar contra el mayorista del día (SIOPEL/DLR-SPOT) hasta
que el BCRA publica el A3500 del día — ahí manda la serie (cierre)."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pytest

from backend.config import settings
from backend.locale_ar import hoy_ba
from backend.services import dolares, marketdata_store as mds, pricing


@pytest.fixture(autouse=True)
def _caches_limpias():
    """El aplicable y el fingerprint cachean 2 s: limpiar entre tests."""
    pricing._a3500_aplicable_cache.clear()
    pricing._index_val_cache.clear()
    yield
    pricing._a3500_aplicable_cache.clear()
    pricing._index_val_cache.clear()


# ── dolares.oficial_intradia_hoy ────────────────────────────────────────────
def test_intradia_prefiere_siopel_fresco(monkeypatch) -> None:
    monkeypatch.setitem(dolares._mae_snap, "ust", {"last": 1480.0, "hora": "12:30"})
    monkeypatch.setitem(dolares._mae_snap, "ts", time.time())
    r = dolares.oficial_intradia_hoy()
    assert r is not None and r["last"] == 1480.0 and r["source"] == "SIOPEL"


def test_intradia_siopel_viejo_cae_a_spot_de_hoy(monkeypatch) -> None:
    monkeypatch.setitem(dolares._mae_snap, "ust", {"last": 1480.0})
    monkeypatch.setitem(dolares._mae_snap, "ts", time.time() - 3600)   # viejo
    hoy_ms = str(int(time.time() * 1000))
    mds.get_store().update_from_md(dolares.SPOT_SYMBOL,
                                   {"LA": {"price": 1479.5, "date": hoy_ms}})
    r = dolares.oficial_intradia_hoy()
    assert r is not None and r["last"] == 1479.5 and r["source"] == "DLR/SPOT"


def test_intradia_spot_de_ayer_no_vale(monkeypatch) -> None:
    monkeypatch.setitem(dolares._mae_snap, "ust", None)
    monkeypatch.setitem(dolares._mae_snap, "ts", 0.0)
    ayer_ms = str(int((time.time() - 86400) * 1000))
    mds.get_store().update_from_md(dolares.SPOT_SYMBOL,
                                   {"LA": {"price": 1470.0, "date": ayer_ms}})
    assert dolares.oficial_intradia_hoy() is None


def test_official_fx_fecha_del_siopel_no_de_la_serie(monkeypatch) -> None:
    """Regresión del riel: con SIOPEL operando HOY, la fecha mostrada era la
    de la serie A3500 (AYER). Cada fuente pone SU fecha."""
    # Fechas en BA: el container puede estar en UTC ya en el día siguiente
    # (00:00–03:00 UTC) mientras dolares estampa la fecha de Buenos Aires —
    # con date.today() naive estos tests fallaban justo en esa ventana.
    from datetime import timedelta
    ayer = (hoy_ba() - timedelta(days=1)).isoformat()
    monkeypatch.setattr(dolares, "a3500_official",
                        lambda: {"source": "A3500", "last": 1477.7, "close": 1474.7,
                                 "var_pct": 0.002, "date": ayer,
                                 "bid": None, "offer": None, "volume": None})
    # SIOPEL fresco (fetch de hoy) → date = HOY
    monkeypatch.setitem(dolares._mae_snap, "ust", {"last": 1478.5, "hora": "12:30"})
    monkeypatch.setitem(dolares._mae_snap, "ts", time.time())
    of = dolares.official_fx()
    assert of["source"] == "SIOPEL" and of["date"] == hoy_ba().isoformat()
    # sin SIOPEL → DLR/SPOT con last_ts de hoy → date = HOY
    monkeypatch.setitem(dolares._mae_snap, "ust", None)
    mds.get_store().update_from_md(dolares.SPOT_SYMBOL,
                                   {"LA": {"price": 1479.0, "date": str(int(time.time() * 1000))}})
    of = dolares.official_fx()
    assert of["source"] == "DLR/SPOT" and of["date"] == hoy_ba().isoformat()
    # sólo serie → conserva la fecha de la serie (AYER), como corresponde
    monkeypatch.setattr(dolares, "_spot_official", lambda: None)
    of = dolares.official_fx()
    assert of["source"] == "A3500" and of["date"] == ayer


def test_siopel_de_hoy_viejo_es_el_ultimo_recurso(monkeypatch) -> None:
    """Desk 19/10: 'durante el día hay que usar el último de SIOPEL hasta que
    se publique el A3500'. Con MAE sin responder un rato (o el mayorista ya
    cerrado), el último SIOPEL de HOY vale igual — recién si tampoco hay eso
    se cae a la serie (ayer). Un SIOPEL de AYER sigue sin valer."""
    class _SinSpot:                       # el store no tiene DLR/SPOT (otro test pudo sembrarlo)
        @staticmethod
        def get(symbol):
            return None

    monkeypatch.setattr(dolares.marketdata_store, "get_store", lambda: _SinSpot())
    hoy_0 = datetime.now(dolares._TZ_BA).replace(hour=0, minute=5, second=0, microsecond=0)
    monkeypatch.setitem(dolares._mae_snap, "ust", {"last": 1480.0, "hora": "15:00"})
    monkeypatch.setitem(dolares._mae_snap, "ts", max(hoy_0.timestamp(), time.time() - 3 * 3600))   # hoy, viejo
    r = dolares.oficial_intradia_hoy()
    assert r is not None and r["last"] == 1480.0 and r["source"] == "SIOPEL"
    monkeypatch.setitem(dolares._mae_snap, "ts", (hoy_0 - timedelta(hours=2)).timestamp())        # ayer
    assert dolares.oficial_intradia_hoy() is None


# ── pricing.a3500_aplicable — la regla de arbitraje ─────────────────────────
def _con_serie(monkeypatch, fecha, valor=1474.7):
    """El BCRA (backup `historico`) y la serie de rentafija dicen lo mismo."""
    f = fecha.date() if hasattr(fecha, "date") else fecha
    monkeypatch.setattr(pricing, "_a3500_bcra", lambda: (f, valor))
    monkeypatch.setattr(pricing, "_last_series_value",
                        lambda k, c: (fecha, valor) if k == "a3500" else (None, float("nan")))


def _serie_rentafija(monkeypatch, fecha, valor):
    monkeypatch.setattr(pricing, "_last_series_value",
                        lambda k, c: (fecha, valor) if k == "a3500" else (None, float("nan")))


def test_inyeccion_de_especies_no_cuenta_como_a3500_de_hoy(monkeypatch) -> None:
    """Regresión desk 19/10: especies.py inyecta al importarse una fila de HOY
    en inputs['a3500'] (el SIOPEL del arranque, o el cierre de ayer
    relabelado) y la regla la tomaba por el cierre publicado → los DLK se
    valuaban todo el día contra ese número. Manda lo que publicó el BCRA
    (historico), no la serie de rentafija."""
    ayer = hoy_ba() - timedelta(days=1)
    monkeypatch.setattr(pricing, "_a3500_bcra", lambda: (ayer, 1474.7))
    _serie_rentafija(monkeypatch, hoy_ba(), 1474.7)                 # cierre de ayer relabelado HOY
    monkeypatch.setattr(dolares, "oficial_intradia_hoy",
                        lambda: {"last": 1480.0, "source": "SIOPEL", "hora": "12:30"})
    a = pricing.a3500_aplicable()
    assert a["intradia"] and a["value"] == 1480.0 and a["fuente"] == "SIOPEL"
    assert pricing._dlk_fx_auto() == 1480.0
    # sin intradía: el último del BCRA (ayer), nunca la fila inyectada (SIOPEL del arranque)
    pricing._a3500_aplicable_cache.clear()
    _serie_rentafija(monkeypatch, hoy_ba(), 1499.0)
    monkeypatch.setattr(dolares, "oficial_intradia_hoy", lambda: None)
    a = pricing.a3500_aplicable()
    assert not a["intradia"] and a["value"] == 1474.7 and a["fecha"] == ayer
    assert pricing._dlk_fx_auto() == 1474.7        # la serie tiene 1499 inyectado → override con el BCRA


def test_bcra_publico_y_rentafija_todavia_no_refresco(monkeypatch) -> None:
    """16:05: el backup ya tiene el A3500 de HOY (historico.refresh) pero
    inputs['a3500'] sigue con el de ayer hasta que inputs.refresh() termine →
    el override lleva el publicado, no el intradía ni el de ayer."""
    hoy = hoy_ba()
    monkeypatch.setattr(pricing, "_a3500_bcra", lambda: (hoy, 1481.3))
    _serie_rentafija(monkeypatch, hoy - timedelta(days=1), 1474.7)
    monkeypatch.setattr(dolares, "oficial_intradia_hoy",
                        lambda: {"last": 1480.0, "source": "SIOPEL", "hora": "15:00"})
    a = pricing.a3500_aplicable()
    assert not a["intradia"] and a["value"] == 1481.3 and a["fecha"] == hoy
    assert pricing._dlk_fx_auto() == 1481.3
    # serie ya refrescada y coincidente → sin override (comportamiento de siempre)
    pricing._a3500_aplicable_cache.clear()
    _serie_rentafija(monkeypatch, hoy, 1481.3)
    assert pricing._dlk_fx_auto() is None


def test_sin_backup_cae_a_la_serie_de_rentafija(monkeypatch) -> None:
    monkeypatch.setattr(pricing, "_a3500_bcra", lambda: (None, float("nan")))
    _serie_rentafija(monkeypatch, hoy_ba() - timedelta(days=1), 1474.7)
    monkeypatch.setattr(dolares, "oficial_intradia_hoy", lambda: None)
    a = pricing.a3500_aplicable()
    assert a["value"] == 1474.7 and a["fecha"] == hoy_ba() - timedelta(days=1) and not a["intradia"]


def test_sanear_inyeccion_de_especies(monkeypatch) -> None:
    """Al cargar el universo se saca de inputs['a3500'] la fila de HOY que
    inyectó especies.py si el BCRA no la publicó; una fila de hoy que SÍ está
    en el backup se respeta; sin backup no se toca nada."""
    import pandas as pd
    import rentafija
    from backend.services import bond_universe, historico

    hoy, ayer = hoy_ba(), hoy_ba() - timedelta(days=1)
    antes = ayer - timedelta(days=1)
    orig = rentafija.inputs.get("a3500")

    def _bcra(puntos):
        monkeypatch.setattr(historico, "series_points",
                            lambda key, *a, **k: {"label": "", "points": puntos if key == "a3500" else []})

    def _serie(fechas):
        return pd.DataFrame({"tca3500": [1470.0, 1474.7, 1499.0][:len(fechas)]},
                            index=pd.Index(fechas, name="fecha"))
    try:
        rentafija.inputs["a3500"] = _serie([antes, ayer, hoy])          # hoy = inyección (SIOPEL del arranque)
        _bcra([(antes.isoformat(), 1470.0), (ayer.isoformat(), 1474.7)])
        assert bond_universe._sanear_inyeccion_a3500() == 1
        assert list(rentafija.inputs["a3500"].index) == [antes, ayer]
        assert bond_universe._sanear_inyeccion_a3500() == 0            # idempotente
        # el BCRA ya publicó hoy → la fila de hoy es legítima y queda
        rentafija.inputs["a3500"] = _serie([antes, ayer, hoy])
        _bcra([(ayer.isoformat(), 1474.7), (hoy.isoformat(), 1499.0)])
        assert bond_universe._sanear_inyeccion_a3500() == 0
        assert hoy in list(rentafija.inputs["a3500"].index)
        # sin backup: no se puede distinguir, no se toca
        _bcra([])
        assert bond_universe._sanear_inyeccion_a3500() == 0
        # índice string (como inyecta el legacy en algún camino) también se reconoce
        rentafija.inputs["a3500"] = _serie([antes, ayer, hoy.isoformat()])
        _bcra([(antes.isoformat(), 1470.0), (ayer.isoformat(), 1474.7)])
        assert bond_universe._sanear_inyeccion_a3500() == 1
    finally:
        rentafija.inputs["a3500"] = orig


def test_al_cargar_el_universo_la_serie_termina_en_lo_publicado() -> None:
    """Integración: con especies importado, la última fecha de inputs['a3500']
    nunca pasa la última publicada por el BCRA (el backup)."""
    import rentafija
    from backend.services import bond_universe, historico

    bond_universe.ensure_loaded()
    pts = historico.series_points("a3500").get("points") or []
    if not pts:
        pytest.skip("sin backup BCRA")
    ultima = date.fromisoformat(pts[-1][0])
    fechas = [bond_universe._a_date(ix) for ix in rentafija.inputs["a3500"].index]
    assert max(f for f in fechas if f is not None) <= ultima
    assert pricing.a3500_aplicable()["fecha"] == ultima or pricing.a3500_aplicable()["intradia"]


def test_a3500_de_hoy_publicado_manda(monkeypatch) -> None:
    """Con el cierre del día ya en la serie, el intradía NO pisa nada."""
    _con_serie(monkeypatch, datetime.combine(hoy_ba(), datetime.min.time()))   # serie fecha HOY (BA)
    monkeypatch.setattr(dolares, "oficial_intradia_hoy",
                        lambda: {"last": 1480.0, "source": "SIOPEL", "hora": None})
    a = pricing.a3500_aplicable()
    assert a["value"] == 1474.7 and a["fuente"] == "A3500" and not a["intradia"]
    assert pricing._dlk_fx_auto() is None


def test_serie_de_ayer_usa_intradia(monkeypatch) -> None:
    _con_serie(monkeypatch, datetime.combine(hoy_ba() - timedelta(days=1),
                                             datetime.min.time()))   # serie de AYER (BA)
    monkeypatch.setattr(dolares, "oficial_intradia_hoy",
                        lambda: {"last": 1480.0, "source": "SIOPEL", "hora": "12:30"})
    a = pricing.a3500_aplicable()
    assert a["value"] == 1480.0 and a["fuente"] == "SIOPEL" and a["intradia"]
    assert pricing._dlk_fx_auto() == 1480.0


def test_sin_intradia_cae_a_la_serie(monkeypatch) -> None:
    _con_serie(monkeypatch, datetime.now() - timedelta(days=1))
    monkeypatch.setattr(dolares, "oficial_intradia_hoy", lambda: None)
    a = pricing.a3500_aplicable()
    assert a["value"] == 1474.7 and a["fuente"] == "A3500" and not a["intradia"]
    assert pricing._dlk_fx_auto() is None


def test_escape_hatch_apagado(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dlk_fx_intradia", False)
    _con_serie(monkeypatch, datetime.now() - timedelta(days=1))
    monkeypatch.setattr(dolares, "oficial_intradia_hoy",
                        lambda: {"last": 1480.0, "source": "SIOPEL", "hora": None})
    assert not pricing.a3500_aplicable()["intradia"]
    assert pricing._dlk_fx_auto() is None


# ── integración: compute_metrics + fingerprint + card YAS ───────────────────
def _dlk_code():
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("dlk") or []
    if not codes:
        pytest.skip("sin DLK en el universo")
    return codes[0]


def test_compute_metrics_dlk_auto_equivale_a_tc_custom(monkeypatch) -> None:
    """El auto-override produce EXACTAMENTE el mismo cálculo que tipear el
    TC custom en YAS; sin intradía, idéntico al comportamiento histórico."""
    code = _dlk_code()
    monkeypatch.setattr(pricing, "_dlk_fx_auto", lambda: None)
    base = pricing.compute_metrics(code, "precio", 95.0, include_cashflows=False)
    if base.get("error"):
        pytest.skip(f"DLK no calcula en sandbox: {base['error']}")
    manual = pricing.compute_metrics(code, "precio", 95.0, fx_override=1480.0,
                                     include_cashflows=False)
    monkeypatch.setattr(pricing, "_dlk_fx_auto", lambda: 1480.0)
    auto = pricing.compute_metrics(code, "precio", 95.0, include_cashflows=False)
    assert auto["tirea"] == pytest.approx(manual["tirea"], rel=1e-12)
    # el TC custom explícito siempre gana sobre el auto
    explicit = pricing.compute_metrics(code, "precio", 95.0, fx_override=1400.0,
                                       include_cashflows=False)
    assert explicit["tirea"] != pytest.approx(auto["tirea"], rel=1e-9) or \
        manual["tirea"] == explicit["tirea"]


def test_no_dlk_no_consulta_intradia(monkeypatch) -> None:
    """Un bono no-DLK jamás paga el lookup del intradía (ni lo aplica)."""
    llamadas = []
    monkeypatch.setattr(pricing, "_dlk_fx_auto", lambda: llamadas.append(1) or None)
    pricing.compute_metrics("AL30", "precio", 80.0, include_cashflows=False)
    assert llamadas == []


def test_fingerprint_usa_el_valor_aplicado(monkeypatch) -> None:
    """Si el SIOPEL tickea, el fingerprint cambia → el cache de métricas de
    los DLK se invalida y la TIR se recalcula con el dólar nuevo."""
    monkeypatch.setattr(pricing, "a3500_aplicable",
                        lambda: {"value": 1480.25, "fuente": "SIOPEL",
                                 "fecha": None, "intradia": True})
    assert pricing._index_fingerprint("a3500") == 1480.25


def test_card_yas_muestra_fuente(monkeypatch) -> None:
    class _Obj:
        ajuste_sobre_capital = "A3500"
        moneda = "ARS"
        tipo_tasa_interes = "FIJA"
        index = ""

    monkeypatch.setattr(pricing, "a3500_aplicable",
                        lambda: {"value": 1480.0, "fuente": "SIOPEL",
                                 "fecha": None, "intradia": True})
    out = pricing.index_applied(_Obj())
    assert out["value"] == 1480.0 and "intradía" in out["label"] and "SIOPEL" in out["label"]
    monkeypatch.setattr(pricing, "a3500_aplicable",
                        lambda: {"value": 1474.7, "fuente": "A3500",
                                 "fecha": date.today(), "intradia": False})
    out = pricing.index_applied(_Obj())
    assert out["value"] == 1474.7 and "cierre" in out["label"]


def test_fx_custom_se_muestra_en_el_card() -> None:
    """Regresión: con TC (A3500) custom en YAS, las cuentas usaban el override
    pero el card 'FX A3500 aplicable' seguía mostrando el cierre de la serie.
    Ahora el card muestra el TC que realmente priceó los flujos."""
    from backend.services import bond_universe, pricing

    bond_universe.ensure_loaded()
    # TZV28 (DLK soberano, vence en 2028): el D30S6 de antes vencía el 30/09/2026 y
    # desde el 29/09 (liquidación 24hs = vencimiento) ya no tenía flujos → sin card.
    m = pricing.compute_metrics("TZV28", "precio", 148000.0, fx_override=1498.5,
                                include_cashflows=False)
    ia = m["index_applied"]
    assert ia["value"] == 1498.5 and "custom" in ia["label"].lower()
    # sin override → el card sigue leyendo la serie/intradía (label sin 'custom')
    m2 = pricing.compute_metrics("TZV28", "precio", 148000.0, include_cashflows=False)
    assert "custom" not in m2["index_applied"]["label"].lower()
