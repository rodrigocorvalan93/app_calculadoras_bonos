/* Charts client-side con uPlot. Por ahora: Gráficos (scatter TIREA vs Duration
 * + curva NSS). El server manda JSON (rápido); uPlot dibuja con zoom (arrastrar),
 * hover y toggle de series por leyenda. Refresh cada 5 s vía setData (preserva
 * el zoom). Se auto-inicializa si está el contenedor de la página. */
(function () {
  "use strict";

  function cssVar(name, fb) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fb;
    } catch (e) { return fb; }
  }
  function fmtPct(v) { return (v == null) ? "" : (v.toFixed(2).replace(".", ",") + "%"); }
  function fmtNum(v) { return (v == null) ? "" : v.toFixed(2).replace(".", ","); }
  // Fechas de las series históricas: el server manda la MEDIANOCHE UTC de cada
  // rueda. Formatearlas con el reloj local corría la etiqueta un día para
  // atrás en Buenos Aires (UTC-3 → "21:00 del día anterior"): eje, leyenda y
  // tabla decían 25/09 para el dato del 26/09. Todo en UTC.
  function utcTz(ts) { return uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC"); }
  function utcDia(v) { return uPlot.fmtDate("{DD}/{MM}/{YYYY}")(utcTz(v)); }
  // Eje x en es-AR (DD/MM; con el año cuando el rango pasa de un año) — el
  // default de uPlot es M/D.
  function ejeFechas(u, vals) {
    var span = vals.length > 1 ? (vals[vals.length - 1] - vals[0]) : 0;
    var f = uPlot.fmtDate(span > 365 * 86400 ? "{DD}/{MM}/{YY}" : "{DD}/{MM}");
    return vals.map(function (v) { return f(utcTz(v)); });
  }
  // Color de una serie ya inicializada: uPlot envuelve `stroke` en una función
  // (fnOrSelf) y deja el valor resuelto en `_stroke`. Asignar la función a
  // ctx.fillStyle se ignora → las etiquetas al final de cada línea salían con
  // el fillStyle anterior (negro: invisibles en el tema oscuro).
  function seriesColor(u, si) {
    var s = u.series[si];
    if (s._stroke != null) return s._stroke;
    return (typeof s.stroke === "function") ? s.stroke(u, si) : s.stroke;
  }
  // Etiqueta al final de cada línea visible (ticker [+ valor]), a la derecha
  // del último punto (en el padding derecho del chart), en píxeles del canvas
  // (escala por pxRatio). Las que caerían encima de otra se CORREN
  // verticalmente (apiladas con un mínimo de separación, el bloque entero sube
  // si se pasa del borde inferior) — antes se omitían y un activo que cerraba
  // pegado a otro se quedaba sin nombre. textAlign se fija explícitamente:
  // uPlot deja el estado del eje y ("right") en el contexto y las etiquetas
  // salían hacia la IZQUIERDA, pisando las líneas.
  function etiquetasFinales(u, texto) {
    var ctx = u.ctx, R = u.pxRatio || window.devicePixelRatio || 1, gap = 12 * R;
    var X = u.data[0], items = [];
    for (var si = 1; si < u.series.length; si++) {
      if (!u.series[si].show) continue;
      var ys = u.data[si], li = -1;
      for (var i = ys.length - 1; i >= 0; i--) { if (ys[i] != null) { li = i; break; } }
      if (li < 0) continue;
      items.push({ si: si, v: ys[li], x: u.valToPos(X[li], "x", true), y: u.valToPos(ys[li], "y", true) });
    }
    if (!items.length) return;
    items.sort(function (a, b) { return a.y - b.y; });
    var top = u.bbox.top + gap / 2, bot = u.bbox.top + u.bbox.height - gap / 2, k;
    for (k = 0; k < items.length; k++) {
      var y = Math.max(items[k].y, k > 0 ? items[k - 1].ly + gap : top);
      items[k].ly = y;
    }
    var exceso = items[items.length - 1].ly - bot;
    if (exceso > 0) for (k = 0; k < items.length; k++) items[k].ly -= exceso;
    ctx.save();
    ctx.font = Math.round(10 * R) + "px system-ui,-apple-system,sans-serif";
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    for (k = 0; k < items.length; k++) {
      var it = items[k];
      ctx.fillStyle = seriesColor(u, it.si);
      ctx.fillText(texto(u.series[it.si], it.v), it.x + 5 * R, it.ly);
    }
    ctx.restore();
  }

  // ── Tabla de Gráficos: filas desde el payload de /graficos/data ────────────
  // Lo que el chart dibuja como puntos, en cuadro: la curva principal en el
  // orden del eje x (duration) y después cada comparación, cada una ordenada
  // igual. Funciones PURAS (sin DOM ni requests): las usa initGraficos en cada
  // render y el harness tests/graficos_tabla_harness.cjs.
  function grafTablaRows(j) {
    var out = [];
    if (!j || !j.xs) return out;
    var meta = j.meta || {};
    function push(curva, codes, yAt) {
      if (!codes) return;
      for (var i = 0; i < codes.length; i++) {
        var c = codes[i];
        if (!c) continue;
        out.push({ curva: curva, code: c, x: j.xs[i], y: yAt(i), m: meta[c] || {} });
      }
    }
    push(null, j.codes, function (i) { return (j.ars && j.ars[i] != null) ? j.ars[i] : (j.usd ? j.usd[i] : null); });
    (j.cmps || []).forEach(function (c) { push(c.label, c.codes, function (i) { return c.vals ? c.vals[i] : null; }); });
    return out;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }
  // Precio con miles (es-AR): 1.234,56. Sin ICU cae al formato simple.
  function fmtPx(v) {
    if (v == null) return "—";
    try { return Number(v).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    catch (e) { return fmtNum(v); }
  }
  // thead + tbody de la tabla. `metric` = la del gráfico: en "margen" se agrega
  // la columna del margen graficado (la TIR sigue siendo la TIREA). `conCurva`
  // agrega la columna Curva (hay comparaciones): el label de la curva
  // principal si viene como string, "principal" si es true.
  function grafTablaHTML(rows, metric, conCurva) {
    var principal = (typeof conCurva === "string" && conCurva) ? conCurva : "principal";
    var cols = conCurva ? [["Curva", ""]] : [];
    cols = cols.concat([["Bono", ""], ["Vto.", ""], ["Calif.", ""], ["Industria", ""], ["Mon.", ""],
                        ["Precio", "num"], ["Fuente", ""], ["TIR", "num"], ["TNA", "num"], ["TEM", "num"], ["Dur", "num"]]);
    if (metric === "margen") cols.push(["Margen", "num"]);
    function pct(v) { return v == null ? "—" : fmtPct(v); }
    function num(v) { return v == null ? "—" : fmtNum(v); }
    var h = "<thead><tr>" + cols.map(function (c) {
      return "<th" + (c[1] ? ' class="' + c[1] + '"' : "") + ">" + c[0] + "</th>";
    }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var m = r.m || {}, cells = [];
      if (conCurva) cells.push(esc(r.curva || principal));
      cells.push("<b>" + esc(r.code) + "</b>", esc(m.vto || "—"), esc(m.cal || "—"), esc(m.ind || "—"),
                 esc(m.mon || "—"), fmtPx(m.p), esc(m.src || "—"), pct(m.tir), pct(m.tna), pct(m.tem),
                 num(m.dur != null ? m.dur : r.x));
      if (metric === "margen") cells.push(pct(r.y));
      h += "<tr>" + cells.map(function (v, i) {
        return "<td" + (cols[i][1] ? ' class="num"' : "") + ">" + v + "</td>";
      }).join("") + "</tr>";
    });
    return h + "</tbody>";
  }
  window.grafTablaRows = grafTablaRows;
  window.grafTablaHTML = grafTablaHTML;

  // ── Gráficos: scatter (Duration → TIREA) + regresión NSS ──────────────────
  function initGraficos() {
    var box = document.getElementById("grafico-uplot");
    var form = document.getElementById("graf-controls");
    if (!box || !form || typeof uPlot === "undefined") return;

    var ORANGE = cssVar("--accent", "#e0843c");
    var CYAN = cssVar("--cyan", "#22b8cf");
    var NSSCOL = "#a78bfa";
    var MUT = cssVar("--text-muted", "#8a8a8a");
    var BORD = cssVar("--border", "#333");
    var u = null, codes = [], yLabel = "TIREA (%)";
    // Zoom del usuario: si arrastró para hacer zoom, el auto-refresh NO debe
    // re-encuadrar (setData con reset pisa el zoom). `selfSet` evita que
    // nuestro propio setData se confunda con una interacción del usuario.
    var userZoomed = false, selfSet = false;

    box.style.position = "relative";
    var tip = document.createElement("div");
    tip.style.cssText = "position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--border);" +
      "border-radius:6px;padding:3px 8px;font-size:11px;line-height:1.35;display:none;z-index:6;white-space:nowrap;color:var(--text)";
    box.appendChild(tip);

    var cmpSel = [];   // [{key,label}] curvas de comparación elegidas (chips)

    // ── Nuevas emisiones / cortes de licitación (★) ─────────────────────────
    // El usuario tipea "ticker; tasa; duration [; nota]" (una por línea, tal cual
    // sale del aviso de resultados) y los puntos se dibujan como estrellas sobre
    // la curva, con la distancia a la NSS y al bono más cercano. 100 % client-
    // side: no hay requests ni cálculos nuevos (la NSS ya viene en el payload);
    // sólo se insertan x extra en el eje y se interpola la línea ahí. Persiste
    // en localStorage.
    var emisBox = document.getElementById("graf-emis");
    var emisN = document.getElementById("graf-emis-n");
    var STAR = "#ffd166";
    var emisCodes = null, emisInfo = {};   // codes alineados a xs · info por ticker
    var lastJ = null;                       // último payload (re-render sin re-fetch)
    // Referencia del "premio" de cada corte: la curva NSS y/o el instrumento
    // que se licita si YA cotiza en el gráfico (match por ticker: exacto o con
    // sufijo de pata, GD30 ↔ GD30C). Del instrumento se toma la TIR offer
    // (punta de venta = lo que paga el que compra en secundario) y, sin punta
    // (después del cierre, cuando salen los resultados), el último/cierre.
    // Todo sale del payload en memoria: cero requests, cero cálculos nuevos.
    //   min   → el menor de los dos premios (default; sin bono = curva)
    //   curva → siempre vs NSS · instr → vs el bono (sin bono = curva)
    var emisRefSel = document.getElementById("graf-emis-ref");
    function emisRefMode() { return emisRefSel ? emisRefSel.value : "min"; }
    function findInstr(j, ticker) {
      if (!j || !ticker) return null;
      var best = null;
      function consider(cds, offs, lastAt, label) {
        if (!cds) return;
        for (var i = 0; i < cds.length; i++) {
          var c = cds[i];
          if (!c) continue;
          var C = String(c).toUpperCase(), score;
          if (C === ticker) score = 3;
          else if (C.length === ticker.length + 1 && C.indexOf(ticker) === 0) score = 2;   // GD30 → GD30C
          else if (ticker.length === C.length + 1 && ticker.indexOf(C) === 0) score = 1;   // GD30C → GD30
          else continue;
          var yl = lastAt(i), yo = offs ? offs[i] : null;
          if (yl == null && yo == null) continue;
          if (!best || score > best.score) best = { code: c, x: j.xs[i], last: yl, off: yo, score: score, curve: label };
        }
      }
      consider(j.codes, j.off, function (i) { return j.ars[i] != null ? j.ars[i] : j.usd[i]; }, null);
      (j.cmps || []).forEach(function (c) { consider(c.codes, null, function (i) { return c.vals[i]; }, c.label); });
      if (!best) return null;
      best.y = (best.off != null) ? best.off : best.last;
      best.src = (best.off != null) ? "offer" : "últ.";
      return best;
    }
    // "27,5" / "27,5%" / "1.234,5" (es-AR) o "27.5" → número; null si no parsea.
    function num(s) {
      s = String(s == null ? "" : s).trim().replace(/%/g, "");
      if (s.indexOf(",") !== -1) s = s.replace(/\./g, "").replace(",", ".");
      var v = parseFloat(s);
      return isNaN(v) ? null : v;
    }
    function parseEmis() {
      if (!emisBox) return [];
      var out = [];
      emisBox.value.split(/\n/).forEach(function (line) {
        var f = line.split(/[;|\t]/).map(function (x) { return x.trim(); });
        if (f.length < 3 || !f[0]) return;
        var t = num(f[1]), d = num(f[2]);
        if (t == null || d == null || d < 0) return;
        out.push({ c: f[0].toUpperCase(), t: t, d: d, note: f.slice(3).join(" ").trim() });
      });
      out.sort(function (a, b) { return a.d - b.d; });
      if (emisN) emisN.textContent = out.length ? (out.length + " punto" + (out.length > 1 ? "s" : "")) : "";
      return out;
    }
    // Interpola lineal la curva (xs, ys) en x (clamp a los bordes; null si no hay curva).
    function interp(xs, ys, x) {
      if (!ys || ys.length !== xs.length || xs.length < 2) return null;
      var xq = Math.min(Math.max(x, xs[0]), xs[xs.length - 1]), k = 0;
      while (k < xs.length - 1 && xs[k + 1] < xq) k++;
      var k1 = Math.min(k + 1, xs.length - 1), y0 = ys[k], y1 = ys[k1];
      if (y0 == null && y1 != null) y0 = y1;
      if (y1 == null && y0 != null) y1 = y0;
      if (y0 == null || y1 == null) return null;
      return (xs[k1] > xs[k]) ? y0 + (y1 - y0) * (xq - xs[k]) / (xs[k1] - xs[k]) : y0;
    }
    function fmtPP(v) { return (v >= 0 ? "+" : "") + v.toFixed(2).replace(".", ",") + " pp"; }

    function params() {
      var p = {};
      form.querySelectorAll("[name]").forEach(function (el) {
        p[el.name] = (el.type === "checkbox") ? (el.checked ? "true" : "false") : el.value;
      });
      // Las comparaciones NO son campos del form (son chips): se arman acá.
      p.curve2 = cmpSel.map(function (c) { return c.key; }).join(",");
      return new URLSearchParams(p).toString();
    }

    function scatter(label, color, size) {
      return { label: label, stroke: color, paths: function () { return null; },
               points: { show: true, size: size || 7, stroke: color, fill: color },
               value: function (uu, v) { return fmtPct(v); } };
    }
    var GREEN = cssVar("--green", "#22c55e"), RED = cssVar("--red", "#ef4444");

    // Comparaciones: hasta 3 curvas, cada una un color (puntos + NSS punteada).
    var CMP_COLORS = ["#f472b6", "#facc15", "#a3e635", "#38bdf8", "#c084fc"];
    var cmps = [];          // [{label, vals[], codes[], nss[]}] del último payload
    var meta = {};          // { code: {p,src,dt,tir,tna,tem,dur,mon,bp,bt,op,ot} }
    var sig = "";           // firma estructural (labels de cmps) → recrea al cambiar
    var SCAT = [];          // [{si, kind, ci}] serie uPlot → rol (labels + tooltip)

    // codes del rol (main = array `codes`; comparación = cmps[ci].codes). Se lee
    // en cada draw/hover, así el auto-refresh (setData) no usa un array viejo.
    function codesOf(e) {
      if (e.kind === "emis") return emisCodes;
      return e.ci < 0 ? codes : (cmps[e.ci] ? cmps[e.ci].codes : null);
    }

    // Tooltip chico (≤4 líneas, 11px): código · moneda / precio · tipo · fecha /
    // TIR · TNA / TEM · Dur. Para bid/offer muestra la punta y su TIR.
    function tipHTML(code, m, kind) {
      var head = "<b>" + code + "</b>";
      if (kind === "emis") {
        var em = emisInfo[code];
        if (!em) return head + " · licitación";
        var o = head + " · licitación" + (em.note ? " · " + em.note : "");
        o += "<br>tasa " + fmtPct(em.t) + " · Dur " + fmtNum(em.d);
        // Las dos distancias; "premio" marca la que se dibuja (según el modo).
        var used = em.ref ? em.ref.kind : null;
        if (em.nss != null) o += "<br>" + (used === "curva" ? "<b>premio</b> " : "") + "vs curva NSS " + fmtPct(em.nss) + " → " + fmtPP(em.t - em.nss);
        if (em.instr) o += "<br>" + (used === "instr" ? "<b>premio</b> " : "") + "vs " + em.instr.code + " " + em.instr.src + " " + fmtPct(em.instr.y) + " → " + fmtPP(em.instr.dif);
        if (em.near) o += "<br>vs " + em.near.code + " (dur " + fmtNum(em.near.x) + ") " + fmtPct(em.near.y) + " → " + fmtPP(em.t - em.near.y);
        return o;
      }
      if (!m) return head;
      if (m.mon) head += " · " + m.mon;
      if (kind === "bid" && m.bp != null)
        return head + "<br>bid " + fmtNum(m.bp) + (m.bt != null ? " · TIR " + fmtPct(m.bt) : "");
      if (kind === "off" && m.op != null)
        return head + "<br>offer " + fmtNum(m.op) + (m.ot != null ? " · TIR " + fmtPct(m.ot) : "");
      var out = head, l2 = "";
      if (m.p != null) { l2 = fmtNum(m.p); if (m.src) l2 += " " + m.src; if (m.dt) l2 += " · " + m.dt; }
      else if (m.src) { l2 = m.src; }
      if (l2) out += "<br>" + l2;
      var l3 = [];
      if (m.tir != null) l3.push("TIR " + fmtPct(m.tir));
      if (m.tna != null) l3.push("TNA " + fmtPct(m.tna));
      if (l3.length) out += "<br>" + l3.join(" · ");
      var l4 = [];
      if (m.tem != null) l4.push("TEM " + fmtPct(m.tem));
      if (m.dur != null) l4.push("Dur " + fmtNum(m.dur));
      if (l4.length) out += "<br>" + l4.join(" · ");
      return out;
    }

    function opts() {
      return {
        width: box.clientWidth || 900, height: 460,
        scales: { x: { time: false } },
        axes: [
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: "Duration (años)", labelSize: 30 },
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: yLabel, size: 56,
            values: function (uu, vals) { return vals.map(function (v) { return v + "%"; }); } },
        ],
        series: (function () {
          SCAT = [];
          var base = [
            { label: "Dur", value: function (uu, v) { return fmtNum(v); } },
            scatter("ARS", ORANGE),
            scatter("USD/USB", CYAN),
            scatter("Bid", GREEN, 5),
            scatter("Offer", RED, 5),
            { label: "NSS", stroke: NSSCOL, width: 2, points: { show: false },
              value: function (uu, v) { return fmtPct(v); } },
          ];
          SCAT.push({ si: 1, kind: "ars", ci: -1 }, { si: 2, kind: "usd", ci: -1 },
                    { si: 3, kind: "bid", ci: -1 }, { si: 4, kind: "off", ci: -1 });
          var si = 6;
          for (var ci = 0; ci < cmps.length; ci++) {
            var col = CMP_COLORS[ci % CMP_COLORS.length], lbl = cmps[ci].label || ("Curva " + (ci + 2));
            base.push(scatter(lbl, col, 6));
            SCAT.push({ si: si, kind: "cmp", ci: ci }); si++;
            base.push({ label: lbl + " NSS", stroke: col, width: 1.6, dash: [5, 4],
                        points: { show: false }, value: function (uu, v) { return fmtPct(v); } });
            si++;
          }
          if (emisCodes) {
            // Los puntos NO los dibuja uPlot (points.show=false): el hook draw
            // pinta las ★ y la distancia a la curva. La serie sigue existiendo
            // para leyenda, cursor/tooltip y escala.
            base.push({ label: "Licitación ★", stroke: STAR, paths: function () { return null; },
                        points: { show: false }, value: function (uu, v) { return fmtPct(v); } });
            SCAT.push({ si: si, kind: "emis", ci: -2 }); si++;
          }
          return base;
        })(),
        cursor: { points: { size: 9 }, focus: { prox: 24 } },
        legend: { isolate: true },
        padding: [12, 34, 0, 0],
        hooks: {
          setScale: [function (uu, key) {
            // Un cambio de escala que NO viene de nuestro setData es zoom/pan del usuario.
            if (key === "x" && !selfSet) userZoomed = true;
          }],
          draw: [function (uu) {
            // Etiqueta el código de cada bono sobre su punto — de TODAS las curvas
            // (principal + comparaciones), con el color de su curva y anti-super-
            // posición global (no etiqueta las puntas bid/offer: mismo bono).
            var ctx = uu.ctx; ctx.save();
            ctx.font = "10px system-ui,-apple-system,sans-serif"; ctx.textBaseline = "bottom";
            var X0 = uu.data[0], drawn = [];
            for (var s = 0; s < SCAT.length; s++) {
              var e = SCAT[s];
              if (e.kind === "bid" || e.kind === "off") continue;
              var arr = uu.data[e.si], ser = uu.series[e.si], cds = codesOf(e);
              if (!arr || !cds || !ser || !ser.show) continue;
              ctx.fillStyle = (e.ci < 0) ? MUT : (ser.stroke || MUT);
              for (var i = 0; i < X0.length; i++) {
                var yv = arr[i];
                if (yv == null || !cds[i]) continue;
                var X = uu.valToPos(X0[i], "x", true), Y = uu.valToPos(yv, "y", true), ok = true;
                for (var k = 0; k < drawn.length; k++) {
                  if (Math.abs(drawn[k][0] - X) < 26 && Math.abs(drawn[k][1] - Y) < 11) { ok = false; break; }
                }
                if (!ok) continue;
                drawn.push([X, Y]);
                ctx.fillText(cds[i], X + 5, Y - 3);
              }
            }
            // ★ de las nuevas emisiones + distancia a la curva NSS (línea
            // punteada hasta la curva y "+0,40 pp" / "−0,40 pp" al costado,
            // como el "premio vs secundario" de los research).
            var es = null;
            for (var q = 0; q < SCAT.length; q++) { if (SCAT[q].kind === "emis") { es = SCAT[q]; break; } }
            if (es && emisCodes && uu.series[es.si] && uu.series[es.si].show) {
              var ev = uu.data[es.si];
              for (var j = 0; j < X0.length; j++) {
                if (ev[j] == null || !emisCodes[j]) continue;
                var SX = uu.valToPos(X0[j], "x", true), SY = uu.valToPos(ev[j], "y", true);
                var info = emisInfo[emisCodes[j]], ref = info && info.ref;
                if (ref) {
                  // Punteada hasta la referencia del premio: vertical a la curva
                  // NSS, o diagonal al punto del instrumento que se licita.
                  var isI = ref.kind === "instr";
                  var RX = isI ? uu.valToPos(ref.x, "x", true) : SX;
                  var RY = uu.valToPos(ref.y, "y", true), dif = ref.dif, col = dif >= 0 ? GREEN : "#fb923c";
                  ctx.strokeStyle = col; ctx.lineWidth = 1.2; ctx.setLineDash([3, 3]);
                  ctx.beginPath(); ctx.moveTo(SX, SY); ctx.lineTo(RX, RY); ctx.stroke(); ctx.setLineDash([]);
                  // uPlot deja textAlign="right" tras los ejes: fijarlo para que el
                  // "+0,40 pp" quede a la DERECHA de la ★ (el ticker va arriba).
                  ctx.fillStyle = col; ctx.textBaseline = "middle"; ctx.textAlign = "left";
                  ctx.font = "bold 10.5px system-ui,-apple-system,sans-serif";
                  ctx.fillText(fmtPP(dif) + (isI ? " vs " + ref.code : ""), SX + 11, isI ? SY + 8 : (SY + RY) / 2);
                  ctx.font = "10px system-ui,-apple-system,sans-serif"; ctx.textBaseline = "bottom";
                }
                // estrella de 5 puntas
                var R = 7, r = 3, ang = -Math.PI / 2;
                ctx.beginPath();
                for (var p = 0; p < 10; p++) {
                  var rr = (p % 2 === 0) ? R : r;
                  ctx.lineTo(SX + rr * Math.cos(ang), SY + rr * Math.sin(ang));
                  ang += Math.PI / 5;
                }
                ctx.closePath();
                ctx.fillStyle = STAR; ctx.fill();
                ctx.strokeStyle = "rgba(0,0,0,0.55)"; ctx.lineWidth = 1; ctx.stroke();
              }
            }
            ctx.restore();
          }],
          setCursor: [function (uu) {
            var i = uu.cursor.idx;
            if (i == null) { tip.style.display = "none"; return; }
            // Punto más cercano (en Y) al cursor entre las series con valor en i.
            var cy = uu.cursor.top, cx = uu.cursor.left, best = null, bestD = Infinity;
            var X0c = uu.data[0];
            for (var s = 0; s < SCAT.length; s++) {
              var e = SCAT[s], ser = uu.series[e.si];
              if (!ser || !ser.show) continue;
              // Una ★ (reapertura) cae a una duration casi igual a la del bono,
              // en un x propio a <1 px: el idx del cursor puede resolver al bono.
              // Para las ★ se miran también los índices vecinos (a ≤8 px) y, a
              // igual distancia, gana la ★ (es lo que el usuario tipeó para mirar).
              // Lo mismo, a ≤2 px, para dos BONOS con la misma duration (dos
              // bullets que vencen el mismo día: M30A7 y la LECAP del 30/04):
              // el server les da x contiguas y sin mirar los vecinos sólo uno
              // tenía hover.
              var esEmis = (e.kind === "emis"), idxs = esEmis ? [i - 1, i, i + 1] : [i - 2, i - 1, i, i + 1, i + 2];
              for (var q = 0; q < idxs.length; q++) {
                var ii = idxs[q];
                if (ii < 0 || ii >= X0c.length) continue;
                var yv = uu.data[e.si][ii];
                if (yv == null) continue;
                if (ii !== i && (cx == null || Math.abs(uu.valToPos(X0c[ii], "x") - cx) > (esEmis ? 8 : 2))) continue;
                var dd = (cy == null) ? 0 : Math.abs(uu.valToPos(yv, "y") - cy);
                if (e.kind === "emis") dd = Math.max(0, dd - 8);
                if (dd < bestD) { bestD = dd; best = { e: e, yv: yv, i: ii }; }
              }
            }
            var cds = best && codesOf(best.e), code = cds ? cds[best.i] : null;
            if (!code) { tip.style.display = "none"; return; }
            tip.innerHTML = tipHTML(code, meta[code], best.e.kind);
            tip.style.display = "block";
            // Anti-clip: si el globito se saldría por la derecha/arriba, lo
            // volteamos para que SIEMPRE se vea completo dentro del gráfico.
            var L = uu.valToPos(X0c[best.i], "x"), T = uu.valToPos(best.yv, "y");
            var bw = box.clientWidth, bh = box.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight;
            var left = L + 12; if (left + tw > bw - 4) { left = L - tw - 12; } if (left < 2) { left = 2; }
            var top = T - th - 8; if (top < 2) { top = T + 16; } if (top + th > bh - 2) { top = bh - th - 2; }
            tip.style.left = left + "px"; tip.style.top = top + "px";
          }],
        },
      };
    }

    function clear() {
      // p = el placeholder "Cargando gráfico…" del template (quedaba pegado
      // arriba del chart para siempre).
      Array.prototype.slice.call(box.querySelectorAll(".uplot,.alert,p,.skel")).forEach(function (n) { n.remove(); });
    }

    function render(j, recreate) {
      if (!j || !j.n) {
        if (u) { u.destroy(); u = null; }
        clear();
        var e = document.createElement("div"); e.className = "alert";
        e.textContent = "Sin bonos con TIREA y Duration (¿hay cotización?).";
        box.appendChild(e);
        renderTabla(j);
        return;
      }
      var xs = j.xs.slice();
      var vac = xs.map(function () { return null; });
      var nss = (j.nss && j.nss.length === xs.length) ? j.nss.slice() : vac.slice();
      var scat = [j.ars.slice(), j.usd.slice(), (j.bid || vac).slice(), (j.off || vac).slice()];
      var newCmps = (j.cmps || []).map(function (c) {
        return { label: c.label, codes: (c.codes || []).slice(),
                 vals: (c.vals || vac).slice(),
                 nss: (c.nss && c.nss.length === xs.length) ? c.nss.slice() : vac.slice() };
      });
      var newCodes = (j.codes || []).slice();
      // Nuevas emisiones: insertar sus durations en el eje x (null en los
      // scatters, NSS interpolada para que la línea no se corte) + distancias
      // sobre el payload ORIGINAL (curva sin las inserciones).
      var em = parseEmis();
      var emisVals = null;
      emisCodes = null; emisInfo = {};
      if (em.length) {
        emisVals = vac.slice(); emisCodes = vac.slice();
        em.forEach(function (p) {
          var k = 0;
          while (k < xs.length && xs[k] < p.d) k++;
          if (k < xs.length && xs[k] === p.d && emisCodes[k] == null) {
            emisVals[k] = p.t; emisCodes[k] = p.c;
          } else {
            xs.splice(k, 0, p.d);
            scat.forEach(function (a) { a.splice(k, 0, null); });
            nss.splice(k, 0, interp(j.xs, j.nss, p.d));
            newCmps.forEach(function (c, ci) {
              c.vals.splice(k, 0, null); c.codes.splice(k, 0, null);
              c.nss.splice(k, 0, interp(j.xs, (j.cmps && j.cmps[ci]) ? j.cmps[ci].nss : null, p.d));
            });
            newCodes.splice(k, 0, null);
            emisVals.splice(k, 0, p.t); emisCodes.splice(k, 0, p.c);
          }
          // bono más cercano por duration (con valor en la curva principal)
          var near = null, bd = Infinity;
          for (var i = 0; i < j.xs.length; i++) {
            var y = (j.ars[i] != null) ? j.ars[i] : j.usd[i];
            if (y == null || !j.codes || !j.codes[i]) continue;
            var dd = Math.abs(j.xs[i] - p.d);
            if (dd < bd) { bd = dd; near = { code: j.codes[i], x: j.xs[i], y: y }; }
          }
          // Premio: vs curva NSS (en la duration del corte) y vs el instrumento
          // si ya cotiza (offer, o último sin punta); `ref` = la que se dibuja.
          var nssY = interp(j.xs, j.nss, p.d), ins = findInstr(j, p.c), mode = emisRefMode();
          var pc = (nssY != null) ? { kind: "curva", y: nssY, x: p.d, dif: p.t - nssY } : null;
          var pi = ins ? { kind: "instr", y: ins.y, x: ins.x, dif: p.t - ins.y, code: ins.code, src: ins.src } : null;
          var ref = (mode === "curva") ? pc
                  : (mode === "instr") ? (pi || pc)
                  : (pc && pi) ? (pi.dif <= pc.dif ? pi : pc) : (pi || pc);
          if (near && ins && near.code === ins.code) near = null;   // ya figura como instrumento
          emisInfo[p.c] = { c: p.c, t: p.t, d: p.d, note: p.note, nss: nssY, instr: pi, ref: ref, near: near };
        });
      }
      var data = [xs].concat(scat, [nss]);
      for (var ci = 0; ci < newCmps.length; ci++) data.push(newCmps[ci].vals, newCmps[ci].nss);
      if (emisVals) data.push(emisVals);
      // Firma estructural = labels de las comparaciones + si hay ★. Si cambió el
      // set de series (cantidad/orden/nombre), hay que recrear el chart; si
      // sólo cambian los datos, setData preserva el zoom.
      var newSig = newCmps.map(function (c) { return c.label; }).join("|") + (emisVals ? "|★" : "");
      if (newSig !== sig) { sig = newSig; recreate = true; }
      cmps = newCmps;
      meta = j.meta || {};
      codes = newCodes;
      if (j.ylabel) yLabel = j.ylabel + " (%)";   // TIREA/TEM según la métrica
      if (recreate || !u) {
        if (u) u.destroy();
        clear();
        selfSet = true;                 // la construcción dispara setScale: no es zoom del usuario
        u = new uPlot(opts(), data, box);
        box.uplot = u;                  // instancia a mano (diagnóstico / tests visuales)
        selfSet = false;
        userZoomed = false;             // chart nuevo → arranca siguiendo los datos
        if (window.chartCopyInject) {
          var curEl0 = form.querySelector("[name=curve]");
          window.chartCopyInject(box, "grafico-" + ((curEl0 && curEl0.value) || "curva"));
        }
      } else {
        // Si el usuario hizo zoom, refrescamos los datos SIN re-encuadrar
        // (resetScales=false) para no pisarle la vista.
        selfSet = true;
        u.setData(data, !userZoomed);
        selfSet = false;
      }
      renderTabla(j);                 // el cuadro de abajo sigue al mismo payload
    }

    // ── Tabla de los bonos graficados (cajón abajo de todo) ─────────────────
    // Mismo payload que el chart: nada de requests extra. Colapsada sólo se
    // actualiza el conteo; el HTML se arma al abrir (y en cada refresh mientras
    // esté abierta: ~1-3 ms para 500 filas).
    var tabla = document.getElementById("graf-tabla");
    var tablaBody = document.getElementById("graf-tabla-body");
    var tablaN = document.getElementById("graf-tabla-n");
    var tablaToggle = document.getElementById("graf-tabla-toggle");
    var tablaDirty = false;
    function renderTabla(j) {
      if (!tabla) return;
      var rows = grafTablaRows(j);
      if (tablaN) tablaN.textContent = rows.length ? (rows.length + " bono" + (rows.length > 1 ? "s" : "")) : "";
      if (tablaBody && tablaBody.hidden) { tablaDirty = true; return; }
      tablaDirty = false;
      // Con comparaciones, la columna Curva nombra la principal con el label
      // del selector ("CER (12)" → "CER").
      var conCurva = false;
      if (j && j.cmps && j.cmps.length) {
        var curEl = form.querySelector("[name=curve]");
        var opt = curEl && curEl.selectedOptions && curEl.selectedOptions[0];
        conCurva = (opt ? opt.textContent.replace(/\s*\(\d+\)\s*$/, "").trim() : "") || true;
      }
      tabla.innerHTML = grafTablaHTML(rows, j && j.metric, conCurva);
    }
    function tablaOpen(open) {
      if (!tablaToggle || !tablaBody) return;
      tablaBody.hidden = !open;
      tablaToggle.setAttribute("aria-expanded", open ? "true" : "false");
      var caret = tablaToggle.querySelector(".graf-emis-caret");
      if (caret) caret.textContent = open ? "▾" : "▸";
      try { localStorage.setItem("graf_tabla_open", open ? "1" : "0"); } catch (e) { /* noop */ }
      if (open && tablaDirty && lastJ) renderTabla(lastJ);
    }
    if (tablaToggle && tablaBody) {
      var t0 = "0";
      try { t0 = localStorage.getItem("graf_tabla_open") || "0"; } catch (e) { /* noop */ }
      tablaOpen(t0 === "1");
      tablaToggle.addEventListener("click", function () { tablaOpen(tablaBody.hidden); });
    }

    // Generación por pedido: sólo la respuesta del ÚLTIMO load() se dibuja.
    // Sin esto, dos cambios de filtro seguidos con respuestas que llegaban
    // invertidas dejaban el gráfico de la selección anterior (auditoría E05).
    // Además, UNA petición en vuelo: la anterior se aborta (AbortController)
    // y cada fetch tiene plazo — con red lenta, dos cambios de filtro seguidos
    // acumulaban requests que igual se descartaban al llegar.
    var loadGen = 0, loadCtrl = null, LOAD_TIMEOUT_MS = 20000;
    function load(recreate) {
      var mine = ++loadGen;
      if (loadCtrl) { try { loadCtrl.abort(); } catch (e) { /* noop */ } }
      var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
      loadCtrl = ctrl;
      var tm = ctrl ? setTimeout(function () { try { ctrl.abort(); } catch (e) { /* noop */ } }, LOAD_TIMEOUT_MS) : null;
      fetch("/graficos/data?" + params(), ctrl ? { signal: ctrl.signal } : undefined)
        .then(function (r) { return r.json(); })
        .then(function (j) { if (mine !== loadGen) return; lastJ = j; render(j, recreate); })
        .catch(function () { /* sin red / abortado → mantiene el último chart */ })
        .then(function () { if (tm) clearTimeout(tm); if (loadCtrl === ctrl) loadCtrl = null; });
    }

    // Textarea de emisiones: re-dibuja con el ÚLTIMO payload (sin re-fetch),
    // debounced; persiste en localStorage.
    if (emisBox) {
      try { emisBox.value = localStorage.getItem("graf_emis") || ""; } catch (e) { /* sin storage */ }
      var emisT = null;
      emisBox.addEventListener("input", function () {
        clearTimeout(emisT);
        emisT = setTimeout(function () {
          try { localStorage.setItem("graf_emis", emisBox.value); } catch (e) { /* noop */ }
          if (lastJ) render(lastJ, false);
        }, 300);
      });
      var emisClear = document.getElementById("graf-emis-clear");
      if (emisClear) emisClear.addEventListener("click", function () {
        emisBox.value = "";
        emisBox.dispatchEvent(new Event("input"));
      });
      // Cajón minimizado por default (abajo del gráfico); recuerda el estado.
      // Colapsado o no, los ★ se dibujan igual: sólo se oculta el cuerpo.
      var emisToggle = document.getElementById("graf-emis-toggle");
      var emisBody = document.getElementById("graf-emis-body");
      function emisOpen(open) {
        if (!emisToggle || !emisBody) return;
        emisBody.hidden = !open;
        emisToggle.setAttribute("aria-expanded", open ? "true" : "false");
        var caret = emisToggle.querySelector(".graf-emis-caret");
        if (caret) caret.textContent = open ? "▾" : "▸";
        try { localStorage.setItem("graf_emis_open", open ? "1" : "0"); } catch (e) { /* noop */ }
      }
      if (emisToggle && emisBody) {
        var o0 = "0";
        try { o0 = localStorage.getItem("graf_emis_open") || "0"; } catch (e) { /* noop */ }
        emisOpen(o0 === "1");
        emisToggle.addEventListener("click", function () { emisOpen(emisBody.hidden); });
      }
    }
    // Modo del premio (mínimo / curva / instrumento): persiste y re-dibuja con
    // el último payload, sin request.
    if (emisRefSel) {
      try { var m0 = localStorage.getItem("graf_emis_ref"); if (m0) emisRefSel.value = m0; } catch (e) { /* noop */ }
      emisRefSel.addEventListener("change", function () {
        try { localStorage.setItem("graf_emis_ref", emisRefSel.value); } catch (e) { /* noop */ }
        if (lastJ) render(lastJ, false);
      });
    }

    // Doble-click resetea el zoom (default de uPlot): volvemos a auto-encuadrar.
    box.addEventListener("dblclick", function () { userZoomed = false; });

    // ── Chips de comparación (dropdown #cmp-add → chips removibles) ──────────
    var chipsBox = document.getElementById("cmp-chips");
    var addSel = document.getElementById("cmp-add");
    function renderChips() {
      if (!chipsBox) return;
      chipsBox.innerHTML = "";
      cmpSel.forEach(function (c, i) {
        var chip = document.createElement("span");
        chip.className = "cmp-chip";
        chip.style.borderLeftColor = CMP_COLORS[i % CMP_COLORS.length];
        chip.appendChild(document.createTextNode(c.label + " "));
        var x = document.createElement("b"); x.textContent = "✕";
        x.onclick = function () { cmpSel.splice(i, 1); renderChips(); load(true); };
        chip.appendChild(x);
        chipsBox.appendChild(chip);
      });
      if (addSel) addSel.style.display = (cmpSel.length >= 3) ? "none" : "";
    }
    if (addSel) {
      addSel.addEventListener("change", function () {
        var v = addSel.value;
        var opt = addSel.selectedOptions && addSel.selectedOptions[0];
        var lbl = (opt && opt.getAttribute("data-label")) || v;
        addSel.value = "";
        if (!v || cmpSel.length >= 3 || cmpSel.some(function (c) { return c.key === v; })) return;
        cmpSel.push({ key: v, label: lbl });
        renderChips();
        load(true);
      });
    }
    renderChips();

    // ── Descargar el gráfico como PNG (para pegar en PPT) ───────────────────
    function downloadPNG() {
      if (!u) return;
      var src = u.ctx && u.ctx.canvas;
      if (!src) return;
      var tmp = document.createElement("canvas");
      tmp.width = src.width; tmp.height = src.height;
      var c = tmp.getContext("2d");
      c.fillStyle = cssVar("--bg", "#0b0e13");        // fondo sólido (el canvas es transparente)
      c.fillRect(0, 0, tmp.width, tmp.height);
      c.drawImage(src, 0, 0);
      var curEl = form.querySelector("[name=curve]");
      var a = document.createElement("a");
      a.download = "grafico-" + ((curEl && curEl.value) || "curva") + ".png";
      a.href = tmp.toDataURL("image/png");
      a.click();
    }
    var dl = document.createElement("button");
    dl.type = "button"; dl.className = "graf-dl"; dl.textContent = "⤓ PNG";
    dl.title = "Descargar el gráfico como imagen";
    dl.onclick = downloadPNG;
    box.appendChild(dl);

    load(true);
    form.querySelectorAll("[name]").forEach(function (el) {
      el.addEventListener("change", function () { load(true); });
    });
    // Refresh en vivo siguiendo el motor live (md-update ~1s tras un tick real),
    // no un poll ciego. Throttle a 1×/2s, fallback 30s y pausa con la pestaña
    // oculta. Antes era un setInterval fijo de 8s que redibujaba aunque no
    // hubiera ticks ni la pestaña estuviera visible (~7,5 req/min por cliente).
    var lastLive = 0;
    function liveRefresh() {
      if (document.hidden || !document.getElementById("grafico-uplot")) return;
      var now = Date.now();
      if (now - lastLive < 2000) return;           // throttle
      lastLive = now;
      load(false);
    }
    document.body.addEventListener("md-update", liveRefresh);
    setInterval(liveRefresh, 30000);               // fallback (datos que no pasan por el store)
    window.addEventListener("resize", function () {
      if (u) u.setSize({ width: box.clientWidth || 900, height: 460 });
    });
  }

  function clearBox(box) {
    // p.muted = el placeholder "Cargando gráfico…" del template: quedaba
    // pegado arriba del chart de Históricos para siempre.
    Array.prototype.slice.call(box.querySelectorAll(".uplot,.alert,p.muted,.skel")).forEach(function (n) { n.remove(); });
  }
  function palette() {
    return ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
            "#e67e22", "#16a085", "#fd79a8", "#00b894", "#0984e3", "#fdcb6e",
            "#6c5ce7", "#d63031", "#00cec9", "#a78bfa", "#e84393", "#55efc4"];
  }
  function paramsOf(ctrls) {
    var p = {};
    ctrls.querySelectorAll("[name]").forEach(function (el) {
      p[el.name] = (el.type === "checkbox") ? (el.checked ? "true" : "false") : el.value;
    });
    return new URLSearchParams(p).toString();
  }

  // ── Históricos · serie macro (línea o barras, eje temporal) ───────────────
  // + "Ver datos": la tabla numérica se arma recién al abrir el <details>, con
  //   el JSON que ya está en memoria (cero requests, cero costo al cargar la
  //   página); si llegan datos nuevos con el panel abierto, se re-arma.
  function initHistMacro() {
    var box = document.getElementById("hist-macro-uplot");
    var ctrls = document.getElementById("hm-ctrls");
    if (!box || !ctrls || typeof uPlot === "undefined") return;
    var MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333");
    var ACC = cssVar("--accent", "#e0843c");
    var tipoSel = document.getElementById("hm-tipo");          // sin `name`: no viaja al server
    var datos = document.getElementById("hm-datos");
    var u = null, lastJ = null;
    box.style.position = "relative";

    function fmtDia(v) { return utcDia(v); }

    function draw() {
      var j = lastJ;
      clearBox(box);
      if (!j || !j.n) {
        if (u) { u.destroy(); u = null; }
        var e = document.createElement("div"); e.className = "alert"; e.textContent = "Sin datos para esta serie.";
        box.appendChild(e); return;
      }
      var barras = !!(tipoSel && tipoSel.value === "barras");
      var serie = { label: j.label, stroke: ACC, width: 1.6, points: { show: false },
                    value: function (uu, v) { return fmtNum(v); } };
      if (barras) {
        // Barras: relleno del acento, ancho relativo al paso; sin línea.
        serie.fill = ACC; serie.width = 0;
        serie.paths = uPlot.paths.bars({ size: [0.7, 100] });
      }
      // Serie proyectada (13/11): `corte` = última observación. El tramo
      // observado va lleno y el proyectado PUNTEADO, mismo color; el punto
      // del corte está en los dos para que el trazo no se corte.
      var series = [{ value: function (uu, v) { return v == null ? "" : fmtDia(v); } }];
      var data = [j.x];
      if (j.corte != null && !barras) {
        var obs = [], proy = [];
        for (var i = 0; i < j.x.length; i++) {
          obs.push(j.x[i] <= j.corte ? j.y[i] : null);
          proy.push(j.x[i] >= j.corte ? j.y[i] : null);
        }
        var sObs = Object.assign({}, serie, { label: j.label + " · observado" });
        var sProy = Object.assign({}, serie, { label: "proyectado", dash: [6, 4] });
        series.push(sObs, sProy); data.push(obs, proy);
      } else {
        series.push(serie); data.push(j.y);
      }
      var opts = {
        width: box.clientWidth || 900, height: 420,
        tzDate: utcTz,
        scales: { x: { time: true } },
        axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, values: ejeFechas },
               { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: 60 }],
        series: series,
        cursor: { focus: { prox: 24 } },
      };
      if (u) u.destroy();
      u = new uPlot(opts, data, box);
      if (window.chartCopyInject) window.chartCopyInject(box, "macro-" + (j.label || "serie"));
    }

    // Tabla numérica (más reciente primero): fecha · valor · Δ · Δ% — mismo
    // formato es-AR que las tablas HP; CSV con el botón genérico [data-csv-of].
    function renderDatos() {
      if (!datos || !datos.open) return;
      var body = datos.querySelector(".hm-datos-body");
      if (!body) return;
      var j = lastJ;
      if (!j || !j.n) { body.innerHTML = '<p class="muted" style="padding:6px">Sin datos.</p>'; return; }
      var n = j.x.length, rows = [], conTramo = (j.corte != null);
      for (var i = n - 1; i >= 0; i--) {
        var v = j.y[i], p = (i > 0) ? j.y[i - 1] : null;
        var d = (v != null && p != null) ? v - p : null;
        var pc = (v != null && p) ? (v / p - 1) * 100 : null;
        var cls = d == null ? "" : (d > 0 ? "var-up" : (d < 0 ? "var-down" : "px-flat"));
        rows.push("<tr><td style=\"text-align:left;color:var(--accent);font-weight:600\">" + fmtDia(j.x[i]) + "</td>" +
                  "<td style=\"font-weight:600\">" + fmtNum(v) + "</td>" +
                  "<td class=\"" + cls + "\">" + (d == null ? "—" : (d > 0 ? "▲ " : (d < 0 ? "▼ " : "■ ")) + fmtNum(d)) + "</td>" +
                  "<td class=\"" + cls + "\">" + (pc == null ? "—" : fmtPct(pc)) + "</td>" +
                  (conTramo ? "<td class=\"muted\">" + (j.x[i] > j.corte ? "proyectado" : "observado") + "</td>" : "") + "</tr>");
      }
      body.innerHTML =
        '<div class="card-title"><span>🗒 ' + (j.label || "Serie") + ' · datos</span>' +
        '<span class="card-title-aux"><button type="button" class="lnk" data-csv-of="#hm-datos-tbl" title="Descargar la tabla (CSV es-AR)">⤓ CSV</button> · ' + n + ' filas · más reciente primero</span></div>' +
        '<div class="card-body table-scroll" style="max-height:420px;overflow:auto"><table class="cashflows curve-table mercado-table" data-sortable id="hm-datos-tbl">' +
        '<thead><tr><th style="text-align:left" data-sort>Fecha</th><th data-sort>Valor</th><th data-sort>Δ</th><th data-sort>Δ%</th>' + (conTramo ? '<th data-sort>Tramo</th>' : '') + '</tr></thead>' +
        '<tbody>' + rows.join("") + '</tbody></table></div>';
      if (window.htmx) window.htmx.process(body);
      document.body.dispatchEvent(new CustomEvent("tables:injected", { detail: { root: body } }));
    }

    // Generación por pedido: una respuesta lenta de la selección ANTERIOR
    // (CER) que llega después de la vigente (TAMAR) no pisa el gráfico.
    var hmGen = 0;
    function load() {
      var mine = ++hmGen;
      // El link ⤓ CSV sigue a los controles (misma serie y rango del gráfico).
      // `typeof document`: live_engine_harness corre este load() en un VM sin DOM.
      var csvLink = (typeof document !== "undefined") ? document.getElementById("hm-csv") : null;
      if (csvLink) csvLink.href = "/historicos/macro.csv?" + paramsOf(ctrls);
      fetch("/historicos/data?" + paramsOf(ctrls)).then(function (r) { return r.json(); }).then(function (j) {
        if (mine !== hmGen) return;
        lastJ = j;
        draw();
        renderDatos();
      }).catch(function () {});
    }
    load();
    ctrls.querySelectorAll("[name]").forEach(function (el) { el.addEventListener("change", load); });
    if (tipoSel) tipoSel.addEventListener("change", draw);            // sólo re-dibuja: sin request
    if (datos) datos.addEventListener("toggle", renderDatos);         // lazy: se arma al abrir
    window.addEventListener("resize", function () { if (u) u.setSize({ width: box.clientWidth || 900, height: 420 }); });
  }

  // ── Históricos · tasas por curva (multilínea + bandas) ────────────────────
  function initHistCurva() {
    var box = document.getElementById("hist-curva-uplot");
    var ctrls = document.getElementById("hc-ctrls");
    if (!box || !ctrls || typeof uPlot === "undefined") return;
    var PAL = palette(), MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333");
    box.style.position = "relative";
    var hcGen = 0;                       // sólo se dibuja la respuesta del último pedido
    function draw() {
      var mine = ++hcGen;
      fetch("/historicos/curva/data?" + paramsOf(ctrls)).then(function (r) { return r.json(); }).then(function (j) {
        if (mine !== hcGen) return;
        clearBox(box);
        if (!j || !j.loaded || !j.series || !j.series.length) {
          if (box._u) { box._u.destroy(); box._u = null; }
          var e = document.createElement("div"); e.className = "alert";
          e.textContent = "Sin datos históricos para esta curva en el rango/filtro elegido.";
          box.appendChild(e); return;
        }
        var data = [j.x].concat(j.series.map(function (s) { return s.y; }));
        var series = [{ label: "Fecha", value: function (uu, v) { return v == null ? "" : utcDia(v); } }]
          .concat(j.series.map(function (s, i) {
            return { label: s.code, stroke: PAL[i % PAL.length], width: 1.4, points: { show: false },
                     value: function (uu, v) { return fmtPct(v); } };
          }));
        var bands = j.bands;
        var opts = {
          width: box.clientWidth || 900, height: 520,
          tzDate: utcTz,
          scales: { x: { time: true } },
          axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, values: ejeFechas },
                 { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: 56,
                   values: function (uu, vals) { return vals.map(function (v) { return v + "%"; }); } }],
          series: series,
          cursor: { focus: { prox: 16 } },
          legend: { isolate: true },
          padding: [12, 64, 0, 0],
          hooks: { draw: [function (u) {
            var ctx = u.ctx; ctx.save();
            // bandas prom/mín/máx
            if (bands) {
              ["mean", "min", "max"].forEach(function (k) {
                if (bands[k] == null) return;
                var y = u.valToPos(bands[k], "y", true);
                ctx.strokeStyle = MUT; ctx.globalAlpha = 0.8;
                ctx.lineWidth = (k === "mean") ? 1.3 : 0.8;
                ctx.setLineDash(k === "mean" ? [] : [4, 3]);
                ctx.beginPath(); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke();
              });
              ctx.setLineDash([]); ctx.globalAlpha = 1;
            }
            ctx.restore();
            // código de cada bono al final de su línea (anti-superposición vertical)
            etiquetasFinales(u, function (s) { return s.label; });
          }] },
        };
        if (box._u) box._u.destroy();
        box._u = new uPlot(opts, data, box);
        if (window.chartCopyInject) window.chartCopyInject(box, "historico-" + (j.curve_label || "curva"));
      }).catch(function () {});
    }
    if (!ctrls.dataset.bound) {
      ctrls.dataset.bound = "1";
      ctrls.querySelectorAll("[name]").forEach(function (el) { el.addEventListener("change", draw); });
    }
    draw();
  }

  // ── Históricos · curva por fecha (SVG del server + interacción sutil) ─────
  // El scatter viene renderizado del server (SVG con data-* por punto). Acá,
  // sin ningún request: hover sobre un bono = línea punteada tenue uniendo
  // sus fotos en cada fecha + texto discreto con cuánto amplió/comprimió y
  // cuánto movió el precio (primera → última fecha); leyenda con apagar/
  // prender por bono (recordado por curva) y × para excluirlo del fit (viaja
  // en "Excluir bonos" y re-arma la foto); etiquetas de la última fecha
  // prendibles. Todo vanilla, O(puntos) por hover.
  // "Quitar el tramo" / "Quitar exclusiones" (Curva por fecha): vacía esos
  // campos del form y re-pide el partial. Va en window porque el alert de
  // "sin puntos" se renderiza sin el wrap del gráfico (no pasa por initHistFechas).
  window.hcQuitar = function (el, campos) {
    var f = document.getElementById("hc-fechas-form");
    if (!f) return;
    (campos || []).forEach(function (n) { var i = f.querySelector("[name=" + n + "]"); if (i) i.value = ""; });
    if (window.htmx) window.htmx.trigger(f, "submit");
  };

  function initHistFechas() {
    var wrap = document.querySelector("#hist-fechas .hc-wrap");
    if (!wrap || wrap._hcInit) return;
    wrap._hcInit = true;
    var svg = wrap.querySelector("svg.hc-svg");
    var hover = svg ? svg.querySelector(".hc-hover") : null;
    if (!svg || !hover) return;
    var curve = wrap.getAttribute("data-curve") || "";
    var NS = "http://www.w3.org/2000/svg";
    var x1 = parseFloat(svg.getAttribute("data-x1")) || 900, y0 = parseFloat(svg.getAttribute("data-y0")) || 0;
    var metric = svg.getAttribute("data-metric") || "";

    function num(s) { var v = parseFloat(s); return isNaN(v) ? null : v; }
    function fmt(v, d) { return (v == null) ? "" : v.toFixed(d).replace(".", ","); }
    function signed(v, d) { return (v > 0 ? "+" : "") + fmt(v, d); }
    function dm(iso) { return iso && iso.length >= 10 ? iso.slice(8, 10) + "/" + iso.slice(5, 7) : iso; }

    // Índice por bono: sus puntos en orden cronológico.
    var byCode = {};
    Array.prototype.forEach.call(svg.querySelectorAll("circle.hc-pt"), function (el) {
      var c = el.getAttribute("data-code");
      if (!c) return;
      (byCode[c] = byCode[c] || []).push({
        el: el, fecha: el.getAttribute("data-fecha") || "", v: num(el.getAttribute("data-v")),
        dur: num(el.getAttribute("data-dur")), px: num(el.getAttribute("data-px")),
        x: num(el.getAttribute("cx")), y: num(el.getAttribute("cy")),
      });
    });
    Object.keys(byCode).forEach(function (c) { byCode[c].sort(function (a, b) { return a.fecha < b.fecha ? -1 : (a.fecha > b.fecha ? 1 : 0); }); });

    // Panel Δ bps (barras, debajo del scatter): hover en una barra = el mismo
    // hover del scatter; el hover del scatter resalta su barra; apagar un bono
    // en la leyenda también la atenúa. Puro agregado: el hover de los puntos
    // (línea punteada + Δ) no cambia.
    var delta = wrap.querySelector("svg.hc-delta");
    function deltaGroup(code) {
      return delta ? delta.querySelector('.hc-dgrp[data-code="' + code.replace(/"/g, "") + '"]') : null;
    }
    function clearHover() {
      while (hover.firstChild) hover.removeChild(hover.firstChild);
      svg.classList.remove("hc-dim");
      Array.prototype.forEach.call(svg.querySelectorAll(".hc-on"), function (n) { n.classList.remove("hc-on"); });
      if (delta) {
        delta.classList.remove("hc-dim");
        Array.prototype.forEach.call(delta.querySelectorAll(".hc-on"), function (n) { n.classList.remove("hc-on"); });
      }
    }
    function el(tag, attrs, text) {
      var n = document.createElementNS(NS, tag);
      Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
      if (text != null) n.textContent = text;
      return n;
    }
    function showHover(code, at) {
      clearHover();
      var pts = byCode[code];
      if (!pts || !pts.length) return;
      svg.classList.add("hc-dim");
      pts.forEach(function (p) { p.el.classList.add("hc-on"); });
      var dg = deltaGroup(code);
      if (dg) { delta.classList.add("hc-dim"); dg.classList.add("hc-on"); }
      Array.prototype.forEach.call(svg.querySelectorAll('.hc-lbl[data-code="' + code.replace(/"/g, "") + '"]'), function (n) { n.classList.add("hc-on"); });
      if (pts.length > 1) {
        hover.appendChild(el("polyline", {
          points: pts.map(function (p) { return p.x + "," + p.y; }).join(" "),
          fill: "none", stroke: "var(--text-muted)", "stroke-width": "1", "stroke-dasharray": "2 3", opacity: "0.55",
        }));
      }
      var a = pts[0], b = pts[pts.length - 1], lines;
      if (pts.length > 1 && a.v != null && b.v != null) {
        var dbps = (b.v - a.v) * 100;                            // métrica en % → bps
        var dir = dbps > 0.5 ? "amplió" : (dbps < -0.5 ? "comprimió" : "sin cambio");
        var l2 = dir + " " + fmt(Math.abs(dbps), 0) + " bps";
        if (a.px != null && b.px != null && a.px > 0) l2 += " · px " + signed((b.px / a.px - 1) * 100, 1) + " %";
        lines = [code + " · " + dm(a.fecha) + " → " + dm(b.fecha), l2];
      } else {
        lines = [code + " · " + dm(b.fecha), "dur " + fmt(b.dur, 2) + " · " + metric + " " + fmt(b.v, 2) + " %"];
      }
      var p = at || b, left = p.x + 9, anchor = "start";
      if (p.x > x1 * 0.78) { left = p.x - 9; anchor = "end"; }
      var top = Math.max(y0 + 12, p.y - 14);
      var t = el("text", { x: left, y: top, "text-anchor": anchor, "font-size": "10", fill: "var(--text-muted)", opacity: "0.95", "class": "hc-tip" });
      t.appendChild(el("tspan", { x: left, dy: "0" }, lines[0]));
      t.appendChild(el("tspan", { x: left, dy: "12" }, lines[1]));
      hover.appendChild(t);
    }
    svg.addEventListener("mouseover", function (e) {
      var n = e.target;
      if (!n || !n.getAttribute) return;
      var code = n.getAttribute("data-code");
      if (!code || !(n.classList.contains("hc-pt") || n.classList.contains("hc-lbl"))) return;
      var at = n.classList.contains("hc-pt") ? { x: num(n.getAttribute("cx")), y: num(n.getAttribute("cy")) } : null;
      showHover(code, at);
    });
    svg.addEventListener("mouseleave", clearHover);
    if (delta) {
      delta.addEventListener("mouseover", function (e) {
        var g = e.target && e.target.closest ? e.target.closest(".hc-dgrp") : null;
        var code = g ? g.getAttribute("data-code") : null;
        if (code && byCode[code]) showHover(code, null);
      });
      delta.addEventListener("mouseleave", clearHover);
    }

    // Leyenda: apagar/prender (client-side, recordado por curva) y excluir del fit.
    var storeKey = "hc_off:" + curve, off = {};
    try { (JSON.parse(localStorage.getItem(storeKey) || "[]") || []).forEach(function (c) { off[c] = 1; }); } catch (e) { /* noop */ }
    function applyOff() {
      Object.keys(byCode).forEach(function (c) {
        var on = !off[c];
        byCode[c].forEach(function (p) { p.el.classList.toggle("hc-off", !on); });
        Array.prototype.forEach.call(svg.querySelectorAll('.hc-lbl[data-code="' + c.replace(/"/g, "") + '"]'), function (n) { n.classList.toggle("hc-off", !on); });
        var chip = wrap.querySelector('.hc-chip[data-code="' + c.replace(/"/g, "") + '"]');
        if (chip) chip.classList.toggle("hc-chip-off", !on);
        var dg = deltaGroup(c);
        if (dg) dg.classList.toggle("hc-off", !on);
      });
      try { localStorage.setItem(storeKey, JSON.stringify(Object.keys(off).filter(function (c) { return byCode[c]; }))); } catch (e) { /* noop */ }
    }
    applyOff();
    var form = document.getElementById("hc-fechas-form"), excl = document.getElementById("hc-exclude");
    function submitWith(value) {
      if (!excl || !form) return;
      excl.value = value.trim();
      if (window.htmx) window.htmx.trigger(form, "submit");
    }
    wrap.addEventListener("click", function (e) {
      var x = e.target.closest ? e.target.closest(".hc-excl") : null;
      if (x) {
        var code = x.parentNode.getAttribute("data-code");
        var cur = (excl ? excl.value : "").split(/[\s,;]+/).filter(Boolean);
        if (cur.indexOf(code) < 0) cur.push(code);
        submitWith(cur.join(" "));
        return;
      }
      var r = e.target.closest ? e.target.closest(".hc-restore") : null;
      if (r) {
        var back = r.getAttribute("data-code");
        submitWith((excl ? excl.value : "").split(/[\s,;]+/).filter(function (c) { return c && c !== back; }).join(" "));
        return;
      }
      var chip = e.target.closest ? e.target.closest(".hc-chip") : null;
      if (chip) {
        var c = chip.getAttribute("data-code");
        if (off[c]) delete off[c]; else off[c] = 1;
        applyOff();
        clearHover();
      }
    });
    wrap.addEventListener("mouseover", function (e) {
      var chip = e.target.closest ? e.target.closest(".hc-chip") : null;
      if (chip && !e.target.classList.contains("hc-excl")) showHover(chip.getAttribute("data-code"), null);
    });
    wrap.querySelector(".hc-legend").addEventListener("mouseleave", clearHover);

    // Etiquetas de la última fecha: prendidas por default, recordado.
    var tog = wrap.querySelector(".hc-labels-toggle");
    function applyLabels(on) { svg.classList.toggle("hc-nolabels", !on); try { localStorage.setItem("hc_labels", on ? "1" : "0"); } catch (e) { /* noop */ } }
    if (tog) {
      var l0 = "1";
      try { l0 = localStorage.getItem("hc_labels") || "1"; } catch (e) { /* noop */ }
      tog.checked = (l0 !== "0");
      applyLabels(tog.checked);
      tog.addEventListener("change", function () { applyLabels(tog.checked); });
    }
    // Proyectados (j): el checkbox del título mueve el selector Tipo del form
    // (Todos ↔ Base) y re-pide la foto — el server saca los 'j' de los puntos,
    // del fit y del panel Δ. Sin estado aparte: el form es la verdad.
    var ptog = wrap.querySelector(".hc-proy-toggle");
    if (ptog && form) {
      ptog.addEventListener("change", function () {
        var sel = form.querySelector("select[name=proy]");
        if (!sel) return;
        sel.value = ptog.checked ? "todos" : "base";
        if (window.htmx) window.htmx.trigger(form, "submit");
      });
    }
  }

  // ── Históricos · COMP (varios activos: base 100 / variación % / nivel) ────
  // El cuerpo del partial trae el JSON embebido (#hist-comp-data): cero
  // requests extra, acá sólo se dibuja. Cada activo con su color (el mismo
  // que el punto de la tabla, viene en el payload), huecos unidos (spanGaps),
  // línea de referencia en 100 / 0, ticker al final de cada línea.
  var COMP_H = 440;
  function initHistComp() {
    var box = document.getElementById("hist-comp-uplot");
    var dataEl = document.getElementById("hist-comp-data");
    if (!box || !dataEl || typeof uPlot === "undefined") return;
    var j = null;
    try { j = JSON.parse(dataEl.textContent || "null"); } catch (e) { j = null; }
    var MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333");
    box.style.position = "relative";
    clearBox(box);
    if (box._u) { box._u.destroy(); box._u = null; }
    if (!j || !j.ok || !j.series || !j.series.length) {
      var e = document.createElement("div"); e.className = "alert"; e.textContent = "Sin datos para comparar.";
      box.appendChild(e); return;
    }
    var esTir = j.campo === "tir", modo = j.modo;
    var enPct = (modo === "pct" || esTir);
    function fmtY(v) {
      if (v == null) return "";
      if (modo === "pct") return (v > 0 ? "+" : "") + fmtPct(v);
      return enPct ? fmtPct(v) : fmtNum(v);
    }
    var ref = (modo === "base") ? 100 : (modo === "pct" ? 0 : null);
    var data = [j.x].concat(j.series.map(function (s) { return s.y; }));
    var series = [{ label: "Fecha", value: function (uu, v) { return v == null ? "" : utcDia(v); } }]
      .concat(j.series.map(function (s) {
        return { label: s.ticker, stroke: s.color, width: 1.6, points: { show: false }, spanGaps: true,
                 value: function (uu, v) { return fmtY(v); } };
      }));
    var opts = {
      width: box.clientWidth || 900, height: COMP_H,
      tzDate: utcTz,
      scales: { x: { time: true } },
      axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, values: ejeFechas },
             { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: 64,
               values: function (uu, vals) { return vals.map(function (v) { return enPct ? fmtPct(v) : fmtNum(v); }); } }],
      series: series,
      cursor: { focus: { prox: 16 } },
      legend: { isolate: true },
      // padding derecho: lugar para "TICKER valor" al final de cada línea
      padding: [12, 96, 0, 0],
      hooks: { draw: [function (u) {
        var ctx = u.ctx; ctx.save();
        if (ref != null) {
          var yr = u.valToPos(ref, "y", true);
          if (yr >= u.bbox.top && yr <= u.bbox.top + u.bbox.height) {
            ctx.strokeStyle = MUT; ctx.globalAlpha = 0.7; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
            ctx.beginPath(); ctx.moveTo(u.bbox.left, yr); ctx.lineTo(u.bbox.left + u.bbox.width, yr); ctx.stroke();
            ctx.setLineDash([]); ctx.globalAlpha = 1;
          }
        }
        ctx.restore();
        etiquetasFinales(u, function (s, v) { return s.label + " " + fmtY(v); });
      }] },
    };
    box._u = new uPlot(opts, data, box);
    if (window.chartCopyInject) window.chartCopyInject(box, "comp-" + j.series.map(function (s) { return s.ticker; }).join("-"));
  }
  // Un solo listener: redimensiona el COMP vigente (el cuerpo se reemplaza en
  // cada consulta; un listener por instancia acumularía gráficos muertos).
  window.addEventListener("resize", function () {
    var b = document.getElementById("hist-comp-uplot");
    if (b && b._u) b._u.setSize({ width: b.clientWidth || 900, height: COMP_H });
  });

  // ── Proyecciones (13/11): CER / A3500 / inflación mensual, vigente vs borrador ──
  // Cada [data-proy-chart] trae su JSON (x epoch, y, corte, barras, y ref_x /
  // ref_y = la vigente cuando se previsualiza). Observado lleno, proyectado
  // punteado, referencia en gris. Se redibuja tras cada swap de #proy-preview.
  function initProyecciones() {
    var boxes = document.querySelectorAll("[data-proy-chart]");
    if (!boxes.length || typeof uPlot === "undefined") return;
    var MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333"), ACC = cssVar("--accent", "#e0843c");
    boxes.forEach(function (box) {
      var j;
      try { j = JSON.parse(box.getAttribute("data-proy-chart") || "{}"); } catch (e) { return; }
      if (box.__u) { box.__u.destroy(); box.__u = null; }
      box.innerHTML = "";
      if (!j.x || !j.x.length) { box.innerHTML = '<p class="muted" style="font-size:12px">' + (j.label || "") + ': sin datos.</p>'; return; }
      var series = [{ value: function (uu, v) { return v == null ? "" : utcDia(v); } }], data = [j.x];
      var fmt = function (uu, v) { return fmtNum(v); };
      if (j.barras) {
        series.push({ label: j.label, stroke: ACC, fill: ACC, width: 0, paths: uPlot.paths.bars({ size: [0.6, 100] }), value: fmt });
        data.push(j.y);
      } else {
        var obs = [], proy = [];
        for (var i = 0; i < j.x.length; i++) {
          obs.push(j.corte != null && j.x[i] <= j.corte ? j.y[i] : null);
          proy.push(j.corte == null || j.x[i] >= j.corte ? j.y[i] : null);
        }
        series.push({ label: j.label + " observado", stroke: ACC, width: 1.6, points: { show: false }, value: fmt },
                    { label: "proyectado", stroke: ACC, width: 1.6, dash: [6, 4], points: { show: false }, value: fmt });
        data.push(obs, proy);
      }
      if (j.ref_x && j.ref_x.length) {
        // La referencia (vigente) puede tener otras x: se alinea por unión del eje.
        var xs = j.x.slice(), extra = j.ref_x.filter(function (x) { return j.x.indexOf(x) < 0; });
        if (extra.length) {
          xs = xs.concat(extra).sort(function (a, b) { return a - b; });
          data = data.map(function (col, ci) {
            if (ci === 0) return xs;
            var m = {}; j.x.forEach(function (x, k) { m[x] = col[k]; });
            return xs.map(function (x) { return (x in m) ? m[x] : null; });
          });
        }
        var rm = {}; j.ref_x.forEach(function (x, k) { rm[x] = j.ref_y[k]; });
        data.push(xs.map(function (x) { return (x in rm) ? rm[x] : null; }));
        series.push({ label: "vigente", stroke: MUT, width: 1.2, dash: j.barras ? undefined : [2, 3],
                      points: { show: false }, value: fmt,
                      paths: j.barras ? uPlot.paths.bars({ size: [0.3, 100] }) : undefined, fill: j.barras ? MUT : undefined });
      }
      box.__u = new uPlot({
        width: Math.max(box.clientWidth || 300, 260), height: 220, tzDate: utcTz,
        scales: { x: { time: true } },
        axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, values: ejeFechas },
               { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: 60 }],
        series: series, cursor: { focus: { prox: 24 } }, legend: { show: true },
      }, data, box);
      if (window.chartCopyInject) window.chartCopyInject(box, "proy-" + (j.serie || "serie"));
    });
  }

  // ── Fondos (26/11): gráficos del panel de un fondo ──────────────────────
  // Cada [data-fondos-chart] trae su JSON en un <script> hijo: {x: [epoch], series: [{label, y,
  // color: acc | mut | red | signo, dash, area, bars, scale: "y2", hum}],
  // ref: línea de referencia (100 / 0), dec, suf, hum}. Se redibuja tras cada
  // swap de #fondos-detalle; un chart por caja, se destruye el anterior.
  function initFondos() {
    var boxes = document.querySelectorAll("[data-fondos-chart]");
    if (!boxes.length || typeof uPlot === "undefined") return;
    var MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333"), ACC = cssVar("--accent", "#e0843c"),
        RED = cssVar("--red", "#ef4444"), GRN = cssVar("--green", "#22c55e");
    function hum(v) {
      if (v == null) return "";
      var a = Math.abs(v), d = [[1e12, "B"], [1e9, "MM"], [1e6, "M"], [1e3, "k"]];
      for (var i = 0; i < d.length; i++) if (a >= d[i][0]) return fmtNum(v / d[i][0]).replace(/,(\d)\d*$/, ",$1") + d[i][1];
      return fmtNum(v);
    }
    function rgba(hex, a) {
      var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec((hex || "").trim());
      return m ? "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + "," + a + ")" : hex;
    }
    boxes.forEach(function (box) {
      // El JSON viene en un <script type="application/json"> adentro de la caja
      // (se lee una vez: dibujar la vacía).
      var j = box.__j, tag = box.querySelector('script[type="application/json"]');
      if (tag) { try { j = JSON.parse(tag.textContent || "{}"); } catch (e) { j = null; } box.__j = j; }
      if (!j) return;
      if (box.__u) { box.__u.destroy(); box.__u = null; }
      box.innerHTML = "";
      if (!j.x || j.x.length < 2 || !j.series || !j.series.length) {
        box.innerHTML = '<p class="muted" style="font-size:12px;padding:8px 0">Sin datos suficientes en la ventana.</p>'; return;
      }
      var dec = j.dec == null ? 2 : j.dec, suf = j.suf || "";
      function fv(v, h) { return v == null ? "" : (h ? hum(v) : (v.toFixed(dec).replace(".", ",") + suf)); }
      // p0..p5: paleta para varias series (contribución por grupo); se lee bien en los tres temas
      var colores = { acc: ACC, mut: MUT, red: RED, p0: ACC, p1: "#38bdf8", p2: "#a78bfa", p3: GRN, p4: "#f472b6", p5: "#facc15" };
      var series = [{ label: "Fecha", value: function (uu, v) { return v == null ? "" : utcDia(v); } }], data = [j.x], hayY2 = false;
      j.series.forEach(function (s) {
        var col = colores[s.color] || ACC, o = { label: s.label, stroke: col, width: 1.6, points: { show: false }, spanGaps: true,
                                                  value: (function (h) { return function (uu, v) { return fv(v, h); }; })(!!s.hum) };
        if (s.dash) o.dash = [5, 4];
        if (s.area) o.fill = rgba(col, 0.14);
        if (s.scale) { o.scale = s.scale; hayY2 = true; }
        if (s.bars) {
          o.width = 0; o.paths = uPlot.paths.bars({ size: [0.7, 60] });
          if (s.color === "signo") {
            // barras verdes (suscripción neta) / rojas (rescate neto)
            o.stroke = GRN; o.fill = rgba(GRN, 0.55);
            var ys = s.y;
            o.paths = uPlot.paths.bars({ size: [0.7, 60], disp: { fill: { unit: 3, values: function () {
              return ys.map(function (v) { return v != null && v < 0 ? rgba(RED, 0.6) : rgba(GRN, 0.55); }); } },
              stroke: { unit: 3, values: function () { return ys.map(function (v) { return v != null && v < 0 ? RED : GRN; }); } } } });
          } else o.fill = rgba(col, 0.5);
        }
        series.push(o); data.push(s.y);
      });
      var ejeY = { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: j.hum ? 62 : (suf.length > 1 ? 70 : 56),
                   values: function (uu, vals) { return vals.map(function (v) { return j.hum ? hum(v) : (fmtNum(v).replace(/,00$/, "") + suf); }); } };
      var axes = [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, values: ejeFechas }, ejeY];
      var scales = { x: { time: true } };
      if (hayY2) {
        scales.y2 = { auto: true };
        axes.push({ scale: "y2", side: 1, stroke: MUT, grid: { show: false }, ticks: { stroke: BORD }, size: 62,
                    values: function (uu, vals) { return vals.map(hum); } });
      }
      var ref = j.ref;
      box.__u = new uPlot({
        width: Math.max(box.clientWidth || 320, 280), height: 230, tzDate: utcTz,
        scales: scales, axes: axes, series: series, cursor: { focus: { prox: 24 } }, legend: { show: true },
        hooks: { draw: [function (u) {
          if (ref == null) return;
          var yr = u.valToPos(ref, "y", true);
          if (!(yr >= u.bbox.top && yr <= u.bbox.top + u.bbox.height)) return;
          var ctx = u.ctx; ctx.save();
          ctx.strokeStyle = MUT; ctx.globalAlpha = 0.7; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(u.bbox.left, yr); ctx.lineTo(u.bbox.left + u.bbox.width, yr); ctx.stroke();
          ctx.restore();
        }] },
      }, data, box);
      if (window.chartCopyInject) window.chartCopyInject(box, "fondo-" + (j.nombre || "serie"));
    });
  }
  window.addEventListener("resize", function () {
    document.querySelectorAll("[data-fondos-chart]").forEach(function (b) {
      if (b.__u) b.__u.setSize({ width: Math.max(b.clientWidth || 320, 280), height: 230 });
    });
  });

  function boot() { initGraficos(); initHistMacro(); initHistFechas(); initHistComp(); initProyecciones(); initFondos(); }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
  // Las pestañas "Tasas por curva" / "Curva por fecha" / "Comparar" se cargan
  // lazy (htmx); al insertarse, init. El form del COMP swapea sólo el cuerpo.
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "hist-curva") initHistCurva();
    if (e.target && e.target.id === "hist-fechas") initHistFechas();
    if (e.target && (e.target.id === "hist-comp" || e.target.id === "hist-comp-body")) initHistComp();
    if (e.target && e.target.id === "proy-preview") initProyecciones();
    if (e.target && (e.target.id === "fondos-detalle" || e.target.id === "fondo-attr")) initFondos();
  });
})();

