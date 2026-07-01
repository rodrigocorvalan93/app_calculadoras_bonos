"""Especie ad-hoc — construir un `rentafija.Bono` desde una ficha PEGADA (dict
estilo `especies.py`) o GENERADA por formulario, calcular en vivo (metrics +
cashflow) y, opcionalmente, PERSISTIR en `especies.py`.

Punto clave de diseño (y de performance): el motor de cálculo NO depende de
`especies.py` ni del universo. Un `Bono` se arma desde un dict plano y todo el
pipeline de `pricing.compute_metrics` (vía `obj_override`) opera sobre esa
instancia. Por eso la especie ad-hoc:

  * NO se agrega al universo → NO entra a curvas / posiciones / warmup,
  * NO suma NADA al tiempo de arranque (se arma en el request y se descarta),
  * reusa el 90 % del pipeline de YAS.

La ficha viva se guarda en un store en memoria acotado (LRU por token) sólo para
no re-pegarla entre recomputes; se descarta sola. `guardar()` (acción deliberada
del usuario) es lo único que toca el disco: agrega el dict + el wrapper
`CODE = rentafija.Bono(CODE)` al final de `especies.py` (patrón del skill
`carga-bonos-rentafija`), previa validación.

Parseo de ficha pegada: `ast.literal_eval` NO evalúa la aritmética de listas que
usan las fichas (`[0]*6 + [4] + [8]*12`), así que usamos un evaluador de AST
restringido que permite SÓLO literales + `+ - *` sobre números/listas/tuplas.
Nada de nombres, llamadas, atributos, indexado, etc.
"""
from __future__ import annotations

import ast
import secrets
import textwrap
import threading
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
_ESPECIES_PATH = REPO_ROOT / "especies.py"

# ── Store en memoria (LRU acotado por token) ─────────────────────────────────
_STORE_MAX = 64
_store: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_store_lock = threading.Lock()

# Códigos ya persistidos en esta corrida del proceso. `especies` no se recarga en
# vivo tras un append, así que `especie_existe` (que mira el módulo importado) NO
# vería el bono recién guardado → sin esto, un segundo click duplicaría el dict en
# el archivo. El lock hace atómico el chequear-y-escribir.
_save_lock = threading.Lock()
_saved_codes: set[str] = set()


def _put(ficha: Dict[str, Any]) -> str:
    token = secrets.token_hex(8)
    with _store_lock:
        _store[token] = ficha
        _store.move_to_end(token)
        while len(_store) > _STORE_MAX:
            _store.popitem(last=False)
    return token


def get_ficha(token: str) -> Optional[Dict[str, Any]]:
    with _store_lock:
        f = _store.get(token)
        if f is not None:
            _store.move_to_end(token)
    return f


# ── Parseo seguro de ficha pegada ────────────────────────────────────────────
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult)


def _eval_node(node: ast.AST) -> Any:
    """Evalúa un subconjunto seguro de AST: literales + `+ - *` sobre
    números/listas/tuplas. Cualquier otra cosa (Name, Call, Attribute,
    Subscript, comprehensions…) es rechazada."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        return {_eval_node(k): _eval_node(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.List):
        return [_eval_node(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e) for e in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval_node(node.operand)
        return +v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        return left * right   # Mult → habilita [0]*6, [8]*12
    raise ValueError(f"expresión no permitida en la ficha: {type(node).__name__}")


def parse_ficha(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Parsea una ficha pegada (dict estilo especies.py, con o sin `NAME = ` y
    con comentarios/aritmética de listas) → (nombre_opcional, dict).

    Acepta tanto `AL30D = { ... }` como sólo `{ ... }`. Toma el PRIMER dict que
    encuentra. Lanza ValueError con un mensaje claro si no hay dict o si contiene
    una expresión no permitida."""
    # dedent tolera un paste uniformemente indentado (copiado desde código); si
    # falla igual (indent mixto), reintenta con las líneas ya sin sangría.
    text = textwrap.dedent(text or "").strip()
    if not text:
        raise ValueError("Pegá una ficha (dict estilo especies.py).")
    try:
        tree = ast.parse(text, mode="exec")
    except (SyntaxError, IndentationError) as exc:
        try:
            tree = ast.parse("\n".join(ln.lstrip() for ln in text.splitlines()), mode="exec")
        except (SyntaxError, IndentationError):
            raise ValueError(f"No pude parsear la ficha (línea {exc.lineno}): {exc.msg}") from exc

    name: Optional[str] = None
    dict_node: Optional[ast.Dict] = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict):
            dict_node = stmt.value
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
            break
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Dict):
            dict_node = stmt.value
            break
    if dict_node is None:
        raise ValueError("No encontré un diccionario de ficha en el texto pegado.")

    ficha = _eval_node(dict_node)
    if not isinstance(ficha, dict) or "Código" not in ficha:
        raise ValueError("La ficha no tiene la clave 'Código'.")
    return name, ficha


