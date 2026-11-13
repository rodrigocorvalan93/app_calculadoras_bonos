"""Proyecciones vigentes — inflación mensual y A3500 editables desde la app (13/11).

Hasta ahora las dos tablas vivían como dicts fijos en `indices.py`
(`proyeccion_inflacion_mensual`, `proyeccion_devaoficial_escenariobase`) y
cambiarlas era editar código, commitear y reiniciar cada PC. Pedido del desk:
una pestaña para modificarlas y que TODO las tome al instante, sin que se
trabe nada (en las calculadoras viejas cada widget re-corría el equivalente de
`indices.main()` entero — HTTP al BCRA + series a 30 años — en el hilo de la
interfaz).

Diseño:
- **Un archivo compartido, no código**: `data/proyecciones.json` (viaja por
  OneDrive a todas las PCs como la pizarra; `PROYECCIONES_PATH` lo mueve, la
  suite lo apunta a un tmp). Los dicts de `indices.py` quedan como semilla y
  fallback (`defaults()`); `indices.main()` lee el archivo si existe
  (`indices.proyecciones_vigentes`), así un reinicio conserva el escenario.
- **Recalcular SÓLO la parte proyectada, nunca `indices.main()`**:
  `calcular()` toma las series OBSERVADAS que ya están en memoria
  (`rentafija.inputs`: CER, inflación INDEC, A3500 publicado, UVA) y pasa por
  `indices.armar_proyecciones` — la MISMA función que usa `main()` — así el
  resultado es idéntico bit a bit a arrancar con esas tablas. Milisegundos.
- **Instalar = reasignar los DataFrames en `inputs`** (`instalar`): los bonos
  leen `cer_proyectado` / `uva_proyectado` / `a3500_proyectado` en cada
  cálculo, y `pricing._proyeccion_token` (id + largo + último valor) entra en
  la key de TODOS los caches de métricas, flujos y filas → las TIR se
  recomputan solas en el próximo tick. Sin tocar floaters (TAMAR/BADLAR siguen
  planas; segunda etapa).
- **Las otras PCs lo toman solas**: `vigilante` (thread daemon, un `stat` por
  segundo) ve cambiar la firma mtime+tamaño del JSON y reinstala.
- **Historial**: cada cambio deja una línea en `proyecciones_log.jsonl` con
  el escenario ANTERIOR y el nuevo (autor, hora, nota); `deshacer` repone el
  anterior; `restablecer` vuelve al del código.

Nada de esto corre en un request salvo `vigente()` (memo por firma) y los
`calcular` de la vista previa / aplicar, que las rutas mandan al executor.
"""
from __future__ import annotations

import csv
import io
import itertools
import json
import logging
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
logger = logging.getLogger("backend.proyecciones")

_lock = threading.RLock()
_ver = itertools.count(1)
_version = 0                       # sube con cada instalación (key de memos derivados)
_instalada_sig: Any = None         # firma del archivo cuyo contenido está instalado en inputs
_vigente_memo: Tuple[Any, Optional[Dict[str, Any]]] = (None, None)
_calc_memo: Tuple[Any, Optional[Dict[str, Any]]] = (None, None)

INFL_MIN, INFL_MAX = -5.0, 50.0            # % mensual: fuera de esto es un typo
A3500_MIN, A3500_MAX = 1.0, 1_000_000.0    # pesos por dólar
MAX_FILAS = 360                            # 30 años de meses
_RE_MES = re.compile(r"^\d{4}-\d{2}$")
_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MESES_EN = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun",
                                             "jul", "aug", "sep", "oct", "nov", "dec"))}
_MESES_AR = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
COLS = ("cer_proyectado", "uva_proyectado", "a3500_proyectado", "inflamom")


# ── rutas ────────────────────────────────────────────────────────────────────
def ruta() -> Path:
    env = os.getenv("PROYECCIONES_PATH")
    if env:
        return Path(os.path.expandvars(os.path.expanduser(env)))
    return REPO_ROOT / "data" / "proyecciones.json"


