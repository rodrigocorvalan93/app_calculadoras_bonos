/* Funciones custom del add-in OMS Bonos (runtime compartido con el taskpane).
 *
 * Motor: UNA sola conexión por libro — sondea /excel/v1/seq (entero plano)
 * cada 1 s y sólo cuando la secuencia avanzó baja /excel/v1/snapshot; todas
 * las celdas suscritas se actualizan en batch desde ese único snapshot. Mismo
 * patrón seq→refresh que la web (static/js/app.js). Vanilla JS, sin libs.
 */
/* global CustomFunctions, Office, OfficeRuntime, Excel */
"use strict";

// ── Motor de datos compartido ────────────────────────────────────────────────
var OMSFeed = (function () {
  var POLL_MS = 1000;
  var token = "";
  var snap = null;        // último snapshot completo
  var lastSeq = null;
  var timer = null;
  var status = "off";     // off | live | idle | auth | error
  var sinks = [];         // callbacks (celdas + taskpane)

  function getTokenSync() { return token; }

  function loadToken() {
    // OfficeRuntime.storage es el storage compartido del add-in; localStorage
    // queda de fallback para pruebas en browser.
    return new Promise(function (resolve) {
      try {
        OfficeRuntime.storage.getItem("oms_token").then(function (t) {
          if (t) token = t;
          resolve(token);
        }, function () { resolve(token); });
      } catch (e) {
        try { token = window.localStorage.getItem("oms_token") || token; } catch (e2) { /* noop */ }
        resolve(token);
      }
    });
  }

  function setToken(t) {
    token = (t || "").trim();
    try { OfficeRuntime.storage.setItem("oms_token", token); } catch (e) { /* noop */ }
    try { window.localStorage.setItem("oms_token", token); } catch (e) { /* noop */ }
    snap = null; lastSeq = null;          // fuerza re-fetch con el token nuevo
    tick();
  }

  function headers() { return { "X-OMS-Token": token }; }

  function notify() {
    for (var i = 0; i < sinks.length; i++) {
      try { sinks[i](snap, status); } catch (e) { /* una celda rota no frena al resto */ }
    }
  }

  function tick() {
    loadToken().then(function () {
      if (!token) { status = "auth"; notify(); return; }
      fetch("/excel/v1/seq", { headers: headers(), cache: "no-store" })
        .then(function (r) {
          if (r.status === 401) { status = "auth"; notify(); return null; }
          if (!r.ok) { throw new Error("http " + r.status); }
          return r.text();
        })
        .then(function (txt) {
          if (txt === null) { return null; }
          var s = parseInt(txt, 10);
          if (snap !== null && s === lastSeq) {
            status = (snap.health && snap.health.warn) ? "stale" : "idle";
            notify(); return null;
          }
          return fetch("/excel/v1/snapshot", { headers: headers(), cache: "no-store" })
            .then(function (r) {
              if (r.status === 401) { status = "auth"; notify(); return null; }
              if (!r.ok) { throw new Error("http " + r.status); }
              return r.json();
            })
            .then(function (data) {
              if (!data) { return null; }
              snap = data; lastSeq = data.seq;
              // "stale" pisa a "live": el seq avanza también por MAE/pollers,
              // así que puede haber snapshot nuevo con precios BYMA viejos.
              status = (data.health && data.health.warn) ? "stale" : "live";
              notify();
              return null;
            });
        })
        .catch(function () { if (status !== "auth") { status = "error"; } notify(); });
    });
  }

  function start() {
    if (!timer) { timer = setInterval(tick, POLL_MS); tick(); }
  }

  function subscribe(fn) {
    sinks.push(fn);
    start();
    if (snap !== null || status !== "off") {
      try { fn(snap, status); } catch (e) { /* noop */ }
    }
    return function () {
      var i = sinks.indexOf(fn);
      if (i >= 0) { sinks.splice(i, 1); }
    };
  }

  return { subscribe: subscribe, setToken: setToken, loadToken: loadToken,
           getToken: getTokenSync, snapshot: function () { return snap; },
           status: function () { return status; }, tick: tick };
})();

