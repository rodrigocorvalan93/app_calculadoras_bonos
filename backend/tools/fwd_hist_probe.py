"""Sonda por FRAME del panel "Histórico del forward" (/forwards, `#fwd-hist`):
registra, con Playwright contra un server con ticks, lo que el ojo lee como
"el gráfico se mueve" — posición (viewport) del card, de las tarjetas, del ⧉,
del svg y del pie; frames sin ⧉; swaps / settles de `#fwd-hist`; `md-update`;
entradas `layout-shift` del browser con el nodo que se movió.

    DEV_TICKS_HIST=1 python backend/tools/dev_ticks.py 8765     # base histórica sintética
    python backend/tools/fwd_hist_probe.py http://127.0.0.1:8765/forwards [segundos] [ancho] [alto]

`PROBE_PAIR=CORTO,LARGO` elige el par (default TZXD6,TZXY7: con la base
sintética cualquier par de la curva CER con duration distinta rinde);
`PROBE_SHOT=/ruta.png` guarda una captura al final. Playwright no es
dependencia del proyecto (`pip install playwright && playwright install
chromium`, o `PW_CHROMIUM=/ruta/a/chrome`). Imprime un JSON: lo que importa es
`btn_missing_frames`, `changes_n` (cambios de posición entre frames) y
`layout_shifts_n` → todo 0 = panel quieto aunque se actualice en cada tick.
Medido el 22/10 (fix del ⧉ flotante + inyección en afterSwap): antes 10
frames sin botón y 16 cambios (svg 1381 → 1387 → 1381, card 626 → 632 → 626)
en 8 s; después 0 / 0 / 0."""
from __future__ import annotations

import json
import os
import sys
import time

PROBE = r"""
() => {
  const rec = { frames: 0, changes: [], shifts: [], swaps: [], settles: [], mdu: [], t0: performance.now(), btnMissing: 0 };
  const po = new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      rec.shifts.push({ t: Math.round(e.startTime - rec.t0), v: +e.value.toFixed(5),
        src: (e.sources || []).slice(0, 5).map(s => {
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
    const t = e.detail && e.detail.target; if (t && t.id === 'fwd-hist') rec.swaps.push(Math.round(performance.now() - rec.t0));
  });
  document.body.addEventListener('htmx:afterSettle', (e) => {
    const t = e.detail && e.detail.target; if (t && t.id === 'fwd-hist') rec.settles.push(Math.round(performance.now() - rec.t0));
  });
  function snap() {
    const q = (s) => document.querySelector(s);
    const top = (el) => el ? Math.round(el.getBoundingClientRect().top * 10) / 10 : null;
    const h = (el) => el ? Math.round(el.getBoundingClientRect().height * 10) / 10 : null;
    const hist = q('#fwd-hist');
    const btn = hist ? hist.querySelector('.chart-copy') : null;
    const svg = hist ? hist.querySelector('svg') : null;
    const card = hist ? hist.closest('.card') : null;
    let btnCss = null;
    if (btn) { const cs = getComputedStyle(btn); btnCss = [cs.height, cs.marginBottom, cs.display, cs.position, cs.cssFloat || cs.float].join('|'); }
    return {
      scrollY: Math.round(window.scrollY * 10) / 10, docH: document.documentElement.scrollHeight,
      card: top(card), cardH: h(card),
      grid: top(hist && hist.querySelector('.metrics-grid')),
      btn: top(btn), btnH: h(btn), btnCss,
      svg: top(svg), svgH: h(svg),
      pie: top(hist && hist.querySelector(':scope > p')),
      wi: !!(hist && hist.querySelector('.fc-dot-wi')),
    };
  }
  let last = null;
  function tick() {
    rec.frames++;
    const t = Math.round(performance.now() - rec.t0);
    const s = snap();
    if (!s.btn) rec.btnMissing++;
    if (last) {
      const d = {};
      for (const k in s) if (s[k] !== last[k]) d[k] = [last[k], s[k]];
      if (Object.keys(d).length) rec.changes.push({ t, d });
    }
    last = s;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  window.__probe = rec;
  window.__snap = snap;
}
"""


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - herramienta manual
        sys.exit("falta playwright: pip install playwright && playwright install chromium")
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/forwards"
    segs = float(sys.argv[2]) if len(sys.argv) > 2 else 8
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1882
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 910
    launch = {"executable_path": os.environ["PW_CHROMIUM"]} if os.environ.get("PW_CHROMIUM") else {}
    with sync_playwright() as p:
        b = p.chromium.launch(**launch)
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(url, wait_until="networkidle")
        pair = os.environ.get("PROBE_PAIR", "TZXD6,TZXY7").split(",")
        if len(pair) == 2 and pair[0]:
            pg.select_option("select[name=fw-corto]", pair[0])
            pg.select_option("select[name=fw-largo]", pair[1])
        pg.wait_for_selector("#fwd-hist svg", timeout=30000)
        # El what-if (arriba del histórico) se carga al revelarse y empuja el
        # card: se lo revela primero y recién después se ubica el histórico.
        pg.evaluate("() => { document.querySelector('#forwards-whatif').scrollIntoView({block:'start'}); }")
        pg.wait_for_function("() => !/Cargando what-if/.test(document.querySelector('#forwards-whatif').textContent)", timeout=30000)
        pg.wait_for_timeout(500)
        pg.evaluate("() => { const c = document.querySelector('#fwd-hist').closest('.card'); "
                    "c.scrollIntoView({block: 'start'}); window.scrollBy(0, -60); }")
        pg.wait_for_timeout(1500)
        pg.evaluate(PROBE)
        time.sleep(segs)
        rec = pg.evaluate("() => window.__probe")
        snap = pg.evaluate("() => window.__snap()")
        if os.environ.get("PROBE_SHOT"):
            pg.screenshot(path=os.environ["PROBE_SHOT"])
        b.close()
    out = {"frames": rec["frames"], "md_update_n": len(rec["mdu"]), "swaps": rec["swaps"], "settles": rec["settles"],
           "btn_missing_frames": rec["btnMissing"], "final": snap,
           "changes_n": len(rec["changes"]), "changes": rec["changes"][:30],
           "layout_shifts_n": len([s for s in rec["shifts"] if s["t"] > 0]),
           "layout_shifts": [s for s in rec["shifts"] if s["t"] > 0][:20]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
