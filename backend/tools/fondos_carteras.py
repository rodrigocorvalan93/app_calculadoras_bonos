"""Carteras diarias de los fondos → caché local compacto para la atribución.

    python -m backend.tools.fondos_carteras --carteras <Delta Bases\\Carteras>
           --out <carpeta local> [--dias 400] [--max 0] [--quiet]

La atribución del rendimiento (pestaña Fondos) necesita las tenencias de
CADA rueda: `Carteras/AAAAMMDD/AAAAMMDD_Delta_Composicion.xlsx` (~6.400 filas ×
37 columnas, ~0,9 MB) y `AAAAMMDD_Delta_PN.xlsx`. Leer un año de esos Excel
con openpyxl son ~10 minutos de CPU: por eso corre en ESTE proceso aparte (lo
lanza `services/fondos_attr`; nunca en el proceso que sirve los paneles) y
deja un parquet por día con sólo lo que la cuenta usa (≈ 60 KB), en la carpeta
LOCAL de la máquina (`estado_local`: fuera de OneDrive). Después de la primera
vez sólo convierte el día nuevo.

- Lector rápido de xlsx (`leer_xlsx`): zip + expresiones regulares sobre el
  XML de la hoja, sólo las columnas pedidas (≈ 0,2 s por archivo). Si algo no
  cuadra (cabecera, tipo de celda desconocido, filas que no coinciden con la
  dimensión declarada) cae a pandas / openpyxl: más lento, mismo resultado.
- `manifest.json`: firma (mtime + tamaño) del Excel de cada día convertido;
  un día cuyo Excel cambió se vuelve a convertir. `progreso.json`: avance para
  la pestaña. Escrituras atómicas.
- Un archivo "sólo en la nube" de OneDrive que no se puede leer se anota en
  `errores` y se reintenta en la corrida siguiente; no corta la corrida.

Sólo depende de la stdlib + numpy / pandas / pyarrow (no importa el backend).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = 2                                  # cambia el esquema del parquet → se reconvierte todo
DIAS_DEFAULT = 400
# columna del Excel → columna del caché
COLUMNAS: Dict[str, str] = {
    "CodFondo": "cod", "IsinCode": "isin", "Cod_Delta": "ticker", "Inversion": "inv",
    "Instrumento": "instr", "Ajuste": "ajuste", "Pago": "pago", "Sector Delta": "sector",
    "Clasifica": "clasif", "Tasa": "tasa", "Vencimiento": "vto", "Cantidad": "q", "Valor": "v",
}
_TEXTO = ("isin", "ticker", "inv", "instr", "ajuste", "pago", "sector", "clasif")
FILA_PN = "__PN__"                           # el patrimonio del fondo viaja como una fila más (instr = FILA_PN)
_RE_DIA = re.compile(r"^(\d{8})")


# ── lector rápido de xlsx ────────────────────────────────────────────────────
_RE_ROW = re.compile(rb"<row\b[^>]*>(.*?)</row>", re.S)
_RE_CELL = re.compile(rb'<c\b([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_RE_REF = re.compile(rb'\br="([A-Z]+)(\d+)"')
_RE_T = re.compile(rb'\bt="(\w+)"')
_RE_V = re.compile(rb"<v\b[^>]*>(.*?)</v>", re.S)
_RE_TXT = re.compile(rb"<t\b[^>]*>(.*?)</t>", re.S)
_RE_SI = re.compile(rb"<si\b[^>]*>(.*?)</si>|<si\b[^>]*/>", re.S)
_RE_DIM = re.compile(rb'<dimension\b[^>]*\bref="[A-Z]+\d+:[A-Z]+(\d+)"')


class FormatoInesperado(ValueError):
    """El lector rápido no reconoce el archivo: se cae al lector de pandas."""


def _texto(b: bytes) -> str:
    return html.unescape(b.decode("utf-8", "replace"))


def _hoja_y_strings(path: str) -> Tuple[bytes, Optional[List[str]]]:
    with zipfile.ZipFile(path) as z:
        nombres = z.namelist()
        hoja = "xl/worksheets/sheet1.xml"
        if hoja not in nombres:
            hojas = sorted(n for n in nombres if n.startswith("xl/worksheets/") and n.endswith(".xml"))
            if not hojas:
                raise FormatoInesperado("sin hojas")
            hoja = hojas[0]
        xml = z.read(hoja)
        compartidos: Optional[List[str]] = None
        if "xl/sharedStrings.xml" in nombres:
            ss = z.read("xl/sharedStrings.xml")
            compartidos = ["".join(_texto(t) for t in _RE_TXT.findall(m.group(1) or b""))
                           for m in _RE_SI.finditer(ss)]
    return xml, compartidos


def _valor(attrs: bytes, cuerpo: Optional[bytes], compartidos: Optional[List[str]]) -> Any:
    if not cuerpo:
        return None
    t = _RE_T.search(attrs)
    tipo = t.group(1) if t else b"n"
    if tipo == b"inlineStr":
        return "".join(_texto(x) for x in _RE_TXT.findall(cuerpo))
    v = _RE_V.search(cuerpo)
    if v is None:
        return None
    crudo = v.group(1)
    if tipo == b"n":
        try:
            return float(crudo)
        except ValueError as exc:
            raise FormatoInesperado(f"número ilegible {crudo[:20]!r}") from exc
    if tipo == b"s":
        if compartidos is None:
            raise FormatoInesperado("texto compartido sin tabla")
        return compartidos[int(crudo)]
    if tipo in (b"str", b"d", b"e"):
        return _texto(crudo)
    if tipo == b"b":
        return crudo == b"1"
    raise FormatoInesperado(f"tipo de celda {tipo!r}")


def leer_xlsx_rapido(path: str, columnas: Sequence[str]) -> Dict[str, List[Any]]:
    """Primera hoja de un xlsx → {columna: [valores]} sólo para `columnas`
    (por nombre de cabecera, fila 1). Las celdas vacías quedan en None y los
    números en float. `FormatoInesperado` si algo no cuadra.

    Una sola pasada de regex sobre el XML, armada con las LETRAS de las
    columnas pedidas (13 de 37 en la composición): las demás celdas ni se
    miran. Supone lo que escriben pandas / openpyxl / xlsxwriter / Excel: `r`
    es el primer atributo de `<c>` y las filas van numeradas sin huecos."""
    xml, compartidos = _hoja_y_strings(path)
    primera = _RE_ROW.search(xml)
    if primera is None:
        raise FormatoInesperado("hoja vacía")
    letra: Dict[str, str] = {}
    for m in _RE_CELL.finditer(primera.group(1)):
        ref = _RE_REF.search(m.group(1))
        if ref is None:
            raise FormatoInesperado("celda sin referencia")
        v = _valor(m.group(1), m.group(2), compartidos)
        if isinstance(v, str) and v.strip() not in letra:
            letra[v.strip()] = ref.group(1).decode()
    falta = [c for c in columnas if c not in letra]
    if falta:
        raise FormatoInesperado(f"faltan columnas {falta}")
    n = xml.count(b"<row ") + xml.count(b"<row>") - 1
    por_letra = {letra[c]: [None] * n for c in columnas}
    pat = re.compile(rb'<c r="(' + b"|".join(sorted((x.encode() for x in por_letra), key=len, reverse=True))
                     + rb')(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
    vistas = 0
    for m in pat.finditer(xml, primera.end()):
        i = int(m.group(2)) - 2
        if not 0 <= i < n:
            raise FormatoInesperado(f"fila {i + 2} fuera de las {n} declaradas")
        v = _valor(m.group(3), m.group(4), compartidos)
        if v is not None:
            por_letra[m.group(1).decode()][i] = v
            vistas += 1
    dim = _RE_DIM.search(xml[:4096])
    if dim is not None and int(dim.group(1)) - 1 != n:
        # la dimensión declarada no coincide con las filas (formato que no esperamos): no confiar
        raise FormatoInesperado(f"{n} filas leídas, la hoja declara {int(dim.group(1)) - 1}")
    if n and not vistas:
        raise FormatoInesperado("ninguna celda reconocida")
    return {c: por_letra[letra[c]] for c in columnas}


def leer_xlsx(path: str, columnas: Sequence[str]) -> Tuple[Dict[str, List[Any]], str]:
    """({columna: [valores]}, lector usado). Rápido si se puede; si no, pandas."""
    try:
        return leer_xlsx_rapido(path, columnas), "rapido"
    except (FormatoInesperado, KeyError, IndexError, zipfile.BadZipFile):
        import pandas as pd
        df = pd.read_excel(path, sheet_name=0)
        df.columns = [str(c).strip() for c in df.columns]
        falta = [c for c in columnas if c not in df.columns]
        if falta:
            raise ValueError(f"{os.path.basename(path)}: faltan columnas {falta}")
        return {c: [None if _es_nulo(v) else v for v in df[c].tolist()] for c in columnas}, "pandas"


def _es_nulo(v: Any) -> bool:
    try:
        return v is None or v != v          # NaN / NaT
    except (TypeError, ValueError):
        return False


# ── un día ───────────────────────────────────────────────────────────────────
def _num(v: Any) -> float:
    if v is None or isinstance(v, bool):
        return float("nan")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "")
    if not s:
        return float("nan")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    s = " ".join(str(v).split())
    return "" if s.lower() in ("nan", "nat", "none") else s


_EPOCA_EXCEL = dt.date(1899, 12, 30)


def _fecha(v: Any) -> str:
    """Vencimiento → 'AAAA-MM-DD' ('' si no hay): texto ISO, fecha de pandas o
    número de serie de Excel."""
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not (20000 < float(v) < 80000):
            return ""
        return (_EPOCA_EXCEL + dt.timedelta(days=int(float(v)))).isoformat()
    s = str(v).strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def convertir_dia(comp: str, pn: Optional[str]):
    """Excel de composición (+ PN) de un día → DataFrame compacto: una fila por
    fondo y tenencia (las repetidas se suman) más una fila `FILA_PN` por fondo.
    Devuelve (df, lector)."""
    import numpy as np
    import pandas as pd
    datos, lector = leer_xlsx(comp, list(COLUMNAS))
    cod = np.array([_num(x) for x in datos["CodFondo"]], dtype=float)
    ok = np.isfinite(cod)
    df = pd.DataFrame({"cod": cod})
    for xl, c in COLUMNAS.items():
        if c in _TEXTO:
            df[c] = [_txt(x) for x in datos[xl]]
    df["tasa"] = np.array([_num(x) for x in datos["Tasa"]], dtype=float)
    df["vto"] = [_fecha(x) for x in datos["Vencimiento"]]
    df["q"] = np.array([_num(x) for x in datos["Cantidad"]], dtype=float)
    df["v"] = np.array([_num(x) for x in datos["Valor"]], dtype=float)
    df = df[ok & np.isfinite(df["v"].to_numpy())]
    df["cod"] = df["cod"].astype("int32")
    df["q"] = df["q"].fillna(0.0)
    claves = ["cod", *_TEXTO, "vto"]
    df = df.groupby(claves, sort=False, as_index=False).agg(tasa=("tasa", "first"), q=("q", "sum"), v=("v", "sum"))
    if pn:
        dpn, _ = leer_xlsx(pn, ["CodFondo", "PN"])
        filas = [(int(_num(c)), _num(p)) for c, p in zip(dpn["CodFondo"], dpn["PN"])
                 if _num(c) == _num(c) and _num(p) == _num(p)]
        if filas:
            extra = pd.DataFrame({"cod": [c for c, _ in filas], "v": [p for _, p in filas]})
            for c in _TEXTO:
                extra[c] = ""
            extra["instr"] = FILA_PN
            extra["vto"] = ""
            extra["tasa"] = float("nan")
            extra["q"] = 0.0
            extra["cod"] = extra["cod"].astype("int32")
            df = pd.concat([df, extra[df.columns]], ignore_index=True)
    df["tasa"] = df["tasa"].astype("float32")
    return df, lector


# ── días disponibles y corrida ───────────────────────────────────────────────
def dias_disponibles(carteras: str) -> List[Tuple[str, str, Optional[str]]]:
    """[(AAAAMMDD, ruta composición, ruta PN | None)] ascendente. Una carpeta
    `AAAAMMDDbis` pisa a la del mismo día (es la corrección)."""
    out: Dict[str, Tuple[str, str, Optional[str]]] = {}
    try:
        nombres = sorted(os.listdir(carteras))
    except OSError:
        return []
    for nombre in nombres:
        m = _RE_DIA.match(nombre)
        if not m:
            continue
        dia = m.group(1)
        carpeta = os.path.join(carteras, nombre)
        comp = os.path.join(carpeta, f"{dia}_Delta_Composicion.xlsx")
        if not os.path.isfile(comp):
            continue
        pn = os.path.join(carpeta, f"{dia}_Delta_PN.xlsx")
        out[dia] = (dia, comp, pn if os.path.isfile(pn) else None)
    return [out[k] for k in sorted(out)]


def _firma(*paths: Optional[str]) -> List[Any]:
    sig: List[Any] = []
    for p in paths:
        if not p:
            sig.append(None)
            continue
        try:
            st = os.stat(p)
            sig.append([st.st_mtime_ns, st.st_size])
        except OSError:
            sig.append(None)
    return sig


def _escribir_json(path: str, data: Dict[str, Any]) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def leer_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def desde_de(dias: int, hoy: Optional[dt.date] = None) -> str:
    return ((hoy or dt.date.today()) - dt.timedelta(days=int(dias))).strftime("%Y%m%d")


def pendientes(carteras: str, out: str, desde: str) -> Tuple[List[Tuple[str, str, Optional[str]]], Dict[str, Any], List[str]]:
    """(días a convertir, manifiesto vigente, días del caché que ya quedaron
    fuera de la ventana). Sólo stats: se puede llamar desde la app."""
    man = leer_json(os.path.join(out, "manifest.json"))
    if man.get("version") != VERSION:
        man = {"version": VERSION, "dias": {}}
    hechos: Dict[str, Any] = man.setdefault("dias", {})
    todos = [d for d in dias_disponibles(carteras) if d[0] >= desde]
    falta = [d for d in todos
             if hechos.get(d[0], {}).get("firma") != _firma(d[1], d[2])
             or not os.path.isfile(os.path.join(out, f"{d[0]}.parquet"))]
    viejos = [k for k in hechos if k < desde]
    return falta, man, viejos


def correr(carteras: str, out: str, dias: int = DIAS_DEFAULT, maximo: int = 0, quiet: bool = True,
           hoy: Optional[dt.date] = None) -> Dict[str, Any]:
    """Convierte lo que falte. Devuelve el resumen (también en progreso.json)."""
    os.makedirs(out, exist_ok=True)
    desde = desde_de(dias, hoy)
    falta, man, viejos = pendientes(carteras, out, desde)
    prog_path = os.path.join(out, "progreso.json")
    man_path = os.path.join(out, "manifest.json")
    if maximo and len(falta) > maximo:
        falta = falta[-maximo:]                      # los más nuevos primero en importancia
    prog: Dict[str, Any] = {"pid": os.getpid(), "total": len(falta), "hechos": 0, "dia": None, "errores": [],
                            "inicio": time.time(), "fin": None, "desde": desde, "lectores": {}}
    _escribir_json(prog_path, prog)
    for k in viejos:                                 # fuera de la ventana: se poda
        man["dias"].pop(k, None)
        try:
            os.remove(os.path.join(out, f"{k}.parquet"))
        except OSError:
            pass
    ultimo_guardado = time.time()
    # del más nuevo al más viejo: lo reciente (MTD, 30 días) queda listo primero
    for dia, comp, pn in reversed(falta):
        prog["dia"] = dia
        try:
            df, lector = convertir_dia(comp, pn)
            dest = os.path.join(out, f"{dia}.parquet")
            tmp = f"{dest}.{os.getpid()}.tmp"
            df.to_parquet(tmp, index=False, compression="zstd")
            os.replace(tmp, dest)
            man["dias"][dia] = {"firma": _firma(comp, pn), "filas": int(len(df)), "pn": bool(pn)}
            prog["lectores"][lector] = prog["lectores"].get(lector, 0) + 1
        except Exception as exc:  # noqa: BLE001 — un día ilegible (marcador de OneDrive, archivo en uso) no corta la corrida
            prog["errores"].append({"dia": dia, "error": f"{type(exc).__name__}: {exc}"[:300]})
            if not quiet:
                print(f"  ! {dia}: {type(exc).__name__}: {exc}", flush=True)
        prog["hechos"] += 1
        ahora = time.time()
        if ahora - ultimo_guardado > 2.0 or prog["hechos"] == prog["total"]:
            _escribir_json(man_path, man)
            _escribir_json(prog_path, prog)
            ultimo_guardado = ahora
            if not quiet:
                print(f"  {prog['hechos']}/{prog['total']} · {dia}", flush=True)
    _escribir_json(man_path, man)
    prog["fin"] = time.time()
    prog["dia"] = None
    _escribir_json(prog_path, prog)
    return prog


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Carteras diarias de los fondos → caché local para la atribución.")
    ap.add_argument("--carteras", required=True, help="carpeta Delta Bases\\Carteras (subcarpetas AAAAMMDD)")
    ap.add_argument("--out", required=True, help="carpeta local del caché")
    ap.add_argument("--dias", type=int, default=DIAS_DEFAULT, help="días corridos hacia atrás (default 400)")
    ap.add_argument("--max", type=int, default=0, help="tope de días a convertir en esta corrida (0 = todos)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(list(argv) if argv is not None else None)
    try:
        os.nice(10)                                  # POSIX: que no le gane CPU a la app
    except (AttributeError, OSError):
        pass
    if not os.path.isdir(a.carteras):
        if not a.quiet:
            print(f"No encuentro la carpeta de carteras: {a.carteras}")
        return 2
    r = correr(a.carteras, a.out, a.dias, a.max, a.quiet)
    if not a.quiet:
        seg = (r["fin"] or time.time()) - r["inicio"]
        print(f"{r['hechos']} día(s) en {seg:.1f} s · {len(r['errores'])} con error · lectores {r['lectores']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
