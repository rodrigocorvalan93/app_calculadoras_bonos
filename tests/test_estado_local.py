"""Estado por máquina fuera de la carpeta sincronizada (15/10).

El desk vio `data/` con ~6 GB de `market_snapshot-DAM-NB-CIO-<n>.json`: cada
PC reescribía el snapshot del store cada 5 min adentro del clon que sincroniza
OneDrive y OneDrive dejaba la versión perdedora como copia en conflicto. El
snapshot, el riesgo país, el BNA y el dump CER van ahora a la carpeta local
(`estado_local.dir_local()`); el primer arranque lee una vez el viejo de
`data/` para no abrir vacío."""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.services import bna_fx, estado_local, riesgo_pais, store_persist
from backend.services import marketdata_store as mds

ROOT = Path(__file__).resolve().parents[1]


def _sin_overrides(monkeypatch, local: Path, legacy: Path) -> None:
    """Como en una PC del desk: sin `*_PATH`, carpeta local y `data/` propias."""
    for env in ("MARKET_SNAPSHOT_PATH", "BNA_FX_PATH", "RIESGO_PAIS_PATH"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("BONOS_LOCAL_DIR", str(local))
    monkeypatch.setattr(estado_local, "LEGACY_DIR", legacy)


def test_dir_local_por_env_localappdata_o_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BONOS_LOCAL_DIR", str(tmp_path / "x"))
    assert estado_local.dir_local() == tmp_path / "x"
    monkeypatch.delenv("BONOS_LOCAL_DIR")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert estado_local.dir_local() == tmp_path / "AppData" / "Local" / "bonos"
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    assert estado_local.dir_local() == tmp_path / "home" / ".local" / "share" / "bonos"
    # nunca adentro del clon (lo que sincroniza OneDrive en las PCs del desk)
    assert ROOT not in estado_local.dir_local().parents


def test_ruta_lectura_migra_desde_data_una_sola_vez(monkeypatch, tmp_path) -> None:
    local, legacy = tmp_path / "local", tmp_path / "data"
    legacy.mkdir()
    _sin_overrides(monkeypatch, local, legacy)
    # sin nada: lee y escribe en la local
    assert estado_local.ruta_lectura("x.json", "X_PATH") == local / "x.json"
    # con el viejo en data/ y sin copia local: se lee el viejo
    (legacy / "x.json").write_text("{}")
    assert estado_local.ruta_lectura("x.json", "X_PATH") == legacy / "x.json"
    assert estado_local.ruta("x.json", "X_PATH") == local / "x.json"     # se escribe en la local
    # en cuanto existe la local, manda la local
    local.mkdir()
    (local / "x.json").write_text("{}")
    assert estado_local.ruta_lectura("x.json", "X_PATH") == local / "x.json"
    # con override de archivo: ése, sin migración
    monkeypatch.setenv("X_PATH", str(tmp_path / "otro.json"))
    assert estado_local.ruta_lectura("x.json", "X_PATH") == tmp_path / "otro.json"
    assert estado_local.ruta("x.json", "X_PATH") == tmp_path / "otro.json"


def test_snapshot_del_store_va_a_la_carpeta_local_y_migra_el_viejo(monkeypatch, tmp_path) -> None:
    local, legacy = tmp_path / "local", tmp_path / "data"
    legacy.mkdir()
    _sin_overrides(monkeypatch, local, legacy)
    sym = "MERV - XMEV - TESTLOCAL - 24hs"
    # el snapshot viejo que dejó la versión anterior en data/
    viejo = {"saved_at": time.time() - 3600,
             "symbols": {sym: {"symbol": sym, "last": 123.4, "close": 120.0, "updated_at": time.time() - 3600}}}
    (legacy / "market_snapshot.json").write_text(json.dumps(viejo), encoding="utf-8")
    store = mds.get_store()
    store._data.pop(sym, None)
    assert store_persist.path() == local / "market_snapshot.json"
    assert store_persist.load() >= 1                                     # 1er arranque: abre poblado
    assert store.get(sym).last == 123.4
    # el guardado va a la local; data/ no se toca
    antes = (legacy / "market_snapshot.json").read_bytes()
    assert store_persist.save() is True
    assert (local / "market_snapshot.json").is_file()
    assert (legacy / "market_snapshot.json").read_bytes() == antes
    assert not any(p.name != "market_snapshot.json" for p in legacy.iterdir())   # sin .tmp en data/
    # desde ahí se lee la local (el viejo ya no cuenta)
    (legacy / "market_snapshot.json").write_text("roto", encoding="utf-8")
    store._data.pop(sym, None)
    assert store_persist.load() >= 1 and store.get(sym).last == 123.4
    store._data.pop(sym, None)


def test_bna_y_riesgo_pais_escriben_local_y_leen_el_viejo_una_vez(monkeypatch, tmp_path) -> None:
    local, legacy = tmp_path / "local", tmp_path / "data"
    legacy.mkdir()
    _sin_overrides(monkeypatch, local, legacy)
    assert bna_fx._path() == local / "bna_fx.json"
    assert riesgo_pais._path() == local / "riesgo_pais.json"
    (legacy / "bna_fx.json").write_text(json.dumps(
        {"billete": {"compra": 1380.0, "venta": 1430.0, "fecha": "2026-10-14"}, "divisa": None,
         "actualizado": "2026-10-14T10:00:00"}), encoding="utf-8")
    (legacy / "riesgo_pais.json").write_text(json.dumps(
        {"puntos": [{"fecha": "2026-10-13", "valor": 650}, {"fecha": "2026-10-14", "valor": 640}]}),
        encoding="utf-8")
    assert bna_fx._leer_archivo()["billete"]["venta"] == 1430.0
    assert [v for _f, v in riesgo_pais._leer_archivo()] == [650.0, 640.0]
    # la escritura va a la local
    riesgo_pais._escribir_archivo([("2026-10-14", 640.0)])
    assert (local / "riesgo_pais.json").is_file()
    assert [v for _f, v in riesgo_pais._leer_archivo()] == [640.0]       # ya lee la local
    assert sorted(p.name for p in legacy.iterdir()) == ["bna_fx.json", "riesgo_pais.json"]


def test_ningun_cache_por_maquina_apunta_a_data_del_clon(monkeypatch) -> None:
    """Sin overrides, ningún escritor periódico cae adentro del clon."""
    for env in ("MARKET_SNAPSHOT_PATH", "BNA_FX_PATH", "RIESGO_PAIS_PATH", "BONOS_LOCAL_DIR"):
        monkeypatch.delenv(env, raising=False)
    for p in (store_persist.path(), bna_fx._path(), riesgo_pais._path()):
        assert ROOT not in p.parents, p


def test_el_dump_cer_de_indices_va_a_la_carpeta_local() -> None:
    """indices.main() deja el CER proyectado para mirar a mano: antes en la raíz
    del clon (cada PC en cada arranque → copias en conflicto); ahora en la
    carpeta local (la suite la apunta a un tmp vía BONOS_LOCAL_DIR)."""
    import os

    import rentafija
    assert len(rentafija.inputs) > 0                                     # fuerza indices.main() una vez
    assert (Path(os.environ["BONOS_LOCAL_DIR"]) / "cer_completo.generated.csv").is_file()
    src = (ROOT / "indices.py").read_text(encoding="utf-8")
    assert 'os.environ.get("CER_PROY_DUMP_PATH", "cer_completo.generated.csv")' not in src
