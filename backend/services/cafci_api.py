"""API privada de CAFCI (cloud.cafci.org.ar) — poller + cache en memoria.

Fase B0 (sólo superuser en la UI): VCP diario de los fondos propios desde
`/reports/daily` (shape confirmado por el legacy cafciapi.py: registros con
nombreDeLaClaseDeFondo / fecha / vcp ×1000 / moneda). Gated por CAFCI_TOKEN
en secrets.txt (formato `Bearer eyJ...`); sin token todo queda deshabilitado
y la pestaña CAFCI sigue exactamente igual (Excel del bot).

Patrón calcado de `mae.py`: el poller corre en background (dato diario →
cada 30 min alcanza), escribe un snapshot bajo lock, y el request path SOLO
lee memoria (~µs) — el presupuesto de <50 ms p95 ni se entera.

Fase B1 (pendiente del probe scripts/cafci_probe.py): si
`/vectores/cafci_closing_prices` trae los campos del Excel (tir/duration/
spreads), este módulo pasa a alimentar también el vector con fallback al
Excel. `_normalize_precio` queda preparada con los alias a completar.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("backend.cafci_api")

_API_BASE = "https://cloud.cafci.org.ar/api"
_TIMEOUT = 10
_POLL_SEC = 1800.0                    # VCP es dato diario: 30 min de sobra

# Fondos a mostrar en el panel (env CAFCI_FONDOS separada por ';' pisa esto).
_DEFAULT_FONDOS = [
    "Fima Renta Fija Dólares - Clase C", "Fima Premium Dólares - Clase A",
    "Delta Ahorro Plus - Clase A", "Delta Acciones - Clase A",
    "Delta Gestion VI - Clase A", "Delta Retorno Real - Clase A",
    "Delta Latinoamerica - Clase A", "Delta Renta - Clase A",
    "Delta Renta Dolares - Clase D",
]

_lock = threading.Lock()
_snap: Dict[str, Any] = {
    "funds": [], "funds_fecha": None,          # VCP fondos propios (daily)
    "rows": [], "fecha": None, "n": 0,         # vector (B1, post-probe)
    "ts": 0.0, "error": None, "auth_error": False,
}


def enabled() -> bool:
    return bool(os.getenv("CAFCI_TOKEN"))


def _auth() -> Dict[str, str]:
    t = os.getenv("CAFCI_TOKEN") or ""
    return {"Authorization": t if t.startswith("Bearer ") else "Bearer " + t}


def _num(v: Any) -> Optional[float]:
    """Número tolerante: float directo o string es-AR/plana."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    from backend.locale_ar import parse_ar_num
    return parse_ar_num(str(v))


