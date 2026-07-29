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


# ── pricing.a3500_aplicable — la regla de arbitraje ─────────────────────────
def _con_serie(monkeypatch, fecha, valor=1474.7):
    monkeypatch.setattr(pricing, "_last_series_value",
                        lambda k, c: (fecha, valor) if k == "a3500" else (None, float("nan")))


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
    m = pricing.compute_metrics("D30S6", "precio", 148000.0, fx_override=1498.5,
                                include_cashflows=False)
    ia = m["index_applied"]
    assert ia["value"] == 1498.5 and "custom" in ia["label"].lower()
    # sin override → el card sigue leyendo la serie/intradía (label sin 'custom')
    m2 = pricing.compute_metrics("D30S6", "precio", 148000.0, include_cashflows=False)
    assert "custom" not in m2["index_applied"]["label"].lower()
