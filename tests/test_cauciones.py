"""Tests for the BYMA cauciones service + the overnight KPI in the riel + the
1D–7D strip of the Tasas tab.

Covers:
  - `_overnight_n`: the overnight plazo by CALENDAR (1D normal, 3D Friday, 4D
    Friday before a Monday holiday — 09/10/2026 — and on the weekend/holiday
    the plazo of the last rueda).
  - `rail_pick(calendario=True)` (riel / Inicio) shows THAT plazo: live, or
    its previous close (`es_cierre`), or `sin_dato`; another 1D–4D plazo wins
    only if it traded today and the calendar one is absent from the store.
  - `rail_pick(calendario=False)` (hist_row) keeps the volume heuristic among
    1D–4D (what actually traded), falling back to the shortest with a tasa.
  - `tira_rows`: 1D–7D always (placeholders "hoy no hay"), >7D only if traded.
  - The /dolares/rail partial renders the "📊 Tasa" block with the picked
    caución above the "💵 Dólar" header; /tasas/table renders the strip.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import cauciones as cauc_svc
from backend.services import marketdata_store as mds_


def _seed_caucion(n: int, *, tasa: float, close: float, vol: float, moneda: str = "PESOS") -> None:
    store = mds_.get_store()
    store.update_from_md(f"MERV - XMEV - {moneda} - {n}D", {
        "BI": {"price": tasa - 0.1}, "OF": {"price": tasa + 0.1},
        "LA": {"price": tasa}, "CL": {"price": close}, "EV": {"size": vol},
    })


def _clear_cauciones() -> None:
    """El store es un singleton: limpio las cauciones para aislar el test del
    resto (otro test pudo dejar un plazo con más volumen sembrado)."""
    store = mds_.get_store()
    for moneda in ("PESOS", "DOLAR"):
        for n in cauc_svc.PLAZOS:
            store._data.pop(f"MERV - XMEV - {moneda} - {n}D", None)


@pytest.fixture()
def overnight(monkeypatch):
    """Fija el plazo del overnight por calendario (la suite corre cualquier
    día: un viernes pre-feriado el calendario real diría 4D)."""
    def _set(n: int) -> None:
        monkeypatch.setattr(cauc_svc, "_overnight_n", lambda *a, **k: n)
    return _set


# ── calendario ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hoy, n", [
    (date(2026, 10, 8), 1),     # jueves normal → 1D
    (date(2026, 10, 2), 3),     # viernes normal → 3D (vence el lunes)
    (date(2026, 10, 9), 4),     # viernes con el lunes 12/10 feriado → 4D (vence el martes)
    (date(2026, 10, 10), 4),    # sábado: la rueda es la del viernes 09/10 → 4D
    (date(2026, 10, 12), 4),    # feriado: ídem, última rueda = viernes 09/10
    (date(2026, 10, 13), 1),    # martes después del feriado → 1D
    (date(2026, 10, 1), 1),     # jueves 01/10 → viernes 02/10 hábil → 1D
])
def test_overnight_n_por_calendario(hoy, n) -> None:
    assert cauc_svc._overnight_n(hoy) == n


def test_overnight_n_no_se_cae_sin_calendario(monkeypatch) -> None:
    import sys
    monkeypatch.setitem(sys.modules, "dias_habiles", None)     # import falla → 1D
    assert cauc_svc._overnight_n(date(2026, 10, 9)) == 1


# ── rail_pick por calendario (riel / Inicio) ────────────────────────────────

def test_viernes_pre_feriado_muestra_el_4d_no_el_3d(overnight) -> None:
    """Regresión 09/10/2026 (lunes 12/10 feriado): el riel mostraba "Caución
    ARS 3D · vol 6,4B · cierre previo" — el 3D es el overnight de un viernes
    NORMAL, pero ese día vence en feriado: lo que opera es el 4D. El store
    tenía el 3D sticky de la rueda del martes (cierre + volumen gigante) y el
    pick por volumen lo elegía. Ahora manda el calendario: 4D, con su cierre
    previo hasta que opere."""
    _clear_cauciones()
    overnight(4)
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 3D", {   # sticky del martes: sólo cierre
        "CL": {"price": 20.0}, "EV": {"size": 6.4e12}})
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 4D", {"CL": {"price": 21.1}})
    try:
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "4D"
        assert r["es_cierre"] is True and r["tasa"] == pytest.approx(21.1) and r["var"] is None
        # cuando el 4D opera, pasa a vivo (y el 3D con su volumen viejo sigue sin importar)
        _seed_caucion(4, tasa=21.4, close=21.1, vol=3e11)
        r = cauc_svc.rail_pick("PESOS")
        assert r["plazo"] == "4D" and "es_cierre" not in r
        assert r["tasa"] == pytest.approx(21.4) and r["var"] == pytest.approx(0.3)
    finally:
        _clear_cauciones()


def test_rail_pick_calendario_gana_al_plazo_que_opero(overnight) -> None:
    """Día normal (o/n = 1D): el 1D todavía no operó pero el 3D sí → el riel
    muestra el 1D con su cierre previo (un 3D no es el overnight de hoy)."""
    _clear_cauciones()
    overnight(1)
    _seed_caucion_close_only(1, close=23.0)
    _seed_caucion(3, tasa=22.0, close=22.3, vol=90_000_000_000)
    try:
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "1D" and r["es_cierre"] is True
        assert r["tasa"] == pytest.approx(23.0)
    finally:
        _clear_cauciones()


def test_rail_pick_sin_el_plazo_del_calendario_gana_el_que_opero_hoy(overnight) -> None:
    """El calendario dice 1D pero el store no lo tiene (feriado que `holidays`
    no trae, símbolo rechazado) y el 3D operó HOY → el mercado sabe más: 3D."""
    _clear_cauciones()
    overnight(1)
    _seed_caucion(3, tasa=22.0, close=22.3, vol=90_000_000_000)
    try:
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "3D" and "es_cierre" not in r
    finally:
        _clear_cauciones()


def test_rail_pick_sin_el_plazo_del_calendario_ni_operaciones_no_inventa_otro(overnight) -> None:
    """Calendario 4D, el store no tiene 4D y nada de 1D–4D operó hoy: NO se
    muestra el cierre viejo del 3D como si fuera el overnight (eso era el bug)
    sino el 4D marcado `sin_dato`."""
    _clear_cauciones()
    overnight(4)
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 3D", {
        "CL": {"price": 20.0}, "EV": {"size": 6.4e12}})
    try:
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "4D" and r["sin_dato"] is True
        assert r["tasa"] is None and r["var"] is None and r.get("es_cierre") is None
    finally:
        _clear_cauciones()


def test_rail_pick_calendario_solo_puntas_sin_cierre(overnight) -> None:
    """El plazo del día está cotizado (puntas) pero nunca operó ni tiene
    cierre → `sin_dato` (nada que mostrar como tasa), no un cierre inventado."""
    _clear_cauciones()
    overnight(1)
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 1D", {
        "BI": {"price": 22.9}, "OF": {"price": 23.2}})
    try:
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "1D" and r["sin_dato"] is True and r["tasa"] is None
        assert r["bid"] == pytest.approx(22.9)
    finally:
        _clear_cauciones()


# ── rail_pick por volumen (hist_row) ────────────────────────────────────────

def test_rail_pick_prefers_highest_volume_overnight() -> None:
    _clear_cauciones()
    # 1D con más volumen que 2D → se elige 1D (día normal).
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000)
    _seed_caucion(2, tasa=24.0, close=23.8, vol=5_000_000_000)
    r = cauc_svc.rail_pick("PESOS", calendario=False)
    assert r is not None
    assert r["plazo"] == "1D"
    assert r["tasa"] == pytest.approx(23.5)
    assert r["var"] == pytest.approx(0.5)          # last − close, en puntos de TNA


def test_rail_pick_rolls_to_longer_overnight_when_it_has_the_volume() -> None:
    _clear_cauciones()
    # Feriado/finde: el 1D casi no opera y el 3D concentra el volumen.
    _seed_caucion(1, tasa=23.5, close=23.5, vol=1_000_000)
    _seed_caucion(3, tasa=22.0, close=22.3, vol=90_000_000_000)
    r = cauc_svc.rail_pick("PESOS", calendario=False)
    assert r is not None
    assert r["plazo"] == "3D"
    assert r["tasa"] == pytest.approx(22.0)
    assert r["var"] == pytest.approx(-0.3)         # bajó vs cierre → flecha roja


def test_rail_picks_returns_ars_then_usd(overnight) -> None:
    _clear_cauciones()
    overnight(1)
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    _seed_caucion(1, tasa=2.1, close=2.0, vol=4_000_000, moneda="DOLAR")
    picks = cauc_svc.rail_picks()
    assert [p["moneda"] for p in picks] == ["ARS", "USD"]      # orden ARS → USD
    assert picks[0]["tasa"] == pytest.approx(23.5)
    assert picks[1]["tasa"] == pytest.approx(2.1)


def test_rail_picks_skips_currency_without_data(overnight) -> None:
    _clear_cauciones()
    overnight(1)
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    picks = cauc_svc.rail_picks()                              # sólo ARS en el store
    assert [p["moneda"] for p in picks] == ["ARS"]


def _seed_caucion_close_only(n: int, *, close: float, moneda: str = "PESOS") -> None:
    """Snapshot como el que deja el feed fuera de rueda / tras un reinicio:
    sólo CL (cierre previo), sin last/bid/offer ni volumen."""
    store = mds_.get_store()
    store.update_from_md(f"MERV - XMEV - {moneda} - {n}D", {"CL": {"price": close}})


def test_byma_rows_excludes_close_only_by_default() -> None:
    # byma_rows a secas no trae filas sin cotización viva.
    _clear_cauciones()
    _seed_caucion_close_only(1, close=23.0)
    _seed_caucion(2, tasa=24.0, close=23.8, vol=5_000_000_000)
    assert [r["plazo"] for r in cauc_svc.byma_rows("PESOS")] == ["2D"]
    rows = cauc_svc.byma_rows("PESOS", include_close_only=True)
    assert [r["plazo"] for r in rows] == ["1D", "2D"]


def test_rail_pick_falls_back_to_previous_close(overnight) -> None:
    # Mercado cerrado / pre-apertura: sólo hay cierres en el store → el riel
    # muestra el cierre previo marcado es_cierre (antes desaparecía el KPI).
    _clear_cauciones()
    overnight(1)
    _seed_caucion_close_only(1, close=23.0)
    _seed_caucion_close_only(2, close=23.4)
    r = cauc_svc.rail_pick("PESOS")
    assert r is not None
    assert r["plazo"] == "1D"                      # el del calendario
    assert r["tasa"] == pytest.approx(23.0)
    assert r["var"] is None
    assert r["es_cierre"] is True
    # por volumen (hist_row) también cae al cierre del más corto
    r = cauc_svc.rail_pick("PESOS", calendario=False)
    assert r["plazo"] == "1D" and r["es_cierre"] is True


def test_rail_pick_por_volumen_prefers_live_trade_over_close_fallback() -> None:
    _clear_cauciones()
    _seed_caucion_close_only(1, close=23.0)        # 1D todavía no operó
    _seed_caucion(3, tasa=22.0, close=22.3, vol=90_000_000_000)
    r = cauc_svc.rail_pick("PESOS", calendario=False)
    assert r is not None
    assert r["plazo"] == "3D"                      # gana la operada, no el cierre
    assert r["tasa"] == pytest.approx(22.0)
    assert "es_cierre" not in r


@pytest.mark.asyncio
async def test_rail_renders_caucion_block(overnight) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _clear_cauciones()
    overnight(1)
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    _seed_caucion(1, tasa=2.1, close=2.0, vol=4_000_000, moneda="DOLAR")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/dolares/rail")
    assert r.status_code == 200
    for tok in ("📊 Tasa", "Caución ARS 1D", "23,50%", "Caución USD 1D", "💵 Dólar"):
        assert tok in r.text, tok
    # ARS aparece antes que USD en el riel.
    assert r.text.index("Caución ARS") < r.text.index("Caución USD")


@pytest.mark.asyncio
async def test_rail_renders_close_fallback(overnight) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _clear_cauciones()
    overnight(1)
    _seed_caucion_close_only(1, close=23.0, moneda="PESOS")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/dolares/rail")
    assert r.status_code == 200
    for tok in ("📊 Tasa", "Caución ARS 1D", "23,00%", "cierre previo"):
        assert tok in r.text, tok
    assert "vs cierre</span>" not in r.text.split("💵 Dólar")[0]  # sin flecha/var en el bloque caución


@pytest.mark.asyncio
async def test_rail_renders_sin_dato(overnight) -> None:
    """Viernes pre-feriado sin 4D en el store: el riel muestra el 4D "sin
    operaciones aún", no el cierre viejo del 3D."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _clear_cauciones()
    overnight(4)
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 3D", {"CL": {"price": 20.0}, "EV": {"size": 6.4e12}})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/dolares/rail")
        assert r.status_code == 200
        bloque = r.text.split("💵 Dólar")[0]
        assert "Caución ARS 4D" in bloque and "sin operaciones aún" in bloque
        assert "3D" not in bloque and "20,00" not in bloque
    finally:
        _clear_cauciones()


