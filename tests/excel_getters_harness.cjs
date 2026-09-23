// Harness de los GETTERS del add-in de Excel: corre el functions.js REAL en un
// VM de Node (mismo patrón que excel_poller_harness.cjs) y llama a tablaGet /
// rofexGet / fxGet / wantsDate / isoToSerial con un snapshot sintético. Lo
// invoca tests/test_excel_getters.py; imprime JSON {caso: true|detalle}.
//   - OMS.TABLA("rofex") = mayorista; "rofex_min" / "futuros_min" / "rofex-min"
//     / ("rofex";"minorista") = minorista; el canal en el nombre gana.
//   - OMS.ROFEX acepta "minorista" / "mayorista" como canal.
//   - OMS.FX("a3500") = A3500 OFICIAL con fecha (serial) / anterior / var;
//     sin sección a3500 cae al cierre del feed; "cierre" = cierre del feed.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const source = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "excel", "functions.js"), "utf8");

class FakeCfError extends Error { constructor(code, msg) { super(msg); this.code = code; } }
const sandbox = {
  console, Promise, Math, JSON, Number, String, Array, Object, Error, Map, Set, RegExp, Date,
  setInterval() { return 1; }, clearInterval() {}, setTimeout, clearTimeout,
  window: { location: { search: "" }, localStorage: { getItem() { return null; }, setItem() {} }, OMS_BEACON() {} },
  OfficeRuntime: { storage: { getItem() { return Promise.resolve(null); }, setItem() { return Promise.resolve(); } } },
  CustomFunctions: { associate() {}, Error: FakeCfError, ErrorCode: { notAvailable: "#N/A" } },
  Office: { onReady() { return Promise.resolve({}); } },
  fetch() { return new Promise(() => {}); },
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const may = { code: "DLR/DIC26M", label: "Dic-26", vto: "31/12/2026", dias: 99, last: 1600, bid: 1599, offer: 1601,
              close: 1590, var_pct: 0.0063, tna: 0.30, tem: 0.022, td: 0.056, volume: 1000 };
const min = { code: "DLR/DIC26", label: "Dic-26", vto: "31/12/2026", dias: 99, last: 1610, bid: 1609, offer: 1611,
              close: 1595, var_pct: 0.0094, tna: 0.32, tem: 0.024, td: 0.06, volume: 50 };
const snap = {
  seq: 1, quotes: {}, extras: {},
  futuros: { may: [may], min: [min] },
  fx: { mep: 1539.12, ccl: 1606.87, canje: 0.044 },
  mayorista: { source: "SIOPEL", last: 1512.5, close: 1510.0 },
  a3500: { source: "A3500", last: 1515.1105, close: 1512.3, var_pct: 0.0019, date: "2026-09-09" },
};
const T = (panel, opcion) => sandbox.tablaGet(snap, panel, opcion);
const ultimo = (tabla) => (tabla[1] || [])[3];          // columna "Últ"
const eq = (a, b) => (a === b ? true : { got: a, want: b });
const throws = (fn) => { try { fn(); return { got: "no tiró" }; } catch (e) { return e instanceof FakeCfError ? true : { got: String(e) }; } };

const out = {};
// TABLA: canal por opción (como siempre)
out.rofex_default_mayorista = eq(ultimo(T("rofex")), 1600);
out.futuros_default_mayorista = eq(ultimo(T("futuros")), 1600);
out.rofex_opcion_min = eq(ultimo(T("rofex", "min")), 1610);
out.rofex_opcion_minorista = eq(ultimo(T("rofex", "minorista")), 1610);
out.rofex_opcion_mayorista = eq(ultimo(T("rofex", "mayorista")), 1600);
// TABLA: canal en el nombre del panel
out.rofex_min = eq(ultimo(T("rofex_min")), 1610);
out.futuros_min = eq(ultimo(T("futuros_min")), 1610);
out.rofex_guion_min = eq(ultimo(T("rofex-min")), 1610);
out.rofex_espacio_minorista_mayusculas = eq(ultimo(T("ROFEX MINORISTA")), 1610);
out.rofex_may = eq(ultimo(T("rofex_may")), 1600);
out.nombre_gana_a_opcion = eq(ultimo(T("rofex_min", "may")), 1610);
out.encabezado_igual = eq(JSON.stringify(T("rofex_min")[0]), JSON.stringify(T("rofex")[0]));
out.panel_desconocido_es_error = (() => { const r = T("rofexx"); return r instanceof FakeCfError ? true : { got: r }; })();
// ROFEX: canal con alias
out.rofex_get_default = eq(sandbox.rofexGet(snap, 1, "last"), 1600);
out.rofex_get_min = eq(sandbox.rofexGet(snap, 1, "last", "min"), 1610);
out.rofex_get_minorista = eq(sandbox.rofexGet(snap, 1, "last", "minorista"), 1610);
out.rofex_get_mayorista_tna = eq(sandbox.rofexGet(snap, "DLR/DIC26M", "tna", "mayorista"), 0.30);
// FX: A3500 oficial con fecha; cierre del feed aparte; fallback sin sección
out.fx_a3500_oficial = eq(sandbox.fxGet(snap, "a3500"), 1515.1105);
out.fx_a3500_fecha_serial = eq(sandbox.fxGet(snap, "a3500_fecha"), 46274);   // 09/09/2026
out.fx_a3500_ant = eq(sandbox.fxGet(snap, "a3500_ant"), 1512.3);
out.fx_a3500_var = eq(sandbox.fxGet(snap, "a3500_var"), 0.0019);
out.fx_cierre_feed = eq(sandbox.fxGet(snap, "cierre"), 1510.0);
out.fx_mayorista_intradia = eq(sandbox.fxGet(snap, "mayorista"), 1512.5);
out.fx_a3500_fallback_sin_seccion = eq(sandbox.fxGet({ mayorista: { close: 1510.0 } }, "a3500"), 1510.0);
out.fx_a3500_fecha_sin_seccion_vacia = eq(sandbox.fxGet({ mayorista: { close: 1510.0 } }, "a3500_fecha"), "");
out.tabla_fx_filas = (() => {
  const t = T("fx"); const m = Object.fromEntries(t.slice(1).map((r) => [r[0], r[1]]));
  const ok = m["A3500 (cierre)"] === 1515.1105 && m["A3500 fecha"] === "09/09/2026" &&
             m["Mayorista (cierre feed)"] === 1510.0 && m["Mayorista"] === 1512.5;
  return ok ? true : { got: m };
})();
// MACRO: 2º argumento y serial
out.wantsDate = (() => {
  const w = sandbox.wantsDate;
  const ok = w(true) === true && w("si") === true && w("Sí") === true && w("fecha") === true && w(1) === true && w("VERDADERO") === true &&
             w(false) === false && w(0) === false && w("") === false && w(undefined) === false && w("no") === false && w("valor") === false;
  return ok ? true : { got: "alguna combinación no coincide" };
})();
out.wantsDate_invalido_tira = throws(() => sandbox.wantsDate("zzz"));
out.isoToSerial = eq(sandbox.isoToSerial("2026-09-09"), 46274) === true && sandbox.isoToSerial("nada") === null ? true : { got: sandbox.isoToSerial("2026-09-09") };

process.stdout.write(JSON.stringify(out));
