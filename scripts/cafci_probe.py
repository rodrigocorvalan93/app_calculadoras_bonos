#!/usr/bin/env python
"""Probe de la API privada de CAFCI (cloud.cafci.org.ar) — correr EN TU MÁQUINA.

Pega a los 6 endpoints conocidos con tu CAFCI_TOKEN (secrets.txt) y arma un
reporte markdown con: estructura de cada respuesta, inventario de campos con
muestras, match automático contra las columnas del Excel del bot (¿sirve para
reemplazar el vector de precios?), presencia de FX y semántica del parámetro
date. NUNCA imprime el token.

Uso:
    python scripts/cafci_probe.py                # date = último hábil
    python scripts/cafci_probe.py --date 2026-07-14
    python scripts/cafci_probe.py --full         # muestras de 10 filas

Pegá en el chat la sección final "Checklist para Fase B" (o el reporte entero).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import date, timedelta

try:
    import OMSsecrets  # noqa: F401 — auto-carga secrets.txt → os.environ
except Exception:  # noqa: BLE001 — sin OMSsecrets: vale el env directo
    pass

import requests

_API_BASE = "https://cloud.cafci.org.ar/api"
_TIMEOUT = 15

# Los 9 fondos que filtra el legacy cafciapi.py — para verificar que el daily
# los trae y que la escala del vcp (÷1000) da valores plausibles.
_FONDOS_PROPIOS = [
    "Fima Renta Fija Dólares - Clase C", "Fima Premium Dólares - Clase A",
    "Delta Ahorro Plus - Clase A", "Delta Acciones - Clase A",
    "Delta Gestion VI - Clase A", "Delta Retorno Real - Clase A",
    "Delta Latinoamerica - Clase A", "Delta Renta - Clase A",
    "Delta Renta Dolares - Clase D",
]

# Columnas del Excel actual del vector → alias posibles en la API (nombres
# normalizados: lowercase, sin acentos/espacios/guiones). Si closing_prices
# matchea la mayoría, la API puede reemplazar al bot de OneDrive.
_EXCEL_ALIAS = {
    "isin": ("isin",),
    "byma": ("byma", "ticker", "especie", "simbolo", "symbol"),
    "cafci": ("cafci", "codigo", "codigocafci", "id"),
    "moneda": ("moneda", "valuacion", "currency"),
    "cdo": ("cdo", "precio", "preciocierre", "cierre", "px", "contado", "valor"),
    "var_cdo": ("variacion", "varcdo", "var", "variacioncdo"),
    "mod_dur": ("modduration", "duration", "md", "duracion", "modifiedduration"),
    "tir": ("tir", "irr", "yield", "rendimiento"),
    "tna": ("tna",),
    "spread": ("spread",),
    "zspread": ("zspread", "zsprd"),
}

_FX_HINTS = ("usd", "usb", "tipodecambio", "fx", "cotizacion", "dolar", "cable", "mep")


def _token() -> str:
    t = os.getenv("CAFCI_TOKEN")
    if not t:
        print("Falta CAFCI_TOKEN. Agregalo en secrets.txt así:\n"
              "    CAFCI_TOKEN=Bearer eyJ...\ny volvé a correr.", file=sys.stderr)
        sys.exit(1)
    return t if t.startswith("Bearer ") else "Bearer " + t


def _prev_habil(d: date, n: int = 1) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def _get(path: str, params=None) -> dict:
    out = {"path": path, "params": params or {}, "status": None, "ms": None,
           "bytes": 0, "json": None, "body_head": "", "error": None}
    t0 = time.perf_counter()
    try:
        r = requests.get(f"{_API_BASE}/{path}", params=params or {},
                         headers={"Authorization": _token()}, timeout=_TIMEOUT)
        out["ms"] = round((time.perf_counter() - t0) * 1000)
        out["status"] = r.status_code
        out["bytes"] = len(r.content or b"")
        try:
            out["json"] = r.json()
        except ValueError:
            out["body_head"] = (r.text or "")[:400]
        if r.status_code in (401, 403):
            out["error"] = f"AUTH {r.status_code} — ¿token vencido? Respuesta: {(r.text or '')[:300]}"
        elif r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}: {(r.text or '')[:300]}"
    except requests.Timeout:
        out["error"] = f"timeout tras {_TIMEOUT}s"
    except requests.RequestException as exc:
        out["error"] = f"conexión: {exc}"
    return out


def _describe(obj, prefix="", depth=0, lines=None) -> list:
    lines = lines if lines is not None else []
    if depth > 3 or len(lines) > 40:
        return lines
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:25]:
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, list):
                lines.append(f"{p}: list[{len(v)}]")
                if v and isinstance(v[0], (dict, list)):
                    _describe(v[0], p + "[0]", depth + 1, lines)
            elif isinstance(v, dict):
                lines.append(f"{p}: dict({len(v)} keys)")
                _describe(v, p, depth + 1, lines)
            else:
                lines.append(f"{p}: {type(v).__name__}")
    elif isinstance(obj, list):
        lines.append(f"{prefix}: list[{len(obj)}]")
        if obj and isinstance(obj[0], (dict, list)):
            _describe(obj[0], prefix + "[0]", depth + 1, lines)
    return lines


def _find_rows(payload):
    """(ruta, filas) de cada lista-de-dicts encontrada (hasta profundidad 2)."""
    found = []
    def _walk(obj, path, depth):
        if depth > 2:
            return
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            found.append((path, obj))
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{path}.{k}" if path else str(k), depth + 1)
    _walk(payload, "", 0)
    found.sort(key=lambda t: -len(t[1]))
    return found


def _field_inventory(rows, sample_n=200) -> dict:
    inv = {}
    for r in rows[:sample_n]:
        if not isinstance(r, dict):
            continue
        for k, v in r.items():
            e = inv.setdefault(k, {"tipos": set(), "no_null": 0, "muestras": []})
            e["tipos"].add(type(v).__name__)
            if v is not None and v != "":
                e["no_null"] += 1
                if len(e["muestras"]) < 3:
                    e["muestras"].append(str(v)[:80])
    n = min(len(rows), sample_n) or 1
    return {k: {"tipos": "/".join(sorted(e["tipos"])),
                "pct": round(100 * e["no_null"] / n),
                "muestras": e["muestras"]} for k, e in inv.items()}


def _match_excel(field_names) -> list:
    normed = {_norm(f): f for f in field_names}
    out = []
    for col, aliases in _EXCEL_ALIAS.items():
        hit = next((normed[a] for a in aliases if a in normed), None)
        out.append(f"{col} → {'`' + hit + '` ✔' if hit else '✘ (sin match)'}")
    return out


def _scan_fx(payload) -> list:
    hits = []
    def _walk(obj, path, depth):
        if depth > 3 or len(hits) > 10:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else str(k)
                if any(h in _norm(k) for h in _FX_HINTS):
                    hits.append(f"{p} = {str(v)[:60]}")
                _walk(v, p, depth + 1)
        elif isinstance(obj, list) and obj:
            _walk(obj[0], path + "[0]", depth + 1)
    _walk(payload, "", 0)
    return hits


def _section(md, titulo, res, full=False, match_excel=False, check_fondos=False):
    md.append(f"\n## {titulo}")
    md.append(f"- Status **{res['status']}** · {res['ms']} ms · {res['bytes']:,} bytes"
              + (f" · ⚠ {res['error']}" if res["error"] else ""))
    if res["json"] is None:
        if res["body_head"]:
            md.append(f"- Respuesta no-JSON: `{res['body_head']}`")
        return
    md.append("- Estructura:")
    md.extend(f"  - `{l}`" for l in _describe(res["json"]))
    listas = _find_rows(res["json"])
    for ruta, rows in listas[:3]:
        inv = _field_inventory(rows)
        md.append(f"- Filas en `{ruta or '(raíz)'}`: **{len(rows):,}** · campos ({len(inv)}):")
        for k, e in inv.items():
            md.append(f"  - `{k}` ({e['tipos']}, {e['pct']}% no-null) — ej: {', '.join(e['muestras']) or '—'}")
        n_muestra = 10 if full else 3
        md.append(f"- Muestra ({min(n_muestra, len(rows))} filas):")
        md.append("```json\n" + json.dumps(rows[:n_muestra], ensure_ascii=False,
                                           indent=2, default=str)[:4000] + "\n```")
        if match_excel:
            md.append("- **Match vs columnas del Excel del bot:**")
            md.extend(f"  - {l}" for l in _match_excel(inv.keys()))
        if check_fondos:
            nombres = {str(r.get("nombreDeLaClaseDeFondo", "")) for r in rows}
            hay = [f for f in _FONDOS_PROPIOS if f in nombres]
            md.append(f"- Fondos propios encontrados: **{len(hay)}/{len(_FONDOS_PROPIOS)}**"
                      + (f" (faltan: {sorted(set(_FONDOS_PROPIOS) - set(hay))})" if len(hay) < len(_FONDOS_PROPIOS) else " ✔"))
        break                                     # la lista principal alcanza
    fx = _scan_fx(res["json"])
    if fx:
        md.append("- Posible FX en la respuesta:")
        md.extend(f"  - `{l}`" for l in fx)


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe API CAFCI")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: último hábil)")
    ap.add_argument("--out", default=None, help="archivo de salida (.md)")
    ap.add_argument("--full", action="store_true", help="muestras de 10 filas")
    args = ap.parse_args()

    hoy = date.today()
    d1 = args.date or _prev_habil(hoy).isoformat()
    d5 = _prev_habil(hoy, 5).isoformat()
    sabado = (hoy - timedelta(days=(hoy.weekday() - 5) % 7 or 7)).isoformat()

    md = [f"# Probe API CAFCI — {hoy.isoformat()} · date base {d1}"]

    r_daily = _get("reports/daily")
    _section(md, "1. /reports/daily", r_daily, args.full, check_fondos=True)

    _section(md, f"2a. /reports/historic?date={d1}", _get("reports/historic", {"date": d1}), args.full)
    _section(md, f"2b. /reports/historic?date={d5}", _get("reports/historic", {"date": d5}))

    r_cp = _get("vectores/cafci_closing_prices", {"date": d1})
    _section(md, f"3a. /vectores/cafci_closing_prices?date={d1}", r_cp, args.full, match_excel=True)
    _section(md, f"3b. …closing_prices?date={hoy.isoformat()} (¿publica t-0?)",
             _get("vectores/cafci_closing_prices", {"date": hoy.isoformat()}))
    _section(md, f"3c. …closing_prices?date={sabado} (¿y en no-hábil?)",
             _get("vectores/cafci_closing_prices", {"date": sabado}))

    for i, ep in enumerate(("vectores/cafci_historic_prices",
                            "vectores/valuation_cashflows", "vectores/variables"), start=4):
        r = _get(ep)
        if r["status"] in (400, 422):
            r = _get(ep, {"date": d1})
        _section(md, f"{i}. /{ep}", r, args.full)

    md.append("\n## Checklist para Fase B (pegá esta sección en el chat)")
    cp_ok = r_cp["status"] == 200 and r_cp["json"] is not None
    campos_cp = []
    if cp_ok:
        listas = _find_rows(r_cp["json"])
        if listas:
            campos_cp = list(_field_inventory(listas[0][1]).keys())
    md.append(f"- closing_prices responde: {'SÍ' if cp_ok else 'NO — ' + str(r_cp['error'])}")
    if campos_cp:
        md.append(f"- campos de closing_prices: {', '.join('`' + c + '`' for c in campos_cp)}")
        md.append("- match Excel: " + " · ".join(_match_excel(campos_cp)))
    md.append(f"- daily responde: {'SÍ' if r_daily['status'] == 200 else 'NO — ' + str(r_daily['error'])}")
    md.append("- (mirá arriba 3b/3c para la semántica del date, y las secciones 4-6 por FX/extras)")

    reporte = "\n".join(md)
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        f"cafci_probe_{hoy.strftime('%Y%m%d')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(reporte)
    print(reporte)
    print(f"\n[guardado en {out_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