// ── Normalización de argumentos ──────────────────────────────────────────────
var FIELD_ALIASES = {
  "": "last", "last": "last", "ultimo": "last", "último": "last", "px": "last",
  "bid": "bid", "compra": "bid", "ask": "ask", "offer": "ask", "venta": "ask",
  "bid_size": "bid_size", "volbid": "bid_size", "ask_size": "ask_size", "volask": "ask_size",
  "last_size": "last_size", "open": "open", "apertura": "open",
  "close": "close", "cierre": "close", "close_date": "close_date", "fechacierre": "close_date",
  "high": "high", "max": "high", "low": "low", "min": "low",
  "vol": "vol", "volumen": "vol", "monto": "vol", "nominal": "nominal", "nominales": "nominal",
  "trades": "trades", "operaciones": "trades", "vwap": "vwap",
  "var": "var", "variacion": "var", "variación": "var", "last_ts": "last_ts", "hora": "last_ts",
  "oi": "oi", "interes_abierto": "oi", "interés_abierto": "oi"
};
var MAE_FIELDS = {
  "last": "last", "close": "close", "var": "var_pct", "vol": "volumen",
  "nominal": "volumen", "monto": "monto", "high": "max", "low": "min",
  "plazo": "plazo", "moneda": "moneda", "segmento": "segmento"
};

function normField(campo) {
  var k = String(campo == null ? "" : campo).trim().toLowerCase();
  return FIELD_ALIASES[k] || k;
}

function normPlazo(plazo) {
  var p = String(plazo == null ? "" : plazo).trim().toLowerCase();
  if (p === "" || p === "24" || p === "24hs" || p === "48" || p === "48hs" ||
      p === "t1" || p === "t+1" || p === "t2" || p === "t+2") { return "24hs"; }
  if (p === "ci" || p === "0" || p === "t0" || p === "t+0" || p === "contado") { return "CI"; }
  return "24hs";
}

function naError(msg) {
  return new CustomFunctions.Error(CustomFunctions.ErrorCode.notAvailable, msg || "Sin dato");
}

// ── Getters contra el snapshot ───────────────────────────────────────────────
function quoteGet(s, especie, campo, plazo, mercado) {
  var code = String(especie || "").trim().toUpperCase();
  var f = normField(campo);
  var mkt = String(mercado || "byma").trim().toLowerCase();
  if (!code) { return naError("Especie vacía"); }
  if (mkt === "mae") {
    var m = (s.mae || {})[code] || (s.mae || {})[code.replace(/[CD]$/, "")];
    if (!m) { return naError("Sin dato MAE para " + code); }
    // Plazo EXPLÍCITO → fila de ese segmento (CI / 24hs). Antes se ignoraba y
    // pedir CI devolvía la fila default (mayor volumen = t+1) en silencio.
    if (plazo != null && String(plazo).trim() !== "") {
      var pn = normPlazo(plazo);
      var pp = (m.plazos || {})[pn];
      if (!pp) { return naError("Sin dato MAE " + pn + " para " + code); }
      m = pp;
    }
    var mv = m[MAE_FIELDS[f] || f];
    return mv == null ? "" : mv;
  }
  var q = (s.quotes || {})[code];
  var row = q ? q[normPlazo(plazo)] : null;
  if (!row) { row = (s.extras || {})[code]; }
  if (!row) { return naError("Sin dato para " + code); }
  var v = row[f];
  return v == null ? "" : v;
}

function fxGet(s, tipo) {
  var t = String(tipo || "").trim().toLowerCase();
  var fx = s.fx || {}, may = s.mayorista || {};
  if (t === "mep" || t === "usb") { return fx.mep == null ? "" : fx.mep; }
  if (t === "ccl" || t === "cable" || t === "usd") { return fx.ccl == null ? "" : fx.ccl; }
  if (t === "canje") { return fx.canje == null ? "" : fx.canje; }
  if (t === "mep_ci") { return fx.mep_ci == null ? "" : fx.mep_ci; }
  if (t === "ccl_ci") { return fx.ccl_ci == null ? "" : fx.ccl_ci; }
  if (t === "mayorista" || t === "oficial" || t === "siopel") { return may.last == null ? "" : may.last; }
  if (t === "a3500" || t === "cierre") { return may.close == null ? "" : may.close; }
  if (t === "mep_base") { return fx.mep_base || ""; }
  if (t === "ccl_base") { return fx.ccl_base || ""; }
  return naError("Tipo desconocido: " + t);
}

function rofexRow(s, contrato, canal) {
  var rows = ((s.futuros || {})[String(canal || "may").toLowerCase() === "min" ? "min" : "may"]) || [];
  if (typeof contrato === "number") { return rows[contrato - 1] || null; }
  var c = String(contrato || "").trim().toUpperCase();
  if (!c) { return null; }
  if (/^\d+$/.test(c)) { return rows[parseInt(c, 10) - 1] || null; }
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].code.toUpperCase() === c || rows[i].label.toUpperCase() === c) { return rows[i]; }
  }
  return null;
}