def test_viernes_1d_vieja_no_cuenta_como_viva(overnight) -> None:
    """Regresión: viernes la caución 1D no opera (liquidaría sábado), pero el
    last sticky del jueves — con el volumen más grande — hacía que el riel la
    mostrara operando. Un last que no es DE HOY se degrada a cierre y el pick
    overnight va al plazo del viernes (3D), que SÍ operó hoy."""
    from datetime import timedelta

    from backend.locale_ar import hoy_ba

    _clear_cauciones()
    overnight(3)                                    # un viernes normal
    store = mds_.get_store()
    ayer = (hoy_ba() - timedelta(days=1)).isoformat()
    hoy = hoy_ba().isoformat()
    # 1D: last del JUEVES con volumen gigante (sticky/persistido)
    store.update_from_md("MERV - XMEV - PESOS - 1D", {
        "LA": {"price": 29.5, "date": f"{ayer}T16:59:00"},
        "CL": {"price": 29.0}, "EV": {"size": 9e11},
    })
    # 3D: operó HOY (el overnight real del viernes)
    store.update_from_md("MERV - XMEV - PESOS - 3D", {
        "LA": {"price": 31.2, "date": f"{hoy}T11:00:00"},
        "CL": {"price": 30.8}, "EV": {"size": 2e11},
    })
    try:
        vivos = cauc_svc.byma_rows("PESOS")
        assert [r["plazo"] for r in vivos] == ["3D"]          # la 1D vieja no es viva
        for calendario in (True, False):
            pick = cauc_svc.rail_pick("PESOS", calendario=calendario)
            assert pick is not None and pick["plazo"] == "3D" and not pick.get("es_cierre")
            assert pick["tasa"] == 31.2
        # con include_close_only la 1D entra pero como CIERRE (tasa None)
        todas = cauc_svc.byma_rows("PESOS", include_close_only=True)
        r1d = next(r for r in todas if r["plazo"] == "1D")
        assert r1d["tasa"] is None and r1d["close"] == 29.0
    finally:
        _clear_cauciones()


