"""Copias en conflicto y archivos viejos al lado de las bases y del estado de
la app — panel del superuser en /admin ("Copias en conflicto").

Qué queda tirado en las carpetas y por qué:

  · OneDrive, cuando dos máquinas escriben el mismo archivo, deja la versión
    perdedora al lado con el nombre de la máquina ("Delta - historico_fx-
    NOTEBOOK-RC.xlsx", "… (conflicted copy …)"); esa copia PUEDE tener ruedas
    que la principal perdió (05/10: la base "perdió" 5 ruedas así).
  · La app aparta un archivo ilegible como `<archivo>.corrupto-<fecha>` (nunca
    lo borra), el backfill deja `*.bak-<fecha>` y una escritura cortada deja un
    `<archivo>.<pid>-<n>.tmp`.
  · Copias a mano: "… - copia.xlsx", "… (2).xlsx".

Acá se LISTAN (`escanear`: listdir + stat, µs), se ANALIZAN a pedido
(`analizar`: filas / ruedas / última de cada copia y de su principal, cacheado
por (path, mtime, tamaño) — leer un Excel de un año tarda segundos, por eso es
un botón y corre en el executor) y el superuser decide: `borrar` (sólo
archivos clasificados como copia, adentro de las carpetas escaneadas, con
re-chequeo al momento de borrar) o `incorporar` a la base px/tasas, al
historial FX o al de acciones las ruedas que SÓLO están en la copia (mismos
caminos de escritura de siempre: `append_and_save`, `escribir_fx`,
`append_acciones`). Nada se toca solo.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("backend.copias")

REPO_ROOT = Path(__file__).resolve().parents[2]

TIPOS_COPIA = ("conflicto", "copia", "corrupto", "backup", "temporal")
TIPO_LABEL = {"conflicto": "conflicto OneDrive", "copia": "copia", "corrupto": "apartado (ilegible)",
              "backup": "backup", "temporal": "temporal huérfano"}
_EXT_DATOS = (".xlsx", ".xlsm", ".parquet")
_MAX_POR_CARPETA = 400            # una carpeta con miles de archivos no se escanea entera (no es la nuestra)

_RE_LOCK_EXCEL = re.compile(r"^~\$")
_RE_CORRUPTO = re.compile(r"^(?P<base>.+?)\.corrupto-\d{8}-\d{6}(?:-\d+)?$")
_RE_BAK = re.compile(r"^(?P<base>.+?)\.bak-[\w.\-]+$")
# `_tmp_de`: <archivo>.<pid>-<n>.tmp ; escritores viejos: <archivo>.tmp / <archivo>.tmp.xlsx
_RE_TMP = re.compile(r"^(?P<base>.+?)(?:\.\d+-\d+)?\.tmp(?:\.(?:xlsx|parquet))?$")
_RE_HOST = re.compile(r"-(?=[A-Z0-9.\-]*[A-Z])[A-Z0-9][A-Z0-9.\-]*")   # "-NOTEBOOK-RC", "-DESKTOP-ABC12-2" (no "-old", no "-2025")

_lock = threading.Lock()
_STATS: Dict[str, Tuple[tuple, Dict[str, Any], Optional[Set[date]]]] = {}   # path → (firma, stats, fechas)
_MAX_STATS = 600
# Un .tmp más nuevo que esto puede ser una escritura EN CURSO (el writer cerró
# el archivo pero todavía no hizo os.replace) → no borrarlo todavía (A07).
_TMP_MIN_EDAD_S = 120


# ── carpetas ───────────────────────────────────────────────────────────────
def carpetas() -> List[Dict[str, Any]]:
    """Dónde se busca: la carpeta de la app (+ data/), la de las bases (Delta
    Bases), cierres/ (por año), Carteras y el journal local de esta máquina."""
    from backend.services import deltapaths
    from backend.services.historico_writer import CIERRES_DIRNAME, journal_dir

    out: List[Dict[str, Any]] = []
    vistos: Set[str] = set()

    def _add(label: str, path: Optional[str], recursivo: bool = False, local: bool = False) -> None:
        if not path:
            return
        try:
            if not os.path.isdir(path):
                return
            key = os.path.normcase(os.path.realpath(path))
        except OSError:
            return
        if key in vistos:
            return
        vistos.add(key)
        out.append({"label": label, "path": str(path), "recursivo": recursivo, "local": local})

    _add("app", str(REPO_ROOT))
    _add("app/data", str(REPO_ROOT / "data"))
    hist = deltapaths.historico_dir()
    _add("bases", hist)
    if hist:
        _add("cierres", os.path.join(hist, CIERRES_DIRNAME), recursivo=True)
    _add("carteras", deltapaths.expand(os.getenv("DELTA_BASES_DIR"), want="dir"))
    try:
        _add("journal (local)", journal_dir(), local=True)
    except Exception:  # noqa: BLE001
        pass
    return out


def fmt_bytes(n: int) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{n / 1024 ** 3:.2f} GB".replace(".", ",")


def _dentro_de(path: str, carpeta: str) -> bool:
    try:
        p = os.path.normcase(os.path.realpath(path))
        c = os.path.normcase(os.path.realpath(carpeta))
    except OSError:
        return False
    return p == c or p.startswith(c.rstrip("\\/") + os.sep)


# ── clasificación ──────────────────────────────────────────────────────────
def clasificar(nombre: str, nombres: "set | list") -> Optional[Dict[str, Optional[str]]]:
    """{tipo, principal (nombre en la misma carpeta o None)} si `nombre` es
    una copia; None si es un archivo propio. `nombres` = lo que hay al lado."""
    if _RE_LOCK_EXCEL.match(nombre):
        return None                                   # lock de un Excel abierto: transitorio, no es copia
    vecinos = set(nombres)
    for rx, tipo in ((_RE_TMP, "temporal"), (_RE_CORRUPTO, "corrupto"), (_RE_BAK, "backup")):
        m = rx.match(nombre)
        if m:
            base = m.group("base")
            return {"tipo": tipo, "principal": base if base in vecinos and base != nombre else None}
    stem, ext = os.path.splitext(nombre)
    if not ext:
        return None
    mejor: Optional[Tuple[str, str]] = None           # (stem del principal, resto)
    for otro in vecinos:
        if otro == nombre:
            continue
        s2, e2 = os.path.splitext(otro)
        if e2.lower() != ext.lower() or not s2 or not stem.startswith(s2) or len(stem) <= len(s2):
            continue
        resto = stem[len(s2):]
        low = resto.lower()
        # "-HOST", " (2)", " - copia", " (conflicted copy …)", "_copia". NO un
        # punto: "cer_completo.generated.csv" es otro archivo, no una copia.
        if not (resto[0] in "- (" or low.startswith(("_copia", " copia"))):
            continue
        if mejor is None or len(s2) > len(mejor[0]):
            mejor = (s2, resto)
    if mejor is None:
        return None
    s2, resto = mejor
    low = resto.lower()
    # OneDrive pega el nombre de la máquina (NetBIOS, mayúsculas): "-NOTEBOOK-RC",
    # "-DESKTOP-ABC12-2"; "-old" o "-2025" son copias a mano / archivadas.
    conflicto = "conflict" in low or bool(_RE_HOST.fullmatch(resto))
    return {"tipo": "conflicto" if conflicto else "copia", "principal": s2 + ext}


# ── escaneo ────────────────────────────────────────────────────────────────
def _entrada(carpeta: Dict[str, Any], dirpath: str, nombre: str, clas: Dict[str, Optional[str]]) -> Optional[Dict[str, Any]]:
    from backend.services.historico_writer import _TZ
    path = os.path.join(dirpath, nombre)
    try:
        st = os.stat(path)
    except OSError:
        return None
    mt = datetime.fromtimestamp(st.st_mtime, _TZ)
    principal = os.path.join(dirpath, clas["principal"]) if clas.get("principal") else None
    return {"path": path, "nombre": nombre, "carpeta": carpeta["label"], "carpeta_path": dirpath,
            "local": bool(carpeta.get("local")), "tipo": clas["tipo"], "tipo_label": TIPO_LABEL[clas["tipo"]],
            "principal": principal, "principal_nombre": clas.get("principal"),
            "bytes": int(st.st_size), "tam": fmt_bytes(int(st.st_size)), "mtime_ts": float(st.st_mtime),
            "mtime": mt.strftime("%d/%m/%Y %H:%M"),
            "edad_dias": max(0, (datetime.now(_TZ) - mt).days),
            "datos": _ext_efectiva(nombre) in _EXT_DATOS}


def _listar(dirpath: str) -> List[str]:
    try:
        with os.scandir(dirpath) as it:
            nombres = [e.name for e in it if e.is_file(follow_symlinks=False)]
    except OSError as exc:
        logger.info("[copias] no pude listar %s (%s)", dirpath, exc)
        return []
    if len(nombres) > _MAX_POR_CARPETA:
        logger.info("[copias] %s tiene %d archivos — se escanean los %d más nuevos",
                    dirpath, len(nombres), _MAX_POR_CARPETA)

        def _mt(n: str) -> float:
            try:
                return os.stat(os.path.join(dirpath, n)).st_mtime
            except OSError:
                return 0.0
        nombres = sorted(nombres, key=_mt, reverse=True)[:_MAX_POR_CARPETA]
    return nombres


def escanear(solo: Optional[Tuple[str, ...]] = None) -> List[Dict[str, Any]]:
    """Todas las copias de las carpetas (`solo` = labels a incluir). listdir +
    stat: µs por archivo, sin abrir nada."""
    out: List[Dict[str, Any]] = []
    for c in carpetas():
        if solo and c["label"] not in solo:
            continue
        dirs = [c["path"]]
        if c["recursivo"]:
            try:
                with os.scandir(c["path"]) as it:
                    dirs += sorted(e.path for e in it if e.is_dir(follow_symlinks=False))
            except OSError:
                pass
        for d in dirs:
            nombres = _listar(d)
            for n in nombres:
                clas = clasificar(n, nombres)
                if clas is None:
                    continue
                e = _entrada(c, d, n, clas)
                if e is not None:
                    out.append(e)
    out.sort(key=lambda e: (e["carpeta"], e["principal_nombre"] or "~", -e["mtime_ts"]))
    return out


# ── estadísticas de un archivo (a pedido, cacheadas) ──────────────────────
def _firma(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None


def _stats_frame(df: Any) -> Tuple[Dict[str, Any], Optional[Set[date]]]:
    import pandas as pd
    out: Dict[str, Any] = {"filas": int(len(df))}
    fechas: Optional[Set[date]] = None
    col = "fecha_hoy" if "fecha_hoy" in df.columns else ("fecha" if "fecha" in df.columns else None)
    if col:
        f = pd.to_datetime(df[col], errors="coerce").dropna().dt.date
        fechas = set(f.tolist())
        out["ruedas"] = len(fechas)
        if fechas:
            out["desde"] = min(fechas).strftime("%d/%m/%Y")
            out["hasta"] = max(fechas).strftime("%d/%m/%Y")
        if "Price Source" in df.columns:
            from backend.services.historico_writer import PRICE_SOURCE_RC
            out["reales"] = int(df["Price Source"].astype(str).str.strip().ne(PRICE_SOURCE_RC).sum())
    if "ticker" in df.columns:
        out["tickers"] = int(df["ticker"].nunique())
    elif "symbol" in df.columns:
        out["simbolos"] = int(df["symbol"].nunique())
    return out, fechas


def _ext_efectiva(path: str) -> str:
    """Extensión del archivo ORIGINAL: un `.xlsx.corrupto-…` o `.parquet.bak-…`
    se lee como lo que era."""
    nombre = os.path.basename(path)
    for rx in (_RE_TMP, _RE_CORRUPTO, _RE_BAK):
        m = rx.match(nombre)
        if m:
            nombre = m.group("base")
            break
    return os.path.splitext(nombre)[1].lower()


def _stats_leer(path: str) -> Tuple[Dict[str, Any], Optional[Set[date]]]:
    low = _ext_efectiva(path)
    if low.endswith(".parquet"):
        import pandas as pd
        try:
            df = pd.read_parquet(path, columns=["fecha_hoy", "Price Source"])
        except Exception:  # noqa: BLE001 — otro esquema (acciones, particiones): completo
            df = pd.read_parquet(path)
        return _stats_frame(df)
    if low.endswith((".xlsx", ".xlsm")):
        import pandas as pd
        cols = list(pd.read_excel(path, nrows=0).columns)
        quiero = [c for c in ("fecha_hoy", "fecha", "Price Source", "ticker", "symbol") if c in cols]
        df = pd.read_excel(path, usecols=quiero) if quiero else pd.read_excel(path, usecols=[0])
        if not quiero:
            return {"filas": int(len(df)), "columnas": len(cols)}, None
        return _stats_frame(df)
    if low.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return {"entradas": len(raw)}, None
        if isinstance(raw, list):
            return {"entradas": len(raw)}, None
        return {}, None
    if low.endswith(".jsonl"):
        n = 0
        with open(path, "rb") as f:
            for _ in f:
                n += 1
        return {"lineas": n}, None
    return {}, None


def stats_de(path: str, solo_cache: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[Set[date]]]:
    """Estadísticas de un archivo (filas, ruedas, desde/hasta, reales…) con
    cache por (mtime, tamaño). Un archivo ilegible devuelve {"error": …};
    `solo_cache` devuelve (None, None) en vez de leer un archivo no revisado."""
    firma = _firma(path)
    if firma is None:
        return {"error": "no existe"}, None
    with _lock:
        c = _STATS.get(path)
        if c and c[0] == firma:
            return dict(c[1]), c[2]
    if solo_cache:
        return None, None
    try:
        st, fechas = _stats_leer(path)
    except Exception as exc:  # noqa: BLE001
        st, fechas = {"error": f"{exc.__class__.__name__}: {str(exc)[:120]}"}, None
    with _lock:
        if len(_STATS) >= _MAX_STATS:
            _STATS.clear()
        _STATS[path] = (firma, dict(st), fechas)
    return st, fechas


def _fmt_ruedas(fechas: List[date], n: int = 6) -> str:
    s = ", ".join(d.strftime("%d/%m") for d in fechas[:n])
    return s + (f" (+{len(fechas) - n})" if len(fechas) > n else "")


def _analizar_entrada(e: Dict[str, Any], solo_cache: bool = False) -> None:
    """Completa `e` con sus stats, las del principal y el veredicto. Con
    `solo_cache` no lee nada: lo no revisado queda con veredicto None."""
    e["stats"] = None
    e["veredicto"] = None
    e["aporta"] = None
    e["ruedas_extra"] = []
    e["ruedas_extra_fmt"] = ""
    e["mas_reciente"] = None
    e["mas_filas"] = None
    e["incorporable"] = False
    if e["tipo"] == "temporal":
        if time.time() - float(e.get("mtime_ts") or 0) < _TMP_MIN_EDAD_S:
            # Recién escrito: puede ser un writer a punto de hacer os.replace.
            e["aporta"] = None
            e["veredicto"] = "temporal reciente (posible escritura en curso): no borrar todavía"
        else:
            e["aporta"] = False
            e["veredicto"] = "temporal de una escritura cortada: no sirve, se puede borrar"
        return
    st, fechas = stats_de(e["path"], solo_cache)
    if st is None:
        return
    e["stats"] = st
    if st.get("error"):
        e["veredicto"] = f"ilegible ({st['error']})"
        if e["tipo"] == "corrupto":
            e["veredicto"] = "apartado por ilegible; sigue ilegible — se puede borrar"
            e["aporta"] = False
        return
    p = e.get("principal")
    if not p:
        e["veredicto"] = "sin principal al lado (revisar a mano)"
        return
    pst, pfechas = stats_de(p, solo_cache)
    if pst is None:
        return
    e["principal_stats"] = pst
    try:
        e["mas_reciente"] = e["mtime_ts"] > os.stat(p).st_mtime
    except OSError:
        pass
    if "filas" in st and "filas" in pst:
        e["mas_filas"] = st["filas"] > pst["filas"]
    if fechas is None or pfechas is None:
        if pst.get("error"):
            e["veredicto"] = f"la principal está ilegible ({pst['error']}): NO borrar esta copia sin revisar"
        elif "filas" in st and "filas" in pst:
            e["veredicto"] = (f"{st['filas']} vs {pst['filas']} filas de la principal; sin fechas para comparar"
                              + (" · más reciente que la principal" if e["mas_reciente"] else ""))
        else:
            e["veredicto"] = "sin datos comparables (revisar a mano)" + (
                " · más reciente que la principal" if e["mas_reciente"] else "")
        return
    extra = sorted(fechas - pfechas)
    e["ruedas_extra"] = [d.isoformat() for d in extra]
    e["ruedas_extra_fmt"] = _fmt_ruedas(extra)
    menos = len(pfechas - fechas)
    if extra:
        e["aporta"] = True
        e["incorporable"] = _incorporable(e)
        e["veredicto"] = (f"aporta {len(extra)} rueda{'s' if len(extra) != 1 else ''} que la principal no tiene "
                          f"({e['ruedas_extra_fmt']})" + (f"; le faltan {menos} de la principal" if menos else "")
                          + (" · más reciente" if e["mas_reciente"] else ""))
    else:
        mas_filas = (st.get("filas") or 0) > (pst.get("filas") or 0)
        mas_reales = (st.get("reales") or 0) > (pst.get("reales") or 0)
        if mas_filas or mas_reales:
            # Mismas RUEDAS que la principal pero MÁS filas/reales: puede traer
            # instrumentos nuevos o correcciones dentro de esas fechas que la
            # principal no tiene (A01). No alcanza con comparar fechas → NO es
            # borrable en lote; queda para revisar/incorporar a mano.
            e["aporta"] = None
            det = f"{st.get('filas', '?')} vs {pst.get('filas', '?')} filas"
            if mas_reales:
                det += f" ({st.get('reales')} vs {pst.get('reales')} reales)"
            e["veredicto"] = (f"mismas ruedas que la principal pero {det} — puede tener instrumentos "
                              "o correcciones que la principal no: revisar a mano, NO borrar en lote"
                              + (" · más reciente" if e["mas_reciente"] else ""))
        else:
            e["aporta"] = False
            e["veredicto"] = (f"no aporta: la principal tiene sus {st.get('ruedas', 0)} ruedas"
                              + (f" y {menos} más" if menos else "")
                              + (" (aunque esta copia es más reciente)" if e["mas_reciente"] else ""))


def _base_de(principal: str) -> Optional[Tuple[str, str]]:
    """(tipo de base, path al que se escribe) si el principal es una de las
    bases que sabemos mergear: px/tasas (xlsx o su espejo), FX, acciones."""
    from backend.services.historico_writer import ACCIONES_FILENAME, FX_FILENAME, HIST_FILENAME
    n = os.path.basename(principal)
    d = os.path.dirname(principal)
    stem_hist = os.path.splitext(HIST_FILENAME)[0]
    stem_fx = os.path.splitext(FX_FILENAME)[0]
    if n in (HIST_FILENAME, stem_hist + ".parquet"):
        return "px_tasas", os.path.join(d, HIST_FILENAME)
    if n in (FX_FILENAME, stem_fx + ".parquet"):
        return "fx", os.path.join(d, FX_FILENAME)
    if n == ACCIONES_FILENAME:
        return "acciones", os.path.join(d, ACCIONES_FILENAME)
    return None


def _incorporable(e: Dict[str, Any]) -> bool:
    return bool(e.get("principal") and e.get("datos") and _base_de(e["principal"]))


def analizar(entradas: Optional[List[Dict[str, Any]]] = None, solo_cache: bool = False) -> List[Dict[str, Any]]:
    """Escaneo + stats + veredicto de cada copia (lee los archivos: segundos
    con copias Excel grandes; cacheado por mtime/tamaño). Correr en el
    executor. `solo_cache` = sólo lo ya revisado (el GET de la tarjeta)."""
    if entradas is None:
        entradas = escanear()
    for e in entradas:
        _analizar_entrada(e, solo_cache)
    return entradas


def agrupar(entradas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """[{carpeta, principal, principal_nombre, principal_stats, copias}] en el
    orden del escaneo — lo que la tarjeta pinta."""
    grupos: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for e in entradas:
        key = (e["carpeta"], e.get("principal") or "")
        g = grupos.get(key)
        if g is None:
            g = grupos[key] = {"carpeta": e["carpeta"], "carpeta_path": e["carpeta_path"],
                               "principal": e.get("principal"), "principal_nombre": e.get("principal_nombre"),
                               "principal_stats": e.get("principal_stats"), "copias": []}
        if g.get("principal_stats") is None and e.get("principal_stats"):
            g["principal_stats"] = e["principal_stats"]
        g["copias"].append(e)
    return list(grupos.values())


# ── acciones del superuser ─────────────────────────────────────────────────
def _validar_copia(path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Re-chequeo al momento de actuar: adentro de una carpeta escaneada y
    clasificado como copia AHORA (nunca un principal, nunca afuera)."""
    if not path or not os.path.isfile(path):
        return None, "el archivo ya no existe"
    carp = None
    for c in carpetas():
        if _dentro_de(path, c["path"]):
            carp = c
            break
    if carp is None:
        return None, "el archivo no está en una carpeta de la app"
    d = os.path.dirname(path)
    nombre = os.path.basename(path)
    clas = clasificar(nombre, _listar(d))
    if clas is None:
        return None, "no es una copia (es un archivo propio de la app o de las bases)"
    e = _entrada(carp, d, nombre, clas)
    if e is None:
        return None, "no pude leer el archivo"
    if e.get("tipo") == "temporal" and time.time() - float(e.get("mtime_ts") or 0) < _TMP_MIN_EDAD_S:
        return None, "temporal reciente (posible escritura en curso): no se borra todavía"
    return e, None


