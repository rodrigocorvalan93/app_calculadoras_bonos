# -*- coding: utf-8 -*-
"""recorder_ws.py

Cliente WebSocket de Primary (xOMS Matrizoms) para capturar trades y
updates de book de cauciones BYMA en tiempo real. Captura cada evento
individual — no muestrea como el recorder REST.

Protocolo: JSON sobre WebSocket. Auth por cookie de sesión Spring
heredada del login REST de OMSapi.

Dos modos:

    test     → Conecta y dumpea el primer mensaje que llega a stdout.
               Útil para validar handshake antes de comprometerse a
               un payload de subscripción. Sale después de 30 segundos
               o de recibir 20 mensajes.

    record   → Subscribe MarketData (BI, OF, LA, EV, NV) del símbolo
               de caución del día y persiste cada evento en parquet.
               Re-conecta automáticamente si se cae.

Dependencias:
    pip install websocket-client

Uso:
    python recorder_ws.py test
    python recorder_ws.py record --until 17:00       # captura PESOS + DOLAR (default)
    python recorder_ws.py record --no-dolar          # sólo PESOS
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import OMSapi  # noqa: E402
import OMSsecrets  # noqa: E402
import OMSsettings as cfg  # noqa: E402

from universe import simbolo_caucion  # noqa: E402

try:
    import websocket  # websocket-client
except ImportError:
    raise SystemExit(
        "Falta dependencia: pip install websocket-client"
    )


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
# Auth helper — reusa cookie de OMSapi
# ──────────────────────────────────────────────────────────────────────

def _login_cookies() -> dict:
    OMSsecrets.load()
    user = os.getenv("OMS_USER") or os.getenv("XOMS_USER")
    pwd = os.getenv("OMS_PASS") or os.getenv("XOMS_PASS")
    if not user or not pwd:
        raise SystemExit("Faltan OMS_USER / OMS_PASS en secrets.")
    s = OMSapi.login(user, pwd)
    return s.cookies.get_dict()


def _ws_url() -> str:
    """Deriva la URL WS del BASE_URL HTTP."""
    base = cfg.BASE_URL.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):]
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):]
    return base


def _cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ──────────────────────────────────────────────────────────────────────
# Subscripción
# ──────────────────────────────────────────────────────────────────────

def _build_subscribe_msg(symbols: List[str]) -> str:
    """Mensaje estándar de Primary para subscribir MarketData."""
    return json.dumps({
        "type": "smd",
        "level": 1,
        "entries": ["BI", "OF", "LA", "OP", "CL", "HI", "LO", "EV", "TV", "NV"],
        "products": [{"symbol": s, "marketId": "ROFX"} for s in symbols],
        "depth": 5,
    })


# ──────────────────────────────────────────────────────────────────────
# MODO TEST: handshake + dump raw
# ──────────────────────────────────────────────────────────────────────

def run_test(symbols: List[str], max_messages: int = 20, timeout_s: int = 30) -> None:
    cookies = _login_cookies()
    url = _ws_url()
    print(f"\nWS URL: {url}")
    print(f"Cookies: {list(cookies.keys())}")
    print(f"Símbolos a subscribir: {symbols}\n")

    ws = websocket.create_connection(
        url,
        header=[f"Cookie: {_cookie_header(cookies)}"],
        timeout=15,
    )
    print("✔ Conexión WS abierta.\n")

    sub = _build_subscribe_msg(symbols)
    print(f"→ Enviando subscribe:\n{sub}\n")
    ws.send(sub)

    ws.settimeout(timeout_s)
    t0 = time.time()
    n = 0
    try:
        while n < max_messages and (time.time() - t0) < timeout_s:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                print(f"  (sin mensajes en {timeout_s}s — corto)")
                break
            n += 1
            print(f"── msg #{n}  ({len(raw)} bytes) ──")
            try:
                obj = json.loads(raw)
                print(json.dumps(obj, indent=2, ensure_ascii=False, default=str)[:1500])
            except ValueError:
                print(raw[:600])
            print()
    finally:
        ws.close()
        print(f"\nTotal mensajes recibidos: {n}")


# ──────────────────────────────────────────────────────────────────────
# MODO RECORD: persiste cada mensaje
# ──────────────────────────────────────────────────────────────────────

def _flatten_md_event(obj: dict, t_capture: datetime) -> Optional[dict]:
    """Aplana un evento 'Md' de Primary a una fila tabular.

    El payload típico es:
      {"type":"Md", "timestamp":..., "instrumentId":{"symbol":..,"marketId":..},
       "marketData":{"BI":[{...}], "OF":[{...}], "LA":{...}, ...}}
    """
    if obj.get("type") not in ("Md", "md"):
        return None
    md = obj.get("marketData") or {}
    inst = obj.get("instrumentId") or {}

    def first(entry, key):
        v = md.get(entry)
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, dict):
            return v.get(key)
        return None

    return {
        "ts_capture": t_capture,
        "ts_server": obj.get("timestamp"),
        "symbol": inst.get("symbol"),
        "bid":        first("BI", "price"),
        "bid_size":   first("BI", "size"),
        "offer":      first("OF", "price"),
        "offer_size": first("OF", "size"),
        "last":       first("LA", "price"),
        "last_size":  first("LA", "size"),
        "last_ts":    (md.get("LA") or {}).get("date") if isinstance(md.get("LA"), dict) else None,
        "open":       first("OP", "price"),
        "close":      first("CL", "price"),
        "high":       first("HI", "price"),
        "low":        first("LO", "price"),
        "volume":     (md.get("EV") or {}).get("size") if isinstance(md.get("EV"), dict) else None,
        "trade_vol":  (md.get("TV") or {}).get("size") if isinstance(md.get("TV"), dict) else None,
        "nominal":    (md.get("NV") or {}).get("size") if isinstance(md.get("NV"), dict) else None,
    }


def _append_parquet(path: Path, rows: List[dict]) -> None:
    df_new = pd.DataFrame(rows)
    if path.exists():
        df_old = pd.read_parquet(path)
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_parquet(path, index=False)


def _short_symbol(s: Any) -> str:
    """'MERV - XMEV - PESOS - 1D' → 'PESOS 1D'."""
    if not isinstance(s, str):
        return str(s)
    parts = [p.strip() for p in s.split(" - ")]
    if len(parts) >= 4:
        return f"{parts[2]} {parts[3]}"
    return s


def _fmt_px(v) -> str:
    try:
        f = float(v)
        if f != f:  # NaN
            return "—"
        return f"{f:.3f}"
    except (TypeError, ValueError):
        return "—"


def _humanize(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n != n:
        return "—"
    if abs(n) >= 1e9:
        return f"{n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{n/1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"{n/1e3:.0f}k"
    return f"{n:.0f}"


def _summarize_flush(rows: List[dict]) -> str:
    """Resumen por símbolo de la ventana de flush.

    Por cada símbolo en `rows`, muestra:
      - evs:    cantidad de eventos
      - trades: # de last_ts únicos != None (proxy de trades nuevos en la ventana)
      - bid/ofr/last: primer → último valor visto
      - hi/lo:  rango del 'last' (precios efectivamente operados)
      - Σnom:   suma de last_size de los trades distintos (VWAP-able)
    """
    if not rows:
        return "(vacío)"
    df = pd.DataFrame(rows)
    if df.empty or "symbol" not in df.columns:
        return "(sin symbol)"

    lines = []
    for sym, g in df.groupby("symbol", sort=False):
        n = len(g)

        # Trades nuevos = last_ts únicos no nulos.
        if "last_ts" in g.columns:
            ts_uniq = g["last_ts"].dropna().drop_duplicates()
            n_trades = len(ts_uniq)
            # Σ nominal de un row por trade
            tr_rows = g.dropna(subset=["last_ts"]).drop_duplicates(subset=["last_ts"], keep="first")
            sigma_nom = pd.to_numeric(tr_rows.get("last_size"), errors="coerce").sum()
            last_prices = pd.to_numeric(tr_rows.get("last"), errors="coerce").dropna()
        else:
            n_trades = 0
            sigma_nom = 0
            last_prices = pd.Series([], dtype="float64")

        def _first_last(col):
            s = pd.to_numeric(g.get(col), errors="coerce").dropna()
            if s.empty:
                return "—", "—"
            return _fmt_px(s.iloc[0]), _fmt_px(s.iloc[-1])

        bid_a, bid_b = _first_last("bid")
        ofr_a, ofr_b = _first_last("offer")
        last_a, last_b = _first_last("last")
        hi = _fmt_px(last_prices.max()) if not last_prices.empty else "—"
        lo = _fmt_px(last_prices.min()) if not last_prices.empty else "—"

        lines.append(
            f"    {_short_symbol(sym):<12s} "
            f"evs={n:<4d} trades={n_trades:<3d} "
            f"bid {bid_a}→{bid_b}  ofr {ofr_a}→{ofr_b}  "
            f"last {last_a}→{last_b}  hi {hi} lo {lo}  Σnom={_humanize(sigma_nom)}"
        )
    return "\n".join(lines)


def run_record(symbols: List[str], until: Optional[str], verbose_flush: bool = False) -> None:
    today = date.today()
    out_md = DATA_DIR / f"ws_md_{today.isoformat()}.parquet"
    raw_log = DATA_DIR / f"ws_raw_{today.isoformat()}.jsonl"
    print(f"WS recorder activo.")
    print(f"  símbolos       = {symbols}")
    print(f"  out MD         = {out_md}")
    print(f"  raw log        = {raw_log}")
    print(f"  verbose-flush  = {verbose_flush}")

    until_dt: Optional[datetime] = None
    if until:
        hh, mm = (int(x) for x in until.split(":"))
        until_dt = datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm)

    flush_every = 50
    rows: List[dict] = []
    reconnects = 0
    raw_fh = open(raw_log, "a", encoding="utf-8")

    try:
        while True:
            if until_dt and datetime.now() >= until_dt:
                print("Corte alcanzado.")
                break
            try:
                cookies = _login_cookies()
                ws = websocket.create_connection(
                    _ws_url(),
                    header=[f"Cookie: {_cookie_header(cookies)}"],
                    timeout=15,
                )
                ws.send(_build_subscribe_msg(symbols))
                ws.settimeout(60)
                print(f"✔ WS abierto (reconnect #{reconnects})")

                while True:
                    if until_dt and datetime.now() >= until_dt:
                        break
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        # heartbeat: 60s sin mensajes — el server suele estar
                        # vivo, mandamos ping y seguimos
                        ws.ping()
                        continue

                    t_capture = datetime.now()
                    raw_fh.write(raw + "\n")

                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue

                    row = _flatten_md_event(obj, t_capture)
                    if row:
                        rows.append(row)

                    if len(rows) >= flush_every:
                        _append_parquet(out_md, rows)
                        if verbose_flush:
                            print(f"  ── flush {len(rows)} eventos @ {t_capture:%H:%M:%S} ──")
                            print(_summarize_flush(rows))
                        else:
                            print(f"  flush {len(rows)} eventos  ({t_capture:%H:%M:%S})")
                        rows.clear()

            except (websocket.WebSocketException, ConnectionError, OSError) as e:
                print(f"  ✗ WS caído: {type(e).__name__}: {e}.  Reintentando en 5s.")
                reconnects += 1
                time.sleep(5)
                continue
            else:
                break
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        if rows:
            _append_parquet(out_md, rows)
            if verbose_flush:
                print(f"  ── final flush {len(rows)} eventos ──")
                print(_summarize_flush(rows))
            else:
                print(f"Final flush {len(rows)} eventos → {out_md}")
        raw_fh.close()


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    # Caución PESOS + DOLAR por default; --no-dolar para opt-out.
    common.add_argument("--no-dolar", dest="include_dolar", action="store_false",
                        help="No capturar caución en dólares (default: capturar ambos).")
    common.set_defaults(include_dolar=True)
    common.add_argument("--symbol", action="append", help="Override: símbolo manual (repetible)")

    p_test = sub.add_parser("test", parents=[common], help="Handshake + dump raw, 20 msgs ó 30s")
    p_rec = sub.add_parser("record", parents=[common], help="Persiste eventos en parquet")
    p_rec.add_argument("--until", type=str, default=None, help="HH:MM corte (default: Ctrl+C)")
    p_rec.add_argument("--verbose-flush", action="store_true",
                       help="En cada flush imprime resumen por símbolo: evs/trades/bid/ofr/last/hi/lo/nominal.")

    args = p.parse_args()

    if args.symbol:
        symbols = args.symbol
    else:
        today = date.today()
        symbols = [simbolo_caucion(today, "PESOS")]
        if args.include_dolar:
            symbols.append(simbolo_caucion(today, "DOLAR"))

    if args.cmd == "test":
        run_test(symbols)
    elif args.cmd == "record":
        run_record(symbols, args.until, verbose_flush=args.verbose_flush)


if __name__ == "__main__":
    main()