def test_todo_viejo_cae_a_cierre_marcado(overnight) -> None:
    """Pre-apertura: nada operó hoy → el riel muestra cierre previo MARCADO
    (es_cierre), nunca una tasa vieja disfrazada de viva."""
    from datetime import timedelta

    from backend.locale_ar import hoy_ba

    _clear_cauciones()
    overnight(1)
    ayer = (hoy_ba() - timedelta(days=1)).isoformat()
    mds_.get_store().update_from_md("MERV - XMEV - PESOS - 1D", {
        "LA": {"price": 29.5, "date": f"{ayer}T16:59:00"}, "EV": {"size": 5e11},
    })
    try:
        for calendario in (True, False):
            pick = cauc_svc.rail_pick("PESOS", calendario=calendario)
            assert pick is not None and pick.get("es_cierre") is True
            assert pick["tasa"] == 29.5 and pick["var"] is None   # el last viejo ES el cierre
    finally:
        _clear_cauciones()


def test_rail_pick_no_muestra_plazo_largo_como_overnight(overnight) -> None:
    """Regresión del monitor: el 1D todavía no operó (sólo cierre) pero el 14D
    SÍ tiene tasa viva. El riel NO debe mostrar el 14D como si fuera el
    overnight (un 14D no es o/n) — muestra el cierre previo del 1D."""
    _clear_cauciones()
    overnight(1)
    _seed_caucion_close_only(1, close=21.6)                       # 1D: sólo cierre
    _seed_caucion(14, tasa=21.8, close=21.6, vol=90_000_000_000)  # 14D vivo con volumen
    try:
        for calendario in (True, False):
            r = cauc_svc.rail_pick("PESOS", calendario=calendario)
            assert r is not None
            assert r["plazo"] == "1D" and r["es_cierre"] is True     # NO 14D
            assert r["tasa"] == pytest.approx(21.6)
    finally:
        _clear_cauciones()


