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

    function params() {
      var p = {};
      form.querySelectorAll("[name]").forEach(function (el) {
        if (el.multiple) {
          // 'Comparar con' es multi-select → coma-separado (el server lo splitea).
          p[el.name] = Array.prototype.map.call(el.selectedOptions, function (o) {
            return o.value;
          }).filter(Boolean).join(",");
        } else {
          p[el.name] = (el.type === "checkbox") ? (el.checked ? "true" : "false") : el.value;
        }
      });
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
    function codesOf(e) { return e.ci < 0 ? codes : (cmps[e.ci] ? cmps[e.ci].codes : null); }

    // Tooltip chico (≤4 líneas, 11px): código · moneda / precio · tipo · fecha /
    // TIR · TNA / TEM · Dur. Para bid/offer muestra la punta y su TIR.
    function tipHTML(code, m, kind) {
      var head = "<b>" + code + "</b>";
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
            ctx.restore();
          }],
          setCursor: [function (uu) {
            var i = uu.cursor.idx;
            if (i == null) { tip.style.display = "none"; return; }
            // Punto más cercano (en Y) al cursor entre las series con valor en i.
            var cy = uu.cursor.top, best = null, bestD = Infinity;
            for (var s = 0; s < SCAT.length; s++) {
              var e = SCAT[s], ser = uu.series[e.si];
              if (!ser || !ser.show) continue;
              var yv = uu.data[e.si][i];
              if (yv == null) continue;
              var dd = (cy == null) ? 0 : Math.abs(uu.valToPos(yv, "y") - cy);
              if (dd < bestD) { bestD = dd; best = { e: e, yv: yv }; }
            }
            var cds = best && codesOf(best.e), code = cds ? cds[i] : null;
            if (!code) { tip.style.display = "none"; return; }
            tip.innerHTML = tipHTML(code, meta[code], best.e.kind);
            var L = uu.valToPos(uu.data[0][i], "x"), T = uu.valToPos(best.yv, "y");
            tip.style.left = (L + 10) + "px"; tip.style.top = (T - 6) + "px"; tip.style.display = "block";
          }],
        },
      };
    }

    function clear() {
      // p = el placeholder "Cargando gráfico…" del template (quedaba pegado
      // arriba del chart para siempre).
      Array.prototype.slice.call(box.querySelectorAll(".uplot,.alert,p")).forEach(function (n) { n.remove(); });
    }

    function load(recreate) {
      fetch("/graficos/data?" + params())
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (!j || !j.n) {
            if (u) { u.destroy(); u = null; }
            clear();
            var e = document.createElement("div"); e.className = "alert";
            e.textContent = "Sin bonos con TIREA y Duration (¿hay cotización?).";
            box.appendChild(e); return;
          }
          var vac = j.xs.map(function () { return null; });
          var nss = (j.nss && j.nss.length === j.xs.length) ? j.nss : vac;
          var data = [j.xs, j.ars, j.usd, j.bid || vac, j.off || vac, nss];
          var newCmps = j.cmps || [];
          for (var ci = 0; ci < newCmps.length; ci++) {
            var c = newCmps[ci];
            var cn = (c.nss && c.nss.length === j.xs.length) ? c.nss : vac;
            data.push(c.vals || vac, cn);
          }
          // Firma estructural = labels de las comparaciones. Si cambió el set de
          // series (cantidad/orden/nombre), hay que recrear el chart; si sólo
          // cambian los datos, setData preserva el zoom.
          var newSig = newCmps.map(function (c) { return c.label; }).join("|");
          if (newSig !== sig) { sig = newSig; recreate = true; }
          cmps = newCmps;
          meta = j.meta || {};
          codes = j.codes || [];
          if (j.ylabel) yLabel = j.ylabel + " (%)";   // TIREA/TEM según la métrica
          if (recreate || !u) {
            if (u) u.destroy();
            clear();
            selfSet = true;                 // la construcción dispara setScale: no es zoom del usuario
            u = new uPlot(opts(), data, box);
            selfSet = false;
            userZoomed = false;             // chart nuevo → arranca siguiendo los datos
          } else {
            // Si el usuario hizo zoom, refrescamos los datos SIN re-encuadrar
            // (resetScales=false) para no pisarle la vista.
            selfSet = true;
            u.setData(data, !userZoomed);
            selfSet = false;
          }
        })
        .catch(function () { /* sin red → mantiene el último chart */ });
    }

    // Doble-click resetea el zoom (default de uPlot): volvemos a auto-encuadrar.
    box.addEventListener("dblclick", function () { userZoomed = false; });

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
    Array.prototype.slice.call(box.querySelectorAll(".uplot,.alert")).forEach(function (n) { n.remove(); });
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

  // ── Históricos · serie macro (línea, eje temporal) ────────────────────────
  function initHistMacro() {
    var box = document.getElementById("hist-macro-uplot");
    var ctrls = document.getElementById("hm-ctrls");
    if (!box || !ctrls || typeof uPlot === "undefined") return;
    var MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333");
    var u = null;
    box.style.position = "relative";
    function load() {
      fetch("/historicos/data?" + paramsOf(ctrls)).then(function (r) { return r.json(); }).then(function (j) {
        clearBox(box);
        if (!j || !j.n) {
          if (u) { u.destroy(); u = null; }
          var e = document.createElement("div"); e.className = "alert"; e.textContent = "Sin datos para esta serie.";
          box.appendChild(e); return;
        }
        var opts = {
          width: box.clientWidth || 900, height: 420,
          scales: { x: { time: true } },
          axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD } },
                 { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD }, size: 60 }],
          series: [{ value: function (uu, v) { return v == null ? "" : uPlot.fmtDate("{DD}/{MM}/{YYYY}")(new Date(v * 1000)); } },
                   { label: j.label, stroke: cssVar("--accent", "#e0843c"), width: 1.6, points: { show: false },
                     value: function (uu, v) { return fmtNum(v); } }],
          cursor: { focus: { prox: 24 } },
        };
        if (u) u.destroy();
        u = new uPlot(opts, [j.x, j.y], box);
      }).catch(function () {});
    }
    load();
    ctrls.querySelectorAll("[name]").forEach(function (el) { el.addEventListener("change", load); });
    window.addEventListener("resize", function () { if (u) u.setSize({ width: box.clientWidth || 900, height: 420 }); });
  }

  // ── Históricos · tasas por curva (multilínea + bandas) ────────────────────
  function initHistCurva() {
    var box = document.getElementById("hist-curva-uplot");
    var ctrls = document.getElementById("hc-ctrls");
    if (!box || !ctrls || typeof uPlot === "undefined") return;
    var PAL = palette(), MUT = cssVar("--text-muted", "#8a8a8a"), BORD = cssVar("--border", "#333");
    box.style.position = "relative";
    function draw() {
      fetch("/historicos/curva/data?" + paramsOf(ctrls)).then(function (r) { return r.json(); }).then(function (j) {
        clearBox(box);
        if (!j || !j.loaded || !j.series || !j.series.length) {
          if (box._u) { box._u.destroy(); box._u = null; }
          var e = document.createElement("div"); e.className = "alert";
          e.textContent = "Sin datos históricos para esta curva en el rango/filtro elegido.";
          box.appendChild(e); return;
        }
        var data = [j.x].concat(j.series.map(function (s) { return s.y; }));
        var series = [{ value: function (uu, v) { return v == null ? "" : uPlot.fmtDate("{DD}/{MM}/{YYYY}")(new Date(v * 1000)); } }]
          .concat(j.series.map(function (s, i) {
            return { label: s.code, stroke: PAL[i % PAL.length], width: 1.4, points: { show: false },
                     value: function (uu, v) { return fmtPct(v); } };
          }));
        var bands = j.bands;
        var opts = {
          width: box.clientWidth || 900, height: 520,
          scales: { x: { time: true } },
          axes: [{ stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD } },
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
            // código de cada bono al final de su línea (anti-superposición vertical)
            ctx.font = "10px system-ui,-apple-system,sans-serif"; ctx.textBaseline = "middle";
            var X = u.data[0], drawn = [];
            for (var si = 1; si < u.series.length; si++) {
              if (!u.series[si].show) continue;
              var ys = u.data[si], li = -1;
              for (var i = ys.length - 1; i >= 0; i--) { if (ys[i] != null) { li = i; break; } }
              if (li < 0) continue;
              var px = u.valToPos(X[li], "x", true), py = u.valToPos(ys[li], "y", true), ok = true;
              for (var d = 0; d < drawn.length; d++) { if (Math.abs(drawn[d] - py) < 11) { ok = false; break; } }
              if (!ok) continue;
              drawn.push(py);
              ctx.fillStyle = u.series[si].stroke;
              ctx.fillText(u.series[si].label, px + 4, py);
            }
            ctx.restore();
          }] },
        };
        if (box._u) box._u.destroy();
        box._u = new uPlot(opts, data, box);
      }).catch(function () {});
    }
    if (!ctrls.dataset.bound) {
      ctrls.dataset.bound = "1";
      ctrls.querySelectorAll("[name]").forEach(function (el) { el.addEventListener("change", draw); });
    }
    draw();
  }

  function boot() { initGraficos(); initHistMacro(); }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
  // La pestaña "Tasas por curva" se carga lazy (htmx); al insertarse, init uPlot.
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "hist-curva") initHistCurva();
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
      var hls = pts.map(function () { return xs.map(function () { return null; }); });
      pts.forEach(function (p, i) {
        var j = xs.findIndex(function (x) { return x >= p.d; });
        if (j === -1) j = xs.length;
        xs.splice(j, 0, p.d);
        ars.splice(j, 0, null); usd.splice(j, 0, null);
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
      el.__u = new uPlot({
        width: Math.max(el.clientWidth || 600, 320), height: 240,
        legend: { show: true },
        scales: { x: { time: false } },
        axes: [
          { label: "Duration (años)", stroke: cssVar("--text-muted", "#999"), grid: { stroke: cssVar("--border-soft", "#222") } },
          { label: "TIREA %", stroke: cssVar("--text-muted", "#999"), grid: { stroke: cssVar("--border-soft", "#222") },
            values: function (u, vals) { return vals.map(fmtPct); } },
        ],
        series: series,
      }, data, el);
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
