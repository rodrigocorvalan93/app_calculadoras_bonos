"""Chequeo de la base histórica px/tasas — SÓLO LECTURA, para mirar en un
minuto y en cualquier máquina qué tiene la base compartida y por qué el chip
dice lo que dice:

  · los archivos (xlsx, espejo parquet, firma, manifiesto): tamaño, hora y si
    el espejo es copia fiel del Excel;
  · las últimas ruedas hábiles: filas en la base (reales / RC), lo que esta
    máquina vio (memoria local), lo que dice el manifiesto compartido y lo que
    guarda el journal local;
  · la regresión ("la base nunca pierde ruedas"): qué ruedas faltan o se
    degradaron, cuáles repone el journal propio y cuáles frenan la escritura;
  · copias de conflicto / restos de OneDrive en la carpeta y los huecos
    ignorados.

    python -m backend.tools.base_check [--ruedas 15] [--json]

No escribe nada (ni la memoria local): se puede correr en la PC writer, en la
notebook y en la Mac, y comparar las tres salidas.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)


def _archivo(path: str) -> Dict[str, Any]:
    from backend.services.historico_writer import _TZ      # horas en BA, como el manifiesto y el log
    try:
        st = os.stat(path)
    except OSError:
        return {"path": path, "existe": False}
    return {"path": path, "existe": True, "bytes": int(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime, _TZ).strftime("%Y-%m-%d %H:%M:%S")}


def informe(ruedas: int = 15) -> Dict[str, Any]:
    from backend.config import settings
    from backend.services import espejo, historico_writer as hw

    xlsx = hw._xlsx_default()
    we = hw.writer_estado()                          # flag + rol de quien usó esta instancia hoy
    out: Dict[str, Any] = {
        "host": hw._host(),
        "writer": bool(we["writer"]),
        "writer_motivo": we["motivo"],
        "autosave": bool(settings.historico_autosave),
        "journal_dir": hw.journal_dir(),
        "carpeta": os.path.dirname(xlsx) if xlsx else None,
    }
    if not xlsx:
        out["error"] = "carpeta Delta Bases no montada en esta máquina (DELTA_HISTORICO_DIR / DELTA_BASES_DIR)"
        return out
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    out["archivos"] = {"xlsx": _archivo(xlsx), "parquet": _archivo(pq),
                       "firma": _archivo(espejo.sidecar_path(pq)),
                       "manifiesto": _archivo(hw._manifest_path(xlsx))}
    out["espejo_fiel"] = bool(os.path.isfile(pq) and espejo.espejo_valido(pq, xlsx))
    resumen = hw._resumen_base(xlsx)                 # sin tocar la memoria local
    out["ruedas_en_base"] = len(resumen)
    out["ultima"] = max(resumen).isoformat() if resumen else None
    m = hw._manifest_leer(xlsx)
    out["manifiesto"] = {"host": m.get("host"), "cuando": m.get("cuando"), "ruedas": len(m["fechas"]),
                         "ultima": max(m["fechas"]).isoformat() if m["fechas"] else None}
    memoria = hw._vista_de(xlsx)
    journal = hw._journal_days()
    ignorados = hw.huecos_ignorados()
    sin_rueda = hw._sin_rueda_days()
    reg = hw.regresion_detalle(xlsx, resumen=resumen)
    out["regresion"] = {"ruedas": [d.isoformat() for d in reg["ruedas"]],
                        "recuperables": [d.isoformat() for d in reg["recuperables"]],
                        "bloqueantes": [d.isoformat() for d in reg["bloqueantes"]],
                        "contenido_perdido": reg.get("contenido_perdido") or {},
                        "detalle": {d.isoformat(): v for d, v in reg["detalle"].items()}}
    # Últimas N ruedas hábiles anteriores a hoy (como huecos_base, sin tope por la base).
    hoy = hw._now().date()
    primera = min(resumen) if resumen else None
    filas: List[Dict[str, Any]] = []
    d = hw._habil_anterior(hoy, sin_rueda)
    for _ in range(ruedas):
        n, r = resumen.get(d, (0, 0))
        jn = hw._journal_reales(journal[d]) if d in journal else None
        if d in ignorados:
            estado = "ignorado"
        elif n == 0 and primera is not None and d < primera:
            estado = "anterior a la base"
        elif n == 0:
            estado = "sólo journal" if jn else "FALTA"
        elif r == 0:
            estado = "RC"
        elif d in reg["detalle"]:
            estado = "DEGRADADA"
        else:
            estado = "ok"
        filas.append({"fecha": d.isoformat(), "base": [n, r], "memoria": list(memoria.get(d, (0, 0))),
                      "manifiesto": list(m["fechas"].get(d, (0, 0))),
                      "journal_reales": jn, "estado": estado})
        d = hw._habil_anterior(d, sin_rueda)
    out["ruedas"] = filas
    out["journal"] = {"dias": len(journal), "ultimo": max(journal).isoformat() if journal else None}
    out["ignorados"] = [d.isoformat() for d in sorted(ignorados)]
    # Mismo escaneo que la tarjeta "Copias en conflicto" de /admin (sin abrir nada).
    from backend.services import copias
    out["conflictos"] = copias.resumen_bases()
    return out


def _fmt_par(v: Any) -> str:
    try:
        n, r = v
        return f"{n}/{r}" if n else "—"
    except (TypeError, ValueError):
        return "—"


def imprimir(inf: Dict[str, Any]) -> None:
    print(f"máquina   {inf['host']} · writer={'sí' if inf['writer'] else 'no'} ({inf.get('writer_motivo', '')}) · "
          f"autosave={'sí' if inf['autosave'] else 'no'}")
    print(f"journal   {inf['journal_dir']}")
    if inf.get("error"):
        print(f"ERROR     {inf['error']}")
        return
    print(f"carpeta   {inf['carpeta']}")
    for k, a in inf["archivos"].items():
        if a["existe"]:
            print(f"  {k:<10} {a['bytes']:>12,} bytes  {a['mtime']}".replace(",", "."))
        else:
            print(f"  {k:<10} (no existe)")
    print(f"espejo    {'FIEL al Excel' if inf['espejo_fiel'] else 'NO es copia fiel del Excel → manda el Excel'}")
    print(f"base      {inf['ruedas_en_base']} ruedas · última {inf['ultima'] or '—'}")
    mf = inf["manifiesto"]
    print(f"manifest  {mf['host'] or '—'} {mf['cuando'] or ''} · {mf['ruedas']} ruedas · última {mf['ultima'] or '—'}")
    print()
    print(f"{'rueda':<12}{'base n/real':>13}{'memoria':>11}{'manifest':>11}{'journal':>9}  estado")
    for f in inf["ruedas"]:
        jr = "—" if f["journal_reales"] is None else str(f["journal_reales"])
        print(f"{f['fecha']:<12}{_fmt_par(f['base']):>13}{_fmt_par(f['memoria']):>11}"
              f"{_fmt_par(f['manifiesto']):>11}{jr:>9}  {f['estado']}")
    print()
    reg = inf["regresion"]
    if reg["ruedas"]:
        print(f"REGRESIÓN  perdió {', '.join(reg['ruedas'])}")
        for d, v in reg["detalle"].items():
            print(f"  {d}: {v['motivo']} (antes {v['antes'][0]} filas / {v['antes'][1]} reales, ahora {v['ahora'][0]} / {v['ahora'][1]})")
        print(f"  repone el journal de esta máquina: {', '.join(reg['recuperables']) or 'ninguna'}")
        print(f"  frenan la escritura: {', '.join(reg['bloqueantes']) or 'ninguna'}")
    else:
        print("regresión  ninguna: la base tiene todo lo que esta máquina vio y lo que dice el manifiesto")
    cp = reg.get("contenido_perdido") or {}
    if cp:
        print(f"CONTENIDO  filas reales que journaleaste y ya NO están en la base (igual conteo, posible "
              f"reemplazo entre réplicas): {', '.join(f'{d} ({n})' for d, n in sorted(cp.items()))}")
        print("           revisá / reponé del journal (no frena la escritura por sí solo)")
    print(f"journal    {inf['journal']['dias']} días · último {inf['journal']['ultimo'] or '—'}")
    if inf["ignorados"]:
        print(f"ignorados  {', '.join(inf['ignorados'])}")
    if inf["conflictos"]:
        print("CONFLICTOS en la carpeta (copias de OneDrive / restos):")
        for n in inf["conflictos"]:
            print(f"  {n}")
    else:
        print("conflictos ninguno en la carpeta")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Chequeo (sólo lectura) de la base histórica px/tasas")
    ap.add_argument("--ruedas", type=int, default=15, help="cuántas ruedas hábiles hacia atrás listar")
    ap.add_argument("--json", action="store_true", help="salida JSON")
    args = ap.parse_args(argv)
    inf = informe(max(1, args.ruedas))
    if args.json:
        print(json.dumps(inf, ensure_ascii=False, indent=1, default=str))
    else:
        imprimir(inf)
    return 1 if inf.get("error") or inf.get("regresion", {}).get("ruedas") else 0


if __name__ == "__main__":
    sys.exit(main())