def test_rail_pick_sin_overnight_devuelve_none_o_sin_dato(overnight) -> None:
    """Sólo hay plazos largos (ningún 1D–4D, vivo ni con cierre): por volumen
    no hay pick (None); por calendario se muestra el plazo del día `sin_dato`
    — nunca un tenor largo disfrazado de overnight."""
    _clear_cauciones()
    overnight(1)
    _seed_caucion(14, tasa=21.8, close=21.6, vol=90_000_000_000)  # sólo 14D
    try:
        assert cauc_svc.rail_pick("PESOS", calendario=False) is None
        r = cauc_svc.rail_pick("PESOS")
        assert r is not None and r["plazo"] == "1D" and r["sin_dato"] is True
        # y sin NINGUNA caución en el store, None en los dos modos
        _clear_cauciones()
        assert cauc_svc.rail_pick("PESOS") is None and cauc_svc.rail_pick("PESOS", calendario=False) is None
    finally:
        _clear_cauciones()


# ── tira de Tasas (1D–7D siempre, largos sólo si operaron) ──────────────────

def _viernes_pre_feriado() -> None:
    """Store como el del viernes 09/10/2026: 1D con cierre del jueves (hoy no
    hay), 2D sin snapshot, 3D sticky del martes (cierre + volumen viejo), 4D y
    5D operando, 6D nada, 7D sólo puntas, 14D operando, 21D cotizado sin
    volumen, 28D sólo cierre con volumen viejo."""
    _clear_cauciones()
    st = mds_.get_store()
    _seed_caucion_close_only(1, close=22.8)
    st.update_from_md("MERV - XMEV - PESOS - 3D", {"CL": {"price": 20.0}, "EV": {"size": 6.4e12}})
    _seed_caucion(4, tasa=21.4, close=21.1, vol=3e11)
    _seed_caucion(5, tasa=21.6, close=21.3, vol=4e10)
    st.update_from_md("MERV - XMEV - PESOS - 7D", {"BI": {"price": 21.5}, "OF": {"price": 22.0}})
    _seed_caucion(14, tasa=21.8, close=21.6, vol=9e10)
    _seed_caucion(21, tasa=22.0, close=21.9, vol=0.0)
    st.update_from_md("MERV - XMEV - PESOS - 28D", {"CL": {"price": 22.3}, "EV": {"size": 5e10}})


