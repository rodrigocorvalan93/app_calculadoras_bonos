# -*- coding: utf-8 -*-
"""extractor_cauciones.py

Extractor de datos de cauciones BYMA para entrenar modelos ML.

Símbolos target:
    MERV - XMEV - PESOS - 1D
    MERV - XMEV - PESOS - 3D

Dos modos:

    historical  → Baja trades históricos vía `rest/data/getTrades`
                  para los viernes del rango pedido. Reconstruye OHLCV
                  minuto a minuto. NO trae BID/OFFER (no existen en
                  el histórico REST de Primary).

    recorder    → Loop en vivo contra `rest/marketdata/get`. Guarda
                  BID / BID_SIZE / LAST / OFFER / OFFER_SIZE / VOLUMEN
                  cada N segundos en parquet particionado por fecha.
                  Pensado para correr durante la rueda y acumular.

Uso:
    python extractor_cauciones.py historical --from 2025-01-01 --to 2026-05-15
    python extractor_cauciones.py recorder   --interval 5 --until 17:00
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

# Reusamos los módulos de la app principal — están un nivel arriba.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import OMSapi  # noqa: E402
import OMSsecrets  # noqa: E402
import OMSsettings as cfg  # noqa: E402


SYMBOLS = [
    "MERV - XMEV - PESOS - 1D",
    "MERV - XMEV - PESOS - 3D",
]

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────

def _login() -> requests.Session:
    OMSsecrets.load()
    user = os.getenv("OMS_USER") or os.getenv("XOMS_USER")
    pwd = os.getenv("OMS_PASS") or os.getenv("XOMS_PASS")
    if not user or not pwd:
        raise SystemExit(
            "Faltan credenciales. Definí OMS_USER y OMS_PASS "
            "(o XOMS_USER / XOMS_PASS) en secrets.txt o como env vars."
        )
    return OMSapi.login(user, pwd)


# ──────────────────────────────────────────────────────────────────────
# Fechas
# ──────────────────────────────────────────────────────────────────────

def fridays_between(d_from: date, d_to: date) -> List[date]:
    """Lista de viernes (weekday=4) entre dos fechas inclusive."""
    out: List[date] = []
    d = d_from
    while d <= d_to:
        if d.weekday() == 4:
            out.append(d)
        d += timedelta(days=1)
    return out


# ──────────────────────────────────────────────────────────────────────
# MODO HISTORICAL: trades + reconstrucción OHLCV minuto
# ──────────────────────────────────────────────────────────────────────

def fetch_trades(
    session: requests.Session,
    symbol: str,
    date_from: date,
    date_to: date,
    market_id: str = "ROFX",
) -> pd.DataFrame:
    """Endpoint Primary estándar: rest/data/getTrades.

    Devuelve un DataFrame con columnas crudas tal cual las da el server
    (típicamente: price, size, datetime, servertime, symbol, marketId).
    """
    url = f"{cfg.BASE_URL}rest/data/getTrades"
    params = {
        "marketId": market_id,
        "symbol": symbol,
        "dateFrom": date_from.strftime("%Y-%m-%d"),
        "dateTo": date_to.strftime("%Y-%m-%d"),
    }
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    body = r.json()

    if body.get("status") == "ERROR":
        raise RuntimeError(f"getTrades ERROR {symbol}: {body.get('description')}")

    trades = body.get("trades") or body.get("data") or []
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["symbol"] = symbol
    return df


def normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Detecta la columna timestamp y la pasa a DatetimeIndex en hora local.

    Primary suele exponer 'datetime' (epoch ms) y/o 'servertime'.
    """
    if df.empty:
        return df

    ts_col = None
    for cand in ("datetime", "servertime", "date", "timestamp"):
        if cand in df.columns:
            ts_col = cand
            break
    if ts_col is None:
        raise RuntimeError(f"No encuentro columna de timestamp en {df.columns.tolist()}")

    s = df[ts_col]
    if pd.api.types.is_numeric_dtype(s):
        # Epoch en ms (Primary) o segundos
        unit = "ms" if s.max() > 10**12 else "s"
        ts = pd.to_datetime(s, unit=unit, utc=True).dt.tz_convert("America/Argentina/Buenos_Aires")
    else:
        ts = pd.to_datetime(s, utc=True, errors="coerce").dt.tz_convert("America/Argentina/Buenos_Aires")

    df = df.copy()
    df["ts"] = ts.dt.tz_localize(None)

    # Columnas estándar
    if "price" not in df.columns:
        for cand in ("lastPx", "tradePrice", "last"):
            if cand in df.columns:
                df = df.rename(columns={cand: "price"})
                break
    if "size" not in df.columns:
        for cand in ("lastSize", "tradeSize", "qty"):
            if cand in df.columns:
                df = df.rename(columns={cand: "size"})
                break

    return df.dropna(subset=["ts", "price"]).sort_values("ts")


