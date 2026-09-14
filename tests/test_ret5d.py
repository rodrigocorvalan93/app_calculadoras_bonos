"""%5D en Mercado: retorno a 5 ruedas desde la base diaria PROPIA.

El feed de BYMA/Primary sólo trae last + cierre previo; la referencia de 5
ruedas sale de `historico_byma.ref_5d()` (1 mapa por día y versión de la
base, lookup por fila) y nunca dispara la carga del Excel en un request.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, historico_byma, marketdata_store, symbols as syms


def _base_sintetica(codes, hoy: date, ruedas: int = 8, con_hoy: bool = False):
    """`ruedas` días hábiles anteriores a hoy (y opcionalmente hoy) con precio
    100, 101, 102… por rueda; el segundo código tiene un hueco (None)."""
    dias = []
    d = hoy
    while len(dias) < ruedas:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            dias.append(d.isoformat())
    dias.reverse()
    if con_hoy:
        dias.append(hoy.isoformat())
    by_code = {}
    for j, c in enumerate(codes):
        px = [100.0 + i + 10 * j for i in range(len(dias))]
        if j == 1:
            px[-5] = None                      # hueco: esa rueda no cuenta
        by_code[c] = {"base": syms.calc_to_md_code(c), "proy": 0, "dates": dias,
                      "vals": {"Last Price": px, "TIREA": [0.3] * len(dias)}}
    historico_byma._cache = {
        "loaded": True, "error": None, "path": "synthetic", "by_code": by_code,
        "bounds": (dias[0], dias[-1]), "n_codes": len(by_code), "n_dates": len(dias),
        "n_obs": len(dias) * len(codes), "last_update": dias[-1]}
    return dias


@pytest.fixture
def base_limpia():
    saved = historico_byma._cache
    historico_byma._ref5d_cache = None
    yield
    historico_byma._cache = saved
    historico_byma._ref5d_cache = None


def test_ref_5d_quinta_rueda_anterior_a_hoy(base_limpia) -> None:
    hoy = date(2026, 9, 11)                     # viernes
    dias = _base_sintetica(["AAA", "BBB", "CCC"], hoy, ruedas=8)
    ref = historico_byma.ref_5d(hoy)
    # AAA: 8 ruedas < hoy → la 5ª contando desde la última = dias[-5]
    assert ref["AAA"] == (100.0 + 3, date.fromisoformat(dias[-5]))
    # BBB: la 5ª tiene None → se saltea y la referencia es la 6ª (dias[-6])
    assert ref["BBB"] == (110.0 + 2, date.fromisoformat(dias[-6]))
    # Un día "hoy" en la base NO cuenta como rueda anterior
    dias2 = _base_sintetica(["AAA"], hoy, ruedas=8, con_hoy=True)
    historico_byma._ref5d_cache = None
    assert historico_byma.ref_5d(hoy)["AAA"][1] == date.fromisoformat(dias2[-6])
    # Sábado/domingo: el ancla es el viernes → 5 ruedas desde ahí (no 4)
    historico_byma._ref5d_cache = None
    assert historico_byma.ref_5d(hoy + timedelta(days=1))["AAA"][1] == date.fromisoformat(dias2[-6])
    # Menos de 5 ruedas → no inventa
    _base_sintetica(["ZZZ"], hoy, ruedas=3)
    historico_byma._ref5d_cache = None
    assert "ZZZ" not in historico_byma.ref_5d(hoy)


def test_ref_5d_cacheado_por_dia_y_base_y_sin_base(base_limpia) -> None:
    hoy = date(2026, 9, 11)
    _base_sintetica(["AAA"], hoy)
    a = historico_byma.ref_5d(hoy)
    assert historico_byma.ref_5d(hoy) is a                      # mismo día + base → mismo dict
    assert historico_byma.ref_5d(hoy + timedelta(days=1)) is a  # sábado → ancla viernes: mismo mapa
    assert historico_byma.ref_5d(hoy - timedelta(days=1)) is not a
    historico_byma._cache = None                                # sin base en memoria
    assert historico_byma.ref_5d(hoy) == {}                     # y sin disparar la carga
    assert historico_byma._cache is None


@pytest.mark.asyncio
async def test_http_mercado_muestra_5d(base_limpia) -> None:
    """Fila de Mercado con last=105 y cierre de hace 5 ruedas=100 → 5D = +5,00%
    (verde) con la fecha de referencia en el title; sin referencia → '·'."""
    from backend.main import app

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer") or []
    assert len(codes) >= 2
    c0, c1 = codes[0], codes[1]
    from backend.locale_ar import hoy_ba
    hoy = hoy_ba()                              # la ruta cuenta ruedas en fecha BA, no UTC
    _base_sintetica([c0], hoy, ruedas=8)
    historico_byma._cache["by_code"][c0]["vals"]["Last Price"][-5] = 100.0
    store = marketdata_store.get_store()
    store.update_from_md(syms.md_symbol(c0, "24hs"), {"LA": {"price": 105.0}, "CL": {"price": 104.0}})
    store.update_from_md(syms.md_symbol(c1, "24hs"), {"LA": {"price": 98.0}, "CL": {"price": 98.5}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table", params={"curve": "cer", "only_quoting": "false"})
    assert r.status_code == 200 and "5D %" in r.text
    fecha = historico_byma.ref_5d(hoy)[c0][1].strftime("%d/%m/%Y")
    assert f'class="var-up" title="vs cierre del {fecha}">5,00%</td>' in r.text
    # c1 no está en la base → celda vacía, sin title
    fila = r.text.split(f">{c1}<", 1)[1].split("</tr>", 1)[0]
    assert "vs cierre" not in fila and "%</td>" in fila     # Var % sigue; 5D no
