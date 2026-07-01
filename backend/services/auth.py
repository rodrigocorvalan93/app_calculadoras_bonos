"""Auth — login wall + roles (superuser / premium / básico).

Diseño (y performance):
- El store de usuarios es un JSON chico (`auth_store.json`, gitignored) que se
  lee UNA vez y se cachea en memoria bajo lock. Las escrituras (alta/edición de
  usuario, config de tabs) reescriben el archivo y refrescan el cache. El path
  caliente (cada request) sólo lee el cache → dict/set lookups, sub-µs. No hay
  I/O ni hashing por request: el PBKDF2 corre SÓLO en login / reset.
- Contraseñas: PBKDF2-HMAC-SHA256 con salt por usuario (stdlib, sin deps). La
  del superuser NO vive en el código: se siembra en el primer arranque desde
  `APP_SUPERUSER_*`.
- Sesión: cookie firmada por Starlette SessionMiddleware con `secret` (env o
  autogenerado y persistido en el store). Acá sólo guardamos el username; el rol
  se resuelve server-side contra el cache.
- Gating de pestañas: por ROL. `role_tabs` mapea premium/básico → set de tabs;
  el superuser ve todo siempre. Editable desde el panel del superuser.

Modelo de enforcement: se gatea a nivel de PÁGINA (las GET top-level de cada
pestaña). Los sub-endpoints (partials/data) sólo exigen estar logueado —así no
se rompen los endpoints compartidos entre pestañas (p. ej. /historicos/semanal
lo usan Históricos y Qué pasó). Es un modelo de app interna: el muro real es el
login; los roles son tiers de UX, no un sandbox de seguridad duro.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("backend.auth")

REPO_ROOT = Path(__file__).resolve().parents[2]

ROLES: Tuple[str, ...] = ("superuser", "premium", "basico")
ROLE_LABELS: Dict[str, str] = {"superuser": "Superuser", "premium": "Premium", "basico": "Básico"}

# ── Registro de pestañas (orden = orden de la nav) ───────────────────────────
# (key, label es-AR, path de la página). Debe reflejar la nav de base.html.
TABS: List[Tuple[str, str, str]] = [
    ("yas",          "YAS",          "/yas"),
    ("nueva",        "Nueva especie", "/nueva"),
    ("comparador",   "Comparador",   "/comparador"),
    ("curves",       "Curvas",       "/curves"),
    ("mercado",      "Mercado",      "/mercado"),
    ("breakeven",    "Break-even",   "/breakeven"),
    ("dolares",      "Dólares",      "/dolares"),
    ("tasas",        "Tasas",        "/tasas"),
    ("posiciones",   "Posiciones",   "/posiciones"),
    ("matriz",       "Matriz",       "/matriz"),
    ("forwards",     "Forwards",     "/forwards"),
    ("futuros",      "Futuros",      "/futuros"),
    ("graficos",     "Gráficos",     "/graficos"),
    ("total_return", "Total Return", "/total-return"),
    ("escenario",    "Escenario",    "/escenario"),
    ("historicos",   "Históricos",   "/historicos"),
    ("quepaso",      "Qué pasó",     "/que-paso"),
    ("creditos",     "Créditos",     "/creditos"),
    ("cafci",        "CAFCI",        "/cafci"),
    ("ordenes",      "Órdenes",      "/ordenes"),
]
TAB_KEYS: Tuple[str, ...] = tuple(k for k, _, _ in TABS)
_TAB_LABEL: Dict[str, str] = {k: lbl for k, lbl, _ in TABS}
_TAB_PATH: Dict[str, str] = {k: p for k, _, p in TABS}
# páginas por longitud de path desc → longest-prefix match para 'activa'/gating
_PAGES_BY_LEN: List[Tuple[str, str]] = sorted(((p, k) for k, _, p in TABS),
                                              key=lambda t: len(t[0]), reverse=True)

# Default: básico ve un set acotado; premium ve todo. Editable por el superuser.
_DEFAULT_BASICO = ["yas", "nueva", "comparador", "curves", "breakeven",
                   "dolares", "tasas", "graficos", "historicos", "quepaso"]
_DEFAULT_ROLE_TABS: Dict[str, List[str]] = {
    "premium": list(TAB_KEYS),
    "basico": _DEFAULT_BASICO,
}

_PBKDF2_ITERS = 200_000

_lock = threading.RLock()
_cache: Optional[Dict[str, Any]] = None


# ── Path + persistencia ──────────────────────────────────────────────────────
def _store_path() -> Path:
    from backend.config import settings
    p = (settings.app_users_path or "").strip()
    if p:
        return Path(os.path.expandvars(os.path.expanduser(p)))
    return REPO_ROOT / "auth_store.json"


def _load() -> Dict[str, Any]:
    path = _store_path()
    data: Dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            logger.error("[auth] no pude leer %s: %s", path, exc)
            data = {}
    data.setdefault("users", {})
    data.setdefault("role_tabs", {k: list(v) for k, v in _DEFAULT_ROLE_TABS.items()})
    data.setdefault("secret", "")
    return data


def _save_locked(data: Dict[str, Any]) -> None:
    """Escribe el store de forma atómica (tmp + replace). Llamar bajo _lock."""
    path = _store_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _store() -> Dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache


def refresh() -> None:
    global _cache
    with _lock:
        _cache = _load()
        _nav_cache.clear()


# ── Hashing ──────────────────────────────────────────────────────────────────
def _hash(password: str, salt: bytes, iters: int = _PBKDF2_ITERS) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return dk.hex()


def _make_record(password: str, role: str, email: str = "") -> Dict[str, Any]:
    salt = os.urandom(16)
    return {
        "role": role,
        "email": (email or "").strip(),
        "salt": salt.hex(),
        "hash": _hash(password, salt),
        "iterations": _PBKDF2_ITERS,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def verify_password(username: str, password: str) -> bool:
    u = _store()["users"].get(_norm(username))
    if not u:
        return False
    try:
        salt = bytes.fromhex(u["salt"])
        calc = _hash(password, salt, int(u.get("iterations", _PBKDF2_ITERS)))
        return hmac.compare_digest(calc, u["hash"])
    except Exception:  # noqa: BLE001
        return False


def _norm(username: str) -> str:
    return (username or "").strip().lower()


# ── Secret de sesión ─────────────────────────────────────────────────────────
def get_secret_key() -> str:
    """Clave de firma de la cookie. Prioridad: env APP_SECRET_KEY > store. Si no
    hay ninguna, genera una y la persiste (sesiones sobreviven reinicios)."""
    from backend.config import settings
    if settings.app_secret_key:
        return settings.app_secret_key
    with _lock:
        data = _store()
        if not data.get("secret"):
            data["secret"] = secrets.token_hex(32)
            _save_locked(data)
        return data["secret"]


# ── Bootstrap del superuser ──────────────────────────────────────────────────
def ensure_bootstrapped() -> Dict[str, Any]:
    """Crea el superuser desde APP_SUPERUSER_* si el store no tiene ninguno.
    Idempotente. Devuelve {created, user, warning}."""
    from backend.config import settings
    with _lock:
        data = _store()
        has_su = any(u.get("role") == "superuser" for u in data["users"].values())
        if has_su:
            return {"created": False, "user": None, "warning": None}
        user = _norm(settings.app_superuser_user)
        pwd = settings.app_superuser_password
        if not user or not pwd:
            msg = ("No hay superuser y faltan APP_SUPERUSER_USER / APP_SUPERUSER_PASSWORD; "
                   "nadie podrá loguearse. Seteá esas env vars y reiniciá.")
            logger.warning("[auth] %s", msg)
            return {"created": False, "user": None, "warning": msg}
        data["users"][user] = _make_record(pwd, "superuser", settings.app_superuser_email)
        _save_locked(data)
        logger.info("[auth] superuser '%s' creado desde env (bootstrap)", user)
        return {"created": True, "user": user, "warning": None}


def has_any_superuser() -> bool:
    return any(u.get("role") == "superuser" for u in _store()["users"].values())


# ── Consultas de usuario / rol ───────────────────────────────────────────────
def get_user(username: str) -> Optional[Dict[str, Any]]:
    u = _store()["users"].get(_norm(username))
    if not u:
        return None
    return {"username": _norm(username), "role": u.get("role"), "email": u.get("email", ""),
            "created": u.get("created")}


def list_users() -> List[Dict[str, Any]]:
    out = [{"username": name, "role": u.get("role"), "email": u.get("email", ""),
            "created": u.get("created")} for name, u in _store()["users"].items()]
    out.sort(key=lambda x: (x["role"] != "superuser", x["username"]))
    return out


def role_of(username: str) -> Optional[str]:
    u = _store()["users"].get(_norm(username))
    return u.get("role") if u else None


# ── Tabs por rol ─────────────────────────────────────────────────────────────
def role_tabs() -> Dict[str, List[str]]:
    return _store()["role_tabs"]


def allowed_tabs(role: Optional[str]) -> List[str]:
    """Keys de tabs permitidas (en el orden de TABS). Superuser → todas."""
    if role == "superuser":
        return list(TAB_KEYS)
    allowed = set(_store()["role_tabs"].get(role or "", []))
    return [k for k in TAB_KEYS if k in allowed]


_nav_cache: Dict[str, List[Dict[str, str]]] = {}


def nav_for(role: Optional[str]) -> List[Dict[str, str]]:
    """Items de nav (key/label/path) permitidos para el rol, en orden. Cacheado
    por rol: el middleware lo pide en CADA request (incluido el poller de 1/s),
    y `role_tabs` sólo cambia desde el panel → sin esto se reconstruían ~20 dicts
    por request. El cache se invalida en `refresh()` y `set_role_tabs()`. Se
    devuelve la MISMA lista (read-only en los templates)."""
    key = role or ""
    cached = _nav_cache.get(key)
    if cached is None:
        cached = [{"key": k, "label": _TAB_LABEL[k], "path": _TAB_PATH[k]} for k in allowed_tabs(role)]
        _nav_cache[key] = cached
    return cached


def active_tab(path: str) -> Optional[str]:
    """Tab-key para RESALTAR en la nav: match por prefijo más largo, así
    /yas/recompute resalta 'YAS'. NO se usa para gating."""
    for p, k in _PAGES_BY_LEN:
        if path == p or path.startswith(p + "/"):
            return k
    return None


def page_tab(path: str) -> Optional[str]:
    """Tab-key de la PÁGINA EXACTA (para gating), o None. Sólo la GET top-level de
    la pestaña matchea (/yas, /que-paso, …); los sub-endpoints (/yas/recompute,
    /dolares/rail, /historicos/semanal) devuelven None → NO se gatean por tab.

    Clave: endpoints GLOBALES o COMPARTIDOS (el riel /dolares/rail que sondea toda
    página, /historicos/semanal que usan Históricos y Qué pasó) NO deben quedar
    atados a la pestaña de su prefijo, o un rol sin esa pestaña recibiría 403 en
    cada página. El gating es a nivel de página; el resto sólo pide sesión."""
    for p, k in _PAGES_BY_LEN:
        if path == p or path == p + "/":
            return k
    return None


def can_access_path(role: Optional[str], path: str) -> bool:
    """True si el rol puede acceder a `path`. Sólo se gatea la PÁGINA de pestaña
    (match exacto); todo lo demás (sub-endpoints) pasa con estar logueado."""
    tab = page_tab(path)
    if tab is None:
        return True
    if role == "superuser":
        return True
    return tab in set(_store()["role_tabs"].get(role or "", []))


# ── Mutaciones (panel superuser) ─────────────────────────────────────────────
class AuthError(ValueError):
    """Error de negocio de auth (mensaje apto para mostrar al usuario)."""


def create_user(username: str, password: str, role: str, email: str = "") -> None:
    name = _norm(username)
    if not name or not name.isidentifier():
        raise AuthError("El usuario debe ser alfanumérico (sin espacios ni símbolos).")
    if role not in ROLES:
        raise AuthError(f"Rol inválido: {role!r}.")
    if not password or len(password) < 6:
        raise AuthError("La contraseña debe tener al menos 6 caracteres.")
    with _lock:
        data = _store()
        if name in data["users"]:
            raise AuthError(f"El usuario '{name}' ya existe.")
        data["users"][name] = _make_record(password, role, email)
        _save_locked(data)


def set_password(username: str, password: str) -> None:
    name = _norm(username)
    if not password or len(password) < 6:
        raise AuthError("La contraseña debe tener al menos 6 caracteres.")
    with _lock:
        data = _store()
        u = data["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        rec = _make_record(password, u.get("role", "basico"), u.get("email", ""))
        data["users"][name] = rec
        _save_locked(data)


def update_user(username: str, role: Optional[str] = None, email: Optional[str] = None) -> None:
    name = _norm(username)
    with _lock:
        data = _store()
        u = data["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        if role is not None:
            if role not in ROLES:
                raise AuthError(f"Rol inválido: {role!r}.")
            # no dejar el sistema sin superuser
            if u.get("role") == "superuser" and role != "superuser" and _count_superusers(data) <= 1:
                raise AuthError("No podés degradar al último superuser.")
            u["role"] = role
        if email is not None:
            u["email"] = email.strip()
        _save_locked(data)


def delete_user(username: str) -> None:
    name = _norm(username)
    with _lock:
        data = _store()
        u = data["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        if u.get("role") == "superuser" and _count_superusers(data) <= 1:
            raise AuthError("No podés borrar al último superuser.")
        del data["users"][name]
        _save_locked(data)


def set_role_tabs(role: str, tabs: List[str]) -> None:
    if role not in ("premium", "basico"):
        raise AuthError("Sólo se configuran las pestañas de premium y básico "
                        "(el superuser ve todo).")
    clean = [t for t in tabs if t in TAB_KEYS]
    with _lock:
        data = _store()
        data["role_tabs"][role] = clean
        _save_locked(data)
        _nav_cache.pop(role, None)


def _count_superusers(data: Dict[str, Any]) -> int:
    return sum(1 for u in data["users"].values() if u.get("role") == "superuser")


# ── Tokens de reset (firmados, con expiración) ───────────────────────────────
def make_reset_token(username: str, ttl_seconds: int = 3600) -> str:
    import time
    name = _norm(username)
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{name}:{exp}".encode("utf-8")
    sig = hmac.new(get_secret_key().encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + sig


def check_reset_token(token: str) -> Optional[str]:
    """Devuelve el username si el token es válido y no expiró, si no None."""
    import time
    try:
        b64, sig = (token or "").split(".", 1)
        pad = "=" * (-len(b64) % 4)
        payload = base64.urlsafe_b64decode(b64 + pad)
        expected = hmac.new(get_secret_key().encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        name, exp = payload.decode("utf-8").rsplit(":", 1)
        if int(exp) < int(time.time()):
            return None
        return name if name in _store()["users"] else None
    except Exception:  # noqa: BLE001
        return None


def find_user_by_email(email: str) -> Optional[str]:
    e = (email or "").strip().lower()
    if not e:
        return None
    for name, u in _store()["users"].items():
        if (u.get("email") or "").strip().lower() == e:
            return name
    return None
