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
# Índice Merval (si el broker lo sirve; símbolo crudo, sin plazo). Desde el
# 22/10 el índice es el MSCI Merval y el ticker nuevo es MMSCI (desk): van
# primero sus variantes (con y sin el prefijo I. de índice, con y sin plazo);
# las de I.MERVAL quedan por si el broker las sigue publicando — manda la que
# el feed actualiza (merval_snapshot), no el orden de esta tupla.
# Tokens que identifican al índice en el string del broker: el ticker nuevo
# (MMSCI), el viejo (MERVAL) y las grafías con "MSCI" que un endpoint podría
# usar (I.MSCI, "MSCI MERVAL", MSCIMERVAL). "MSCI" a secas NO: sería un CEDEAR
# de MSCI Inc. si BYMA lo listara.
INDICE_TOKENS = ("MMSCI", "MERVAL", "I.MSCI", "MSCI MERVAL", "MSCIMERVAL")
MERVAL_SYMBOLS = ("MERV - XMEV - MMSCI - 24hs", "MERV - XMEV - MMSCI - CI",
                  "MERV - XMEV - MMSCI", "MMSCI",
                  "MERV - XMEV - I.MMSCI - 24hs", "MERV - XMEV - I.MMSCI - CI",
                  "MERV - XMEV - I.MMSCI", "I.MMSCI",
                  "MERV - XMEV - I.MERVAL - 24hs", "MERV - XMEV - I.MERVAL - CI",
                  "MERV - XMEV - I.MERVAL", "I.MERVAL")


def es_simbolo_indice(symbol: str) -> bool:
    """¿Es (una variante de) el índice — MSCI Merval `MMSCI` o el viejo
    `I.MERVAL` — bajo el string que use el broker? Lo usan el escaneo de
    candidatos del store y el seed del WS con el universo real del broker."""
    u = (symbol or "").upper()
    return any(t in u for t in INDICE_TOKENS)


def panel_tickers(panel: str) -> List[str]:
    """Membresía VIVA del panel (BYMA Open Data, refresh diario desde el
    lifespan) con fallback a la lista curada: sin red, la app queda igual
    que siempre. Ver byma_paneles."""
    from backend.services import byma_paneles
    dyn = byma_paneles.tickers(panel)
    if dyn:
        if panel == "cedears":
            # la lista viva viene COMPLETA en orden de volumen (~1.300): el
            # panel default y el seed del WS se quedan con los top
            # CEDEARS_VIVOS_MAX + los curados siempre (un ETF líquido no
            # desaparece un finde sin volumen). El resto del universo queda
            # accesible on-demand vía cedears_view (buscador / "ver más").
            # Líder/General NO unionan: ahí la lista viva manda (una acción
            # que BYMA rota de panel debe moverse de tabla).
            vivos = dyn[:byma_paneles.CEDEARS_VIVOS_MAX]
            extra = [c for c in CEDEARS if c not in set(vivos)]
            return sorted(vivos + extra)
        return dyn
    return {"cedears": CEDEARS, "general": GENERAL}.get(panel, LIDERES)


def panel_map() -> Dict[str, str]:
    """{ticker: 'L' | 'G' | 'C'} de TODO lo suscripto (listas curadas ∪
    membresía viva). Líder gana sobre General y sobre CEDEAR si un ticker
    aparece en dos. Lo usa el histórico diario de acciones para etiquetar."""
    out: Dict[str, str] = {}
    for panel, curada, tag in (("lideres", LIDERES, "L"), ("general", GENERAL, "G"),
                               ("cedears", CEDEARS, "C")):
        for code in sorted(set(curada) | set(panel_tickers(panel))):
            out.setdefault(code, tag)
    return out


def cedears_universo() -> List[str]:
    """TODOS los CEDEARs conocidos: la lista viva completa (orden de volumen
    desc) + los curados que no estén en ella al final. Es una lista de NOMBRES
    (acá no se suscribe ni se tabula nada): alimenta el buscador global y las
    tandas de "ver más" del panel."""
    from backend.services import byma_paneles
    dyn = byma_paneles.tickers("cedears") or []
    en_dyn = set(dyn)
    return dyn + sorted(c for c in CEDEARS if c not in en_dyn)


def cedears_view(q: str = "", mas: int = 0) -> "tuple[List[str], List[str]]":
    """Vista extendida del panel CEDEARs: con `q` busca por substring en TODO
    el universo conocido; con `mas` agrega las siguientes N especies por
    volumen después del panel base. Devuelve (códigos a mostrar, códigos que
    NO están en el panel base) — el caller suscribe los segundos on demand
    (ws.subscribe es incremental: sólo la primera vez por símbolo)."""
    base = panel_tickers("cedears")
    en_base = set(base)
    if q.strip():
        qq = q.strip().upper()
        codes = [c for c in cedears_universo() if qq in c]
        return codes, [c for c in codes if c not in en_base]
    n = max(0, int(mas or 0))
    if n:
        extra = [c for c in cedears_universo() if c not in en_base][:n]
        return base + extra, extra
    return base, []


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
    return _row_from_snap(code, snap)


def _row_from_snap(code: str, snap) -> Dict[str, Any]:
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