def resample_minute_bars(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV por minuto. En cauciones 'price' es la TNA negociada."""
    if df.empty:
        return df
    g = df.set_index("ts")
    bars = pd.DataFrame({
        "tna_open":  g["price"].resample("1min").first(),
        "tna_high":  g["price"].resample("1min").max(),
        "tna_low":   g["price"].resample("1min").min(),
        "tna_close": g["price"].resample("1min").last(),
        "volume":    g["size"].resample("1min").sum() if "size" in g.columns else 0,
        "trades":    g["price"].resample("1min").count(),
    })
    return bars.dropna(subset=["tna_close"])


def run_historical(date_from: date, date_to: date, only_fridays: bool = True) -> None:
    session = _login()
    days = fridays_between(date_from, date_to) if only_fridays else [
        date_from + timedelta(days=i)
        for i in range((date_to - date_from).days + 1)
    ]
    if not days:
        print("Sin días que procesar.")
        return

    print(f"Días a bajar: {len(days)} ({days[0]} → {days[-1]})  símbolos={len(SYMBOLS)}")

    for symbol in SYMBOLS:
        all_trades: List[pd.DataFrame] = []
        # Pedimos por día para no toparnos con caps del server, en paralelo.
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(fetch_trades, session, symbol, d, d): d for d in days}
            for f in as_completed(futs):
                d = futs[f]
                try:
                    raw = f.result()
                except Exception as e:
                    print(f"  ✗ {symbol} {d}: {type(e).__name__}: {e}")
                    continue
                if raw.empty:
                    continue
                all_trades.append(raw)
                print(f"  ✓ {symbol} {d}: {len(raw)} trades")

        if not all_trades:
            print(f"⚠ {symbol}: sin trades en el rango.")
            continue

        df_raw = pd.concat(all_trades, ignore_index=True)
        df_norm = normalize_trades(df_raw)
        df_bars = resample_minute_bars(df_norm)

        # Guardado: un parquet de trades crudos + uno de barras minuto
        safe = symbol.replace(" ", "_").replace("-", "")
        trades_path = DATA_DIR / f"trades_{safe}.parquet"
        bars_path = DATA_DIR / f"bars1m_{safe}.parquet"
        df_norm.to_parquet(trades_path, index=False)
        df_bars.to_parquet(bars_path)
        print(f"→ {symbol}: {len(df_norm)} trades  /  {len(df_bars)} barras 1m")
        print(f"   {trades_path}")
        print(f"   {bars_path}")


# ──────────────────────────────────────────────────────────────────────
# MODO RECORDER: snapshot loop con BID / OFFER / SIZES
# ──────────────────────────────────────────────────────────────────────

def _snap_row(md: dict, symbol: str, t_capture: datetime) -> dict:
    """Aplana el dict marketData a una fila tabular."""
    def first(entry, key="price"):
        v = md.get(entry)
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, dict):
            return v.get(key)
        return None

    return {
        "ts_capture": t_capture,
        "symbol": symbol,
        "bid":        first("BI", "price"),
        "bid_size":   first("BI", "size"),
        "offer":      first("OF", "price"),
        "offer_size": first("OF", "size"),
        "last":       first("LA", "price"),
        "last_size":  first("LA", "size"),
        "last_ts":    (md.get("LA") or [{}])[0].get("date") if isinstance(md.get("LA"), list) else None,
        "open":       first("OP", "price"),
        "close":      first("CL", "price"),
        "high":       first("HI", "price"),
        "low":        first("LO", "price"),
        "volume":     md.get("EV", {}).get("size") if isinstance(md.get("EV"), dict) else None,
        "trade_vol":  md.get("TV", {}).get("size") if isinstance(md.get("TV"), dict) else None,
        "nominal":    md.get("NV", {}).get("size") if isinstance(md.get("NV"), dict) else None,
    }


def _fetch_snapshot(session: requests.Session, symbol: str) -> Optional[dict]:
    r = session.get(
        f"{cfg.BASE_URL}rest/marketdata/get",
        params={
            "marketId": "ROFX",
            "symbol": symbol,
            "entries": "LA,BI,OF,OP,CL,HI,LO,EV,TV,NV",
            "depth": 1,
        },
        timeout=10,
    )
    r.raise_for_status()
    if not r.content:
        return None
    try:
        raw = r.json()
    except ValueError:
        return None
    if raw.get("status") == "ERROR":
        return None
    return raw.get("marketData")


def run_recorder(interval: int, until: Optional[str], outfile: Optional[Path] = None) -> None:
    session = _login()

    today = date.today()
    outfile = outfile or DATA_DIR / f"snapshots_{today.isoformat()}.parquet"
    print(f"Recorder activo. interval={interval}s  out={outfile}")
    print(f"Símbolos: {SYMBOLS}")
    if until:
        print(f"Hasta las {until} (hora local).")

    until_dt: Optional[datetime] = None
    if until:
        hh, mm = (int(x) for x in until.split(":"))
        until_dt = datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm)

    rows: List[dict] = []
    flush_every = 60  # filas → flush a disco
    try:
        while True:
            t_capture = datetime.now()
            if until_dt and t_capture >= until_dt:
                print("Se alcanzó la hora de corte.")
                break

            for sym in SYMBOLS:
                try:
                    md = _fetch_snapshot(session, sym)
                except Exception as e:
                    print(f"  ! {sym} {t_capture:%H:%M:%S}: {type(e).__name__}: {e}")
                    continue
                if md is None:
                    continue
                rows.append(_snap_row(md, sym, t_capture))

            if len(rows) >= flush_every:
                _append_parquet(outfile, rows)
                print(f"  flush {len(rows)} filas → {outfile}")
                rows.clear()

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        if rows:
            _append_parquet(outfile, rows)
            print(f"Final flush {len(rows)} filas → {outfile}")


def _append_parquet(path: Path, rows: List[dict]) -> None:
    df_new = pd.DataFrame(rows)
    if path.exists():
        df_old = pd.read_parquet(path)
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_parquet(path, index=False)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_hist = sub.add_parser("historical", help="Baja trades históricos (viernes por defecto)")
    p_hist.add_argument("--from", dest="d_from", type=_parse_date, required=True)
    p_hist.add_argument("--to", dest="d_to", type=_parse_date, required=True)
    p_hist.add_argument("--all-days", action="store_true", help="No filtrar por viernes; bajar todos los días.")

    p_rec = sub.add_parser("recorder", help="Snapshot loop en vivo (acumula BID/OFFER)")
    p_rec.add_argument("--interval", type=int, default=5, help="Segundos entre snapshots (default 5)")
    p_rec.add_argument("--until", type=str, default=None, help="HH:MM corte (ej. 17:00). Default: corre hasta Ctrl+C.")

    args = p.parse_args()
    if args.cmd == "historical":
        run_historical(args.d_from, args.d_to, only_fridays=not args.all_days)
    elif args.cmd == "recorder":
        run_recorder(args.interval, args.until)


if __name__ == "__main__":
    main()
