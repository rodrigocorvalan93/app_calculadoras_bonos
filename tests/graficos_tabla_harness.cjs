// Harness de la tabla de Gráficos (static/js/charts.js): corre las funciones
// PURAS reales (grafTablaRows / grafTablaHTML) en un VM de Node contra un
// payload como el de /graficos/data. Regresión: orden del eje x, comparaciones
// en bloques propios, ficha (vto / calificación / industria), escape de HTML,
// formatos es-AR y la columna Margen sólo con esa métrica. Lo invoca
// tests/test_graficos_tabla.py; imprime JSON.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "charts.js"), "utf8");

const a = js.indexOf("  function fmtPct(v)");
const marca = "window.grafTablaHTML = grafTablaHTML;";
const b = js.indexOf(marca);
if (a < 0 || b < 0) { throw new Error("No encuentro el bloque de la tabla en charts.js"); }
const ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(js.slice(a, b + marca.length), ctx);

const j = {
  n: 3, metric: "tirea",
  xs: [0.5, 0.9, 1.4, 2.0],
  codes: ["S31L6", null, "T30E6", "TX26"],
  ars: [30.1, null, 31.2, null],
  usd: [null, null, null, 8.5],
  meta: {
    S31L6: { p: 1234.56, src: "últ.", tir: 30.1, tna: 27.0, tem: 2.2, dur: 0.5, mon: "ARS", vto: "31/07/2026", cal: "CCC-", ind: "Soberano Tasa Fija" },
    T30E6: { p: 99.0, src: "cierre", tir: 31.2, tna: 28.0, tem: 2.3, dur: 1.4, mon: "ARS", vto: "30/01/2026", cal: "CCC-", ind: "Soberano Tasa Fija" },
    TX26: { p: null, src: "CAFCI", tir: 8.5, tna: null, tem: null, dur: 2.0, mon: "USD", vto: "09/11/2026", cal: "CCC-", ind: "Soberano <Inflación>" },
    AL30C: { p: 60.2, src: "últ.", tir: 12.0, tna: 11.4, tem: 0.95, dur: 3.1, mon: "USD", vto: "09/07/2030", cal: "CCC-", ind: "Soberano" },
  },
  cmps: [{ label: "Bonares", codes: [null, "AL30C", null, null], vals: [null, 12.0, null, null], nss: [] }],
};

const rows = ctx.window.grafTablaRows(j);
const html = ctx.window.grafTablaHTML(rows, "tirea", "CER");
const anon = ctx.window.grafTablaHTML(rows, "tirea", true);
const solo = ctx.window.grafTablaHTML(ctx.window.grafTablaRows(Object.assign({}, j, { cmps: [] })), "tirea", false);
const margen = ctx.window.grafTablaHTML(rows, "margen", true);
const vacio = ctx.window.grafTablaRows({ n: 0, xs: [], codes: [], ars: [], usd: [], meta: {} });

const fallos = [];
function chk(nombre, cond) { if (!cond) fallos.push(nombre); }
chk("orden principal + comparación", JSON.stringify(rows.map((r) => r.code)) === JSON.stringify(["S31L6", "T30E6", "TX26", "AL30C"]));
chk("curva null en la principal", rows[0].curva === null && rows[2].curva === null);
chk("curva de la comparación", rows[3].curva === "Bonares" && rows[3].y === 12.0 && rows[3].x === 0.9);
chk("y de ars/usd", rows[0].y === 30.1 && rows[2].y === 8.5);
chk("meta enganchada", rows[2].m.ind === "Soberano <Inflación>");
chk("columna Curva con comparaciones", html.indexOf("<th>Curva</th>") >= 0 && solo.indexOf("<th>Curva</th>") < 0);
chk("label de la principal", html.indexOf("<td>CER</td>") >= 0 && html.indexOf("<td>Bonares</td>") >= 0 && anon.indexOf("<td>principal</td>") >= 0);
chk("cabeceras", ["Bono", "Vto.", "Calif.", "Industria", "Mon.", "Precio", "Fuente", "TIR", "TNA", "TEM", "Dur"].every((c) => html.indexOf(">" + c + "</th>") >= 0));
chk("ficha en la fila", html.indexOf("31/07/2026") >= 0 && html.indexOf("CCC-") >= 0 && html.indexOf("Soberano Tasa Fija") >= 0);
chk("html escapado", html.indexOf("Soberano &lt;Inflación&gt;") >= 0 && html.indexOf("<Inflación>") < 0);
chk("porcentajes es-AR", html.indexOf(">30,10%<") >= 0 && html.indexOf(">2,20%<") >= 0);
chk("precio con miles es-AR", html.indexOf(">1.234,56<") >= 0);
chk("sin dato = guion", html.indexOf('<td class="num">—</td>') >= 0 && html.indexOf(">CAFCI<") >= 0);
chk("duration", html.indexOf(">0,50<") >= 0 && html.indexOf(">3,10<") >= 0);
chk("columna Margen sólo en esa métrica", margen.indexOf("<th class=\"num\">Margen</th>") >= 0 && html.indexOf("Margen</th>") < 0);
chk("margen usa el y graficado", margen.indexOf(">12,00%<") >= 0);
chk("payload vacío → sin filas", vacio.length === 0);
chk("filas = 4", (html.match(/<tr>/g) || []).length === 5);      // 1 de cabecera + 4 de datos

process.stdout.write(JSON.stringify({ ok: fallos.length === 0, fallos, n: rows.length }));
process.exit(fallos.length ? 1 : 0);
