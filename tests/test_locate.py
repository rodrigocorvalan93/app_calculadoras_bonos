"""📍 Ubicación en la curva — reverse lookup + contenedores en YAS/Comparador."""
from __future__ import annotations

import pytest

from backend.services import bond_universe, curves


def test_curve_key_for() -> None:
    bond_universe.ensure_loaded()
    assert curves.curve_key_for("TX26") == "cer"
    assert curves.curve_key_for("TXMJ9") == "dualcer"
    assert curves.curve_key_for("TXMJ9v") == "dualtamar"
    assert curves.curve_key_for("S31L6") == "lecap"
    assert curves.curve_key_for("GGAL") is None          # acciones: sin curva


@pytest.mark.asyncio
async def test_yas_locate_container() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/yas/recompute", data={
            "code": "TX26", "mode": "precio", "value": "1450,00", "plazo": "24hs"})
    assert r.status_code == 200
    assert "data-locate" in r.text and 'data-curve="cer"' in r.text
    assert "Ubicación en la curva" in r.text


@pytest.mark.asyncio
async def test_comparador_locate_solo_misma_curva() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        same = await ac.get("/comparador/result?a=TX26&b=TZX26&mode=precio&val_a=1450&val_b=1500&plazo=24hs")
        cross = await ac.get("/comparador/result?a=TX26&b=S31L6&mode=precio&val_a=1450&val_b=132&plazo=24hs")
    assert same.status_code == 200 and cross.status_code == 200
    assert "data-locate" in same.text and 'data-curve="cer"' in same.text   # cer vs cer ✓
    assert "data-locate" not in cross.text                                  # cer vs lecap ✗


def test_curvas_combinadas() -> None:
    """Las combinadas son uniones de curvas base; no afectan el reverse-map."""
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    for k in ("mix_tamar_total", "mix_fija_cerproy", "mix_hd_sob"):
        assert k in table
    # unión exacta de las partes (dedup)
    assert set(table["mix_hd_sob"]) == set(table["globales"]) | set(table["bonares"])
    # aparece en el selector con su label "⊕ …"
    labels = {c.key: c.label for c in curves.list_curves()}
    assert labels.get("mix_fija_cerproy", "").startswith("⊕")
    # un bono NUNCA pertenece a una combinada (no rompe Posiciones/locate)
    assert curves.curve_key_for("TX26") == "cer"
    for code in table["mix_hd_sob"][:5]:
        assert curves.curve_key_for(code) in ("globales", "bonares")
