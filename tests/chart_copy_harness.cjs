// Harness del botón "copiar gráfico" (⧉) de static/js/app.js: corre el IIFE
// REAL en un VM de Node contra un mini DOM. Regresión del price action /
// distribución de Históricos que salían como una banda NEGRA sin línea al
// copiarlos: el SVG toma fill/stroke/opacity de CLASES (.fut-chart .pa-band1
// { fill: var(--accent); opacity: .14 }) y la imagen suelta no ve el CSS de
// la página. copySvg tiene que clonar el SVG con el estilo CALCULADO inline
// (colores ya resueltos al tema), respetar display:none (etiquetas apagadas),
// resolver var(--x, fallback), fijar width/height y NO tocar el SVG vivo.
// Lo invoca tests/test_chart_copy.py; imprime JSON.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const appJs = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "app.js"), "utf8");

const marca = appJs.indexOf("// ── Copiar gráfico al portapapeles");
const begin = appJs.indexOf("(function () {", marca);
const end = appJs.indexOf("\n})();", begin);
if (marca < 0 || begin < 0 || end < 0) { throw new Error("No encuentro el bloque de copiar gráfico en app.js"); }
const copyCode = appJs.slice(begin, end + "\n})();".length);

// ── Mini DOM ────────────────────────────────────────────────────────────────
function mkStyle() {
  const decl = new Map();
  const st = { setProperty(k, v) { if (v !== "" && v != null) { decl.set(k, String(v)); } }, _decl: decl };
  return new Proxy(st, {
    set(t, k, v) {
      if (typeof k === "string" && !(k in t)) { decl.set(k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase()), String(v)); return true; }
      t[k] = v; return true;
    },
  });
}
class El {
  constructor(tag, attrs, children, text) {
    this.tagName = tag.toUpperCase(); this.attrs = Object.assign({}, attrs || {});
    this.children = children || []; this.children.forEach((c) => { c.parentNode = this; });
    this.textContent = text || ""; this.style = mkStyle(); this.parentNode = null;
    const self = this;
    this.classList = {
      contains(c) { return (self.attrs.class || "").split(/\s+/).includes(c); },
      add(c) { if (!this.contains(c)) { self.attrs.class = ((self.attrs.class || "") + " " + c).trim(); } },
      remove(c) { self.attrs.class = (self.attrs.class || "").split(/\s+/).filter((x) => x !== c).join(" "); },
    };
  }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = v; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  cloneNode(deep) { return new El(this.tagName, this.attrs, deep ? this.children.map((c) => c.cloneNode(true)) : [], this.textContent); }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => n.children.forEach((c) => { if (sel === "*" || c.tagName.toLowerCase() === sel) { out.push(c); } walk(c); });
    walk(this); return out;
  }
  querySelector(sel) {
    if (sel === ":scope > .chart-copy" || sel === ":scope > .graf-dl") { return this.children.find((c) => c.classList.contains(sel.slice(9))) || null; }
    return this.querySelectorAll(sel)[0] || null;
  }
  closest() { return null; }
  get previousElementSibling() { const i = this.parentNode.children.indexOf(this); return i > 0 ? this.parentNode.children[i - 1] : null; }
  insertBefore(el, ref) { const i = this.children.indexOf(ref); this.children.splice(i, 0, el); el.parentNode = this; }
  appendChild(el) { this.children.push(el); el.parentNode = this; }
  getBoundingClientRect() { return { width: 980, height: 480 }; }
}
function ser(el) {
  const attrs = Object.entries(el.attrs).map(([k, v]) => ` ${k}="${v}"`).join("");
  const decl = [...el.style._decl].map(([k, v]) => `${k}: ${v}`).join("; ");
  const tag = el.tagName.toLowerCase();
  return `<${tag}${attrs}${decl ? ` style="${decl}"` : ""}>${el.children.map(ser).join("")}${el.textContent}</${tag}>`;
}

// Lo que style.css + el tema resuelven para cada clase (como lo devuelve el
// navegador en getComputedStyle: colores rgb, longitudes en px).
const RULES = {
  "pa-band1": { fill: "rgb(255, 153, 0)", opacity: "0.14" },
  "fc-line": { fill: "none", stroke: "rgb(255, 153, 0)", "stroke-width": "2px" },
  "pa-tend": { stroke: "rgb(255, 153, 0)", "stroke-width": "1.3px", "stroke-dasharray": "6px, 4px", opacity: "0.9" },
  "fc-vlabel": { fill: "rgb(140, 150, 160)", "font-size": "11px" },
  "hc-lbl": { display: "none" },
};
const DEFAULTS = {
  fill: "rgb(0, 0, 0)", "fill-opacity": "1", stroke: "none", "stroke-width": "1px", "stroke-dasharray": "none",
  "stroke-linecap": "butt", "stroke-linejoin": "miter", "stroke-opacity": "1", opacity: "1", display: "inline",
  visibility: "visible", "font-family": "system-ui, sans-serif", "font-size": "13px", "font-weight": "400",
  "font-style": "normal", "letter-spacing": "normal", "text-anchor": "start", "dominant-baseline": "auto",
  "font-variant-numeric": "tabular-nums", "--accent": "rgb(255, 153, 0)", "--bg": "rgb(11, 14, 19)",
};
const computedCalls = [];
function getComputedStyle(el) {
  computedCalls.push(el);
  const v = Object.assign({}, DEFAULTS);
  (el.getAttribute("class") || "").split(/\s+/).forEach((c) => Object.assign(v, RULES[c] || {}));
  if ((el.attrs.fill || "").startsWith("var(")) { v.fill = "rgb(1, 2, 3)"; }      // el browser ya resolvió la var
  return {
    getPropertyValue: (k) => (k in v ? v[k] : ""),
    display: v.display, visibility: v.visibility,
    fontFamily: v["font-family"], fontSize: v["font-size"], fontVariantNumeric: v["font-variant-numeric"],
  };
}

