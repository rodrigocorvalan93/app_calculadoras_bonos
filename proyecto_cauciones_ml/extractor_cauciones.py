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

Columnas derivadas (computadas localmente, no las manda el server):
  - is_new_trade : bool, True si (last, last_size) cambió vs snap anterior
  - cum_trades   : contador acumulado de trades únicos del día
  - cum_nominal  : suma de last_size de los trades detectados

EOD snapshot:
  Al terminar la rueda, captura un snapshot con todos los entries
  (OP/HI/LO/CL/IV) — varios sólo se publican post-cierre — y guarda
  en `data/eod_<fecha>.parquet`. Imprime VWAP del día derivado de los
  snapshots de la sesión.

Uso:
    python extractor_cauciones.py --interval 5 --until 17:00
    python extractor_cauciones.py --interval 5                # corre hasta Ctrl+C
    python extractor_cauciones.py --interval 2                # 2s, captura PESOS + DOLAR (default)
    python extractor_cauciones.py --no-dolar --interval 5     # sólo PESOS
    python extractor_cauciones.py --debug-dump --interval 5   # dumpea raw del 1° response
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

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

# Entries durante la rueda (lo que típicamente está poblado)
_ENTRIES_LIVE = "LA,BI,OF,CL,EV,TV,NV"
# Entries para EOD (incluye OP/HI/LO/IV que sólo aparecen post-cierre)
_ENTRIES_EOD = "LA,BI,OF,OP,CL,HI,LO,EV,TV,NV,IV,SE,OI"


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
# Extractores resilientes a variantes de schema
# ──────────────────────────────────────────────────────────────────────

def _first_record(md: dict, entry: str) -> Optional[dict]:
    """Devuelve el primer record de un entry, sea lista o dict."""
    v = md.get(entry)
    if isinstance(v, list):
        return v[0] if v else None
    if isinstance(v, dict):
        return v
    return None


def _price(md: dict, entry: str) -> Optional[float]:
    rec = _first_record(md, entry)
    return rec.get("price") if isinstance(rec, dict) else None


def _size(md: dict, entry: str):
    """EV/TV/NV/LA/BI/OF: tamaño. Robusto a list/dict/scalar."""
    rec = _first_record(md, entry)
    if isinstance(rec, dict):
        return rec.get("size") if rec.get("size") is not None else rec.get("price")
    if isinstance(rec, (int, float)):
        return rec
    return None


def _extract_last_ts(md: dict):
    """Timestamp del último trade. Primary usa varias keys según versión."""
    rec = _first_record(md, "LA")
    if not isinstance(rec, dict):
        return None
    for key in ("date", "timestamp", "transactTime", "tradeTime", "expireTime"):
        v = rec.get(key)
        if v is not None:
            return v
    return None


# ──────────────────────────────────────────────────────────────────────
# Estado por símbolo (para detectar trades nuevos)
# ──────────────────────────────────────────────────────────────────────

_PREV_STATE: Dict[str, Dict] = {}


def _reset_state(symbol: str) -> None:
    _PREV_STATE[symbol] = {"last": None, "last_size": None, "last_ts": None,
                           "n_trades": 0, "cum_nominal": 0.0}


def _update_trade_state(symbol: str, last_price, last_size, last_ts) -> Dict:
    st = _PREV_STATE.setdefault(symbol, {"last": None, "last_size": None, "last_ts": None,
                                          "n_trades": 0, "cum_nominal": 0.0})
    if last_price is None:
        return {"is_new_trade": False, "cum_trades": st["n_trades"], "cum_nominal": st["cum_nominal"]}

    # Trade nuevo si CAMBIA last_ts (más confiable), o cambia (price, size).
    is_new = False
    if last_ts is not None and last_ts != st["last_ts"]:
        is_new = True
    elif last_ts is None and (last_price != st["last"] or last_size != st["last_size"]):
        is_new = True

    if is_new:
        st["n_trades"] += 1
        try:
            st["cum_nominal"] += float(last_size or 0)
        except (TypeError, ValueError):
            pass

    st["last"] = last_price
    st["last_size"] = last_size
    st["last_ts"] = last_ts
    return {"is_new_trade": is_new, "cum_trades": st["n_trades"], "cum_nominal": st["cum_nominal"]}


# ──────────────────────────────────────────────────────────────────────
# Snapshot
# ──────────────────────────────────────────────────────────────────────

