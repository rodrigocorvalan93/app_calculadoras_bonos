#!/usr/bin/env python3
"""
Encuentra en CNV los links del Suplemento de Prospecto, el Aviso de Resultados y el Prospecto de
programa de un emisor, a partir de su razón social.

Replica el camino manual: buscador global de CNV -> ficha de la empresa (Régimen General) ->
presentaciones (Emisiones / Obligaciones Negociables). Devuelve los links del AIF
(`aif2.cnv.gov.ar/.../publicview/...`) para abrir y descargar el PDF.

Uso:
    python3 buscar_cnv.py "SCANIA"
    python3 buscar_cnv.py "TARJETA NARANJA" --desde 2026-05-01

Notas:
- El buscador de CNV pide un token reCAPTCHA, pero el endpoint acepta el token vacío, así que la
  consulta funciona desde un script.
- Necesita salida de red hacia `www.cnv.gov.ar`. El server es algo lento/inestable: el script
  reintenta.
- Devuelve los links del AIF (publicview). Bajar el byte del PDF en forma automática no está cableado
  (la API de documentos del AIF es frágil / parcialmente interna); abrí el link y el visor del AIF
  descarga el PDF. Si preferís, pasale ese link a Claude para que intente `web_fetch`.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from html import unescape

try:
    import requests
except ImportError:
    print("ERROR: falta 'requests'. Instalá: pip install requests --break-system-packages")
    sys.exit(2)

BUSCADOR = "https://www.cnv.gov.ar/SitioWeb/BuscadorGlobal/DataTableBuscadorGlobal"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


def _post(url, payload):
    hdr = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
           "Referer": "https://www.cnv.gov.ar/sitioweb/buscadorglobal", "User-Agent": "Mozilla/5.0"}
    for _ in range(5):
        try:
            return requests.post(url, data=json.dumps(payload), timeout=50, headers=hdr)
        except Exception:
            time.sleep(2)
    return None


def _get(url):
    for _ in range(5):
        try:
            return requests.get(url, timeout=55, headers={"User-Agent": "Mozilla/5.0"})
        except Exception:
            time.sleep(2)
    return None


def _fecha(txt):
    m = re.match(r"(\d{1,2})\s+(\w{3})\.?\s+(\d{4})", txt)
    if not m:
        return None
    return datetime(int(m.group(3)), MESES.get(m.group(2).lower(), 1), int(m.group(1)))


def _clasif(t):
    T = t.upper()
    if "AVISO DE RESULTADO" in T:
        return "AVISO DE RESULTADOS"
    if "AVISO DE PAGO" in T:
        return None
    if "SUPLEMENTO" in T:
        return "SUPLEMENTO DE PROSPECTO"
    if "PROSPECTO" in T:
        return "PROSPECTO DE PROGRAMA"
    return None


def buscar_empresa(razon):
    r = _post(BUSCADOR, {"draw": 1, "start": 0, "length": 20,
                         "search": {"value": razon, "regex": ""},
                         "order": [], "columns": [], "gRecaptchaResponse": ""})
    if r is None:
        return None, "sin red hacia CNV"
    try:
        data = r.json().get("data", [])
    except Exception:
        return None, "respuesta inesperada del buscador de CNV"
    # preferir Régimen General con Url
    reg = [d for d in data if "General" in d.get("Categoria", "") and d.get("Url")]
    if not reg:
        reg = [d for d in data if d.get("Url")]
    if not reg:
        return None, f"sin resultados con ficha para '{razon}'"
    return reg[0], None


def listar_documentos(emp_url, desde=None):
    r = _get(emp_url)
    if r is None:
        return None, "sin red hacia CNV (ficha de empresa)"
    h = r.text
    vistos = set()
    docs = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        if "publicview" not in fila:
            continue
        link = re.search(r'href="([^"]*publicview[^"]*)"', fila)
        if not link:
            continue
        link = link.group(1)
        txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fila))).strip()
        tipo = _clasif(txt)
        if not tipo:
            continue
        f = _fecha(txt)
        key = (tipo, link)
        if key in vistos:
            continue
        vistos.add(key)
        if desde and f and f < desde:
            continue
        docs.append({"tipo": tipo, "fecha": f, "titulo": txt[:120], "link": link})
    docs.sort(key=lambda d: (d["tipo"], d["fecha"] or datetime.min), reverse=True)
    return docs, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("razon", help="razón social del emisor (p. ej. \"SCANIA\")")
    ap.add_argument("--desde", help="solo documentos desde esta fecha (YYYY-MM-DD)")
    ap.add_argument("--todos", action="store_true", help="listar todos, no solo el más reciente por tipo")
    a = ap.parse_args()
    desde = datetime.strptime(a.desde, "%Y-%m-%d") if a.desde else None

    emp, err = buscar_empresa(a.razon)
    if emp is None:
        print(f"NO SE PUDO BUSCAR EN CNV: {err}")
        sys.exit(1)
    print(f"Emisor: {emp['Denominacion']}  (CUIT {emp['IDFiscal']})")
    print(f"Ficha:  {emp['Url']}\n")

    docs, err = listar_documentos(emp["Url"], desde=desde)
    if docs is None:
        print(f"NO SE PUDO LISTAR DOCUMENTOS: {err}")
        sys.exit(1)
    if not docs:
        print("No encontré Suplemento/Aviso/Prospecto (¿filtro de fecha muy estricto?).")
        return

    mostrados = set()
    for d in docs:
        if not a.todos and d["tipo"] in mostrados:
            continue
        mostrados.add(d["tipo"])
        fecha = d["fecha"].strftime("%d/%m/%Y") if d["fecha"] else "s/f"
        print(f"[{d['tipo']}] {fecha}\n   {d['link']}")


if __name__ == "__main__":
    main()