// ── Árbol: el price action tal como lo arma el template (clases, sin fill inline) ──
const banda = new El("polygon", { class: "pa-band1", points: "0,0 10,0 10,10" }, [new El("title", {}, [], "canal ±1σ")]);
const linea = new El("polyline", { class: "fc-line", points: "0,0 10,10" });
const tend = new El("line", { class: "pa-tend", x1: "0", y1: "0", x2: "10", y2: "10" });
const vlabel = new El("text", { class: "fc-vlabel", x: "1", y: "2" }, [], "10.000");
const apagada = new El("text", { class: "hc-lbl", x: "3", y: "4" }, [], "TZXM7");
const conVar = new El("rect", { fill: "var(--accent)", stroke: "var(--nope, #123456)", x: "0", y: "0", width: "1", height: "1" });
const svg = new El("svg", { class: "fut-chart pa-chart", role: "img", viewBox: "0 0 980 480" }, [banda, linea, tend, vlabel, apagada, conVar]);
const wrap = new El("div", {}, [svg]);
const html = new El("html", {}, [new El("body", {}, [wrap])]);

const images = [];
class Image { set src(v) { this._src = v; images.push(v); } get src() { return this._src; } }
const document = {
  readyState: "complete", documentElement: html,
  body: { addEventListener() {} },
  createElement(tag) { return new El(tag); },
  querySelectorAll(sel) { return html.querySelectorAll(sel); },
};
const context = {
  document, getComputedStyle, Image, XMLSerializer: class { serializeToString(el) { return ser(el); } },
  navigator: {}, window: {}, URL: { createObjectURL() { return "blob:x"; }, revokeObjectURL() {} },
  setTimeout() { return 1; }, console, Math, parseFloat, encodeURIComponent, decodeURIComponent, String, Number, Error, Promise,
};
vm.runInNewContext(copyCode, context, { filename: "app.js:chart-copy" });

const res = { ok: true, fallos: [] };
function check(nombre, cond, detalle) { res[nombre] = !!cond; if (!cond) { res.ok = false; res.fallos.push(nombre + (detalle ? ": " + detalle : "")); } }

// 1) el botón ⧉ queda como hermano ANTES del svg (role=img)
const btn = svg.previousElementSibling;
check("boton_inyectado", btn && btn.classList.contains("chart-copy") && typeof btn.onclick === "function");

// 2) click → serializa un CLON con estilos calculados y lo manda al <img>
btn.onclick();
const src = images[0] || "";
const out = decodeURIComponent(src.split(",", 2)[1] || "");
res.svg = out;
check("img_data_svg", src.startsWith("data:image/svg+xml"));
check("xmlns", /<svg[^>]*xmlns="http:\/\/www\.w3\.org\/2000\/svg"/.test(out));
check("tamano_fijo", /<svg[^>]* width="980"[^>]* height="480"/.test(out));
check("banda_con_color_y_opacidad", /<polygon[^>]*style="[^"]*fill: rgb\(255, 153, 0\)[^"]*opacity: 0\.14/.test(out), out);
check("linea_con_stroke_sin_fill", /<polyline[^>]*style="[^"]*fill: none;[^"]*stroke: rgb\(255, 153, 0\)[^"]*stroke-width: 2px/.test(out), out);
check("tendencia_dasharray", /<line[^>]*style="[^"]*stroke-dasharray: 6px, 4px[^"]*opacity: 0\.9/.test(out), out);
check("texto_con_fuente_y_color", /<text class="fc-vlabel"[^>]*style="[^"]*fill: rgb\(140, 150, 160\)[^"]*font-family: system-ui, sans-serif[^"]*font-size: 11px/.test(out), out);
check("etiqueta_apagada_sigue_oculta", /<text class="hc-lbl"[^>]*style="display: none">/.test(out), out);
check("titles_sin_estilo", /<title>canal ±1σ<\/title>/.test(out), out);
check("var_resuelta_y_fallback", !/var\(/.test(out) && /stroke="#123456"/.test(out) && /fill="rgb\(255, 153, 0\)"/.test(out), out);
check("fuente_en_la_raiz", /<svg[^>]*style="[^"]*font-family: system-ui, sans-serif[^"]*font-variant-numeric: tabular-nums/.test(out), out);
// 3) el SVG vivo no se toca (estilos inline sólo en el clon)
check("svg_vivo_intacto", [svg, ...svg.querySelectorAll("*")].every((e) => e.style._decl.size === 0) && !svg.attrs.width);
// 4) eficiencia: UNA lectura de estilo calculado por nodo renderizable + la raíz
//    (los <title> no se leen); el documentElement se lee sólo para las var(--x).
const renderizables = svg.querySelectorAll("*").filter((e) => e.tagName !== "TITLE").length;
const lecturas = computedCalls.filter((e) => e !== html).length;
check("una_lectura_por_nodo", lecturas === renderizables + 1, `${lecturas} lecturas para ${renderizables} nodos`);

process.stdout.write(JSON.stringify(res));
process.exit(res.ok ? 0 : 1);
