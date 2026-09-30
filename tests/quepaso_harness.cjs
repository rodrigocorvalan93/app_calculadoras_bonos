// Harness de "Qué pasó" (static/js/app.js): corre las funciones PURAS reales
// (qpSegStats / qpSegCells) en un VM de Node. Regresión: los promedios del
// segmento sin los bonos destildados replican la media simple del server
// (_avg_seg: sólo los que tienen dato; cupones sobre el mismo set que Δ
// Precio), el conteo "(n de total)", y los formatos es-AR del encabezado.
// Lo invoca tests/test_historico_semanal.py; imprime JSON.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "app.js"), "utf8");

const a = js.indexOf("// ── Qué pasó: tilde por bono");
const marca = "window.qpSegCells = qpSegCells;";
const b = js.indexOf(marca);
if (a < 0 || b < 0) { throw new Error("No encuentro el bloque de Qué pasó en app.js"); }
const ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(js.slice(a, b + marca.length) + "\n})();", ctx);

const rows = [
  { code: "S30S6", dprice: 0.0369, dtir: -0.0295, dtem: -0.0020, cup: null, tir1: 0.28, tem1: 0.0208, dur: 0.10 },
  { code: "S16O6", dprice: 0.0401, dtir: -0.0548, dtem: -0.0037, cup: 0.01, tir1: 0.26, tem1: 0.0194, dur: 0.20 },
  { code: "S29E7", dprice: null,   dtir: null,    dtem: null,    cup: null, tir1: null, tem1: null,   dur: 0.50 },
  { code: "T30J7", dprice: 0.0235, dtir: 0.0248,  dtem: 0.0016,  cup: null, tir1: 0.30, tem1: 0.0221, dur: 0.80 },
];
const fallos = [];
function chk(cond, msg) { if (!cond) fallos.push(msg); }
const cerca = (x, y) => Math.abs(x - y) < 1e-12;

// Todos: media de los que tienen dato (S29E7 sin Δ no entra a Δ, sí a dur)
const st = ctx.window.qpSegStats(rows, []);
chk(st.n === 4 && st.total === 4, "conteo total");
chk(cerca(st.dprice, (0.0369 + 0.0401 + 0.0235) / 3), "Δ precio = media de los 3 con dato");
chk(cerca(st.cup, (0 + 0.01 + 0) / 3), "cupones sobre el mismo set que Δ precio (sin dato = 0)");
chk(cerca(st.dtir, (-0.0295 - 0.0548 + 0.0248) / 3), "Δ TIR");
chk(cerca(st.tir, (0.28 + 0.26 + 0.30) / 3), "TIR prom.");
chk(cerca(st.dur, (0.10 + 0.20 + 0.50 + 0.80) / 4), "dur prom. cuenta al bono sin Δ");

// Destildando T30J7 (el outlier que sube la TIR)
const st2 = ctx.window.qpSegStats(rows, ["T30J7"]);
chk(st2.n === 3 && st2.total === 4, "conteo con uno afuera");
chk(cerca(st2.dprice, (0.0369 + 0.0401) / 2), "Δ precio sin el excluido");
chk(cerca(st2.dtir, (-0.0295 - 0.0548) / 2), "Δ TIR sin el excluido");
chk(cerca(st2.dur, (0.10 + 0.20 + 0.50) / 3), "dur sin el excluido");

// Todo afuera → sin promedios, no explota
const st3 = ctx.window.qpSegStats(rows, rows.map(r => r.code));
chk(st3.n === 0 && st3.dprice === null && st3.tir === null && st3.dur === null, "sin bonos → null");

// Formatos es-AR del encabezado (idénticos al template)
const c = ctx.window.qpSegCells(st2);
chk(c.n === "(3 de 4)", "conteo '(n de total)': " + c.n);
chk(c.dprice.text === "3,85%" && c.dprice.cls === "px-up", "Δ precio es-AR: " + c.dprice.text);
chk(c.dtir.text === "-4,22 pp" && c.dtir.cls === "px-up", "Δ TIR en pp con signo, compresión = verde: " + c.dtir.text);
chk(c.cup === "✂ cupones +0,50%", "cupones: " + c.cup);
chk(c.tir === "27,0%", "TIR prom. 1 decimal: " + c.tir);
chk(c.tem === "2,01%", "TEM prom. 2 decimales: " + c.tem);
chk(c.dur === "0,27", "dur 2 decimales: " + c.dur);
const c0 = ctx.window.qpSegCells(ctx.window.qpSegStats(rows, []));
chk(c0.n === "(4)", "sin exclusiones el conteo queda como el server: " + c0.n);
const c3 = ctx.window.qpSegCells(st3);
chk(c3.dprice.text === "—" && c3.dtir.text === "—" && c3.cup === "" && c3.tir === "—", "sin bonos → guiones");
const cs = ctx.window.qpSegCells(ctx.window.qpSegStats([{ code: "A", dprice: -0.0201, dtir: 0.0208, dtem: 0.0016, cup: 0.0018, tir1: 0.107, tem1: 0.0085, dur: 3.78 }], []));
chk(cs.dprice.text === "-2,01%" && cs.dprice.cls === "px-down" && cs.dtir.text === "+2,08 pp" && cs.dtir.cls === "px-down", "signos negativos / suba de TIR en rojo");

console.log(JSON.stringify({ ok: fallos.length === 0, fallos, n: 4 }));
process.exit(fallos.length ? 1 : 0);
