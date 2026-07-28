"""Universo de bonos y refresh de índices (regresión de la auditoría).

- MGCTO (ON Pampa XXVII, viva) estaba definida como dict pero sin envolver en
  Bono → ausente de toda la app. Ahora debe aparecer en el universo.
- rentafija.inputs gana un refresh() con swap atómico y un _loading flag que no
  deja el dict marcado como cargado si indices.main() falla.
"""
from __future__ import annotations

import rentafija
from backend.services import bond_universe


def test_mgcto_esta_en_el_universo() -> None:
    bond_universe.ensure_loaded()
    codes = bond_universe.all_codes()
    assert "MGCTO" in codes
    obj = bond_universe.get("MGCTO")
    assert isinstance(obj, rentafija.Bono)


def test_is_future_vto() -> None:
    from datetime import timedelta

    from backend.locale_ar import hoy_ba

    # Fechas relativas a HOY BA (no date.today() naive): el container en UTC ya
    # está en el día siguiente entre 00:00 y 03:00 UTC y el "ayer" naive caía
    # en el hoy de BA, que _is_future_vto (correctamente) considera vigente.
    ayer = (hoy_ba() - timedelta(days=1)).strftime("%d/%m/%Y")
    manana = (hoy_ba() + timedelta(days=1)).strftime("%d/%m/%Y")
    assert bond_universe._is_future_vto(manana) is True
    assert bond_universe._is_future_vto(ayer) is False
    assert bond_universe._is_future_vto(None) is False
    assert bond_universe._is_future_vto("basura") is False


def test_lazy_inputs_no_queda_cargado_si_falla(monkeypatch) -> None:
    """Un fallo transitorio de indices.main() NO debe marcar el dict como cargado
    (antes seteaba _loaded=True antes del call → quedaba vacío para siempre)."""
    li = rentafija._LazyInputs()

    def _boom():
        raise RuntimeError("BCRA caído")

    monkeypatch.setattr(rentafija.indices, "main", _boom)
    # el acceso dispara la carga, que falla; no debe propagar ni quedar 'loaded'
    assert li.get("cer") is None
    assert li._loaded is False and li._loading is False
    # refresh() también devuelve False sin romper
    assert li.refresh() is False


def test_inputs_refresh_hace_swap(monkeypatch) -> None:
    li = rentafija._LazyInputs()
    monkeypatch.setattr(rentafija.indices, "main", lambda: {"cer": 123.0, "uva": 4.5})
    assert li.refresh() is True
    assert li["cer"] == 123.0 and li._loaded is True