def _snap_row(md: dict, symbol: str, t_capture: datetime) -> dict:
    """Aplana marketData a una fila tabular + columnas derivadas."""
    last_price = _price(md, "LA")
    last_size = _size(md, "LA")
    last_ts = _extract_last_ts(md)
    derived = _update_trade_state(symbol, last_price, last_size, last_ts)

    return {
        "ts_capture": t_capture,
        "symbol": symbol,
        "bid":        _price(md, "BI"),
        "bid_size":   _size(md, "BI"),
        "offer":      _price(md, "OF"),
        "offer_size": _size(md, "OF"),
        "last":       last_price,
        "last_size":  last_size,
        "last_ts":    last_ts,
        "open":       _price(md, "OP"),
        "close":      _price(md, "CL"),
        "high":       _price(md, "HI"),
        "low":        _price(md, "LO"),
        "volume":     _size(md, "EV"),
        "trade_vol":  _size(md, "TV"),
        "nominal":    _size(md, "NV"),
        # Derivadas
        "is_new_trade":  derived["is_new_trade"],
        "cum_trades":    derived["cum_trades"],
        "cum_nominal":   derived["cum_nominal"],
    }


_DUMPED: set = set()


def _fetch_snapshot(session: requests.Session, symbol: str,
                    entries: str = _ENTRIES_LIVE,
                    debug_dump: bool = False) -> Optional[dict]:
    r = session.get(
        f"{cfg.BASE_URL}rest/marketdata/get",
        params={
            "marketId": "ROFX",
            "symbol": symbol,
            "entries": entries,
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

    if debug_dump and symbol not in _DUMPED:
        _DUMPED.add(symbol)
        print(f"\n══════ DEBUG RAW {symbol} ══════")
        print(json.dumps(raw, indent=2, ensure_ascii=False, default=str)[:3500])
        print("══════════════════════════════════\n")

    if raw.get("status") == "ERROR":
        return None
    return raw.get("marketData")


def _append_parquet(path: Path, rows: List[dict]) -> None:
    df_new = pd.DataFrame(rows)
    if path.exists():
        df_old = pd.read_parquet(path)
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_parquet(path, index=False)


# ──────────────────────────────────────────────────────────────────────
# Formato de heartbeat
# ──────────────────────────────────────────────────────────────────────

def _humanize(n) -> str:
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
    if raw is None:
        return "—"
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw / 1000).strftime("%H:%M:%S")
        except (OSError, ValueError, OverflowError):
            return str(raw)
    s = str(raw)
    for fmt in ("%Y%m%d-%H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return s[-8:] if len(s) >= 8 else s


def _print_snapshot_line(row: dict) -> None:
    sym = row["symbol"].split(" - ")[-1] if row.get("symbol") else "?"
    t = row["ts_capture"].strftime("%H:%M:%S") if row.get("ts_capture") else "--:--:--"
    bid = f"{row['bid']:.3f}" if row.get("bid") is not None else "—"
    ofr = f"{row['offer']:.3f}" if row.get("offer") is not None else "—"
    last = f"{row['last']:.3f}" if row.get("last") is not None else "—"
    trade_marker = " 🟢" if row.get("is_new_trade") else "  "
    print(
        f"  {t}  {sym:>3}  "
        f"BI {bid}×{_humanize(row.get('bid_size'))}   "
        f"OF {ofr}×{_humanize(row.get('offer_size'))}   "
        f"LAST {last}  @ {_fmt_last_ts(row.get('last_ts'))}{trade_marker}"
        f"  #{row.get('cum_trades', 0)}"
    )


# ──────────────────────────────────────────────────────────────────────
# EOD: snapshot rico + cálculo de VWAP del día
# ──────────────────────────────────────────────────────────────────────

def _capture_eod(session: requests.Session, symbols: List[str], today: date,
                 debug_dump: bool = False) -> None:
    """Snapshot final con todos los entries (post-cierre)."""
    print("\n══════ EOD snapshot ══════")
    eod_rows: List[dict] = []
    for sym in symbols:
        try:
            r = session.get(
                f"{cfg.BASE_URL}rest/marketdata/get",
                params={"marketId": "ROFX", "symbol": sym,
                        "entries": _ENTRIES_EOD, "depth": 1},
                timeout=15,
            )
            r.raise_for_status()
            body = r.json()
        except Exception as e:
            print(f"  ✗ {sym}: {type(e).__name__}: {e}")
            continue

        if debug_dump:
            print(f"\n--- raw EOD {sym} ---")
            print(json.dumps(body, indent=2, ensure_ascii=False, default=str)[:2500])
            print()

        if body.get("status") == "ERROR":
            print(f"  ✗ {sym}: server respondió ERROR ({body.get('description')})")
            continue
        md = body.get("marketData") or {}
        row = _snap_row(md, sym, datetime.now())
        row["raw_eod"] = json.dumps(body, default=str)
        eod_rows.append(row)
        print(f"  ✓ {sym.split(' - ')[-1]:>4}  "
              f"open={row.get('open')}  high={row.get('high')}  "
              f"low={row.get('low')}  close={row.get('close')}  "
              f"vol={_humanize(row.get('volume'))}")

    if eod_rows:
        eod_path = DATA_DIR / f"eod_{today.isoformat()}.parquet"
        pd.DataFrame(eod_rows).to_parquet(eod_path, index=False)
        print(f"  → {eod_path}")


def _summarize_session(session_parquet: Path) -> None:
    """VWAP, número de trades y nominal del día desde la sesión capturada."""
    if not session_parquet.exists():
        return
    df = pd.read_parquet(session_parquet)
    if "is_new_trade" not in df.columns or not df["is_new_trade"].any():
        print("\n(sin trades detectados en la sesión — no se calcula VWAP)")
        return

    print("\n══════ Resumen del día (derivado de snapshots) ══════")
    trades = df[df["is_new_trade"]]
    for sym, grp in trades.groupby("symbol"):
        sizes = grp["last_size"].astype(float)
        prices = grp["last"].astype(float)
        nominal = sizes.sum()
        vwap = (prices * sizes).sum() / nominal if nominal else float("nan")
        print(f"  {sym.split(' - ')[-1]:>4}  "
              f"n={len(grp):>5}  "
              f"VWAP={vwap:.4f}%  "
              f"hi={prices.max():.3f}  lo={prices.min():.3f}  "
              f"open={prices.iloc[0]:.3f}  close={prices.iloc[-1]:.3f}  "
              f"nominal={_humanize(nominal)}")


# ──────────────────────────────────────────────────────────────────────
# Recorder loop
# ──────────────────────────────────────────────────────────────────────

def run_recorder(interval: int, until: Optional[str], include_dolar: bool,
                 debug_dump: bool = False) -> None:
    session = _login()

    today = date.today()
    symbols = [simbolo_caucion(today, "PESOS")]
    if include_dolar:
        symbols.append(simbolo_caucion(today, "DOLAR"))
    for sym in symbols:
        _reset_state(sym)

    outfile = DATA_DIR / f"snapshots_{today.isoformat()}.parquet"
    print(f"Recorder REST activo.")
    print(f"  interval = {interval}s")
    print(f"  símbolos = {symbols}")
    print(f"  out      = {outfile}")
    if until:
        print(f"  corte    = {until} (hora local)")
    if debug_dump:
        print("  debug-dump = ON (se imprime el 1° raw response por símbolo)")

    until_dt: Optional[datetime] = None
    if until:
        hh, mm = (int(x) for x in until.split(":"))
        until_dt = datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm)

    rows: List[dict] = []
    flush_every = 60
    errors_streak = 0
    reached_cutoff = False
    try:
        while True:
            t_capture = datetime.now()
            if until_dt and t_capture >= until_dt:
                print("Se alcanzó la hora de corte.")
                reached_cutoff = True
                break

            for sym in symbols:
                try:
                    md = _fetch_snapshot(session, sym, debug_dump=debug_dump)
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

        # EOD: snapshot rico + summary. Sólo si llegamos al corte
        # (i.e. mercado cerró). Si fue Ctrl+C antes de hora, no tiene sentido.
        if reached_cutoff:
            try:
                _capture_eod(session, symbols, today, debug_dump=debug_dump)
            except Exception as e:
                print(f"  EOD falló: {type(e).__name__}: {e}")
            _summarize_session(outfile)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=int, default=5, help="Segundos entre snapshots (default 5)")
    p.add_argument("--until", type=str, default=None, help="HH:MM corte (ej. 17:00). Default: corre hasta Ctrl+C.")
    # Caución PESOS + DOLAR por default; --no-dolar para sólo pesos.
    p.add_argument("--no-dolar", dest="include_dolar", action="store_false",
                   help="No capturar caución en dólares (default: capturar ambos).")
    p.set_defaults(include_dolar=True)
    p.add_argument("--debug-dump", action="store_true", help="Imprime el 1° raw response por símbolo (y el EOD).")
    args = p.parse_args()
    run_recorder(args.interval, args.until, args.include_dolar, debug_dump=args.debug_dump)


if __name__ == "__main__":
    main()
