"""Posiciones / tenencias Delta — carga ÚNICA y cacheada.

Lee los Excel de carteras una sola vez y los cachea en memoria; releer es
explícito (`refresh()`), por lo que las rutas sirven SIN I/O de Excel por
request (prioridad: velocidad). Failure-silent: si faltan los archivos,
devuelve estructura vacía con `error` para que la UI lo muestre.

Archivos (paths desde env, que OMSsecrets carga del secrets.txt):
  - Delta_Composicion.xlsx    (DELTA_COMPOSICION_PATH | DELTA_BASES_DIR)
  - Delta_PN.xlsx             (DELTA_PN_PATH          | DELTA_BASES_DIR)
  - Delta_Fondos.txt          (DELTA_FONDOS_PATH)  → CodFondo → Nombre (opcional)

Esquema Delta (igual que OMSposiciones.py legacy):
  Composición: CodFondo, Cod_Delta, Cantidad, Valor, (Clase de Activo, Vto…)
  PN:          CodFondo, PN
  %PN = Valor / PN.  Cod_Delta (upper/strip) matchea el ticker del universo.

Galileo (17/11): los fondos Galileo viven en Delta_Composicion.xlsx / Delta_PN.xlsx
como fondos Delta comunes. Los viejos Galileo_Composicion.xlsx / Galileo_PN.xlsx
NO se leen (duplicaban fondos con las tenencias del último día en que se
bajaban); si el archivo sigue en la carpeta, la carga lo avisa una vez
(`status()["galileo_viejo"]`) y nada más.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from backend.services import deltapaths

logger = logging.getLogger("backend.positions")

_COMPOSICION_FILE = "Delta_Composicion.xlsx"
_PN_FILE = "Delta_PN.xlsx"

# Archivo viejo de la familia Galileo: ya no se lee, sólo se avisa si sigue ahí.
_GALILEO_VIEJO_FILE = "Galileo_Composicion.xlsx"

# Fallback CodFondo → Nombre (de OMSposiciones). Se usa si Delta_Fondos.txt
# no está disponible / no parsea, así nunca se muestran sólo números.
_FONDO_NOMBRES_FALLBACK: Dict[int, str] = {
    1: "Acciones", 2: "Ahorro", 13: "Ahorro Plus", 39: "Cohen Pesos",
    18: "Crecimiento", 37: "CRF DOL", 14: "FEDERAL I", 15: "Gestion I",
    16: "Gestion II", 19: "Gestion III", 9: "Gestion IV", 28: "Gestion IX",
    41: "Gestion Pyme", 21: "Gestion V", 23: "Gestión VI", 24: "Gestion VII",
    25: "Gestion VIII", 34: "Gestion X", 40: "Gestion XI", 8: "Internacional",
    3: "Latinoamerica", 7: "Moneda", 12: "Multimercado I", 35: "MULTIMERCADO II",
    27: "Patrimonio I", 20: "Performance", 5: "Pesos", 36: "PLUS", 11: "Pyme",
    38: "PYMES", 6: "Recursos", 4: "Renta", 22: "Renta Dolares",
    26: "DOLARES PLUS", 10: "Select", 42: "Gestion XIII",
}

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_generation = 0          # avanza en cada (re)carga — clave de caches derivados


def generation() -> int:
    """Token de versión de las carteras: cambia sólo cuando se (re)leyeron los
    Excel. Los renders derivados (matriz) se cachean contra esto."""
    ensure_loaded()
    return _generation


# ── paths ────────────────────────────────────────────────────────────────
def _resolve(filename: str, env_override: str) -> Optional[str]:
    p = deltapaths.expand(os.getenv(env_override), want="file")
    if p and os.path.isfile(p):
        return p
    base = deltapaths.expand(os.getenv("DELTA_BASES_DIR"), want="dir")
    if base:
        cand = os.path.join(base, filename)
        if os.path.isfile(cand):
            return cand
    return None


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None  # descarta NaN
    except (TypeError, ValueError):
        return None


_PLAZO_SUFFIX = re.compile(r"\s+(CI|24HS|24|48HS|48|T\+?[012])$")
# Ticker estilo Bloomberg del sistema de carteras: 'LOMA AR' / 'GGAL AR EQUITY'.
# BYMA usa el ticker pelado ('LOMA'), así que el sufijo de país se descarta.
_BBG_SUFFIX = re.compile(r"\s+AR(\s+EQUITY)?$")


def _strip_plazo(s: str) -> str:
    """'S31L6 CI' / 'S31L6 24HS' → 'S31L6': mismo bono, distinto plazo de
    liquidación (un fondo opera normal, otro CI). Para posición / comparador /
    clasificaciones es el mismo papel, así que se ignora el sufijo de plazo.
    También 'LOMA AR' (Bloomberg) → 'LOMA' (ticker BYMA): sin esto las
    acciones de la cartera no matcheaban el store y quedaban sin Last."""
    s = _PLAZO_SUFFIX.sub("", s).strip()
    return _BBG_SUFFIX.sub("", s).strip()


def _norm_code(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().upper()
    if s in ("NC", "NAN", "NONE", ""):
        return None
    return _strip_plazo(s) or None


# ── fondos (CodFondo → Nombre), parser tolerante ──────────────────────────
def _parse_fondos(path: str) -> Dict[int, str]:
    raw: Optional[str] = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, OSError):
            continue
    if not raw:
        return {}
    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return {}
    delim = max(["\t", "|", ";", ","], key=lambda d: sum(1 for ln in lines[:10] if d in ln))
    if any(delim in ln for ln in lines[:10]):
        rows = [[c.strip() for c in ln.split(delim)] for ln in lines]
    else:
        rows = [re.split(r"\s{2,}|\t+", ln.strip()) for ln in lines]
    if not rows or len(rows[0]) < 2:
        return {}
    header = [c.strip().lower() for c in rows[0]]
    is_header = any(t in h for h in header for t in ("cod", "id", "num")) and \
        any(t in h for h in header for t in ("nombre", "denomi", "descri", "fondo"))

    col_code, col_name = 0, 1
    if is_header:
        # columna de código
        for i, h in enumerate(header):
            if any(t in h for t in ("codfondo", "cod_fondo", "cod fondo")) or h in ("cod", "id"):
                col_code = i
                break
        # columna de nombre por prioridad (token específico primero; 'corto'
        # genérico al final para que 'NombreCorto' gane sobre una col 'Corto').
        col_name = -1
        for token in ("nombrecorto", "nombre corto", "denomi", "nombre", "descri", "corto"):
            for i, h in enumerate(header):
                if i != col_code and token in h:
                    col_name = i
                    break
            if col_name >= 0:
                break
        if col_name < 0:
            col_name = 1 if col_code != 1 else (2 if len(header) > 2 else 1)
        data_rows = rows[1:]
    else:
        data_rows = rows

    out: Dict[int, str] = {}
    for r in data_rows:
        if len(r) <= max(col_code, col_name):
            continue
        try:
            cod = int(float(str(r[col_code]).strip().strip('"').strip("'")))
        except (TypeError, ValueError):
            continue
        name = str(r[col_name]).strip().strip('"').strip("'")
        if name:
            out[cod] = name
    return out


def _find_ci(dirpath: str, fname: str) -> Optional[str]:
    """Busca un archivo en dirpath case-insensitive (robusto en Linux)."""
    if not dirpath or not os.path.isdir(dirpath):
        return None
    target = fname.lower()
    try:
        for f in os.listdir(dirpath):
            if f.lower() == target:
                return os.path.join(dirpath, f)
    except OSError:
        return None
    return None


def _fondos_path() -> Optional[str]:
    """Resuelve Delta_Fondos.txt. Prioridad: DELTA_FONDOS_PATH, luego bajo
    DELTA_HISTORICO_DIR y DELTA_BASES_DIR (en Text/Esco/, ../Text/Esco/, raíz),
    case-insensitive (el archivo suele ser 'Delta_fondos.txt')."""
    env = os.getenv("DELTA_FONDOS_PATH")
    if env:
        env = deltapaths.expand(env, want="file")
        if os.path.isfile(env):
            return env
    for base_env in ("DELTA_HISTORICO_DIR", "DELTA_BASES_DIR"):
        base = os.getenv(base_env)
        if not base:
            continue
        base = deltapaths.expand(base, want="dir").rstrip("\\/")
        parent = os.path.dirname(base)
        for d in (os.path.join(base, "Text", "Esco"), base,
                  os.path.join(parent, "Text", "Esco"), parent):
            hit = _find_ci(d, "Delta_Fondos.txt")
            if hit:
                return hit
    return None


def _fondo_names() -> Dict[int, str]:
    path = _fondos_path()
    if path:
        try:
            parsed = _parse_fondos(path)
            if parsed:
                return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning("[positions] fondos parse failed: %s", exc)
    return dict(_FONDO_NOMBRES_FALLBACK)


_MONEDAS_FONDO = {"ARS": "ARS", "$": "ARS", "PESOS": "ARS", "USD": "USD", "USB": "USB"}


def _parse_fondos_moneda(path: str) -> Dict[int, str]:
    """CodFondo → moneda de la contabilidad del fondo (ARS / USD / USB) desde
    la columna `Moneda` de Delta_Fondos.txt (CSV de ESCO con cabecera
    `CodFondo,NumFondo,…,Moneda`). Sin esa columna, {} (el parser de nombres
    es tolerante a archivos sin cabecera; acá no se adivina)."""
    raw: Optional[str] = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, OSError):
            continue
    lines = [ln for ln in (raw or "").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(lines) < 2:
        return {}
    delim = max(["\t", "|", ";", ","], key=lambda d: lines[0].count(d))
    header = [c.strip().strip('"').lower() for c in lines[0].split(delim)]
    if "moneda" not in header:
        return {}
    col_m = header.index("moneda")
    col_c = next((i for i, h in enumerate(header) if h in ("codfondo", "cod_fondo", "cod fondo")), 0)
    out: Dict[int, str] = {}
    for ln in lines[1:]:
        r = [c.strip().strip('"') for c in ln.split(delim)]
        if len(r) <= max(col_c, col_m):
            continue
        try:
            cod = int(float(r[col_c]))
        except (TypeError, ValueError):
            continue
        m = _MONEDAS_FONDO.get(r[col_m].upper())
        if m:
            out[cod] = m
    return out


def _fondo_monedas() -> Dict[int, str]:
    path = _fondos_path()
    if not path:
        return {}
    try:
        return _parse_fondos_moneda(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[positions] monedas de los fondos: %s", exc)
        return {}


# Celdas "sin dato" del pipeline de carteras (no son un ISIN / ticker / moneda).
_SIN_DATO = frozenset({"", "NC", "NAN", "NONE", "NCP", "SIN_DATOS", "-"})


def _celda(v: Any) -> Optional[str]:
    """Texto de una celda de la composición, o None si viene vacía / 'NC' /
    'Sin_Isin_FCI' y similares."""
    if v is None or v != v:
        return None
    s = " ".join(str(v).split())
    if s.upper() in _SIN_DATO or s.upper().startswith("SIN_"):
        return None
    return s


# ── carga ──────────────────────────────────────────────────────────────────
def _file_asof(path: Optional[str]) -> Optional[str]:
    """Fecha/hora de última modificación del archivo → 'DD/MM/AAAA HH:MM'
    (proxy de 'última cartera', no hay columna de fecha en la composición)."""
    if not path:
        return None
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M")
    except OSError:
        return None


def _galileo_viejo_presente(comp_path: str) -> bool:
    """¿Sigue el viejo Galileo_Composicion.xlsx donde el loader anterior lo
    buscaba? (GALILEO_COMPOSICION_PATH de un secrets.txt viejo, la carpeta de
    Delta_Composicion y DELTA_BASES_DIR). Sólo un listado de carpeta / un
    stat por carga: el archivo no se abre."""
    env = os.getenv("GALILEO_COMPOSICION_PATH")
    if env:
        try:
            if os.path.isfile(deltapaths.expand(env, want="file")):
                return True
        except Exception:  # noqa: BLE001
            pass
    carpetas = [os.path.dirname(comp_path)]
    base = os.getenv("DELTA_BASES_DIR")
    if base:
        try:
            carpetas.append(deltapaths.expand(base, want="dir").rstrip("\\/"))
        except Exception:  # noqa: BLE001
            pass
    return any(_find_ci(d, _GALILEO_VIEJO_FILE) for d in carpetas)


def _load() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "loaded": False, "error": None, "holdings": [], "pn": {}, "fondos": {},
        "paths": {}, "asof": None, "galileo_viejo": False,
    }
    comp_path = _resolve(_COMPOSICION_FILE, "DELTA_COMPOSICION_PATH")
    pn_path = _resolve(_PN_FILE, "DELTA_PN_PATH")
    out["paths"] = {"composicion": comp_path, "pn": pn_path}
    out["asof"] = _file_asof(comp_path)
    if comp_path is None:
        out["error"] = ("No se encontró Delta_Composicion.xlsx — configurá "
                        "DELTA_BASES_DIR o DELTA_COMPOSICION_PATH en secrets.txt.")
        return out
    # El viejo archivo Galileo NO se abre (los fondos Galileo ya son fondos
    # Delta): sólo se avisa, una vez por carga, si sigue en la carpeta.
    if _galileo_viejo_presente(comp_path):
        out["galileo_viejo"] = True
        logger.info("[positions] %s sigue en la carpeta de carteras: se ignora "
                    "(los fondos Galileo ya viven en %s)", _GALILEO_VIEJO_FILE, _COMPOSICION_FILE)

    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"pandas no disponible: {exc}"
        return out

    try:
        dfc = pd.read_excel(comp_path, sheet_name="Sheet1")
    except Exception as exc:  # noqa: BLE001
        # Marcador de OneDrive sin bajar (Windows, [Errno 22]): que Posiciones
        # y Matriz digan la CAUSA y el remedio, no el errno (glow-up C, 06/11).
        # El vigilante de datos_nube recarga solo cuando el archivo baja.
        from backend.services import nube
        out["error"] = (nube.remedio(comp_path) if nube.ilegible_por_nube(comp_path, exc)
                        else f"Error leyendo composición: {exc}")
        return out

    if "CodFondo" not in dfc.columns:
        out["error"] = "Delta_Composicion.xlsx no tiene columna 'CodFondo'."
        return out

    dfc = dfc.dropna(subset=["CodFondo"]).copy()
    dfc["CodFondo"] = pd.to_numeric(dfc["CodFondo"], errors="coerce")
    dfc = dfc.dropna(subset=["CodFondo"])
    for col in ("Cantidad", "Valor"):
        if col in dfc.columns:
            dfc[col] = pd.to_numeric(dfc[col], errors="coerce")

    holdings: List[Dict[str, Any]] = []
    has_cd = "Cod_Delta" in dfc.columns
    # Descripción de la tenencia: el archivo real de carteras la trae en
    # `Inversion` (18/11: la app leía `Especie`, que ese archivo no tiene — el
    # Nombre quedaba vacío y la clasificación por descripción no veía nada).
    col_desc = next((c for c in ("Especie", "Inversion", "Inversión") if c in dfc.columns), None)
    has_clase = "Clase de Activo" in dfc.columns
    # Datos de la base de especies que el archivo ya trae por fila: ISIN,
    # moneda de pago (USD cable / USB MEP) y ticker con el que el desk lo
    # valúa. Con eso se concilia el código de ESCO con la ficha (services.esco).
    col_isin = next((c for c in ("IsinCode", "ISIN", "Isin") if c in dfc.columns), None)
    col_pago = "Pago" if "Pago" in dfc.columns else None
    col_tk = next((c for c in ("CAFCI_BYMA", "BYMA") if c in dfc.columns), None)
    for _, r in dfc.iterrows():
        cod_delta = _norm_code(r.get("Cod_Delta")) if has_cd else None
        desc = _celda(r.get(col_desc)) if col_desc else None
        holdings.append({
            "cod_fondo": int(r["CodFondo"]),
            "cod_delta": cod_delta,
            "especie": desc or cod_delta or "—",
            "cantidad": _f(r.get("Cantidad")),
            "valor": _f(r.get("Valor")),
            "clase": (str(r.get("Clase de Activo")).strip() if has_clase and r.get("Clase de Activo") == r.get("Clase de Activo") else None),
            # En Delta, especie de mercado = fila con ticker (NC/None = cash).
            "es_especie": cod_delta is not None,
            "isin": (_celda(r.get(col_isin)) or "").upper() or None if col_isin else None,
            "pago": (_celda(r.get(col_pago)) or "").upper() or None if col_pago else None,
            "ticker": (_celda(r.get(col_tk)) or "").upper() or None if col_tk else None,
        })

    pn: Dict[int, float] = {}
    if pn_path:
        try:
            dfp = pd.read_excel(pn_path, sheet_name="Sheet1")
            dfp["CodFondo"] = pd.to_numeric(dfp["CodFondo"], errors="coerce")
            dfp["PN"] = pd.to_numeric(dfp["PN"], errors="coerce")
            for _, r in dfp.dropna(subset=["CodFondo", "PN"]).iterrows():
                pn[int(r["CodFondo"])] = float(r["PN"])
        except Exception as exc:  # noqa: BLE001
            from backend.services import nube
            logger.warning("[positions] PN load failed: %s",
                           nube.remedio(pn_path) if nube.ilegible_por_nube(pn_path, exc) else exc)

    out["fondos"] = _fondo_names()
    out["monedas"] = _fondo_monedas()
    out["holdings"] = holdings
    out["pn"] = pn
    # Índice por Cod_Delta → posición agregada (O(1) en position_for).
    by_code: Dict[str, Dict[str, Any]] = {}
    for h in holdings:
        code = h["cod_delta"]
        if not code:
            continue
        agg = by_code.setdefault(code, {
            "especie": h["especie"], "total_cantidad": 0.0, "total_valor": 0.0, "funds": [],
        })
        agg["total_cantidad"] += (h["cantidad"] or 0.0)
        agg["total_valor"] += (h["valor"] or 0.0)
        agg["funds"].append({"cod_fondo": h["cod_fondo"], "cantidad": h["cantidad"], "valor": h["valor"]})
    out["by_code"] = by_code
    out["loaded"] = True
    logger.info("[positions] cargado: %d holdings, %d fondos con PN", len(holdings), len(pn))
    return out


# ── API pública ────────────────────────────────────────────────────────────
def ensure_loaded() -> Dict[str, Any]:
    # Fast-path SIN lock (lectura de referencia atómica bajo el GIL): todos los
    # accessors pasan por acá y antes tomaban _lock incondicionalmente — con
    # un refresh() en vuelo (segundos de read_excel sobre OneDrive) CUALQUIER
    # request que tocara posiciones quedaba bloqueado detrás, incluidos los 8
    # workers del pool de curvas vía position_for. Mismo patrón que historico.
    global _cache, _generation
    c = _cache
    if c is not None:
        return c
    with _lock:
        if _cache is None:
            _cache = _load()
            _generation += 1
        return _cache


def is_loaded() -> bool:
    """True si el cache ya está poblado, SIN disparar la carga. Para vistas
    que quieren mostrar data sólo si ya está (p. ej. la tarjeta de fondos de
    /admin durante el boot) sin bloquear el event loop con la lectura de los
    Excel — el warmup la puebla enseguida igual."""
    return _cache is not None


def refresh() -> Dict[str, Any]:
    """Fuerza relectura de los Excel (botón 'actualizar'). La carga corre
    FUERA del lock: los lectores siguen sirviendo el cache viejo mientras
    tanto (segundos de I/O) y sólo el swap de referencia va bajo lock."""
    global _cache, _generation
    nuevo = _load()
    with _lock:
        _cache = nuevo
        _generation += 1
        return nuevo


def status() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "paths": c["paths"],
            "n_holdings": len(c["holdings"]), "n_fondos_pn": len(c["pn"]),
            "asof": c.get("asof"),
            # True = el viejo Galileo_Composicion.xlsx sigue en la carpeta (no se lee)
            "galileo_viejo": bool(c.get("galileo_viejo"))}


def fuentes() -> List[Dict[str, Any]]:
    """De qué archivo salió cada fondo (diagnóstico de /admin): código,
    nombre, archivo, tenencias, PN. Todos salen de Delta_Composicion.xlsx;
    `ignorado` queda siempre False (lo espera el template)."""
    c = ensure_loaded()
    if not c["loaded"]:
        return []
    conteo: Dict[int, int] = {}
    for h in c["holdings"]:
        conteo[h["cod_fondo"]] = conteo.get(h["cod_fondo"], 0) + 1
    return [{"cod": cod, "nombre": fondo_label(cod), "n": n, "pn": c["pn"].get(cod),
             "archivo": _COMPOSICION_FILE, "ignorado": False}
            for cod, n in sorted(conteo.items())]


def fondo_moneda(cod: Optional[int]) -> Optional[str]:
    """Moneda de la contabilidad del fondo (ARS / USD / USB) según
    Delta_Fondos.txt, o None si el archivo no la trae."""
    if cod is None:
        return None
    return (ensure_loaded().get("monedas") or {}).get(cod)


def fondo_label(cod: int) -> str:
    nombre = ensure_loaded()["fondos"].get(cod)
    return f"{cod} — {nombre}" if nombre else f"Fondo {cod}"


# `visibles` en toda la API pública: filtro de fondos por usuario (None = sin
# filtro; set de cod_fondo = sólo esos). Lo setea el superuser desde /admin
# (auth.visible_fondos_for(request)) y se aplica ACÁ, en el provider, para que
# ninguna vista (Posiciones/Matriz/YAS/Comparador/Curvas) pueda filtrar
# tenencias de fondos ajenos por accidente de template.

def fondos(visibles: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    """Lista de fondos presentes en la composición, con su PN."""
    c = ensure_loaded()
    cods = sorted({h["cod_fondo"] for h in c["holdings"]})
    if visibles is not None:
        vis = set(visibles)
        cods = [cod for cod in cods if cod in vis]
    return [{"cod": cod, "nombre": fondo_label(cod), "pn": c["pn"].get(cod)} for cod in cods]


def holdings(cod_fondo: int, visibles: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    if visibles is not None and cod_fondo not in set(visibles):
        return []
    c = ensure_loaded()
    return [h for h in c["holdings"] if h["cod_fondo"] == cod_fondo]


def pn_of(cod_fondo: int) -> Optional[float]:
    return ensure_loaded()["pn"].get(cod_fondo)


def especies_universe() -> List[str]:
    """Cod_Delta únicos (para el warmup de la matriz especies×fondos)."""
    c = ensure_loaded()
    return sorted({h["cod_delta"] for h in c["holdings"] if h["cod_delta"]})


def _conciliada(h: Dict[str, Any]) -> bool:
    try:
        from . import esco
        return esco.resolver_h(h) is not None
    except Exception:  # noqa: BLE001
        return False


def tickers_conciliados() -> List[str]:
    """Tickers de mercado que valúan a las tenencias cuyo código de ESCO se
    concilió con una ficha (`services.esco`): la ficha, su especie en pesos y
    el ticker de la base (CAFCI_BYMA). Para suscribirlos al feed: el símbolo
    del código de ESCO no existe y la fila quedaba sin precio."""
    out: set = set()
    try:
        from . import esco, pricing
        for h in ensure_loaded()["holdings"]:
            if not h["cod_delta"]:
                continue
            f = esco.resolver_h(h)
            if f is None:
                continue
            out.add(f.calc)
            if esco.es_dolar(f.calc):
                sib = pricing.pesos_sibling_code(f.calc)
                if sib:
                    out.add(sib)
                base = f.calc[:-1] if f.calc[-1:] in ("C", "D") else f.calc
                out.add(base + "O")
            tk = h.get("ticker")
            if tk and " " not in tk:
                out.add(tk)
    except Exception:  # noqa: BLE001 — el seed del feed nunca rompe por esto
        logger.exception("[positions] tickers conciliados")
    return sorted(out)


def _equity_tickers_conocidos() -> set:
    """Tickers de acciones/CEDEARs que la app conoce (paneles curados + vivos
    + universo CEDEAR): para que el reporte de faltantes no marque una acción
    mapeada como 'falta en especies.py' (las acciones no viven ahí)."""
    out: set = set()
    try:
        from backend.services import equities
        out |= set(equities.LIDERES) | set(equities.GENERAL) | set(equities.CEDEARS)
        try:
            out |= set(equities.cedears_universo() or [])
        except Exception:  # noqa: BLE001
            pass
        for p in ("lideres", "general", "cedears"):
            try:
                out |= set(equities.panel_tickers(p) or [])
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return {str(t).strip().upper() for t in out if t}


def especies_faltantes() -> Dict[str, Any]:
    """Reporte para el panel de control: qué tickers de las carteras NO
    están en la base (especies.py para bonos; paneles/CEDEARs para acciones).
    Corre sobre el cache de holdings + sets en memoria — O(n) lookups, sub-ms,
    sin I/O."""
    c = ensure_loaded()
    bonos: set = set()
    try:
        from backend.services import bond_universe
        bond_universe.ensure_loaded()
        bonos = {str(x).strip().upper() for x in bond_universe.all_codes()}
    except Exception:  # noqa: BLE001
        pass
    eq = _equity_tickers_conocidos()
    try:                                    # renta variable de la hoja Base RV (ADRs, 'VIST US'…)
        from backend.services import delta_especies
        en_rv = delta_especies.info_rv
    except Exception:  # noqa: BLE001
        en_rv = lambda _c: None             # noqa: E731
    faltantes: Dict[str, Dict[str, Any]] = {}
    for h in c["holdings"]:
        code = h["cod_delta"]
        if not code or not h.get("es_especie", True):
            continue                        # sin ticker (NC / cash): no es especie
        if code in bonos or code in eq or en_rv(code) is not None:
            continue
        if _conciliada(h):                  # código de ESCO con ficha por ISIN (TTCDOD → TTCDC)
            continue
        d = faltantes.setdefault(code, {
            "code": code, "especie": h["especie"], "n_filas": 0, "valor": 0.0})
        d["n_filas"] += 1
        d["valor"] += (h["valor"] or 0.0)
    rows = sorted(faltantes.values(), key=lambda x: -(x["valor"] or 0.0))
    return {"faltantes": rows, "n_faltantes": len(rows)}


_por_ficha: tuple = (None, {})


def _un_fondo_una_vez(funds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Un fondo que tiene el mismo papel bajo dos códigos (el de pesos y el
    "…D" de ESCO) cuenta UNA vez, con cantidad y valor sumados."""
    por: Dict[int, Dict[str, Any]] = {}
    for f in funds:
        d = por.get(f["cod_fondo"])
        if d is None:
            por[f["cod_fondo"]] = dict(f)
        else:
            d["cantidad"] = (d["cantidad"] or 0.0) + (f["cantidad"] or 0.0)
            d["valor"] = (d["valor"] or 0.0) + (f["valor"] or 0.0)
    return list(por.values())


