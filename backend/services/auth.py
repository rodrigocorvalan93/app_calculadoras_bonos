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
import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

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
    ("alertas",      "Alertas",      "/alertas"),
]
# Tabs que NO entran en los defaults de ningún rol: son superuser-only por
# middleware (main._SUPERUSER_ONLY); listarlas en la nav de premium/básico
# sólo mostraría un link a un 403.
_SUPERUSER_ONLY_TABS = ("alertas",)

# ── Features por rol (paneles/funciones sueltas, no pestañas) ────────────────
# Registro de features gateables desde el panel del superuser: el superuser
# las tiene TODAS siempre; premium/básico arrancan sin ninguna (default
# restrictivo) hasta que el superuser las tilda en /admin. Agregar una feature
# nueva = una línea acá + su gate en main._FEATURE_PATHS / el template.
# (Alertas NO es una feature: es superuser-exclusiva por diseño.)
FEATURES: List[Tuple[str, str]] = [
    ("cafci_fondos", "Panel VCP fondos propios (API CAFCI)"),
]
FEATURE_KEYS: Tuple[str, ...] = tuple(k for k, _ in FEATURES)
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
    "premium": [k for k in TAB_KEYS if k not in _SUPERUSER_ONLY_TABS],
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
            # NO devolver {} y seguir: la próxima escritura (get_secret_key /
            # bootstrap) persistiría el store vacío, BORRANDO todos los usuarios y
            # rotando el secret de firma (invalida todas las sesiones). Un archivo
            # existente pero ilegible es un problema de operación (disco, corrupción,
            # edición manual), no un "primer arranque": fallamos ruidoso para que el
            # operador lo restaure en vez de destruirlo en silencio.
            logger.error("[auth] store ILEGIBLE %s: %s — abortando para no sobrescribirlo", path, exc)
            raise RuntimeError(
                f"auth_store ilegible ({path}): {exc}. Se aborta para no pisarlo vacío; "
                "restaurá el archivo o movelo y reiniciá para bootstrap limpio.") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"auth_store con formato inesperado ({path}): se esperaba un objeto JSON.")
    data.setdefault("users", {})
    data.setdefault("role_tabs", {k: list(v) for k, v in _DEFAULT_ROLE_TABS.items()})
    data.setdefault("role_features", {})     # rol → features tildadas (default: ninguna)
    data.setdefault("secret", "")
    return data


def _save_locked(data: Dict[str, Any]) -> None:
    """Escribe el store de forma atómica (tmp + fsync + replace) con permisos 0600.
    Contiene hashes de contraseñas y el secret de firma de sesión, así que el
    archivo no debe quedar world-readable (umask default lo dejaría 0644, y
    cualquier cuenta local podría forjar una sesión superuser). Llamar bajo _lock."""
    path = _store_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # O_CREAT con modo 0600 → sólo el dueño lee/escribe. Si el tmp ya existía con
    # otros permisos, O_TRUNC lo vacía pero el modo no cambia; lo forzamos igual.
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        # os.fchmod no existe en Windows antes de Python 3.13: ahí el archivo
        # queda protegido por las ACL del perfil del usuario (el store vive
        # fuera de OneDrive, bajo la cuenta del servicio) y chmod sólo toca el
        # bit read-only. En Unix el fchmod fuerza 0600 aunque el tmp ya
        # existiera con otro modo. Antes: AttributeError → NINGÚN guardado de
        # usuarios/claves/tokens funcionaba en un server Windows.
        fchmod = getattr(os, "fchmod", None)
        if fchmod is not None:
            fchmod(fd, 0o600)
        else:
            try:
                os.chmod(str(tmp), 0o600)
            except OSError:
                pass
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())        # durabilidad: sobrevive un corte tras el replace
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)


_disk_lock = threading.Lock()      # serializa las escrituras a disco; los LECTORES no lo tocan


