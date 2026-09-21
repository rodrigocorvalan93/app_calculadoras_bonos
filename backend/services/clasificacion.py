"""Clasificación fina de tenencias SIN ficha (pestaña Posiciones). Stdlib puro.

Una tenencia con ficha en `especies.py` se categoriza por la ficha
(`routes.posiciones._categoria`: CER / UVA / USD-Linked / USD / USB / Dual /
ARS Fija / ARS TAMAR …). Todo lo demás caía a la 'Clase de Activo' cruda del
Excel de carteras — y en Delta esa columna es gruesa: "Renta Fija" junta ONs
sin ficha, fideicomisos financieros, plazos fijos, cauciones, cheques, pagarés
y FCI cerrados (en Delta Ahorro, 47 % del PN en una sola línea). Acá se abre,
primer match gana:

  1. TIPO de instrumento por texto — fila de 'Delta - Especies' si el ticker
     está en la base (Subclase / Clase de Activo / Industria / Sector Delta),
     descripción de la cartera (columna Especie) y Clase de Activo del Excel:
     plazo fijo · caución · cheque (garantizado / no garantizado) · pagaré
     (ídem) · fideicomiso financiero (con su grupo de tasa: TAMAR/BADLAR ·
     CER/UVA · Tasa Fija · USD-Linked · USD) · FCI (money market · cerrado ·
     otro).
  2. Ajuste × Tasa de 'Delta - Especies' (la regla del legacy OMSposiciones):
     ONs y subsoberanos sin ficha → las MISMAS etiquetas que las fichas
     ('ARS TAMAR', 'ARS Fija', 'CER', 'USD-Linked', …), así un ON TAMAR sin
     ficha suma al mismo grupo que los que sí la tienen.
  3. Clase de Activo inferida (CEDEARs / Acciones / FCI / Liquidez) o cruda —
     lo de siempre. Una fila de 'Liquidez' con un código que no es caja
     ("$", "USD"…) se lee como FCI money market (Delta valúa los FCI de
     liquidez con cuotapartes y ticker; la caja no tiene ticker).

Devuelve también la FUENTE de la decisión (ficha / base / texto / clase) —
Posiciones la muestra como tooltip para que el desk vea qué falta cargar en
la base. Strings cortos + regex precompiladas: ~µs por tenencia.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

# Campos de la base Delta - Especies en los que puede venir el TIPO de
# instrumento (texto libre del desk: "Fideicomiso Financiero", "FCI Cerrado"…).
_COLS_TIPO = ("Subclase de Activo", "Clase de Activo", "Industria",
              "Sub Industria", "Sector Delta")

# Fuentes de la categoría (para el tooltip de Posiciones).
FUENTES = {
    "ficha": "Categoría por la ficha de especies.py",
    "base": "Categoría por Delta - Especies (tipo de instrumento o Ajuste × Tasa de la base)",
    "texto": "Categoría por la descripción de la cartera (columna Especie)",
    "clase": "Categoría por la Clase de Activo del Excel de cartera",
    "sin_regla": "Sin regla fina: Categoría = Clase de Activo cruda del Excel. Completá Ajuste/Tasa "
                 "en Delta - Especies o pasame la descripción para agregar la regla.",
}

# Tokens sobre texto NORMALIZADO (mayúsculas, sin tildes, sólo [A-Z0-9] y
# espacios) — \b funciona porque todo lo demás ya es espacio.
_RE_PF = re.compile(r"\bPLAZOS? ?FIJOS?\b|\bP ?FIJO\b|\bPFIJO\b|\bPF\b")
_RE_CAUCION = re.compile(r"\bCAUCION(ES)?\b|\bCAUC\b")
_RE_CHEQUE = re.compile(r"\bCHEQUES?\b|\bCPD\b|\bECHEQS?\b|\bCHPD\b|\bCH ?P ?D\b")
_RE_PAGARE = re.compile(r"\bPAGARES?\b")
_RE_FF = re.compile(r"\bFIDEICOMISOS?\b|\bFID\b|\bFF\b|\bVDF[A-Z]?\b|\bVRD[A-Z]?\b|\bTDF\b")
_RE_FCI = re.compile(r"\bFCI\b|\bFONDOS? COMUN(ES)?\b|\bFONDOS?\b|\bCUOTAPARTES?\b")
_RE_FCI_MM = re.compile(r"\bMONEY ?MARKET\b|\bMM\b|\bT 0\b|\bMERCADO DE DINERO\b|\bLIQUIDEZ\b")
_RE_FCI_CERRADO = re.compile(r"\bCERRADOS?\b|\bFCIC\b|\bFCC\b")
_RE_NO_GARANT = re.compile(r"\b(NO|SIN) (GARANT[A-Z]*|AVAL[A-Z]*|GTIA)\b|\bNG\b")
_RE_GARANT = re.compile(r"\bGARANT[A-Z]*\b|\bGTIA\b|\bAVAL[A-Z]*\b|\bSGR\b")
_RE_TAMAR_BADLAR = re.compile(r"\bTAMAR\b|\bBADLAR\b")
_RE_CER_UVA = re.compile(r"\bCER\b|\bUVA\b")
_RE_DLK = re.compile(r"\bDLK\b|\bDOLAR LINKED\b|\bUSD LINKED\b|\bA3500\b")
_RE_USD = re.compile(r"\bUSD\b|\bUSB\b|\bHARD DOL[A-Z]*\b|\bMEP\b|\bCABLE\b|\bDOLARES\b")
_RE_FIJA = re.compile(r"\bFIJA\b")

# Códigos que Delta usa para CAJA en filas de Liquidez (no son FCI).
_CODIGOS_CAJA = {"$", "ARS", "PESOS", "USD", "USB", "DOLARES", "DOLAR", "CABLE",
                 "MEP", "CCL", "CAJA", "CTA", "CUENTA", "DISPONIBILIDADES", "NC"}

# Etiquetas cuya tasa es fija por naturaleza (descuento / tasa pactada).
_FIJA_POR_NATURALEZA = frozenset({
    "Plazos Fijos", "Plazos Fijos UVA", "Caución", "Cheques", "Cheques Garantizados",
    "Cheques No Garantizados", "Pagarés", "Pagarés Garantizados", "Pagarés No Garantizados",
})


def _s(v: Any) -> str:
    """str limpio de un valor de Excel/pandas: None / NaN / 'nan' / 'NC' → ''."""
    if v is None:
        return ""
    try:
        if isinstance(v, float) and v != v:
            return ""
    except TypeError:
        pass
    s = str(v).strip()
    return "" if s.lower() in ("", "nan", "none", "nc") else s


def _norm(s: Any) -> str:
    """MAYÚSCULAS sin tildes, todo lo que no es alfanumérico → espacio, y un
    espacio a cada lado para matchear tokens con \\b sin sorpresas."""
    t = _s(s)
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t).strip()
    return f" {t} " if t else ""


def tipo_instrumento(txt: str) -> Optional[str]:
    """'PF' · 'CAUCION' · 'CHEQUE' · 'PAGARE' · 'FF' · 'FCI' · None. Orden fijo:
    lo más específico primero (un "FCI CERRADO … FIDEICOMISO" es un FCI)."""
    if not txt:
        return None
    if _RE_PF.search(txt):
        return "PF"
    if _RE_CAUCION.search(txt):
        return "CAUCION"
    if _RE_CHEQUE.search(txt):
        return "CHEQUE"
    if _RE_PAGARE.search(txt):
        return "PAGARE"
    if _RE_FCI.search(txt) and _RE_FCI_CERRADO.search(txt):
        return "FCI"
    if _RE_FF.search(txt):
        return "FF"
    if _RE_FCI.search(txt):
        return "FCI"
    return None


def _garantizado(txt: str) -> Optional[bool]:
    """True / False / None (no dice). 'NO GARANTIZADO' se chequea ANTES que
    'GARANTIZADO' — contiene el token."""
    if _RE_NO_GARANT.search(txt):
        return False
    if _RE_GARANT.search(txt):
        return True
    return None


def _grupo_ff(cat_tasa: Optional[str], txt: str) -> str:
    c = cat_tasa or ""
    if c in ("ARS TAMAR", "ARS BADLAR") or _RE_TAMAR_BADLAR.search(txt):
        return "Fideicomisos TAMAR/BADLAR"
    if c in ("CER", "UVA") or _RE_CER_UVA.search(txt):
        return "Fideicomisos CER/UVA"
    if c == "USD-Linked" or _RE_DLK.search(txt):
        return "Fideicomisos USD-Linked"
    if c in ("USD", "USB") or _RE_USD.search(txt):
        return "Fideicomisos USD"
    if c == "ARS Fija" or _RE_FIJA.search(txt):
        return "Fideicomisos Tasa Fija"
    return "Fideicomisos Financieros"


def etiqueta_tipo(tipo: Optional[str], txt: str, cat_tasa: Optional[str],
                  clase_liquidez: bool = False, txt_tasa: Optional[str] = None) -> Optional[str]:
    """Etiqueta de categoría para un tipo detectado. `txt` = TODO el texto
    disponible (base + descripción + clase) para garantía y tipo de FCI;
    `txt_tasa` = base + descripción SIN la Clase de Activo para el grupo de
    tasa (la clase 'Renta Fija' no vuelve 'Tasa Fija' a un fideicomiso)."""
    t_tasa = txt if txt_tasa is None else txt_tasa
    if tipo == "PF":
        return "Plazos Fijos UVA" if _RE_CER_UVA.search(t_tasa) else "Plazos Fijos"
    if tipo == "CAUCION":
        return "Caución"
    if tipo in ("CHEQUE", "PAGARE"):
        base = "Cheques" if tipo == "CHEQUE" else "Pagarés"
        g = _garantizado(txt)
        if g is None:
            return base
        return f"{base} Garantizados" if g else f"{base} No Garantizados"
    if tipo == "FF":
        return _grupo_ff(cat_tasa, t_tasa)
    if tipo == "FCI":
        if _RE_FCI_CERRADO.search(txt):
            return "FCI Cerrados"
        if clase_liquidez or _RE_FCI_MM.search(txt):
            return "FCI Money Markets"
        return "FCI"
    return None


def categoria_ajuste_tasa(ajuste: Any, tasa: Any) -> Optional[str]:
    """Categoría por Ajuste × Tasa de 'Delta - Especies' (regla del legacy
    OMSposiciones._categoria_bono), con las MISMAS etiquetas que las fichas.
    None si la base no dice nada usable (vacío / NC / desconocido)."""
    aj, ta = _s(ajuste), _s(tasa)
    aju = _norm(aj).strip()
    tau = _norm(ta).strip()
    if aju.startswith("DUAL"):
        if "TAMAR" in aju:
            if "CER" in aju:
                return "Dual CER / TAMAR"
            if "FIJA" in aju:
                return "Dual Fija / TAMAR"
            return "Dual / TAMAR"
        return aj
    if aju == "CER":
        return "CER"
    if aju == "UVA":
        return "UVA"
    if aju in ("USD LINKED", "DLK", "DOLAR LINKED", "A3500"):
        return "USD-Linked"
    if aju == "USD":
        return "USD"
    if aju == "USB":
        return "USB"
    por_tasa = {"FIJA": "ARS Fija", "TAMAR": "ARS TAMAR", "BADLAR": "ARS BADLAR",
                "STEP UP": "ARS Step Up", "STEPUP": "ARS Step Up"}
    if aju in ("ARS", "EN PESOS", "PESOS"):
        if tau in por_tasa:
            return por_tasa[tau]
        return "ARS (s/tasa)" if not tau else f"ARS {ta}"
    if not aju and tau in por_tasa:       # sólo Tasa cargada → es en pesos
        return por_tasa[tau]
    return None


def tasa_base(info: Optional[Dict[str, Any]]) -> Optional[str]:
    """'Fija' / 'TAMAR' / 'BADLAR' / 'Step Up' según la columna Tasa de la base."""
    t = _norm((info or {}).get("Tasa")).strip()
    return {"FIJA": "Fija", "TAMAR": "TAMAR", "BADLAR": "BADLAR",
            "STEP UP": "Step Up", "STEPUP": "Step Up"}.get(t)


def tasa_para(categoria: str, info: Optional[Dict[str, Any]]) -> str:
    """Tasa (cuadro 'Tasa' de la composición) de una tenencia sin ficha: la de
    la base si la hay; fija por naturaleza para PF / caución / cheques /
    pagarés; 'Variable' para un FF TAMAR/BADLAR sin base."""
    t = tasa_base(info)
    if t:
        return t
    if categoria in _FIJA_POR_NATURALEZA or categoria == "Fideicomisos Tasa Fija":
        return "Fija"
    if categoria == "Fideicomisos TAMAR/BADLAR":
        return "Variable"
    return "(sin clasif.)"


def calificacion_base(info: Optional[Dict[str, Any]]) -> Optional[str]:
    return _s((info or {}).get("Califica_Local")) or None


# Memo por (descripción, clase, código, campos usados de la base): Posiciones
# clasifica cada tenencia 2-3 veces por request (composición + tabla + targets)
# y la cartera no cambia entre refrescos — el regex corre una vez por tenencia
# y después es un lookup de dict (~1 µs). Acotado: se vacía al llenarse.
_COLS_MEMO = _COLS_TIPO + ("Ajuste", "Tasa")
_MEMO: Dict[Tuple[Any, ...], Tuple[str, str]] = {}
_MEMO_MAX = 4096


def clasificar(especie: Any, clase: Any, info: Optional[Dict[str, Any]] = None,
               codigo: Any = None) -> Tuple[str, str]:
    """→ (categoría, fuente) de una tenencia SIN ficha en especies.py.
    fuente ∈ 'base' · 'texto' · 'clase' · 'sin_regla' (ver FUENTES)."""
    key = (especie, clase, codigo, tuple(info.get(c) for c in _COLS_MEMO) if info else None)
    try:
        hit = _MEMO.get(key)
    except TypeError:                   # algo no hasheable (no debería): sin memo
        return _clasificar(especie, clase, info, codigo)
    if hit is not None:
        return hit
    out = _clasificar(especie, clase, info, codigo)
    if len(_MEMO) >= _MEMO_MAX:
        _MEMO.clear()
    _MEMO[key] = out
    return out


def _clasificar(especie: Any, clase: Any, info: Optional[Dict[str, Any]],
                codigo: Any) -> Tuple[str, str]:
    info = info or {}
    t_base = _norm(" ".join(_s(info.get(c)) for c in _COLS_TIPO if _s(info.get(c))))
    t_desc = _norm(especie)
    t_clase = _norm(clase)
    cat_tasa = categoria_ajuste_tasa(info.get("Ajuste"), info.get("Tasa"))
    liquidez = " LIQUIDEZ " in t_clase
    todo = t_base + t_desc + t_clase
    for txt, fuente in ((t_base, "base"), (t_desc, "texto"), (t_clase, "clase")):
        tipo = tipo_instrumento(txt)
        if tipo:
            lab = etiqueta_tipo(tipo, todo, cat_tasa, liquidez, txt_tasa=t_base + t_desc)
            if lab:
                return lab, fuente
    if cat_tasa:
        return cat_tasa, "base"
    # Clase de Activo inferida (lo de siempre) o cruda.
    if " CEDEAR" in t_clase:
        return "CEDEARs", "clase"
    if " ACCION" in t_clase or " EQUITY " in t_clase:
        return "Acciones", "clase"
    if liquidez:
        cod = _s(codigo).upper()
        if cod and cod not in _CODIGOS_CAJA and len(cod) >= 3:
            return "FCI Money Markets", "clase"
    cruda = _s(clase)
    return (cruda or "(sin clasif.)"), ("sin_regla" if cruda else "clase")
