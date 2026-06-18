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

  var advances = [];   // timestamps de avances (ventana 60s) → ticks/min
  function meta(rtt) {
    var el = document.getElementById('live-meta');
    if (!el) return;
    var now = Date.now();
    while (advances.length && now - advances[0] > 60000) advances.shift();
    el.textContent = advances.length ? (advances.length + ' t/min · ' + Math.round(rtt) + ' ms') : '';
  }
  function poll() {
    if (document.hidden) return; // visibilitychange re-arma
    var t0 = performance.now();
    fetch('/market/seq', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (txt) {
        failures = 0;
        var rtt = performance.now() - t0;
        var seq = parseInt(txt, 10);
        if (isNaN(seq)) return;
        if (lastSeq !== null && seq !== lastSeq) {
          lastAdvance = Date.now();
          advances.push(lastAdvance);
          dot('live', 'En vivo — tick hace instantes');
          if (window.htmx) { window.htmx.trigger(document.body, 'md-update'); }
        } else if (Date.now() - lastAdvance > QUIET_AFTER_MS) {
          dot('idle', 'Sin operaciones recientes');
        }
        meta(rtt);
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
    // genérico: cualquier valor con [data-fl="clave"] (barra de activos, etc.)
    var fls = root.querySelectorAll('[data-fl]');
    for (var f = 0; f < fls.length; f++) {
      map['fl|' + fls[f].getAttribute('data-fl')] = (fls[f].textContent || '').trim();
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
    var fls = t.querySelectorAll('[data-fl]');
    for (var q = 0; q < fls.length; q++) {
      var was3 = num(old['fl|' + fls[q].getAttribute('data-fl')]);
      var now3 = num((fls[q].textContent || '').trim());
      if (was3 === null || now3 === null || was3 === now3) continue;
      flash(fls[q], now3 > was3 ? 'tick-up' : 'tick-down');
    }
  });
})();

// ── Orden por columna (client-side, genérico) ─────────────────────────────
// Tablas con [data-sortable]: click en un th[data-sort] ordena por esa
// columna (numérico es-AR si se puede, si no alfabético). El estado se
// guarda por id de tabla y se re-aplica tras cada swap de htmx, así el
// orden elegido sobrevive a los refrescos live. Cero requests.
(function () {
  var state = {}; // tableId -> { idx, dir }

  function cellVal(row, idx) {
    var c = row.cells[idx];
    if (!c) return '';
    var inp = c.querySelector('input');
    return (inp ? inp.value : c.textContent || '').trim();
  }
  function parseAr(txt) {
    if (!txt) return null;
    var s = txt.replace(/[▲▼%\s]/g, '').replace(/\./g, '').replace(',', '.');
    if (s === '' || s === '—' || s === '-' || s === '·') return null;
    var v = parseFloat(s);
    return isNaN(v) ? null : v;
  }
  function applySort(table) {
    var st = state[table.id];
    if (!st) return;
    var tbody = table.tBodies[0];
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var va = cellVal(a, st.idx), vb = cellVal(b, st.idx);
      var na = parseAr(va), nb = parseAr(vb);
      var r;
      if (na !== null && nb !== null) r = na - nb;
      else if (na !== null) r = -1;          // números antes que texto/vacíos
      else if (nb !== null) r = 1;
      else r = va.localeCompare(vb, 'es');
      return st.dir * r;
    });
    for (var i = 0; i < rows.length; i++) tbody.appendChild(rows[i]);
    var ths = table.querySelectorAll('th[data-sort]');
    for (var j = 0; j < ths.length; j++) ths[j].classList.remove('sort-asc', 'sort-desc');
    var th = table.rows[0] && table.rows[0].cells[st.idx];
    if (th) th.classList.add(st.dir > 0 ? 'sort-asc' : 'sort-desc');
  }
  document.body.addEventListener('click', function (evt) {
    var th = evt.target.closest && evt.target.closest('th[data-sort]');
    if (!th) return;
    var table = th.closest('table[data-sortable]');
    if (!table || !table.id) return;
    var idx = th.cellIndex;
    var st = state[table.id];
    state[table.id] = { idx: idx, dir: (st && st.idx === idx) ? -st.dir : 1 };
    applySort(table);
  });
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    var t = evt.detail.target;
    if (!t || !t.querySelectorAll) return;
    var tables = t.querySelectorAll('table[data-sortable]');
    for (var i = 0; i < tables.length; i++) applySort(tables[i]);
  });
})();