def test_tira_rows_1d_a_7d_siempre_y_largos_solo_si_operaron(overnight) -> None:
    overnight(4)
    _viernes_pre_feriado()
    try:
        rows = cauc_svc.tira_rows("PESOS")
        assert [r["plazo"] for r in rows] == ["1D", "2D", "3D", "4D", "5D", "6D", "7D", "14D"]
        by = {r["_n"]: r for r in rows}
        # 1D–7D: "hoy no hay" cuando no hay cotización viva (conserva el cierre si lo hay)
        assert by[1]["sin_dato"] and by[1]["close"] == pytest.approx(22.8)
        assert by[2]["sin_dato"] and by[2]["close"] is None           # sin snapshot
        assert by[3]["sin_dato"] and by[3]["close"] == pytest.approx(20.0)
        assert by[6]["sin_dato"]
        assert not by[4]["sin_dato"] and by[4]["tasa"] == pytest.approx(21.4)
        assert not by[7]["sin_dato"] and by[7]["tasa"] is None and by[7]["bid"] == pytest.approx(21.5)
        # overnight del calendario marcado una sola vez
        assert [r["_n"] for r in rows if r["es_overnight"]] == [4]
        # > 7D: 14D operó (volumen) → entra; 21D sin volumen y 28D sólo cierre viejo → afuera
        assert not by[14]["sin_dato"] and by[14]["volumen"] == pytest.approx(9e10)
        assert 21 not in by and 28 not in by
        # cada fila tiene la forma de byma_rows (la plantilla no distingue)
        for r in rows:
            assert {"plazo", "_n", "moneda", "tasa", "bid", "offer", "close", "var", "volumen"} <= set(r)
            assert r["moneda"] == "ARS"
    finally:
        _clear_cauciones()


