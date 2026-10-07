"""Pizarra de Inicio — cuadros elegidos por CADA usuario (07/10).

El usuario arma su propia pizarra debajo del resumen: cuadros "libro" (el
mismo libro con profundidad y TIR por nivel de Mercado / Órdenes) o
"cotización" (cuadro compacto estilo BYMA: último, puntas con cantidad, var,
máx/mín, volumen, TIR / TEM / duration). Se guardan POR USUARIO en
`data/pizarra.json` (fuera de git, como `escenario_prefs.json`); por default
nadie tiene cuadros. La métrica por nivel de los libros (`y`: tirea / tem /
tna / margen) también es por usuario y vale para todos sus libros.

El render de la pizarra es UN request por tick para todos los cuadros
(`routes.inicio`): este módulo sólo persiste. Validaciones acá: el código
tiene que ser un bono del universo, `tipo` libro | cotizacion, `plazo`
24hs | CI, tope de cuadros y sin duplicados (mismo código + tipo + plazo).

    PIZARRA_PATH=…   archivo (default data/pizarra.json; la suite lo apunta a un tmp)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.pizarra")

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = REPO_ROOT / "data" / "pizarra.json"
_lock = threading.Lock()

TIPOS = ("libro", "cotizacion")
PLAZOS = ("24hs", "CI")
METRICAS = ("tirea", "tem", "tna", "margen")
MAX_CUADROS = 24

# Versión por usuario (memoria del proceso): sube con cada mutación. La ruta
# la mete en la key de su memo de render → un cuadro recién agregado se ve en
# el próximo refresh aunque la seq del feed esté quieta.
_version: Dict[str, int] = {}


def _path() -> Path:
    return Path(os.getenv("PIZARRA_PATH") or _DEFAULT_PATH)


class PizarraError(ValueError):
    """Error de negocio (mensaje apto para mostrar al usuario)."""


def _sane_cuadro(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip().upper()
    tipo = str(raw.get("tipo") or "libro").strip().lower()
    plazo = str(raw.get("plazo") or "24hs").strip()
    plazo = "CI" if plazo.lower().startswith("ci") else "24hs"
    if not code or tipo not in TIPOS:
        return None
    return {"code": code, "tipo": tipo, "plazo": plazo}


def _sane_user(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    y = str(raw.get("y") or "tirea").lower()
    cuadros = [c for c in (_sane_cuadro(x) for x in (raw.get("cuadros") or [])) if c]
    return {"y": y if y in METRICAS else "tirea", "cuadros": cuadros[:MAX_CUADROS]}


def _vacio() -> Dict[str, Any]:
    return {"v": 1, "users": {}}


def _load_all(strict: bool = False) -> Dict[str, Any]:
    """`strict=True` (los que ESCRIBEN): un archivo que existe pero no se puede
    leer sube el OSError en vez de devolver vacío — si no, el guardado que
    sigue pisaría las pizarras de los demás con sólo la del que guardó."""
    p = _path()
    if not p.is_file():
        return _vacio()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        if strict:
            raise
        logger.exception("[pizarra] archivo ilegible; arranco vacío")
        return _vacio()
    except ValueError as exc:
        from backend.services.archivos import apartar_corrupto
        logger.error("[pizarra] archivo corrupto (%s); lo aparto y arranco vacío", exc)
        apartar_corrupto(p, str(exc))
        return _vacio()
    if not isinstance(data, dict):
        return _vacio()
    users = {u: _sane_user(e) for u, e in (data.get("users") or {}).items() if isinstance(u, str)}
    return {"v": 1, "users": users}


def _write(cur: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _bump(user: str) -> None:
    _version[user] = _version.get(user, 0) + 1


def version(user: str) -> int:
    return _version.get(user, 0)


def load_user(user: str) -> Dict[str, Any]:
    """{"y": métrica, "cuadros": [{code, tipo, plazo}, …]} — vacío por default."""
    return _sane_user(_load_all()["users"].get(user))


def _mutar(user: str, fn) -> Dict[str, Any]:
    with _lock:
        all_ = _load_all(strict=True)
        ent = _sane_user(all_["users"].get(user))
        fn(ent)
        all_["users"][user] = ent
        _write(all_)
        _bump(user)
        return ent


def _codigo_valido(code: str) -> bool:
    from backend.services import bond_universe
    return bond_universe.get(code) is not None


def agregar(user: str, code: str, tipo: str = "libro", plazo: str = "24hs") -> Dict[str, Any]:
    c = _sane_cuadro({"code": code, "tipo": tipo, "plazo": plazo})
    if c is None:
        raise PizarraError("Elegí un bono y un tipo de cuadro (libro o cotización).")
    if not _codigo_valido(c["code"]):
        raise PizarraError(f"'{c['code']}' no es un bono de la app (buscalo por su código, p. ej. GD30 o TX26).")

    def fn(ent: Dict[str, Any]) -> None:
        if c in ent["cuadros"]:
            raise PizarraError(f"{c['code']} · {c['tipo']} · {c['plazo']} ya está en tu pizarra.")
        if len(ent["cuadros"]) >= MAX_CUADROS:
            raise PizarraError(f"La pizarra admite hasta {MAX_CUADROS} cuadros; quitá alguno antes.")
        ent["cuadros"].append(c)

    return _mutar(user, fn)


def quitar(user: str, idx: int) -> Dict[str, Any]:
    def fn(ent: Dict[str, Any]) -> None:
        if 0 <= idx < len(ent["cuadros"]):
            ent["cuadros"].pop(idx)

    return _mutar(user, fn)


def mover(user: str, idx: int, delta: int) -> Dict[str, Any]:
    """Corre el cuadro `idx` una posición (delta −1 / +1)."""
    def fn(ent: Dict[str, Any]) -> None:
        cu = ent["cuadros"]
        j = idx + (1 if delta > 0 else -1)
        if 0 <= idx < len(cu) and 0 <= j < len(cu):
            cu[idx], cu[j] = cu[j], cu[idx]

    return _mutar(user, fn)


def set_metrica(user: str, y: str) -> Dict[str, Any]:
    y = (y or "").lower()
    if y not in METRICAS:
        raise PizarraError("Métrica inválida.")

    def fn(ent: Dict[str, Any]) -> None:
        ent["y"] = y

    return _mutar(user, fn)


def limpiar(user: str) -> Dict[str, Any]:
    def fn(ent: Dict[str, Any]) -> None:
        ent["cuadros"] = []

    return _mutar(user, fn)


def usuarios_con_cuadros() -> List[str]:
    return sorted(u for u, e in _load_all()["users"].items() if e["cuadros"])