def _mutar(fn):
    """Copy-on-write del store: `fn(data)` muta una COPIA (bajo _lock, µs), la
    copia se escribe a disco FUERA de _lock (fsync + replace: decenas o cientos
    de ms con OneDrive / antivirus) y recién entonces se publica. Así

      - los lectores (`_store()`: el middleware en cada request, el feed) nunca
        esperan el disco — antes compartían el RLock con el guardado y un
        guardado lento de /admin frenaba /market/seq de toda la mesa
        (auditoría 30/09: 150 ms de disco = 153 ms de latencia);
      - un cambio se ve recién cuando ya es durable: si el disco falla, el
        store en memoria queda como estaba (F05 — antes: descartar la copia
        mutada y releer).

    Dos mutaciones cruzadas: la segunda se reaplica sobre el resultado de la
    primera (`fn` se re-ejecuta, tiene que ser determinista sobre `data`; una
    AuthError sube sin escribir nada). Devuelve lo que devuelva `fn`."""
    global _cache, _excel_index
    for _ in range(16):
        with _lock:
            base = _store()
            nuevo = copy.deepcopy(base)
            out = fn(nuevo)
        with _disk_lock:
            with _lock:
                if _cache is not base:        # se publicó otra versión: reaplicar
                    continue
            _save_locked(nuevo)               # el disco, sin _lock tomado
            with _lock:
                _cache = nuevo
                _nav_cache.clear()
                _feat_cache.clear()
                _excel_index = None
            return out
    raise RuntimeError("auth: demasiadas mutaciones concurrentes del store")


def _store() -> Dict[str, Any]:
    """Store en memoria. Lectura de la referencia SIN lock (atómica por el
    GIL): `_mutar` nunca muta lo publicado, publica una versión nueva."""
    global _cache
    c = _cache
    if c is not None:
        return c
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache


def refresh() -> None:
    global _cache, _excel_index
    with _lock:
        _cache = _load()
        _nav_cache.clear()
        _feat_cache.clear()
        _excel_index = None


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
        # Identidad de la CUENTA (no del nombre): la cookie la lleva y el
        # middleware la compara. Borrar y recrear un usuario con el mismo
        # nombre da otro uid → las cookies del anterior no autentican al nuevo
        # (auditoría R04/B06: antes el sv arrancaba en 0 y la cookie vieja
        # entraba con el rol del recreado).
        "uid": secrets.token_hex(8),
    }


# Salt fijo para el branch de usuario-ausente: corre un PBKDF2 del mismo costo
# que una verificación real, así el tiempo de respuesta NO revela si el usuario
# existe (anti-enumeración por timing). Se genera una vez por proceso.
_DUMMY_SALT = os.urandom(16)


def verify_password(username: str, password: str) -> bool:
    u = _store()["users"].get(_norm(username))
    if not u:
        # Trabajo equivalente a un login real: sin esto, un usuario inexistente
        # responde en sub-µs y uno real en ~50 ms → oráculo de enumeración.
        _hash(password, _DUMMY_SALT)
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
    secret = _store().get("secret")
    if secret:
        return secret

    def fn(d: Dict[str, Any]) -> str:
        if not d.get("secret"):
            d["secret"] = secrets.token_hex(32)
        return d["secret"]

    return _mutar(fn)


# ── Bootstrap del superuser ──────────────────────────────────────────────────
def ensure_bootstrapped() -> Dict[str, Any]:
    """Crea el superuser desde APP_SUPERUSER_* si el store no tiene ninguno.
    Idempotente. Devuelve {created, user, warning}."""
    from backend.config import settings
    data = _store()
    # Registros anteriores a la versión con `uid`: se les asigna uno (una
    # sola vez, persistido). Hasta acá su uid es "" y una cookie con "" los
    # autentica; desde acá, sólo las cookies emitidas para este uid.
    sin_uid = any(isinstance(u, dict) and not u.get("uid") for u in data["users"].values())
    has_su = any(u.get("role") == "superuser" for u in data["users"].values())
    user = _norm(settings.app_superuser_user)
    pwd = settings.app_superuser_password
    # PBKDF2 (~0,2 s) fuera del lock, sólo si hay que crear el superuser
    rec = _make_record(pwd, "superuser", settings.app_superuser_email) if (not has_su and user and pwd) else None
    if sin_uid or rec is not None:
        def fn(d: Dict[str, Any]) -> bool:
            for u in d["users"].values():
                if isinstance(u, dict) and not u.get("uid"):
                    u["uid"] = secrets.token_hex(8)
            if rec is not None and not any(u.get("role") == "superuser" for u in d["users"].values()):
                d["users"][user] = dict(rec)
                return True
            return False

        if _mutar(fn):
            logger.info("[auth] superuser '%s' creado desde env (bootstrap)", user)
            return {"created": True, "user": user, "warning": None}
    if has_su or any(u.get("role") == "superuser" for u in _store()["users"].values()):
        return {"created": False, "user": None, "warning": None}
    msg = ("No hay superuser y faltan APP_SUPERUSER_USER / APP_SUPERUSER_PASSWORD; "
           "nadie podrá loguearse. Seteá esas env vars y reiniciá.")
    logger.warning("[auth] %s", msg)
    return {"created": False, "user": None, "warning": msg}


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
            "created": u.get("created"),
            "excel_enabled": bool(u.get("excel_enabled")),
            "excel_token": u.get("excel_token") or "",
            # None = ve todos los fondos; lista = allowlist (panel /admin)
            "fondos": u.get("fondos")} for name, u in _store()["users"].items()]
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


