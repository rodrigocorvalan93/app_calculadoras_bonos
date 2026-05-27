# -*- coding: utf-8 -*-
"""recorder_ws.py

Cliente WebSocket de Primary (xOMS Matrizoms) para capturar trades y
updates de book de cauciones BYMA en tiempo real. Captura cada evento
individual — no muestrea como el recorder REST.

Protocolo: JSON sobre WebSocket. Auth por cookie de sesión Spring
heredada del login REST de OMSapi.

Tres modos:

    test     → Conecta y dumpea el primer mensaje que llega a stdout.
               Útil para validar handshake antes de comprometerse a
               un payload de subscripción. Sale después de 30 segundos
               o de recibir 20 mensajes.

    record   → Subscribe MarketData (BI, OF, LA, EV, NV) del símbolo
               de caución del día y persiste cada evento en parquet.
               Re-conecta automáticamente si se cae.

    reparse  → Lee un .jsonl crudo y emite un parquet con el parser
               actual. Útil para recuperar data grabada con parser viejo.

Dependencias:
    pip install websocket-client

Uso:
    python recorder_ws.py test
    python recorder_ws.py record --until 17:00                  # captura PESOS + DOLAR (default)
    python recorder_ws.py record --no-dolar                     # sólo PESOS
    python recorder_ws.py record --verbose-flush                # resumen por símbolo en cada flush
    python recorder_ws.py reparse data/ws_raw_2026-05-19.jsonl  # re-parsea data vieja

`--verbose-flush` muestra en cada flush (~50 eventos, 10-20 s):

    ── flush 50 eventos @ 14:32:18 ──
      PESOS 1D  evs=42 trades=8  bid 14.20→14.22 ofr 14.45→14.50 last 14.30→14.35 hi 14.40 lo 14.20 Σnom=234M  ‖ acum: ev=1.2k tr=58 nom=1.42B
      DOLAR 1D  evs=8  trades=1  bid 2.10→2.12   ofr 2.25→2.30   last 2.20→2.20   hi 2.20  lo 2.20  Σnom=1.5M  ‖ acum: ev=210 tr=12 nom=8.4M

Métricas por símbolo en la ventana:
  evs       eventos recibidos (incluye book updates sin trade)
  trades    trades NUEVOS en la ventana (last_ts no vistos antes)
  bid/ofr   evolución del top of book (primer → último de la ventana)
  last      primer → último precio operado
  hi / lo   rango de precios efectivamente operados en la ventana
  Σnom      nominal de los trades nuevos en la ventana

Acumulado de la sesión (= desde que arrancó el script):
  acum ev   total de eventos recibidos para ese símbolo
  acum tr   total de trades únicos del día
  acum nom  Σ nominal operado en la rueda hasta ahora
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

def _md_value(v: Any, key: str = "price"):
    """Extrae 'price' o 'size' de un campo de marketData del WS.

    El schema de Primary varía según el entry:
      - LA / BI / OF / CL  → dict {"price":.., "size":..} o lista de dicts (depth)
      - OP / HI / LO       → SCALAR (es el precio)
      - EV / NV / TV       → SCALAR (es el size acumulado)
      - null               → no hay dato

    Esta función es tolerante a las tres formas: list-of-dict, dict, scalar.
    """
    if v is None:
        return None
    if isinstance(v, list):
        if not v:
            return None
        v = v[0]
    if isinstance(v, dict):
        return v.get(key)
    if isinstance(v, (int, float)):
        # Scalar: vale tanto como price (OP/HI/LO) como size (EV/NV/TV).
        # El llamador sabe qué pidió.
        return v
    return None


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

    # last_ts: fecha del último trade. LA es dict cuando hay trade; si no, None.
    la_raw = md.get("LA")
    last_ts = la_raw.get("date") if isinstance(la_raw, dict) else None

    return {
        "ts_capture": t_capture,
        "ts_server": obj.get("timestamp"),
        "symbol": inst.get("symbol"),
        "bid":        _md_value(md.get("BI"), "price"),
        "bid_size":   _md_value(md.get("BI"), "size"),
        "offer":      _md_value(md.get("OF"), "price"),
        "offer_size": _md_value(md.get("OF"), "size"),
        "last":       _md_value(md.get("LA"), "price"),
        "last_size":  _md_value(md.get("LA"), "size"),
        "last_ts":    last_ts,
        "open":       _md_value(md.get("OP"), "price"),  # scalar
        "close":      _md_value(md.get("CL"), "price"),
        "high":       _md_value(md.get("HI"), "price"),  # scalar
        "low":        _md_value(md.get("LO"), "price"),  # scalar
        "volume":     _md_value(md.get("EV"), "size"),   # scalar (acumulado $)
        "trade_vol":  _md_value(md.get("TV"), "size"),   # scalar (#trades del día)
        "nominal":    _md_value(md.get("NV"), "size"),   # scalar (nominal acum)
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


def _summarize_flush(rows: List[dict], cum_state: Dict[str, Dict[str, Any]]) -> str:
    """Resumen por símbolo de la ventana de flush + acumulado de la sesión.

    Por cada símbolo en `rows`, muestra:
      - evs:    eventos recibidos en la ventana
      - trades: # de trades NUEVOS (last_ts no visto antes en la sesión)
      - bid/ofr/last: primer → último valor visto
      - hi/lo:  rango del 'last' (precios efectivamente operados, nuevos)
      - Σnom:   nominal total de los trades nuevos en la ventana

    Y al final de cada línea:
      - acum:   evs / trades / Σnom acumulados desde el inicio del recorder.

    `cum_state` se muta in-place. Llamadas sucesivas deduplican last_ts
    correctamente: un trade que aparece reportado en eventos de dos
    flushes consecutivos se cuenta UNA sola vez (en el flush donde se vió
    primero).
    """
    if not rows:
        return "(vacío)"
    df = pd.DataFrame(rows)
    if df.empty or "symbol" not in df.columns:
        return "(sin symbol)"

    lines = []
    for sym, g in df.groupby("symbol", sort=False):
        n_evs = len(g)
        st = cum_state.setdefault(sym, {
            "evs": 0, "trades": 0, "sigma_nom": 0.0, "seen_ts": set(),
        })
        st["evs"] += n_evs

        # NUEVOS trades = last_ts en esta ventana que no estaban en seen_ts.
        if "last_ts" in g.columns:
            window_ts = g["last_ts"].dropna().drop_duplicates()
            new_ts_mask = ~window_ts.isin(st["seen_ts"])
            new_ts = window_ts[new_ts_mask]
            new_rows = (
                g[g["last_ts"].isin(new_ts)]
                .drop_duplicates(subset=["last_ts"], keep="first")
            )
            n_trades_new = len(new_rows)
            sigma_nom_new = float(
                pd.to_numeric(new_rows.get("last_size"), errors="coerce").sum()
            )
            st["seen_ts"].update(new_ts.tolist())
            st["trades"] += n_trades_new
            st["sigma_nom"] += sigma_nom_new
            last_prices = pd.to_numeric(new_rows.get("last"), errors="coerce").dropna()
        else:
            n_trades_new = 0
            sigma_nom_new = 0.0
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
            f"evs={n_evs:<4d} trades={n_trades_new:<3d} "
            f"bid {bid_a}→{bid_b}  ofr {ofr_a}→{ofr_b}  "
            f"last {last_a}→{last_b}  hi {hi} lo {lo}  Σnom={_humanize(sigma_nom_new)}  "
            f"‖ acum: ev={st['evs']:,} tr={st['trades']:,} nom={_humanize(st['sigma_nom'])}"
        )
    return "\n".join(lines)


def _resolve_symbols(include_dolar: bool) -> List[str]:
    today = date.today()
    symbols = [simbolo_caucion(today, "PESOS")]
    if include_dolar:
        symbols.append(simbolo_caucion(today, "DOLAR"))
    return symbols


def run_record(
    symbols: List[str],
    until: Optional[str],
    verbose_flush: bool = False,
    include_dolar: bool = True,
    auto_symbols: bool = True,
) -> None:
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
    # Acumulado de la sesión (mientras el proceso siga vivo). Se conserva a
    # través de reconnects del WS — sólo se reinicia si reiniciás el script.
    cum_state: Dict[str, Dict[str, Any]] = {}
    need_resubscribe = False

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

                    new_today = date.today()
                    if new_today != today:
                        if rows:
                            _append_parquet(out_md, rows)
                            if verbose_flush:
                                print(f"  ── flush {len(rows)} eventos (cierre día {today}) ──")
                                print(_summarize_flush(rows, cum_state))
                            else:
                                print(f"  flush {len(rows)} eventos (cierre día {today})")
                            rows.clear()
                        raw_fh.close()

                        today = new_today
                        out_md = DATA_DIR / f"ws_md_{today.isoformat()}.parquet"
                        raw_log = DATA_DIR / f"ws_raw_{today.isoformat()}.jsonl"
                        raw_fh = open(raw_log, "a", encoding="utf-8")
                        cum_state.clear()

                        if auto_symbols:
                            symbols = _resolve_symbols(include_dolar)

                        if until:
                            hh, mm = (int(x) for x in until.split(":"))
                            until_dt = datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm)

                        print(f"\n╔══ Rotación de día → {today.isoformat()} ══╗")
                        print(f"  símbolos  = {symbols}")
                        print(f"  out MD    = {out_md}")
                        print(f"  raw log   = {raw_log}")
                        need_resubscribe = True
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
                            print(_summarize_flush(rows, cum_state))
                        else:
                            print(f"  flush {len(rows)} eventos  ({t_capture:%H:%M:%S})")
                        rows.clear()

            except (websocket.WebSocketException, ConnectionError, OSError) as e:
                print(f"  ✗ WS caído: {type(e).__name__}: {e}.  Reintentando en 5s.")
                reconnects += 1
                time.sleep(5)
                continue
            else:
                if need_resubscribe:
                    need_resubscribe = False
                    reconnects += 1
                    continue
                break
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        if rows:
            _append_parquet(out_md, rows)
            if verbose_flush:
                print(f"  ── final flush {len(rows)} eventos ──")
                print(_summarize_flush(rows, cum_state))
            else:
                print(f"Final flush {len(rows)} eventos → {out_md}")
        raw_fh.close()


# ──────────────────────────────────────────────────────────────────────
# Re-parse: lee un .jsonl crudo y emite un parquet con el parser actual.
# Útil para recuperar data grabada con un parser viejo bugueado.
# ──────────────────────────────────────────────────────────────────────

def run_reparse(jsonl_path: Path, out_parquet: Path) -> int:
    """Re-parsea un raw log y escribe un parquet limpio.

    ts_capture se deriva del `timestamp` del payload (ts_server) ya que el
    original no fue persistido. Es suficiente para todos los análisis
    intraday — la diferencia con ts_capture real es del orden de ms.
    """
    rows: List[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            ts = obj.get("timestamp")
            t_capture = (
                datetime.fromtimestamp(ts / 1000) if isinstance(ts, (int, float)) and ts > 0
                else datetime.now()
            )
            row = _flatten_md_event(obj, t_capture)
            if row:
                rows.append(row)
    if rows:
        pd.DataFrame(rows).to_parquet(out_parquet, index=False)
    return len(rows)


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

    p_rp = sub.add_parser("reparse",
                          help="Re-parsea un .jsonl crudo con el parser actual (útil cuando el parser tenía bug).")
    p_rp.add_argument("input", type=str, help="Path al .jsonl crudo (ej. data/ws_raw_2026-05-19.jsonl)")
    p_rp.add_argument("--out", type=str, default=None,
                      help="Path del parquet de salida (default: input_dir/ws_md_<date>_reparsed.parquet)")

    args = p.parse_args()

    if args.cmd == "reparse":
        in_path = Path(args.input)
        if not in_path.exists():
            raise SystemExit(f"No existe: {in_path}")
        if args.out:
            out_path = Path(args.out)
        else:
            # data/ws_raw_2026-05-19.jsonl  →  data/ws_md_2026-05-19_reparsed.parquet
            stem = in_path.stem.replace("ws_raw_", "ws_md_")
            out_path = in_path.with_name(f"{stem}_reparsed.parquet")
        n = run_reparse(in_path, out_path)
        print(f"✔ Re-parseados {n} eventos → {out_path}")
        return

    auto_symbols = not args.symbol
    if args.symbol:
        symbols = args.symbol
    else:
        symbols = _resolve_symbols(args.include_dolar)

    if args.cmd == "test":
        run_test(symbols)
    elif args.cmd == "record":
        run_record(
            symbols,
            args.until,
            verbose_flush=args.verbose_flush,
            include_dolar=args.include_dolar,
            auto_symbols=auto_symbols,
        )


if __name__ == "__main__":
    main()
