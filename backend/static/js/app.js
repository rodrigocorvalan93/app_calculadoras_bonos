// Minimal client-side glue: htmx + Alpine + the "live" engine.
//
// Live engine (zero new deps):
//   1) SSE (/market/events): el server PUSHEA la seq del store cuando avanza
//      — un tick llega a pantalla en ~250 ms, sin requests de sondeo (clave
//      en el celular: la radio no se despierta 1×/s). Si EventSource no
//      conecta (proxy viejo, 401, browser raro) cae solo al plan B: poll de
//      /market/seq cada 1 s, el motor anterior. En ambos casos, al avanzar
//      la seq se dispara un único `md-update` en <body> — cada panel con
//      `hx-trigger="md-update from:body, …"` se re-renderiza. Sin mercado,
//      nada se re-renderiza.
//   2) Pause completely while the tab is hidden; catch up on return.
//   3) Tick flashes: before each swap of a `[data-flash-scope]` container we
//      snapshot its numeric cells (key = first cell of the row + column);
//      after the swap, cells whose value moved get .tick-up / .tick-down
//      (a CSS background flash, like a broker terminal).
//   4) Live dot in the topbar: green pulse while ticks flow, gray when the
//      market is quiet, amber if the feed is unreachable.

// El riel del dólar se oculta con Alpine (x-show) pero queda en el DOM, así que
// sin esto seguía polleando /dolares/rail en cada md-update + cada 30s aunque
// estuviera plegado. El trigger del riel usa [fxRailOpen()] como filtro htmx.
window.fxRailOpen = function () {
  var l = document.querySelector('.layout');
  return !l || !l.classList.contains('rail-closed');
};

