"""Backfill del histórico de acciones (Delta - historico_acciones.parquet).

El autosave del cierre arma la serie desde el día que se prende; este tool
carga historia previa para que la pestaña "Acciones" de Históricos sirva desde
el primer día. Corre SIEMPRE fuera de la app (nunca en un request):

  python -m backend.tools.backfill_acciones --csv cierres.csv
      columnas: fecha, ticker, cierre [, volumen] (encabezado libre de
      mayúsculas; fecha ISO o DD/MM/AAAA; decimales con coma o punto;
      separador , ; o tab). Sirve para lo que exporte el broker / una planilla.

  python -m backend.tools.backfill_acciones --byma [--desde AAAA-MM-DD] [--tickers GGAL,YPFD,SPY]
      BYMA Open Data: el endpoint "free" de series históricas que usa el
      gráfico del sitio de BYMA (formato UDF de TradingView:
      {"s":"ok","t":[epoch],"c":[cierre],"v":[volumen]}). Best-effort: si BYMA
      cambió el endpoint o no responde, avisa y NO toca el archivo. Default:
      Líderes + General + CEDEARs curados + Merval, desde hace 2 años.

Las filas que la app ya capturó GANAN sobre el backfill (dedup keep-app); el
archivo se escribe atómico con el mismo append del cierre (historico_writer).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)                           # backups/secrets relativos a la raíz

_BYMA_BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
_BYMA_HIST = "chart/historical-series/history"
_TIMEOUT = 15.0
_PAUSA = 0.15                             # entre tickers: no martillar el sitio
_MERVAL_SYMS = ("I.MERVAL", "MERVAL", "MERV")


def _fecha(s: Any) -> Optional[date]:
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def _num(s: Any) -> Optional[float]:
    from backend.locale_ar import parse_ar_num
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s) if s == s else None
    try:
        v = parse_ar_num(str(s))
    except Exception:  # noqa: BLE001
        return None
    return float(v) if v is not None else None


def _panel_de(ticker: str) -> str:
    from backend.services import equities
    from backend.services.historico_writer import MERVAL_TICKER
    if ticker == MERVAL_TICKER:
        return "I"
    return equities.panel_map().get(ticker, "")


def importar_csv(path: str) -> "Any":
    """CSV → DataFrame con el esquema del parquet (fecha_hoy, ticker, panel,
    ultimo, volumen; el resto vacío). Filas sin fecha/ticker/cierre se saltean."""
    import pandas as pd

    raw = pd.read_csv(path, sep=None, engine="python", dtype=str)
    cols = {c.strip().lower(): c for c in raw.columns}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    c_f, c_t, c_p = col("fecha", "date", "fecha_hoy"), col("ticker", "especie", "symbol", "codigo", "código"), col("cierre", "ultimo", "último", "close", "precio", "last")
    c_v = col("volumen", "volume", "monto", "efectivo")
    if not (c_f and c_t and c_p):
        raise SystemExit("el CSV necesita columnas fecha, ticker y cierre (encontré: %s)" % ", ".join(raw.columns))
    rows: List[Dict[str, Any]] = []
    for _, r in raw.iterrows():
        f, t, p = _fecha(r[c_f]), str(r[c_t] or "").strip().upper(), _num(r[c_p])
        if f is None or not t or p is None or p <= 0:
            continue
        rows.append({"fecha_hoy": f, "ticker": t, "panel": _panel_de(t), "ultimo": p,
                     "apertura": None, "maximo": None, "minimo": None, "cierre_ant": None,
                     "vwap": None, "volumen": (_num(r[c_v]) if c_v else None), "nominal": None})
    return pd.DataFrame(rows)


def _byma_get(session, params: Dict[str, Any]):
    """GET con el mismo fallback TLS que byma_paneles (cadena incompleta del
    sitio de BYMA): verify normal primero, sin verificar sólo ante SSLError."""
    import requests
    url = _BYMA_BASE + _BYMA_HIST
    try:
        r = session.get(url, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.SSLError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = session.get(url, params=params, timeout=_TIMEOUT, verify=False)
        r.raise_for_status()
        return r.json()


def _parse_udf(j: Any) -> List[Dict[str, Any]]:
    """Formato UDF de TradingView → filas (fecha, cierre, apertura, máx, mín, volumen)."""
    if not isinstance(j, dict) or j.get("s") not in (None, "ok") or not j.get("t"):
        return []
    t, c = j.get("t") or [], j.get("c") or []
    o, h, lo, v = j.get("o") or [], j.get("h") or [], j.get("l") or [], j.get("v") or []
    out = []
    for i, ts in enumerate(t):
        try:
            f = datetime.utcfromtimestamp(float(ts)).date()
            px = float(c[i])
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
        if px <= 0:
            continue
        g = lambda arr: (float(arr[i]) if i < len(arr) and arr[i] is not None else None)  # noqa: E731
        out.append({"fecha_hoy": f, "ultimo": px, "apertura": g(o), "maximo": g(h), "minimo": g(lo),
                    "volumen": g(v)})
    return out


def descargar_byma(tickers: List[str], desde: date, hasta: Optional[date] = None) -> "Any":
    """Series diarias de BYMA Open Data para `tickers` (+ Merval con sus
    variantes de símbolo). Un ticker que falla se saltea con aviso."""
    import pandas as pd
    import requests

    from backend.services.historico_writer import MERVAL_TICKER

    hasta = hasta or date.today()
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (app_calculadoras_bonos backfill)", "Accept": "application/json"})
    p_from, p_to = int(time.mktime(desde.timetuple())), int(time.mktime((hasta + timedelta(days=1)).timetuple()))
    rows: List[Dict[str, Any]] = []
    fallos: List[str] = []
    for t in tickers:
        syms = _MERVAL_SYMS if t == MERVAL_TICKER else (t,)
        got: List[Dict[str, Any]] = []
        for sym in syms:
            try:
                got = _parse_udf(_byma_get(s, {"symbol": sym, "resolution": "D", "from": p_from, "to": p_to}))
            except Exception as exc:  # noqa: BLE001
                print(f"  {t} ({sym}): {exc}")
                got = []
            if got:
                break
        if not got:
            fallos.append(t)
        for r in got:
            rows.append({**r, "ticker": t, "panel": _panel_de(t), "cierre_ant": None, "vwap": None, "nominal": None})
        print(f"  {t}: {len(got)} ruedas")
        time.sleep(_PAUSA)
    if fallos:
        print(f"sin datos de BYMA para: {', '.join(fallos)}")
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill del histórico de acciones (Históricos → Acciones)")
    ap.add_argument("--csv", help="CSV con fecha, ticker, cierre [, volumen]")
    ap.add_argument("--byma", action="store_true", help="bajar de BYMA Open Data (best-effort)")
    ap.add_argument("--desde", help="AAAA-MM-DD (default: hace 2 años)")
    ap.add_argument("--hasta", help="AAAA-MM-DD (default: hoy)")
    ap.add_argument("--tickers", help="lista separada por comas (default: paneles curados + MERVAL)")
    ap.add_argument("--destino", help="carpeta del parquet (default: Delta Bases de secrets.txt)")
    a = ap.parse_args(argv)
    if not a.csv and not a.byma:
        ap.print_help()
        return 2

    from backend.services import deltapaths
    from backend.services.historico_writer import ACCIONES_FILENAME, MERVAL_TICKER, append_acciones

    hist_dir = a.destino or deltapaths.historico_dir()
    if not hist_dir or not os.path.isdir(hist_dir):
        print("no encuentro la carpeta 'Delta Bases' (DELTA_HISTORICO_DIR / DELTA_BASES_DIR en secrets.txt, o --destino)")
        return 1
    if a.csv:
        df = importar_csv(a.csv)
        print(f"CSV: {len(df)} filas válidas de {a.csv}")
    else:
        from backend.services import equities
        desde = _fecha(a.desde) or (date.today() - timedelta(days=730))
        hasta = _fecha(a.hasta)
        if a.tickers:
            tks = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
        else:
            tks = list(dict.fromkeys(equities.LIDERES + equities.GENERAL + equities.CEDEARS + [MERVAL_TICKER]))
        print(f"BYMA Open Data: {len(tks)} tickers desde {desde}…")
        df = descargar_byma(tks, desde, hasta)
    if df is None or not len(df):
        print("nada para guardar — el archivo queda como estaba")
        return 1
    res = append_acciones(df, os.path.join(hist_dir, ACCIONES_FILENAME), gana_previo=True)
    print(f"parquet: {res['parquet']} · {res['filas']} filas · {res['tickers']} tickers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
