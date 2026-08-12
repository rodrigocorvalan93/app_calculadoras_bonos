/* Funciones custom del add-in OMS Bonos (runtime compartido con el taskpane).
 *
 * Motor: UNA sola conexión por libro — sondea /excel/v1/seq (entero plano)
 * cada 1 s y sólo cuando la secuencia avanzó baja /excel/v1/snapshot; todas
 * las celdas suscritas se actualizan en batch desde ese único snapshot. Mismo
 * patrón seq→refresh que la web (static/js/app.js). Vanilla JS, sin libs.
 */
/* global CustomFunctions, Office, OfficeRuntime, Excel */
"use strict";

// Sello de build: OMS.PING() lo devuelve. Sirve para confirmar que Excel cargó
// el functions.js ACTUAL y no una copia vieja cacheada (la causa #1 del #¡VALOR!
// que no se va con los reinstalar). Subir esta fecha en cada cambio del add-in.
var OMS_BUILD = "v11 · 2026-08-12 (HTTPS del runtime + beacons de diagnóstico)";

// Telemetría al log del server — SÓLO activa en functions.html, que define
// window.OMS_BEACON (el taskpane comparte este archivo pero no la define, así
// no mete ruido: al panel se lo ve a ojo; al runtime de funciones headless
// sólo se lo ve por estas líneas en el log). Jamás tira.
function _beacon(st, d) {
  try {
    if (typeof window !== "undefined" && window.OMS_BEACON) { window.OMS_BEACON(st, d); }
  } catch (e) { /* noop */ }
}