// Filtro de texto client-side para tablas live: un <input data-table-filter="#id">
// oculta las filas del tbody que no contienen el texto (en cualquier celda).
// Vive FUERA del contenedor que swapea htmx, así el filtro persiste; se
// re-aplica tras cada swap. Cero requests.
(function () {
  function apply(input) {
    var table = document.querySelector(input.getAttribute('data-table-filter'));
    if (!table || !table.tBodies[0]) return;
    var q = (input.value || '').trim().toLowerCase();
    var rows = table.tBodies[0].rows;
    for (var i = 0; i < rows.length; i++) {
      var ok = !q || (rows[i].textContent || '').toLowerCase().indexOf(q) >= 0;
      rows[i].style.display = ok ? '' : 'none';
    }
  }
  document.body.addEventListener('input', function (e) {
    if (e.target && e.target.getAttribute && e.target.getAttribute('data-table-filter')) apply(e.target);
  });
  document.body.addEventListener('htmx:afterSwap', function () {
    var ins = document.querySelectorAll('[data-table-filter]');
    for (var i = 0; i < ins.length; i++) if ((ins[i].value || '').trim()) apply(ins[i]);
  });
})();

// ── Posiciones: Last editable + retorno ponderado del día ────────────────
// Todo client-side: ret_i = Last_ajustado / PxVal − 1 (escala automática por
// potencias de 10 — el Excel valúa por VN 1 y BYMA cotiza por VN 100), y el
// retorno del fondo = Σ (valor_i/Σvalor) · ret_i. Las ediciones del usuario
// se guardan por especie y se re-aplican tras cada refresh live.
(function () {
  var overrides = {}; // especie -> string editado por el usuario

  function parseAr(txt) {
    if (!txt) return null;
    var s = String(txt).replace(/\s/g, '').replace(/\./g, '').replace(',', '.');
    if (s === '' || s === '—') return null;
    var v = parseFloat(s);
    return isNaN(v) ? null : v;
  }
  function fmtPct(x) {
    var s = (x * 100).toFixed(2).replace('.', ',');
    return (x > 0 ? '+' : '') + s + '%';
  }
  function recalc() {
    var tbl = document.getElementById('pos-tbl');
    if (!tbl || !tbl.tBodies[0]) return;
    var rows = tbl.tBodies[0].rows;
    var totV = 0, acc = 0, any = false;
    var rets = [];
    for (var i = 0; i < rows.length; i++) {
      var tr = rows[i];
      var pxv = parseFloat(tr.dataset.pxval);
      var valor = parseFloat(tr.dataset.valor);
      var inp = tr.querySelector('.pos-last');
      var last = inp ? parseAr(inp.value) : null;
      var ret = null;
      if (pxv > 0 && last !== null && last > 0) {
        var f = 1, k = 0;
        while (last * f / pxv > 5 && k < 8) { f /= 10; k++; }
        while (last * f / pxv < 0.2 && k < 16) { f *= 10; k++; }
        var ratio = last * f / pxv;
        if (ratio > 0.2 && ratio < 5) ret = ratio - 1;
      }
      rets.push(ret);
      if (ret !== null && valor > 0) { totV += valor; acc += valor * ret; any = true; }
      var cell = tr.querySelector('.pos-ret');
      if (cell) {
        cell.textContent = ret === null ? '—' : fmtPct(ret);
        cell.classList.remove('var-up', 'var-down');
        if (ret !== null) cell.classList.add(ret >= 0 ? 'var-up' : 'var-down');
      }
    }
    var chip = document.getElementById('pos-day-ret');
    if (chip) {
      if (any && totV > 0) {
        var r = acc / totV;
        chip.textContent = 'Ret. día ' + fmtPct(r);
        chip.classList.remove('var-up', 'var-down');
        chip.classList.add(r >= 0 ? 'var-up' : 'var-down');
      } else {
        chip.textContent = 'Ret. día —';
        chip.classList.remove('var-up', 'var-down');
      }
    }
  }
  function reapply() {
    var tbl = document.getElementById('pos-tbl');
    if (!tbl || !tbl.tBodies[0]) return;
    var rows = tbl.tBodies[0].rows;
    for (var i = 0; i < rows.length; i++) {
      var esp = rows[i].dataset.esp;
      var inp = rows[i].querySelector('.pos-last');
      if (esp && inp && overrides[esp] !== undefined) inp.value = overrides[esp];
    }
    recalc();
  }
  document.body.addEventListener('input', function (evt) {
    var inp = evt.target;
    if (!inp.classList || !inp.classList.contains('pos-last')) return;
    var tr = inp.closest('tr');
    if (tr && tr.dataset.esp) overrides[tr.dataset.esp] = inp.value;
    recalc();
  });
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    var t = evt.detail.target;
    if (t && (t.id === 'pos-fondo' || (t.querySelector && t.querySelector('#pos-tbl')))) reapply();
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', reapply);
  else reapply();
})();
