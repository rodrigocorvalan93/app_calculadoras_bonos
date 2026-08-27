"""Escenario — defaults de senderos + preferencias persistidas.

Defaults (lo que ve el usuario al abrir la pestaña, todo desde memoria,
costo ~µs):
  - Inflación: la proyección mensual de la economista cargada a mano en
    `indices.proyeccion_inflacion_mensual` (%/mes), alineada al mes del DATO
    que rige el CER en cada tramo (lag del índice; ver _slot_ipc_ref).
  - Deva A3500: mes a mes implícita en los futuros ROFEX del store —
    ln(1+deva) lineal en días entre contratos con precio (interpola meses
    faltantes y extrapola con la última pendiente). Sin futuros con precio,
    cae a la deva mensual implícita del A3500 proyectado (flat).
  - Deva CCL y MEP: MISMO sendero que el oficial (brecha y canje
    constantes).
  - TAMAR: nivel TNA actual proyectado flat.

Persistencia (data/escenario_prefs.json, fuera de git): el usuario edita
una fila → esa fila queda FIJA (sobrevive reinicios y se comparte entre
PC/Mac/celu); las filas no tocadas siguen siendo defaults VIVOS (el ROFEX
de mañana, la TAMAR de mañana). "Restablecer defaults" borra lo guardado.
También persiste qué categorías están destildadas del comparativo.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.escenario_prefs")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = REPO_ROOT / "data" / "escenario_prefs.json"
_lock = threading.Lock()

SENDERO_KEYS = ("infl_path", "a3500_path", "ccl_path", "mep_path", "tamar_path")


def _path() -> Path:
    return Path(os.getenv("ESCENARIO_PREFS_PATH") or _DEFAULT_PATH)


# ── persistencia ────────────────────────────────────────────────────────────
_MAX_PRESETS = 20


def _sane_senderos(raw: Any) -> Dict[str, str]:
    return {k: v for k, v in (raw or {}).items()
            if k in SENDERO_KEYS and isinstance(v, str)}


def _sane_cats(raw: Any) -> List[str]:
    return [c for c in (raw or []) if isinstance(c, str)]


# Multi-usuario (v2): el estado ACTIVO (senderos fijos + tildes) es POR
# USUARIO — con el equipo compartiendo el server, el escenario de uno no
# pisa el de otro. Los PRESETS nombrados quedan COMPARTIDOS a propósito:
# son la biblioteca del equipo ("base", "estrés deva"), no estado personal.
# El formato viejo (un solo estado global) migra solo: pasa a
# users["_migrado"] y sirve de fallback para quien todavía no guardó nada
# propio — nadie pierde sus senderos fijados al actualizar.
_MIGRADO = "_migrado"


def _sane_user_entry(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {"senderos": _sane_senderos(raw.get("senderos")),
            "cats_off": _sane_cats(raw.get("cats_off"))}


def _load_all() -> Dict[str, Any]:
    """Estructura v2 completa: {"v": 2, "users": {u: {senderos, cats_off}},
    "presets": {...}} — migrando el formato viejo si hace falta."""
    p = _path()
    if not p.is_file():
        return {"v": 2, "users": {}, "presets": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"v": 2, "users": {}, "presets": {}}
    except (OSError, ValueError):
        logger.exception("[escenario_prefs] archivo ilegible; arranco de defaults")
        return {"v": 2, "users": {}, "presets": {}}
    presets = {}
    for name, pr in (data.get("presets") or {}).items():
        if isinstance(name, str) and isinstance(pr, dict):
            presets[name[:40]] = {"senderos": _sane_senderos(pr.get("senderos")),
                                  "cats_off": _sane_cats(pr.get("cats_off"))}
    if data.get("v") == 2:
        users = {u: _sane_user_entry(e) for u, e in (data.get("users") or {}).items()
                 if isinstance(u, str)}
        return {"v": 2, "users": users, "presets": presets}
    # formato viejo (estado global único) → migra a users["_migrado"]
    old = _sane_user_entry(data)
    users = {_MIGRADO: old} if (old["senderos"] or old["cats_off"]) else {}
    return {"v": 2, "users": users, "presets": presets}


def _write(cur: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def load_user(user: str) -> Dict[str, Any]:
    """Estado del usuario (mismo shape que el load() histórico):
    {"senderos": {...}, "cats_off": [...], "presets": {...}} — presets
    compartidos. Sin estado propio cae al migrado del formato viejo."""
    all_ = _load_all()
    ent = all_["users"].get(user) or all_["users"].get(_MIGRADO) or {}
    out: Dict[str, Any] = {"senderos": dict(ent.get("senderos") or {}),
                           "cats_off": list(ent.get("cats_off") or [])}
    if all_["presets"]:
        out["presets"] = all_["presets"]
    return out


def save(senderos: Optional[Dict[str, str]] = None,
         cats_off: Optional[List[str]] = None, user: str = "_local") -> Dict[str, Any]:
    """Persiste (atómico) el estado ACTIVO del usuario. `senderos` REEMPLAZA el
    set guardado (el cliente manda sólo las filas tocadas); `cats_off`
    reemplaza la lista. None = no tocar esa parte. Presets intactos."""
    with _lock:
        all_ = _load_all()
        ent = _sane_user_entry(all_["users"].get(user) or all_["users"].get(_MIGRADO))
        if senderos is not None:
            ent["senderos"] = {k: str(v) for k, v in senderos.items() if k in SENDERO_KEYS}
        if cats_off is not None:
            ent["cats_off"] = [str(c) for c in cats_off]
        all_["users"][user] = ent
        _write(all_)
        return load_user(user)


def reset(user: str = "_local") -> None:
    """Borra lo ACTIVO del usuario → defaults vivos. Los presets nombrados
    sobreviven (biblioteca compartida), y el estado de los DEMÁS también."""
    with _lock:
        all_ = _load_all()
        all_["users"].pop(user, None)
        # el fallback migrado ya no aplica para quien pidió reset explícito
        if user != _MIGRADO and _MIGRADO in all_["users"]:
            all_["users"][user] = {"senderos": {}, "cats_off": []}
        _write(all_)


# ── presets nombrados ("base", "estrés deva", …) — COMPARTIDOS ─────────────
def preset_save(name: str, user: str = "_local") -> bool:
    """Fotografía el estado ACTIVO del usuario bajo `name` (visible a todos)."""
    name = (name or "").strip()[:40]
    if not name:
        return False
    with _lock:
        all_ = _load_all()
        presets = all_["presets"]
        if name not in presets and len(presets) >= _MAX_PRESETS:
            return False
        ent = load_user(user)
        presets[name] = {"senderos": dict(ent.get("senderos") or {}),
                         "cats_off": list(ent.get("cats_off") or [])}
        _write(all_)
        return True


def preset_apply(name: str, user: str = "_local") -> bool:
    """Carga un preset compartido como estado activo DEL USUARIO."""
    with _lock:
        all_ = _load_all()
        pr = all_["presets"].get((name or "").strip()[:40])
        if pr is None:
            return False
        all_["users"][user] = {"senderos": dict(pr.get("senderos") or {}),
                               "cats_off": list(pr.get("cats_off") or [])}
        _write(all_)
        return True


def preset_delete(name: str) -> bool:
    with _lock:
        all_ = _load_all()
        key = (name or "").strip()[:40]
        if key not in all_["presets"]:
            return False
        del all_["presets"][key]
        _write(all_)
        return True


def preset_names() -> List[str]:
    return sorted(_load_all()["presets"].keys())


# ── defaults ────────────────────────────────────────────────────────────────
def _fmt(v: float, dec: int = 2) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def _month_add(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


_MESES_AR = ("ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic")


def _slot_mid(settle_d: date, k: int) -> date:
    """Punto medio de la ventana del slot k (0-based): el slot compone sobre
    settle+k·30,44d → settle+(k+1)·30,44d (ver total_return.compound_path)."""
    return settle_d + timedelta(days=round((k + 0.5) * 30.4375))


def _slot_ipc_ref(settle_d: date, k: int) -> date:
    """Mes del DATO de IPC (INDEC) que rige el CER en la ventana del slot k.

    Mecánica del índice: el CER de mediados de M a mediados de M+1 corre con
    el IPC de M−1 (publicado a mediados de M). Evaluado en el punto medio de
    la ventana: antes del día 16 ⇒ IPC de 2 meses atrás; después ⇒ 1 mes."""
    mid = _slot_mid(settle_d, k)
    return _month_add(date(mid.year, mid.month, 1), -(2 if mid.day < 16 else 1))


def slot_meses(settle_d: date, n: int) -> List[Dict[str, str]]:
    """Etiquetas de los slots del grid de senderos, por slot:
      mes   → mes calendario que el tramo impacta (punto medio de su ventana;
              con ’AA cuando cruza de año) — vale para devas y TAMAR (sin lag).
      ipc   → mes del dato de INDEC que va en ese casillero de Inflación
              (regla del lag del CER, ver _slot_ipc_ref).
      rango → fechas exactas del tramo (tooltip).
    """
    def _lbl(d: date) -> str:
        m = _MESES_AR[d.month - 1]
        return m if d.year == settle_d.year else f"{m} ’{d.year % 100:02d}"

    out: List[Dict[str, str]] = []
    for k in range(max(0, int(n))):
        mid = _slot_mid(settle_d, k)
        d0 = settle_d + timedelta(days=round(k * 30.4375))
        d1 = settle_d + timedelta(days=round((k + 1) * 30.4375))
        out.append({"mes": _lbl(mid), "ipc": _lbl(_slot_ipc_ref(settle_d, k)),
                    "rango": f"{d0.day:02d}/{d0.month:02d} → {d1.day:02d}/{d1.month:02d}"})
    return out


def infl_default(settle_d: date, n_months: int) -> str:
    """Sendero de inflación desde `indices.proyeccion_inflacion_mensual`
    (la proyección manual de la economista, %/mes), alineado al MES DEL DATO
    que rige el CER en cada slot (mismo mes que la fila Inflación muestra como
    'IPC <mes>'; regla del lag en _slot_ipc_ref). Meses sin proyección: hacia
    atrás usa la primera conocida, hacia adelante extiende la última."""
    try:
        import indices
        proy = {datetime.strptime(k, "%b-%y").date().replace(day=1): float(v)
                for k, v in indices.proyeccion_inflacion_mensual.items()}
    except Exception:  # noqa: BLE001
        logger.exception("[escenario_prefs] proyección de inflación no disponible")
        return ""
    if not proy:
        return ""
    out: List[str] = []
    last = None
    for i in range(n_months):
        v = proy.get(_slot_ipc_ref(settle_d, i))
        if v is None:
            v = last if last is not None else proy[min(proy)]
        last = v
        out.append(_fmt(v))
    return ";".join(out)


def rofex_monthly_deva(settle_d: date, n_months: int) -> Optional[List[float]]:
    """Deva oficial mes a mes implícita en los futuros DLR (fracciones).
    ln(1+deva acumulada) lineal en días entre contratos CON precio →
    interpola meses sin dato y extrapola con la pendiente del último tramo.
    None si no hay ni un futuro con precio (feed frío)."""
    from backend.services import futuros

    pts: List[tuple] = []
    for r in futuros.rows("may"):
        if r.get("dias") and r["dias"] > 0 and r.get("td") is not None and r["td"] > -1.0:
            pts.append((float(r["dias"]), math.log1p(float(r["td"]))))
    if not pts:
        return None
    pts.sort()
    xs = [(0.0, 0.0)] + pts

    def _cum(d: float) -> float:                     # ln(1+deva acumulada) a d días
        for (d0, l0), (d1, l1) in zip(xs, xs[1:]):
            if d <= d1:
                w = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
                return l0 + w * (l1 - l0)
        (d0, l0), (d1, l1) = xs[-2] if len(xs) > 1 else xs[0], xs[-1]
        slope = (l1 - l0) / (d1 - d0) if d1 > d0 else 0.0
        return l1 + (d - d1) * slope

    out: List[float] = []
    prev = 0.0
    for m in range(1, n_months + 1):
        cur = _cum(m * 30.4375)
        out.append(math.expm1(cur - prev))           # (1+D_m)/(1+D_{m-1}) − 1
        prev = cur
    return out


def defaults(settle_d: date, n_months: int,
             tamar_now: Optional[float], deva_mens_flat: float) -> Dict[str, str]:
    """Los 5 senderos default como strings es-AR 'v1;v2;…' (el formato que
    viaja en el form). Todo lectura de memoria — apto para el render de la
    página sin costo."""
    deva = rofex_monthly_deva(settle_d, n_months)
    if deva is None:                                  # sin futuros: flat implícita
        deva = [deva_mens_flat] * n_months
    deva_str = ";".join(_fmt(v * 100.0) for v in deva)
    return {
        "infl_path": infl_default(settle_d, n_months),
        "a3500_path": deva_str,
        "ccl_path": deva_str,                         # brecha constante
        "mep_path": deva_str,                         # canje constante
        "tamar_path": ";".join([_fmt(tamar_now)] * n_months) if tamar_now is not None else "",
    }