def ruta_log() -> Path:
    p = ruta()
    return p.with_name(p.stem + "_log.jsonl")


def firma() -> Optional[Tuple[int, int]]:
    try:
        st = ruta().stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


# ── semilla del código ───────────────────────────────────────────────────────
def mes_iso(clave: Any) -> Optional[str]:
    """'Nov-26' / '2026-11' / '2026-11-30' → '2026-11'; None si no se entiende."""
    s = str(clave).strip()
    if _RE_MES.match(s) or _RE_FECHA.match(s):
        try:
            date.fromisoformat(s[:7] + "-01")
        except ValueError:
            return None
        return s[:7]
    m = re.match(r"^([A-Za-z]{3})-(\d{2})$", s)
    if m and m.group(1).lower() in _MESES_EN:
        return f"20{m.group(2)}-{_MESES_EN[m.group(1).lower()]:02d}"
    return None


def defaults() -> Dict[str, Any]:
    """Las tablas de `indices.py` (semilla), en el formato del archivo."""
    import indices
    infl = {}
    for k, v in indices.proyeccion_inflacion_mensual.items():
        mi = mes_iso(k)
        if mi:
            infl[mi] = float(v)
    deva = {str(k)[:10]: float(v) for k, v in indices.proyeccion_devaoficial_escenariobase.items()}
    return {"inflacion": dict(sorted(infl.items())), "a3500": dict(sorted(deva.items()))}


# ── validación ───────────────────────────────────────────────────────────────
def normalizar(raw: Any) -> Dict[str, Any]:
    """{'inflacion': {mes: %}, 'a3500': {fecha: nivel}} saneado y ordenado, o
    ValueError con TODOS los problemas (en es-AR, para mostrar tal cual)."""
    problemas: List[str] = []
    if not isinstance(raw, dict):
        raise ValueError("el escenario tiene que ser un objeto con 'inflacion' y 'a3500'")
    infl: Dict[str, float] = {}
    for k, v in (raw.get("inflacion") or {}).items():
        mi = mes_iso(k)
        if not mi:
            problemas.append(f"inflación: mes inválido '{k}' (esperaba AAAA-MM)")
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            problemas.append(f"inflación {mi}: valor inválido '{v}'")
            continue
        if f != f or not (INFL_MIN <= f <= INFL_MAX):
            problemas.append(f"inflación {mi}: {f} fuera de rango [{INFL_MIN:g} %, {INFL_MAX:g} %]")
            continue
        infl[mi] = f
    deva: Dict[str, float] = {}
    for k, v in (raw.get("a3500") or {}).items():
        s = str(k).strip()
        try:
            d = date.fromisoformat(s[:10])
        except ValueError:
            problemas.append(f"A3500: fecha inválida '{k}' (esperaba AAAA-MM-DD)")
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            problemas.append(f"A3500 {d.isoformat()}: valor inválido '{v}'")
            continue
        if f != f or not (A3500_MIN <= f <= A3500_MAX):
            problemas.append(f"A3500 {d.isoformat()}: {f} fuera de rango")
            continue
        deva[d.isoformat()] = f
    if len(infl) > MAX_FILAS or len(deva) > MAX_FILAS:
        problemas.append(f"demasiadas filas (tope {MAX_FILAS})")
    if problemas:
        raise ValueError("; ".join(problemas))
    return {"inflacion": dict(sorted(infl.items())), "a3500": dict(sorted(deva.items()))}


# ── archivo ──────────────────────────────────────────────────────────────────
def _leer_archivo() -> Optional[Dict[str, Any]]:
    p = ruta()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[proyecciones] %s ilegible (%s): uso las del código", p.name, exc)
        return None
    try:
        esc = normalizar(data)
    except ValueError as exc:
        logger.warning("[proyecciones] %s inválido (%s): uso las del código", p.name, exc)
        return None
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    esc["meta"] = {"origen": "archivo", "autor": str(meta.get("autor") or ""),
                   "ts": str(meta.get("ts") or ""), "nota": str(meta.get("nota") or ""),
                   "accion": str(meta.get("accion") or "")}
    return esc


