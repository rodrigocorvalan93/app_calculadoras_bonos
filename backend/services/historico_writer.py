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
    from backend.services import symbols as syms

    store = marketdata_store.get_store()
    seen: set = set()
    rows: List[Dict[str, Any]] = []
    hoy = _now().date()
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
            m = pricing.metrics_for_market_price(code, ref_px, None)
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


def _append_and_save_locked(df: "Any", xlsx_path: str, np, pd,
                            incluir_journal: bool = True) -> Dict[str, Any]:
    prev = None
    if os.path.exists(xlsx_path):
        prev = pd.read_excel(xlsx_path, parse_dates=["fecha_hoy"])
        prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"]).dt.date

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
    días hábiles vs el último cierre esperado (feriados cuentan como atraso —
    no conocemos el calendario), journal local y el último autosave."""
    from backend.config import settings
    from backend.services import deltapaths
    out: Dict[str, Any] = {"writer": settings.historico_base_writer}
    hist_dir = deltapaths.historico_dir()
    if not hist_dir:
        out["error"] = "carpeta Delta Bases no montada en esta máquina"
        return out
    xlsx = os.path.join(hist_dir, HIST_FILENAME)
    fechas = _fechas_base(xlsx)
    ultima = max(fechas) if fechas else None
    out["ultima_fecha"] = ultima.isoformat() if ultima else "—"
    ahora = _now()
    try:
        hh, mm = (int(x) for x in settings.historico_autosave_hhmm.split(":", 1))
    except ValueError:
        hh, mm = 17, 1
    esperado = ahora.date()
    if (ahora.hour, ahora.minute) < (hh, mm):
        esperado -= timedelta(days=1)
    while esperado.weekday() >= 5:
        esperado -= timedelta(days=1)
    atraso = None
    if ultima:
        atraso, d = 0, ultima
        while d < esperado:
            d += timedelta(days=1)
            if d.weekday() < 5:
                atraso += 1
    out["esperado"] = esperado.isoformat()
    out["atraso_habiles"] = atraso
    out["ok"] = atraso == 0
    dias_j = _journal_days()
    out["journal_dias"] = len(dias_j)
    pend = sorted(d for d in dias_j if d not in fechas)
    if pend:
        out["journal_pendiente"] = ", ".join(str(d) for d in pend)
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
        _prune_journal()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[historico_writer] guardado falló")
        res["error"] = str(exc)
        return res
    try:
        historico_byma.refresh()          # Qué pasó / Históricos ven el día nuevo ya
    except Exception:  # noqa: BLE001
        logger.exception("[historico_writer] refresh del histórico falló")
    logger.info("[historico_writer] base guardada: %d filas de hoy (%d operados) → %s",
                res["rows"], res["operados"], xlsx)
    return res


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
