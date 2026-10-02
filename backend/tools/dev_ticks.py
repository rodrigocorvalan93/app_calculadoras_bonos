"""Server de desarrollo con precios SINTÉTICOS sembrados + TICKS continuos,
para mirar / medir los paneles live sin broker (parpadeos, flashes, delta por
filas): siembra todos los bonos de las curvas y las acciones / CEDEARs como
`bench_tick`, y un hilo mueve cada ~1 s ~40 símbolos al azar (precio ±0,3 %,
tamaños de punta con distinta cantidad de dígitos, volumen creciente) → el seq
del store avanza y app.js dispara `md-update` en todas las pestañas abiertas.

    python backend/tools/dev_ticks.py <puerto> [intervalo_s]

Abrir http://127.0.0.1:<puerto>/mercado (o cualquier panel live). Auth
apagada y host loopback (el guard de arranque lo permite). Nunca contra una
base real: es sólo para el navegador. Medición automática del parpadeo:
`backend/tools/flicker_probe.py`."""
from __future__ import annotations

import logging
import os
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AUTH_ENABLED", "0")
os.environ.setdefault("APP_HOST", "127.0.0.1")
os.environ.setdefault("PRIMARY_REJECTED_CACHE", "0")
logging.getLogger().setLevel(logging.WARNING)

from backend.main import app  # noqa: E402
from backend.services import bond_universe, curves, marketdata_store, symbols as syms  # noqa: E402

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SIZES = [500, 5000, 12000, 123000, 1500000, 25000000]   # distinta cantidad de dígitos → ancho de celda


def _ts() -> str:
    return str(int(datetime.now(_TZ).timestamp() * 1000))


def _px(c: str) -> float:
    return 95.0 + (sum(map(ord, c)) * 7 % 900) / 10


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    intervalo = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    bond_universe.ensure_loaded()
    store = marketdata_store.get_store()
    estado: dict = {}

    def md(sym: str, px: float, bsz: int, osz: int, ev: float, nv: float, tv: int) -> None:
        store.update_from_md(sym, {"LA": {"price": px, "size": 1000, "date": _ts()}, "CL": {"price": px * 0.995},
                                  "BI": [{"price": px * 0.999, "size": bsz}, {"price": px * 0.998, "size": bsz * 2}],
                                  "OF": [{"price": px * 1.001, "size": osz}, {"price": px * 1.002, "size": osz + 2000}],
                                  "OP": px * 0.99, "HI": px * 1.01, "LO": px * 0.98, "EV": ev, "NV": nv, "TV": tv})

    def seed(sym: str, px: float) -> None:
        estado[sym] = {"px": px, "bsz": 5000, "osz": 7000, "ev": 2e7, "nv": 2e5, "tv": 120}
        md(sym, px, 5000, 7000, 2e7, 2e5, 120)

    n = 0
    for codes in curves.build_curve_codes().values():
        for c in codes:
            seed(syms.md_symbol(c, "24hs"), _px(c)); n += 1
    try:
        from backend.services import equities
        for c in equities.LIDERES + equities.GENERAL + equities.CEDEARS:
            seed(syms.md_symbol(c, "24hs"), _px(c) * 40); n += 1
        store.update_from_md("MERV - XMEV - I.MERVAL - 24hs", {"IV": {"price": 2_000_000.0, "date": _ts()},
                                                              "CL": {"price": 1_974_000.0}, "OP": 1_980_000.0,
                                                              "HI": 2_010_000.0, "LO": 1_970_000.0})
    except Exception as exc:  # noqa: BLE001
        print("equities:", exc)
    print(f"sembrados {n} símbolos · tick cada {intervalo:g} s · http://127.0.0.1:{port}/mercado", flush=True)

    def ticker() -> None:
        rnd = random.Random(7)
        todos = list(estado)
        while True:
            time.sleep(intervalo)
            for sym in rnd.sample(todos, min(40, len(todos))):
                e = estado[sym]
                e["px"] *= 1 + rnd.uniform(-0.003, 0.003)
                e["bsz"] = rnd.choice(SIZES); e["osz"] = rnd.choice(SIZES)
                e["ev"] *= 1 + rnd.uniform(0, 0.4); e["nv"] *= 1 + rnd.uniform(0, 0.4); e["tv"] += 1
                md(sym, e["px"], e["bsz"], e["osz"], e["ev"], e["nv"], e["tv"])

    threading.Thread(target=ticker, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