def vigente() -> Dict[str, Any]:
    """El escenario que rige: el archivo (si existe y es válido) o el del
    código. Memo por firma del archivo: µs en caliente."""
    global _vigente_memo
    sig = firma()
    memo_sig, memo = _vigente_memo
    if memo is not None and memo_sig == sig and sig is not None:
        return memo
    esc = _leer_archivo() if sig is not None else None
    if esc is None:
        # Sin archivo (o ilegible): las tablas del código, SIN memo — son dos
        # dicts chicos y un test puede parchear `indices.proyeccion_*`.
        esc = defaults()
        esc["meta"] = {"origen": "codigo", "autor": "", "ts": "", "nota": "", "accion": ""}
        if sig is None:
            return esc
    _vigente_memo = (sig, esc)
    return esc


def _escribir(esc: Dict[str, Any], meta: Dict[str, Any]) -> None:
    p = ruta()
    p.parent.mkdir(parents=True, exist_ok=True)
    cuerpo = {"v": 1, "inflacion": esc["inflacion"], "a3500": esc["a3500"], "meta": meta}
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cuerpo, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _log(entrada: Dict[str, Any]) -> None:
    try:
        with open(ruta_log(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("[proyecciones] no pude escribir el log")


def historial(n: int = 20) -> List[Dict[str, Any]]:
    """Las últimas `n` entradas del log (más nueva primero), sin los escenarios
    completos (para la pestaña)."""
    try:
        lineas = ruta_log().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for ln in reversed(lineas[-n:]):
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        out.append({"ts": e.get("ts"), "autor": e.get("autor"), "accion": e.get("accion"),
                    "nota": e.get("nota"), "resumen": e.get("resumen")})
    return out


def _ultima_entrada() -> Optional[Dict[str, Any]]:
    try:
        lineas = ruta_log().read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for ln in reversed(lineas):
        try:
            return json.loads(ln)
        except ValueError:
            continue
    return None


# ── observadas + cálculo ─────────────────────────────────────────────────────
def _a_date(x: Any) -> Optional[date]:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


_obs_memo: Tuple[Any, Optional[Dict[str, Any]]] = (None, None)


def _indice_de_fechas(df: Any) -> Any:
    """El frame con el índice como objetos `date` puros, ordenado y sin
    duplicados (gana el último). `inputs['a3500']` puede traer filas con
    índice de TEXTO o datetime (el poller de FX legacy y algún test inyectan
    `.loc["2026-06-26"]`) y `armar_proyecciones` hace `index[-1].strftime`.
    Un frame ya limpio vuelve tal cual (misma identidad: el memo y el bit a
    bit con `indices.main()` no cambian)."""
    if df is None or not len(df):
        return df
    idx = list(df.index)
    if all(type(ix) is date for ix in idx):
        return df
    fechas = [_a_date(ix) for ix in idx]
    keep = [i for i, d in enumerate(fechas) if d is not None]
    out = df.iloc[keep].copy()
    out.index = [fechas[i] for i in keep]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.index.name = df.index.name
    return out


def observadas() -> Dict[str, Any]:
    """Las series observadas en memoria con las que se arma la proyección:
    CER, inflación mensual INDEC, A3500 publicado y UVA. El A3500 de
    `inputs` puede traer la fila de HOY que inyecta especies.py (SIOPEL del
    arranque, saneada por bond_universe); acá se corta en el último publicado
    por el BCRA (backup en memoria de `historico`), que es exactamente lo que
    usa `indices.main()`. Memo por los ids de los frames + versión del backup
    (cambian con cada refresh de índices)."""
    global _obs_memo
    import rentafija
    from backend.services import historico

    cer = rentafija.inputs["CER"]
    infl = rentafija.inputs["inflamom_observado"]
    a3500 = rentafija.inputs["a3500"]
    uva = rentafija.inputs["UVA"]
    try:
        carga = historico.ensure_loaded()
        pts = (carga["series"].get("a3500") or {}).get("points") or []
        ver = carga.get("ver")
    except Exception:  # noqa: BLE001
        pts, ver = [], None
    key = (id(cer), id(infl), id(a3500), id(uva), ver)
    memo_key, memo = _obs_memo
    if memo is not None and memo_key == key:
        return memo
    cer, infl, a3500, uva = (_indice_de_fechas(x) for x in (cer, infl, a3500, uva))
    if pts and len(a3500):
        ult = _a_date(pts[-1][0])
        if ult is not None:
            mask = [(_a_date(ix) or ult) <= ult for ix in a3500.index]
            if not all(mask):
                a3500 = a3500[mask]
    out = {"cer": cer, "inflamom": infl, "a3500": a3500, "uva": uva, "key": key,
           "ultimos": {"cer": _a_date(cer.index[-1]) if len(cer) else None,
                       "inflamom": _a_date(infl.index[-1]) if len(infl) else None,
                       "a3500": _a_date(a3500.index[-1]) if len(a3500) else None,
                       "cer_valor": float(cer["CER"].iloc[-1]) if len(cer) else None,
                       "a3500_valor": float(a3500["tca3500"].iloc[-1]) if len(a3500) else None}}
    _obs_memo = (key, out)
    return out


def calcular(esc: Dict[str, Any]) -> Dict[str, Any]:
    """Series proyectadas para un escenario (sin instalar nada): las cuatro
    claves de `COLS` + `ultimos` (fechas de corte). Mismo camino que
    `indices.main()` → bit a bit igual a arrancar con esas tablas."""
    import indices

    obs = observadas()
    inflamom, cer, uva, a3500 = indices.armar_proyecciones(
        obs["cer"], obs["inflamom"], obs["a3500"], obs["uva"], esc["inflacion"], esc["a3500"])
    return {"cer_proyectado": cer, "uva_proyectado": uva, "a3500_proyectado": a3500,
            "inflamom": inflamom, "ultimos": obs["ultimos"]}


def calcular_vigente() -> Dict[str, Any]:
    """`calcular(vigente())` memoizado por (firma del archivo, observadas):
    la página y cada vista previa la piden; µs en caliente."""
    global _calc_memo
    obs = observadas()
    key = (firma(), obs["key"])
    memo_key, memo = _calc_memo
    if memo is not None and memo_key == key:
        return memo
    series = calcular(vigente())
    _calc_memo = (key, series)
    return series


def _instalar(series: Dict[str, Any], sig: Any) -> None:
    global _version, _instalada_sig, _calc_memo
    import rentafija

    with _lock:
        rentafija.inputs.update({k: series[k] for k in COLS})     # un setitem por clave (atómico bajo el GIL)
        _version = next(_ver)
        _instalada_sig = sig
        _calc_memo = (None, None)


def version() -> int:
    return _version


def token() -> tuple:
    """Huella de las series proyectadas instaladas (ids de los frames):
    cambia con `instalar` Y con un `inputs.refresh()` del warmup."""
    try:
        import rentafija
        return tuple(id(rentafija.inputs.get(k)) for k in COLS)
    except Exception:  # noqa: BLE001
        return ()


# ── acciones ─────────────────────────────────────────────────────────────────
def _ahora() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def resumen_escenario(esc: Dict[str, Any]) -> str:
    infl, deva = esc.get("inflacion") or {}, esc.get("a3500") or {}
    partes = []
    if infl:
        ks = sorted(infl)
        partes.append(f"inflación {len(ks)} meses ({mes_label(ks[0])} → {mes_label(ks[-1])})")
    if deva:
        ks = sorted(deva)
        partes.append(f"A3500 {len(ks)} puntos (hasta {ks[-1]}: {deva[ks[-1]]:.2f})")
    return " · ".join(partes) or "vacío"


def mes_label(mes: str) -> str:
    try:
        y, m = int(mes[:4]), int(mes[5:7])
        return f"{_MESES_AR[m - 1]}-{y % 100:02d}"
    except (ValueError, IndexError):
        return mes


def aplicar(raw: Any, autor: str, nota: str = "", accion: str = "aplicar") -> Dict[str, Any]:
    """Valida, guarda en el archivo compartido (+ log con el escenario anterior),
    recalcula e instala en `inputs`. Devuelve {'esc', 'series', 'cambio'}."""
    esc = normalizar(raw)
    with _lock:
        antes = vigente()
        series = calcular(esc)
        meta = {"autor": autor or "", "ts": _ahora(), "nota": (nota or "")[:200], "accion": accion}
        _escribir(esc, meta)
        _log({"ts": meta["ts"], "autor": meta["autor"], "accion": accion, "nota": meta["nota"],
              "resumen": resumen_escenario(esc),
              "antes": {"inflacion": antes["inflacion"], "a3500": antes["a3500"]},
              "despues": {"inflacion": esc["inflacion"], "a3500": esc["a3500"]}})
        _instalar(series, firma())
        global _vigente_memo
        _vigente_memo = (None, None)
    cambio = {"inflacion": esc["inflacion"] != antes["inflacion"], "a3500": esc["a3500"] != antes["a3500"]}
    logger.info("[proyecciones] %s por %s: %s%s", accion, autor or "?", resumen_escenario(esc),
                f" — {nota}" if nota else "")
    return {"esc": vigente(), "series": series, "cambio": cambio}


def deshacer(autor: str) -> Dict[str, Any]:
    """Repone el escenario ANTERIOR al último cambio del log (un deshacer de un
    deshacer vuelve adelante: es un intercambio, no una pila)."""
    ult = _ultima_entrada()
    if not ult or not isinstance(ult.get("antes"), dict):
        raise ValueError("no hay un cambio anterior para deshacer")
    return aplicar(ult["antes"], autor, nota=f"deshace lo de {ult.get('autor') or '?'} ({ult.get('ts') or ''})",
                   accion="deshacer")


def restablecer(autor: str) -> Dict[str, Any]:
    """Vuelve a las tablas de `indices.py` (quedan escritas en el archivo, así
    todas las PCs convergen)."""
    return aplicar(defaults(), autor, nota="escenario del código (indices.py)", accion="restablecer")


def instalar_desde_archivo(force: bool = False) -> bool:
    """Si el archivo cambió desde la última instalación (otra PC lo escribió,
    llegó por OneDrive), recalcula con lo vigente e instala. True si instaló."""
    sig = firma()
    if not force and sig == _instalada_sig:
        return False
    with _lock:
        if not force and sig == _instalada_sig:
            return False
        esc = vigente()
        series = calcular(esc)
        _instalar(series, sig)
    logger.info("[proyecciones] escenario %s instalado desde %s: %s",
                esc["meta"].get("origen"), ruta().name, resumen_escenario(esc))
    return True


# ── vigilante (otras PCs) ────────────────────────────────────────────────────
_vig_stop = threading.Event()
_vig_thread: Optional[threading.Thread] = None


def start_vigilante(intervalo: float = 1.0) -> bool:
    """Thread daemon: un `stat` por segundo sobre el JSON; al cambiar la firma
    reinstala (pandas, decenas de ms, fuera del event loop). `PROYECCIONES_WATCH=0`
    lo apaga (la suite)."""
    global _vig_thread, _instalada_sig
    if os.getenv("PROYECCIONES_WATCH", "1") == "0":
        return False
    if _vig_thread is not None and _vig_thread.is_alive():
        return True
    _instalada_sig = firma()           # lo que indices.main() leyó al arrancar
    _vig_stop.clear()

    def _run() -> None:
        while not _vig_stop.wait(intervalo):
            try:
                instalar_desde_archivo()
            except Exception:  # noqa: BLE001
                logger.exception("[proyecciones] el vigilante no pudo reinstalar")
                _vig_stop.wait(10)

    _vig_thread = threading.Thread(target=_run, name="proyecciones-vigilante", daemon=True)
    _vig_thread.start()
    return True


def stop_vigilante() -> None:
    _vig_stop.set()


# ── vistas (chart / tabla / CSV) ─────────────────────────────────────────────
def _fin_de_mes(d: date) -> date:
    nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return nxt - timedelta(days=1)


def _serie_ordenada(df: Any, col: str, desde: Optional[date], hasta: Optional[date]) -> Any:
    """pd.Series (índice datetime ordenado, float) recortada a [desde, hasta];
    None si no hay nada. Vectorizado: el CER diario son 11k filas."""
    import pandas as pd
    if df is None or not len(df):
        return None
    idx = pd.to_datetime(pd.Index(df.index), errors="coerce")
    s = pd.Series(df[col].to_numpy(dtype=float), index=idx)
    s = s[~s.index.isna()].sort_index()
    if desde is not None:
        s = s[s.index >= pd.Timestamp(desde)]
    if hasta is not None:
        s = s[s.index <= pd.Timestamp(hasta)]
    return s if len(s) else None


def muestreo_mensual(df: Any, col: str, desde: Optional[date] = None, hasta: Optional[date] = None,
                     ) -> List[Tuple[str, float]]:
    """(ISO, valor) en el ÚLTIMO dato de cada mes (liviano para un gráfico:
    30 años = 360 puntos en vez de 11.000)."""
    s = _serie_ordenada(df, col, desde, hasta)
    if s is None:
        return []
    ult = s.groupby([s.index.year, s.index.month]).tail(1)
    return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(ult.index, ult.to_numpy())]


def puntos(df: Any, col: str, desde: Optional[date] = None, hasta: Optional[date] = None) -> List[Tuple[str, float]]:
    s = _serie_ordenada(df, col, desde, hasta)
    if s is None:
        return []
    return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(s.index, s.to_numpy())]


