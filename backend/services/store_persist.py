"""Persistencia del MarketDataStore entre reinicios.

Sin esto, un reinicio fuera de rueda arranca con el store VACÍO: el riel, las
curvas y los paneles quedan en blanco hasta que el feed reenvía los cierres
(y si el broker está caído, indefinidamente). Guardamos el snapshot completo
a disco (JSON, ~1 MB para ~1000 símbolos) y lo reponemos al boot — la app
abre ya poblada con el último dato conocido; el dot del feed sigue mostrando
el estado real (los restores no bumpean la secuencia ni updated_at).

Se guarda cada `SAVE_EVERY_SECONDS` (crash-safe) y al shutdown; se repone al
boot si el archivo tiene menos de `MAX_AGE_DAYS` (un fin de semana largo
entra; un snapshot de hace un mes ya es ruido). Path por env
`MARKET_SNAPSHOT_PATH` o `data/market_snapshot.json` en el repo (fuera de
git: el .gitignore whitelist ignora `data/`).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from backend.services import marketdata_store

logger = logging.getLogger("backend.store_persist")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = REPO_ROOT / "data" / "market_snapshot.json"

SAVE_EVERY_SECONDS = 300.0
MAX_AGE_DAYS = 5.0


def path() -> Path:
    return Path(os.getenv("MARKET_SNAPSHOT_PATH") or _DEFAULT_PATH)


def save() -> bool:
    """Vuelca el store a disco (atómico: tmp + replace). False si el store
    está vacío — nunca pisamos un snapshot bueno con uno vacío."""
    symbols = marketdata_store.get_store().to_persist()
    if not symbols:
        return False
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"saved_at": time.time(), "symbols": symbols},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        logger.exception("[store_persist] no pude guardar el snapshot en %s", p)
        return False


def load() -> int:
    """Repone el snapshot persistido en el store. Devuelve # símbolos
    repuestos (0 si no hay archivo, está viejo o no parsea)."""
    p = path()
    if not p.is_file():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("[store_persist] snapshot ilegible en %s", p)
        return 0
    saved_at = data.get("saved_at") or 0
    age_days = (time.time() - saved_at) / 86400.0 if saved_at else None
    if age_days is None or age_days > MAX_AGE_DAYS:
        logger.info("[store_persist] snapshot descartado por viejo (%.1f días)",
                    age_days if age_days is not None else -1)
        return 0
    n = marketdata_store.get_store().restore(data.get("symbols") or {})
    if n:
        logger.info("[store_persist] %d símbolos restaurados (snapshot de hace %.1f h)",
                    n, age_days * 24)
    return n
