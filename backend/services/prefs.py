"""Preferencias de interfaz POR USUARIO en el server (glow-up D, 06/11).

Hasta ahora cada preferencia chica (tema, riel de dólar plegado, métrica del
libro, último fondo de Posiciones, recientes de Ctrl+K, …) vivía SÓLO en el
`localStorage` del navegador: cambiar de PC o de navegador era arrancar de
cero. Acá se guardan por username en `data/prefs.json` (compartido a
propósito, como la pizarra: lo escribe una acción del usuario) y `app.js`
las sincroniza: al cargar la página trae las del server para las claves que
el navegador todavía no tiene, y cada tanto manda las que cambiaron.

Sólo claves de una ALLOWLIST (`CLAVES`), valores string (lo que guarda
localStorage) acotados; nunca se interpreta nada del lado del server.

    PREFS_PATH=…   archivo (default data/prefs.json; la suite lo apunta a un tmp)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("backend.prefs")

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = REPO_ROOT / "data" / "prefs.json"
_lock = threading.Lock()

# Claves que viajan (son las de localStorage). Cualquier otra se ignora.
CLAVES = ("yas_theme", "fx_rail", "book-y", "pos_fondo", "graf_tabla_open",
          "graf_emis", "graf_emis_open", "graf_emis_ref", "hc_labels",
          "curvas_combos", "ck_recent", "qp_excl")
MAX_VALOR = 4000
MAX_USUARIO = 64


def _path() -> Path:
    return Path(os.getenv("PREFS_PATH") or _DEFAULT_PATH)


def _load_all(strict: bool = False) -> Dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"v": 1, "users": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        if strict:
            raise
        logger.exception("[prefs] archivo ilegible; arranco vacío")
        return {"v": 1, "users": {}}
    except ValueError as exc:
        from backend.services.archivos import apartar_corrupto
        dst = apartar_corrupto(p, str(exc))
        if strict and dst is None:
            raise OSError(f"prefs corrupto y no se pudo apartar: {p}") from exc
        logger.error("[prefs] archivo corrupto (%s); %s", exc,
                     f"apartado como {dst.name}" if dst else "arranco vacío")
        return {"v": 1, "users": {}}
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, dict):
        return {"v": 1, "users": {}}
    return {"v": 1, "users": {u: sanear(e) for u, e in users.items() if isinstance(u, str)}}


def sanear(raw: Any) -> Dict[str, str]:
    """Sólo claves conocidas, valores string acotados."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if k not in CLAVES or v is None:
            continue
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        if len(s) <= MAX_VALOR:
            out[k] = s
    return out


def _write(cur: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def load_user(user: str) -> Dict[str, str]:
    return dict(_load_all()["users"].get(str(user)[:MAX_USUARIO]) or {})


def set_user(user: str, cambios: Any) -> Dict[str, str]:
    """Mergea `cambios` (dict clave → string; `None` borra la clave) en las
    prefs del usuario y devuelve el resultado. Claves desconocidas se ignoran."""
    user = str(user)[:MAX_USUARIO]
    nuevos = sanear(cambios)
    borrar = [k for k, v in (cambios.items() if isinstance(cambios, dict) else []) if v is None and k in CLAVES]
    with _lock:
        all_ = _load_all(strict=True)
        ent = dict(all_["users"].get(user) or {})
        ent.update(nuevos)
        for k in borrar:
            ent.pop(k, None)
        if ent != (all_["users"].get(user) or {}):
            all_["users"][user] = ent
            _write(all_)
        return ent