function rofexGet(s, contrato, campo, canal) {
  var r = rofexRow(s, contrato, canal);
  if (!r) { return naError("Contrato no encontrado"); }
  var f = normField(campo);
  var map = { "last": "last", "bid": "bid", "ask": "offer", "close": "close",
              "var": "var_pct", "vol": "volume", "tna": "tna", "tem": "tem",
              "tea": "tea", "tir": "tea", "td": "td", "directo": "td",
              "dias": "dias", "vto": "vto",
              "label": "label", "code": "code", "tna_bid": "tna_bid", "tna_ask": "tna_offer",
              "oi": "oi", "bid_size": "bid_size", "ask_size": "offer_size" };
  var v = r[map[f] || f];
  return v == null ? "" : v;
}

function caucionGet(s, dias, campo, moneda) {
  var m = String(moneda || "ARS").trim().toUpperCase() === "USD" ? "USD" : "ARS";
  var rows = ((s.cauciones || {})[m]) || [];
  var n = parseInt(dias, 10);
  var row = null;
  for (var i = 0; i < rows.length; i++) { if (rows[i]._n === n) { row = rows[i]; break; } }
  if (!row) { return naError("Sin caución a " + dias + "D"); }
  var f = normField(campo);
  var map = { "last": "tasa", "tasa": "tasa", "bid": "bid", "ask": "offer",
              "close": "close", "var": "var", "vol": "volumen", "plazo": "plazo" };
  var v = row[map[f] || f];
  return v == null ? "" : v;
}

// ── Tablas (spill) ───────────────────────────────────────────────────────────
function nn(v) { return v == null ? "" : v; }

function tablaGet(s, panel, opcion) {
  var p = String(panel || "").trim().toLowerCase();
  var i, r, out;
  if (p === "futuros" || p === "rofex") {
    var rows = ((s.futuros || {})[String(opcion || "may").toLowerCase() === "min" ? "min" : "may"]) || [];
    out = [["Contrato", "Vto", "Días", "Últ", "Bid", "Ask", "Cierre", "Var %", "TNA", "TEM", "Directo", "Vol"]];
    for (i = 0; i < rows.length; i++) {
      r = rows[i];
      out.push([r.code, nn(r.vto), nn(r.dias), nn(r.last), nn(r.bid), nn(r.offer),
                nn(r.close), nn(r.var_pct), nn(r.tna), nn(r.tem), nn(r.td), nn(r.volume)]);
    }
    return out;
  }
  if (p === "cauciones") {
    var m = String(opcion || "ARS").trim().toUpperCase() === "USD" ? "USD" : "ARS";
    var crows = ((s.cauciones || {})[m]) || [];
    out = [["Plazo", "TNA", "Bid", "Ask", "Cierre", "Var (pp)", "Vol"]];
    for (i = 0; i < crows.length; i++) {
      r = crows[i];
      out.push([r.plazo, nn(r.tasa), nn(r.bid), nn(r.offer), nn(r.close), nn(r.var), nn(r.volumen)]);
    }
    return out;
  }
  if (p === "fx" || p === "dolares" || p === "dólares") {
    var fx = s.fx || {}, may = s.mayorista || {};
    return [["Tipo", "Valor"],
            ["MEP", nn(fx.mep)], ["CCL", nn(fx.ccl)], ["Canje", nn(fx.canje)],
            ["MEP CI", nn(fx.mep_ci)], ["CCL CI", nn(fx.ccl_ci)],
            ["Mayorista", nn(may.last)], ["A3500 (cierre)", nn(may.close)]];
  }
  if (p === "mae") {
    var mae = s.mae || {};
    out = [["Ticker", "Últ", "Cierre", "Var %", "Mín", "Máx", "VN", "Monto", "Plazo", "Moneda"]];
    var ks = Object.keys(mae).sort();
    for (i = 0; i < ks.length; i++) {
      r = mae[ks[i]];
      if (!r) { continue; }
      out.push([ks[i], nn(r.last), nn(r.close), nn(r.var_pct), nn(r.min), nn(r.max),
                nn(r.volumen), nn(r.monto), nn(r.plazo), nn(r.moneda)]);
    }
    return out;
  }
  if (p === "quotes" || p === "especies" || p === "cruda") {
    var plazo = opcion ? normPlazo(opcion) : null;
    var qs = s.quotes || {};
    out = [["Especie", "Plazo", "Últ", "Bid", "Ask", "Vol Bid", "Vol Ask",
            "Cierre", "F. cierre", "Var", "Vol $", "Nominal", "VWAP"]];
    var codes = Object.keys(qs).sort();
    for (i = 0; i < codes.length; i++) {
      var byPlazo = qs[codes[i]];
      var plazos = plazo ? [plazo] : Object.keys(byPlazo);
      for (var j = 0; j < plazos.length; j++) {
        r = byPlazo[plazos[j]];
        if (!r) { continue; }
        out.push([codes[i], plazos[j], nn(r.last), nn(r.bid), nn(r.ask), nn(r.bid_size),
                  nn(r.ask_size), nn(r.close), nn(r.close_date), nn(r.var), nn(r.vol),
                  nn(r.nominal), nn(r.vwap)]);
      }
    }
    return out;
  }
  return naError("Panel desconocido: " + p);
}

