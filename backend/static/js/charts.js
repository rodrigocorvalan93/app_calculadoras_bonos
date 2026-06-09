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
    var u = null, codes = [];

    box.style.position = "relative";
    var tip = document.createElement("div");
    tip.style.cssText = "position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--border);" +
      "border-radius:6px;padding:3px 8px;font-size:11px;display:none;z-index:6;white-space:nowrap;color:var(--text)";
    box.appendChild(tip);

    function params() {
      var p = {};
      form.querySelectorAll("[name]").forEach(function (el) {
        p[el.name] = (el.type === "checkbox") ? (el.checked ? "true" : "false") : el.value;
      });
      return new URLSearchParams(p).toString();
    }

    function scatter(label, color) {
      return { label: label, stroke: color, paths: function () { return null; },
               points: { show: true, size: 7, stroke: color, fill: color },
               value: function (uu, v) { return fmtPct(v); } };
    }

    function opts() {
      return {
        width: box.clientWidth || 900, height: 460,
        scales: { x: { time: false } },
        axes: [
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: "Duration (años)", labelSize: 30 },
          { stroke: MUT, grid: { stroke: BORD, width: 1 }, ticks: { stroke: BORD },
            label: "TIREA (%)", size: 56,
            values: function (uu, vals) { return vals.map(function (v) { return v + "%"; }); } },
        ],
        series: [
          { label: "Dur", value: function (uu, v) { return fmtNum(v); } },
          scatter("ARS", ORANGE),
          scatter("USD/USB", CYAN),
          { label: "NSS", stroke: NSSCOL, width: 2, points: { show: false },
            value: function (uu, v) { return fmtPct(v); } },
        ],
        cursor: { points: { size: 9 }, focus: { prox: 24 } },
        legend: { isolate: true },
        padding: [12, 34, 0, 0],
        hooks: {
          draw: [function (uu) {
            // Etiqueta el código de cada bono sobre su punto (anti-superposición).
            var ctx = uu.ctx; ctx.save();
            ctx.font = "10px system-ui,-apple-system,sans-serif"; ctx.fillStyle = MUT; ctx.textBaseline = "bottom";
            var X0 = uu.data[0], A = uu.data[1], U = uu.data[2];
            var aS = uu.series[1].show, uS = uu.series[2].show, drawn = [];
            for (var i = 0; i < X0.length; i++) {
              if (!codes[i]) continue;
              var isA = A[i] != null, isU = U[i] != null, yv = isA ? A[i] : (isU ? U[i] : null);
              if (yv == null || (isA && !aS) || (isU && !uS)) continue;
              var X = uu.valToPos(X0[i], "x", true), Y = uu.valToPos(yv, "y", true), ok = true;
              for (var k = 0; k < drawn.length; k++) {
                if (Math.abs(drawn[k][0] - X) < 26 && Math.abs(drawn[k][1] - Y) < 11) { ok = false; break; }
              }
              if (!ok) continue;
              drawn.push([X, Y]);
              ctx.fillText(codes[i], X + 5, Y - 3);
            }
            ctx.restore();
          }],
          setCursor: [function (uu) {
            var i = uu.cursor.idx;
            if (i == null) { tip.style.display = "none"; return; }
            var yv = (uu.data[1][i] != null) ? uu.data[1][i] : uu.data[2][i];
            if (yv == null || !codes[i]) { tip.style.display = "none"; return; }
            var L = uu.valToPos(uu.data[0][i], "x"), T = uu.valToPos(yv, "y");
            tip.innerHTML = "<b>" + codes[i] + "</b> · Dur " + fmtNum(uu.data[0][i]) + " · " + fmtPct(yv);
            tip.style.left = (L + 10) + "px"; tip.style.top = (T - 6) + "px"; tip.style.display = "block";
          }],
        },
      };
    }

    function clear() {
      Array.prototype.slice.call(box.querySelectorAll(".uplot,.alert")).forEach(function (n) { n.remove(); });
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
          var nss = (j.nss && j.nss.length === j.xs.length) ? j.nss : j.xs.map(function () { return null; });
          var data = [j.xs, j.ars, j.usd, nss];
          codes = j.codes || [];
          if (recreate || !u) {
            if (u) u.destroy();
            clear();
            u = new uPlot(opts(), data, box);
          } else {
            u.setData(data);
          }
        })
        .catch(function () { /* sin red → mantiene el último chart */ });
    }

    load(true);
    form.querySelectorAll("[name]").forEach(function (el) {
      el.addEventListener("change", function () { load(true); });
    });
    setInterval(function () { load(false); }, 5000);
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