// ── 📍 Ubicación en la curva (YAS / Comparador) ────────────────────────────
// Tras cada swap de htmx, busca [data-locate] y dibuja un mini-scatter de la
// curva del bono (puntos ARS/USD + línea NSS, vía /graficos/data que ya está
// cacheado server-side ~2ms) con el/los bonos del usuario resaltados (rojo /
// verde) a SU precio. El JSON de la curva se cachea 4s client-side para no
// re-pedirlo en recomputes seguidos.
(function () {
  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fb;
  }
  function fmtPct(v) { return (v == null) ? "" : (v.toFixed(2).replace(".", ",") + "%"); }
  var HL_COLORS = ["#ef4444", "#22c55e", "#a78bfa"];
  var cache = {};   // curva|plazo -> {t, data}

  function getData(curve, plazo, fuente) {
    var key = curve + "|" + plazo + "|" + (fuente || "byma");
    var hit = cache[key];
    if (hit && Date.now() - hit.t < 4000) return Promise.resolve(hit.data);
    var url = "/graficos/data?curve=" + encodeURIComponent(curve) + "&plazo=" + encodeURIComponent(plazo);
    if (fuente && fuente !== "byma") url += "&fuente=" + encodeURIComponent(fuente);
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) { cache[key] = { t: Date.now(), data: d }; return d; });
  }

  function draw(el) {
    if (typeof uPlot === "undefined") return;
    var curve = el.dataset.curve, plazo = el.dataset.plazo || "24hs";
    var pts;
    try { pts = JSON.parse(el.dataset.pts || "[]"); } catch (e) { pts = []; }
    if (!curve || !pts.length) return;
    var fuente = el.dataset.fuente || "byma";
    getData(curve, plazo, fuente).then(function (d) {
      if (!d || !d.n) { el.innerHTML = '<p class="muted" style="font-size:12px">Sin puntos con cotización en la curva.</p>'; return; }
      // Merge: eje x = xs de la curva + las durations de los bonos resaltados.
      var xs = d.xs.slice();
      var ars = d.ars.slice(), usd = d.usd.slice(), nss = (d.nss || []).slice();
      // Códigos de la curva alineados a xs (los spliceamos igual que ars/usd):
      // etiquetas tenues sobre cada punto + tooltip al pasar el mouse (pedido
      // del desk 13/11: "para tener referencia"). Los resaltados llevan su
      // propio código en `hlCodes`.
      var codes = (d.codes && d.codes.length === d.xs.length) ? d.codes.slice() : xs.map(function () { return null; });
      var hls = pts.map(function () { return xs.map(function () { return null; }); });
      var hlCodes = xs.map(function () { return null; });
      pts.forEach(function (p, i) {
        var j = xs.findIndex(function (x) { return x >= p.d; });
        if (j === -1) j = xs.length;
        xs.splice(j, 0, p.d);
        ars.splice(j, 0, null); usd.splice(j, 0, null); codes.splice(j, 0, null); hlCodes.splice(j, 0, p.c);
        if (nss.length) nss.splice(j, 0, null);
        hls.forEach(function (h, k) { h.splice(j, 0, k === i ? p.t : null); });
      });
      var sc = function (label, color, size) {
        return { label: label, stroke: color, paths: function () { return null; },
                 points: { show: true, size: size || 6, fill: color, stroke: color },
                 value: function (u, v) { return fmtPct(v); } };
      };
      var series = [ {},
        sc("ARS", cssVar("--accent", "#ff9f00")),
        sc("USD", cssVar("--cyan", "#4cc9f0")) ];
      if (nss.length) series.push({ label: "NSS", stroke: cssVar("--cyan", "#4cc9f0"), width: 1.5,
                                    dash: [4, 3], points: { show: false },
                                    value: function (u, v) { return fmtPct(v); } });
      pts.forEach(function (p, i) { series.push(sc(p.c, HL_COLORS[i % HL_COLORS.length], 10)); });
      var data = [xs, ars, usd];
      if (nss.length) data.push(nss);
      hls.forEach(function (h) { data.push(h); });
      // Distancia a la curva (pedido: "en algún lado chiquito"): interpola la
      // NSS ORIGINAL (d.xs/d.nss, antes del splice) en la duration del bono y
      // muestra bono vs curva + el spread en pp. Cero requests extra.
      var metaTxt = "";
      if (d.nss && d.nss.length === d.xs.length && d.xs.length > 1) {
        var mlabel = (d.ylabel || "TIREA") + (d.fuente === "cafci" ? " · CAFCI" : "");
        pts.forEach(function (p) {
          var xq = Math.min(Math.max(p.d, d.xs[0]), d.xs[d.xs.length - 1]);
          var k = 0;
          while (k < d.xs.length - 1 && d.xs[k + 1] < xq) k++;
          var x0 = d.xs[k], x1 = d.xs[Math.min(k + 1, d.xs.length - 1)];
          var y0 = d.nss[k], y1 = d.nss[Math.min(k + 1, d.xs.length - 1)];
          if (y0 == null && y1 != null) y0 = y1;
          if (y1 == null && y0 != null) y1 = y0;
          if (y0 == null || y1 == null) return;
          var cy = (x1 > x0) ? y0 + (y1 - y0) * (xq - x0) / (x1 - x0) : y0;
          var dist = p.t - cy;
          metaTxt += (metaTxt ? " · " : "") + p.c + " " + fmtPct(p.t) +
            " vs curva NSS (" + mlabel + ") " + fmtPct(cy) + " → " +
            (dist >= 0 ? "+" : "") + dist.toFixed(2).replace(".", ",") + " pp";
        });
      }
      if (el.__u) { el.__u.destroy(); el.__u = null; }
      el.innerHTML = "";
      if (metaTxt) {
        var meta = document.createElement("p");
        meta.className = "muted";
        meta.style.cssText = "font-size:11.5px;margin:0 0 4px";
        meta.textContent = metaTxt;
        el.appendChild(meta);
      }
      // Series "scatter" con código por índice: ARS (1) y USD (2) llevan los de
      // la curva; cada resaltado, el suyo. La NSS no tiene código.
      var scat = [{ si: 1, cds: codes }, { si: 2, cds: codes }];
      var hlBase = nss.length ? 4 : 3;
      pts.forEach(function (p, i) { scat.push({ si: hlBase + i, cds: hlCodes }); });
      el.style.position = "relative";
      var tip = document.createElement("div");
      tip.className = "locate-tip";
      tip.style.cssText = "position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--border);" +
        "border-radius:6px;padding:3px 8px;font-size:11px;line-height:1.35;display:none;z-index:6;white-space:nowrap;color:var(--text)";
      var MUT = cssVar("--text-muted", "#8a8a8a");
      var fmtDur = function (v) { return v.toFixed(2).replace(".", ","); };
      el.__u = new uPlot({
        width: Math.max(el.clientWidth || 600, 320), height: 240,
        legend: { show: true },
        scales: { x: { time: false } },
        cursor: { points: { size: 9 }, focus: { prox: 24 } },
        axes: [
          { label: "Duration (años)", stroke: cssVar("--text-muted", "#999"), grid: { stroke: cssVar("--border-soft", "#222") } },
          { label: "TIREA %", stroke: cssVar("--text-muted", "#999"), grid: { stroke: cssVar("--border-soft", "#222") },
            values: function (u, vals) { return vals.map(fmtPct); } },
        ],
        series: series,
        hooks: {
          draw: [function (uu) {
            // Código tenue sobre cada punto de la curva (mismo criterio que el
            // chart de Gráficos: anti-superposición a 26×11 px; los resaltados
            // van primero para que nunca pierdan su etiqueta, en su color).
            var ctx = uu.ctx; ctx.save();
            ctx.font = "10px system-ui,-apple-system,sans-serif"; ctx.textBaseline = "bottom"; ctx.textAlign = "left";
            var X0 = uu.data[0], drawn = [];
            var orden = scat.slice(2).concat(scat.slice(0, 2));
            for (var s = 0; s < orden.length; s++) {
              var e = orden[s], arr = uu.data[e.si], ser = uu.series[e.si];
              if (!arr || !ser || !ser.show) continue;
              ctx.fillStyle = (e.cds === hlCodes) ? (ser.stroke || MUT) : MUT;
              ctx.globalAlpha = (e.cds === hlCodes) ? 1 : 0.75;
              for (var i = 0; i < X0.length; i++) {
                var yv = arr[i];
                if (yv == null || !e.cds[i]) continue;
                var X = uu.valToPos(X0[i], "x", true), Y = uu.valToPos(yv, "y", true), ok = true;
                for (var k = 0; k < drawn.length; k++) {
                  if (Math.abs(drawn[k][0] - X) < 26 && Math.abs(drawn[k][1] - Y) < 11) { ok = false; break; }
                }
                if (!ok) continue;
                drawn.push([X, Y]);
                ctx.fillText(e.cds[i], X + 5, Y - 3);
              }
            }
            ctx.restore();
          }],
          setCursor: [function (uu) {
            var i = uu.cursor.idx;
            if (i == null) { tip.style.display = "none"; return; }
            var cy = uu.cursor.top, cxl = uu.cursor.left, best = null, bestD = Infinity;
            var X0c = uu.data[0], i0 = i;
            // vecinos a ≤2 px: dos bonos con la misma duration tienen x contiguas
            for (var ii = Math.max(0, i0 - 2); ii <= Math.min(X0c.length - 1, i0 + 2); ii++) {
              if (ii !== i0 && (cxl == null || Math.abs(uu.valToPos(X0c[ii], "x") - cxl) > 2)) continue;
              for (var s = 0; s < scat.length; s++) {
                var e = scat[s], ser = uu.series[e.si];
                if (!ser || !ser.show) continue;
                var yv = uu.data[e.si][ii];
                if (yv == null || !e.cds[ii]) continue;
                var dd = (cy == null) ? 0 : Math.abs(uu.valToPos(yv, "y") - cy);
                if (dd < bestD) { bestD = dd; best = { e: e, yv: yv, i: ii }; }
              }
            }
            if (!best) { tip.style.display = "none"; return; }
            i = best.i;
            tip.innerHTML = "<b>" + best.e.cds[i] + "</b>" + (best.e.cds === hlCodes ? " · a tu precio" : "") +
              "<br>" + (d.ylabel || "TIREA") + " " + fmtPct(best.yv) + " · Dur " + fmtDur(X0c[i]);
            tip.style.display = "block";
            var L = uu.valToPos(X0c[i], "x"), T = uu.valToPos(best.yv, "y");
            var bw = el.clientWidth, bh = el.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight;
            var left = L + 12; if (left + tw > bw - 4) { left = L - tw - 12; } if (left < 2) { left = 2; }
            var top = T - th - 8; if (top < 2) { top = T + 16; } if (top + th > bh - 2) { top = bh - th - 2; }
            tip.style.left = left + "px"; tip.style.top = top + "px";
          }],
        },
      }, data, el);
      el.appendChild(tip);
      if (window.chartCopyInject) window.chartCopyInject(el, "curva-" + curve);
    }).catch(function () { /* red caída: sin chart, sin ruido */ });
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    var els = root.querySelectorAll("[data-locate]");
    for (var i = 0; i < els.length; i++) draw(els[i]);
    if (root.hasAttribute && root.hasAttribute("data-locate")) draw(root);
  }
  document.body.addEventListener("htmx:afterSwap", function (evt) { scan(evt.detail.target); });
  // Switch BYMA/CAFCI del card (YAS y Comparador comparten este widget): al
  // cambiar el select, la caja re-dibuja con la otra fuente. Default: BYMA.
  document.body.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.classList || !t.classList.contains("locate-fuente")) return;
    var card = t.closest(".locate-card");
    var el = card && card.querySelector("[data-locate]");
    if (el) { el.dataset.fuente = t.value; draw(el); }
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { scan(document); });
  } else { scan(document); }
})();