// ── Motor de datos compartido ────────────────────────────────────────────────
var OMSFeed = (function () {
  var POLL_MS = 1000;
  var token = "";
  var snap = null;        // último snapshot completo
  var lastSeq = null;
  var timer = null;
  var status = "off";     // off | live | idle | auth | error
  var sinks = [];         // callbacks (celdas + taskpane)
  var lastErr = "";       // detalle del último error de red (para el beacon)
  var beaconed = {};      // estados ya reportados (1 beacon por estado y vida)

  function getTokenSync() { return token; }

  // Token embebido en la URL de la página (functions.html?token=… del manifest
  // per-usuario). Es la fuente MÁS confiable en el modelo clásico: el runtime
  // de funciones es SEPARADO del panel, y OfficeRuntime.storage no siempre le
  // comparte el token → sin esto, todas las celdas dan 401/#N/D aunque el panel
  // esté conectado. La URL lo tiene siempre, sin depender de storage compartido.
  var _urlToken = null;
  function urlToken() {
    if (_urlToken !== null) { return _urlToken; }
    _urlToken = "";
    try {
      var m = (window.location.search || "").match(/[?&]token=([^&]+)/);
      if (m) { _urlToken = decodeURIComponent(m[1]); }
    } catch (e) { /* noop */ }
    return _urlToken;
  }

  function loadToken() {
    return new Promise(function (resolve) {
      var done = false;
      function fin() { if (!done) { done = true; resolve(token); } }
      // 1) URL de la página (manifest per-usuario) — determinístico.
      var ut = urlToken();
      if (ut) { token = ut; fin(); return; }
      // 2) OfficeRuntime.storage (compartido cuando el build lo soporta).
      // 3) localStorage de fallback (mismo origen).
      function fromLS() {
        try { token = window.localStorage.getItem("oms_token") || token; } catch (e) { /* noop */ }
      }
      // OfficeRuntime.storage puede COLGARSE en algunas builds (la promise no
      // resuelve nunca) y como tick() espera loadToken(), eso frenaba TODO el
      // poll del feed sin error visible → tope de 1,5 s y seguimos con lo que
      // haya (URL / localStorage).
      var guard = setTimeout(function () { fromLS(); fin(); }, 1500);
      try {
        OfficeRuntime.storage.getItem("oms_token").then(function (t) {
          clearTimeout(guard);
          if (t) { token = t; } else { fromLS(); }
          fin();
        }, function () { clearTimeout(guard); fromLS(); fin(); });
      } catch (e) {
        clearTimeout(guard);
        fromLS();
        fin();
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
    // La PRIMERA vez que el feed pisa cada estado lo reporta al server (live/
    // idle/auth/error una vez por vida del runtime, no por tick): con eso el
    // log muestra si este runtime llegó a datos o dónde quedó trabado.
    if (!beaconed[status]) {
      beaconed[status] = 1;
      _beacon("feed-" + status,
              status === "error" ? lastErr : (lastSeq != null ? "seq " + lastSeq : ""));
    }
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
        .catch(function (e) {
          if (status !== "auth") { status = "error"; }
          lastErr = String((e && e.message) || e);
          notify();
        });
    });
  }

  function start() {
    if (!timer) { timer = setInterval(tick, POLL_MS); tick(); }
  }

  // Rescate one-shot: baja el snapshot por HTTP directo cuando una celda llegó
  // a su timeout sin datos (p. ej. el poller del runtime no arrancó — la causa
  // del #¡OCUPADO! eterno en algunas builds). Single-flight: N celdas en
  // timeout → 1 solo fetch; si funciona, inyecta el snapshot y notifica a
  // TODAS las suscripciones (el poller sigue reintentando por su lado).
  var _oneshot = null;
  function oneshot() {
    if (_oneshot) { return _oneshot; }
    _oneshot = loadToken().then(function () {
      if (!token) { status = "auth"; notify(); return null; }
      return fetch("/excel/v1/snapshot", { headers: headers(), cache: "no-store" })
        .then(function (r) {
          if (r.status === 401) { status = "auth"; notify(); return null; }
          if (!r.ok) { throw new Error("http " + r.status); }
          return r.json();
        })
        .then(function (data) {
          if (data) {
            snap = data; lastSeq = data.seq;
            status = (data.health && data.health.warn) ? "stale" : "live";
            notify();
          }
          return data;
        });
    }).catch(function () { return null; }).then(function (d) { _oneshot = null; return d; });
    return _oneshot;
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
           status: function () { return status; }, tick: tick, oneshot: oneshot };
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
var _celdaOkReportada = false;   // 1 beacon "celda-ok" por vida del runtime

function makeStreaming(nombre, getter) {
  return function () {
    var args = Array.prototype.slice.call(arguments);
    var invocation = args.pop();
    var lastPushed, got = false;
    // Si en 6 s no llegó ningún snapshot, ANTES de errorear se intenta un
    // snapshot one-shot por HTTP (si el poller del runtime no arrancó, esto
    // resuelve igual y alimenta a todas las celdas). Si tampoco, error LEGIBLE
    // con el motivo real — distinguiendo "runtime sin token" (manifest
    // universal instalado) de red/feed — en vez de #¡OCUPADO! eterno.
    var t = setTimeout(function () {
      if (got) { return; }
      _beacon("celda-timeout", nombre + "(" + String(args[0] == null ? "" : args[0]) +
              ") estado=" + OMSFeed.status());
      OMSFeed.oneshot().then(function (d) {
        if (got || d) { return; }          // la inyección ya resolvió via sink
        try {
          invocation.setResult(naError(!OMSFeed.getToken()
            ? "El runtime de funciones no tiene token: instalá el manifest “⬇ con token” de tu usuario desde /admin (el manifest universal no autentica las celdas en este Excel)"
            : "Sin datos del feed (estado: " + OMSFeed.status() + "). Revisá el token en " +
              "el panel OMS Bonos y que el servidor esté corriendo."));
        } catch (e) { /* noop */ }
      });
    }, 6000);
    var un = OMSFeed.subscribe(function (s, status) {
      var v;
      if (status === "auth") {
        v = naError(OMSFeed.getToken()
          ? "Token de Excel inválido o deshabilitado (revisá /admin o el panel OMS Bonos)"
          : "El runtime de funciones no tiene token: instalá el manifest “⬇ con token” de tu usuario desde /admin");
      } else if (!s) {
        return;                               // todavía sin primer snapshot
      } else {
        try { v = getter.apply(null, [s].concat(args)); }
        catch (e) { v = naError(String(e && e.message || e)); }
      }
      got = true;
      if (!_celdaOkReportada && typeof CustomFunctions !== "undefined" &&
          !(v instanceof CustomFunctions.Error)) {
        _celdaOkReportada = true;
        _beacon("celda-ok", nombre + "(" + String(args[0] == null ? "" : args[0]) + ")");
      }
      var key = JSON.stringify(v);
      if (key !== lastPushed) { lastPushed = key; invocation.setResult(v); }
    });
    invocation.onCanceled = function () { clearTimeout(t); if (un) { un(); } };
  };
}

// Las funciones de CÁLCULO son async CLÁSICAS: devuelven una Promise y Office
// espera el resultado. Es el MISMO camino (POST /excel/v1/calc) que el botón
// "Probar" del panel, que funciona siempre. El streaming quedó para los datos
// EN VIVO (QUOTE/TABLA/…): en algunas builds el runtime de funciones no logra
// sondear el feed y esas celdas quedan en #¡OCUPADO! — pero el cálculo puntual
// no depende del feed, sólo del POST, así que va por la vía confiable.
//
// `guard(fn)` sólo normaliza los throws SÍNCRONos (p. ej. calcItem valida y
// tira ValueError) a un CustomFunctions.Error → #N/A con motivo, en vez de
// #¡VALOR! sin mensaje. Los rechazos async ya salen como Error via calcField.
function guard(fn) {
  return function () {
    try {
      return Promise.resolve(fn.apply(null, arguments)).catch(function (e) {
        return Promise.reject(
          (typeof CustomFunctions !== "undefined" && e instanceof CustomFunctions.Error)
            ? e : naError(String((e && e.message) || e)));
      });
    } catch (e) {
      return Promise.reject(
        (typeof CustomFunctions !== "undefined" && e instanceof CustomFunctions.Error)
          ? e : naError(String((e && e.message) || e)));
    }
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
  var noMemo = {};         // keys "a precio de mercado": re-resolver en cada recálculo
  var pending = {};        // key → [{resolve, reject}]
  var queue = [];          // items únicos a mandar
  var flushTimer = null;

  function keyOf(it) {
    // El DÍA local va en la key: el server keyea su cache por fecha de
    // liquidación (que rueda con el día), pero este memo cortaba antes de
    // llegar al server → un libro abierto de ayer devolvía el TIREA de AYER
    // en cada F9 hasta recargar el add-in.
    return [it.code, it.modo, (it.valor == null ? "@mercado" : it.valor),
            it.plazo, it.settle || "", it.fx || "", it.nominales || "",
            it.tipo || "", it.tir_salida == null ? "" : it.tir_salida,
            it.fecha_salida || "", new Date().toDateString()].join("|");
  }

  function request(it) {
    var k = keyOf(it);
    // Sin precio explícito el server resuelve el last del MOMENTO: no se
    // memoiza (cada F9 re-pide); el dedup en vuelo del mismo tick sí corre.
    var live = (it.valor == null);
    if (!live && Object.prototype.hasOwnProperty.call(memo, k)) { return Promise.resolve(memo[k]); }
    return new Promise(function (resolve, reject) {
      if (pending[k]) { pending[k].push({ resolve: resolve, reject: reject }); return; }
      pending[k] = [{ resolve: resolve, reject: reject }];
      if (live) { noMemo[k] = 1; }
      queue.push(it);
      if (!flushTimer) { flushTimer = setTimeout(flush, BATCH_MS); }
    });
  }

  function settle(k, val, err) {
    var subs = pending[k] || [];
    delete pending[k];
    // `val.error` NO se memoiza: el server marca los errores como _nocache
    // (transitorios: índice sin cargar, warmup, sin precio de mercado) pero el
    // memo del cliente los retenía para SIEMPRE → celdas en #N/D permanente
    // hasta recargar el add-in, aunque el server ya estuviera sano.
    if (val && !err && !val.error && !noMemo[k]) {
      if (memoN >= MEMO_MAX) { memo = {}; memoN = 0; }
      memo[k] = val; memoN++;
    }
    delete noMemo[k];
    // Rechazar SIEMPRE con CustomFunctions.Error: un reject con Error pelado
    // (p.ej. TypeError "failed to fetch" con el server caído) Office lo pinta
    // #¡VALOR! sin mensaje; envuelto sale #N/A con el motivo visible.
    if (err && typeof CustomFunctions !== "undefined" &&
        !(err instanceof CustomFunctions.Error)) {
      err = naError(String((err && err.message) || err));
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

var FECHA_RE = /^\s*\d{1,2}\/\d{1,2}\/\d{2,4}\s*$/;

function calcItem(especie, modo, valor, plazo, nominales, fx) {
  var code = String(especie == null ? "" : especie).trim().toUpperCase();
  if (!code) { throw naError("Especie vacía"); }
  var it = { code: code, modo: modo };
  // Precio omitido (sólo modo precio): el server usa el last del mercado —
  // puntual, sin anidar QUOTE (streaming anidada da #¡VALOR! en Office).
  if (valor == null || valor === "") {
    if (modo !== "precio") { throw naError("Falta el valor (TIR/TNA no tienen default)"); }
  } else {
    var v = Number(valor);
    if (!isFinite(v)) { throw naError("Valor inválido: " + valor); }
    it.valor = v;
  }
  // El 3er argumento admite plazo (CI/24hs) O una fecha de liquidación
  // custom DD/MM/AAAA — mismo settle_custom que la ficha YAS.
  var p = String(plazo == null ? "" : plazo).trim();
  if (FECHA_RE.test(p)) { it.settle = p; it.plazo = "24hs"; }
  else { it.plazo = normPlazo(plazo); }
  if (nominales != null && nominales !== "") { it.nominales = Number(nominales); }
  if (fx != null && fx !== "") {
    var f = Number(fx);
    if (!isFinite(f) || f <= 0) { throw naError("FX inválido: " + fx); }
    it.fx = f;                           // FX custom, como en la ficha YAS
  }
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

function tireaFn(especie, precio, plazo, fx) {
  return calcField(calcItem(especie, "precio", precio, plazo, null, fx), "tirea");
}

function precioFn(especie, tir, plazo, fx) {
  // TIR decimal (0,1388 = 13,88 %) → precio clean % del par, como el YAS.
  return calcField(calcItem(especie, "tir", tir, plazo, null, fx), "precio_clean_pct");
}

function tnaFn(especie, precio, plazo, fx) {
  return calcField(calcItem(especie, "precio", precio, plazo, null, fx), "tna");
}

var CALC_MODOS = { "": "precio", "precio": "precio", "px": "precio",
                   "tir": "tir", "tirea": "tir", "tna": "tna", "margen": "margen" };

function calcFn(especie, campo, valor, modo, plazo, fx) {
  var md = CALC_MODOS[String(modo == null ? "" : modo).trim().toLowerCase()];
  if (!md) { throw naError("Modo inválido: " + modo + " (precio | tir | tna | margen)"); }
  var c = String(campo == null ? "" : campo).trim().toLowerCase() || "tirea";
  return calcField(calcItem(especie, md, valor, plazo, null, fx), c);
}

function trFn(especie, precio, tirSalida, fechaSalida, nominales, plazo, fx) {
  var it = calcItem(especie, "precio", precio, plazo, nominales, fx);
  it.tipo = "tr";
  if (tirSalida != null && tirSalida !== "") { it.tir_salida = Number(tirSalida); }
  var fs = String(fechaSalida == null ? "" : fechaSalida).trim();
  if (fs) {
    if (!FECHA_RE.test(fs)) { throw naError("Fecha de salida inválida: " + fechaSalida + " (DD/MM/AAAA)"); }
    it.fecha_salida = fs;
  }
  return OMSCalc.request(it).then(function (m) {
    if (m.error) { throw naError(m.error); }
    var nn = function (v) { return v != null ? v : ""; };
    return [["Concepto", "Valor"],
            ["Especie", m.codigo || it.code],
            ["Entrada (settle)", nn(m.fecha_entrada)],
            ["Salida", nn(m.fecha_salida) + (m.a_vencimiento ? " (a vencimiento)" : "")],
            ["Días", nn(m.dias)],
            ["TIR entrada", nn(m.tir_entrada)],
            ["TIR salida", nn(m.tir_salida) + (m.salida_flat ? "" : "")],
            ["Px inicial %", nn(m.px_ini_pct)],
            ["Px final %", nn(m.px_fin_pct)],
            ["P&L capital %", nn(m.pnl_capital_pct)],
            ["Cobrado %", nn(m.cobrado_pct)],
            ["TR directo", nn(m.tr)],
            ["TEA", nn(m.tea)],
            ["TNA", nn(m.tna)],
            ["P&L total $", nn(m.pnl_total_m)]];
  });
}

function ticketFn(especie, precio, nominales, plazo, fx) {
  // nominales opcional: default 1.000.000 VN, el mismo del ticket del YAS.
  var nom = (nominales == null || nominales === "") ? 1000000 : Number(nominales);
  if (!isFinite(nom) || nom <= 0) { throw naError("Nominales inválidos: " + nominales); }
  var it = calcItem(especie, "precio", precio, plazo, nom, fx);
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

// ── Diagnóstico (para cazar el #¡VALOR!) ─────────────────────────────────────
// PING: función SÍNCRONA, sin server, sin async → si esto no devuelve el texto,
// el problema es de carga/registro del add-in (metadata o JS cacheados), NO del
// cálculo. Confirma además QUÉ build cargó Excel.
function pingFn() { return "OMS Bonos " + OMS_BUILD; }

// DIAG: mismo camino de cálculo que TIREA pero devuelve TEXTO (nunca #¡VALOR!):
// el resultado, o el motivo del error, visible en la celda. Async "clásica"
// (devuelve la Promise, sin el canal streaming) → también sirve para comparar:
// si DIAG funciona y TIREA no, el problema es el mecanismo streaming en tu build.
function diagFn(especie, precio, plazo, fx) {
  try {
    var it = calcItem(especie, "precio", precio, plazo, null, fx);
    return OMSCalc.request(it).then(function (m) {
      if (m && m.error) { return "ERROR: " + m.error; }
      return "OK tirea=" + (m && m.tirea) + " tna=" + (m && m.tna) +
             " tem=" + (m && m.tem) + " dur=" + (m && m.duration);
    }, function (e) {
      return "REJECT: " + ((e && (e.message || e.code)) || e);
    });
  } catch (e) {
    return "THROW: " + ((e && e.message) || e);
  }
}

function registerFunctions() {
  if (typeof CustomFunctions === "undefined") {
    _beacon("sin-customfunctions", "en registerFunctions (runtime sin soporte de funciones)");
    return;
  }
  CustomFunctions.associate("PING", pingFn);
  CustomFunctions.associate("DIAG", diagFn);
  CustomFunctions.associate("QUOTE", makeStreaming("QUOTE", quoteGet));
  CustomFunctions.associate("FX", makeStreaming("FX", fxGet));
  CustomFunctions.associate("ROFEX", makeStreaming("ROFEX", rofexGet));
  CustomFunctions.associate("CAUCION", makeStreaming("CAUCION", caucionGet));
  CustomFunctions.associate("TABLA", makeStreaming("TABLA", tablaGet));
  CustomFunctions.associate("HIST", histFn);
  CustomFunctions.associate("TIREA", guard(tireaFn));
  CustomFunctions.associate("PRECIO", guard(precioFn));
  CustomFunctions.associate("TNA", guard(tnaFn));
  CustomFunctions.associate("TICKET", guard(ticketFn));
  CustomFunctions.associate("CALC", guard(calcFn));
  CustomFunctions.associate("TR", guard(trFn));
  // Marca para el watchdog de functions.html + confirmación en el log de QUÉ
  // build registró (si esta línea no aparece, el runtime murió antes).
  try { if (typeof window !== "undefined") { window.OMS_REGISTRADO = true; } } catch (e) { /* noop */ }
  _beacon("funciones-registradas", OMS_BUILD);
}

if (typeof Office !== "undefined" && Office.onReady) {
  Office.onReady(function () { _beacon("office-ready"); registerFunctions(); });
} else {
  _beacon("sin-office", "office.js no está — registro directo");
  registerFunctions();
}
