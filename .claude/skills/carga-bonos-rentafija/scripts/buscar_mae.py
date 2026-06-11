#!/usr/bin/env python3
"""
Consulta el listado público del MAE (`listado_instrumentos.aspx`, renta fija) para resolver datos
de un instrumento. Dos usos:

  # 1) Buscar el ticker + ISIN de un emisor por su nombre (aparece en la descripción):
  python3 buscar_mae.py --emisor "SCANIA"
      -> SBC1O | AR0200205687 | ON.SCANIA CREDIT ARG CLASE 1 | Dólares
         SBC2O | AR0318379242 | ON.SCANIA CREDIT ARG CLASE 2 | Dólares
         SBC3O | AR0183143921 | ON.SCANIA CREDIT ARG CLASE 3 | Dólares

  # 2) Buscar el ISIN de un código puntual (prueba también la variante terminada en O):
  python3 buscar_mae.py --codigo T672O T673O

Por qué este script y no un fetch simple: la página es un GridView ASP.NET paginado de a 50 SIN
buscador, así que hay que paginar haciendo postbacks con el ViewState. Por `--codigo` corta apenas
encuentra; por `--emisor` recorre todo el listado (tarda más, varios segundos).

Necesita salida de red hacia `servicios.mae.com.ar`. Si no hay red, lo informa y hay que dejar el
campo pendiente en el dict.

Recordá: el ticker del MAE termina en `O`. El ticker de la casa puede cambiar esa letra por la
moneda (ver tipos-y-convenciones.md), pero el ISIN y el prefijo del código salen de acá.
"""
import argparse
import re
import sys
import time
from html import unescape

try:
    import requests
except ImportError:
    print("ERROR: falta 'requests'. Instalá: pip install requests --break-system-packages")
    sys.exit(2)

URL = "https://servicios.mae.com.ar/mercados/listado_instrumentos.aspx"
EVENT_TARGET = "ctl00$ContentPlaceHolder1$UWTCodigos$_ctl0$GVInstrumentosRF"
MAX_PAGES = 90


def _hidden(html):
    f = {}
    for k in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(r'id="' + k + r'"[^>]*value="([^"]*)"', html)
        f[k] = unescape(m.group(1)) if m else ""
    return f


def _rows(html):
    """Devuelve filas [codigo, isin, descripcion, moneda] de la grilla de renta fija."""
    start = html.find("GVInstrumentosRF")
    seg = html[start:start + 90000] if start != -1 else ""
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) >= 4:
            vals = [unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells[:4]]
            if vals[0]:
                out.append(vals)
    return out


def _paginar(session, hasta_codigos=None):
    """Recorre las páginas. Si `hasta_codigos` (set) se da, corta cuando los encontró todos."""
    try:
        html = session.get(URL, timeout=30).text
    except Exception as e:
        return None, f"sin red hacia MAE ({e})"
    todas = []
    encontrados = set()
    prev_first = None
    resp = None
    for page in range(1, MAX_PAGES + 1):
        rs = _rows(html)
        todas.extend(rs)
        if hasta_codigos:
            encontrados |= {r[0] for r in rs if r[0] in hasta_codigos}
            if hasta_codigos <= encontrados:
                break
        first = rs[0][0] if rs else None
        if page > 1 and (first is None or first == prev_first):
            break
        prev_first = first
        data = {**_hidden(html), "__EVENTTARGET": EVENT_TARGET,
                "__EVENTARGUMENT": f"Page${page + 1}"}
        ok = False
        for _ in range(3):
            try:
                resp = session.post(URL, data=data, timeout=30)
            except Exception as e:
                return todas, f"corte de red al paginar ({e})"
            if resp.status_code == 200 and "GVInstrumentosRF" in resp.text:
                ok = True
                break
            time.sleep(0.6)
        if not ok:
            break
        html = resp.text
        time.sleep(0.15)
    return todas, None


def por_emisor(nombre):
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    filas, err = _paginar(s)
    if filas is None:
        return None, err
    nn = nombre.strip().upper()
    hits = [f for f in filas if nn in f[2].upper()]
    if hits:
        return hits, err
    # Fallback: el MAE abrevia la descripción (p. ej. "ON.CRESUD SERIE 36 CL 52"), así que si la
    # razón social completa no matchea, probá con la primera palabra distintiva (>=4 letras, no
    # genérica como SOCIEDAD/ANONIMA/COMERCIAL...).
    GENERICAS = {"SOCIEDAD", "ANONIMA", "ANÓNIMA", "COMERCIAL", "INMOBILIARIA", "FINANCIERA",
                 "AGROPECUARIA", "INDUSTRIAL", "ARGENTINA", "ARGENTINr", "COMPANIA", "COMPAÑIA",
                 "GROUP", "HOLDING", "DE", "LA", "EL", "Y", "DEL", "S.A.", "SAU", "S.A.U."}
    tokens = [t for t in re.split(r"[^A-Za-zÁÉÍÓÚÑ0-9]+", nn) if len(t) >= 4 and t not in GENERICAS]
    for tok in tokens:
        hits = [f for f in filas if tok in f[2].upper()]
        if hits:
            return hits, (err or f"match por token '{tok}'")
    return [], err


def por_codigo(codigos):
    objetivo = set()
    for c in codigos:
        c = c.strip().upper()
        objetivo.add(c)
        if c and c[-1] != "O":
            objetivo.add(c[:-1] + "O")
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    filas, err = _paginar(s, hasta_codigos=objetivo)
    if filas is None:
        return None, err
    idx = {f[0]: f for f in filas}
    res = {}
    for c in codigos:
        c = c.strip().upper()
        f = idx.get(c) or idx.get(c[:-1] + "O" if c and c[-1] != "O" else c)
        res[c] = f[1] if f else None
    return res, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emisor", help="nombre del emisor a buscar en la descripción")
    ap.add_argument("--codigo", nargs="+", help="uno o más códigos (usá el que termina en O)")
    a = ap.parse_args()
    if not a.emisor and not a.codigo:
        print("Usá --emisor \"NOMBRE\" o --codigo COD1 [COD2 ...]")
        sys.exit(2)

    if a.emisor:
        filas, err = por_emisor(a.emisor)
        if filas is None:
            print(f"NO SE PUDO CONSULTAR EL MAE: {err}")
            sys.exit(1)
        if not filas:
            print(f"Sin resultados para '{a.emisor}' (¿todavía no listado, u otro nombre?).")
        for f in filas:
            print(" | ".join(f))
        if err:
            print(f"(aviso: {err})", file=sys.stderr)
    else:
        res, err = por_codigo(a.codigo)
        if res is None:
            print(f"NO SE PUDO CONSULTAR EL MAE: {err}")
            sys.exit(1)
        for c, isin in res.items():
            print(f"{c} -> {isin if isin else 'NO ENCONTRADO (¿todavía no listado?)'}")
        if err:
            print(f"(aviso: {err})", file=sys.stderr)


if __name__ == "__main__":
    main()
