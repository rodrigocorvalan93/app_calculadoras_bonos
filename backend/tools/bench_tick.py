"""Benchmark reproducible del camino por TICK (auditoría externa del 30/09).

Mide EN PROCESO (httpx.ASGITransport sobre `backend.main.app`, sin red, sin
lifespan ni jobs de fondo) lo que cuesta servir un md-update a los paneles
live, con la misma metodología que usó la auditoría:

  warm   misma seq del store → hit de cache (lo que cuesta un refresh sin tick)
  tick   UN update del store antes de cada request (la seq avanza; las
         métricas por precio siguen calientes: es el tick típico de la rueda,
         no un repricing masivo)
  delta  /mercado/rows con 1 y 30 filas cambiadas (since/order válidos)
  burst  N ondas × C clientes simultáneos con el MISMO tick (24 pestañas):
         p95 por request, duración de la onda y retraso del event loop medido
         con un heartbeat de 1 ms

Tiempos server-side: desde la entrada ASGI hasta el último byte del body
(incluye espera de workers y compresión; excluye httpx). Bytes crudos y
gzip por respuesta. Un número absoluto depende de la máquina y de la fecha
(vencimientos): comparar A/B en la misma máquina, secuencialmente.

  python -m backend.tools.bench_tick                          # tabla
  python -m backend.tools.bench_tick --json despues.json      # + JSON
  python -m backend.tools.bench_tick --compare antes.json despues.json
  python -m backend.tools.bench_tick --n 50 --waves 30 --clients 8 --solo warm,tick
  python -m backend.tools.bench_tick --slo 50                 # exit 1 si un p95 (1 cliente) pasa 50 ms

Aislado de producción: usuarios, journal local y snapshot del store van a una
carpeta temporal; AUTH_ENABLED=0; warmup, autosave, reconstrucción, watchdog
y puente TLS apagados. Los precios sembrados salen de las fichas (precio a
una TIR plausible por tipo de bono, así el Newton de la TIR recorre el
camino real); el store se completa hasta `--symbols` con símbolos sintéticos
sin ficha (el tamaño del snapshot de Excel depende de eso).
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

_MODOS = ("warm", "tick", "delta", "burst")


def _entorno(tmp: str) -> None:
    os.environ.setdefault("AUTH_ENABLED", "0")
    os.environ.setdefault("APP_HOST", "127.0.0.1")
    os.environ.setdefault("APP_SECRET_KEY", "bench-tick-local-only")
    for k, v in {
        "WARMUP_ENABLED": "0", "HISTORICO_AUTOSAVE": "0", "HISTORICO_RECONSTRUIR": "0",
        "FEED_WATCHDOG": "0", "TLS_BRIDGE": "0", "PRIMARY_REJECTED_CACHE": "0",
        "APP_USERS_PATH": os.path.join(tmp, "auth.json"),
        "HISTORICO_JOURNAL_DIR": os.path.join(tmp, "journal"),
        "MARKET_SNAPSHOT_PATH": os.path.join(tmp, "market.json"),
    }.items():
        os.environ[k] = v


def _pct(xs: List[float], p: float) -> float:
    ys = sorted(xs)
    if not ys:
        return float("nan")
    k = (len(ys) - 1) * p
    f = int(k)
    c = min(f + 1, len(ys) - 1)
    return ys[f] + (ys[c] - ys[f]) * (k - f)


def _stats(xs: List[float]) -> Dict[str, float]:
    if not xs:
        return {"avg": float("nan"), "p50": float("nan"), "p95": float("nan"), "p99": float("nan")}
    return {"avg": round(statistics.mean(xs), 2), "p50": round(_pct(xs, .5), 2),
            "p95": round(_pct(xs, .95), 2), "p99": round(_pct(xs, .99), 2)}


# ── siembra ───────────────────────────────────────────────────────────────
def _tir_objetivo(code: str) -> float:
    from backend.services import pricing
    m = pricing.bond_meta(code) or {}
    mon = (m.get("moneda") or "").upper()
    aj = (m.get("ajuste_sobre_capital") or "").upper()
    if "A3500" in aj:
        return 0.06
    if mon in ("USD", "USB"):
        return 0.10
    if "CER" in aj or "UVA" in aj:
        return 0.10
    return 0.32


def _precio_para(code: str, memo: Dict[str, Optional[float]]) -> Optional[float]:
    """Precio de pantalla (base de la ficha nativa) a una TIR plausible."""
    from backend.services import pricing
    if code in memo:
        return memo[code]
    calc = pricing.native_dollar_code(code) or code
    px: Optional[float] = None
    try:
        m = pricing.compute_metrics(calc, "tir", _tir_objetivo(calc), include_cashflows=False)
        v = m.get("precio_mercado_pct")
        if not m.get("error") and v is not None and v == v and v > 0:
            px = float(v)
    except Exception:  # noqa: BLE001 — una ficha que no valúa queda sin precio
        px = None
    memo[code] = px
    return px


def sembrar(n_simbolos: int, plazos=("24hs", "CI")) -> Dict[str, Any]:
    import random

    from backend.services import curves, marketdata_store, pricing, symbols as syms
    st = marketdata_store.get_store()
    tbl = curves.build_curve_codes()
    codes = sorted({c for v in tbl.values() for c in v})
    memo: Dict[str, Optional[float]] = {}
    rnd = random.Random(7)
    ts = "2026-09-30T14:00:00-03:00"
    con_precio = 0
    for c in codes:
        px = _precio_para(c, memo)
        if px is None:
            continue
        con_precio += 1
        m = pricing.bond_meta(c) or {}
        if m.get("moneda") in ("USD", "USB") and c[-1:] not in ("C", "D"):
            px = px * 1400.0                  # especie pesos de un hard-dollar
        nv = rnd.uniform(1e5, 5e9)
        md = {
            "LA": {"price": round(px, 3), "size": 1000, "date": ts},
            "CL": {"price": round(px * 0.995, 3), "date": "2026-09-29"},
            "OP": {"price": round(px * 0.997, 3)}, "HI": {"price": round(px * 1.004, 3)},
            "LO": {"price": round(px * 0.993, 3)},
            "EV": {"size": nv * px / 100.0}, "NV": {"size": nv},
            "BI": [{"price": round(px * (1 - 0.002 * k), 3), "size": 1e5 * k} for k in range(1, 6)],
            "OF": [{"price": round(px * (1 + 0.002 * k), 3), "size": 1e5 * k} for k in range(1, 6)],
        }
        for pl in plazos:
            st.update_from_md(syms.md_symbol(c, pl), md)
    for base in ("GD30", "AL30", "GD35", "AL35"):              # patas FX: CCL / MEP implícitos
        pc = _precio_para(base + "C", memo) or _precio_para(base + "D", memo)
        if pc is None:
            continue
        for pl in plazos:
            st.update_from_md(syms.md_symbol(base, pl), {"LA": {"price": pc * 1400, "date": ts}, "CL": {"price": pc * 1400 * .99}, "EV": {"size": 1e9}, "NV": {"size": 1e6}})
            st.update_from_md(syms.md_symbol(base + "C", pl), {"LA": {"price": pc, "date": ts}, "CL": {"price": pc * .99}, "EV": {"size": 2e7}, "NV": {"size": 1e6}})
            st.update_from_md(syms.md_symbol(base + "D", pl), {"LA": {"price": pc * 1.01, "date": ts}, "CL": {"price": pc * .995}, "EV": {"size": 1e7}, "NV": {"size": 1e6}})
    i = 0
    while len(st.symbols()) < n_simbolos:                       # relleno sin ficha
        for pl in plazos:
            st.update_from_md(f"MERV - XMEV - BENCH{i:04d} - {pl}", {
                "LA": {"price": 100 + i / 100, "size": 100, "date": ts}, "CL": {"price": 99.0},
                "BI": [{"price": 99, "size": 1000}], "OF": [{"price": 101, "size": 1000}],
                "EV": {"size": 1e6}, "NV": {"size": 1e4}})
        i += 1
    return {"curvas": {k: len(v) for k, v in tbl.items()}, "bonos_con_precio": con_precio,
            "simbolos": len(st.symbols())}


def calentar(plazos=("24hs", "CI")) -> int:
    from backend.services import curves, warmup
    n = 0
    for pl in plazos:
        for v in curves.build_curve_codes().values():
            for c in v:
                if warmup._warm_code(c, pl):
                    n += 1
    return n


# ── medición ──────────────────────────────────────────────────────────────
_muestra: contextvars.ContextVar = contextvars.ContextVar("bench_muestra")


def _app_medida(app):
    async def medida(scope, receive, send):
        stat = _muestra.get()
        t0 = time.perf_counter()

        async def send_medido(message):
            if message["type"] == "http.response.body":
                stat["wire"] += len(message.get("body", b""))
                if not message.get("more_body", False):
                    stat["ms"] = (time.perf_counter() - t0) * 1000
            await send(message)
        await app(scope, receive, send_medido)
    return medida


def _cliente(app):
    import httpx

    class Cliente(httpx.AsyncClient):
        async def request(self, *a, **k):
            stat = {"wire": 0, "ms": float("nan")}
            token = _muestra.set(stat)
            try:
                r = await super().request(*a, **k)
                r.extensions.update(stat)
                return r
            finally:
                _muestra.reset(token)
    return Cliente(transport=httpx.ASGITransport(app=_app_medida(app)), base_url="http://127.0.0.1",
                   headers={"Accept-Encoding": "gzip"})


async def correr(args) -> Dict[str, Any]:
    from backend.main import app
    from backend.routes import curves as rc
    from backend.services import curves, marketdata_store, symbols as syms
    store = marketdata_store.get_store()
    tbl = curves.build_curve_codes()
    curva = args.curve if args.curve in tbl else next(iter(tbl))
    codes = tbl[curva]
    code = args.code or next((c for c in codes if c.endswith("D")), codes[0])
    sym = syms.md_symbol(code, "24hs")
    modos = set(args.solo.split(",")) if args.solo else set(_MODOS)
    n = args.n
    filas: List[Dict[str, Any]] = []

    def emitir(rec: Dict[str, Any]) -> None:
        filas.append(rec)
        s = rec
        extra = ""
        if "wave_ms" in s:
            extra = (f"  onda p95 {s['wave_ms']['p95']:8.2f}  lag p95 {s['lag_ms']['p95']:6.2f}"
                     f"  gzip/onda {s['wire_per_wave']:>9,d}")
        elif "raw_bytes" in s:
            extra = f"  {s['raw_bytes']:>9,d} / {s['wire_bytes']:>8,d} B"
        print(f"{s['label']:<24} {s['mode']:<5} {s['n']:>5}  avg {s['avg']:7.2f}  p50 {s['p50']:7.2f}"
              f"  p95 {s['p95']:7.2f}  p99 {s['p99']:7.2f}{extra}", flush=True)

    casos: List[Tuple[str, str, str, Optional[dict], bool]] = [
        ("seq", "GET", "/market/seq", None, False),
        ("yas_recompute", "POST", "/yas/recompute", {"code": code, "value": "90", "mode": "precio"}, False),
        ("curves", "GET", f"/curves/table?curve={curva}", None, True),
        ("market_top30", "GET", f"/mercado/table?curve={curva}", None, True),
        ("market_all", "GET", f"/mercado/table?curve={curva}&mas=1", None, True),
        ("book", "GET", f"/mercado/book/{code}", None, True),
        ("yas_market", "GET", f"/yas/market?code={code}", None, True),
        ("forwards", "GET", "/forwards/table?curve=lecap", None, True),
        ("graficos", "GET", f"/graficos/data?curve={curva}", None, True),
        ("rail", "GET", "/dolares/rail", None, True),
        ("tape", "GET", "/tape", None, True),
        ("breakeven_table", "GET", "/breakeven/table", None, True),
        ("excel_snapshot", "GET", "/excel/v1/snapshot", None, False),
        ("excel_hist_full", "GET", "/excel/v1/hist/a3500", None, False),
        ("excel_hist_365", "GET", "/excel/v1/hist/a3500?days=365", None, False),
    ]
    async with _cliente(app) as ac:
        print(f"{'endpoint':<24} {'modo':<5} {'n':>5}  {'ms server-side (avg / p50 / p95 / p99)':<44}  bytes crudo / gzip")
        if modos & {"warm", "tick"}:
            for label, method, url, data, live in casos:
                for _ in range(2):
                    r = await ac.request(method, url, data=data)
                    r.raise_for_status()
                for modo in [m for m in ("warm", "tick") if m in modos and (live or m == "warm")]:
                    ts, wire = [], []
                    for i in range(n):
                        if modo == "tick":
                            store.update_from_md(sym, {"NV": 100000 + i})
                        r = await ac.request(method, url, data=data)
                        r.raise_for_status()
                        ts.append(r.extensions["ms"])
                        wire.append(r.extensions["wire"])
                    emitir(dict(label=label, mode=modo, url=url, n=n, **_stats(ts), raw_bytes=len(r.content),
                                wire_bytes=round(statistics.mean(wire)), encoding=r.headers.get("content-encoding")))
        seq0, _rows, _meta, order = await rc._rows_en_seq(curva, "24hs", True, "native", "byma", "", 1)
        if "delta" in modos:
            for cambios in (1, 30):
                ts, wire, full = [], [], 0
                for i in range(n):
                    since = store.seq()
                    for c in codes[:cambios]:
                        store.update_from_md(syms.md_symbol(c, "24hs"), {"NV": 150000 + i})
                    r = await ac.get(f"/mercado/rows?curve={curva}&mas=1&since={since}&order={order}")
                    r.raise_for_status()
                    ts.append(r.extensions["ms"])
                    wire.append(r.extensions["wire"])
                    full += r.headers.get("X-Full") == "1"
                emitir(dict(label=f"delta_{cambios}", mode="tick", n=n, **_stats(ts), raw_bytes=len(r.content),
                            wire_bytes=round(statistics.mean(wire)), x_full=full, x_rows=r.headers.get("X-Rows")))
        if "burst" in modos:
            C, W = args.clients, args.waves
            for modo in ("delta1", "delta30", "paneles", "excel", "curvas"):
                ts, totales, lags, wires = [], [], [], []
                for i in range(W):
                    since = store.seq()
                    for c in codes[:30 if modo == "delta30" else 1]:
                        store.update_from_md(syms.md_symbol(c, "24hs"), {"NV": 200000 + i})
                    url_delta = f"/mercado/rows?curve={curva}&mas=1&since={since}&order={order}"
                    if modo.startswith("delta"):
                        urls = [url_delta] * C
                    elif modo == "excel":
                        urls = ["/excel/v1/snapshot"] * C
                    elif modo == "curvas":
                        urls = [f"/curves/table?curve={curva}"] * C
                    else:
                        base = [f"/curves/table?curve={curva}", f"/mercado/book/{code}", f"/yas/market?code={code}"]
                        urls = (base * (C // 3 + 1))[:C]

                    async def uno(u):
                        r = await ac.get(u)
                        r.raise_for_status()
                        return r.extensions["ms"], r.extensions["wire"]
                    parar = False

                    async def latido():
                        while not parar:
                            t = time.perf_counter()
                            await asyncio.sleep(.001)
                            lags.append(max(0.0, (time.perf_counter() - t) * 1000 - 1))
                    h = asyncio.create_task(latido())
                    await asyncio.sleep(0)
                    t = time.perf_counter()
                    res = await asyncio.gather(*(uno(u) for u in urls))
                    totales.append((time.perf_counter() - t) * 1000)
                    parar = True
                    await h
                    ts.extend(x[0] for x in res)
                    wires.append(sum(x[1] for x in res))
                emitir(dict(label=f"burst{C}_{modo}", mode="tick", n=len(ts), waves=W, **_stats(ts),
                            wave_ms=_stats(totales), lag_ms=_stats(lags), wire_per_wave=round(statistics.mean(wires))))
    return {"curva": curva, "code": code, "resultados": filas}


def comparar(a_path: str, b_path: str) -> None:
    a = json.load(open(a_path, encoding="utf-8"))
    b = json.load(open(b_path, encoding="utf-8"))
    ia = {(r["label"], r["mode"]): r for r in a["resultados"]}
    ib = {(r["label"], r["mode"]): r for r in b["resultados"]}
    print(f"{'caso':<30} {'p50 A':>8} {'p50 B':>8} {'Δ%':>7}   {'p95 A':>8} {'p95 B':>8} {'Δ%':>7}")
    for k in [k for k in ia if k in ib]:
        ra, rb = ia[k], ib[k]

        def d(x, y):
            return f"{(y - x) / x * 100:+6.1f}%" if x else "   n/a"
        print(f"{k[0] + ' ' + k[1]:<30} {ra['p50']:8.2f} {rb['p50']:8.2f} {d(ra['p50'], rb['p50']):>7}   "
              f"{ra['p95']:8.2f} {rb['p95']:8.2f} {d(ra['p95'], rb['p95']):>7}")
        if "wave_ms" in ra and "wave_ms" in rb:
            print(f"{'   onda p95 / lag p95':<30} {ra['wave_ms']['p95']:8.2f} {rb['wave_ms']['p95']:8.2f} "
                  f"{d(ra['wave_ms']['p95'], rb['wave_ms']['p95']):>7}   {ra['lag_ms']['p95']:8.2f} {rb['lag_ms']['p95']:8.2f} "
                  f"{d(ra['lag_ms']['p95'], rb['lag_ms']['p95']):>7}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=100, help="requests por caso (default 100)")
    ap.add_argument("--waves", type=int, default=100, help="ondas por ráfaga (default 100)")
    ap.add_argument("--clients", type=int, default=24, help="clientes simultáneos por onda (default 24)")
    ap.add_argument("--symbols", type=int, default=2000, help="tamaño del store (default 2000)")
    ap.add_argument("--curve", default="corp_hdmep")
    ap.add_argument("--code", default=None, help="instrumento del libro / YAS (default: primer …D de la curva)")
    ap.add_argument("--solo", default="", help="subconjunto: warm,tick,delta,burst")
    ap.add_argument("--json", default=None, help="archivo de salida para --compare")
    ap.add_argument("--slo", type=float, default=None, help="exit 1 si un p95 de 1 cliente pasa este umbral (ms)")
    ap.add_argument("--no-gc", action="store_true", help="no aplicar el gc.freeze / umbrales del lifespan")
    ap.add_argument("--compare", nargs=2, metavar=("ANTES", "DESPUES"))
    args = ap.parse_args(argv)
    if args.compare:
        comparar(*args.compare)
        return 0
    if args.solo and (set(args.solo.split(",")) - set(_MODOS)):
        ap.error(f"--solo acepta {', '.join(_MODOS)}")
    tmp = tempfile.mkdtemp(prefix="bench_tick_")
    _entorno(tmp)
    import logging
    logging.disable(logging.WARNING)
    t0 = time.perf_counter()
    from backend import consola
    from backend.services import bond_universe
    bond_universe.ensure_loaded()
    t_univ = time.perf_counter() - t0
    siembra = sembrar(args.symbols)
    t1 = time.perf_counter()
    n_warm = calentar()
    t_warm = time.perf_counter() - t1
    if not args.no_gc:
        # El mismo GC que deja el lifespan (freeze del estado de larga vida +
        # umbrales altos): sin esto las ráfagas muestran las pausas gen-2 de
        # ~100 ms que en producción no existen (p99 de todos los casos).
        import gc
        gc.collect()
        gc.freeze()
        gc.set_threshold(10_000, 20, 100)
    print(f"universo {t_univ:.1f} s · {siembra['bonos_con_precio']} bonos con precio · {siembra['simbolos']} símbolos "
          f"· warm {n_warm} métricas en {t_warm:.1f} s · python {platform.python_version()} · {platform.platform()}")
    out = asyncio.run(correr(args))
    out.update({"version": consola.version(), "python": platform.python_version(), "platform": platform.platform(),
                "n": args.n, "waves": args.waves, "clients": args.clients, "siembra": siembra,
                "fecha": time.strftime("%Y-%m-%d %H:%M")})
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)
        print(f"→ {args.json}")
    if args.slo is not None:
        lentos = [r for r in out["resultados"] if "wave_ms" not in r and r["p95"] > args.slo]
        if lentos:
            print(f"SLO {args.slo:.0f} ms superado: " + ", ".join(f"{r['label']} {r['mode']} p95 {r['p95']}" for r in lentos))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
