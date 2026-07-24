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
          if (snap !== null && s === lastSeq) { status = "idle"; notify(); return null; }
          return fetch("/excel/v1/snapshot", { headers: headers(), cache: "no-store" })
            .then(function (r) {
              if (r.status === 401) { status = "auth"; notify(); return null; }
              if (!r.ok) { throw new Error("http " + r.status); }
              return r.json();
            })
            .then(function (data) {
              if (!data) { return null; }
              snap = data; lastSeq = data.seq; status = "live"; notify();
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
              "td": "td", "directo": "td", "dias": "dias", "vto": "vto",
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

function registerFunctions() {
  if (typeof CustomFunctions === "undefined") { return; }
  CustomFunctions.associate("QUOTE", makeStreaming(quoteGet));
  CustomFunctions.associate("FX", makeStreaming(fxGet));
  CustomFunctions.associate("ROFEX", makeStreaming(rofexGet));
  CustomFunctions.associate("CAUCION", makeStreaming(caucionGet));
  CustomFunctions.associate("TABLA", makeStreaming(tablaGet));
  CustomFunctions.associate("HIST", histFn);
}

if (typeof Office !== "undefined" && Office.onReady) {
  Office.onReady(function () { registerFunctions(); });
} else {
  registerFunctions();
}