def borrar(path: str, quien: str = "") -> Dict[str, Any]:
    e, err = _validar_copia(path)
    if err:
        return {"ok": False, "error": err, "path": path}
    assert e is not None
    try:
        os.remove(path)
    except OSError as exc:
        return {"ok": False, "error": f"no pude borrar: {exc}", "path": path}
    with _lock:
        _STATS.pop(path, None)
    logger.warning("[copias] %s borró %s (%s, %s bytes, %s) de %s", quien or "superuser", e["nombre"],
                   e["tipo"], f"{e['bytes']:,}".replace(",", "."), e["mtime"], e["carpeta_path"])
    return {"ok": True, "path": path, "nombre": e["nombre"], "bytes": e["bytes"], "tipo": e["tipo"]}


def borrar_inutiles(quien: str = "") -> Dict[str, Any]:
    """Borra las copias que el análisis dio como `aporta == False` (datos ya
    contenidos en la principal, temporales, apartados ilegibles). Lo demás no
    se toca."""
    out: Dict[str, Any] = {"borradas": [], "errores": [], "bytes": 0}
    for e in analizar():
        if e.get("aporta") is not False:
            continue
        r = borrar(e["path"], quien)
        if r.get("ok"):
            out["borradas"].append(e["nombre"])
            out["bytes"] += int(e["bytes"])
        else:
            out["errores"].append(f"{e['nombre']}: {r.get('error')}")
    return out


