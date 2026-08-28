"""Acciones y CEDEARs — monitor de precios BYMA (sin calculadora).

Listas curadas de tickers (panel líderes + CEDEARs líquidos). Se suscriben al
WS del broker en el arranque igual que los bonos; las filas salen del store en
memoria (OCLH, last, var, VWAP, book, volumen) — son acciones: NO hay
TIR/duration, así que cada fila es puro lookup (~µs), sin pasar por pricing.

EWZ y SPY además alimentan la barra superior con su variación "vista en cable":
    var_cable = (1 + var_ars) / (1 + var_ccl) − 1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services import marketdata_store as mds, symbols as syms

# Listas CURADAS y editables (BYMA rota la composición de los paneles ~1x/año;
# ajustar acá). Un ticker que no cotiza — o ya no existe — simplemente no
# aparece en la tabla: agregar de más es inocuo, faltar es invisible.
# Panel líderes BYMA (ARS).
LIDERES: List[str] = [
    "GGAL", "YPFD", "PAMP", "ALUA", "BBAR", "BMA", "BYMA", "CEPU", "COME",
    "CRES", "EDN", "IRSA", "LOMA", "METR", "MIRG", "SUPV", "TECO2", "TGNO4",
    "TGSU2", "TRAN", "TXAR", "VALO", "TEN", "AGRO",
]
# Panel general BYMA (ARS) — el resto de las acciones locales con mercado.
GENERAL: List[str] = [
    "AUSO", "BHIP", "BOLT", "BPAT", "CADO", "CAPX", "CARC", "CECO2", "CELU",
    "CGPA2", "CTIO", "DGCU2", "DOME", "DYCA", "FERR", "FIPL", "GAMI", "GARO",
    "GBAN", "GCLA", "GRIM", "HARG", "HAVA", "INTR", "INVJ", "LEDE", "LONG",
    "MOLA", "MOLI", "MORI", "OEST", "PATA", "POLL", "RIGO", "ROSE", "SAMI",
    "SEMI", "GCDI",
]
# CEDEARs (ARS; el subyacente cotiza en USD afuera). Los ~80 más operados:
# ETFs, tech, ADRs argentinos, Brasil, bancos, energía, consumo y salud.
CEDEARS: List[str] = [
    # ETFs
    "SPY", "EWZ", "QQQ", "DIA", "IWM", "XLE", "XLF", "EEM", "ARKK",
    # ADRs argentinos
    "VIST", "GLOB", "ARCO", "DESP", "BIOX",
    # Tech / growth
    "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "MELI", "AMD",
    "NFLX", "INTC", "CSCO", "IBM", "ORCL", "CRM", "ADBE", "QCOM", "AVGO",
    "MU", "PYPL", "UBER", "ABNB", "PLTR", "SNOW", "SHOP", "SPOT", "COIN",
    "MSTR", "TSM", "BABA", "JD", "NIO",
    # Brasil
    "PBR", "VALE", "ITUB", "BBD", "ABEV",
    # Financieras
    "BRKB", "JPM", "V", "MA", "BAC", "C", "WFC", "GS", "MS", "AXP",
    # Energía / materiales
    "XOM", "CVX", "OXY", "SLB", "HAL", "FCX", "RIO", "BHP", "GOLD", "NEM",
    "AA", "X",
    # Industriales / autos
    "GE", "CAT", "DE", "BA", "MMM", "F", "GM",
    # Consumo
    "KO", "DIS", "WMT", "COST", "MCD", "SBUX", "NKE", "HD", "PG", "PEP",
    # Salud / telco
    "PFE", "JNJ", "MRK", "ABBV", "LLY", "UNH", "GILD", "BMY", "T", "VZ",
]
# Índice Merval (si el broker lo sirve; símbolo crudo, sin plazo).
MERVAL_SYMBOLS = ("MERV - XMEV - I.MERVAL - 24hs", "MERV - XMEV - I.MERVAL - CI",
                  "MERV - XMEV - I.MERVAL", "I.MERVAL")


def panel_tickers(panel: str) -> List[str]:
    """Membresía VIVA del panel (BYMA Open Data, refresh diario desde el
    lifespan) con fallback a la lista curada: sin red, la app queda igual
    que siempre. Ver byma_paneles."""
    from backend.services import byma_paneles
    dyn = byma_paneles.tickers(panel)
    if dyn:
        return dyn
    return {"cedears": CEDEARS, "general": GENERAL}.get(panel, LIDERES)


def all_symbols() -> List[str]:
    """Símbolos a suscribir en el WS (24hs + CI + Merval): la UNIÓN de las
    listas curadas y la membresía viva ya conocida — el refresher del
    lifespan re-llama esto tras cada refresh y suscribe la diferencia."""
    out: List[str] = []
    vistos = set()
    for panel, curada in (("lideres", LIDERES), ("general", GENERAL), ("cedears", CEDEARS)):
        for code in set(curada) | set(panel_tickers(panel)):
            if code in vistos:
                continue
            vistos.add(code)
            out.append(syms.md_symbol(code, "24hs"))
            out.append(syms.md_symbol(code, "CI"))
    out.extend(MERVAL_SYMBOLS)
    return out


def _var(last: Optional[float], close: Optional[float]) -> Optional[float]:
    if last is None or close in (None, 0):
        return None
    return last / close - 1.0


def row_for(code: str, plazo: str = "24hs") -> Optional[Dict[str, Any]]:
    """Fila de precio puro desde el store (sin TIR). None si nunca cotizó."""
    snap = mds.get_store().get(syms.md_symbol(code, plazo))
    if snap is None:
        return None
    var = _var(snap.last, snap.close)
    range_pos = None
    if snap.last is not None and snap.low is not None and snap.high is not None and snap.high > snap.low:
        range_pos = max(0.0, min(1.0, (snap.last - snap.low) / (snap.high - snap.low)))
    return {
        "range_pos": range_pos,
        "code": code,
        "open": snap.open, "close": snap.close, "low": snap.low, "high": snap.high,
        "bid": snap.bid, "bid_size": snap.bid_size,
        "offer": snap.offer, "offer_size": snap.offer_size,
        "last": snap.last, "vwap": snap.vwap(),
        "var_pct": (var * 100.0) if var is not None else None,   # en pp, como mercado
        "var_px": (snap.last - snap.close) if (snap.last is not None and snap.close is not None) else None,
        "volume": snap.volume, "nominal": snap.nominal,
        "last_ts": snap.last_ts,
    }


def panel_rows(panel: str, plazo: str = "24hs") -> List[Dict[str, Any]]:
    if panel == "todas":
        # Líder + General en una tabla, con badge L/G por fila. Dedupe por si
        # las fuentes mixtas (viva + curada) solapan un ticker: gana Líder.
        rows: List[Dict[str, Any]] = []
        vistos: set = set()
        for p, tag in (("lideres", "L"), ("general", "G")):
            for c in panel_tickers(p):
                if c in vistos:
                    continue
                vistos.add(c)
                if (r := row_for(c, plazo)) is not None:
                    r["panel"] = tag
                    rows.append(r)
    else:
        rows = [r for c in panel_tickers(panel) if (r := row_for(c, plazo)) is not None]
    vmax = max((r.get("volume") or 0.0) for r in rows) if rows else 0.0
    for r in rows:
        r["volume_frac"] = (r.get("volume") or 0.0) / vmax if vmax > 0 else 0.0
    # Orden: volumen efectivo descendente; sin volumen al final, alfabético.
    rows.sort(key=lambda r: (-(r["volume"] or 0.0), r["code"]))
    return rows


_merval_sym = None                      # símbolo MERVAL resuelto (memo)


def merval_snapshot():
    """Snapshot del índice Merval. Prueba las variantes conocidas y, si ninguna
    pega, ESCANEA el store por cualquier símbolo que contenga 'MERVAL' — robusto al
    formato exacto que mande el broker (los índices no siempre llegan con el string
    esperado, que era por qué el 'MERVAL US$' del tape no aparecía)."""
    global _merval_sym
    store = mds.get_store()
    # símbolo ya descubierto: lookup directo — el escaneo de ~2k símbolos
    # (bajo el lock del store, disputado con el thread del feed) corría en
    # CADA render del tape porque el fallback ES el caso común.
    if _merval_sym:
        snap = store.get(_merval_sym)
        if snap is not None and (snap.last is not None or snap.close is not None):
            return snap
    for s in MERVAL_SYMBOLS:
        snap = store.get(s)
        if snap is not None and (snap.last is not None or snap.close is not None):
            _merval_sym = s
            return snap
    for s in store.symbols():                       # fallback: cualquier I.MERVAL del feed
        if "MERVAL" in s.upper():
            snap = store.get(s)
            if snap is not None and (snap.last is not None or snap.close is not None):
                _merval_sym = s
                return snap
    return None
