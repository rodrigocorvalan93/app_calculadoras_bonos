"""Backfill del historial FX diario (Delta - historico_fx: CCL, MEP y canje).

El autosave arma la serie desde el día que se prende; este tool completa la
historia ANTERIOR desde una fuente externa para que Series diarias sirva
desde el primer día — y de ahí en más manda lo que graba la app. Corre
SIEMPRE fuera de la app (nunca en un request), en la máquina que ve la
carpeta Delta Bases:

  python -m backend.tools.backfill_fx --argentinadatos --dry-run
      muestra qué fechas entrarían (rango, cantidad, empalme) SIN escribir nada
  python -m backend.tools.backfill_fx --argentinadatos
      ArgentinaDatos (api.argentinadatos.com): series diarias de CCL
      ("contadoconliqui") y MEP ("bolsa"); de compra/venta se guarda el
      promedio (o el único lado que haya). canje = ccl/mep − 1.
  python -m backend.tools.backfill_fx --csv fx.csv
      columnas: fecha, ccl, mep [, canje] (encabezado libre de mayúsculas;
      fecha ISO o DD/MM/AAAA; decimales con coma o punto; separador , ; o tab).

Reglas — con mucho cuidado:
  · Sólo entran fechas ANTERIORES a la primera fila que grabó la app; con
    --huecos, también los días hábiles que faltan DENTRO del rango de la app.
  · NUNCA se pisa una fila existente: lo que grabó la app queda tal cual.
  · Las filas externas llevan ccl_base = "ext:<fuente>" (trazabilidad).
  · Antes de escribir se copia el Excel (y el espejo) a *.bak-<fecha-hora>.
  · La escritura es la MISMA del autosave (historico_writer.escribir_fx):
    xlsx atómico con reintentos + espejo parquet + firma del espejo.
  · Fines de semana y valores no positivos quedan afuera.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)                           # secrets relativos a la raíz

_AD_BASE = "https://api.argentinadatos.com/v1/cotizaciones/dolares/"
_AD_CASAS = {"ccl": "contadoconliqui", "mep": "bolsa"}
_TIMEOUT = 20.0
_TLS_INSEGURO = False


def _fecha(s: Any) -> Optional[date]:
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def _num(s: Any) -> Optional[float]:
    """Número positivo y finito (es-AR o punto decimal), o None."""
    from backend.locale_ar import parse_ar_num
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        v = float(s)
    else:
        v = parse_ar_num(s)
        if v is None:
            return None
    return v if math.isfinite(v) and v > 0 else None


def _promedio(compra: Any, venta: Any) -> Optional[float]:
    c, v = _num(compra), _num(venta)
    if c is not None and v is not None:
        return (c + v) / 2.0
    return c if c is not None else v


def _canje(ccl: Optional[float], mep: Optional[float]) -> Optional[float]:
    return (ccl / mep - 1.0) if (ccl and mep) else None


# ── Fuentes ──────────────────────────────────────────────────────────────────
def parsear_argentinadatos(payload_ccl: Any, payload_mep: Any) -> "Any":
    """Listas de {"fecha": "AAAA-MM-DD", "compra": x, "venta": y} (una por
    casa) → DataFrame [fecha_hoy, ccl, mep, canje], un día por fila, sólo días
    hábiles. Ítems raros (sin fecha, sin valor) se saltean."""
    import pandas as pd

    por_dia: Dict[date, Dict[str, float]] = {}
    for col, payload in (("ccl", payload_ccl), ("mep", payload_mep)):
        if not isinstance(payload, list):
            continue
        for it in payload:
            if not isinstance(it, dict):
                continue
            f = _fecha(it.get("fecha"))
            if f is None or f.weekday() >= 5:
                continue
            v = _promedio(it.get("compra"), it.get("venta"))
            if v is None:
                v = _num(it.get("valor"))
            if v is None:
                continue
            por_dia.setdefault(f, {})[col] = v
    rows = []
    for f in sorted(por_dia):
        d = por_dia[f]
        ccl, mep = d.get("ccl"), d.get("mep")
        rows.append({"fecha_hoy": f, "ccl": ccl, "mep": mep, "canje": _canje(ccl, mep)})
    return pd.DataFrame(rows, columns=["fecha_hoy", "ccl", "mep", "canje"])


def descargar_argentinadatos(session: Any = None) -> "Any":
    """Baja las dos series (best-effort; un error de red sube como excepción)."""
    import requests

    s = session or requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (app_calculadoras_bonos backfill_fx)", "Accept": "application/json"})
    payloads: Dict[str, Any] = {}
    for col, casa in _AD_CASAS.items():
        url = _AD_BASE + casa
        kw: Dict[str, Any] = {"timeout": _TIMEOUT}
        if _TLS_INSEGURO:
            import warnings
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            kw["verify"] = False
        r = s.get(url, **kw)
        r.raise_for_status()
        payloads[col] = r.json()
        print(f"  {casa}: {len(payloads[col]) if isinstance(payloads[col], list) else '?'} ítems")
    return parsear_argentinadatos(payloads["ccl"], payloads["mep"])


def importar_csv(path: str) -> "Any":
    """CSV con fecha, ccl, mep [, canje] — encabezado libre de mayúsculas."""
    import csv

    import pandas as pd

    with open(path, encoding="utf-8-sig", newline="") as fh:
        head = fh.readline()
        fh.seek(0)
        sep = max((";", ",", "\t"), key=head.count)
        rd = csv.DictReader(fh, delimiter=sep)
        cols = {c.strip().lower(): c for c in (rd.fieldnames or [])}

        def col(*names):
            return next((cols[n] for n in names if n in cols), None)

        c_f, c_ccl, c_mep, c_cj = (col("fecha", "date", "fecha_hoy"), col("ccl", "contadoconliqui", "cable"),
                                   col("mep", "bolsa", "usb"), col("canje", "brecha"))
        if not c_f or not (c_ccl or c_mep):
            raise SystemExit("el CSV necesita columnas fecha y ccl y/o mep")
        rows = []
        for r in rd:
            f = _fecha(r.get(c_f))
            if f is None or f.weekday() >= 5:
                continue
            ccl = _num(r.get(c_ccl)) if c_ccl else None
            mep = _num(r.get(c_mep)) if c_mep else None
            if ccl is None and mep is None:
                continue
            cj = _num(r.get(c_cj)) if c_cj else None
            rows.append({"fecha_hoy": f, "ccl": ccl, "mep": mep, "canje": cj if cj is not None else _canje(ccl, mep)})
    df = pd.DataFrame(rows, columns=["fecha_hoy", "ccl", "mep", "canje"])
    return df.drop_duplicates(subset=["fecha_hoy"], keep="last").sort_values("fecha_hoy").reset_index(drop=True)


# ── Plan y aplicación ─────────────────────────────────────────────────────────
def _leer_previo(xlsx: str, pq: str, escribir: bool) -> "Any":
    """Historial existente. Al escribir se usa el lector del writer (aparta un
    xlsx ilegible con espejo sano, como el autosave). En dry-run se lee SIN
    efectos secundarios (nada se renombra)."""
    import pandas as pd

    from backend.services import espejo, historico_writer as hw

    if escribir:
        prev = hw._leer_fx_previo(xlsx, pq, pd)
    else:
        prev = None
        hay_x, hay_p = os.path.isfile(xlsx), os.path.isfile(pq)
        if hay_x or hay_p:
            orden = [(pq, pd.read_parquet), (xlsx, pd.read_excel)] if (hay_p and espejo.espejo_valido(pq, xlsx)) \
                else [(xlsx, pd.read_excel), (pq, pd.read_parquet)]
            errores = []
            for p, reader in orden:
                if not os.path.isfile(p):
                    continue
                try:
                    prev = reader(p)
                    break
                except Exception as exc:  # noqa: BLE001
                    errores.append(f"{os.path.basename(p)}: {exc}")
            if prev is None:
                raise RuntimeError("el historial FX existe pero no se pudo leer: " + "; ".join(errores))
    if prev is not None and len(prev):
        prev = prev.copy()
        prev["fecha_hoy"] = pd.to_datetime(prev["fecha_hoy"], errors="coerce").dt.date
        prev = prev[prev["fecha_hoy"].notna()].reset_index(drop=True)
    return prev


def planificar(externo: "Any", previo: "Any", desde: Optional[date] = None,
               hasta: Optional[date] = None, huecos: bool = False) -> Dict[str, Any]:
    """Qué filas externas entran: las ANTERIORES a la primera fecha de la app
    y, con `huecos`, los días hábiles que faltan dentro de su rango. Las
    fechas que la app ya tiene NUNCA entran. Devuelve el plan + el empalme
    (último externo vs primera fila de la app) para mirarlo antes de escribir."""
    ext = externo.copy()
    if desde is not None:
        ext = ext[ext["fecha_hoy"] >= desde]
    if hasta is not None:
        ext = ext[ext["fecha_hoy"] <= hasta]
    ext = ext.sort_values("fecha_hoy").reset_index(drop=True)
    plan: Dict[str, Any] = {"primera_app": None, "ultima_app": None, "n_app": 0,
                            "externo_rango": (ext["fecha_hoy"].min(), ext["fecha_hoy"].max()) if len(ext) else (None, None),
                            "huecos": 0, "empalme": None}
    if previo is None or not len(previo):
        plan["nuevas"] = ext
        return plan
    fechas_app = set(previo["fecha_hoy"])
    primera, ultima = min(fechas_app), max(fechas_app)
    plan.update(primera_app=primera, ultima_app=ultima, n_app=len(fechas_app))
    antes = ext["fecha_hoy"] < primera
    if huecos:
        adentro = (ext["fecha_hoy"] >= primera) & (ext["fecha_hoy"] <= ultima) & ~ext["fecha_hoy"].isin(fechas_app)
        plan["huecos"] = int(adentro.sum())
        antes = antes | adentro
    plan["nuevas"] = ext[antes].reset_index(drop=True)
    # Empalme: la última fecha externa que entra vs la primera de la app.
    if len(plan["nuevas"]):
        u = plan["nuevas"][plan["nuevas"]["fecha_hoy"] < primera]
        fila_app = previo[previo["fecha_hoy"] == primera].iloc[0]
        if len(u):
            u = u.iloc[-1]
            plan["empalme"] = {"fecha_ext": u["fecha_hoy"], "ccl_ext": u["ccl"], "mep_ext": u["mep"],
                               "fecha_app": primera, "ccl_app": fila_app.get("ccl"), "mep_app": fila_app.get("mep")}
    return plan


def aplicar(hist_dir: str, externo: "Any", fuente: str, desde: Optional[date] = None,
            hasta: Optional[date] = None, huecos: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    import pandas as pd

    from backend.services.historico_writer import FX_COLUMNAS, FX_FILENAME, escribir_fx

    xlsx = os.path.join(hist_dir, FX_FILENAME)
    pq = os.path.splitext(xlsx)[0] + ".parquet"
    previo = _leer_previo(xlsx, pq, escribir=not dry_run)
    plan = planificar(externo, previo, desde, hasta, huecos)
    nuevas = plan["nuevas"]
    plan["insertadas"] = int(len(nuevas))
    plan["dry_run"] = dry_run
    if dry_run or not len(nuevas):
        return plan
    # Respaldo antes de tocar nada (evidencia; nunca se borra).
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan["backups"] = []
    for p in (xlsx, pq):
        if os.path.isfile(p):
            bak = f"{p}.bak-{marca}"
            shutil.copy2(p, bak)
            plan["backups"].append(bak)
    nuevas = nuevas.copy()
    nuevas["ccl_base"] = f"ext:{fuente}"
    columnas = list(FX_COLUMNAS)
    if previo is not None and len(previo):
        columnas += [c for c in previo.columns if c not in columnas]
        partes = [previo, nuevas]
    else:
        partes = [nuevas]
    df = pd.concat(partes, ignore_index=True)
    for c in columnas:
        if c not in df.columns:
            df[c] = None
    df = df[columnas].sort_values("fecha_hoy").reset_index(drop=True)
    assert not df["fecha_hoy"].duplicated().any(), "fechas duplicadas: no debería pasar"
    res = escribir_fx(df, xlsx)
    plan.update(filas_total=res["filas"], xlsx=xlsx)
    return plan


def _print_plan(plan: Dict[str, Any], fuente: str) -> None:
    r0, r1 = plan["externo_rango"]
    print(f"fuente {fuente}: {r0} → {r1}")
    if plan["primera_app"]:
        print(f"la app grabó {plan['n_app']} días: {plan['primera_app']} → {plan['ultima_app']}")
    else:
        print("la app todavía no grabó ninguna fila: entra toda la serie externa")
    print(f"entrarían {plan['insertadas']} fechas" + (f" ({plan['huecos']} huecos dentro del rango de la app)" if plan["huecos"] else "")
          + (" · sólo anteriores a la primera de la app" if plan["primera_app"] and not plan["huecos"] else ""))
    e = plan.get("empalme")
    if e:
        def _f(v):
            return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        print(f"empalme: {e['fecha_ext']} ext ccl {_f(e['ccl_ext'])} / mep {_f(e['mep_ext'])}  →  "
              f"{e['fecha_app']} app ccl {_f(e['ccl_app'])} / mep {_f(e['mep_app'])}")
    if plan.get("dry_run"):
        print("dry-run: no se escribió nada")
    elif plan.get("xlsx"):
        print(f"escrito: {plan['xlsx']} · {plan['filas_total']} filas · respaldos: {', '.join(plan.get('backups') or ['—'])}")
    elif not plan["insertadas"]:
        print("nada para insertar — el archivo queda como estaba")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill del historial FX (Históricos → Series diarias: CCL, MEP, canje)")
    ap.add_argument("--argentinadatos", action="store_true", help="bajar CCL y MEP de api.argentinadatos.com")
    ap.add_argument("--csv", help="CSV con fecha, ccl, mep [, canje]")
    ap.add_argument("--desde", help="AAAA-MM-DD: primera fecha externa a considerar")
    ap.add_argument("--hasta", help="AAAA-MM-DD: última fecha externa a considerar")
    ap.add_argument("--huecos", action="store_true", help="también completar días hábiles faltantes DENTRO del rango de la app")
    ap.add_argument("--dry-run", action="store_true", help="mostrar el plan sin escribir")
    ap.add_argument("--destino", help="carpeta del historial (default: Delta Bases de secrets.txt)")
    ap.add_argument("--tls-inseguro", action="store_true", help="si la cadena TLS falla, bajar SIN verificar (sólo esta bajada)")
    a = ap.parse_args(argv)
    global _TLS_INSEGURO
    _TLS_INSEGURO = bool(a.tls_inseguro)
    if not a.argentinadatos and not a.csv:
        ap.print_help()
        return 2
    from backend.services import deltapaths

    hist_dir = a.destino or deltapaths.historico_dir()
    if not hist_dir or not os.path.isdir(hist_dir):
        print("no encuentro la carpeta 'Delta Bases' (DELTA_HISTORICO_DIR / DELTA_BASES_DIR en secrets.txt, o --destino)")
        return 1
    try:
        if a.csv:
            fuente, externo = "csv", importar_csv(a.csv)
        else:
            fuente = "argentinadatos"
            print("ArgentinaDatos…")
            externo = descargar_argentinadatos()
    except Exception as exc:  # noqa: BLE001
        print(f"no pude obtener la serie externa ({exc}) — el archivo queda como estaba")
        return 1
    if externo is None or not len(externo):
        print("la fuente no devolvió filas válidas — el archivo queda como estaba")
        return 1
    try:
        plan = aplicar(hist_dir, externo, fuente, _fecha(a.desde), _fecha(a.hasta), a.huecos, a.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"ABORTADO sin escribir: {exc}")
        return 1
    _print_plan(plan, fuente)
    return 0


if __name__ == "__main__":
    sys.exit(main())
