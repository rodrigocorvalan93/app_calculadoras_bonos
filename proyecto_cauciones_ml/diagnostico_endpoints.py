# -*- coding: utf-8 -*-
"""diagnostico_endpoints.py

Sondea qué endpoints históricos expone la xOMS de Matrizoms para
cauciones BYMA. Imprime la respuesta cruda de cada uno para poder
decidir cuál usar en el extractor.

Uso:
    python diagnostico_endpoints.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import OMSapi  # noqa: E402
import OMSsecrets  # noqa: E402
import OMSsettings as cfg  # noqa: E402
import os  # noqa: E402


SYMBOL = "MERV - XMEV - PESOS - 1D"

# Buscar el último viernes (hoy es jueves 2026-05-14 → viernes pasado fue 2026-05-08)
def last_friday(d: date) -> date:
    delta = (d.weekday() - 4) % 7
    return d - timedelta(days=delta or 7)


def dump(label: str, r) -> None:
    print("\n" + "═" * 70)
    print(f"  {label}")
    print(f"  URL : {r.request.url}")
    print(f"  HTTP: {r.status_code}   bytes={len(r.content)}")
    print("─" * 70)
    try:
        body = r.json()
    except ValueError:
        print(r.text[:800])
        return
    s = json.dumps(body, indent=2, ensure_ascii=False, default=str)
    # No spamear si la lista es enorme — recortar
    print(s[:2500] + ("\n…[truncado]" if len(s) > 2500 else ""))


def main() -> None:
    OMSsecrets.load()
    user = os.getenv("OMS_USER") or os.getenv("XOMS_USER")
    pwd = os.getenv("OMS_PASS") or os.getenv("XOMS_PASS")
    if not user or not pwd:
        raise SystemExit("Faltan OMS_USER / OMS_PASS en secrets.")
    s = OMSapi.login(user, pwd)

    d = last_friday(date.today())
    d_prev = d - timedelta(days=1)
    print(f"\nSímbolo: {SYMBOL}")
    print(f"Probando con fecha viernes: {d}\n")

    base = cfg.BASE_URL

    # 1) rest/data/getTrades (el que usamos hoy)
    r = s.get(f"{base}rest/data/getTrades",
              params={"marketId": "ROFX", "symbol": SYMBOL,
                      "dateFrom": d.isoformat(), "dateTo": d.isoformat()},
              timeout=20)
    dump("1) rest/data/getTrades   dateFrom=dateTo=ese viernes", r)

    # 2) Mismo endpoint pero rango más ancho (a veces dateTo es exclusivo)
    r = s.get(f"{base}rest/data/getTrades",
              params={"marketId": "ROFX", "symbol": SYMBOL,
                      "dateFrom": d_prev.isoformat(),
                      "dateTo": (d + timedelta(days=1)).isoformat()},
              timeout=20)
    dump("2) rest/data/getTrades   rango ±1 día", r)

    # 3) externalTrades  (algunos brokers exponen ésta)
    r = s.get(f"{base}rest/data/getTrades",
              params={"marketId": "ROFX", "symbol": SYMBOL,
                      "dateQuery": d.isoformat()},
              timeout=20)
    dump("3) rest/data/getTrades   dateQuery=hoy", r)

    # 4) Snapshot live (control: debería traer market data ahora)
    r = s.get(f"{base}rest/marketdata/get",
              params={"marketId": "ROFX", "symbol": SYMBOL,
                      "entries": "LA,BI,OF,EV,TV,NV", "depth": 1},
              timeout=20)
    dump("4) rest/marketdata/get   (control live)", r)

    # 5) Variante histórica alternativa que algunos xOMS exponen
    for path in [
        "rest/marketdata/historic",
        "rest/data/historicTrades",
        "rest/data/getHistoricTrades",
        "rest/data/trades",
    ]:
        try:
            r = s.get(f"{base}{path}",
                      params={"marketId": "ROFX", "symbol": SYMBOL,
                              "dateFrom": d.isoformat(), "dateTo": d.isoformat()},
                      timeout=20)
            dump(f"5) {path}", r)
        except Exception as e:
            print(f"\n   ✗ {path}: {type(e).__name__}: {e}")

    # 6) Listar segments / instruments — ver si la xOMS tiene la
    #    instancia del símbolo o pide otro marketId
    r = s.get(f"{base}rest/instruments/details",
              params={"marketId": "ROFX", "symbol": SYMBOL},
              timeout=20)
    dump("6) rest/instruments/details  (qué metadata tiene)", r)


if __name__ == "__main__":
    main()
