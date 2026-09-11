"""Autoguardado de la base histórica px/tasas al cierre de rueda.

Si la app está corriendo al cierre (17:01 hora BA por default), arma las
filas del día desde el estado vivo del proceso — el mismo store + métricas
que muestra la pestaña Curvas — y las appendea al Excel/Parquet que mantiene
`bymaapi.py`, con el MISMO esquema y dedup (symbol, Código, fecha_hoy;
keep last). O sea: correr bymaapi a mano sigue funcionando igual y, si ambos
guardan el mismo día, gana el que guardó último, sin duplicar filas.

Guards para no ensuciar la base:
  - fin de semana → skip;
  - feriado / sin rueda: exige un mínimo de bonos con OPERACIONES DE HOY
    (last_ts parsea a hoy) — un feriado sin ticks no llega al mínimo aunque
    el store tenga cierres pegajosos del día anterior;
  - si la base ya tiene filas de hoy (chequeo rápido vía parquet) → skip.

El guardado manual (`save_today(force=True)`) saltea los guards: es el botón
"Guardar base de hoy" de Históricos, sólo superuser.

SOLIDEZ (tras la semana perdida 25-28/08/26, base clavada en el 24):
  1. JOURNAL LOCAL por día: cada máquina guarda las filas del cierre en una
     carpeta local propia (fuera de OneDrive → sin locks ni copias de
     conflicto). El día queda CAPTURADO aunque la base compartida falle.
  2. CATCH-UP: al arrancar la app (y en cada guardado) se consolidan a la
     base los días del journal que le falten — un cierre perdido se
     auto-repara solo apenas una máquina que lo tenga vuelve a consolidar.
  3. REINTENTOS: el write de la base reintenta ante un xlsx lockeado
     (OneDrive sincronizando / archivo abierto en Excel), y el autosave de
     las 17:01 reintenta cada 10 min hasta ~90 min si el guardado falló.
  4. MULTI-INSTANCIA: dejá HISTORICO_AUTOSAVE=1 en TODAS las máquinas (el
     journal local es gratis y es la red de seguridad); en las secundarias
     poné HISTORICO_BASE_WRITER=0 para que NO escriban la base compartida
     (evita los conflictos de OneDrive) — el botón manual la escribe igual.
  5. VISIBILIDAD: /admin/salud muestra última fecha de la base, atraso en
     días hábiles y journal pendiente (`estado()`).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("backend.historico_writer")

HIST_FILENAME = "Delta - historico_byma_px_tasas.xlsx"
_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Columnas obligatorias (mismas que el dropna de bymaapi.guardar_excel).
_REQUIRED = ["Last Price", "TIREA", "TNA", "TEM", "Paridad", "Duration"]


def _now() -> datetime:
    """Hora actual en BA (helper monkeypatcheable en tests)."""
    return datetime.now(_TZ)


def _fecha_dato(ts: Any) -> Optional[date]:
    """Fecha (BA) de un timestamp del feed: epoch millis ('1751833623000')
    o ISO. None si no parsea."""
    if ts in (None, ""):
        return None
    s = str(ts).strip()
    try:
        if s.isdigit() and len(s) >= 12:
            return datetime.fromtimestamp(int(s) / 1000.0, tz=_TZ).date()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ).date()
    except (ValueError, OSError, OverflowError):
        return None


def build_rows(plazo: str = "24hs") -> "Any":
    """Filas del día para TODOS los códigos de las curvas (soberanos +
    corporativos), con el mismo precio de referencia que la tabla de Curvas:
    last si operó, si no cierre previo. Devuelve un DataFrame con el esquema
    de la base de bymaapi (fracciones numéricas, no % strings)."""
    import pandas as pd

    from backend.services import curves, marketdata_store, pricing
    from backend.services import fx as fx_svc
    from backend.services import symbols as syms

    store = marketdata_store.get_store()
    seen: set = set()
    rows: List[Dict[str, Any]] = []
    hoy = _now().date()
    # Mismo settle que la tabla de Curvas (CI = hoy, 24hs = t+1): comparte el
    # cache de métricas y la TIR guardada coincide con la de pantalla.
    settle = pricing.settlement_date_str(plazo)
    fx = None   # lazy: sólo si aparece una especie pesos de un hard-dollar
    for codes in curves.build_curve_codes().values():
        for code in codes or []:
            if code in seen:
                continue
            seen.add(code)
            symbol = syms.md_symbol(code, plazo)
            snap = store.get(symbol)
            if snap is None:
                continue
            if snap.last is not None:
                ref_px, source, ts = snap.last, "LA", snap.last_ts
            elif snap.close is not None:
                ref_px, source, ts = snap.close, "CL", snap.close_ts
            else:
                continue
            # Especie en PESOS (o referencia clean) de un bono hard-dollar
            # (BPCVO/GYC5O/…): la base guardaba TIREA/paridad calculadas sobre
            # el precio en ARS crudo (GYC5O a 150.000 → TIR -100%, paridad
            # ~1500) y contaminaba el histórico todos los días. Mismo camino
            # que Curvas: ficha NATIVA (…D/…C) + precio ÷ FX de la moneda de
            # pago. El precio guardado sigue siendo el de pantalla (ARS).
            meta = pricing.bond_meta(code) or {}
            calc, px = code, ref_px
            if meta.get("moneda") in ("USD", "USB") and code[-1:] not in ("C", "D"):
                if fx is None:
                    fx = fx_svc.get_fx(plazo)
                calc = pricing.native_dollar_code(code) or code
                px = fx_svc.normalize_price(ref_px, "ARS", meta.get("moneda"), fx)
                if px is None:
                    continue   # sin FX no hay TIR honesta — mejor sin fila hoy
            m = pricing.metrics_for_market_price(calc, px, settle)
            if not m:
                continue
            var = None
            try:
                if snap.last is not None and snap.close not in (None, 0):
                    var = snap.last / snap.close - 1.0
            except (TypeError, ZeroDivisionError):
                var = None
            rows.append({
                "symbol": symbol, "Código": code,
                "Last Price": ref_px, "Close Price": snap.close, "Variación %": var,
                "TIREA": m.get("tirea"), "TNA": m.get("tna"), "TEM": m.get("tem"),
                "Paridad": m.get("paridad"), "Duration": m.get("duration"),
                "Price Source": source, "Price Date": ts,
                "fecha_hoy": hoy,
            })
    return pd.DataFrame(rows)


def operados_en_store() -> int:
    """Bonos de las curvas con una OPERACIÓN de hoy en el store (last_ts de
    hoy). El mismo guard de `save_today` pero sin armar filas ni TIRs (~ms):
    la captura headless lo sondea para saber cuándo el feed ya mandó los
    snapshots del día."""
    from backend.services import curves, marketdata_store
    from backend.services import symbols as syms

    store = marketdata_store.get_store()
    hoy = _now().date()
    vistos: set = set()
    n = 0
    for codes in curves.build_curve_codes().values():
        for code in codes or []:
            if code in vistos:
                continue
            vistos.add(code)
            snap = store.get(syms.md_symbol(code, "24hs"))
            if snap is not None and snap.last is not None and _fecha_dato(snap.last_ts) == hoy:
                n += 1
    return n


def operados_hoy(df: "Any") -> int:
    """Cuántas filas tienen una OPERACIÓN de hoy (Price Source LA con fecha de
    hoy). Los cierres pegajosos de ayer no cuentan → un feriado da ~0."""
    if df is None or len(df) == 0:
        return 0
    hoy = _now().date()
    n = 0
    for src, ts in zip(df.get("Price Source", []), df.get("Price Date", [])):
        if src == "LA" and _fecha_dato(ts) == hoy:
            n += 1
    return n


# ── Journal LOCAL por día (red de seguridad, fuera de OneDrive) ────────────
def journal_dir() -> str:
    """Carpeta local POR MÁQUINA para el journal diario. Override:
    HISTORICO_JOURNAL_DIR. Default: %LOCALAPPDATA%\\bonos\\journal (Windows) /
    ~/.local/share/bonos/journal (mac/linux) — nunca dentro de OneDrive."""
    d = os.getenv("HISTORICO_JOURNAL_DIR")
    if not d:
        base = os.getenv("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
        d = os.path.join(base, "bonos", "journal")
    os.makedirs(d, exist_ok=True)
    return d


def write_journal(df: "Any") -> str:
    """Parquet del día en el journal local (atómico; pisa el del mismo día).
    Es lo PRIMERO que se guarda al cierre: sin OneDrive en el medio no hay
    locks ni conflictos, el día queda capturado pase lo que pase con la base."""
    path = os.path.join(journal_dir(), f"px_tasas_{_now().date():%Y%m%d}.parquet")
    mirror = df.copy()
    for col in ("symbol", "Código", "Price Source", "Price Date"):
        if col in mirror.columns:
            mirror[col] = mirror[col].astype("string")
    tmp = path + ".tmp"
    mirror.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def _journal_days() -> Dict[date, str]:
    """{fecha: path} de los días guardados en el journal local."""
    out: Dict[date, str] = {}
    try:
        nombres = os.listdir(journal_dir())
    except OSError:
        return out
    for fn in nombres:
        m = re.fullmatch(r"px_tasas_(\d{8})\.parquet", fn)
        if m:
            try:
                out[datetime.strptime(m.group(1), "%Y%m%d").date()] = \
                    os.path.join(journal_dir(), fn)
            except ValueError:
                continue
    return out


def _prune_journal(max_dias: int = 90) -> None:
    """Higiene: journal más viejo que `max_dias` se borra (la base ya lo tiene
    hace rato; el dedup protege si no)."""
    limite = _now().date() - timedelta(days=max_dias)
    for dia, path in _journal_days().items():
        if dia < limite:
            try:
                os.remove(path)
            except OSError:
                pass
    for dia in _sin_rueda_days():
        if dia < limite:
            try:
                os.remove(_sin_rueda_path(dia))
            except OSError:
                pass


def _fechas_base(xlsx_path: str) -> set:
    """Fechas presentes en la base según el espejo parquet (ms, sin abrir el
    Excel). Sin espejo → set(): la consolidación procede y el dedup protege."""
    pq = os.path.splitext(xlsx_path)[0] + ".parquet"
    if not os.path.isfile(pq):
        return set()
    try:
        import pandas as pd
        f = pd.read_parquet(pq, columns=["fecha_hoy"])["fecha_hoy"]
        return set(pd.to_datetime(f).dt.date)
    except Exception:  # noqa: BLE001
        return set()


_fechas_cache: tuple = ()      # (parquet, mtime_ns, size, fechas)


def _fechas_base_cached(xlsx_path: str) -> set:
    """Como _fechas_base pero cacheado por (mtime, size) del espejo parquet:
    os.stat por llamada (~µs) y la lectura real UNA vez por cambio del archivo.
    Es lo que sondea el chip de la topbar (1 req/min por pestaña)."""
    global _fechas_cache
    pq = os.path.splitext(xlsx_path)[0] + ".parquet"
    try:
        st = os.stat(pq)
    except OSError:
        return set()
    key = (pq, st.st_mtime_ns, st.st_size)
    c = _fechas_cache
    if c and c[:3] == key:
        return c[3]
    fechas = _fechas_base(xlsx_path)
    _fechas_cache = key + (fechas,)
    return fechas


def _hora_archivo(xlsx_path: str) -> Optional[str]:
    """HH:MM (BA) del último write del espejo parquet — la hora a la que se
    guardó el cierre, válida también en las máquinas que sólo leen la base."""
    pq = os.path.splitext(xlsx_path)[0] + ".parquet"
    try:
        return datetime.fromtimestamp(os.path.getmtime(pq), _TZ).strftime("%H:%M")
    except OSError:
        return None


# ── Calendario hábil (feriados AR vía dias_habiles; sin el módulo, sólo finde) ─
def _es_habil(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    try:
        import dias_habiles
        return d not in dias_habiles.ar_holidays
    except Exception:  # noqa: BLE001 — sin calendario: aproximación lun-vie
        return True


def _hhmm(s: str) -> tuple:
    try:
        hh, mm = (int(x) for x in str(s).split(":", 1))
        return hh, mm
    except ValueError:
        return 17, 1


def _ultimo_cierre_esperado(ahora: datetime, hhmm: str, excluir: Optional[set] = None) -> date:
    """Último día hábil cuyo cierre YA debería estar en la base: hoy si pasó la
    hora del autosave, si no el hábil anterior. Feriados y días marcados
    'sin rueda' por el autosave no cuentan."""
    hh, mm = _hhmm(hhmm)
    d = ahora.date()
    if (ahora.hour, ahora.minute) < (hh, mm):
        d -= timedelta(days=1)
    while not _es_habil(d) or (excluir and d in excluir):
        d -= timedelta(days=1)
    return d


def _atraso_habiles(ultima: Optional[date], esperado: date, excluir: Optional[set] = None) -> Optional[int]:
    """Ruedas que le faltan a la base entre su última fecha y el cierre esperado."""
    if ultima is None:
        return None
    n, d = 0, ultima
    while d < esperado:
        d += timedelta(days=1)
        if _es_habil(d) and not (excluir and d in excluir):
            n += 1
    return n


# ── Marcas locales "sin rueda" ──────────────────────────────────────────────
# Cuando el autosave encuentra un día hábil sin operaciones (feriado que el
# calendario no tiene / mercado cerrado) lo marca en el journal local: el
# estado del cierre no reclama ese día como faltante en esta máquina.
def _sin_rueda_path(d: date) -> str:
    return os.path.join(journal_dir(), f"sin_rueda_{d:%Y%m%d}")


def _marcar_sin_rueda(d: date) -> None:
    try:
        with open(_sin_rueda_path(d), "w", encoding="utf-8") as f:
            f.write("sin rueda\n")
    except OSError:
        pass


def _sin_rueda_days() -> set:
    out: set = set()
    try:
        nombres = os.listdir(journal_dir())
    except OSError:
        return out
    for fn in nombres:
        m = re.fullmatch(r"sin_rueda_(\d{8})", fn)
        if m:
            try:
                out.add(datetime.strptime(m.group(1), "%Y%m%d").date())
            except ValueError:
                continue
    return out


def estado_cierre() -> Dict[str, Any]:
    """Estado del cierre para el chip de la topbar, el banner y /admin/salud.
    Costo ~50 µs (stat + listdir + fechas); nunca abre el Excel.

    estado: ok | pendiente | capturado | falta | sin_base
      ok        → el último cierre esperado está en la base compartida
      pendiente → pasó la hora del autosave, hoy no está, ventana de reintentos
      capturado → esta máquina lo journaleó pero la base compartida no lo tiene
      falta     → el cierre esperado no está (¿app cerrada a las 17:01?)
      sin_base  → carpeta Delta Bases no montada (chip oculto)"""
    from backend.config import settings
    from backend.services import deltapaths

    ahora = _now()
    hoy = ahora.date()
    hh, mm = _hhmm(settings.historico_autosave_hhmm)
    out: Dict[str, Any] = {"estado": "sin_base", "texto": "", "detalle": "",
                           "writer": bool(settings.historico_base_writer),
                           "autosave": bool(settings.historico_autosave),
                           "hhmm": f"{hh:02d}:{mm:02d}", "hoy": hoy.isoformat()}
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        return out
    xlsx = os.path.join(hist_dir, HIST_FILENAME)
    fechas = _fechas_base_cached(xlsx)
    ultima = max(fechas) if fechas else None
    sin_rueda = _sin_rueda_days()
    esperado = _ultimo_cierre_esperado(ahora, settings.historico_autosave_hhmm, sin_rueda)
    journal = _journal_days()
    atraso = _atraso_habiles(ultima, esperado, sin_rueda)
    r = (_autosave.last_result or {}) if _autosave is not None else {}
    out.update({"ultima": ultima.isoformat() if ultima else None,
                "esperado": esperado.isoformat(), "esperado_fmt": esperado.strftime("%d/%m/%Y"),
                "atraso": atraso, "hoy_en_base": hoy in fechas, "hoy_en_journal": hoy in journal,
                "error": r.get("error")})
    dm = esperado.strftime("%d/%m")
    if esperado in fechas:
        out["estado"] = "ok"
        if esperado == hoy:
            hora = _hora_archivo(xlsx) or r.get("hora")
            out["texto"] = "✓ cierre hoy" + (f" {hora}" if hora else "")
            out["detalle"] = ("Base histórica con el cierre de hoy"
                              + (f" (guardado {hora})" if hora else "")
                              + (f" · {r['rows']} filas" if r.get("rows") else ""))
        else:
            out["texto"] = f"✓ cierre {dm}"
            quien = (f"hoy se guarda solo a las {hh:02d}:{mm:02d} — dejá la app abierta (o la captura programada)"
                     if out["autosave"] and out["writer"] else f"hoy lo guarda la PC writer a las {hh:02d}:{mm:02d}")
            out["detalle"] = f"Base histórica al día (último cierre {dm}); {quien}"
        return out
    if esperado in journal:
        out["estado"] = "capturado"
        out["texto"] = f"⏳ cierre {dm} capturado"
        out["detalle"] = ("Esta máquina guardó el journal local pero la base compartida todavía no lo "
                          "tiene (se consolida en el próximo guardado / al arrancar la app writer)")
        return out
    if esperado == hoy:
        mins = (ahora - ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)).total_seconds() / 60.0
        if mins <= 95 and out["autosave"]:
            out["estado"] = "pendiente"
            out["texto"] = "⏳ cierre pendiente"
            out["detalle"] = (f"El autosave de las {hh:02d}:{mm:02d} todavía no guardó "
                              "(reintenta cada 10 min hasta ~90 min)"
                              + (f" · último intento: {r['error']}" if r.get("error") else ""))
            return out
    out["estado"] = "falta"
    out["texto"] = f"⚠ falta cierre {dm}" + (f" (+{atraso - 1})" if atraso and atraso > 1 else "")
    out["detalle"] = (f"La base histórica no tiene el cierre del {dm}"
                      + (f" — atraso {atraso} ruedas" if atraso and atraso > 1 else "")
                      + (f" · último error: {r['error']}" if r.get("error")
                         else f" · ¿la app estaba cerrada a las {hh:02d}:{mm:02d}? "
                              "Programá la captura headless (python -m backend.tools.cierre)"))
    return out


# El read→concat→write de la base NO es reentrante: dos guardados a la vez
# (autosave 17:01 + botón manual, o doble click del botón — cada POST va a un
# thread distinto del executor) compartían el MISMO tmp determinístico y se
# pisaban (xlsx corrupto promovido a base, o lost update). El tmp+replace
# protege contra un CORTE, no contra concurrencia — esto sí.
_save_lock = threading.Lock()

# Backoff ante un xlsx lockeado (OneDrive sincronizando / abierto en Excel):
# 3 reintentos, después sube el error (el autosave reintenta a los 10 min).
_LOCK_ESPERAS = (2.0, 5.0, 15.0)


def append_and_save(df: "Any", xlsx_path: str, incluir_journal: bool = True) -> Dict[str, Any]:
    """Appendea `df` a la base (Excel + espejo Parquet) con la semántica de
    bymaapi.guardar_excel: concat con lo existente, dedup (symbol, Código,
    fecha_hoy) keep last, dropna de métricas, Proy por sufijo 'j'. Escritura
    atómica (tmp + replace) — un corte a mitad de escritura no corrompe la
    base — y SERIALIZADA (_save_lock) — dos guardados concurrentes tampoco.

    `df` puede ser None (consolidación pura). Con `incluir_journal`, mergea
    además los días del journal local que a la base le FALTEN — un cierre que
    la base se perdió se repara solo. Reintenta ante un xlsx lockeado."""
    import numpy as np
    import pandas as pd

    with _save_lock:
        for i in range(len(_LOCK_ESPERAS) + 1):
            try:
                return _append_and_save_locked(df, xlsx_path, np, pd, incluir_journal)
            except (PermissionError, OSError) as exc:
                if i == len(_LOCK_ESPERAS):
                    raise
                logger.warning("[historico_writer] base lockeada/inaccesible (%s) — "
                               "reintento en %.0f s", exc, _LOCK_ESPERAS[i])
                time.sleep(_LOCK_ESPERAS[i])
    raise RuntimeError("unreachable")            # pragma: no cover


def _leer_base(xlsx_path: str, pd) -> "Any":
    """Lee la base existente con AUTO-RECUPERACIÓN: si el xlsx está corrupto
    (OneDrive a mitad de sync, Excel que murió guardando, write viejo no
    atómico) pero el espejo parquet está sano, el corrupto se renombra a
    .corrupto-<fecha> (evidencia, nunca se borra) y la base sigue desde el
    espejo — el write de salida regenera un xlsx limpio. Sin espejo sano, el
    error sube con la instrucción de recuperación manual."""
    try:
        prev = pd.read_excel(xlsx_path, parse_dates=["fecha_hoy"])
        prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"]).dt.date
        return prev
    except Exception as exc_xlsx:  # noqa: BLE001 — BadZipFile/ValueError/etc.
        pq = os.path.splitext(xlsx_path)[0] + ".parquet"
        try:
            import pandas as _pd
            prev = _pd.read_parquet(pq)
            prev["fecha_hoy"] = _pd.to_datetime(prev["fecha_hoy"]).dt.date
        except Exception as exc_pq:  # noqa: BLE001
            raise RuntimeError(
                f"La base {xlsx_path} está ilegible ({exc_xlsx}) y el espejo "
                f"parquet tampoco se pudo leer ({exc_pq}). Recuperación manual: "
                "restaurar el xlsx desde el Historial de versiones de OneDrive."
            ) from exc_xlsx
        marca = _now().strftime("%Y%m%d-%H%M%S")
        respaldo = f"{xlsx_path}.corrupto-{marca}"
        try:
            os.replace(xlsx_path, respaldo)
        except OSError as exc_mv:
            raise RuntimeError(
                f"La base {xlsx_path} está corrupta pero no se pudo apartar "
                f"({exc_mv}) — ¿archivo abierto en Excel? Cerralo y reintentá."
            ) from exc_mv
        logger.warning("[historico_writer] base xlsx CORRUPTA (%s) — apartada como %s; "
                       "regenerando desde el espejo parquet (%d filas)",
                       exc_xlsx, respaldo, len(prev))
        return prev


def _append_and_save_locked(df: "Any", xlsx_path: str, np, pd,
                            incluir_journal: bool = True) -> Dict[str, Any]:
    prev = None
    if os.path.exists(xlsx_path):
        prev = _leer_base(xlsx_path, pd)

    frames = [prev] if prev is not None else []
    consolidados = 0
    if incluir_journal:
        en_base = set(prev["fecha_hoy"]) if prev is not None else set()
        hoy = _now().date()
        for dia, path in sorted(_journal_days().items()):
            # el día de HOY viene fresco en `df` (si hay); del journal entran
            # sólo los días que a la base le faltan
            if dia in en_base or (df is not None and len(df) and dia == hoy):
                continue
            try:
                jf = pd.read_parquet(path)
                jf["fecha_hoy"] = pd.to_datetime(jf["fecha_hoy"]).dt.date
                frames.append(jf)
                consolidados += 1
                logger.info("[historico_writer] consolidando %s desde el journal local", dia)
            except Exception as exc:  # noqa: BLE001 — un journal roto no frena la base
                logger.warning("[historico_writer] journal %s ilegible: %s", path, exc)
    if df is not None and len(df):
        frames.append(df)
    if not frames:
        return {"total_rows": 0, "xlsx": xlsx_path, "parquet": None, "consolidados": 0}
    df_final = pd.concat(frames, ignore_index=True)

    df_last = df_final.drop_duplicates(subset=["symbol", "Código", "fecha_hoy"], keep="last")
    df_last = df_last.dropna(subset=[c for c in _REQUIRED if c in df_last.columns])
    df_last = df_last.copy()
    df_last["Proy"] = np.where(df_last["Código"].astype(str).str.endswith("j"), 1, 0)

    # Excel no acepta datetimes tz-aware (mataría el guardado entero).
    for col in df_last.columns:
        if isinstance(df_last[col].dtype, pd.DatetimeTZDtype):
            df_last[col] = df_last[col].dt.tz_localize(None)

    tmp = xlsx_path + ".tmp.xlsx"
    df_last.to_excel(tmp, index=False)
    os.replace(tmp, xlsx_path)

    pq_path = os.path.splitext(xlsx_path)[0] + ".parquet"
    try:
        # Columnas de texto con tipos mixtos rompen pyarrow: al re-appendear,
        # read_excel devuelve 'Price Date' como int y el df nuevo trae str →
        # object mixto → ArrowTypeError. String dtype (con NA) las unifica.
        mirror = df_last.copy()
        for col in ("symbol", "Código", "Price Source", "Price Date"):
            if col in mirror.columns:
                mirror[col] = mirror[col].astype("string")
        tmp_pq = pq_path + ".tmp"
        mirror.to_parquet(tmp_pq, index=False)
        os.replace(tmp_pq, pq_path)
    except Exception as exc:  # noqa: BLE001 — el Excel ya quedó bien
        logger.warning("[historico_writer] espejo parquet no guardado: %s", exc)
        pq_path = None

    return {"total_rows": len(df_last), "xlsx": xlsx_path, "parquet": pq_path,
            "consolidados": consolidados}


def _ya_guardado_hoy(xlsx_path: str) -> bool:
    """Chequeo rápido vía el espejo parquet (ms). Sin parquet devolvemos False
    y seguimos: el dedup del append garantiza que no se duplique nada."""
    return _now().date() in _fechas_base(xlsx_path)


def consolidar_journal() -> Optional[Dict[str, Any]]:
    """Mergea a la base los días del journal local que le FALTEN, sin armar
    filas nuevas. Corre al ARRANCAR la app (catch-up): si la base se perdió
    un cierre que esta máquina sí capturó (app caída a las 17:01, xlsx
    lockeado, conflicto de OneDrive), se repara acá. None = nada para hacer."""
    from backend.config import settings
    from backend.services import deltapaths
    if not settings.historico_base_writer:
        return None
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        return None
    dias = _journal_days()
    if not dias:
        return None
    xlsx = os.path.join(hist_dir, HIST_FILENAME)
    fechas = _fechas_base(xlsx)
    pendientes = sorted(d for d in dias if d not in fechas)
    if not pendientes:
        return None
    logger.warning("[historico_writer] catch-up: a la base le faltan %s — consolidando "
                   "desde el journal local", ", ".join(str(d) for d in pendientes))
    res = append_and_save(None, xlsx)
    try:
        from backend.services import historico_byma
        historico_byma.refresh()
    except Exception:  # noqa: BLE001
        logger.exception("[historico_writer] refresh tras catch-up falló")
    return res


def estado() -> Dict[str, Any]:
    """Estado de la base para /admin/salud: última fecha guardada, atraso en
    ruedas vs el último cierre esperado (calendario de feriados AR + días
    marcados 'sin rueda'), journal local, chip y el último autosave."""
    from backend.services import deltapaths
    e = estado_cierre()
    out: Dict[str, Any] = {"writer": e["writer"], "cierre": e["texto"] or "—"}
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        out["error"] = "carpeta Delta Bases no montada en esta máquina"
        return out
    xlsx = os.path.join(hist_dir, HIST_FILENAME)
    fechas = _fechas_base_cached(xlsx)
    out["ultima_fecha"] = e["ultima"] or "—"
    out["esperado"] = e["esperado"]
    out["atraso_habiles"] = e["atraso"]
    out["ok"] = e["estado"] == "ok"
    out["detalle"] = e["detalle"]
    dias_j = _journal_days()
    out["journal_dias"] = len(dias_j)
    pend = sorted(d for d in dias_j if d not in fechas)
    if pend:
        out["journal_pendiente"] = ", ".join(str(d) for d in pend)
    try:
        import pandas as _pd
        pq_fx = os.path.splitext(os.path.join(hist_dir, FX_FILENAME))[0] + ".parquet"
        if os.path.isfile(pq_fx):
            f = _pd.read_parquet(pq_fx, columns=["fecha_hoy"])["fecha_hoy"]
            out["fx_ultima"] = str(_pd.to_datetime(f).max().date())
    except Exception:  # noqa: BLE001
        pass
    if _autosave is not None and _autosave.last_result:
        r = _autosave.last_result
        out["ultimo_autosave"] = (r.get("skipped") or r.get("error")
                                  or f"OK {r.get('rows')} filas")
    return out


def save_today(force: bool = False) -> Dict[str, Any]:
    """Orquesta el guardado del día. `force=True` (botón manual del superuser)
    saltea los guards de calendario/actividad, nunca el dedup."""
    from backend.config import settings
    from backend.services import deltapaths, historico_byma

    res: Dict[str, Any] = {"ok": False, "skipped": None, "error": None,
                           "rows": 0, "operados": 0, "total_rows": None, "xlsx": None}
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        res["error"] = ("No encontré la carpeta 'Delta Bases' (DELTA_HISTORICO_DIR / "
                        "DELTA_BASES_DIR en secrets.txt).")
        return res
    xlsx = os.path.join(hist_dir, HIST_FILENAME)
    res["xlsx"] = xlsx

    if not force:
        if _now().weekday() >= 5:
            res["skipped"] = "fin de semana"
            return res
        if _ya_guardado_hoy(xlsx):
            res["skipped"] = "la base ya tiene filas de hoy"
            return res

    df = build_rows()
    res["rows"] = int(len(df))
    res["operados"] = operados_hoy(df)
    if len(df) == 0:
        # error (no skip): en día hábil un store vacío es una anomalía y el
        # autosave debe REINTENTAR (feed que se cae justo a las 17:01)
        res["error"] = "sin datos en el store (¿feed caído?)"
        return res
    if not force and res["operados"] < settings.historico_autosave_min_operados:
        res["skipped"] = (f"sólo {res['operados']} bonos operaron hoy "
                          f"(mínimo {settings.historico_autosave_min_operados}: ¿feriado?)")
        _marcar_sin_rueda(_now().date())      # el chip no reclama este día
        return res

    # 1) JOURNAL LOCAL primero: el día queda capturado aunque la base falle.
    try:
        res["journal"] = write_journal(df)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[historico_writer] journal local no guardado: %s", exc)

    # 2) Base compartida (OneDrive) — sólo si esta máquina es writer (el
    #    botón manual la escribe siempre).
    if not settings.historico_base_writer and not force:
        res["ok"] = True
        res["skipped"] = "base_writer=0: sólo journal local (la consolida otra máquina)"
        return res
    try:
        saved = append_and_save(df, xlsx)
        res.update(saved)
        res["ok"] = True
        res["hora"] = _now().strftime("%H:%M")
        _prune_journal()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[historico_writer] guardado falló")
        res["error"] = str(exc)
        return res
    # Historial FX del día (cable/MEP/canje/A3500): 1 fila, archivo propio.
    # Best-effort: un FX caído jamás voltea el cierre de bonos ya guardado.
    try:
        fxres = _guardar_fx(hist_dir)
        if fxres:
            res["fx_filas"] = fxres["filas"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[historico_writer] historial FX falló: %s", exc)
    try:
        historico_byma.refresh()          # Qué pasó / Históricos ven el día nuevo ya
    except Exception:  # noqa: BLE001
        logger.exception("[historico_writer] refresh del histórico falló")
    logger.info("[historico_writer] base guardada: %d filas de hoy (%d operados) → %s",
                res["rows"], res["operados"], xlsx)
    return res


# ── Historial diario de FX (cable / MEP / canje) ───────────────────────────
# Se guarda junto con el cierre de siempre: UNA fila por día (contra las ~500
# de bonos es costo cero), en su propio archivo con espejo parquet, escritura
# atómica y dedup por fecha. Lo escribe sólo la máquina writer (mismo gate que
# la base) dentro del autosave / botón manual.
FX_FILENAME = "Delta - historico_fx.xlsx"


def build_fx_row() -> Optional[Dict[str, Any]]:
    """Fila del día con los FX de referencia del proceso: CCL (cable) y MEP
    implícitos del store (mismos que usa toda la app), canje = CCL/MEP − 1,
    el oficial A3500, y la caución BYMA overnight EN PESOS Y EN DÓLARES
    (plazo real del día por volumen — viernes 3D, feriado mid-week 2D,
    feriado+finde 4D — con TNA de cierre y, si el feed lo codifica en EV/NV,
    el VWAP del día). Serie diaria acumulada estilo A3500/TAMAR, en el mismo
    archivo FX. None si no hay NINGÚN dato."""
    from backend.services import dolares, fx as fx_svc
    snap = fx_svc.get_fx("24hs")
    oficial = None
    try:
        oficial = (dolares.official_fx() or {}).get("last")
    except Exception:  # noqa: BLE001
        pass
    cauc = cauc_usd = None
    try:
        from backend.services import cauciones
        cauc = cauciones.hist_row("PESOS")
        cauc_usd = cauciones.hist_row("DOLAR")
    except Exception:  # noqa: BLE001 — la caución jamás frena el guardado del FX
        logger.warning("[historico_writer] caución para el histórico falló", exc_info=True)
    if not (snap.ccl or snap.usb or oficial or cauc or cauc_usd):
        return None
    return {"fecha_hoy": _now().date(), "ccl": snap.ccl, "mep": snap.usb,
            "canje": snap.canje, "oficial_a3500": oficial,
            "ccl_base": snap.ccl_base or "",
            # Caución BYMA o/n en $ y US$ (las claves van SIEMPRE para que las
            # columnas existan aunque un día no haya dato — None = celda vacía).
            "caucion_plazo_d": (cauc or {}).get("plazo_d"),
            "caucion_tna": (cauc or {}).get("tna"),
            "caucion_tna_vwap": (cauc or {}).get("vwap"),
            "caucion_monto": (cauc or {}).get("monto"),
            "caucion_usd_plazo_d": (cauc_usd or {}).get("plazo_d"),
            "caucion_usd_tna": (cauc_usd or {}).get("tna"),
            "caucion_usd_tna_vwap": (cauc_usd or {}).get("vwap"),
            "caucion_usd_monto": (cauc_usd or {}).get("monto")}


def _guardar_fx(hist_dir: str) -> Optional[Dict[str, Any]]:
    """Appendea la fila FX del día a Delta - historico_fx (xlsx + espejo
    parquet): dedup por fecha keep-last, escritura atómica y reintentos ante
    lock — la misma solidez que la base grande, en miniatura."""
    import pandas as pd

    fila = build_fx_row()
    if fila is None:
        logger.info("[historico_writer] sin FX para guardar (feed sin CCL/MEP/A3500)")
        return None
    xlsx = os.path.join(hist_dir, FX_FILENAME)
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    prev = None
    for path, reader in ((pq, pd.read_parquet), (xlsx, pd.read_excel)):
        if os.path.exists(path):
            try:
                prev = reader(path)
                break
            except Exception as exc:  # noqa: BLE001 — un FX ilegible no frena el cierre
                logger.warning("[historico_writer] historial FX ilegible (%s): %s — "
                               "pruebo la otra copia / re-arranco desde hoy", path, exc)
    df = pd.DataFrame([fila])
    if prev is not None and len(prev):
        prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"]).dt.date
        df = pd.concat([prev, df], ignore_index=True)
    df = (df.drop_duplicates(subset=["fecha_hoy"], keep="last")
            .sort_values("fecha_hoy").reset_index(drop=True))
    for i in range(len(_LOCK_ESPERAS) + 1):
        try:
            tmp = xlsx + ".tmp.xlsx"
            df.to_excel(tmp, index=False)
            os.replace(tmp, xlsx)
            break
        except (PermissionError, OSError) as exc:
            if i == len(_LOCK_ESPERAS):
                raise
            logger.warning("[historico_writer] FX lockeado (%s) — reintento en %.0f s",
                           exc, _LOCK_ESPERAS[i])
            time.sleep(_LOCK_ESPERAS[i])
    try:
        mirror = df.copy()
        mirror["ccl_base"] = mirror["ccl_base"].astype("string")
        tmp_pq = pq + ".tmp"
        mirror.to_parquet(tmp_pq, index=False)
        os.replace(tmp_pq, pq)
    except Exception as exc:  # noqa: BLE001 — el xlsx ya quedó bien
        logger.warning("[historico_writer] espejo parquet FX no guardado: %s", exc)
    return {"filas": len(df), "xlsx": xlsx}


def next_fire(now: datetime, hhmm: str) -> datetime:
    """Próximo disparo: hoy a HH:MM (BA) si todavía no pasó, si no mañana.
    El guard de fin de semana / feriado vive en save_today, no acá."""
    try:
        hh, mm = (int(x) for x in hhmm.split(":", 1))
    except ValueError:
        hh, mm = 17, 1
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class HistoricoAutosave:
    """Task asyncio: duerme hasta las HH:MM de cada día y corre save_today()
    en el threadpool (Excel I/O + TIRs fuera del event loop)."""

    def __init__(self, hhmm: str = "17:01") -> None:
        self.hhmm = hhmm
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.last_result: Optional[Dict[str, Any]] = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="historico-autosave")
        logger.info("[historico_writer] autosave armado (%s BA, días hábiles)", self.hhmm)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        # CATCH-UP al arranque: si la base se perdió un cierre que el journal
        # local sí tiene (app caída a las 17:01, xlsx lockeado, conflicto de
        # OneDrive), se consolida acá mismo, sin esperar al próximo cierre.
        try:
            r0 = await loop.run_in_executor(None, consolidar_journal)
            if r0:
                logger.info("[historico_writer] catch-up del journal OK: %s día(s) "
                            "consolidados (%s filas totales)",
                            r0.get("consolidados"), r0.get("total_rows"))
        except Exception:  # noqa: BLE001
            logger.exception("[historico_writer] catch-up del journal falló")
        while not self._stop.is_set():
            wait = (next_fire(_now(), self.hhmm) - _now()).total_seconds()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(wait, 1.0))
                break                                  # stop durante la espera
            except asyncio.TimeoutError:
                pass
            # Ventana de REINTENTOS: un xlsx lockeado o el feed caído justo a
            # las 17:01 no puede costar el día entero — reintenta cada 10 min
            # hasta ~90 min. Los skips de calendario (finde/feriado/ya
            # guardado) cortan al primer intento.
            for _intento in range(10):
                try:
                    self.last_result = await loop.run_in_executor(None, save_today)
                except Exception:  # noqa: BLE001
                    logger.exception("[historico_writer] autosave reventó")
                    self.last_result = {"ok": False, "skipped": None,
                                        "error": "excepción — ver log"}
                r = self.last_result
                if r.get("ok"):
                    logger.info("[historico_writer] autosave OK: %s filas de hoy", r["rows"])
                    # Mail de cierre con el "Qué pasó" del día (best-effort,
                    # en el threadpool; SMTP apagado → no-op logueado).
                    try:
                        from backend.services import quepaso_report
                        await loop.run_in_executor(None, quepaso_report.send_close_mail)
                    except Exception:  # noqa: BLE001
                        logger.exception("[historico_writer] mail de cierre falló")
                    break
                if r.get("skipped"):
                    logger.info("[historico_writer] autosave salteado: %s", r["skipped"])
                    break
                logger.warning("[historico_writer] autosave falló (%s) — reintento en "
                               "10 min", r.get("error"))
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=600.0)
                    return                             # shutdown durante la espera
                except asyncio.TimeoutError:
                    continue


_autosave: Optional[HistoricoAutosave] = None


def get_autosave() -> HistoricoAutosave:
    global _autosave
    if _autosave is None:
        from backend.config import settings
        _autosave = HistoricoAutosave(hhmm=settings.historico_autosave_hhmm)
    return _autosave