# Prefijos cuyo SUBÁRBOL COMPLETO se gatea por su tab (no sólo la página exacta).
# Para superficies sensibles —plata real o data confidencial del desk— donde los
# sub-endpoints NO son compartidos entre pestañas: un rol sin la pestaña no debe
# alcanzar NINGÚN sub-endpoint de ese prefijo.
#   /ordenes    → ticket, confirmar, multi, kill, live, quote…
#   /posiciones → /posiciones/table, /posiciones/targets (tenencias reales de los
#                 fondos: VN, valor, %PN por bono). Gatear sólo la página dejaba
#                 los partials de datos abiertos a cualquier rol logueado.
#   /matriz     → /matriz/table (matriz cruzada de tenencias por fondo).
# El modelo general sigue siendo página-exacta (así /dolares/rail, /historicos/
# semanal y demás partials COMPARTIDOS no se atan a la pestaña de su prefijo).
_TAB_PREFIX_GATED: Tuple[Tuple[str, str], ...] = (
    ("/ordenes", "ordenes"),
    ("/posiciones", "posiciones"),
    ("/matriz", "matriz"),
)


def can_access_path(role: Optional[str], path: str) -> bool:
    """True si el rol puede acceder a `path`. Las superficies sensibles
    (`_TAB_PREFIX_GATED`) se gatean por todo el subárbol; el resto sólo gatea la
    PÁGINA de pestaña (match exacto) y deja pasar los sub-endpoints compartidos."""
    if role == "superuser":
        return True
    for prefix, tab in _TAB_PREFIX_GATED:
        if path == prefix or path.startswith(prefix + "/"):
            return tab in set(_store()["role_tabs"].get(role or "", []))
    tab = page_tab(path)
    if tab is None:
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
    if name in _store()["users"]:
        raise AuthError(f"El usuario '{name}' ya existe.")
    # El PBKDF2 (200k iteraciones, ~0,2 s) corre FUERA del lock: `_store()` lo
    # toma en cada request (auth_guard, ~4 veces) y el feed también → un alta
    # o cambio de clave frenaba a toda la mesa mientras se calculaba el hash.
    rec = _make_record(password, role, email)

    def fn(d: Dict[str, Any]) -> None:
        if name in d["users"]:
            raise AuthError(f"El usuario '{name}' ya existe.")
        d["users"][name] = dict(rec)

    _mutar(fn)


def _perfil_para_clave(name: str) -> Tuple[str, str]:
    """(role, email) del usuario para armar el registro nuevo; AuthError si
    no existe."""
    u = _store()["users"].get(name)
    if not u:
        raise AuthError(f"El usuario '{name}' no existe.")
    return u.get("role", "basico"), u.get("email", "")