def resumen(series: Dict[str, Any], esc: Dict[str, Any]) -> Dict[str, Any]:
    """Cifras para la pestaña: inflación anualizada implícita por año
    calendario de la tabla, CER y A3500 a 12 / 24 / 36 meses del corte y deva
    anual implícita."""
    import math

    infl = esc.get("inflacion") or {}
    por_anio: Dict[str, float] = {}
    meses_por_anio: Dict[str, int] = {}
    for mes, v in sorted(infl.items()):
        y = mes[:4]
        por_anio[y] = por_anio.get(y, 1.0) * (1.0 + v / 100.0)
        meses_por_anio[y] = meses_por_anio.get(y, 0) + 1
    anual = [{"anio": y, "meses": meses_por_anio[y], "acum": (por_anio[y] - 1.0) * 100.0,
              "anualizada": (por_anio[y] ** (12.0 / meses_por_anio[y]) - 1.0) * 100.0}
             for y in sorted(por_anio)]
    ult = series.get("ultimos") or {}
    cer_df, a3500_df = series.get("cer_proyectado"), series.get("a3500_proyectado")

    series_ord: Dict[str, Any] = {}

    def _en(df: Any, col: str, d0: Optional[date], meses: int) -> Optional[Dict[str, Any]]:
        if df is None or d0 is None or not len(df):
            return None
        objetivo = _fin_de_mes(date(d0.year + (d0.month - 1 + meses) // 12, (d0.month - 1 + meses) % 12 + 1, 1))
        if col not in series_ord:
            series_ord[col] = _serie_ordenada(df, col, None, None)
        s = series_ord[col]
        if s is None:
            return None
        cand = s[s.index <= __import__("pandas").Timestamp(objetivo)]
        if not len(cand) or cand.index[-1].date() < objetivo - timedelta(days=35):
            return None                         # la serie termina antes del horizonte: no se inventa
        return {"fecha": cand.index[-1].strftime("%Y-%m-%d"), "valor": float(cand.iloc[-1])}

    horizontes = []
    for m in (12, 24, 36):
        c = _en(cer_df, "CER", ult.get("cer"), m)
        a = _en(a3500_df, "tca3500", ult.get("a3500"), m)
        fila = {"meses": m, "cer": c, "a3500": a}
        if c and ult.get("cer_valor"):
            fila["cer_var"] = (c["valor"] / ult["cer_valor"]) ** (12.0 / m) * 100.0 - 100.0
        if a and ult.get("a3500_valor"):
            fila["deva"] = (a["valor"] / ult["a3500_valor"]) ** (12.0 / m) * 100.0 - 100.0
        horizontes.append(fila)
    return {"anual": anual, "horizontes": horizontes, "ultimos": ult,
            "inflacion_media": (math.prod(1.0 + v / 100.0 for v in infl.values()) ** (1.0 / len(infl)) - 1.0) * 100.0 if infl else None}


def chart_payload(series: Dict[str, Any], label: str, anios_atras: int = 2) -> Dict[str, Any]:
    """Series mensuales para el gráfico de la pestaña: CER y A3500, observado
    (último `anios_atras`) + proyectado, con la fecha de corte."""
    ult = series.get("ultimos") or {}
    out: Dict[str, Any] = {"label": label}
    for key, col, corte in (("cer", "CER", ult.get("cer")), ("a3500", "tca3500", ult.get("a3500"))):
        df = series.get(f"{key}_proyectado")
        desde = (corte - timedelta(days=365 * anios_atras)) if corte else None
        out[key] = {"pts": muestreo_mensual(df, col, desde=desde), "corte": corte.isoformat() if corte else None}
    infl = series.get("inflamom")
    out["inflamom"] = {"pts": puntos(infl, "inflacionmom", desde=(ult.get("inflamom") - timedelta(days=365 * anios_atras)) if ult.get("inflamom") else None),
                       "corte": ult["inflamom"].isoformat() if ult.get("inflamom") else None}
    return out


def _fmt_ar(v: Any, dec: int = 6) -> str:
    try:
        return f"{float(v):.{dec}f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _fmt_fecha(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso


def csv_serie(pts: List[Tuple[str, float]], corte: Optional[str], etiqueta: str, dec: int = 6) -> bytes:
    """CSV es-AR (`;` + coma decimal + BOM): Fecha;<etiqueta>;Tramo."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Fecha", etiqueta, "Tramo"])
    for iso, v in pts:
        tramo = "proyectado" if (corte and iso > corte) else "observado"
        w.writerow([_fmt_fecha(iso), _fmt_ar(v, dec), tramo])
    return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8")


SERIES_CSV = {
    "cer": ("cer_proyectado", "CER", "CER", "cer", 6),
    "uva": ("uva_proyectado", "UVA", "UVA", "cer", 6),
    "a3500": ("a3500_proyectado", "tca3500", "A3500", "a3500", 4),
    "inflamom": ("inflamom", "inflacionmom", "Inflación mensual (%)", "inflamom", 4),
}


def csv_de(series: Dict[str, Any], clave: str) -> Tuple[bytes, str]:
    """(bytes, nombre de archivo) del CSV de una serie proyectada."""
    if clave not in SERIES_CSV:
        raise KeyError(clave)
    key, col, etiqueta, corte_key, dec = SERIES_CSV[clave]
    ult = series.get("ultimos") or {}
    corte = ult.get(corte_key)
    pts = puntos(series.get(key), col)
    return csv_serie(pts, corte.isoformat() if corte else None, etiqueta, dec), f"{clave}_proyectado.csv"