(function () {
  // htmx custom event hooks (debug logging behind a flag).
  if (window.localStorage.getItem('yas_debug') === '1') {
    document.body.addEventListener('htmx:afterRequest', function (evt) {
      console.log('[htmx]', evt.detail.requestConfig.verb, evt.detail.requestConfig.path, evt.detail.xhr.status);
    });
  }

  // ── 1+2+4: motor live (SSE con fallback a polling) ────────────────────
  var POLL_MS = 1000;       // cadencia del fallback
  var QUIET_AFTER_MS = 20000; // sin avances por 20s → dot "quieto"
  var HEALTH_MS = 15000;      // cada ~15s chequeo el estado del feed
  var lastSeq = null;
  var lastAdvance = 0;
  var failures = 0;
  var timer = null;
  var healthTimer = null;
  var feedDown = false;       // el broker tiene sesión pero el WS está caído
  var sse = null;             // EventSource activo (null = modo polling)
  var sseEverOk = false;      // llegó a conectar al menos una vez

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
    // Feed caído: aviso explícito en la topbar (el dot rojo solo puede pasar
    // desapercibido; el trader tiene que SABER que ve precios congelados).
    if (feedDown) {
      el.textContent = '⚠ Feed caído';
      el.classList.add('feed-down-txt');
      return;
    }
    el.classList.remove('feed-down-txt');
    var now = Date.now();
    while (advances.length && now - advances[0] > 60000) advances.shift();
    // rtt sólo aplica al fallback de polling; con SSE (push) no hay RTT que medir.
    var rttTxt = (rtt !== null && rtt !== undefined) ? ' · ' + Math.round(rtt) + ' ms' : '';
    el.textContent = advances.length ? (advances.length + ' t/min' + rttTxt) : '';
  }
  // Estado real del feed del broker (liviano, cada ~15s): distingue "feed caído"
  // (sesión abierta pero WS del broker desconectado → precios congelados) de
  // "mercado quieto" (conectado, sin operaciones). Sin esto el dot mostraba
  // 'idle' en ambos casos y el trader no sabía que veía precios viejos.
  function checkHealth() {
    fetch('/market/health', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (h) { feedDown = !!(h && h.feed_down); })
      .catch(function () { /* dejamos el estado previo del feed */ });
  }

  // En el celular, re-renderizar todos los paneles en cada tick gasta batería
  // del TELÉFONO al pedo (el server aguanta de sobra): coalescamos los
  // md-update a uno cada MOBILE_MIN_MS, con disparo trailing — el último tick
  // siempre llega a pantalla, sólo se espacian los intermedios. Desktop igual.
  var IS_MOBILE = !!(window.matchMedia &&
    window.matchMedia('(max-width: 980px), (pointer: coarse)').matches);
  var MOBILE_MIN_MS = 2500;
  var lastDispatch = 0, pendingDispatch = null;
  function dispatchUpdate() {
    if (!window.htmx) return;
    if (!IS_MOBILE) { window.htmx.trigger(document.body, 'md-update'); return; }
    var now = Date.now();
    var wait = lastDispatch + MOBILE_MIN_MS - now;
    if (wait <= 0) {
      lastDispatch = now;
      window.htmx.trigger(document.body, 'md-update');
    } else if (!pendingDispatch) {
      pendingDispatch = setTimeout(function () {
        pendingDispatch = null;
        lastDispatch = Date.now();
        if (window.htmx) window.htmx.trigger(document.body, 'md-update');
      }, wait);
    }
  }

  // Núcleo compartido SSE/polling: avanzó la seq → md-update + dot + meta.
  function handleSeq(seq, rtt) {
    if (isNaN(seq)) return;
    var advanced = (lastSeq !== null && seq !== lastSeq);
    if (advanced) {
      lastAdvance = Date.now();
      advances.push(lastAdvance);
      dispatchUpdate();
    }
    // Prioridad del dot: feed caído (rojo) > tick en vivo (verde) > quieto (gris).
    if (feedDown) {
      dot('down', 'Feed caído — el WS del broker está desconectado; los precios pueden estar congelados');
    } else if (advanced) {
      dot('live', 'En vivo — tick hace instantes');
    } else if (Date.now() - lastAdvance > QUIET_AFTER_MS) {
      dot('idle', 'Sin operaciones recientes');
    }
    meta(rtt);
    lastSeq = seq;
  }

  function poll() {
    if (document.hidden) return; // visibilitychange re-arma
    var t0 = performance.now();
    fetch('/market/seq', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (txt) {
        failures = 0;
        handleSeq(parseInt(txt, 10), performance.now() - t0);
      })
      .catch(function () {
        failures += 1;
        if (failures >= 3) dot('off', 'Sin conexión con el feed');
      });
  }

  function stopAll() {
    if (timer) { clearInterval(timer); timer = null; }
    if (sse) { try { sse.close(); } catch (e) { } sse = null; }
    if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
  }
  function armPoll() {
    if (timer) clearInterval(timer);
    timer = setInterval(poll, POLL_MS);
    poll();
  }
  // SSE primero; el primer evento trae la seq actual como baseline. Si nunca
  // conecta (404/proxy/401) → polling. Cortes transitorios los reconecta el
  // propio EventSource (retry del server); mientras, dot en 'off'.
  function startSSE() {
    if (!window.EventSource) return false;
    try { sse = new EventSource('/market/events'); } catch (e) { return false; }
    sse.onmessage = function (ev) {
      sseEverOk = true;
      failures = 0;
      handleSeq(parseInt(ev.data, 10), null);
    };
    sse.onerror = function () {
      if (!sseEverOk) {           // nunca conectó: este entorno no soporta SSE
        if (sse) { try { sse.close(); } catch (e) { } sse = null; }
        armPoll();
        return;
      }
      dot('off', 'Reconectando al feed…'); // transitorio: EventSource reintenta solo
    };
    return true;
  }
  function arm() {
    stopAll();
    checkHealth();
    healthTimer = setInterval(function () { if (!document.hidden) checkHealth(); }, HEALTH_MS);
    if (!startSSE()) armPoll();
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) arm(); // al volver: reconexión inmediata + baseline fresco
    else stopAll();              // oculto: ni SSE abierto ni polls (batería)
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
    el.addEventListener('animationend', function h(e) {
      // La clase corre DOS animaciones: el flash de color (tick-up/tick-down,
      // 0,9s) y un tick-pop de escala (0,22s). Sin filtrar por animationName, el
      // animationend del pop (que termina primero) removía la clase y cortaba el
      // flash a 0,22s. Esperamos el fin de la animación de color (nombre = cls).
      if (e.animationName !== cls) return;
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

// Filtros de tabla client-side (texto + reglas numéricas por columna). Un
// contenedor <div data-table-filters="#id"> con [data-f-text] (filtro por
// ticker), [data-f-col]/[data-f-op]/[data-f-val]/[data-f-add] (regla numérica
// ≥/≤ sobre una columna) y [data-f-chips] (reglas activas). Vive FUERA del
// contenedor que swapea htmx → persiste y se re-aplica tras cada refresh live.
// Cero requests, sin tocar formatos: parsea los valores ya renderizados
// (es-AR + sufijos k/M/MM/B de ar_hum).
(function () {
  function parseNum(txt) {
    if (txt == null) return null;
    var s = String(txt).replace(/[▲▼%]/g, '').trim();
    if (s === '' || s === '—' || s === '-' || s === '·') return null;
    var mult = 1, m = s.match(/(MM|B|M|k)\s*$/);   // sufijos de ar_hum (MM antes que M)
    if (m) { mult = { k: 1e3, M: 1e6, MM: 1e9, B: 1e12 }[m[1]]; s = s.slice(0, m.index); }
    s = s.replace(/\s/g, '').replace(/\./g, '').replace(',', '.');  // es-AR: '.' miles, ',' decimal
    var v = parseFloat(s);
    return isNaN(v) ? null : v * mult;
  }
  function cellVal(row, idx) {
    var c = row.cells[idx]; if (!c) return '';
    var inp = c.querySelector('input');
    return inp ? inp.value : (c.textContent || '');
  }
  var state = {}; // sel -> { text, rules:[{idx,label,op,val,valTxt}] }

  function st(sel) { return state[sel] || (state[sel] = { text: '', rules: [] }); }

  function buildCols(bar, table) {
    var colSel = bar.querySelector('[data-f-col]');
    if (!colSel || colSel.options.length) return;        // ya armado
    var ths = table.querySelectorAll('thead th'), html = '';
    for (var i = 0; i < ths.length; i++) {
      if (!ths[i].hasAttribute('data-sort')) continue;   // sólo columnas de dato
      html += '<option value="' + i + '">' + (ths[i].textContent || '').trim() + '</option>';
    }
    colSel.innerHTML = html;
  }
  function chips(bar, sel) {
    var box = bar.querySelector('[data-f-chips]'); if (!box) return;
    box.innerHTML = '';
    st(sel).rules.forEach(function (r, i) {
      var sp = document.createElement('span'); sp.className = 'mix-chip';
      sp.appendChild(document.createTextNode(r.label + ' ' + (r.op === '>=' ? '≥' : '≤') + ' ' + r.valTxt + ' '));
      var b = document.createElement('button'); b.type = 'button'; b.textContent = '✕';
      b.onclick = function () { st(sel).rules.splice(i, 1); apply(sel); chips(bar, sel); };
      sp.appendChild(b); box.appendChild(sp);
    });
  }
  function apply(sel) {
    var s = st(sel), table = document.querySelector(sel);
    if (!table || !table.tBodies[0]) return;
    var q = (s.text || '').toLowerCase(), rows = table.tBodies[0].rows;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], ok = !q || (r.textContent || '').toLowerCase().indexOf(q) >= 0;
      for (var k = 0; ok && k < s.rules.length; k++) {
        var rule = s.rules[k], v = parseNum(cellVal(r, rule.idx));
        ok = (v !== null) && (rule.op === '>=' ? v >= rule.val : v <= rule.val);
      }
      r.style.display = ok ? '' : 'none';
    }
  }
  function initAll() {
    document.querySelectorAll('[data-table-filters]').forEach(function (bar) {
      var sel = bar.getAttribute('data-table-filters'), table = document.querySelector(sel);
      if (table) { st(sel); buildCols(bar, table); chips(bar, sel); }
    });
  }
  document.body.addEventListener('input', function (e) {
    var t = e.target;
    if (t && t.hasAttribute && t.hasAttribute('data-f-text')) {
      var bar = t.closest('[data-table-filters]'), sel = bar.getAttribute('data-table-filters');
      st(sel).text = t.value; apply(sel);
    }
  });
  document.body.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-f-add]');
    if (!btn) return;
    var bar = btn.closest('[data-table-filters]'), sel = bar.getAttribute('data-table-filters');
    var col = bar.querySelector('[data-f-col]'), op = bar.querySelector('[data-f-op]'), val = bar.querySelector('[data-f-val]');
    var num = parseNum(val.value);
    if (num === null || !col.options.length) return;
    st(sel).rules.push({ idx: +col.value, label: col.options[col.selectedIndex].text, op: op.value, val: num, valTxt: val.value.trim() });
    val.value = ''; apply(sel); chips(bar, sel);
  });
  document.body.addEventListener('htmx:afterSwap', function () {
    document.querySelectorAll('[data-table-filters]').forEach(function (bar) {
      var sel = bar.getAttribute('data-table-filters');
      if (state[sel] && (state[sel].text || state[sel].rules.length)) apply(sel);
    });
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else initAll();
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

// ── Ctrl+K: búsqueda global (bonos → YAS · pestañas por nombre) ────────────
// Overlay client-side puro: el universo se baja UNA vez (/market/codes, cache
// en memoria) y las pestañas se leen del nav ya renderizado (respeta el rol).
// Cero costo por request: filtrar es un loop en JS sobre ~550 códigos.
(function () {
  var codes = null, box = null, inp = null, list = null, sel = 0, items = [];

  function ensureBox() {
    if (box) return;
    box = document.createElement("div");
    box.id = "ck-overlay";
    box.innerHTML = '<div id="ck-panel"><input id="ck-input" type="text" ' +
      'placeholder="Bono (T15E7, GD30C…) o pestaña (curvas, escenario…)" autocomplete="off">' +
      '<ul id="ck-list"></ul><div id="ck-hint" class="muted">↑↓ moverse · Enter abrir · Esc cerrar</div></div>';
    document.body.appendChild(box);
    inp = box.querySelector("#ck-input");
    list = box.querySelector("#ck-list");
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    inp.addEventListener("input", render);
    inp.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { sel = Math.min(sel + 1, items.length - 1); paint(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); paint(); e.preventDefault(); }
      else if (e.key === "Enter") { go(); e.preventDefault(); }
      else if (e.key === "Escape") { close(); }
    });
  }
  function tabs() {
    var out = [];
    document.querySelectorAll(".topbar nav a[href]").forEach(function (a) {
      var label = (a.textContent || "").trim();
      if (label) out.push({ kind: "tab", label: label, href: a.getAttribute("href") });
    });
    return out;
  }
  function open() {
    ensureBox();
    box.style.display = "flex";
    inp.value = ""; sel = 0;
    if (!codes) {
      fetch("/market/codes").then(function (r) { return r.json(); })
        .then(function (d) { codes = d.items || []; render(); }).catch(function () { codes = []; });
    }
    render();
    inp.focus();
  }
  function close() { if (box) box.style.display = "none"; }
  function render() {
    var q = (inp.value || "").trim().toUpperCase();
    items = [];
    if (q) {
      tabs().forEach(function (t) {
        if (t.label.toUpperCase().indexOf(q) >= 0) items.push(t);
      });
      (codes || []).forEach(function (b) {
        if (items.length >= 12) return;
        if (b.c.toUpperCase().indexOf(q) === 0) items.push({ kind: "bond", label: b.c, sub: b.v, href: "/yas?code=" + encodeURIComponent(b.c) });
      });
      if (items.length < 12) (codes || []).forEach(function (b) {
        if (items.length >= 12) return;
        if (b.c.toUpperCase().indexOf(q) > 0) items.push({ kind: "bond", label: b.c, sub: b.v, href: "/yas?code=" + encodeURIComponent(b.c) });
      });
    } else {
      items = tabs().slice(0, 12);
    }
    sel = 0;
    paint();
  }
  function paint() {
    list.innerHTML = "";
    items.forEach(function (it, i) {
      var li = document.createElement("li");
      li.className = i === sel ? "ck-sel" : "";
      li.innerHTML = (it.kind === "bond" ? "📈 " : "🗂 ") + "<b></b>" +
        (it.sub ? ' <span class="muted"></span>' : "");
      li.querySelector("b").textContent = it.label;
      if (it.sub) li.querySelector("span").textContent = "vto " + it.sub;
      li.addEventListener("click", function () { sel = i; go(); });
      list.appendChild(li);
    });
  }
  function go() {
    var it = items[sel];
    if (it && it.href) window.location.href = it.href;
  }
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      (box && box.style.display === "flex") ? close() : open();
    }
  });
})();