def test_tira_rows_vacia_sin_cauciones_en_el_store() -> None:
    _clear_cauciones()
    assert cauc_svc.tira_rows("PESOS") == [] and cauc_svc.tira_rows("DOLAR") == []


def test_tira_rows_dia_normal(overnight) -> None:
    overnight(1)
    _clear_cauciones()
    _seed_caucion(1, tasa=23.5, close=23.0, vol=8e10)
    _seed_caucion(2, tasa=24.0, close=23.8, vol=5e9, moneda="DOLAR")
    try:
        ars = cauc_svc.tira_rows("PESOS")
        assert [r["plazo"] for r in ars] == ["1D", "2D", "3D", "4D", "5D", "6D", "7D"]
        assert ars[0]["es_overnight"] and not ars[0]["sin_dato"] and all(r["sin_dato"] for r in ars[1:])
        usd = cauc_svc.tira_rows("DOLAR")
        assert [r["plazo"] for r in usd] == ["1D", "2D", "3D", "4D", "5D", "6D", "7D"]
        assert usd[1]["tasa"] == pytest.approx(24.0) and usd[1]["moneda"] == "USD" and usd[0]["sin_dato"]
    finally:
        _clear_cauciones()


@pytest.mark.asyncio
async def test_tasas_table_renders_tira(overnight) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    overnight(4)
    _viernes_pre_feriado()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/tasas/table")
        assert r.status_code == 200
        ars = r.text.split("Cauciones BYMA $")[1].split("Cauciones BYMA US$")[0]
        for n in range(1, 8):
            assert f">{n}D" in ars, n
        assert ">14D" in ars and ">21D" not in ars and ">28D" not in ars
        assert ars.count("hoy no hay") == 4                     # 1D 2D 3D 6D
        assert "cierre previo 22,80" in ars                      # el 1D conserva su cierre
        assert ars.count('class="on-tag"') == 1 and "o/n" in ars  # el 4D
        assert "/tasas/caucion/book?moneda=PESOS&amp;dias=4" in ars or "/tasas/caucion/book?moneda=PESOS&dias=4" in ars
        assert "dias=2\"" not in ars                             # las filas sin dato no abren libro
        assert "Sin caución BYMA US$ en el store" in r.text      # US$ sin nada → mensaje de siempre
    finally:
        _clear_cauciones()
