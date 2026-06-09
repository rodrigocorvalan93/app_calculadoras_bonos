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