def _aplicar_clave(data: Dict[str, Any], name: str, rec: Dict[str, Any]) -> None:
    """Instala `rec` (registro con la clave nueva, ya hasheada) en `data`
    conservando lo que NO es clave. Corre adentro de `_mutar` (sobre la copia)."""
    u = data["users"].get(name)
    if not u:
        raise AuthError(f"El usuario '{name}' no existe.")
    rec = dict(rec)
    # rol / mail vigentes (por si cambiaron mientras se hasheaba)
    rec["role"] = u.get("role", rec.get("role", "basico"))
    if "email" in rec:
        rec["email"] = u.get("email", rec["email"])
    # el reset de contraseña no debe cortar el acceso Excel ya otorgado
    rec["excel_enabled"] = bool(u.get("excel_enabled"))
    rec["excel_token"] = u.get("excel_token", "")
    # ...ni pisar la visibilidad de fondos configurada
    if u.get("fondos") is not None:
        rec["fondos"] = u.get("fondos")
    # Clave nueva ⇒ las sesiones web anteriores dejan de valer (F06).
    rec["sv"] = int(u.get("sv") or 0) + 1
    # ...pero la cuenta es la MISMA: el uid se conserva (sólo cambia al
    # borrar y recrear el usuario).
    rec["uid"] = u.get("uid") or rec["uid"]
    data["users"][name] = rec


def set_password(username: str, password: str) -> None:
    name = _norm(username)
    if not password or len(password) < 6:
        raise AuthError("La contraseña debe tener al menos 6 caracteres.")
    role, email = _perfil_para_clave(name)
    rec = _make_record(password, role, email)        # hash fuera del lock
    _mutar(lambda d: _aplicar_clave(d, name, rec))


def session_uid(username: Optional[str]) -> str:
    """Identidad de la cuenta que viaja en la cookie (`uid`). "" si el usuario
    no existe o el registro es anterior al campo (hasta el próximo
    `ensure_bootstrapped`, que lo completa)."""
    if not username:
        return ""
    u = _store()["users"].get(_norm(username))
    return str((u or {}).get("uid") or "")


def session_version(username: Optional[str]) -> int:
    """Versión de sesión del usuario: la cookie la lleva y el middleware la
    compara en cada request. Sube al cambiar/resetear la contraseña o al
    'cerrar sesiones' desde /admin → todas las cookies anteriores dejan de
    autenticar (antes una cookie robada seguía válida 14 días aunque el usuario
    cambiara la clave). Cookies viejas sin `sv` cuentan como 0."""
    if not username:
        return 0
    u = _store()["users"].get(_norm(username))
    return int((u or {}).get("sv") or 0)


def bump_session_version(username: str) -> int:
    """Invalida todas las sesiones web del usuario (Excel NO: su token es aparte)."""
    name = _norm(username)

    def fn(d: Dict[str, Any]) -> int:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        u["sv"] = int(u.get("sv") or 0) + 1
        return u["sv"]

    return _mutar(fn)


def reset_with_token(token: str, password: str) -> str:
    """Reset por token de forma ATÓMICA (re-chequeo + cambio bajo el mismo
    lock): dos POST simultáneos con el mismo token hashean los dos en
    paralelo, pero el primero que entra al lock cambia la huella y el segundo
    ya ve el token usado. El hash corre fuera del lock (ver create_user).
    Devuelve el username."""
    if not password or len(password) < 6:
        raise AuthError("La contraseña debe tener al menos 6 caracteres.")
    user = check_reset_token(token)
    if not user:
        raise AuthError("El enlace no es válido, expiró o ya se usó.")
    name = _norm(user)
    role, email = _perfil_para_clave(name)
    rec = _make_record(password, role, email)

    def fn(d: Dict[str, Any]) -> None:
        # re-chequeo adentro de la mutación (bajo _lock, sobre la misma base
        # que la copia): el primero que publica cambia la huella y el segundo
        # ya ve el token usado — aunque los dos hayan hasheado en paralelo.
        if check_reset_token(token) != user:
            raise AuthError("El enlace no es válido, expiró o ya se usó.")
        _aplicar_clave(d, name, rec)

    _mutar(fn)
    return user


def update_user(username: str, role: Optional[str] = None, email: Optional[str] = None) -> None:
    name = _norm(username)

    def fn(d: Dict[str, Any]) -> None:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        if role is not None:
            if role not in ROLES:
                raise AuthError(f"Rol inválido: {role!r}.")
            # no dejar el sistema sin superuser
            if u.get("role") == "superuser" and role != "superuser" and _count_superusers(d) <= 1:
                raise AuthError("No podés degradar al último superuser.")
            u["role"] = role
        if email is not None:
            u["email"] = email.strip()

    _mutar(fn)


