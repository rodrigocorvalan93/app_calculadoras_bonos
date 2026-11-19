// Harness de los gráficos nuevos de static/js/charts.js (19/11): corre el
// bloque REAL "Curvas en vivo" en un VM de Node con un uPlot falso. Lo invoca
// tests/test_curvas_whatif_graficos.py; imprime JSON {caso: true | detalle}.
//   - cvChartCfg: bid / último / offer + what-if (rojo). Un bullet no cambia de
//     duration con el precio → el what-if comparte la x de su bono; el hover lo
//     alcanza y muestra precio, TIR y Δ bps contra el último.
//   - gmCfg (cuadro de todas las curvas): puntos + tendencia en un eje x estrictamente
//     creciente (dos bonos con la misma duration no se pisan) y rango de y
//     robusto a outliers.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "charts.js"), "utf8");
const a = js.indexOf("// ── Curvas en vivo (19/11)");
if (a < 0) throw new Error("No encuentro el bloque 'Curvas en vivo' en charts.js");

let inst = null;
function Fake(opts, data, el) { this.opts = opts; this.data = data; this.series = opts.series.map((s) => Object.assign({ show: true }, s));
  this.cursor = {}; this.bbox = { left: 0, width: 1000 }; inst = this; }
Fake.prototype.valToPos = function (v, scale) { return scale === "x" ? v * 100 : 300 - v * 5; };
Fake.prototype.destroy = function () {};
Fake.prototype.setData = function (d) { this.data = d; this.sets = (this.sets || 0) + 1; };
Fake.prototype.setSize = function () {};
function el(tag) {
  return { tagName: tag, style: { setProperty() {} }, dataset: {}, children: [], innerHTML: "", textContent: "", className: "",
           clientWidth: 600, clientHeight: 320, offsetWidth: 90, offsetHeight: 30,
           classList: { add() {}, toggle() {} }, appendChild(c) { this.children.push(c); }, addEventListener() {},
           querySelectorAll() { return []; }, querySelector() { return null; }, hasAttribute() { return false; } };
}
const win = {};
const ctx = {
  console, Promise, Date, Math, JSON, Array, Object, Infinity, parseInt, setTimeout, clearTimeout, setInterval() { return 0; },
  encodeURIComponent, URLSearchParams,
  uPlot: Fake,
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  fetch: () => new Promise(() => {}),
  document: { readyState: "complete", hidden: false, documentElement: {}, body: { addEventListener() {} },
              createElement: el, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null, addEventListener() {} },
  window: win,
};
vm.createContext(ctx);
vm.runInContext(js.slice(a), ctx);

const eq = (x, y) => (JSON.stringify(x) === JSON.stringify(y) ? true : { got: x, want: y });
const out = {};

// ── Curvas ──
const j = { n: 3, xs: [0.44, 0.9, 1.5], ars: [29.7, 31.0, null], usd: [null, null, 8.5],
            bid: [29.9, null, 8.7], off: [29.5, 30.8, null], codes: ["M30A7", "TML27", "AL30D"], ylabel: "TIREA",
            meta: { M30A7: { p: 100.68, src: "últ", mon: "ARS", bp: 100.6, op: 100.75 }, TML27: { p: 104.5, src: "cierre", mon: "ARS", op: 104.6 },
                    AL30D: { p: 70.1, src: "últ", mon: "USB", bp: 70.0 } } };