def _get(path: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
    """Un GET (sync, sólo poller/refresh — NUNCA el request path)."""
    import requests
    try:
        r = requests.get(f"{_API_BASE}/{path}", params=params or {},
                         headers=_auth(), timeout=_TIMEOUT)
    except requests.RequestException as exc:
        with _lock:
            _snap["error"] = f"CAFCI API inaccesible: {exc}"
        logger.warning("[cafci_api] %s falló: %s", path, exc)
        return None
    if r.status_code in (401, 403):
        with _lock:
            _snap["auth_error"] = True
            _snap["error"] = "Token CAFCI vencido o inválido — renovalo en secrets.txt (CAFCI_TOKEN=Bearer …)."
        logger.warning("[cafci_api] auth %s en %s (¿token vencido?)", r.status_code, path)
        return None
    if r.status_code != 200:
        with _lock:
            _snap["error"] = f"CAFCI API HTTP {r.status_code} en {path}"
        logger.warning("[cafci_api] HTTP %s en %s", r.status_code, path)
        return None
    try:
        return r.json()
    except ValueError:
        with _lock:
            _snap["error"] = f"CAFCI API devolvió no-JSON en {path}"
        return None


def _fund_names() -> List[str]:
    env = (os.getenv("CAFCI_FONDOS") or "").strip()
    if env:
        return [f.strip() for f in env.split(";") if f.strip()]
    return list(_DEFAULT_FONDOS)


def _fecha_ddmm(iso: Any) -> Optional[str]:
    s = str(iso or "")
    if len(s) >= 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s or None


def _prev_habil(d, n: int = 1):
    from datetime import timedelta
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _rows_de(payload) -> List[Dict[str, Any]]:
    """Ubica la lista de precios en la respuesta (defensivo: `records.precios`
    confirmado por el legacy, con fallbacks por si el shape difiere)."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    rec = payload.get("records", payload)
    if isinstance(rec, list):
        return [r for r in rec if isinstance(r, dict)]
    if isinstance(rec, dict):
        pre = rec.get("precios")
        if isinstance(pre, list):
            return [r for r in pre if isinstance(r, dict)]
        for v in rec.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def _rows_usable(rows: List[Dict[str, Any]]) -> bool:
    """La API sólo TOMA EL MANDO del vector si sus filas están a la altura del
    Excel: volumen razonable, mayoría con precio y una fracción con TIR (el
    valor de la pestaña son las analíticas). Si trae menos —p. ej. sólo
    precios— el Excel sigue primario y la pestaña no pierde nada."""
    if len(rows) < 100:
        return False
    muestra = rows[:500]
    con_cdo = sum(1 for r in muestra if r.get("cdo") is not None)
    con_tir = sum(1 for r in muestra if r.get("tir") is not None)
    return con_cdo >= 0.5 * len(muestra) and con_tir >= 0.2 * len(muestra)


def _refresh_vector() -> None:
    """Vector de cierre por activo (closing_prices): prueba hoy y hasta 5
    hábiles atrás; guarda el primer día con filas usables. Si la API no trae
    campos a la altura del Excel, deja el vector vacío → el arbitraje en
    cafci.py sigue con el Excel (nunca degrada la pestaña)."""
    from datetime import date as _date
    d = _date.today()
    for intento in range(6):                     # hoy + 5 hábiles atrás
        payload = _get("vectores/cafci_closing_prices", {"date": d.isoformat()})
        crudas = _rows_de(payload) if payload is not None else []
        rows = [n for r in crudas if (n := _normalize_precio(r)) is not None]
        if rows and _rows_usable(rows):
            with _lock:
                _snap["rows"] = rows
                _snap["fecha"] = d.strftime("%Y%m%d")   # el strip slicea AAAAMMDD
                _snap["n"] = len(rows)
            logger.info("[cafci_api] vector por API: %d filas (fecha %s)", len(rows), d)
            return
        if crudas and rows and not _rows_usable(rows):
            logger.info("[cafci_api] vector API con campos insuficientes "
                        "(%d filas, pocas con cdo/tir) — sigue el Excel", len(rows))
            return                                # hay data pero no alcanza: no insistir
        d = _prev_habil(d)
    logger.info("[cafci_api] closing_prices sin filas usables en 6 fechas — sigue el Excel")


def refresh() -> bool:
    """Relee daily + vector de CAFCI (sync, blocking — sólo poller/botón)."""
    if not enabled():
        return False
    try:
        _refresh_vector()
    except Exception:  # noqa: BLE001 — el vector nunca voltea el daily
        logger.exception("[cafci_api] refresh del vector falló")
    data = _get("reports/daily")
    records = (data or {}).get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return False
    quiero = _fund_names()
    by_name = {str(r.get("nombreDeLaClaseDeFondo") or ""): r
               for r in records if isinstance(r, dict)}
    funds: List[Dict[str, Any]] = []
    fecha = None
    for nombre in quiero:                        # respeta el orden configurado
        r = by_name.get(nombre)
        if r is None:
            continue
        vcp = _num(r.get("vcp"))
        funds.append({
            "nombre": nombre,
            "vcp": (vcp / 1000.0) if vcp is not None else None,   # viene ×1000
            "moneda": str(r.get("moneda") or ""),
            "fecha": _fecha_ddmm(r.get("fecha")),
        })
        fecha = fecha or _fecha_ddmm(r.get("fecha"))
    with _lock:
        _snap["funds"] = funds
        _snap["funds_fecha"] = fecha
        _snap["ts"] = time.time()
        if funds:
            _snap["error"] = None
            _snap["auth_error"] = False
    logger.info("[cafci_api] snapshot: %d/%d fondos con VCP (fecha %s)",
                len(funds), len(quiero), fecha)
    return bool(funds)


def funds() -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """(fondos, fecha, error) — lectura de cache, ~µs."""
    with _lock:
        return list(_snap["funds"]), _snap["funds_fecha"], _snap["error"]


def vector_snapshot() -> Dict[str, Any]:
    """Vector por API para el arbitraje de cafci.py — lectura de cache, ~µs."""
    with _lock:
        return {"rows": _snap["rows"], "fecha": _snap["fecha"], "n": _snap["n"]}


def status() -> Dict[str, Any]:
    with _lock:
        return {"enabled": enabled(), "n_funds": len(_snap["funds"]),
                "funds_fecha": _snap["funds_fecha"], "ts": _snap["ts"],
                "error": _snap["error"], "auth_error": _snap["auth_error"]}


# ── Fase B1 (post-probe): normalización del vector de closing_prices ───────
def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


# output_key → keys candidatas normalizadas. Sólo 'codigo' está CONFIRMADO
# (cafciapi.py); el resto se completa con el reporte de scripts/cafci_probe.py.
_ALIASES: Dict[str, Tuple[str, ...]] = {
    "cafci": ("codigo", "codigocafci"),
    "isin": ("isin",),
    "byma": ("byma", "ticker", "especie", "simbolo"),
    "moneda": ("moneda", "valuacion", "currency"),
    "cdo": ("cdo", "precio", "preciocierre", "cierre", "px", "contado"),
    "var_cdo": ("variacion", "varcdo", "var"),
    "mod_dur": ("modduration", "duration", "md", "duracion"),
    "tir": ("tir", "irr",),
    "tna": ("tna",),
    "spread": ("spread",),
    "zspread": ("zspread", "zsprd"),
}
_TEXT_KEYS = ("cafci", "isin", "byma", "moneda")


def _normalize_precio(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Record de closing_prices → fila con el shape del Excel del vector
    (cafci.py). None si no trae ningún identificador. Defensiva: campos sin
    match quedan en None (el template ya banca None)."""
    normed = {_norm_key(k): v for k, v in rec.items()}

    def _pick(out_key: str) -> Any:
        for a in _ALIASES.get(out_key, ()):
            if a in normed and normed[a] not in (None, ""):
                return normed[a]
        return None

    row: Dict[str, Any] = {}
    for k in _ALIASES:
        v = _pick(k)
        row[k] = (str(v).strip() if v is not None else "") if k in _TEXT_KEYS else _num(v)
    if not (row["cafci"] or row["isin"] or row["byma"]):
        return None
    row["_key"] = " ".join(str(row[k]).lower() for k in ("isin", "byma", "cafci") if row[k])
    return row


# ── Poller (background, sólo con CAFCI_TOKEN) ───────────────────────────────
class _Poller:
    def __init__(self, interval: float = _POLL_SEC) -> None:
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(refresh)
            except Exception:  # noqa: BLE001
                logger.exception("[cafci_api] poller error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if not enabled():
            logger.info("[cafci_api] CAFCI_TOKEN ausente; panel VCP deshabilitado (la pestaña usa el Excel)")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("[cafci_api] poller iniciado (cada %ss)", self.interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


_poller: Optional[_Poller] = None


def get_poller() -> _Poller:
    global _poller
    if _poller is None:
        _poller = _Poller()
    return _poller
