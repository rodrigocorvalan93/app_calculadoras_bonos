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
"Guardar base de hoy" de Históricos, sólo superuser. Si corrés la app en DOS
máquinas a la vez, dejá el autosave prendido en una sola
(HISTORICO_AUTOSAVE=0 en la otra) para no escribir el mismo archivo en
paralelo vía OneDrive.
"""
from __future__ import annotations

import asyncio
import logging
import os
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


def append_and_save(df: "Any", xlsx_path: str) -> Dict[str, Any]:
    """Appendea `df` a la base (Excel + espejo Parquet) con la semántica de
    bymaapi.guardar_excel: concat con lo existente, dedup (symbol, Código,
    fecha_hoy) keep last, dropna de métricas, Proy por sufijo 'j'. Escritura
    atómica (tmp + replace) — un corte a mitad de escritura no corrompe la
    base."""
    import numpy as np
    import pandas as pd

    if os.path.exists(xlsx_path):
        prev = pd.read_excel(xlsx_path, parse_dates=["fecha_hoy"])
        prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"]).dt.date
        df_final = pd.concat([prev, df], ignore_index=True)
    else:
        df_final = df

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

    return {"total_rows": len(df_last), "xlsx": xlsx_path, "parquet": pq_path}


def _ya_guardado_hoy(xlsx_path: str) -> bool:
    """Chequeo rápido vía el espejo parquet (ms). Sin parquet devolvemos False
    y seguimos: el dedup del append garantiza que no se duplique nada."""
    pq = os.path.splitext(xlsx_path)[0] + ".parquet"
    if not os.path.isfile(pq):
        return False
    try:
        import pandas as pd
        fechas = pd.read_parquet(pq, columns=["fecha_hoy"])["fecha_hoy"]
        maxima = pd.to_datetime(fechas).max()
        return maxima is not None and maxima.date() == _now().date()
    except Exception:  # noqa: BLE001
        return False


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
        res["skipped" if not force else "error"] = "sin datos en el store (¿feed caído?)"
        return res
    if not force and res["operados"] < settings.historico_autosave_min_operados:
        res["skipped"] = (f"sólo {res['operados']} bonos operaron hoy "
                          f"(mínimo {settings.historico_autosave_min_operados}: ¿feriado?)")
        return res

    try:
        saved = append_and_save(df, xlsx)
        res.update(saved)
        res["ok"] = True
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
        while not self._stop.is_set():
            wait = (next_fire(_now(), self.hhmm) - _now()).total_seconds()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(wait, 1.0))
                break                                  # stop durante la espera
            except asyncio.TimeoutError:
                pass
            try:
                self.last_result = await loop.run_in_executor(None, save_today)
                r = self.last_result
                if r.get("ok"):
                    logger.info("[historico_writer] autosave OK: %s filas de hoy", r["rows"])
                elif r.get("skipped"):
                    logger.info("[historico_writer] autosave salteado: %s", r["skipped"])
                else:
                    logger.warning("[historico_writer] autosave falló: %s", r.get("error"))
            except Exception:  # noqa: BLE001
                logger.exception("[historico_writer] autosave reventó")


_autosave: Optional[HistoricoAutosave] = None


def get_autosave() -> HistoricoAutosave:
    global _autosave
    if _autosave is None:
        from backend.config import settings
        _autosave = HistoricoAutosave(hhmm=settings.historico_autosave_hhmm)
    return _autosave