def _agg_por_ficha() -> Dict[str, Dict[str, Any]]:
    """Ficha del universo → posición agregada de las tenencias cuyo código de
    ESCO se concilia con ella (`services.esco`). Se arma una vez por carga de
    carteras / universo; después es un lookup."""
    global _por_ficha
    try:
        from . import esco
        c = ensure_loaded()
        tok = (_generation, esco.token())
        if _por_ficha[0] == tok:
            return _por_ficha[1]
        out: Dict[str, Dict[str, Any]] = {}
        for h in c["holdings"]:
            if not h["cod_delta"]:
                continue
            f = esco.resolver_h(h)
            if f is None:
                continue
            agg = out.setdefault(f.calc, {"especie": h["especie"], "total_cantidad": 0.0,
                                          "total_valor": 0.0, "funds": []})
            agg["total_cantidad"] += (h["cantidad"] or 0.0)
            agg["total_valor"] += (h["valor"] or 0.0)
            agg["funds"].append({"cod_fondo": h["cod_fondo"], "cantidad": h["cantidad"], "valor": h["valor"]})
        for agg in out.values():
            agg["funds"] = _un_fondo_una_vez(agg["funds"])
        _por_ficha = (tok, out)
        return out
    except Exception:  # noqa: BLE001 — la tenencia en YAS nunca rompe por esto
        logger.exception("[positions] tenencias por ficha conciliada")
        return {}


