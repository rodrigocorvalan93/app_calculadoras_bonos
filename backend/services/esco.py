"""Código de ESCO (cartera) → ficha del bono en el universo (18/11).

El sistema de carteras (ESCO) no nombra a los bonos como el mercado:

- un bono en dólares va con su ticker de PESOS, y con una "D" atrás cuando la
  contabilidad del fondo es en dólares: `GD30` / `GD30D`, `TTCDO` / `TTCDOD`.
  El "…D" es una especie aparte en ESCO (mismo ISIN, descripción + " D"), no
  la pata MEP: `GD30D` de ESCO es el global en un fondo dólar, y su ficha
  nativa es `GD30C` (paga cable);
- no distingue dólar MEP (USB) de cable (USD);
- a veces ni siquiera usa el ticker: `YPF34` es `YM34O`, `YLUZ2` es `YFC2O`.

La app valúa cada bono con UNA ficha nativa (`…C` cable / `…D` MEP), y los
tickers no siguen siempre "O pesos / D MEP / C cable" (`BPOC7` ↔ `BPC7D`), así
que jugar con sufijos no alcanza. Se concilia por DATO:

1. **ISIN.** La composición trae `IsinCode` por fila (y la Base RF de
   `Delta - Especies` tiene una fila por código de ESCO, de respaldo). Se
   buscan las fichas del universo con ese ISIN. Como `especies.py` arrastra
   ISINs repetidos entre series (GD29 / GD30, VSCV / VSCX), el grupo se parte
   por vencimiento + cupón y, si quedan varios bonos, se elige el que comparte
   raíz con el código o con el ticker de la base; si no se puede elegir UNO,
   no se resuelve (nunca se adivina).
   Dentro del bono: la ficha NATIVA (`…C` / `…D` en dólares). Si hay más de una
   decide la moneda de pago de la base (USB → …D, USD → …C), después el ticker
   de la base, y recién al final el parecido de ticker (BPOA8D → BPA8D).
2. **Ticker de la base** (`CAFCI_BYMA` / `BYMA`) cuando no hay ISIN utilizable
   y ese ticker tiene ficha.
3. **Sufijo**, último recurso: el código es una especie en pesos CON ficha en
   dólares más una "D" / "C" (`GD29D` → `GD29` → `GD29C`).

Un código que ya tiene ficha propia no pasa por acá (`AL30D`, `BA37D`,
`GD30`): sigue como siempre. Todo en memoria, memoizado por código.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.services import bond_universe

_DOLAR = ("USD", "USB")
_RE_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_SUFIJO_PAGO = {"USB": "D", "USD": "C"}

VIAS = {
    "isin": "mismo ISIN que la ficha",
    "ticker": "ticker de la base de especies",
    "sufijo": "especie en pesos con ficha + sufijo de ESCO",
}


@dataclass(frozen=True)
class Ficha:
    """Ficha del universo que corresponde a un código de ESCO."""
    calc: str                       # código de la ficha (la nativa si es hard-dollar)
    via: str                        # isin | ticker | sufijo
    isin: Optional[str] = None
    pago: Optional[str] = None      # USD (cable) / USB (MEP) según la base
    nota: str = ""                  # algo que conviene mirar (no impide resolver)


def isin_ok(v: Any) -> Optional[str]:
    """ISIN con formato estándar (12 caracteres), o None: 'Sin_Isin_FCI',
    'PENDIENTE', 'AO29' y demás marcadores no sirven para conciliar."""
    if v is None:
        return None
    s = str(v).strip().upper()
    return s if _RE_ISIN.match(s) else None


def _pago(v: Any) -> Optional[str]:
    s = str(v or "").strip().upper()
    return s if s in _DOLAR else None


def _clase_pago(v: Any) -> Optional[str]:
    """'dolar' / 'pesos' según la columna Pago de la cartera o de la base
    ('USD', 'USB', 'en Dólares' · 'ARS', 'en Pesos'); None si no dice nada."""
    s = str(v or "").strip().upper().replace("Ó", "O")
    if s in ("USD", "USB", "EN DOLARES", "DOLARES"):
        return "dolar"
    if s in ("ARS", "EN PESOS", "PESOS", "$"):
        return "pesos"
    return None


def _tk(v: Any) -> Optional[str]:
    s = " ".join(str(v or "").split()).upper()
    return s if s and s not in ("NC", "NAN", "NONE") else None


def _moneda(code: str) -> str:
    return str(getattr(bond_universe.get(code), "moneda", "") or "").upper()


def es_dolar(code: Optional[str]) -> bool:
    """¿La ficha `code` es de un bono hard-dollar (Moneda USD / USB)?"""
    return bool(code) and _moneda(code) in _DOLAR


def _es_nativa(code: str) -> bool:
    return code[-1:] in ("C", "D") and _moneda(code) in _DOLAR


def _es_dirty(code: str) -> bool:
    return str(getattr(bond_universe.get(code), "quote_price_cnv", "") or "").upper() == "DIRTY"


# ── índice ISIN → fichas ────────────────────────────────────────────────────
_lock = threading.Lock()
_idx: Tuple[Any, Dict[str, List[str]]] = (None, {})
_memo: Tuple[Any, Dict[tuple, Tuple[Optional[Ficha], str]]] = (None, {})


def _token_universo() -> tuple:
    bond_universe.ensure_loaded()
    objs = bond_universe._objs or {}
    return (id(objs), len(objs))


def token() -> tuple:
    """Cambia cuando cambia el universo de bonos o se recarga la base de
    especies: keyea los memos que dependen de la conciliación."""
    try:
        from backend.services import delta_especies
        gen = delta_especies.generacion()
    except Exception:  # noqa: BLE001
        gen = 0
    return (_token_universo(), gen)


def _indice() -> Dict[str, List[str]]:
    """ISIN → códigos del universo con ese ISIN, sin las patas calculadas
    (`…j` CER proyectado / `…v` TAMAR de un dual: comparten ISIN con su base y
    nunca son la tenencia)."""
    global _idx
    tok = _token_universo()
    if _idx[0] == tok:
        return _idx[1]
    with _lock:
        if _idx[0] == tok:
            return _idx[1]
        todos = set(bond_universe.all_codes())
        out: Dict[str, List[str]] = {}
        for c in sorted(todos):
            if c[-1:] in ("j", "v") and c[:-1] in todos:
                continue
            i = isin_ok(getattr(bond_universe.get(c), "isin", None))
            if i:
                out.setdefault(i, []).append(c)
        _idx = (tok, out)
        return out


def _bonos(cands: List[str]) -> List[List[str]]:
    """Parte un grupo de fichas del mismo ISIN en BONOS reales (vencimiento +
    cupón): GD29 / GD29C y GD30 / GD30C comparten ISIN en la data."""
    g: Dict[tuple, List[str]] = {}
    for c in cands:
        o = bond_universe.get(c)
        g.setdefault((str(getattr(o, "vencimiento", None)),
                      str(getattr(o, "cupon_spread", None))), []).append(c)
    return list(g.values())


def _raiz(code: str) -> str:
    """Código sin la "D" / "C" que agrega ESCO (`TTCDOD` → `TTCDO`; también
    `GN47O C`, con espacio)."""
    c = code.upper().strip()
    return c[:-1].rstrip() if c[-1:] in ("D", "C") and len(c) > 3 else c


def _elegir(grupo: List[str], code: str, pago: Optional[str],
            tickers: List[str]) -> Tuple[Optional[str], str]:
    """La ficha de UN bono que valúa la tenencia → (código, nota)."""
    nativas = [c for c in grupo if _es_nativa(c)]
    # La nativa que valúa es la DIRTY: CO32D / CO35D terminan en "D" pero son
    # la referencia CLEAN de CO32DC / CO35DC.
    nativas = [c for c in nativas if _es_dirty(c)] or nativas
    if nativas:
        if len(nativas) == 1:
            n = nativas[0]
            suf = _SUFIJO_PAGO.get(pago or "")
            nota = ""
            if suf and not n.endswith(suf):
                nota = f"la base dice pago {pago} y la ficha nativa es {n}"
            return n, nota
        suf = _SUFIJO_PAGO.get(pago or "")
        sub = [c for c in nativas if suf and c.endswith(suf)]
        if len(sub) == 1:
            return sub[0], ""
        pool = sub or nativas
        for t in tickers:
            if t in pool:
                return t, ""
        from backend.services import pricing
        n = pricing._mas_parecido(_raiz(code), pool)
        return n, "elegida por parecido de ticker entre " + ", ".join(sorted(pool))
    if len(grupo) == 1:
        return grupo[0], ""
    for t in tickers:
        if t in grupo:
            return t, ""
    r = _raiz(code)
    if r in grupo:
        return r, ""
    return None, "varias fichas con ese ISIN y ninguna coincide con el código: " + ", ".join(sorted(grupo))


def _resolver(code: str, isin: Any, pago: Any, ticker: Any) -> Tuple[Optional[Ficha], str]:
    if bond_universe.get(code) is not None:
        return None, "ficha propia"
    base: Dict[str, Any] = {}
    try:
        from backend.services import delta_especies
        base = delta_especies.info_cod(code) or {}
    except Exception:  # noqa: BLE001 — sin base se sigue con lo que trae la cartera
        base = {}
    isin_ = isin_ok(isin) or isin_ok(base.get("ISIN"))
    pago_ = _pago(pago) or _pago(base.get("Pago"))
    clase = _clase_pago(pago) or _clase_pago(base.get("Pago"))

    def _ok(f: Ficha) -> Tuple[Optional[Ficha], str]:
        """Último control antes de asignar: la cartera y la ficha tienen que
        coincidir en pesos vs dólares. Si no, una de las dos está mal y no se
        elige por ella (queda sin ficha, con el motivo en /admin)."""
        if clase == "pesos" and es_dolar(f.calc):
            return None, (f"contradicción: la cartera dice que paga en pesos y la ficha del mismo "
                          f"ISIN ({f.calc}) es en dólares")
        if clase == "dolar" and not es_dolar(f.calc):
            return None, (f"contradicción: la cartera dice que paga en dólares y la ficha del mismo "
                          f"ISIN ({f.calc}) es en pesos")
        return f, ""
    tickers = [t for t in dict.fromkeys(_tk(x) for x in (ticker, base.get("CAFCI_BYMA"), base.get("BYMA")))
               if t and t != code.upper()]
    motivo = "sin ISIN en la cartera ni en la base" if not isin_ else ""

    # 1) ISIN
    if isin_:
        cands = _indice().get(isin_) or []
        if not cands:
            motivo = f"ninguna ficha de especies.py tiene el ISIN {isin_}"
        else:
            grupos = _bonos(cands)
            grupo: Optional[List[str]] = grupos[0] if len(grupos) == 1 else None
            if grupo is None:
                raices = {code.upper(), _raiz(code)} | set(tickers)
                hits = [g for g in grupos if raices & set(g)]
                if len(hits) == 1:
                    grupo = hits[0]
                else:
                    # el código y el ticker apuntan a bonos distintos (o a
                    # ninguno): no se adivina, ni por ticker ni por sufijo
                    return None, (f"el ISIN {isin_} está en varias fichas de bonos distintos ("
                                  + ", ".join(sorted(cands)) + ") y el código no dice cuál")
            r = _raiz(code)
            if bond_universe.get(r) is not None and r not in grupo:
                return None, (f"contradicción: el código apunta a la ficha {r} y el ISIN {isin_} "
                              "es de " + ", ".join(sorted(grupo)))
            calc, nota = _elegir(grupo, code, pago_, tickers)
            if calc:
                return _ok(Ficha(calc, "isin", isin_, pago_, nota))
            return None, nota

    from backend.services import pricing
    # 2) ticker de la base (sin ISIN utilizable)
    # Con un ISIN válido que ninguna ficha tiene, el ticker sólo vale si es
    # del mismo papel que el código (misma raíz): CO27D con ticker CO32D no.
    for t in tickers:
        if isin_ and _raiz(t) != _raiz(code):
            continue
        tt = bond_universe.resolve(t)
        if tt and bond_universe.get(tt) is not None:
            calc = (pricing.native_dollar_code(tt) or tt) if es_dolar(tt) else tt
            return _ok(Ficha(calc, "ticker", isin_, pago_, motivo))

    # 3) sufijo de ESCO sobre una especie en pesos con ficha en dólares
    p = _raiz(code)
    if p != code.upper().strip():
        if bond_universe.get(p) is not None and es_dolar(p) and p[-1:] not in ("C", "D"):
            calc = pricing.native_dollar_code(p) or p
            return _ok(Ficha(calc, "sufijo", isin_, pago_, motivo))
    return None, motivo or "sin ficha"


def _memo_get(code: Any, isin: Any, pago: Any, ticker: Any) -> Tuple[Optional[Ficha], str]:
    global _memo
    if not code:
        return None, ""
    code = str(code).strip()
    key = (code, isin, pago, ticker)
    tok = token()
    if _memo[0] != tok:
        _memo = (tok, {})
    m = _memo[1]
    hit = m.get(key)
    if hit is None:
        try:
            hit = _resolver(code, isin, pago, ticker)
        except Exception as exc:  # noqa: BLE001 — una fila rara no rompe Posiciones
            hit = (None, f"{type(exc).__name__}: {exc}")
        if len(m) > 20000:
            m.clear()
        m[key] = hit
    return hit


def resolver(code: Any, isin: Any = None, pago: Any = None, ticker: Any = None) -> Optional[Ficha]:
    """Ficha del universo para un código de ESCO SIN ficha propia, o None (ya
    tiene ficha, o no se pudo conciliar con certeza). `isin` / `pago` /
    `ticker` son los de la fila de la cartera (IsinCode, Pago, CAFCI_BYMA)."""
    return _memo_get(code, isin, pago, ticker)[0]


def resolver_h(h: Dict[str, Any]) -> Optional[Ficha]:
    """Lo mismo para una tenencia de `services.positions`."""
    return resolver(h.get("cod_delta"), h.get("isin"), h.get("pago"), h.get("ticker"))


def motivo(h: Dict[str, Any]) -> str:
    """Por qué una tenencia no se concilió (para /admin)."""
    return _memo_get(h.get("cod_delta"), h.get("isin"), h.get("pago"), h.get("ticker"))[1]


_CAJA = frozenset({"$", "ARS", "PESOS", "USD", "USB", "DOLARES", "DOLAR", "CABLE", "MEP", "CCL", "NC"})


def _es_rv(code: str) -> bool:
    try:
        from backend.services import delta_especies
        return delta_especies.info_rv(code) is not None
    except Exception:  # noqa: BLE001
        return False


def diagnostico(holdings: List[Dict[str, Any]], etiqueta_fondo=None) -> Dict[str, Any]:
    """Para /admin: cómo quedó cada código de ESCO.
      - `resueltos`: código → ficha, por qué vía, con qué ISIN, en qué fondos;
      - `sin_resolver`: bonos en dólares (Pago USD / USB) sin ficha y por qué;
      - `isin_distinto`: códigos CON ficha propia cuyo ISIN de la cartera no es
        el de la ficha (ISIN mal cargado en especies.py, o un código de ESCO
        que choca con el ticker de otro bono)."""
    res: Dict[str, Dict[str, Any]] = {}
    sin: Dict[str, Dict[str, Any]] = {}
    dist: Dict[str, Dict[str, Any]] = {}

    def _acum(d: Dict[str, Dict[str, Any]], code: str, h: Dict[str, Any], **extra: Any) -> None:
        r = d.setdefault(code, {"code": code, "especie": h.get("especie"), "isin": isin_ok(h.get("isin")),
                                "pago": _pago(h.get("pago")), "valor": 0.0, "n_filas": 0,
                                "fondos": set(), **extra})
        r["valor"] += h.get("valor") or 0.0
        r["n_filas"] += 1
        r["fondos"].add(h["cod_fondo"])

    for h in holdings:
        code = h.get("cod_delta")
        if not code:
            continue
        if bond_universe.get(code) is not None:
            hi = isin_ok(h.get("isin"))
            fi = isin_ok(getattr(bond_universe.get(code), "isin", None))
            if hi and fi and hi != fi:
                _acum(dist, code, h, isin_ficha=fi)
            continue
        f = resolver_h(h)
        if f is not None:
            _acum(res, code, h, ficha=f.calc, via=f.via, via_txt=VIAS.get(f.via, f.via), nota=f.nota)
            continue
        mot = motivo(h)
        # Sin ficha: los bonos en dólares (y cualquier contradicción entre la
        # cartera y la ficha). Afuera la caja ('USD') y la renta variable.
        if not (_pago(h.get("pago")) or mot.startswith("contradicción")):
            continue
        if str(code).upper() in _CAJA or _es_rv(code):
            continue
        _acum(sin, code, h, motivo=mot)

    def _fin(d: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = sorted(d.values(), key=lambda x: -abs(x["valor"]))
        for r in rows:
            fs = sorted(r["fondos"])
            r["n_fondos"] = len(fs)
            lab = etiqueta_fondo or (lambda c: str(c))
            r["fondos"] = ", ".join(lab(x) for x in fs[:3]) + (" …" if len(fs) > 3 else "")
        return rows

    return {"resueltos": _fin(res), "sin_resolver": _fin(sin), "isin_distinto": _fin(dist),
            "n_resueltos": len(res), "n_sin_resolver": len(sin), "n_isin_distinto": len(dist)}
