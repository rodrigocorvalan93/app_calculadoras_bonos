// Harness del widget "Ubicación en la curva" (YAS / Comparador) de
// static/js/charts.js: corre el bloque REAL en un VM de Node con un uPlot
// falso que captura opciones, datos y hooks. Regresión 13/11: etiqueta tenue
// con el código de cada bono de la curva sobre su punto (anti-superposición),
// el resaltado etiquetado en su color, y tooltip al pasar el mouse con
// código · TIR · duration. Lo invoca tests/test_locate.py; imprime JSON.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "charts.js"), "utf8");
const a = js.indexOf("// ── 📍 Ubicación en la curva");
const b = js.indexOf("})();", a);
if (a < 0 || b < 0) throw new Error("No encuentro el bloque de Ubicación en la curva en charts.js");

const payload = { n: 3, xs: [0.5, 1.0, 1.5], ars: [30.0, null, 31.0], usd: [null, 8.0, null],
                  nss: [29.5, 30.2, 30.9], codes: ["S31L6", "AL30C", "T30E6"], ylabel: "TIREA" };
let instancia = null;
function Fake(opts, data, el) { this.opts = opts; this.data = data; this.series = opts.series.map((s) => Object.assign({ show: true }, s)); this.ctx = null;
  this.cursor = {}; instancia = this; }
Fake.prototype.valToPos = function (v, scale) { return scale === "x" ? v * 100 : 300 - v * 5; };
Fake.prototype.destroy = function () {};
function el(tag) {
  return { tagName: tag, style: {}, dataset: {}, children: [], innerHTML: "", textContent: "", className: "",
           clientWidth: 600, clientHeight: 240, offsetWidth: 80, offsetHeight: 30,
           appendChild(c) { this.children.push(c); }, hasAttribute() { return false; },
           querySelectorAll() { return []; } };
}
const listeners = {};
const ctx = {
  console, Promise, Date, Math, JSON,
  uPlot: Fake,
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  fetch: () => Promise.resolve({ json: () => Promise.resolve(payload) }),
  document: { readyState: "complete", body: { addEventListener: (k, f) => { listeners[k] = f; } },
              createElement: el, querySelectorAll: () => [], addEventListener() {} },
  window: {},
};
vm.createContext(ctx);
vm.runInContext(js.slice(a, b + 5), ctx);

const box = el("div");
box.dataset = { curve: "lecap", plazo: "24hs", pts: JSON.stringify([{ c: "S29G6", d: 0.8, t: 32.5 }]) };
listeners["htmx:afterSwap"]({ detail: { target: { querySelectorAll: () => [box], hasAttribute: () => false } } });

setTimeout(() => {
  const u = instancia;
  const out = { ok: !!u };
  if (u) {
    out.xs = u.data[0];
    out.labels_series = u.opts.series.slice(1).map((s) => s.label);
    // draw: qué texto cayó sobre cada punto
    const textos = [];
    u.ctx = { save() {}, restore() {}, fillText: (t, x, y) => textos.push([t, x, y]), set fillStyle(v) {}, set font(v) {},
              set textBaseline(v) {}, set textAlign(v) {}, set globalAlpha(v) {} };
    u.opts.hooks.draw[0](u);
    out.etiquetas = textos.map((t) => t[0]);
    // setCursor sobre el AL30C (índice 2 tras el splice del resaltado en 0.8)
    const tip = box.children.find((c) => c.className === "locate-tip");
    u.cursor = { idx: u.data[0].indexOf(1.0), top: 300 - 8.0 * 5, left: 100 };
    u.opts.hooks.setCursor[0](u);
    out.tip_curva = tip.innerHTML;
    u.cursor = { idx: u.data[0].indexOf(0.8), top: 300 - 32.5 * 5, left: 80 };
    u.opts.hooks.setCursor[0](u);
    out.tip_resaltado = tip.innerHTML;
    u.cursor = { idx: null };
    u.opts.hooks.setCursor[0](u);
    out.tip_oculto = tip.style.display;
  }
  process.stdout.write(JSON.stringify(out));
}, 10);