def _finish_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Post-proceso común de las tablas de equities: fracción de volumen para
    la barrita + orden por volumen efectivo desc (sin volumen al final,
    alfabético)."""
    vmax = max((r.get("volume") or 0.0) for r in rows) if rows else 0.0
    for r in rows:
        r["volume_frac"] = (r.get("volume") or 0.0) / vmax if vmax > 0 else 0.0
    rows.sort(key=lambda r: (-(r["volume"] or 0.0), r["code"]))
    return rows


# Campos de una fila stub (código sin dato en el store todavía): los filtros
# es-AR renderizan None como "—", así que la fila aparece al instante y se
# llena sola cuando el feed contesta la suscripción (~1-2 s, md-update).
_STUB_KEYS = ("open", "close", "low", "high", "bid", "bid_size", "offer",
              "offer_size", "last", "vwap", "var_pct", "var_px", "volume",
              "nominal", "last_ts", "range_pos")


def rows_for_codes(codes: List[str], plazo: str = "24hs") -> List[Dict[str, Any]]:
    """Filas para una lista EXPLÍCITA de códigos (buscador / "ver más" de
    CEDEARs). Un código sin dato rinde una fila stub con guiones — el usuario
    VE que la especie existe y quedó suscripta, en vez de una tabla que no
    cambia."""
    rows: List[Dict[str, Any]] = []
    for c in codes:
        r = row_for(c, plazo)
        if r is None:
            r = {"code": c, **{k: None for k in _STUB_KEYS}}
        rows.append(r)
    return _finish_rows(rows)


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
    rows = _finish_rows(rows)
    if panel in ("lideres", "todas"):
        # El índice encabeza el panel de sus componentes (nivel + var del día,
        # como en el tape). Va DESPUÉS de _finish_rows: no entra en el orden por
        # volumen ni en la barrita de volumen, y el cliente lo deja fijado
        # arriba aunque ordene por otra columna (`data-pin`).
        m = merval_row()
        if m is not None:
            if panel == "todas":
                m["panel"] = "I"
            rows.insert(0, m)
    return rows


def merval_row() -> Optional[Dict[str, Any]]:
    """Fila del índice Merval para el panel líderes: nivel (IV → last), OCLH
    si el feed los manda y var vs cierre; sin puntas, VWAP ni volumen (no es
    un papel) y no abre libro. None si el índice todavía no llegó."""
    snap = merval_snapshot()
    if snap is None:
        return None
    r = _row_from_snap("MSCI Merval", snap)
    r.update({"bid": None, "bid_size": None, "offer": None, "offer_size": None, "vwap": None,
              "volume": None, "nominal": None, "volume_frac": 0.0, "indice": True})
    return r


_merval_sym = None                      # símbolo MERVAL elegido la última vez (diagnóstico)
# Candidatos descubiertos en el store (cualquier símbolo con 'MERVAL'): el
# escaneo de ~2k símbolos bajo el lock del store se hace una vez por cambio
# de tamaño del store o cada _MERVAL_RESCAN_S, nunca en cada render.
_merval_cands: Dict[str, Any] = {"n": -1, "at": 0.0, "syms": []}
_MERVAL_RESCAN_S = 30.0


def merval_candidatos() -> List[str]:
    """Símbolos del store que son el índice (MSCI Merval `MMSCI` / viejo
    `I.MERVAL`): las variantes conocidas más cualquier otro string con esos
    tokens que mande el broker (`es_simbolo_indice`)."""
    import time as _t
    store = mds.get_store()
    n = store.stats().get("symbols") if hasattr(store, "stats") else None
    now = _t.time()
    c = _merval_cands
    if c["n"] != n or now - c["at"] > _MERVAL_RESCAN_S:
        vistos = list(MERVAL_SYMBOLS)
        for s in store.symbols():
            if es_simbolo_indice(s) and s not in vistos:
                vistos.append(s)
        c.update(n=n, at=now, syms=vistos)
    return c["syms"]


def merval_snapshot():
    """Snapshot del índice Merval: de TODAS las variantes que haya en el store
    (`merval_candidatos`), la que el feed actualizó más recientemente
    (`updated_at`), prefiriendo las que tienen `last` (el IV) sobre las que
    sólo traen un cierre. Antes se memoizaba la PRIMERA variante con dato y se
    la usaba para siempre: con '… I.MERVAL - 24hs' en el store con un cierre
    viejo (persistido, o una CL suelta) y el broker publicando el IV en vivo
    bajo otro string, el panel, el tape e Inicio mostraban el índice clavado
    mientras las acciones se movían (desk, 14/10). Un snapshot restaurado
    del disco conserva su `updated_at` original, así que pierde contra uno
    vivo. Costo: ≤ 5 lookups por render."""
    global _merval_sym
    store = mds.get_store()
    mejor = None
    mejor_k = None
    for s in merval_candidatos():
        snap = store.get(s)
        if snap is None or (snap.last is None and snap.close is None):
            continue
        k = (1 if snap.last is not None else 0, float(snap.updated_at or 0.0))
        if mejor is None or k > mejor_k:
            mejor, mejor_k = snap, k
    _merval_sym = mejor.symbol if mejor is not None else None
    return mejor


def merval_diag() -> Dict[str, Any]:
    """Qué variantes del índice hay en el store y cuál se está usando
    (/market/diag): para ver en la máquina del desk bajo qué string manda
    el broker el IV y si alguna quedó con un cierre viejo."""
    store = mds.get_store()
    out = []
    for s in merval_candidatos():
        snap = store.get(s)
        if snap is None:
            continue
        out.append({"symbol": s, "last": snap.last, "close": snap.close, "last_ts": snap.last_ts,
                    "updated_at": snap.updated_at, "seq": snap.seq})
    el = merval_snapshot()
    return {"elegido": el.symbol if el is not None else None, "variantes": out}
