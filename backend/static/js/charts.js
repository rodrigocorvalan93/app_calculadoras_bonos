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
        hooks: {
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

  function boot() { initGraficos(); }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
