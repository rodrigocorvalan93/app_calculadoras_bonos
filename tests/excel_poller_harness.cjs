// Harness del poller del add-in de Excel: corre el functions.js REAL en un VM
// de Node con Office/fetch/reloj simulados (idea tomada de la auditoría
// externa, A19/A20). Lo invoca tests/test_excel_poller.py; imprime JSON.
//   1) seq quieto → igual baja el snapshot cada MAX_AGE (salud / MAE)
//   2) fetch que nunca resuelve → UN solo sondeo en vuelo, con timeout
//   3) errores seguidos → backoff (menos intentos que ticks)
//   4) flag "stale"/"down" en /seq → estado sin bajar snapshot
//   5) headers que llegan pero cuerpo que nunca termina → timeout igual, el
//      poller vuelve a sondear (antes quedaba "en vuelo" para siempre, R09)
//   6) el rescate one-shot también tiene plazo (y libera el single-flight)
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const source = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "excel", "functions.js"), "utf8");

function fixture(opts) {
  let now = 1_700_000_000_000;
  class FakeDate extends Date { static now() { return now; } }
  const timers = [];
  const state = { tick: null, seqCalls: 0, snapCalls: 0, pending: 0, seq: 42, flag: "", statuses: [] };
  const sandbox = {
    console, Promise, Math, JSON, Number, String, Array, Object, Error, Map, Set, RegExp,
    Date: FakeDate,
    AbortController: typeof AbortController !== "undefined" ? AbortController : undefined,
    setInterval(fn) { state.tick = fn; return 1; }, clearInterval() {},
    // Los timeouts del poller (≥ 1 s) se comprimen para no esperar de verdad.
    setTimeout(fn, ms) { const id = setTimeout(fn, ms >= 1000 ? 15 : ms); timers.push(id); return id; },
    clearTimeout,
    window: { location: { search: "?token=SYNTHETIC" }, localStorage: { getItem() { return "SYNTHETIC"; }, setItem() {} }, OMS_BEACON() {} },
    OfficeRuntime: { storage: { getItem() { return Promise.resolve("SYNTHETIC"); }, setItem() { return Promise.resolve(); } } },
    CustomFunctions: { associate() {}, Error: class extends Error {}, ErrorCode: {} },
    Office: { onReady() { return Promise.resolve({}); } },
    fetch(url) {
      if (opts.mode === "hang") { state.pending++; return new Promise(() => {}); }
      if (opts.mode === "fail") { state.pending++; return Promise.reject(new Error("red caída")); }
      if (opts.mode === "hang_body") {
        // headers OK, cuerpo que nunca llega (text()/json() no resuelven)
        if (url.indexOf("/seq") >= 0) { state.seqCalls++; } else { state.snapCalls++; }
        state.pending++;
        return Promise.resolve({ ok: true, status: 200, text: () => new Promise(() => {}), json: () => new Promise(() => {}) });
      }
      if (url.indexOf("/seq") >= 0) {
        state.seqCalls++;
        return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(String(state.seq) + (state.flag ? " " + state.flag : "")) });
      }
      state.snapCalls++;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ seq: state.seq, quotes: {}, health: null }) });
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  sandbox.OMSFeed.subscribe((_s, st) => state.statuses.push(st));
  return { sandbox, state, advance(ms) { now += ms; }, timers };
}
const flush = () => new Promise((r) => setTimeout(r, 30));

(async () => {
  const out = {};
  // 1) seq quieto 70 s: snapshot inicial + uno cada 30 s → ≥ 3
  {
    const f = fixture({ mode: "ok" });
    await flush();
    for (let i = 0; i < 70; i++) { f.state.tick(); f.advance(1000); await flush(); }
    out.seq_quieto = { seq_calls: f.state.seqCalls, snapshot_fetches: f.state.snapCalls,
                       ok: f.state.snapCalls >= 3 && f.state.snapCalls <= 5,
                       ultimo_estado: f.state.statuses[f.state.statuses.length - 1] };
  }
  // 2) fetch colgado: 21 ticks → 1 solo request en vuelo hasta el timeout
  {
    const f = fixture({ mode: "hang" });
    await flush();
    for (let i = 0; i < 20; i++) { f.state.tick(); await flush(); }
    // el timeout (comprimido) ya disparó → el poller vuelve a intentar con backoff
    out.fetch_colgado = { ticks: 21, requests: f.state.pending, ok: f.state.pending <= 3,
                          estado: f.state.statuses[f.state.statuses.length - 1] };
  }
  // 3) errores seguidos con reloj avanzando 1 s por tick → backoff exponencial
  {
    const f = fixture({ mode: "fail" });
    await flush();
    for (let i = 0; i < 40; i++) { f.state.tick(); f.advance(1000); await flush(); }
    out.errores = { ticks: 41, requests: f.state.pending, ok: f.state.pending <= 8,
                    estado: f.state.statuses[f.state.statuses.length - 1] };
  }
  // 4) flag en /seq: "stale" y "down" cambian el estado sin esperar snapshot
  {
    const f = fixture({ mode: "ok" });
    await flush();
    f.state.tick(); await flush();
    f.state.flag = "stale"; f.advance(1000); f.state.tick(); await flush();
    const stale = f.state.statuses[f.state.statuses.length - 1];
    f.state.flag = "down"; f.advance(1000); f.state.tick(); await flush();
    const down = f.state.statuses[f.state.statuses.length - 1];
    f.state.flag = ""; f.advance(1000); f.state.tick(); await flush();
    const idle = f.state.statuses[f.state.statuses.length - 1];
    out.flags = { stale, down, idle, snapshot_fetches: f.state.snapCalls,
                  ok: stale === "stale" && down === "down" && idle === "idle" && f.state.snapCalls === 1 };
  }
  // 5) cuerpo colgado (R09): el timeout (comprimido) dispara aunque los headers
  //    hayan llegado → estado "error", y con el reloj avanzando el poller
  //    vuelve a sondear (≥ 2 requests a /seq en 8 ticks). Antes: 1 solo request
  //    y nunca más (inflight pegado), sin estado de error.
  {
    const f = fixture({ mode: "hang_body" });
    await flush();
    for (let i = 0; i < 8; i++) { f.state.tick(); f.advance(1000); await flush(); await flush(); }
    out.cuerpo_colgado = { ticks: 9, seq_calls: f.state.seqCalls, requests: f.state.pending,
                           con_error: f.state.statuses.indexOf("error") >= 0,
                           ok: f.state.seqCalls >= 2 && f.state.pending <= 6 && f.state.statuses.indexOf("error") >= 0,
                           estado: f.state.statuses[f.state.statuses.length - 1] };
  }
  // 6) rescate one-shot con cuerpo colgado: resuelve null tras el plazo y
  //    libera el single-flight (el segundo rescate vuelve a pedir).
  {
    const f = fixture({ mode: "hang_body" });
    await flush();
    const antes = f.state.snapCalls;
    const d1 = await f.sandbox.OMSFeed.oneshot();
    const d2 = await f.sandbox.OMSFeed.oneshot();
    out.oneshot_colgado = { resultado: d1 === null && d2 === null, snapshot_fetches: f.state.snapCalls - antes,
                            ok: d1 === null && d2 === null && (f.state.snapCalls - antes) === 2 };
  }
  out.ok = Object.keys(out).every((k) => typeof out[k] !== "object" || out[k].ok);
  console.log(JSON.stringify(out, null, 1));
  process.exit(out.ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
