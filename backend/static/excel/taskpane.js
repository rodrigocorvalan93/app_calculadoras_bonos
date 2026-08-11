/* Taskpane del add-in OMS Bonos: token, estado del feed y modo hoja CRUDA.
 * Modelo CLÁSICO: las funciones custom corren en su propio runtime
 * (functions.html); el panel es un runtime aparte. Ambos cargan functions.js
 * (cada uno su OMSFeed) y comparten el token vía OfficeRuntime.storage, así
 * guardar el token acá reconecta las celdas en ~1 s (el poll siguiente). */
/* global Office, Excel, OMSFeed */
"use strict";

(function () {
  var $ = function (id) { return document.getElementById(id); };

  var STATUS_LABEL = { off: "sin conexión", live: "en vivo", idle: "sin ticks",
                       stale: "⚠ conectado pero SIN market data — precios posiblemente viejos",
                       auth: "token inválido / falta token", error: "error de red" };

  function paintStatus(_snap, status) {
    $("dot").className = "dot " + status;
    $("status").textContent = STATUS_LABEL[status] || status;
  }

  function init() {
    OMSFeed.loadToken().then(function (t) { if (t) { $("token").value = t; } });
    OMSFeed.subscribe(paintStatus);

    // Diagnóstico multi-máquina: el add-in pega SIEMPRE contra el host del
    // manifest con el que se instaló. Mostrarlo evita adivinar por qué en una
    // compu anda y en otra no (nombre que no resuelve, cert no confiado, etc.).
    try {
      $("server-line").textContent = "Servidor del complemento: " + window.location.origin +
        " (definido por el manifest instalado en ESTA máquina)";
    } catch (e) { /* noop */ }

    $("save").onclick = function () {
      OMSFeed.setToken($("token").value);
      $("test-result").textContent = "Token guardado.";
    };

    $("test").onclick = function () {
      $("test-result").textContent = "Probando…";
      OMSFeed.loadToken().then(function (t) {
        return fetch("/excel/v1/ping", { headers: { "X-OMS-Token": t }, cache: "no-store" });
      }).then(function (r) {
        if (r.status === 401) { throw new Error("token inválido o deshabilitado"); }
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      }).then(function (d) {
        var quien = d.user || "?";
        // 2º paso: probar la CALCULADORA (POST /excel/v1/calc). Aísla "server
        // viejo sin el endpoint" vs "runtime de Excel roto": si acá da OK y la
        // celda sigue en #¡VALOR!, el problema es la caché Wef del add-in.
        return OMSFeed.loadToken().then(function (t) {
          return fetch("/excel/v1/calc", {
            method: "POST", cache: "no-store",
            headers: { "X-OMS-Token": t, "Content-Type": "application/json" },
            body: JSON.stringify({ items: [{ code: "GD30", modo: "precio", valor: 78.5 }] })
          });
        }).then(function (r) {
          if (r.status === 404) {
            throw new Error("conectado como " + quien + ", pero este server NO tiene " +
                            "/excel/v1/calc — falta git pull + reiniciar el .bat");
          }
          if (!r.ok) { throw new Error("conectado como " + quien + ", calc HTTP " + r.status); }
          return r.json();
        }).then(function (dd) {
          var x = (dd.results && dd.results[0]) || {};
          if (x.tirea != null) {
            $("test-result").innerHTML = '<span class="ok">Conectado como ' + quien +
              ' · calculadora OK (TIREA GD30@78,5 = ' +
              (x.tirea * 100).toFixed(2).replace(".", ",") + '%)</span>';
          } else {
            $("test-result").innerHTML = '<span class="err">Conectado como ' + quien +
              ' pero el calc devolvió: ' + (x.error || "sin dato") + '</span>';
          }
        });
      }).catch(function (e) {
        // "Failed to fetch" = no se llegó al server (nombre que no resuelve
        // desde esta máquina, firewall, notebook suspendida o certificado no
        // confiado — WebView2 no tiene el "continuar de todos modos" del
        // navegador). Distinto de token inválido (401).
        var red = /fetch|network|load/i.test(e.message || "");
        $("test-result").innerHTML = '<span class="err">Sin conexión: ' + e.message +
          (red ? ' — no se llegó a ' + window.location.origin +
                 ' desde esta máquina (probá abrir ' + window.location.origin +
                 '/healthz en el navegador acá mismo; si no responde es red/DNS/cert, no el add-in)'
               : '') + '</span>';
      });
    };

    // ── Modo hoja CRUDA ─────────────────────────────────────────────────────
    var crudaOn = false, crudaPrevRows = 0, crudaLastSeq = null, crudaBusy = false;

    function buildCruda(s) {
      var rows = [["KEY", "LAST", "BID", "ASK", "BID_SIZE", "ASK_SIZE", "CLOSE",
                   "CLOSE_DATE", "VAR", "VOL", "NOMINAL", "VWAP", "TNA", "TEM"]];
      var nn = function (v) { return v == null ? "" : v; };
      var codes = Object.keys(s.quotes || {}).sort(), i, j, r;
      for (i = 0; i < codes.length; i++) {
        var byPlazo = s.quotes[codes[i]], plazos = Object.keys(byPlazo);
        for (j = 0; j < plazos.length; j++) {
          r = byPlazo[plazos[j]];
          rows.push([codes[i] + "|" + plazos[j], nn(r.last), nn(r.bid), nn(r.ask),
                     nn(r.bid_size), nn(r.ask_size), nn(r.close), nn(r.close_date),
                     nn(r.var), nn(r.vol), nn(r.nominal), nn(r.vwap), "", ""]);
        }
      }
      var fx = s.fx || {}, may = s.mayorista || {};
      rows.push(["FX|MEP", nn(fx.mep), "", "", "", "", "", "", "", "", "", "", "", ""]);
      rows.push(["FX|CCL", nn(fx.ccl), "", "", "", "", "", "", "", "", "", "", "", ""]);
      rows.push(["FX|CANJE", nn(fx.canje), "", "", "", "", "", "", "", "", "", "", "", ""]);
      rows.push(["FX|MAYORISTA", nn(may.last), nn(may.bid), nn(may.offer), "", "",
                 nn(may.close), nn(may.date), nn(may.var_pct), nn(may.volume), "", "", "", ""]);
      var canales = ["may", "min"];
      for (i = 0; i < canales.length; i++) {
        var futs = (s.futuros || {})[canales[i]] || [];
        for (j = 0; j < futs.length; j++) {
          r = futs[j];
          rows.push(["FUT|" + r.code, nn(r.last), nn(r.bid), nn(r.offer), "", "",
                     nn(r.close), nn(r.vto), nn(r.var_pct), nn(r.volume), "", "",
                     nn(r.tna), nn(r.tem)]);
        }
      }
      var mons = ["ARS", "USD"];
      for (i = 0; i < mons.length; i++) {
        var caus = (s.cauciones || {})[mons[i]] || [];
        for (j = 0; j < caus.length; j++) {
          r = caus[j];
          rows.push(["CAU|" + mons[i] + "|" + r.plazo, nn(r.tasa), nn(r.bid), nn(r.offer),
                     "", "", nn(r.close), "", nn(r.var), nn(r.volumen), "", "", "", ""]);
        }
      }
      var mae = s.mae || {}, ks = Object.keys(mae).sort();
      for (i = 0; i < ks.length; i++) {
        r = mae[ks[i]];
        if (!r) { continue; }
        rows.push(["MAE|" + ks[i], nn(r.last), "", "", "", "", nn(r.close), "",
                   nn(r.var_pct), nn(r.monto), nn(r.volumen), "", "", ""]);
      }
      return rows;
    }

    function crudaTick(s) {
      if (!crudaOn || crudaBusy || !s || s.seq === crudaLastSeq) { return; }
      crudaBusy = true;
      var rows = buildCruda(s);
      Excel.run(function (ctx) {
        var sheets = ctx.workbook.worksheets;
        var sh = sheets.getItemOrNullObject("OMS_DATA");
        return ctx.sync().then(function () {
          if (sh.isNullObject) { sh = sheets.add("OMS_DATA"); }
          var width = rows[0].length;
          sh.getRangeByIndexes(0, 0, rows.length, width).values = rows;
          if (crudaPrevRows > rows.length) {
            sh.getRangeByIndexes(rows.length, 0, crudaPrevRows - rows.length, width)
              .clear(Excel.ClearApplyTo.contents);
          }
          crudaPrevRows = rows.length;
          return ctx.sync();
        });
      }).then(function () {
        crudaLastSeq = s.seq;
        $("cruda-status").textContent = "OMS_DATA · " + (rows.length - 1) + " filas · seq " + s.seq;
      }).catch(function (e) {
        $("cruda-status").textContent = "error: " + (e && e.message || e);
      }).then(function () { crudaBusy = false; });
    }

    OMSFeed.subscribe(function (s) { crudaTick(s); });

    $("cruda").onclick = function () {
      crudaOn = !crudaOn;
      $("cruda").textContent = crudaOn ? "Desactivar" : "Activar";
      $("cruda-status").textContent = crudaOn ? "activado — esperando tick…" : "";
      if (crudaOn) { crudaLastSeq = null; crudaTick(OMSFeed.snapshot()); }
    };
  }

  if (typeof Office !== "undefined" && Office.onReady) {
    Office.onReady(function () { init(); });
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