def position_for(code: Optional[str],
                 visibles: Optional[Iterable[int]] = None) -> Optional[Dict[str, Any]]:
    """Posición agregada en un instrumento (suma de los fondos VISIBLES).

    `code` matchea Cod_Delta (upper). None si no se tiene el papel (o si el
    usuario no ve ningún fondo que lo tenga — no debe enterarse de que el desk
    lo tiene). Incluye el detalle por fondo (nombre + % PN) ordenado por valor;
    con filtro, los totales se recalculan sobre lo visible.
    """
    if not code:
        return None
    from . import symbols as syms  # normaliza sufijos j/v igual que el path de precios
    c = ensure_loaded()
    by = c.get("by_code", {})
    key = _strip_plazo(str(code).strip().upper())    # ignora ' CI' / ' 24hs'
    agg = by.get(key)
    if not agg:                       # fallback: TTS26v / TX26j → TTS26 / TX26 (md_symbol)
        # El strip del sufijo de calc (j/v MINÚSCULA) corre sobre el case ORIGINAL:
        # uppercasear antes ('v'→'V') lo rompía y además mutilaba tickers reales
        # como SUPV. Se quita primero el plazo, después el sufijo j/v. Ver
        # symbols.calc_to_md_code.
        base = _strip_plazo(str(code).strip())       # conserva el case del sufijo j/v
        key = syms.calc_to_md_code(base).upper()
        agg = by.get(key)
    # Tenencias que ESCO trae con OTRO código y se concilian con esta ficha
    # (TTCDOD / YPF34 → la ficha nativa): se suman a las del código exacto.
    por_ficha = _agg_por_ficha()
    limpio = _strip_plazo(str(code).strip().upper())   # mismo trato que el código directo: sin plazo ni mayúsculas
    extra = por_ficha.get(limpio)
    if extra:
        agg = extra if not agg else {
            "especie": agg["especie"],
            "total_cantidad": agg["total_cantidad"] + extra["total_cantidad"],
            "total_valor": agg["total_valor"] + extra["total_valor"],
            "funds": _un_fondo_una_vez(agg["funds"] + extra["funds"])}
    if not agg:
        return None
    vis = set(visibles) if visibles is not None else None
    funds = []
    for f in agg["funds"]:
        if vis is not None and f["cod_fondo"] not in vis:
            continue
        pn = c["pn"].get(f["cod_fondo"])
        funds.append({
            "cod_fondo": f["cod_fondo"],
            "nombre": fondo_label(f["cod_fondo"]),
            "cantidad": f["cantidad"],
            "valor": f["valor"],
            "pct_pn": (f["valor"] / pn) if (f["valor"] and pn and pn > 0) else None,
        })
    if not funds:                     # ningún fondo visible lo tiene ⇒ "no hay posición"
        return None
    funds.sort(key=lambda x: (x["valor"] or 0.0), reverse=True)
    if vis is None:
        total_cantidad, total_valor = agg["total_cantidad"], agg["total_valor"]
    else:                             # totales SOLO de lo visible (no filtrar el agregado)
        total_cantidad = sum((f["cantidad"] or 0.0) for f in funds)
        total_valor = sum((f["valor"] or 0.0) for f in funds)
    # El Valor de cada fondo está en SU moneda: con fondos en pesos y en
    # dólares teniendo el mismo papel la suma no significa nada (3.223 M de
    # pesos + 1,4 M de dólares) → sin total; el detalle por fondo sigue.
    monedas = ensure_loaded().get("monedas") or {}
    clases = {("dolar" if monedas.get(f["cod_fondo"]) in ("USD", "USB") else "pesos")
              for f in funds if monedas.get(f["cod_fondo"])}
    if len(clases) > 1:
        total_valor = None
    return {
        "code": key,
        "total_cantidad": total_cantidad,
        "total_valor": total_valor,
        "n_fondos": len(funds),
        "funds": funds,
    }