def delete_user(username: str) -> None:
    name = _norm(username)

    def fn(d: Dict[str, Any]) -> None:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        if u.get("role") == "superuser" and _count_superusers(d) <= 1:
            raise AuthError("No podés borrar al último superuser.")
        del d["users"][name]

    _mutar(fn)      # su token de Excel (si tenía) deja de valer ya (_excel_index se rearma)


def set_role_tabs(role: str, tabs: List[str]) -> None:
    if role not in ("premium", "basico"):
        raise AuthError("Sólo se configuran las pestañas de premium y básico "
                        "(el superuser ve todo).")
    clean = [t for t in tabs if t in TAB_KEYS]

    def fn(d: Dict[str, Any]) -> None:
        d["role_tabs"][role] = clean

    _mutar(fn)


# ── Features por rol ─────────────────────────────────────────────────────────
_feat_cache: Dict[str, frozenset] = {}


def role_features() -> Dict[str, List[str]]:
    return _store().get("role_features", {})


def features_for(role: Optional[str]) -> frozenset:
    """Features habilitadas para el rol (cacheado — el middleware lo pide en
    CADA request). Superuser → todas, siempre."""
    key = role or ""
    cached = _feat_cache.get(key)
    if cached is None:
        if role == "superuser":
            cached = frozenset(FEATURE_KEYS)
        else:
            cached = frozenset(k for k in role_features().get(key, []) if k in FEATURE_KEYS)
        _feat_cache[key] = cached
    return cached


def can_feature(role: Optional[str], key: str) -> bool:
    return key in features_for(role)


def set_role_features(role: str, keys: List[str]) -> None:
    if role not in ("premium", "basico"):
        raise AuthError("Sólo se configuran features de premium y básico "
                        "(el superuser las tiene todas).")
    clean = [k for k in keys if k in FEATURE_KEYS]

    def fn(d: Dict[str, Any]) -> None:
        d.setdefault("role_features", {})[role] = clean

    _mutar(fn)


def _count_superusers(data: Dict[str, Any]) -> int:
    return sum(1 for u in data["users"].values() if u.get("role") == "superuser")


# ── Visibilidad de FONDOS por usuario ────────────────────────────────────────
# Filtro fino ADENTRO de las pestañas con tenencias (Posiciones / Matriz / los
# desplegables de tenencia en YAS / Comparador / Curvas): el superuser elige
# POR USUARIO qué fondos ve. Campo `fondos` del record: ausente/None = TODOS
# (default de siempre, premium y básico); lista = allowlist de cod_fondo — un
# fondo NUEVO que aparezca en carteras NO se le muestra a un usuario
# restringido hasta que el superuser lo tilde (safe default: es tenencia real
# del desk). El superuser ve todo siempre. El filtro corre SERVER-SIDE en los
# providers de datos (services.positions), no escondiendo columnas en el HTML.

def visible_fondos(username: Optional[str]) -> Optional[FrozenSet[int]]:
    """None = ve todos los fondos; frozenset = sólo esos cod_fondo."""
    if not username:
        return None
    u = _store()["users"].get(_norm(username))
    if not u or u.get("role") == "superuser":
        return None
    cods = u.get("fondos")
    if cods is None:
        return None
    try:
        return frozenset(int(c) for c in cods)
    except (TypeError, ValueError):     # store editado a mano y roto → no filtrar
        return None


def visible_fondos_for(request: Any) -> Optional[FrozenSet[int]]:
    """Fondos visibles para el usuario del request (None = todos). Sin muro de
    login (dev) o superuser → sin filtro. Duck-typed sobre request.state para
    no importar FastAPI acá."""
    u = getattr(getattr(request, "state", None), "user", None)
    if not u or u.get("role") == "superuser":
        return None
    return visible_fondos(u.get("username"))


def set_visible_fondos(username: str, cods: Optional[List[int]]) -> None:
    """None = todos (borra la restricción); lista = allowlist de cod_fondo."""
    name = _norm(username)

    def fn(d: Dict[str, Any]) -> None:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        if u.get("role") == "superuser":
            raise AuthError("El superuser siempre ve todos los fondos.")
        if cods is None:
            u.pop("fondos", None)
        else:
            try:
                u["fondos"] = sorted({int(c) for c in cods})
            except (TypeError, ValueError):
                raise AuthError("Códigos de fondo inválidos.") from None

    _mutar(fn)


