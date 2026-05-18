# -*- coding: utf-8 -*-
"""extractor_cauciones.py

Recorder REST de cauciones BYMA: snapshots periódicos del book vía
`rest/marketdata/get`. Pensado para correr durante la rueda y acumular
microestructura (BID/OFFER/SIZES/LAST/volúmenes) en parquet.

Por qué no hay modo histórico:
  Primary REST devuelve trades históricos sólo para futuros ROFEX.
  Para cauciones BYMA, `rest/data/getTrades` responde `{trades: []}`
  silenciosamente — no hay manera de bajar histórico pasado por
  REST. Si necesitás trade-by-trade, usá `recorder_ws.py` (WebSocket).

Símbolo del día:
  El plazo que opera (1D/2D/3D/4D/5D) depende del calendario:
  ver `universe.py`. Captura sólo ese — el resto no opera.

Uso:
    python extractor_cauciones.py --interval 5 --until 17:00
    python extractor_cauciones.py --interval 5                # corre hasta Ctrl+C
    python extractor_cauciones.py --interval 2 --include-dolar
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

# Reusamos los módulos de la app principal — están un nivel arriba.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import OMSapi  # noqa: E402
import OMSsecrets  # noqa: E402
import OMSsettings as cfg  # noqa: E402

from universe import simbolo_caucion  # noqa: E402

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
# Snapshot
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

    la_list = md.get("LA")
    last_ts = la_list[0].get("date") if isinstance(la_list, list) and la_list else None

    return {
        "ts_capture": t_capture,
        "symbol": symbol,
        "bid":        first("BI", "price"),
        "bid_size":   first("BI", "size"),
        "offer":      first("OF", "price"),
        "offer_size": first("OF", "size"),
        "last":       first("LA", "price"),
        "last_size":  first("LA", "size"),
        "last_ts":    last_ts,
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


def _append_parquet(path: Path, rows: List[dict]) -> None:
    df_new = pd.DataFrame(rows)
    if path.exists():
        df_old = pd.read_parquet(path)
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_parquet(path, index=False)


def _humanize(n) -> str:
    """Formatea sizes grandes (cauciones tradean montos enormes)."""
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}k"
    return f"{n:.0f}"


def _fmt_last_ts(raw) -> str:
    """Primary devuelve last_ts como epoch ms o string ISO/'YYYYMMDD-HH:MM:SS'."""
    if raw is None:
        return "—"
    # epoch en milisegundos
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw / 1000).strftime("%H:%M:%S")
        except (OSError, ValueError, OverflowError):
            return str(raw)
    s = str(raw)
    # Formato Primary: '20260518-12:34:50' o ISO 'YYYY-MM-DDTHH:MM:SS'
    for fmt in ("%Y%m%d-%H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return s[-8:] if len(s) >= 8 else s


def _print_snapshot_line(row: dict) -> None:
    """Heartbeat por snapshot: hora local, símbolo, top of book, último trade."""
    sym = row["symbol"].split(" - ")[-1] if row.get("symbol") else "?"
    t = row["ts_capture"].strftime("%H:%M:%S") if row.get("ts_capture") else "--:--:--"
    bid = f"{row['bid']:.3f}" if row.get("bid") is not None else "—"
    ofr = f"{row['offer']:.3f}" if row.get("offer") is not None else "—"
    last = f"{row['last']:.3f}" if row.get("last") is not None else "—"
    print(
        f"  {t}  {sym:>3}  "
        f"BI {bid}×{_humanize(row.get('bid_size'))}   "
        f"OF {ofr}×{_humanize(row.get('offer_size'))}   "
        f"LAST {last}  @ {_fmt_last_ts(row.get('last_ts'))}"
    )


# ──────────────────────────────────────────────────────────────────────
# Recorder loop
# ──────────────────────────────────────────────────────────────────────

def run_recorder(interval: int, until: Optional[str], include_dolar: bool) -> None:
    session = _login()

    today = date.today()
    symbols = [simbolo_caucion(today, "PESOS")]
    if include_dolar:
        symbols.append(simbolo_caucion(today, "DOLAR"))

    outfile = DATA_DIR / f"snapshots_{today.isoformat()}.parquet"
    print(f"Recorder REST activo.")
    print(f"  interval = {interval}s")
    print(f"  símbolos = {symbols}")
    print(f"  out      = {outfile}")
    if until:
        print(f"  corte    = {until} (hora local)")

    until_dt: Optional[datetime] = None
    if until:
        hh, mm = (int(x) for x in until.split(":"))
        until_dt = datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm)

    rows: List[dict] = []
    flush_every = 60
    errors_streak = 0
    try:
        while True:
            t_capture = datetime.now()
            if until_dt and t_capture >= until_dt:
                print("Se alcanzó la hora de corte.")
                break

            for sym in symbols:
                try:
                    md = _fetch_snapshot(session, sym)
                    errors_streak = 0
                except Exception as e:
                    errors_streak += 1
                    print(f"  ! {sym} {t_capture:%H:%M:%S}: {type(e).__name__}: {e}")
                    if errors_streak >= 5:
                        print("  Re-login por errores consecutivos.")
                        session = _login()
                        errors_streak = 0
                    continue
                if md is None:
                    continue
                row = _snap_row(md, sym, t_capture)
                rows.append(row)
                _print_snapshot_line(row)

            if len(rows) >= flush_every:
                _append_parquet(outfile, rows)
                print(f"  ── flush {len(rows)} filas → parquet  ({t_capture:%H:%M:%S})")
                rows.clear()

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        if rows:
            _append_parquet(outfile, rows)
            print(f"Final flush {len(rows)} filas → {outfile}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=int, default=5, help="Segundos entre snapshots (default 5)")
    p.add_argument("--until", type=str, default=None, help="HH:MM corte (ej. 17:00). Default: corre hasta Ctrl+C.")
    p.add_argument("--include-dolar", action="store_true", help="Capturar también caución en dólares.")
    args = p.parse_args()
    run_recorder(args.interval, args.until, args.include_dolar)


if __name__ == "__main__":
    main()
