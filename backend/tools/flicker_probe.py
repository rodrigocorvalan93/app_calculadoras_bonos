"""Sonda del parpadeo de un panel live (Mercado): abre la página con Playwright
contra un server con ticks (`backend/tools/dev_ticks.py`) y durante N segundos
registra POR FRAME lo que un ojo lee como "salto del recuadro":

- alto del card de la tabla (`#mercado-table .card`) y anchos de las columnas
  del thead (cambios = la tabla se mueve / las columnas se corren),
- scroll horizontal de `.table-scroll` (¿un swap lo resetea?) y si aparece o
  desaparece la barra horizontal,
- frames sin el botón ⧉ (se inyecta adentro del swap), frames con el
  contenedor atenuado (opacity ≠ 1) y con celdas en flash,
- eventos md-update / swaps completos de htmx y las entradas `layout-shift`
  del browser con el nodo que se movió (antes y después, en px).

    python backend/tools/flicker_probe.py <url> [segundos] [ancho] [alto] [panel]

`panel` = valor del select de /mercado (lideres, general, cedears…); sin
panel mide Renta Fija (delta por filas: un swap completo cada 30 s). Playwright
no es dependencia del proyecto: `pip install playwright && playwright install
chromium`, o `PW_CHROMIUM=/ruta/a/chrome` para usar un Chromium ya instalado.
Imprime un JSON con los conteos (lo que importa: card_height_changes_n,
col_width_changes_n, btn_missing_frames, dim_opacity_frames,
scroll_left_changes_n y layout_shifts después de t=0 → todo 0 = recuadro
quieto; flash_frames alto es lo esperado: el flash de color sigue)."""
from __future__ import annotations

import json
import os
import sys
import time

PROBE = r"""
() => {
  const rec = { frames: 0, cardH: [], colW: [], btnMissing: 0, flashFrames: 0, dimFrames: 0, hscroll: [],
                shifts: [], swaps: [], mdu: [], t0: performance.now(), rowsN: 0, scrollLeft: [] };
  const po = new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      rec.shifts.push({ t: Math.round(e.startTime - rec.t0), v: +e.value.toFixed(5),
        src: (e.sources || []).slice(0, 4).map(s => {
          const n = s.node; if (!n) return 'null';
          const cls = (n.className && typeof n.className === 'string') ? '.' + n.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
          const p = s.previousRect, c = s.currentRect;
          return (n.tagName || '#text') + (n.id ? '#' + n.id : '') + cls + ' ' +
                 [p.x | 0, p.y | 0, p.width | 0, p.height | 0].join('x') + '->' + [c.x | 0, c.y | 0, c.width | 0, c.height | 0].join('x');
        }) });
    }
  });
  po.observe({ type: 'layout-shift', buffered: true });
  document.body.addEventListener('md-update', () => rec.mdu.push(Math.round(performance.now() - rec.t0)));
  document.body.addEventListener('htmx:afterSwap', (e) => {
    const t = e.detail && e.detail.target; if (t && t.id === 'mercado-table') rec.swaps.push(Math.round(performance.now() - rec.t0));
  });
  let lastH = null, lastW = null, lastHS = null, lastSL = null;
  function tick() {
    rec.frames++;
    const t = Math.round(performance.now() - rec.t0);
    const scope = document.getElementById('mercado-table');
    const card = document.querySelector('#mercado-table .card');
    const tbl = document.querySelector('#mercado-table table');
    const tsc = document.querySelector('#mercado-table .table-scroll');
    if (card) {
      const h = Math.round(card.getBoundingClientRect().height * 10) / 10;
      if (lastH !== null && h !== lastH) rec.cardH.push([t, lastH, h]);
      lastH = h;
    }
    if (tbl && tbl.tHead) {
      rec.rowsN = tbl.tBodies[0] ? tbl.tBodies[0].rows.length : 0;
      const ws = Array.from(tbl.tHead.rows[0].cells).map(c => Math.round(c.getBoundingClientRect().width * 10) / 10);
      const key = ws.join(',');
      if (lastW !== null && key !== lastW) {
        const a = lastW.split(',').map(Number), d = [];
        for (let i = 0; i < ws.length; i++) if (a[i] !== ws[i]) d.push([i, a[i], ws[i]]);
        rec.colW.push([t, d]);
      }
      lastW = key;
    }
    if (tsc) {
      const hs = tsc.scrollWidth > tsc.clientWidth + 1;
      if (lastHS !== null && hs !== lastHS) rec.hscroll.push([t, hs]);
      lastHS = hs;
      const sl = tsc.scrollLeft;
      if (lastSL !== null && sl !== lastSL) rec.scrollLeft.push([t, lastSL, sl]);
      lastSL = sl;
    }
    if (!document.querySelector('#mercado-table .tbl-copy')) rec.btnMissing++;
    if (document.querySelector('#mercado-table td.tick-up, #mercado-table td.tick-down')) rec.flashFrames++;
    if (scope && getComputedStyle(scope).opacity !== '1') rec.dimFrames++;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  window.__probe = rec;
}
"""


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - herramienta manual
        sys.exit("falta playwright: pip install playwright && playwright install chromium")
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mercado"
    segs = float(sys.argv[2]) if len(sys.argv) > 2 else 45
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1920
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 1080
    panel = sys.argv[5] if len(sys.argv) > 5 else ""
    launch = {"executable_path": os.environ["PW_CHROMIUM"]} if os.environ.get("PW_CHROMIUM") else {}
    with sync_playwright() as p:
        b = p.chromium.launch(**launch)
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_selector("#mercado-table tbody tr")
        if panel:
            pg.select_option("select[name=panel]", panel)
            pg.wait_for_timeout(2500)
            pg.wait_for_selector("#mercado-table tbody tr")
        pg.wait_for_timeout(1500)
        # scroll horizontal adentro de la tabla (si desborda): un swap NO debe resetearlo
        pg.evaluate("() => { const t = document.querySelector('#mercado-table .table-scroll'); if (t) t.scrollLeft = 150; }")
        pg.wait_for_timeout(300)
        pg.evaluate(PROBE)
        time.sleep(segs)
        rec = pg.evaluate("() => window.__probe")
        b.close()
    out = {
        "viewport": [w, h], "panel": panel or "rf", "frames": rec["frames"], "rows": rec["rowsN"],
        "md_update_n": len(rec["mdu"]), "full_swaps_n": len(rec["swaps"]),
        "card_height_changes_n": len(rec["cardH"]), "card_height_changes": rec["cardH"][:12],
        "col_width_changes_n": len(rec["colW"]), "col_width_changes": rec["colW"][:12],
        "hscroll_toggles": rec["hscroll"], "btn_missing_frames": rec["btnMissing"],
        "dim_opacity_frames": rec["dimFrames"], "flash_frames": rec["flashFrames"],
        "scroll_left_changes_n": len(rec["scrollLeft"]), "scroll_left_changes": rec["scrollLeft"][:8],
        "layout_shifts_n": len(rec["shifts"]), "layout_shift_total": round(sum(s["v"] for s in rec["shifts"]), 5),
        "layout_shifts_after_t0": [s for s in rec["shifts"] if s["t"] > 0][:40],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