def _leer_copia(path: str) -> Any:
    import pandas as pd
    if _ext_efectiva(path) == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_excel(path)
    if "fecha_hoy" in df.columns:
        df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"], errors="coerce").dt.date
        df = df[df["fecha_hoy"].notna()]
    return df


def incorporar(path: str, quien: str = "") -> Dict[str, Any]:
    """Las ruedas que SÓLO están en la copia pasan a la base principal (px/tasas,
    FX o acciones) por el camino de escritura de siempre. La copia queda tal
    cual (borrarla es otro click)."""
    import pandas as pd
    from backend.services import historico_writer as hw

    e, err = _validar_copia(path)
    if err:
        return {"ok": False, "error": err}
    assert e is not None
    if not e.get("principal") or not e.get("datos"):
        return {"ok": False, "error": "sólo se incorporan copias de una base con fechas (px/tasas, FX, acciones)"}
    base = _base_de(e["principal"])
    if base is None:
        return {"ok": False, "error": f"{e['principal_nombre']} no es una base que sepa mergear "
                                      "(px/tasas, historico_fx o historico_acciones)"}
    tipo, destino = base
    try:
        df = _leer_copia(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"no pude leer la copia: {exc}"}
    if "fecha_hoy" not in df.columns or not len(df):
        return {"ok": False, "error": "la copia no tiene columna fecha_hoy o está vacía"}
    fechas_copia = set(df["fecha_hoy"].tolist())
    if tipo == "px_tasas":
        resumen = hw._resumen_base(destino)
        faltan = {d for d in fechas_copia if d not in resumen}
        # ruedas que la base tiene sólo como RC (reconstruidas) y la copia trae reales
        if "Price Source" in df.columns:
            reales = df[df["Price Source"].astype(str).str.strip().ne(hw.PRICE_SOURCE_RC)]
            degradadas = {d for d, (n, r) in resumen.items() if n > 0 and r == 0}
            faltan |= set(reales["fecha_hoy"].tolist()) & degradadas
        sub = df[df["fecha_hoy"].isin(faltan)]
        if not len(sub):
            return {"ok": False, "error": "la copia no tiene ruedas que le falten a la base"}
        from backend.services import espejo
        sub = espejo.normalizar_numericas(sub, f"copia {e['nombre']}")
        res = hw.append_and_save(sub, destino, incluir_journal=True, ignorar_regresion=True)
        ruedas = sorted(faltan)
        logger.warning("[copias] %s incorporó %d rueda(s) (%s) desde %s a la base px/tasas: %d filas",
                       quien or "superuser", len(ruedas), _fmt_ruedas(ruedas), e["nombre"], len(sub))
        return {"ok": True, "tipo": tipo, "ruedas": [d.isoformat() for d in ruedas], "ruedas_fmt": _fmt_ruedas(ruedas),
                "filas": int(len(sub)), "total_rows": res.get("total_rows")}
    if tipo == "fx":
        prev = None
        from backend.services import fx_hist
        src = fx_hist._path()
        if src:
            try:
                prev = pd.read_parquet(src) if src.endswith(".parquet") else pd.read_excel(src)
                prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"], errors="coerce").dt.date
                prev = prev[prev["fecha_hoy"].notna()]
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"no pude leer el historial FX actual ({exc}); no escribo encima"}
        tiene = set(prev["fecha_hoy"].tolist()) if prev is not None else set()
        sub = df[~df["fecha_hoy"].isin(tiene)]
        if not len(sub):
            return {"ok": False, "error": "la copia no tiene días que le falten al historial FX"}
        todo = pd.concat([prev, sub], ignore_index=True) if prev is not None else sub.copy()
        todo = todo.sort_values("fecha_hoy").reset_index(drop=True)
        hw.escribir_fx(todo, destino)
        fx_hist.refresh()
        ruedas = sorted(set(sub["fecha_hoy"].tolist()))
        logger.warning("[copias] %s incorporó %d día(s) (%s) desde %s al historial FX", quien or "superuser",
                       len(ruedas), _fmt_ruedas(ruedas), e["nombre"])
        return {"ok": True, "tipo": tipo, "ruedas": [d.isoformat() for d in ruedas], "ruedas_fmt": _fmt_ruedas(ruedas),
                "filas": int(len(sub)), "total_rows": int(len(todo))}
    # acciones: entran sólo las (fecha, ticker) que el principal no tiene
    if "ticker" not in df.columns:
        return {"ok": False, "error": "la copia no tiene columna ticker"}
    tiene: Set[tuple] = set()
    if os.path.isfile(destino):
        try:
            prev = pd.read_parquet(destino, columns=["fecha_hoy", "ticker"])
            prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"], errors="coerce").dt.date
            tiene = set(zip(prev["fecha_hoy"], prev["ticker"]))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"no pude leer el historial de acciones actual ({exc}); no escribo encima"}
    keys = list(zip(df["fecha_hoy"], df["ticker"]))
    sub = df[[k not in tiene for k in keys]]
    if not len(sub):
        return {"ok": False, "error": "la copia no tiene filas (fecha, ticker) que le falten al historial de acciones"}
    res = hw.append_acciones(sub, destino, gana_previo=True)
    from backend.services import acciones_hist
    acciones_hist.refresh()
    ruedas = sorted(set(sub["fecha_hoy"].tolist()))
    logger.warning("[copias] %s incorporó %d fila(s) de acciones (%s) desde %s", quien or "superuser",
                   len(sub), _fmt_ruedas(ruedas), e["nombre"])
    return {"ok": True, "tipo": tipo, "ruedas": [d.isoformat() for d in ruedas], "ruedas_fmt": _fmt_ruedas(ruedas),
            "filas": int(len(sub)), "total_rows": res.get("filas")}


def resumen_bases() -> List[str]:
    """Para base_check: nombres de las copias que hay al lado de las bases y
    en cierres/ (sin abrir nada)."""
    return [f"{e['nombre']} [{e['tipo']}]" + (f" ← {e['principal_nombre']}" if e.get("principal_nombre") else "")
            for e in escanear(solo=("bases", "cierres"))]