# ── Armado de ficha desde formulario ─────────────────────────────────────────
def _pdate(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: {s!r} (usá DD/MM/AAAA).")


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _add_months(d: date, months: int) -> date:
    """Suma meses conservando el día (recorta a fin de mes si hace falta)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # último día del mes destino
    if m == 12:
        last = 31
    else:
        last = (date(y, m + 1, 1) - date(y, m, 1)).days
    return date(y, m, min(d.day, last))


def coupon_dates(emision: date, vencimiento: date, freq: int) -> List[date]:
    """Cronograma de cupones REGULAR anclado al vencimiento: venc, venc−step,
    … hasta el primero > emisión (primer período puede quedar de stub, lo maneja
    rentafija por dias_entre_cupones). `freq` = pagos/año (debe dividir a 12)."""
    if freq <= 0 or 12 % int(freq) != 0:
        raise ValueError("Frecuencia debe ser 1, 2, 3, 4, 6 o 12 pagos/año.")
    if vencimiento <= emision:
        raise ValueError("El vencimiento debe ser posterior a la emisión.")
    step = 12 // int(freq)
    dates: List[date] = []
    d = vencimiento
    while d > emision:
        dates.append(d)
        d = _add_months(d, -step)
    dates.sort()
    if not dates:
        raise ValueError("No se generó ningún cupón (revisá fechas/frecuencia).")
    return dates


def _amortizacion(tipo: str, n_cupones: int, valor_nominal: float,
                  cuotas_finales: int, custom: Optional[List[float]]) -> List[float]:
    """Lista de amortización (largo == n_cupones) que suma exactamente VN.
    BULLET → rentafija la sobreescribe, devolvemos placeholder. Custom tiene
    prioridad si viene. Si no, N cuotas iguales al final."""
    if tipo.upper() == "BULLET":
        return [0.0] * (n_cupones - 1) + [float(valor_nominal)]
    if custom:
        if len(custom) != n_cupones:
            raise ValueError(f"La amortización custom tiene {len(custom)} valores "
                             f"pero hay {n_cupones} cupones.")
        vals = [float(x) for x in custom]
    else:
        n = max(1, min(int(cuotas_finales or 1), n_cupones))
        cuota = float(valor_nominal) / n
        vals = [0.0] * (n_cupones - n) + [cuota] * n
    # corrección de redondeo en la última cuota no nula → suma == VN exacta
    diff = float(valor_nominal) - round(sum(vals), 8)
    for i in range(len(vals) - 1, -1, -1):
        if vals[i] != 0.0:
            vals[i] = round(vals[i] + diff, 8)
            break
    return vals


def build_ficha_from_form(p: Dict[str, Any]) -> Dict[str, Any]:
    """Arma un dict de ficha (formato especies.py) desde los campos del
    formulario. Soporta FIJA / VARIABLE / VARIABLE_CAP y ajustes CER/UVA/A3500.
    Cupón único (escalar) → sin step-up (el motor arma los intereses solo)."""
    codigo = (p.get("codigo") or "").strip().upper()
    if not codigo:
        raise ValueError("Falta el código/ticker.")
    if not codigo.isidentifier():
        raise ValueError("El código debe ser un identificador válido (letras/números, sin espacios).")

    emision = _pdate(p.get("emision"))
    vencimiento = _pdate(p.get("vencimiento"))
    if emision is None or vencimiento is None:
        raise ValueError("Emisión y Vencimiento son obligatorias (DD/MM/AAAA).")
    freq = int(float(p.get("frecuencia") or 2))
    fechas = coupon_dates(emision, vencimiento, freq)
    primer = _pdate(p.get("primer_cupon")) or fechas[0]

    vn = float(p.get("valor_nominal") or 100.0)
    tipo_amort = (p.get("tipo_amortizacion") or "BULLET").upper()
    custom_raw = (p.get("amortizacion_custom") or "").strip()
    custom = [float(x.replace(",", ".")) for x in custom_raw.replace(";", ",").split(",") if x.strip()] if custom_raw else None
    amort = _amortizacion(tipo_amort, len(fechas), vn, int(float(p.get("cuotas_finales") or 1)), custom)

    tipo_tasa = (p.get("tipo_tasa") or "FIJA").upper()
    index = (p.get("index") or "").strip().upper() or None
    ajuste = (p.get("ajuste") or "").strip().upper() or None
    if ajuste in ("NONE", "NINGUNO", ""):
        ajuste = None
    cupon = float(str(p.get("cupon") or 0).replace(",", "."))

    moneda = (p.get("moneda") or "ARS").strip().upper()
    clasificacion = (p.get("clasificacion") or "").strip()
    devengo = (p.get("convencion_devengamiento") or "Actual").strip()
    base = float(p.get("convencion_base") or 365)

    ficha: Dict[str, Any] = {
        "Nombre Security": (p.get("nombre") or codigo).strip(),
        "Código": codigo,
        "ISIN": (p.get("isin") or "").strip() or None,
        "Calificación": (p.get("calificacion") or "").strip() or None,
        "País": "Argentina",
        "Clasificación": clasificacion or None,
        "Industria": (p.get("industria") or "").strip() or None,
        "Legislación": (p.get("legislacion") or "").strip() or None,
        "Moneda": moneda,
        "Plazo habitual de liquidación: t +": float(p.get("plazo_liq") or 1),
        "Emisión": _fmt(emision),
        "Vencimiento": _fmt(vencimiento),
        "Fecha Primer Cupón": _fmt(primer),
        "Cupón / Spread": cupon,
        "Step-up": False,
        "Frecuencia de pago de cupón anual": float(freq),
        "Convención fechas de pago": "Regular",
        "Convención de devengamiento": devengo,
        "Convención Base": base,
        "Tipo de Amortización": tipo_amort,
        "Tipo Tasa Interés": tipo_tasa,
        "Index": index,
        "Días Lag índice desde inc": int(float(p.get("lag_desde") or 0)),
        "Días Lag índice hasta inc": int(float(p.get("lag_hasta") or 0)),
        "Valor Nominal": vn,
        "Ajuste sobre Capital": ajuste,
        "Factor Capitalización": float(p.get("factor_capitalizacion") or 1.0),
        "Días lag Ajuste base": int(float(p.get("lag_ajuste_base") or -10)),
        "Días lag Ajuste": int(float(p.get("lag_ajuste") or -10)),
        "Fechas de cupón": [_fmt(d) for d in fechas],
        "Amortización": amort,
        "Quote Price Convention": (p.get("quote_price_cnv") or "DIRTY").strip().upper(),
        "Callable": False,
        "Tipo de Call": None,
        "Fecha Call": None,
        "Precio Call": None,
    }
    return ficha


# ── Construcción + validación del Bono ───────────────────────────────────────
def build_bono(ficha: Dict[str, Any]):
    """Construye el `rentafija.Bono` (valida amortización, fechas, etc.).
    Relanza cualquier error de construcción como ValueError legible."""
    import rentafija
    try:
        return rentafija.Bono(ficha)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"No se pudo construir el bono: {exc}") from exc


def register(ficha: Dict[str, Any]) -> Tuple[str, str]:
    """Valida (construyendo el Bono) y guarda la ficha en el store en memoria.
    Devuelve (token, codigo). NO toca el disco."""
    build_bono(ficha)                       # valida; si falla, lanza ValueError
    token = _put(ficha)
    return token, str(ficha.get("Código"))


def compute(token: str, mode: str, value: float, settle: Optional[str] = None,
            fx_override: Optional[float] = None, freq_override: Optional[int] = None,
            base_override: Optional[int] = None) -> Dict[str, Any]:
    """Corre el cálculo en vivo sobre la ficha ad-hoc del `token`. Reusa
    `pricing.compute_metrics` vía `obj_override` → mismo output que YAS."""
    from backend.services import pricing
    ficha = get_ficha(token)
    if ficha is None:
        return {"error": "La ficha expiró o no existe. Volvé a cargarla."}
    try:
        bono = build_bono(ficha)
    except ValueError as exc:
        return {"error": str(exc)}
    return pricing.compute_metrics(
        code=str(ficha.get("Código")),
        mode=mode, value=value, settle=settle,
        fx_override=fx_override, freq_override=freq_override, base_override=base_override,
        obj_override=bono,
    )


def meta_from_ficha(ficha: Dict[str, Any]) -> Dict[str, Any]:
    """Meta liviana para el encabezado (sin depender de bond_meta, que cachea por
    código del universo)."""
    return {
        "codigo": ficha.get("Código"),
        "nombre": ficha.get("Nombre Security"),
        "moneda": ficha.get("Moneda"),
        "vencimiento": ficha.get("Vencimiento"),
        "emision": ficha.get("Emisión"),
        "tipo_tasa_interes": ficha.get("Tipo Tasa Interés"),
        "index": ficha.get("Index") or "",
        "ajuste_sobre_capital": ficha.get("Ajuste sobre Capital") or "",
        "frecuencia": ficha.get("Frecuencia de pago de cupón anual"),
        "tipo_amortizacion": ficha.get("Tipo de Amortización"),
        "convencion_base": ficha.get("Convención Base"),
        "quote_price_cnv": ficha.get("Quote Price Convention") or "",
        "calificacion": ficha.get("Calificación") or "",
        "callable": ficha.get("Callable", False),
        "legislacion": ficha.get("Legislación") or "",
    }


# ── Persistencia a especies.py (acción deliberada) ───────────────────────────
def _ficha_source(name: str, ficha: Dict[str, Any]) -> str:
    """Serializa la ficha a código Python estilo especies.py + el wrapper
    `NAME = rentafija.Bono(NAME)`. Usa repr() por valor → seguro y round-trippable."""
    lines = [f"{name} = {{"]
    for k, v in ficha.items():
        lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    lines.append(f"{name} = rentafija.Bono({name})")
    return "\n".join(lines)


def especie_existe(name: str) -> bool:
    """True si `name` ya está definido en el módulo especies o ya se guardó en esta
    corrida (evita pisar y hace que el botón Guardar desaparezca tras persistir)."""
    if name in _saved_codes:
        return True
    try:
        import especies
        return hasattr(especies, name)
    except Exception:  # noqa: BLE001
        return False


def guardar(token: str) -> Dict[str, Any]:
    """Agrega la ficha del token al FINAL de especies.py (dict + wrapper Bono),
    previa validación y chequeo de colisión de nombre. Acción deliberada del
    usuario; no se dispara sola. No recarga el universo del proceso vivo (para
    eso alcanza la ficha en memoria); persiste para el próximo arranque."""
    ficha = get_ficha(token)
    if ficha is None:
        return {"ok": False, "error": "La ficha expiró o no existe."}
    name = str(ficha.get("Código") or "").strip()
    if not name.isidentifier():
        return {"ok": False, "error": f"Código {name!r} no es un identificador Python válido."}
    build_bono(ficha)                       # revalida antes de escribir
    block = "\n\n# --- Especie ad-hoc agregada desde la app ---\n" + _ficha_source(name, ficha) + "\n"
    with _save_lock:                        # chequear-y-escribir atómico → sin duplicados
        if name in _saved_codes or especie_existe(name):
            return {"ok": False, "error": f"Ya existe una especie '{name}' en especies.py."}
        try:
            with open(_ESPECIES_PATH, "a", encoding="utf-8") as fh:
                fh.write(block)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"No pude escribir especies.py: {exc}"}
        _saved_codes.add(name)
    return {"ok": True, "codigo": name,
            "msg": f"'{name}' agregada a especies.py. Estará en el universo tras reiniciar la app."}
