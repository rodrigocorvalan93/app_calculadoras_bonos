"""Posiciones — categorización de duales (CER/TAMAR y Fija/TAMAR).

La detección lee el campo `Industria` de la especie (NO una lista de tickers),
así que un dual nuevo entra solo. Se testea con stubs (CI-safe, sin Excel) y un
smoke HTTP del endpoint.
"""
from __future__ import annotations

import pytest

from backend.routes.posiciones import _categoria, _dual_label, _tasa


class _Bono:
    """Stub mínimo con los atributos que miran las clasificaciones."""
    def __init__(self, **kw):
        self.industria = kw.get("industria", "")
        self.ajuste_sobre_capital = kw.get("ajuste", "")
        self.tipo_tasa_interes = kw.get("tipo", "")
        self.index = kw.get("index", "")
        self.moneda = kw.get("moneda", "ARS")
        self.step_up = kw.get("step_up", False)


def test_dual_label_por_industria() -> None:
    cer = _Bono(industria="Soberano ARS Dual CER/Tamar", ajuste="CER", tipo="FIJA")
    fija = _Bono(industria="Soberano ARS Dual Fija/Tamar", tipo="FIJA")
    proy = _Bono(industria="Soberano ARS Dual CER/Tamar Proyectado", ajuste="CER PROYECTADO")
    rev = _Bono(industria="Soberano ARS Dual Tamar/CER", tipo="VARIABLE_CAP", index="TAMAR")
    assert _dual_label(cer) == "Dual CER / TAMAR"
    assert _dual_label(fija) == "Dual Fija / TAMAR"
    assert _dual_label(proy) == "Dual CER / TAMAR"     # proy agrupa con su par
    assert _dual_label(rev) == "Dual CER / TAMAR"      # 'Tamar/CER' también
    # no-duales → None
    assert _dual_label(_Bono(industria="Soberano ARS CER", ajuste="CER")) is None
    assert _dual_label(_Bono(industria="")) is None
    assert _dual_label(None) is None


def test_categoria_y_tasa_de_duales() -> None:
    cer = _Bono(industria="Soberano ARS Dual CER/Tamar", ajuste="CER", tipo="FIJA")
    fija = _Bono(industria="Soberano ARS Dual Fija/Tamar", tipo="FIJA")
    # Las DOS divisiones muestran el dual (ni 'CER' ni 'Fija').
    assert _categoria(cer) == "Dual CER / TAMAR"
    assert _tasa(cer) == "Dual CER / TAMAR"
    assert _categoria(fija) == "Dual Fija / TAMAR"
    assert _tasa(fija) == "Dual Fija / TAMAR"


def test_no_duales_sin_cambios() -> None:
    cer_puro = _Bono(industria="Soberano ARS CER", ajuste="CER", tipo="FIJA")
    assert _categoria(cer_puro) == "CER" and _tasa(cer_puro) == "Fija"
    usd = _Bono(industria="Soberano USD Hard Dollar", ajuste="", moneda="USD")
    assert _categoria(usd) == "USD"
    tamar = _Bono(industria="Soberano ARS", tipo="VARIABLE_CAP", index="TAMAR")
    assert _tasa(tamar) == "TAMAR" and _categoria(tamar) == "ARS TAMAR"


@pytest.mark.asyncio
async def test_posiciones_endpoint_ok() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/posiciones")
    assert r.status_code == 200 and r.text          # degrada solo si no hay carteras


def test_ticker_bloomberg_ar_se_normaliza_a_byma() -> None:
    """El sistema de carteras trae acciones estilo Bloomberg ('LOMA AR');
    BYMA usa el ticker pelado. Sin normalizar, esas filas no matcheaban el
    store y quedaban sin Last."""
    from backend.services import positions

    assert positions._norm_code("LOMA AR") == "LOMA"
    assert positions._norm_code("loma ar") == "LOMA"
    assert positions._norm_code("GGAL AR EQUITY") == "GGAL"
    assert positions._norm_code("LOMA AR CI") == "LOMA"     # plazo + país
    # tickers/bonos SIN el sufijo no se tocan (SUPV no pierde la V, etc.)
    assert positions._norm_code("SUPV") == "SUPV"
    assert positions._norm_code("TXAR") == "TXAR"
    assert positions._norm_code("AL30") == "AL30"
    assert positions._norm_code("S31L6 CI") == "S31L6"


