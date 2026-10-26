"""Memo de cashflows por valuación (22/10) + warmup que cede el GIL.

`pricing._flujos_de` deja sobre la copia per-request los flujos + intereses
corridos memoizados por (código, liquidación, día, huella del índice, FX
override del DLK, cupón del floater) y `calcula_tirea` / `calcula_precio`
los reusan (`_flujos_generados=True`). Profiling del 22/10: generate_cashflows
era el 61 % de cada TIR y se repetía por cada precio distinto del mismo bono
(last / bid / offer / cierre, cada tick). Estos tests prueban que el camino
memoizado da EXACTAMENTE lo mismo que el de siempre, en todos los modos y
tipos de bono, y que un cambio de índice / FX / día invalida la entrada.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from backend.services import bond_universe, curves, pricing, warmup


_CAMPOS = ("tirea", "tna", "tem", "duration", "paridad", "precio", "precio_clean",
           "intereses_corridos", "dias_corridos", "dias_remanentes", "valor_residual",
           "valor_tecnico", "margen_tna", "precio_mercado_pct", "g_spread_bps", "z_spread_bps")


def _muestra() -> list[str]:
    """Un bono por curva (cubre CER, CER proy, DLK, hard-dollar, floaters, LECAP,
    duales y corporativos) — los primeros de cada curva que pricean a 90."""
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    out: list[str] = []
    for c in curves.list_curves():
        for code in (table.get(c.key) or [])[:2]:
            m = pricing.compute_metrics(code, "precio", 90.0, include_cashflows=True)
            if not m.get("error") and np.isfinite(m.get("tirea", float("nan"))):
                out.append(code)
                break
    assert len(out) >= 8, out
    return out


def _sin_memo(code, mode, value, settle=None):
    """El camino legacy: compute_metrics con el memo apagado vía monkeypatch."""
    return pricing.compute_metrics(code, mode, value, settle=settle, include_cashflows=True)


def _eq(x, y) -> bool:
    """Igualdad bit a bit con NaN == NaN (dicts / listas anidados)."""
    if isinstance(x, float) and isinstance(y, float):
        return (math.isnan(x) and math.isnan(y)) or x == y
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(_eq(x[k], y[k]) for k in x)
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        return len(x) == len(y) and all(_eq(a, b) for a, b in zip(x, y))
    return x == y


def _igual(a, b, campo):
    return _eq(a.get(campo), b.get(campo))


@pytest.fixture
def memo_apagado(monkeypatch):
    """Fuerza el camino de siempre (generate_cashflows adentro de calcula_tirea)."""
    monkeypatch.setattr(pricing, "_flujos_de", lambda obj, code, settle, memo: False)


def test_memo_da_los_mismos_numeros_que_generar_cada_vez(monkeypatch) -> None:
    codes = _muestra()
    settle = pricing.settlement_date_str("24hs")
    casos = [("precio", 90.0, None), ("precio", 90.0, settle), ("precio", 95.5, settle),
             ("tir", 0.35, settle), ("tna", 0.30, settle), ("margen", 0.05, settle)]
    pricing._flujos_cache.clear()
    con: dict = {}
    for code in codes:
        for mode, v, s in casos:
            con[(code, mode, v, s)] = pricing.compute_metrics(code, mode, v, settle=s, include_cashflows=True)
    # Segunda pasada: TODO hit del memo (los flujos ya están)
    assert len(pricing._flujos_cache._store) >= len(codes)
    for code in codes:
        for mode, v, s in casos:
            m = pricing.compute_metrics(code, mode, v, settle=s, include_cashflows=True)
            for campo in _CAMPOS:
                assert _igual(m, con[(code, mode, v, s)], campo), (code, mode, campo, m.get(campo), con[(code, mode, v, s)].get(campo))
            assert _eq(m.get("cashflows"), con[(code, mode, v, s)].get("cashflows")), (code, mode)
    # Y contra el camino legacy (sin memo) — bit a bit, incluidos ticket y flujos
    monkeypatch.setattr(pricing, "_flujos_de", lambda obj, code, settle, memo: False)
    for code in codes:
        for mode, v, s in casos:
            m = pricing.compute_metrics(code, mode, v, settle=s, include_cashflows=True)
            for campo in _CAMPOS:
                assert _igual(m, con[(code, mode, v, s)], campo), (code, mode, campo, m.get(campo), con[(code, mode, v, s)].get(campo))
            assert _eq(m.get("cashflows"), con[(code, mode, v, s)].get("cashflows")), (code, mode)
            assert _eq(m.get("index_applied"), con[(code, mode, v, s)].get("index_applied")), (code, mode)
            assert m.get("error") == con[(code, mode, v, s)].get("error")


def test_memo_no_se_usa_con_overrides_ni_fichas_adhoc() -> None:
    """FX custom (DLK), benchmark custom (floater) y objeto ad-hoc mutan la
    copia: no pueden compartir flujos con nadie. El memo queda afuera y el
    resultado es el de siempre."""
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    dlk = next(iter(table.get("dolarlinked") or table.get("corp_dlk") or []), None)
    lecap = next(iter(table.get("lecap") or []), None)
    assert dlk and lecap
    pricing._flujos_cache.clear()
    px = pricing.compute_metrics(dlk, "tir", 0.08, include_cashflows=False)["precio_mercado_pct"]
    base = pricing.compute_metrics(dlk, "precio", px, include_cashflows=False)
    n0 = len(pricing._flujos_cache._store)
    custom = pricing.compute_metrics(dlk, "precio", px, fx_override=5000.0, include_cashflows=False)
    assert len(pricing._flujos_cache._store) == n0          # el override no sembró nada
    assert custom.get("tirea") != base.get("tirea")           # y efectivamente valuó con otro FX
    # Ad-hoc: una copia del singleton como obj_override — mismo número, sin memo
    base = pricing.compute_metrics(lecap, "precio", 95.0, include_cashflows=False)
    n0 = len(pricing._flujos_cache._store)
    obj = pricing._bond_obj_copy(lecap)
    adhoc = pricing.compute_metrics(lecap, "precio", 95.0, obj_override=obj, include_cashflows=False)
    assert adhoc.get("tirea") == base.get("tirea")
    assert len(pricing._flujos_cache._store) == n0


def test_la_key_del_memo_cambia_con_el_indice_el_fx_y_el_dia(monkeypatch) -> None:
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    cer = next(iter(table.get("cer") or []), None)
    assert cer
    pricing._flujos_cache.clear()
    pricing.compute_metrics(cer, "precio", 100.0, include_cashflows=False)
    keys0 = set(pricing._flujos_cache._store)
    assert len(keys0) == 1
    (k,) = keys0
    assert k[0] == cer and isinstance(k[2], int)             # (código, settle, día ordinal, huella, fx, cupón)
    # Otra liquidación → otra entrada
    ci = pricing.settlement_date_str("ci")
    pricing.compute_metrics(cer, "precio", 100.0, settle=ci, include_cashflows=False)
    assert len(pricing._flujos_cache._store) == 2
    # Otro día (rollover) → otra entrada aunque el settle explícito sea el mismo
    hoy = pricing.hoy_ba()
    monkeypatch.setattr(pricing, "hoy_ba", lambda: hoy.replace(year=hoy.year + 1))
    pricing.compute_metrics(cer, "precio", 100.0, settle=ci, include_cashflows=False)
    assert len(pricing._flujos_cache._store) == 3
    # Otra huella del índice → otra entrada
    monkeypatch.setattr(pricing, "_index_fingerprint", lambda kind: ("otro", kind))
    pricing.compute_metrics(cer, "precio", 100.0, settle=ci, include_cashflows=False)
    assert len(pricing._flujos_cache._store) == 4


def test_bono_vencido_no_queda_en_el_memo_y_sigue_dando_error_legible() -> None:
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    code = next(iter(table.get("lecap") or []), None)
    assert code
    pricing._flujos_cache.clear()
    m = pricing.compute_metrics(code, "precio", 100.0, settle="31/12/2099", include_cashflows=False)
    assert m.get("error") and "venció" in m["error"]
    assert not pricing._flujos_cache._store


def test_warm_market_price_toca_el_hit_y_computa_el_miss() -> None:
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    code = next(iter(table.get("lecap") or []), None)
    settle = pricing.settlement_date_str("24hs")
    k = pricing._market_key(code, 97.123, settle)
    assert k is not None
    key, kind, bucket = k
    assert bucket == 97.12
    cache = pricing._curve_metrics_cache_idx if kind else pricing._curve_metrics_cache
    cache.invalidate(key)
    assert pricing.warm_market_price(code, 97.123, settle) is True      # miss → computó
    exp0 = cache._store[key][1]
    assert pricing.warm_market_price(code, 97.123, settle) is False     # hit → touch
    assert cache._store[key][1] >= exp0                                 # TTL extendido, no recalculado
    assert pricing.warm_market_price(code, None, settle) is None
    assert pricing.warm_market_price(code, -1, settle) is None


def test_warm_code_cede_el_gil_solo_cuando_calculo(monkeypatch) -> None:
    """El barrido duerme _GIL_YIELD_S después de cada TIR que calcula de
    verdad (medido 22/10: el sweep tomaba el GIL 2-4 s seguidos y era el 67 %
    de la CPU con ticks); un touch no paga pausa."""
    from backend.services import marketdata_store as mds_
    from backend.services import symbols as syms_
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    code = next(iter(table.get("lecap") or []), None)
    mds_.get_store().update_from_md(syms_.md_symbol(code, "24hs"),
                                    {"LA": {"price": 96.5, "size": 1}, "BI": [{"price": 96.4, "size": 1}],
                                     "OF": [{"price": 96.6, "size": 1}]})
    pausas: list[float] = []
    monkeypatch.setattr(warmup.time, "sleep", lambda s: pausas.append(s))
    settle = pricing.settlement_date_str("24hs")
    for px in (96.5, 96.4, 96.6):
        key, kind, _ = pricing._market_key(code, px, settle)
        (pricing._curve_metrics_cache_idx if kind else pricing._curve_metrics_cache).invalidate(key)
    assert warmup._warm_code(code, "24hs", settle) is True
    assert pausas == [warmup._GIL_YIELD_S] * 3                  # 3 TIRs calculadas → 3 pausas
    pausas.clear()
    assert warmup._warm_code(code, "24hs", settle) is True
    assert pausas == []                                         # todo touch → ninguna