// ── Registro de funciones streaming ──────────────────────────────────────────
// Cada celda se suscribe al feed; en cada snapshot nuevo recalcula su valor y
// sólo pushea si cambió (evita repaints de celdas quietas).
function makeStreaming(getter) {
  return function () {
    var args = Array.prototype.slice.call(arguments);
    var invocation = args.pop();
    var lastPushed;
    var un = OMSFeed.subscribe(function (s, status) {
      var v;
      if (status === "auth") {
        v = naError("Token de Excel inválido o no configurado (abrí el panel OMS Bonos)");
      } else if (!s) {
        return;                               // todavía sin primer snapshot
      } else {
        try { v = getter.apply(null, [s].concat(args)); }
        catch (e) { v = naError(String(e && e.message || e)); }
      }
      var key = JSON.stringify(v);
      if (key !== lastPushed) { lastPushed = key; invocation.setResult(v); }
    });
    invocation.onCanceled = function () { if (un) { un(); } };
  };
}

function histFn(serie, dias) {
  var qs = dias ? ("?days=" + encodeURIComponent(dias)) : "";
  return OMSFeed.loadToken().then(function (t) {
    return fetch("/excel/v1/hist/" + encodeURIComponent(String(serie || "").trim()) + qs,
                 { headers: { "X-OMS-Token": t }, cache: "no-store" });
  }).then(function (r) {
    if (r.status === 401) { throw naError("Token de Excel inválido"); }
    if (!r.ok) { throw naError("HTTP " + r.status); }
    return r.json();
  }).then(function (data) {
    var pts = data.points || [];
    if (!pts.length) { throw naError("Serie vacía o desconocida: " + serie); }
    var out = [["Fecha", data.label || data.serie || String(serie)]];
    for (var i = 0; i < pts.length; i++) { out.push([pts[i][0], pts[i][1]]); }
    return out;
  });
}

// ── Calculadora YAS en celdas (TIREA / PRECIO / TNA / TICKET / CALC) ────────
// Anti-carga: estas funciones NO streamean — corren sólo cuando Excel
// recalcula. Todas las celdas que recalculan juntas se juntan en UN POST
// batch (ventana de 80 ms, dedup en vuelo) y el resultado se memoiza por
// argumentos, así arrastrar una fórmula por 200 filas es 5 requests chicos
// una única vez, y F9 sin cambios no pega al server.
var OMSCalc = (function () {
  var BATCH_MS = 80;
  var CHUNK = 40;          // límite del server por batch
  var MEMO_MAX = 800;
  var memo = {}, memoN = 0;
  var pending = {};        // key → [{resolve, reject}]
  var queue = [];          // items únicos a mandar
  var flushTimer = null;

  function keyOf(it) {
    return [it.code, it.modo, it.valor, it.plazo, it.nominales || ""].join("|");
  }

  function request(it) {
    var k = keyOf(it);
    if (Object.prototype.hasOwnProperty.call(memo, k)) { return Promise.resolve(memo[k]); }
    return new Promise(function (resolve, reject) {
      if (pending[k]) { pending[k].push({ resolve: resolve, reject: reject }); return; }
      pending[k] = [{ resolve: resolve, reject: reject }];
      queue.push(it);
      if (!flushTimer) { flushTimer = setTimeout(flush, BATCH_MS); }
    });
  }

  function settle(k, val, err) {
    var subs = pending[k] || [];
    delete pending[k];
    if (val && !err) {
      if (memoN >= MEMO_MAX) { memo = {}; memoN = 0; }
      memo[k] = val; memoN++;
    }
    for (var i = 0; i < subs.length; i++) {
      if (err) { subs[i].reject(err); } else { subs[i].resolve(val); }
    }
  }

  function sendChunk(items) {
    OMSFeed.loadToken().then(function (t) {
      return fetch("/excel/v1/calc", {
        method: "POST",
        headers: { "X-OMS-Token": t, "Content-Type": "application/json" },
        body: JSON.stringify({ items: items }),
        cache: "no-store"
      });
    }).then(function (r) {
      if (r.status === 401) { throw naError("Token de Excel inválido"); }
      if (!r.ok) { throw naError("HTTP " + r.status); }
      return r.json();
    }).then(function (data) {
      var res = (data && data.results) || [];
      for (var i = 0; i < items.length; i++) {
        settle(keyOf(items[i]), res[i] || { error: "sin resultado" }, null);
      }
    }).catch(function (e) {
      for (var j = 0; j < items.length; j++) { settle(keyOf(items[j]), null, e); }
    });
  }

  function flush() {
    flushTimer = null;
    var items = queue.splice(0, queue.length);
    while (items.length) { sendChunk(items.splice(0, CHUNK)); }
  }

  return { request: request };
})();

