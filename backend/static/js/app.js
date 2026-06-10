// Minimal client-side glue: htmx + Alpine + the "live" engine.
//
// Live engine (zero new deps):
//   1) Poll /market/seq every 1s (a plain int, ~µs server-side). When it
//      advances, fire a single `md-update` event on <body> — every panel
//      declaring `hx-trigger="md-update from:body, …"` re-renders. Result:
//      a real tick reaches the screen in ~1s, and with no market activity
//      nothing re-renders at all (cheaper than the old fixed every-5/15s).
//   2) Pause completely while the tab is hidden; catch up on return.
//   3) Tick flashes: before each swap of a `[data-flash-scope]` container we
//      snapshot its numeric cells (key = first cell of the row + column);
//      after the swap, cells whose value moved get .tick-up / .tick-down
//      (a CSS background flash, like a broker terminal).
//   4) Live dot in the topbar: green pulse while ticks flow, gray when the
//      market is quiet, amber if /market/seq is unreachable.

(function () {
  // htmx custom event hooks (debug logging behind a flag).
  if (window.localStorage.getItem('yas_debug') === '1') {
    document.body.addEventListener('htmx:afterRequest', function (evt) {
      console.log('[htmx]', evt.detail.requestConfig.verb, evt.detail.requestConfig.path, evt.detail.xhr.status);
    });
  }

  // ── 1+2+4: seq poller ──────────────────────────────────────────────────
  var POLL_MS = 1000;       // cadencia base
  var QUIET_AFTER_MS = 20000; // sin avances por 20s → dot "quieto"
  var lastSeq = null;
  var lastAdvance = 0;
  var failures = 0;
  var timer = null;

  function dot(state, title) {
    var el = document.getElementById('live-dot');
    if (!el) return;
    el.dataset.state = state;
    el.title = title || '';
  }

  function poll() {
    if (document.hidden) return; // visibilitychange re-arma
    fetch('/market/seq', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (txt) {
        failures = 0;
        var seq = parseInt(txt, 10);
        if (isNaN(seq)) return;
        if (lastSeq !== null && seq !== lastSeq) {
          lastAdvance = Date.now();
          dot('live', 'En vivo — tick hace instantes');
          if (window.htmx) { window.htmx.trigger(document.body, 'md-update'); }
        } else if (Date.now() - lastAdvance > QUIET_AFTER_MS) {
          dot('idle', 'Sin operaciones recientes');
        }
        lastSeq = seq;
      })
      .catch(function () {
        failures += 1;
        if (failures >= 3) dot('off', 'Sin conexión con el feed');
      });
  }

  function arm() {
    if (timer) clearInterval(timer);
    timer = setInterval(poll, POLL_MS);
    poll();
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) arm(); // al volver: chequeo inmediato + re-arma
    else if (timer) { clearInterval(timer); timer = null; }
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arm);
  } else { arm(); }

  // ── 3: tick flashes ────────────────────────────────────────────────────
  var MAX_CELLS = 1500; // tope de trabajo por swap (tablas gigantes: skip)

  // '1.234,56' / '7,23%' / '▲ 0,33' → float (es-AR). null si no es número.
  function num(txt) {
    if (!txt) return null;
    var s = txt.replace(/[▲▼%\s]/g, '').replace(/\./g, '').replace(',', '.');
    if (s === '' || s === '—' || s === '-') return null;
    var v = parseFloat(s);
    return isNaN(v) ? null : v;
  }

  // key por (índice de tabla | 1ª celda de la fila | nº de columna): en Dólares
  // conviven varias tablas con los mismos tickers — sin el índice colisionan.
  function snapshot(root) {
    var map = {};
    var tables = root.querySelectorAll('table');
    var n = 0;
    for (var ti = 0; ti < tables.length; ti++) {
      var rows = tables[ti].querySelectorAll('tbody tr');
      for (var i = 0; i < rows.length; i++) {
        var cells = rows[i].cells;
        if (!cells || !cells.length) continue;
        var key = ti + '|' + (cells[0].textContent || '').trim();
        if (key === ti + '|') continue;
        for (var j = 1; j < cells.length; j++) {
          if (++n > MAX_CELLS) return map;
          map[key + '|' + j] = (cells[j].textContent || '').trim();
        }
      }
    }
    // riel del dólar: .rail-l (label) → .rail-v (valor)
    var items = root.querySelectorAll('.rail-item');
    for (var k = 0; k < items.length; k++) {
      var l = items[k].querySelector('.rail-l');
      var v = items[k].querySelector('.rail-v');
      if (l && v) map['rail|' + (l.textContent || '').trim()] = (v.textContent || '').trim();
    }
    return map;
  }

  function flash(el, cls) {
    el.classList.remove('tick-up', 'tick-down');
    void el.offsetWidth; // reinicia la animación si ya estaba corriendo
    el.classList.add(cls);
    el.addEventListener('animationend', function h() {
      el.classList.remove(cls);
      el.removeEventListener('animationend', h);
    });
  }

  var pre = {};
  document.body.addEventListener('htmx:beforeSwap', function (evt) {
    var t = evt.detail.target;
    if (t && t.hasAttribute && t.hasAttribute('data-flash-scope')) {
      pre[t.id || 'x'] = snapshot(t);
    }
  });
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    var t = evt.detail.target;
    if (!t || !t.hasAttribute || !t.hasAttribute('data-flash-scope')) return;
    var old = pre[t.id || 'x'];
    delete pre[t.id || 'x'];
    if (!old) return;
    var tables = t.querySelectorAll('table');
    var n = 0;
    for (var ti = 0; ti < tables.length; ti++) {
      var rows = tables[ti].querySelectorAll('tbody tr');
      for (var i = 0; i < rows.length; i++) {
        var cells = rows[i].cells;
        if (!cells || !cells.length) continue;
        var key = ti + '|' + (cells[0].textContent || '').trim();
        if (key === ti + '|') continue;
        for (var j = 1; j < cells.length; j++) {
          if (++n > MAX_CELLS) return;
          var was = num(old[key + '|' + j]);
          var now = num((cells[j].textContent || '').trim());
          if (was === null || now === null || was === now) continue;
          flash(cells[j], now > was ? 'tick-up' : 'tick-down');
        }
      }
    }
    var items = t.querySelectorAll('.rail-item');
    for (var k = 0; k < items.length; k++) {
      var l = items[k].querySelector('.rail-l');
      var v = items[k].querySelector('.rail-v');
      if (!l || !v) continue;
      var was2 = num(old['rail|' + (l.textContent || '').trim()]);
      var now2 = num((v.textContent || '').trim());
      if (was2 === null || now2 === null || was2 === now2) continue;
      flash(v, now2 > was2 ? 'tick-up' : 'tick-down');
    }
  });
})();