def test_px_val_reescalado_a_base_del_last() -> None:
    """El Excel valúa por VN 1 (TXMD8 0,9160) y BYMA cotiza por VN 100
    (91,85): la columna Px val se muestra en la base del Last."""
    from backend.routes.posiciones import _px_val_like_last

    assert _px_val_like_last(0.9160, 91.85) == pytest.approx(91.60)
    assert _px_val_like_last(91.60, 91.85) == pytest.approx(91.60)     # misma base: no toca
    assert _px_val_like_last(5350.0, 5400.0) == pytest.approx(5350.0)  # acción en la misma base
    # acciones valuadas en otra potencia de 10 también se homogeneizan (el
    # reescalado es genérico por fila, no distingue bonos de acciones)
    assert _px_val_like_last(3.5, 3512.0) == pytest.approx(3500.0)
    assert _px_val_like_last(1.05, 98.7) == pytest.approx(105.0)       # letra valuada por VN 1
    assert _px_val_like_last(0.916, None) == 0.916                     # sin Last: tal cual
    assert _px_val_like_last(None, 91.85) is None


def test_acciones_levantan_last_del_store() -> None:
    """Especies fuera del universo de bonos (acciones/CEDEARs) toman el Last
    directo del store del WS — antes quedaban sin precio en Posiciones."""
    from backend.routes.posiciones import _enrich
    from backend.services import marketdata_store as mds, symbols as syms

    mds.get_store().update_from_md(syms.md_symbol("GGAL", "24hs"),
                                   {"LA": {"price": 5400.0}, "CL": {"price": 5300.0}})
    rows = _enrich([{"cod_fondo": 1, "cod_delta": "GGAL", "especie": "GGAL",
                     "cantidad": 1000.0, "valor": 5_350_000.0, "clase": "Acciones"}],
                   100_000_000.0, "24hs")
    r = rows[0]
    assert r["last"] == 5400.0 and r["price_source"] == "LA"
    assert r["categoria"] == "Acciones" and r["px_val"] == 5350.0
    assert r["tirea"] is None                      # sin calculadora para equities


def test_rating_muestra_la_calificacion_de_la_ficha() -> None:
    """Regresión: la columna Rating mostraba el literal 'Soberano' para los
    soberanos (early-return) en vez de su calificación (CCC-), y los AA(arg)
    de las ONs sólo aparecían si no eran soberanos. El split sob/corp ya vive
    en Categoría — Rating muestra la calificación real de la ficha."""
    from backend.routes.posiciones import _calif
    from backend.services import bond_universe

    bond_universe.ensure_loaded()
    gd30 = bond_universe.get("GD30")
    assert gd30 is not None
    assert _calif(gd30) == (gd30.calificacion or "").strip()   # CCC-, no "Soberano"
    assert _calif(None) == "(sin clasif.)"

    class _FakeSinCalif:
        calificacion = None
        clasificacion = "Soberano"

    assert _calif(_FakeSinCalif()) == "Soberano"               # fallback sin dato


def test_agrupar_tenencias_ramas_por_categoria() -> None:
    """El cuadro de tenencias se agrupa por Categoría (ramas estilo Excel):
    grupos ordenados por Σ valor desc, subtotales de valor y % PN (None si
    ninguna fila lo tiene), filas en su orden original."""
    from backend.routes.posiciones import _agrupar_tenencias

    rows = [
        {"categoria": "CER", "valor": 100.0, "pct_pn": 0.10},
        {"categoria": "USD", "valor": 500.0, "pct_pn": 0.50},
        {"categoria": "CER", "valor": 300.0, "pct_pn": None},
        {"categoria": None, "valor": None, "pct_pn": None},
    ]
    gs = _agrupar_tenencias(rows)
    assert [g["cat"] for g in gs] == ["USD", "CER", "(sin clasif.)"]
    cer = gs[1]
    assert cer["n"] == 2 and cer["valor"] == 400.0 and cer["pct_pn"] == 0.10
    assert [r["valor"] for r in cer["rows"]] == [100.0, 300.0]
    assert gs[2]["pct_pn"] is None