function calcItem(especie, modo, valor, plazo, nominales) {
  var code = String(especie == null ? "" : especie).trim().toUpperCase();
  if (!code) { throw naError("Especie vacía"); }
  var v = Number(valor);
  if (!isFinite(v)) { throw naError("Valor inválido: " + valor); }
  var it = { code: code, modo: modo, valor: v, plazo: normPlazo(plazo) };
  if (nominales != null && nominales !== "") { it.nominales = Number(nominales); }
  return it;
}

function calcField(it, campo) {
  return OMSCalc.request(it).then(function (m) {
    if (m.error) { throw naError(m.error); }
    var v = m[campo];
    if (v === undefined || v === null) { throw naError("Sin " + campo + " para " + it.code); }
    return v;
  });
}

function tireaFn(especie, precio, plazo) {
  return calcField(calcItem(especie, "precio", precio, plazo), "tirea");
}

function precioFn(especie, tir, plazo) {
  // TIR decimal (0,1388 = 13,88 %) → precio clean % del par, como el YAS.
  return calcField(calcItem(especie, "tir", tir, plazo), "precio_clean_pct");
}

function tnaFn(especie, precio, plazo) {
  return calcField(calcItem(especie, "precio", precio, plazo), "tna");
}

var CALC_MODOS = { "": "precio", "precio": "precio", "px": "precio",
                   "tir": "tir", "tirea": "tir", "tna": "tna", "margen": "margen" };

function calcFn(especie, campo, valor, modo, plazo) {
  var md = CALC_MODOS[String(modo == null ? "" : modo).trim().toLowerCase()];
  if (!md) { throw naError("Modo inválido: " + modo + " (precio | tir | tna | margen)"); }
  var c = String(campo == null ? "" : campo).trim().toLowerCase() || "tirea";
  return calcField(calcItem(especie, md, valor, plazo), c);
}

function ticketFn(especie, precio, nominales, plazo) {
  var nom = Number(nominales);
  if (!isFinite(nom) || nom <= 0) { throw naError("Nominales inválidos: " + nominales); }
  var it = calcItem(especie, "precio", precio, plazo, nom);
  return OMSCalc.request(it).then(function (m) {
    if (m.error) { throw naError(m.error); }
    return [["Concepto", "Valor"],
            ["Especie", m.codigo || it.code],
            ["VN", m.vn_ticket != null ? m.vn_ticket : nom],
            ["Monto total", m.monto_total != null ? m.monto_total : ""],
            ["Principal", m.principal != null ? m.principal : ""],
            ["Interés", m.interes != null ? m.interes : ""],
            ["TIREA", m.tirea != null ? m.tirea : ""],
            ["TNA (" + (m.tna_convention_label || "conv.") + ")", m.tna != null ? m.tna : ""],
            ["TEM", m.tem != null ? m.tem : ""],
            ["Duration", m.duration != null ? m.duration : ""],
            ["Liquidación", m.settle || ""]];
  });
}

function registerFunctions() {
  if (typeof CustomFunctions === "undefined") { return; }
  CustomFunctions.associate("QUOTE", makeStreaming(quoteGet));
  CustomFunctions.associate("FX", makeStreaming(fxGet));
  CustomFunctions.associate("ROFEX", makeStreaming(rofexGet));
  CustomFunctions.associate("CAUCION", makeStreaming(caucionGet));
  CustomFunctions.associate("TABLA", makeStreaming(tablaGet));
  CustomFunctions.associate("HIST", histFn);
  CustomFunctions.associate("TIREA", tireaFn);
  CustomFunctions.associate("PRECIO", precioFn);
  CustomFunctions.associate("TNA", tnaFn);
  CustomFunctions.associate("TICKET", ticketFn);
  CustomFunctions.associate("CALC", calcFn);
}

if (typeof Office !== "undefined" && Office.onReady) {
  Office.onReady(function () { registerFunctions(); });
} else {
  registerFunctions();
}