const sinWi = win.cvChartCfg(j, []);
out.sin_whatif_solo_puntas_y_ultimo = eq(sinWi.pts.map((p) => p.label), ["Últ. ARS", "Últ. USD", "Bid", "Offer"]);
out.sin_lineas = eq(sinWi.lines.length, 0);
// what-if de un bullet: MISMA duration que su bono → comparte el índice
const wi = [{ c: "M30A7", d: 0.44, t: 34.77, px: "99,00", tm: 29.7 }, { c: "TML27", d: 0.95, t: 33.0, px: "103,00", tm: 31.0 }];
const con = win.cvChartCfg(j, wi);
out.con_whatif_serie_roja = eq(con.pts.map((p) => [p.label, p.color])[4], ["What-if", "#ef4444"]);
out.x_del_bullet_compartida = eq(con.xs, [0.44, 0.9, 0.95, 1.5]);
const W = con.pts[4];
out.whatif_vals = eq(W.vals, [34.77, null, 33.0, null]);
out.whatif_codes = eq(W.codes, ["M30A7", null, "TML27", null]);
out.mercado_intacto = eq([con.pts[0].vals, con.pts[0].codes], [[29.7, 31.0, null, null], ["M30A7", "TML27", null, "AL30D"]]);
out.payload_no_se_muta = eq(j.xs, [0.44, 0.9, 1.5]);
// dos what-if a la misma duration: cada uno su x
const dos = win.cvChartCfg(j, [{ c: "A", d: 2.0, t: 10, px: "1" }, { c: "B", d: 2.0, t: 11, px: "2" }]);
out.dos_whatif_misma_duration = (dos.xs.length === 5 && dos.xs[3] < dos.xs[4]) ? true : { got: dos.xs };
// tooltips
out.tip_whatif = eq(con.tip("M30A7", "wi", 34.77, 0.44), "<b>M30A7</b> · what-if<br>precio 99,00 → TIR 34,77% · Dur 0,44<br>vs últ. 29,70% → +507 bps");
out.tip_bid = eq(con.tip("M30A7", "bid", 29.9, 0.44), "<b>M30A7</b> · ARS<br>bid 100,60 · TIR 29,90%");
out.tip_ultimo = eq(con.tip("TML27", "last", 31.0, 0.9), "<b>TML27</b> · ARS<br>104,50 cierre<br>TIR 31,00% · Dur 0,90");

// ── Cuadro de todas las curvas ──
const cv = { k: "tamar", l: "TAMAR", n: 6, x: [0.44, 0.44, 0.9, 1.2, 1.5, 1.8], y: [29.7, 30.4, 31.0, 31.5, 32.0, 900.0],
             c: ["M30A7", "T30A7", "TML27", "TMG27", "TMF28", "RARO"], u: [0, 0, 0, 0, 1, 0], gx: [0.44, 1.0, 1.8], gy: [29.9, 31.2, 32.1] };
const g = win.gmCfg(cv, "TIREA");
out.gm_x_estrictamente_creciente = g.xs.every((x, i) => i === 0 || x > g.xs[i - 1]) ? true : { got: g.xs };
out.gm_todos_los_bonos = eq(g.pts[0].codes.filter(Boolean).sort(), ["M30A7", "RARO", "T30A7", "TMF28", "TMG27", "TML27"]);
out.gm_series = eq([g.pts.map((p) => p.label), g.lines.map((l) => l.label), g.compact, g.legend], [["ARS", "USD"], ["Tendencia"], true, false]);
out.gm_usd_separado = eq(g.pts[1].vals.filter((v) => v != null), [32.0]);
out.gm_nss_alineada = eq(g.lines[0].vals.filter((v) => v != null), [29.9, 31.2, 32.1]);
out.gm_outlier_fuera_de_escala = (g.fuera === 1 && g.yr && g.yr[1] < 100 && g.yr[0] < 29.7) ? true : { got: [g.fuera, g.yr] };
const sano = win.gmCfg({ k: "x", l: "X", n: 5, x: [1, 2, 3, 4, 5], y: [10, 11, 12, 13, 14], c: ["a", "b", "c", "d", "e"], u: [0, 0, 0, 0, 0], gx: [], gy: [] }, "TIREA");
out.gm_sin_outliers_rango_libre = eq([sano.yr, sano.fuera, sano.lines.length, sano.pts.length], [null, 0, 0, 1]);

process.stdout.write(JSON.stringify(out));
