"""Captura headless del cierre — para el Programador de tareas / cron.

Guarda la base histórica del día AUNQUE LA APP ESTÉ CERRADA: se conecta al
feed con las mismas credenciales/secrets que la app, espera los snapshots del
día, corre el mismo `save_today` de siempre (journal local + base compartida +
FX + mail de cierre) y sale.

    python -m backend.tools.cierre              # guards normales (finde, ya guardado, mín. operados)
    python -m backend.tools.cierre --force      # como el botón manual (sin guards de calendario)
    python -m backend.tools.cierre --timeout 180

Salida: 0 = guardado o salteado por calendario ("ya tiene filas de hoy", finde,
feriado); 1 = error (sin credenciales, login, feed sin datos, base ilegible).
Si la app está abierta y ya guardó, sale enseguida sin conectarse.

Windows (PC writer) — dos disparos por si el primero encuentra el feed a medio
poblar. El propio script fija el working dir en la raíz del repo (schtasks no
lo setea), así encuentra secrets.txt / .env:

    schtasks /Create /F /TN "Bonos cierre 17:05" /SC WEEKLY /D LUN,MAR,MIE,JUE,VIE /ST 17:05 ^
        /TR "\"C:\\ruta\\a\\python.exe\" -m backend.tools.cierre"
    schtasks /Create /F /TN "Bonos cierre 17:35" /SC WEEKLY /D LUN,MAR,MIE,JUE,VIE /ST 17:35 ^
        /TR "\"C:\\ruta\\a\\python.exe\" -m backend.tools.cierre"

mac/linux: cron  `5,35 17 * * 1-5  cd /ruta/app && python -m backend.tools.cierre`.

El chip "cierre" de la topbar lo refleja igual: lee la base, no la memoria de
la app.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("backend.tools.cierre")


def precheck(force: bool) -> Optional[Dict[str, Any]]:
    """Skips que no necesitan feed: fin de semana y base que ya tiene hoy.
    None = hay que conectarse y capturar."""
    from backend.services import deltapaths, historico_writer as hw

    if force:
        return None
    if hw._now().weekday() >= 5:
        return {"ok": False, "skipped": "fin de semana"}
    hist_dir = deltapaths.historico_dir()
    if hist_dir and hw._ya_guardado_hoy(os.path.join(hist_dir, hw.HIST_FILENAME)):
        return {"ok": True, "skipped": "la base ya tiene filas de hoy"}
    return None


async def capturar(force: bool = False, timeout: float = 150.0,
                   min_espera: float = 15.0) -> Dict[str, Any]:
    """Feed arriba → esperar los snapshots del día → save_today → feed abajo."""
    from backend.config import settings
    from backend.services import bond_universe, historico_writer as hw, store_persist
    from backend.services.primary_ws import get_ws_client

    pre = precheck(force)
    if pre is not None:
        return pre
    if not (settings.primary_user and settings.primary_pass):
        return {"ok": False, "error": "sin PRIMARY_USER / PRIMARY_PASS (secrets.txt / .env)"}
    bond_universe.ensure_loaded()
    try:
        store_persist.load()        # arranca con los cierres pegajosos; el feed los pisa
    except Exception:  # noqa: BLE001
        logger.exception("[cierre] restore del store falló (sigo)")
    from backend.main import _initial_symbols       # mismo seed que la app

    ws = get_ws_client()
    try:
        ok = await ws.login(settings.primary_user, settings.primary_pass)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"login al broker falló: {exc}"}
    if not ok:
        return {"ok": False, "error": "login al broker rechazado"}
    seed = _initial_symbols()
    await ws.start(symbols=seed)
    logger.info("[cierre] feed arriba: %d símbolos; esperando los snapshots del día…", len(seed))
    t0 = time.monotonic()
    n = 0
    minimo = settings.historico_autosave_min_operados
    while time.monotonic() - t0 < timeout:
        await asyncio.sleep(3.0)
        n = hw.operados_en_store()
        if n >= minimo and time.monotonic() - t0 >= min_espera:
            break
    logger.info("[cierre] %d bonos con operaciones de hoy en el store (mínimo %d) tras %.0f s",
                n, minimo, time.monotonic() - t0)
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, lambda: hw.save_today(force=force))
    if res.get("ok") and not res.get("skipped"):
        # Mismo mail de cierre que manda el autosave de la app (best-effort).
        try:
            from backend.services import quepaso_report
            await loop.run_in_executor(None, quepaso_report.send_close_mail)
        except Exception:  # noqa: BLE001
            logger.exception("[cierre] mail de cierre falló")
    try:
        await asyncio.wait_for(ws.stop(), timeout=10.0)
    except Exception:  # noqa: BLE001
        pass
    return res


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Captura headless del cierre (base histórica px/tasas)")
    ap.add_argument("--force", action="store_true",
                    help="sin guards de calendario (como el botón manual de Históricos)")
    ap.add_argument("--timeout", type=float, default=150.0, help="segundos máximos esperando el feed")
    args = ap.parse_args(argv)
    from backend.config import REPO_ROOT
    os.chdir(REPO_ROOT)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = asyncio.run(capturar(force=args.force, timeout=args.timeout))
    if res.get("skipped"):
        print(f"cierre: salteado — {res['skipped']}")
        return 0
    if res.get("ok"):
        print(f"cierre: OK — {res.get('rows')} filas de hoy ({res.get('operados')} operados) → {res.get('xlsx')}")
        return 0
    print(f"cierre: ERROR — {res.get('error') or 'no se guardó'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
