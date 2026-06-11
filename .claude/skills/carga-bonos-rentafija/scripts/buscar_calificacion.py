#!/usr/bin/env python3
"""
Busca la calificación de FIX (FIX SCR, afiliada de Fitch) para un emisor y la asigna según el plazo
del bono. Devuelve la calificación nacional con el sufijo "(arg)".

Regla de la casa (confirmada): plazo del bono <= 12 meses -> calificación de **corto plazo**
(p. ej. A1+(arg)); plazo > 12 meses -> calificación de **largo plazo** (p. ej. AA(arg)).

Uso:
    python3 buscar_calificacion.py "Naranja X" --plazo-meses 12
    python3 buscar_calificacion.py --id 613 --plazo-meses 18
    python3 buscar_calificacion.py --url "https://www.fixscr.com/emisor/view?type=emisor&id=613" --plazo-meses 12 --isin AR0771688576

Notas:
- El buscador del sitio FIX es JavaScript y no se puede consultar por querystring. Por eso:
  * para los emisores frecuentes hay un mini-mapa nombre -> id acá abajo (ampliable), y
  * para un emisor nuevo, resolvé la URL del emisor con web_search ("fixscr <emisor>") y pasala con
    --url (o el id con --id).
- Si pasás --isin y ese ISIN ya figura en FIX, devuelve esa calificación exacta; si no, usa la del
  emisor (corto/largo plazo) según el plazo.
- Necesita salida de red hacia www.fixscr.com. Si no hay red, lo informa y hay que dejar la
  calificación como pendiente.
- Siempre se carga con "(arg)" al final.
"""
import argparse
import re
import sys
from html import unescape

try:
    import requests
except ImportError:
    print("ERROR: falta 'requests'. Instalá: pip install requests --break-system-packages")
    sys.exit(2)

# Emisores frecuentes (ampliá a medida que aparezcan): nombre normalizado -> id de FIX
EMISORES = {
    "naranja x": 613,
    "tarjeta naranja": 613,
}

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

BASE = "https://www.fixscr.com/emisor/view?type=emisor&id={}"


def _fecha(s):
    m = re.match(r"(\d{1,2})-(\w{3})-(\d{4})", s)
    if not m:
        return None
    return (int(m.group(3)), MESES.get(m.group(2).lower(), 0), int(m.group(1)))


def _es_corto_plazo(rating):
    # Escala nacional de corto plazo: A1+, A1, A2, A3, B, C, D -> empieza con A y dígito
    return bool(re.match(r"A[123]", rating))


def _parse(html):
    plain = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    filas = re.findall(
        r"Fecha\s+(\d{1,2}-\w{3}-\d{4})\s+ISIN\s+(\S+)\s+Rating\s+([A-Za-z0-9\+\-]+\(arg\))",
        plain,
    )
    return filas  # lista de (fecha, isin, rating)


def buscar(id_=None, url=None, nombre=None, plazo_meses=None, isin=None):
    if url is None:
        if id_ is None and nombre:
            id_ = EMISORES.get(nombre.strip().lower())
        if id_ is None:
            return None, ("emisor no está en el mini-mapa; resolvé la URL con web_search "
                          "('fixscr <emisor>') y pasala con --url o --id")
        url = BASE.format(id_)

    try:
        html = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"}).text
    except Exception as e:
        return None, f"sin red hacia FIX ({e})"

    filas = _parse(html)
    if not filas:
        return None, "no pude leer calificaciones en la página (¿cambió el formato?)"

    # 1) match exacto por ISIN si se pidió y está
    if isin:
        cand = [(_fecha(f), r) for f, i, r in filas if i == isin and _fecha(f)]
        if cand:
            return max(cand)[1], None

    # 2) vigente por plazo
    cp = [(_fecha(f), r) for f, i, r in filas if _es_corto_plazo(r) and _fecha(f)]
    lp = [(_fecha(f), r) for f, i, r in filas if not _es_corto_plazo(r) and _fecha(f)]
    if plazo_meses is not None and plazo_meses <= 12:
        if cp:
            return max(cp)[1], None
        return (max(lp)[1] if lp else None), "no hay calificación de corto plazo; devuelvo largo plazo"
    else:
        if lp:
            return max(lp)[1], None
        return (max(cp)[1] if cp else None), "no hay calificación de largo plazo; devuelvo corto plazo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("emisor", nargs="?", help="nombre del emisor (si está en el mini-mapa)")
    ap.add_argument("--id", type=int, dest="id_")
    ap.add_argument("--url")
    ap.add_argument("--plazo-meses", type=int, dest="plazo")
    ap.add_argument("--isin")
    a = ap.parse_args()

    rating, err = buscar(id_=a.id_, url=a.url, nombre=a.emisor, plazo_meses=a.plazo, isin=a.isin)
    if rating is None:
        print(f"NO SE PUDO OBTENER LA CALIFICACIÓN: {err}")
        print("Dejá 'Calificación' como pendiente (None) en el dict.")
        sys.exit(1)
    print(rating)
    if err:
        print(f"(aviso: {err})", file=sys.stderr)


if __name__ == "__main__":
    main()