# ── Acceso Excel (add-in) por usuario ────────────────────────────────────────
# El add-in de Excel no navega el login wall (no tiene cookie de sesión): se
# autentica con un token POR USUARIO que sólo el superuser habilita/corta desde
# /admin. El hot path (1 req/s por libro abierto) es un dict en memoria
# token→username (O(1), sin I/O ni hashing); se reconstruye lazy tras cada
# mutación / refresh().
_excel_index: Optional[Dict[str, str]] = None


def _excel_index_live() -> Dict[str, str]:
    global _excel_index
    with _lock:
        if _excel_index is None:
            _excel_index = {
                u["excel_token"]: name
                for name, u in _store()["users"].items()
                if u.get("excel_enabled") and u.get("excel_token")
            }
        return _excel_index


def user_for_excel_token(token: Optional[str]) -> Optional[str]:
    """Username dueño del token, o None si es inválido o está deshabilitado.
    Deshabilitar/regenerar desde /admin invalida el token viejo al instante."""
    if not token:
        return None
    return _excel_index_live().get(str(token).strip())


def excel_info(username: str) -> Dict[str, Any]:
    u = _store()["users"].get(_norm(username)) or {}
    return {"enabled": bool(u.get("excel_enabled")), "token": u.get("excel_token") or None}


def set_excel_access(username: str, enabled: bool) -> Optional[str]:
    """Habilita/corta el acceso Excel de un usuario (panel del superuser). Al
    habilitar por primera vez genera el token; al deshabilitar lo CONSERVA
    (re-habilitar no obliga a reconfigurar los libros ya armados) pero deja de
    validar. Devuelve el token vigente si quedó habilitado."""
    name = _norm(username)
    nuevo_token = secrets.token_urlsafe(24)

    def fn(d: Dict[str, Any]) -> Optional[str]:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        u["excel_enabled"] = bool(enabled)
        if enabled and not u.get("excel_token"):
            u["excel_token"] = nuevo_token
        return u.get("excel_token") if enabled else None

    return _mutar(fn)       # _excel_index se rearma al publicar


def regen_excel_token(username: str) -> str:
    """Rota el token de Excel del usuario (el anterior deja de valer ya)."""
    name = _norm(username)
    nuevo_token = secrets.token_urlsafe(24)

    def fn(d: Dict[str, Any]) -> str:
        u = d["users"].get(name)
        if not u:
            raise AuthError(f"El usuario '{name}' no existe.")
        u["excel_token"] = nuevo_token
        return u["excel_token"]

    return _mutar(fn)


# ── Tokens de reset (firmados, con expiración, single-use) ───────────────────
def _pw_fingerprint(name: str) -> str:
    """Huella corta del hash+salt ACTUAL del usuario, firmada. Se incluye en el
    token de reset para que sea de un solo uso efectivo: apenas se cambia la
    contraseña, el hash muta y cualquier token viejo deja de validar (sin esto,
    el mismo link servía para resetear de nuevo durante toda la hora de TTL). No
    expone el hash — es un HMAC truncado."""
    u = _store()["users"].get(name)
    seed = (u or {}).get("hash", "") + "|" + (u or {}).get("salt", "")
    return hmac.new(get_secret_key().encode("utf-8"), seed.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def make_reset_token(username: str, ttl_seconds: int = 3600) -> str:
    import time
    name = _norm(username)
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{name}:{exp}:{_pw_fingerprint(name)}".encode("utf-8")
    sig = hmac.new(get_secret_key().encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + sig


def check_reset_token(token: str) -> Optional[str]:
    """Devuelve el username si el token es válido, no expiró y la contraseña no
    cambió desde que se emitió (single-use); si no, None."""
    import time
    try:
        b64, sig = (token or "").split(".", 1)
        pad = "=" * (-len(b64) % 4)
        payload = base64.urlsafe_b64decode(b64 + pad)
        expected = hmac.new(get_secret_key().encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        parts = payload.decode("utf-8").split(":")
        if len(parts) != 3:                          # tokens con formato viejo → inválidos
            return None
        name, exp, fp = parts
        if int(exp) < int(time.time()):
            return None
        if name not in _store()["users"]:
            return None
        if not hmac.compare_digest(fp, _pw_fingerprint(name)):
            return None                              # la contraseña cambió → token ya usado
        return name
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
