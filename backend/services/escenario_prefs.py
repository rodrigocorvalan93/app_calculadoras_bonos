"""Escenario — defaults de senderos + preferencias persistidas.

Defaults (lo que ve el usuario al abrir la pestaña, todo desde memoria,
costo ~µs):
  - Inflación: la proyección mensual de la economista cargada a mano en
    `indices.proyeccion_inflacion_mensual` (%/mes), alineada al mes del
    settle.
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
from datetime import date, datetime
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
def load() -> Dict[str, Any]:
    """{"senderos": {key: "v1;v2;…"}, "cats_off": [keys]} — {} si no hay nada."""
    p = _path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        senderos = {k: v for k, v in (data.get("senderos") or {}).items()
                    if k in SENDERO_KEYS and isinstance(v, str)}
        cats_off = [c for c in (data.get("cats_off") or []) if isinstance(c, str)]
        return {"senderos": senderos, "cats_off": cats_off}
    except (OSError, ValueError):
        logger.exception("[escenario_prefs] archivo ilegible; arranco de defaults")
        return {}


def save(senderos: Optional[Dict[str, str]] = None,
         cats_off: Optional[List[str]] = None) -> Dict[str, Any]:
    """Persiste (atómico). `senderos` REEMPLAZA el set guardado (el cliente
    manda sólo las filas tocadas); `cats_off` reemplaza la lista. None = no
    tocar esa parte."""
    with _lock:
        cur = load()
        if senderos is not None:
            cur["senderos"] = {k: str(v) for k, v in senderos.items() if k in SENDERO_KEYS}
        if cats_off is not None:
            cur["cats_off"] = [str(c) for c in cats_off]
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return cur


def reset() -> None:
    """Borra lo guardado → la pestaña vuelve a los defaults vivos."""
    with _lock:
        try:
            _path().unlink(missing_ok=True)
        except OSError:
            logger.exception("[escenario_prefs] no pude borrar el archivo de prefs")


# ── defaults ────────────────────────────────────────────────────────────────
def _fmt(v: float, dec: int = 2) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def _month_add(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def infl_default(settle_d: date, n_months: int) -> str:
    """Sendero de inflación desde `indices.proyeccion_inflacion_mensual`
    (la proyección manual de la economista, %/mes), alineado al mes del
    settle. Meses sin proyección: se extiende el último valor conocido."""
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
        v = proy.get(_month_add(settle_d, i))
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