// ── Curvas en vivo (19/11): gráfico de la pestaña Curvas + cuadro de Gráficos ──
// Dos pantallas, un mismo scatter chico sobre uPlot (`mk`):
//   · Curvas: bid / último / offer de cada bono de la curva elegida y, en ROJO,
//     los what-if del Last (app.js los manda por el evento `cv-whatif`). Datos
//     de /graficos/data con nss=0 (sin ajuste ni grilla), cacheado por seq.
//   · Gráficos (superuser): un gráfico por curva en un cuadro de 2-3 columnas,
//     con UN pedido (/graficos/multi) para todas; recién cuando la sección
//     entra en pantalla y a lo sumo cada 5 s. La línea es una tendencia barata
//     que arma el server (la NSS exacta está en el gráfico grande).
// Velocidad: refresco por setData (sin recrear el chart), throttle por tick,
// nada con la pestaña oculta ni con el gráfico fuera de pantalla.
(function () {
  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fb;
  }
  function fPct(v) { return (v == null) ? "" : (v.toFixed(2).replace(".", ",") + "%"); }
  function fNum(v) { return (v == null) ? "" : v.toFixed(2).replace(".", ","); }
  function nulos(n) { var a = new Array(n); for (var i = 0; i < n; i++) a[i] = null; return a; }
  function vacio(a) { for (var i = 0; i < a.length; i++) if (a[i] != null) return false; return true; }

  // Scatter genérico. cfg = { xs, pts: [{label, color, size, hollow, vals, codes,
  //   kind, lbl, lblColor, bold}], lines: [{label, color, dash, width, vals}], h, ylabel,
  //   legend, compact, tip(code, kind, y, x), after(uu, cfg) }.
  function mk(el) {
    var st = { u: null, cfg: null, sig: "", zoom: false, self: false, tip: null };
    function build() {
      var cfg = st.cfg, MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border-soft", "#2a2a2a");
      var BG = cssVar("--bg", "#0b0e13");
      var series = [{ label: "Dur", value: function (u, v) { return fNum(v); } }];
      cfg.pts.forEach(function (p) {
        series.push({ label: p.label, stroke: p.color, paths: function () { return null; },
                      points: { show: true, size: p.size || 6, stroke: p.color, fill: p.hollow ? BG : p.color, width: p.hollow ? 1.5 : 1 },
                      value: function (u, v) { return fPct(v); } });
      });
      cfg.lines.forEach(function (l) {
        series.push({ label: l.label, stroke: l.color, width: l.width || 1.6, dash: l.dash || undefined,
                      points: { show: false }, value: function (u, v) { return fPct(v); } });
      });
      return {
        width: Math.max(el.clientWidth || 600, 240), height: cfg.h,
        legend: { show: !!cfg.legend, isolate: true },
        // `yr` (gráficos chicos): rango de y robusto a outliers — un bono por
        // vencer con una TIR disparatada aplastaba toda la curva contra el eje.
        scales: { x: { time: false },
                  y: { range: function (u, mn, mx) {
                    var r = st.cfg && st.cfg.yr;
                    if (r) return r;
                    return (typeof uPlot.rangeNum === "function") ? uPlot.rangeNum(mn, mx, 0.1, true) : [mn, mx];
                  } } },
        cursor: { points: { size: 8 }, focus: { prox: 24 } },
        padding: cfg.compact ? [8, 12, 0, 0] : [12, 30, 0, 0],
        axes: [
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: cfg.compact ? undefined : "Duration (años)", labelSize: cfg.compact ? 0 : 28, size: cfg.compact ? 26 : undefined },
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: cfg.compact ? undefined : cfg.ylabel, size: cfg.compact ? 52 : 56,
            values: function (u, vals) {
              return vals.map(function (v) { return (Math.abs(v) >= 1e5 ? v.toExponential(0) : v) + "%"; });
            } },
        ],
        series: series,
        hooks: {
          setScale: [function (u, key) { if (key === "x" && !st.self) st.zoom = true; }],
          draw: [function (uu) {
            var c = st.cfg, ctx = uu.ctx; ctx.save();
            ctx.textBaseline = "bottom"; ctx.textAlign = "left";
            var X0 = uu.data[0], drawn = [], MUT2 = cssVar("--text-muted", "#8a8a8a");
            // las series `bold` (what-if) primero: nunca pierden su etiqueta
            var orden = [];
            c.pts.forEach(function (p, i) { if (p.lbl && p.bold) orden.push(i); });
            c.pts.forEach(function (p, i) { if (p.lbl && !p.bold) orden.push(i); });
            for (var s = 0; s < orden.length; s++) {
              var p = c.pts[orden[s]], arr = uu.data[1 + orden[s]], ser = uu.series[1 + orden[s]];
              if (!arr || !ser || ser.show === false) continue;
              ctx.font = (p.bold ? "bold " : "") + (c.compact ? "9px" : "10px") + " system-ui,-apple-system,sans-serif";
              ctx.fillStyle = p.lblColor || MUT2;
              ctx.globalAlpha = p.bold ? 1 : 0.8;
              for (var i = 0; i < X0.length; i++) {
                var yv = arr[i], cd = p.codes[i];
                if (yv == null || !cd) continue;
                var X = uu.valToPos(X0[i], "x", true), Y = uu.valToPos(yv, "y", true), ok = true;
                for (var k = 0; k < drawn.length; k++) {
                  if (Math.abs(drawn[k][0] - X) < 26 && Math.abs(drawn[k][1] - Y) < 11) { ok = false; break; }
                }
                if (!ok) continue;
                drawn.push([X, Y]);
                // Sobre el borde derecho la etiqueta va a la izquierda del punto
                // (si no, el código del bono más largo quedaba cortado).
                var tx = X + 5;
                if (uu.bbox && ctx.measureText) {
                  var tw = ctx.measureText(cd).width;
                  if (tx + tw > uu.bbox.left + uu.bbox.width) tx = X - 5 - tw;
                }
                ctx.fillText(cd, tx, Y - 3);
              }
            }
            ctx.globalAlpha = 1;
            if (c.after) c.after(uu, c);
            ctx.restore();
          }],
          setCursor: [function (uu) {
            var c = st.cfg, tip = st.tip, i = uu.cursor.idx;
            if (!tip) return;
            if (i == null) { tip.style.display = "none"; return; }
            var X0 = uu.data[0], cy = uu.cursor.top, cx = uu.cursor.left, best = null, bestD = Infinity;
            // Vecinos a ≤ 8 px: dos bonos con la misma duration (o un what-if
            // sobre su bono) caen en x casi iguales y el idx resuelve a uno solo.
            for (var ii = Math.max(0, i - 4); ii <= Math.min(X0.length - 1, i + 4); ii++) {
              var dx = (cx == null) ? 0 : Math.abs(uu.valToPos(X0[ii], "x") - cx);
              if (ii !== i && dx > 8) continue;
              for (var s = 0; s < c.pts.length; s++) {
                var ser = uu.series[1 + s], yv = uu.data[1 + s][ii], cd = c.pts[s].codes[ii];
                if (!ser || ser.show === false || yv == null || !cd) continue;
                var dd = ((cy == null) ? 0 : Math.abs(uu.valToPos(yv, "y") - cy)) + 0.5 * dx;
                if (c.pts[s].bold) dd = Math.max(0, dd - 6);          // el what-if gana el empate
                if (dd < bestD) { bestD = dd; best = { s: s, i: ii, y: yv, code: cd }; }
              }
            }
            if (!best) { tip.style.display = "none"; return; }
            tip.innerHTML = c.tip ? c.tip(best.code, c.pts[best.s].kind, best.y, X0[best.i]) :
              ("<b>" + best.code + "</b><br>" + fPct(best.y) + " · Dur " + fNum(X0[best.i]));
            tip.style.display = "block";
            var L = uu.valToPos(X0[best.i], "x"), T = uu.valToPos(best.y, "y");
            var bw = el.clientWidth, bh = el.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight;
            var left = L + 12; if (left + tw > bw - 4) { left = L - tw - 12; } if (left < 2) { left = 2; }
            var top = T - th - 8; if (top < 2) { top = T + 16; } if (top + th > bh - 2) { top = bh - th - 2; }
            tip.style.left = left + "px"; tip.style.top = top + "px";
          }],
        },
      };
    }
    function limpiar() {
      Array.prototype.slice.call(el.querySelectorAll(".uplot,.alert,p,.skel")).forEach(function (n) { n.remove(); });
    }
    return {
      set: function (cfg) {
        var sig = cfg.pts.map(function (p) { return p.label; }).join("|") + "#" +
                  cfg.lines.map(function (l) { return l.label; }).join("|") + "#" + cfg.ylabel + "#" + cfg.h;
        var data = [cfg.xs];
        cfg.pts.forEach(function (p) { data.push(p.vals); });
        cfg.lines.forEach(function (l) { data.push(l.vals); });
        st.cfg = cfg;
        if (!st.u || sig !== st.sig) {
          if (st.u) { st.u.destroy(); st.u = null; }
          limpiar();
          st.sig = sig;
          if (!st.tip) {
            el.classList.add("cv-chart-box");
            st.tip = document.createElement("div");
            st.tip.className = "cv-tip";
            el.addEventListener("dblclick", function () { st.zoom = false; });
          }
          st.self = true;
          st.u = new uPlot(build(), data, el);
          st.self = false; st.zoom = false;
          el.appendChild(st.tip);
        } else {
          st.self = true;
          st.u.setData(data, !st.zoom);
          st.self = false;
        }
      },
      msg: function (txt) {
        if (st.u) { st.u.destroy(); st.u = null; st.sig = ""; }
        limpiar();
        var d = document.createElement("div"); d.className = "alert"; d.textContent = txt;
        el.appendChild(d);
      },
      size: function () { if (st.u && st.cfg) st.u.setSize({ width: Math.max(el.clientWidth || 600, 240), height: st.cfg.h }); },
      uplot: function () { return st.u; },
    };
  }

  // ── Curvas: bid / último / offer + what-if ────────────────────────────────
  var C_BID = "#22c55e", C_OFF = "#c084fc", C_WI = "#ef4444";

  // (payload de /graficos/data, what-if [{c, d, t, px, tm}]) → cfg del scatter. Pura.
  function cvChartCfg(j, wi) {
    var xs = j.xs.slice(), n0 = xs.length;
    var ars = (j.ars || nulos(n0)).slice(), usd = (j.usd || nulos(n0)).slice();
    var bid = (j.bid || nulos(n0)).slice(), off = (j.off || nulos(n0)).slice();
    var codes = (j.codes || nulos(n0)).slice();
    var wv = nulos(n0), wc = nulos(n0), info = {};
    (wi || []).slice().sort(function (a, b) { return a.d - b.d; }).forEach(function (p) {
      if (p.d == null || p.t == null) return;
      info[p.c] = p;
      var k = 0;
      while (k < xs.length && xs[k] < p.d) k++;
      // Un bullet no cambia de duration con el precio: el what-if cae en la
      // MISMA x que su bono → comparte el índice (otra serie).
      if (k < xs.length && xs[k] === p.d && wv[k] == null) { wv[k] = p.t; wc[k] = p.c; return; }
      var x = p.d;
      if (k < xs.length && xs[k] === x) { x = xs[k] + 1e-9; k++; }
      xs.splice(k, 0, x);
      [ars, usd, bid, off, codes].forEach(function (a) { a.splice(k, 0, null); });
      wv.splice(k, 0, p.t); wc.splice(k, 0, p.c);
    });
    var ORANGE = cssVar("--accent", "#e0843c"), CYAN = cssVar("--cyan", "#22b8cf"), meta = j.meta || {};
    var pts = [];
    if (!vacio(ars)) pts.push({ label: "Últ. ARS", color: ORANGE, size: 7, vals: ars, codes: codes, kind: "last", lbl: true });
    if (!vacio(usd)) pts.push({ label: "Últ. USD", color: CYAN, size: 7, vals: usd, codes: codes, kind: "last", lbl: true });
    pts.push({ label: "Bid", color: C_BID, size: 5, hollow: true, vals: bid, codes: codes, kind: "bid" });
    pts.push({ label: "Offer", color: C_OFF, size: 5, hollow: true, vals: off, codes: codes, kind: "off" });
    if (!vacio(wv)) pts.push({ label: "What-if", color: C_WI, size: 11, vals: wv, codes: wc, kind: "wi",
                               lbl: true, lblColor: C_WI, bold: true });
    return {
      xs: xs, pts: pts, lines: [], h: 320, ylabel: (j.ylabel || "TIREA") + " (%)", legend: true,
      tip: function (code, kind, y, x) {
        if (kind === "wi") {
          var w = info[code] || {}, o = "<b>" + code + "</b> · what-if";
          o += "<br>precio " + (w.px || "—") + " → TIR " + fPct(y) + " · Dur " + fNum(x);
          if (w.tm != null) {
            var d = (y - w.tm) * 100;
            o += "<br>vs últ. " + fPct(w.tm) + " → " + (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(0) + " bps";
          }
          return o;
        }
        var m = meta[code] || {}, h = "<b>" + code + "</b>" + (m.mon ? " · " + m.mon : "");
        if (kind === "bid") return h + "<br>bid " + fNum(m.bp) + " · TIR " + fPct(y);
        if (kind === "off") return h + "<br>offer " + fNum(m.op) + " · TIR " + fPct(y);
        var l2 = (m.p != null) ? (fNum(m.p) + (m.src ? " " + m.src : "") + (m.dt ? " · " + m.dt : "")) : (m.src || "");
        return h + (l2 ? "<br>" + l2 : "") + "<br>TIR " + fPct(y) + " · Dur " + fNum(x);
      },
      // Punteada del último al what-if del mismo bono + aro del punto rojo.
      after: function (uu, c) {
        var wis = null, wiIdx = -1;
        c.pts.forEach(function (p, i) { if (p.kind === "wi") { wis = p; wiIdx = i; } });
        if (!wis || uu.series[1 + wiIdx].show === false) return;
        var ctx = uu.ctx, X0 = uu.data[0];
        for (var i = 0; i < X0.length; i++) {
          if (wis.vals[i] == null) continue;
          var WX = uu.valToPos(X0[i], "x", true), WY = uu.valToPos(wis.vals[i], "y", true);
          for (var k = 0; k < X0.length; k++) {
            if (codes[k] !== wis.codes[i]) continue;
            var y0 = (ars[k] != null) ? ars[k] : usd[k];
            if (y0 == null) continue;
            ctx.strokeStyle = C_WI; ctx.lineWidth = 1.2; ctx.setLineDash([3, 3]);
            ctx.beginPath(); ctx.moveTo(uu.valToPos(X0[k], "x", true), uu.valToPos(y0, "y", true));
            ctx.lineTo(WX, WY); ctx.stroke(); ctx.setLineDash([]);
            break;
          }
          ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(WX, WY, 7, 0, Math.PI * 2); ctx.stroke();
        }
      },
    };
  }
  window.cvChartCfg = cvChartCfg;

  // (curva del payload de /graficos/multi, ylabel) → cfg del gráfico chico. Pura.
  function gmCfg(cv, ylabel) {
    var xs = [], ars = [], usd = [], cds = [], nss = [];
    var i = 0, g = 0, nx = cv.x.length, ng = (cv.gx || []).length, prev = -Infinity;
    while (i < nx || g < ng) {
      var esPt = (g >= ng) || (i < nx && cv.x[i] <= cv.gx[g]);
      var x = esPt ? cv.x[i] : cv.gx[g];
      if (x <= prev) x = prev + 1e-9;               // misma duration: cada bono su x
      prev = x; xs.push(x);
      if (esPt) {
        var u = cv.u && cv.u[i];
        ars.push(u ? null : cv.y[i]); usd.push(u ? cv.y[i] : null); cds.push(cv.c[i]); nss.push(null);
        i++;
      } else {
        ars.push(null); usd.push(null); cds.push(null); nss.push(cv.gy[g]);
        g++;
      }
    }
    var pts = [];
    if (!vacio(ars)) pts.push({ label: "ARS", color: cssVar("--accent", "#e0843c"), size: 5, vals: ars, codes: cds, kind: "last", lbl: true });
    if (!vacio(usd)) pts.push({ label: "USD", color: cssVar("--cyan", "#22b8cf"), size: 5, vals: usd, codes: cds, kind: "last", lbl: true });
    var lines = ng ? [{ label: "Tendencia", color: "#a78bfa", width: 1.4, vals: nss }] : [];
    // Rango de y robusto: cuartiles ± 2,5 rangos intercuartiles, recortado a
    // los datos. `fuera` = bonos que quedan fuera de escala (el título lo dice).
    var yr = null, fuera = 0, ys = cv.y.slice().sort(function (a, b) { return a - b; }), n = ys.length;
    if (n >= 5) {
      var q1 = ys[Math.floor((n - 1) * 0.25)], q3 = ys[Math.ceil((n - 1) * 0.75)], iqr = q3 - q1;
      if (iqr > 0) {
        var lo = Math.max(ys[0], q1 - 2.5 * iqr), hi = Math.min(ys[n - 1], q3 + 2.5 * iqr), pad = (hi - lo) * 0.08 || 0.5;
        for (var q = 0; q < n; q++) if (ys[q] < lo || ys[q] > hi) fuera++;
        if (fuera) yr = [lo - pad, hi + pad];
      }
    }
    return { xs: xs, pts: pts, lines: lines, h: 210, ylabel: ylabel || "TIREA", legend: false, compact: true,
             yr: yr, fuera: fuera,
             tip: function (code, kind, y, x) { return "<b>" + code + "</b><br>" + (ylabel || "TIREA") + " " + fPct(y) + " · Dur " + fNum(x); } };
  }
  window.gmCfg = gmCfg;

  // ¿está en pantalla? (IntersectionObserver; sin soporte = siempre sí)
  function enPantalla(el) {
    var st = { v: true };
    if (typeof IntersectionObserver !== "undefined") {
      st.v = false;
      new IntersectionObserver(function (es) { st.v = es[es.length - 1].isIntersecting; if (st.v && st.on) st.on(); },
                               { rootMargin: "200px" }).observe(el);
    }
    return st;
  }

  function initCurvaChart() {
    var el = document.querySelector("[data-curve-chart]");
    if (!el || typeof uPlot === "undefined") return;
    var sc = mk(el), lastJ = null, gen = 0, ctrl = null, lastLive = 0, pend = false;
    var vis = enPantalla(el);
    function val(name) {
      var e = document.querySelector('.curves [name="' + name + '"]:not([type=hidden])');
      if (!e) return "";
      return (e.type === "checkbox") ? (e.checked ? "true" : "false") : e.value;
    }
    function render() {
      if (!lastJ) return;
      var wi = window.cvWhatif || [];
      if (!lastJ.n && !wi.length) { sc.msg("Sin bonos con TIR y duration en esta curva (¿hay cotización?)."); return; }
      sc.set(cvChartCfg(lastJ, wi));
      if (window.chartCopyInject) window.chartCopyInject(el, "curva-" + (val("curve") || "curva"));
    }
    function load() {
      var mine = ++gen;
      if (ctrl) { try { ctrl.abort(); } catch (e) { /* noop */ } }
      var c = (typeof AbortController !== "undefined") ? new AbortController() : null;
      ctrl = c;
      var tm = c ? setTimeout(function () { try { c.abort(); } catch (e) { /* noop */ } }, 20000) : null;
      var q = "curve=" + encodeURIComponent(val("curve")) + "&plazo=" + encodeURIComponent(val("plazo") || "24hs") +
              "&leg=" + encodeURIComponent(val("leg") || "native") + "&only_quoting=" + (val("only_quoting") || "true") + "&nss=0";
      fetch("/graficos/data?" + q, c ? { signal: c.signal } : undefined)
        .then(function (r) { return r.json(); })
        .then(function (j) { if (mine !== gen) return; lastJ = j; render(); })
        .catch(function () { /* sin red / abortado: queda el último */ })
        .then(function () { if (tm) clearTimeout(tm); if (ctrl === c) ctrl = null; });
    }
    function live() {
      if (document.hidden) return;
      if (!vis.v) { pend = true; return; }             // fuera de pantalla: al volver
      var now = Date.now();
      if (now - lastLive < 2000) return;
      lastLive = now; pend = false;
      load();
    }
    vis.on = function () { if (pend || !lastJ) live(); };
    document.body.addEventListener("md-update", live);
    setInterval(live, 30000);
    document.body.addEventListener("cv-whatif", render);          // sin pedido: sólo redibuja
    document.body.addEventListener("change", function (e) {
      var n = e.target && e.target.name;
      if ((n === "curve" || n === "plazo" || n === "leg" || n === "only_quoting") &&
          e.target.closest && e.target.closest(".curves")) { lastLive = Date.now(); load(); }
    });
    var rz = null;
    window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(sc.size, 120); });
    load();
  }

  function initGrafMulti() {
    var grid = document.querySelector("[data-graf-multi]");
    var form = document.getElementById("graf-controls");
    if (!grid || !form || typeof uPlot === "undefined") return;
    var card = document.getElementById("graf-multi-card"), body = document.getElementById("graf-multi-body");
    var toggle = document.getElementById("graf-multi-toggle"), nEl = document.getElementById("graf-multi-n");
    var cells = {}, gen = 0, ctrl = null, lastLive = 0, pend = true, cargado = false;
    var vis = enPantalla(card || grid);
    function abierto() { return !body || !body.hidden; }
    function params() {
      var p = {};
      ["plazo", "metric", "dmin", "dmax", "exclude"].forEach(function (k) {
        var e = form.querySelector('[name="' + k + '"]'); if (e) p[k] = e.value;
      });
      var oq = form.querySelector('input[type=checkbox][name="only_quoting"]');
      p.only_quoting = (!oq || oq.checked) ? "true" : "false";
      return new URLSearchParams(p).toString();
    }
    function verArriba(key) {
      var sel = form.querySelector('[name="curve"]');
      if (!sel) return;
      sel.value = key;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      var top = document.getElementById("grafico-uplot");
      if (top && top.scrollIntoView) top.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function celda(cv) {
      var c = cells[cv.k];
      if (c) return c;
      var div = document.createElement("div"); div.className = "gm-cell";
      var t = document.createElement("div"); t.className = "gm-t";
      var a = document.createElement("a"); a.title = "Ver esta curva en el gráfico grande";
      a.addEventListener("click", function () { verArriba(cv.k); });
      var n = document.createElement("span"); n.className = "muted";
      t.appendChild(a); t.appendChild(n);
      var box = document.createElement("div"); box.className = "gm-c";
      div.appendChild(t); div.appendChild(box);
      c = cells[cv.k] = { div: div, a: a, n: n, sc: mk(box) };
      return c;
    }
    function pintar(j) {
      var vistos = {}, cola = [], bonos = 0;
      (j.curvas || []).forEach(function (cv) {
        var c = celda(cv);
        vistos[cv.k] = 1; bonos += cv.n;
        var cfg = gmCfg(cv, j.ylabel);
        c.a.textContent = cv.l;
        c.n.textContent = cv.n + " bono" + (cv.n === 1 ? "" : "s") + (cfg.fuera ? " · " + cfg.fuera + " fuera de escala" : "");
        c.n.title = cfg.fuera ? "Bonos con una tasa muy lejos del resto (p. ej. por vencer): no se dibujan para no aplastar la curva. Se ven en el gráfico grande." : "";
        grid.appendChild(c.div);                       // (re)ordena como el payload
        cola.push([c, cfg]);
      });
      Object.keys(cells).forEach(function (k) {
        if (!vistos[k]) { if (cells[k].div.parentNode) cells[k].div.parentNode.removeChild(cells[k].div); delete cells[k]; }
      });
      if (nEl) nEl.textContent = cola.length ? (cola.length + " curvas · " + bonos + " bonos · ") : "";
      if (!cola.length) { grid.textContent = "Sin curvas con cotización."; return; }
      // De a 4 por frame: crear ~20 charts de una frenaba el primer paint.
      var raf = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };
      (function paso() {
        for (var k = 0; k < 4 && cola.length; k++) { var e = cola.shift(); e[0].sc.set(e[1]); }
        if (cola.length) raf(paso);
      })();
    }
    function load() {
      var mine = ++gen;
      if (ctrl) { try { ctrl.abort(); } catch (e) { /* noop */ } }
      var c = (typeof AbortController !== "undefined") ? new AbortController() : null;
      ctrl = c;
      var tm = c ? setTimeout(function () { try { c.abort(); } catch (e) { /* noop */ } }, 30000) : null;
      fetch("/graficos/multi?" + params(), c ? { signal: c.signal } : undefined)
        .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
        .then(function (j) { if (mine !== gen) return; cargado = true; pintar(j); })
        .catch(function () { /* queda lo último */ })
        .then(function () { if (tm) clearTimeout(tm); if (ctrl === c) ctrl = null; });
    }
    function live(force) {
      if (document.hidden || !abierto()) { pend = true; return; }
      if (!vis.v) { pend = true; return; }
      var now = Date.now();
      if (!force && now - lastLive < 5000) return;
      lastLive = now; pend = false;
      load();
    }
    vis.on = function () { if (pend || !cargado) live(true); };
    document.body.addEventListener("md-update", function () { live(false); });
    setInterval(function () { live(false); }, 60000);
    var deb = null;
    ["plazo", "metric", "dmin", "dmax", "exclude", "only_quoting"].forEach(function (k) {
      Array.prototype.forEach.call(form.querySelectorAll('[name="' + k + '"]'), function (e) {
        e.addEventListener("change", function () { clearTimeout(deb); deb = setTimeout(function () { live(true); }, 250); });
      });
    });
    function tam() { Object.keys(cells).forEach(function (k) { cells[k].sc.size(); }); }
    function cols(n) {
      n = (n === 2) ? 2 : 3;
      grid.style.setProperty("--gm-cols", n);
      Array.prototype.forEach.call(document.querySelectorAll("[data-gm-cols]"), function (b) {
        b.classList.toggle("on", parseInt(b.getAttribute("data-gm-cols"), 10) === n);
      });
      try { localStorage.setItem("graf_multi_cols", String(n)); } catch (e) { /* noop */ }
      (window.requestAnimationFrame || setTimeout)(tam);
    }
    Array.prototype.forEach.call(document.querySelectorAll("[data-gm-cols]"), function (b) {
      b.addEventListener("click", function () { cols(parseInt(b.getAttribute("data-gm-cols"), 10)); });
    });
    function abrir(open) {
      if (!body || !toggle) return;
      body.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      var caret = toggle.querySelector(".graf-emis-caret");
      if (caret) caret.textContent = open ? "▾" : "▸";
      try { localStorage.setItem("graf_multi_open", open ? "1" : "0"); } catch (e) { /* noop */ }
      if (open) { live(true); (window.requestAnimationFrame || setTimeout)(tam); }
    }
    var c0 = 3, o0 = "1";
    try { c0 = parseInt(localStorage.getItem("graf_multi_cols") || "3", 10); o0 = localStorage.getItem("graf_multi_open") || "1"; } catch (e) { /* noop */ }
    cols(c0);
    if (toggle) toggle.addEventListener("click", function () { abrir(body.hidden); });
    abrir(o0 === "1");
    var rz = null;
    window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(tam, 150); });
  }

  function boot() { initCurvaChart(); initGrafMulti(); }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
