// Harness del motor live de la web (static/js/app.js) y de los loaders de
// gráficos (static/js/charts.js): corre el JS REAL en un VM de Node con
// reloj virtual y red simulada (idea tomada de la auditoría de eficiencia,
// E03/E05). Lo invoca tests/test_auditoria_eficiencia.py; imprime JSON.
//   1) delta cuyo fetch / cuerpo nunca vuelve → el plazo lo corta, el panel
//      pide el swap completo y sigue pidiendo deltas (antes: 1 fetch y nunca más)
//   2) fallback de polling con la red colgada → un solo sondeo en vuelo, con
//      plazo y backoff (antes: un request pendiente nuevo por segundo)
//   3) respuestas de seq en orden → un solo md-update por avance real
//   4) controles: dos deltas sanos seguidos = dos fetches; pestaña oculta = 0 requests
//   5) históricos macro: la respuesta de la selección ANTERIOR que llega
//      después no pisa el gráfico de la vigente
//   6) salud sin seq nueva: /market/health que pasa a feed_down con el mercado
//      quieto → el dot pasa a 'down' sin esperar otra seq, y vuelve;
//      connecting:true NO es caída ('idle' + "Conectando al broker…")
//   7) health colgado: a los 6 s se aborta y el estado no queda pegado — el
//      health siguiente se aplica y la respuesta vieja que llega tarde se ignora
//   8) EventSource que nunca abre (CONNECTING eterno) → a los 8 s se cierra, el
//      dot avisa ('off') y arranca el polling (antes: pestaña muda para siempre)
//   9) control SSE sano: el watchdog no lo toca, cero polls, un md-update por
//      mensaje nuevo, y live → idle a los 20 s SIN otra seq (timer de estado)
//  10) pestaña oculta: arm() no abre SSE ni health; un mensaje que entra en la
//      carrera con el visibilitychange no dispara md-update; el guard de
//      htmx:beforeRequest cancela los requests por md-update (no un click)
//  11) htmx.config.timeout = 30 s (antes 0: un XHR colgado no avisaba nunca)
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const appJs = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "app.js"), "utf8");
const chartsJs = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "js", "charts.js"), "utf8");

// Motor live: desde el IIFE que arranca con "// htmx custom" hasta el bloque
// de orden por columna (mismos marcadores que usó la auditoría).
const marca = appJs.indexOf("// htmx custom");
const begin = appJs.lastIndexOf("(function () {", marca);
const end = appJs.indexOf("// ── Orden por columna", begin);
if (marca < 0 || begin < 0 || end < 0) { throw new Error("No encuentro el motor live en app.js"); }
const liveCode = appJs.slice(begin, end);

// opts: { hidden: pestaña oculta al cargar, sse: "hang" (nunca abre) | "ok"
// (abre a los 100 ms y manda la seq 5), health: "hang_first" (el PRIMER
// /market/health nunca vuelve; se resuelve a mano con healthPend[0](json)) }
function env(mode, opts) {
  opts = opts || {};
  let now = 100000, id = 0;
  const calls = [], timers = new Map(), pending = [], events = [], aborts = [], dotHist = [], sses = [], healthPend = [];
  const health = { feed_down: false };                   // lo que contesta /market/health (mutable desde el caso)
  // el dot graba cada cambio de estado / título con la hora virtual
  const dotState = { s: undefined, t: "" };
  const dot = {
    dataset: {}, classList: { add() {}, remove() {} },
    get title() { return dotState.t; }, set title(v) { dotState.t = v; dotHist.push({ kind: "title", v, at: now }); },
  };
  Object.defineProperty(dot.dataset, "state", {
    get() { return dotState.s; }, set(v) { dotState.s = v; dotHist.push({ kind: "state", v, at: now }); }, enumerable: true,
  });
  const handlers = {};
  let tbl = { getAttribute(k) { return { "data-delta": "/mercado/rows?curve=globales", "data-seq": "1", "data-order": "same" }[k]; }, setAttribute() {} };
  const scope = { id: "market-scope", querySelector() { return tbl; } };
  const document = {
    hidden: !!opts.hidden, readyState: "complete",
    body: { addEventListener(n, f) { handlers[n] = f; } },
    addEventListener(n, f) { handlers[n] = f; },
    getElementById(n) { return n === "live-dot" ? dot : null; },
    querySelectorAll() { return [scope]; },
  };
  function fetch(url, o) {
    calls.push({ url, at: now });
    if (o && o.signal) { o.signal.url = url; }               // el abort sabe a qué request pertenece
    if (url === "/market/health") {
      const nth = calls.filter((c) => c.url === "/market/health").length;
      if (opts.health === "hang_first" && nth === 1) {
        return new Promise((resolve) => healthPend.push((h) => resolve({ text: async () => JSON.stringify(h) })));
      }
      return Promise.resolve({ text: async () => JSON.stringify(health) });
    }
    if (url.startsWith("/mercado/rows")) {
      if (mode === "delta_body") { return Promise.resolve({ text: () => new Promise(() => {}), ok: true, headers: { get: () => null } }); }
      if (mode === "delta_fetch") { return new Promise(() => {}); }
      return Promise.resolve({ text: async () => "", ok: true, headers: { get: (k) => (k === "X-Seq" ? "2" : null) } });
    }
    if (mode === "poll_hang") { return new Promise(() => {}); }
    if (mode === "poll_manual") { return new Promise((resolve) => pending.push((v) => resolve({ text: async () => String(v) }))); }
    return Promise.resolve({ text: async () => "1" });
  }
  function vSetTimeout(f, ms) { const k = ++id; timers.set(k, { f, ms, next: now + ms }); return k; }
  // EventSource simulado: "hang" nunca llama onopen/onmessage (readyState 0
  // para siempre); "ok" abre a los 100 ms y manda la seq 5 como baseline.
  class EventSourceMock {
    constructor(url) {
      this.url = url; this.readyState = 0; this.closed = false; sses.push(this);
      if (opts.sse === "ok") {
        vSetTimeout(() => {
          if (this.closed) { return; }
          this.readyState = 1;
          if (this.onopen) { this.onopen({}); }
          if (this.onmessage) { this.onmessage({ data: "5" }); }
        }, 100);
      }
    }
    close() { this.closed = true; this.readyState = 2; }
  }
  const window = {
    localStorage: { getItem: () => null }, matchMedia: () => ({ matches: false }),
    htmx: { config: {}, trigger: (target, name) => events.push({ name, at: now }), process() {} },
    requestAnimationFrame: (f) => f(),
  };
  if (opts.sse) { window.EventSource = EventSourceMock; }
  const context = {
    window, document, fetch, performance: { now: () => now },
    Date: class extends Date { static now() { return now; } }, console, Promise, Math, parseInt, isNaN, String, Number, Error, JSON,
    AbortController: class { constructor() { this.signal = {}; } abort() { aborts.push({ url: this.signal.url, at: now }); } },
    setInterval(f, ms) { const k = ++id; timers.set(k, { f, ms, next: now + ms, repeat: true }); return k; },
    setTimeout: vSetTimeout,
    clearInterval(k) { timers.delete(k); }, clearTimeout(k) { timers.delete(k); },
  };
  if (opts.sse) { context.EventSource = EventSourceMock; }   // el motor chequea window.EventSource y construye el global
  vm.runInNewContext(liveCode, context, { filename: "app.js:live-engine" });
  async function flush() { for (let i = 0; i < 12; i++) { await Promise.resolve(); } }
  async function advance(ms) {
    const target = now + ms;
    for (;;) {
      const next = [...timers].filter(([, t]) => t.next <= target).sort((a, b) => a[1].next - b[1].next)[0];
      if (!next) { break; }
      now = next[1].next;
      if (next[1].repeat) { next[1].next += next[1].ms; } else { timers.delete(next[0]); }
      next[1].f();
      await flush();
    }
    now = target;
    await flush();
  }
  const t0 = now;
  return { calls, events, pending, dot, dotHist, handlers, document, window, scope, health, healthPend, aborts, sses, t0,
           advance, flush, replaceTable() { tbl = { ...tbl }; },
           seqs() { return calls.filter((x) => x.url === "/market/seq").length; },
           healths() { return calls.filter((x) => x.url === "/market/health").length; },
           updates() { return events.filter((x) => x.name === "md-update").length; } };
}

(async () => {
  const out = {};
  // 1) delta colgado (fetch que nunca resuelve / cuerpo que nunca llega)
  for (const mode of ["delta_fetch", "delta_body"]) {
    const e = env(mode);
    await e.flush();
    e.window.__mercadoDelta.tick(e.scope);
    await e.flush();
    for (let i = 0; i < 120; i++) { await e.advance(1000); if (i === 30) { e.replaceTable(); } e.window.__mercadoDelta.tick(e.scope); }
    const fetches = e.calls.filter((x) => x.url.startsWith("/mercado/rows")).length;
    const refresh = e.events.filter((x) => x.name === "refresh").length;
    out[mode] = { ticks: 121, delta_fetches: fetches, full_refresh_events: refresh,
                  ok: fetches >= 5 && refresh >= 5 };          // ~1 intento cada 8 s (plazo), no 1 y nunca más
  }
  // 2) fallback de polling con la red colgada: plazo + backoff, un solo request en vuelo
  {
    const e = env("poll_hang");
    await e.advance(120000);
    const seqs = e.calls.filter((x) => x.url === "/market/seq").length;
    out.fallback_poll_colgado = { seq_requests: seqs, dot_state: e.dot.dataset.state || null,
                                  ok: seqs >= 2 && seqs <= 12 && e.dot.dataset.state === "off" };
  }
  // 3) un solo sondeo en vuelo: mientras el primero no vuelve, los intervalos
  //    siguientes NO disparan otro (antes: uno nuevo por segundo y respuestas
  //    cruzadas); resueltos en orden 10 → 12 → 12 = un solo md-update.
  {
    const e = env("poll_manual");
    await e.flush();
    const seqs = () => e.calls.filter((x) => x.url === "/market/seq").length;
    const primero = seqs();
    await e.advance(1000); await e.advance(1000);
    const sinResolver = seqs();                          // sigue siendo 1: el anterior no volvió
    e.pending[0](10); await e.flush();
    await e.advance(1000); e.pending[1](12); await e.flush();
    await e.advance(1000); e.pending[2](12); await e.flush();
    const updates = e.events.filter((x) => x.name === "md-update").length;
    out.seq_en_orden = { llegadas: [10, 12, 12], md_updates: updates, requests_con_uno_colgado: sinResolver,
                         ok: updates === 1 && primero === 1 && sinResolver === 1 && seqs() === 3 };
  }
  // 4) controles
  {
    const e = env("ok");
    await e.flush();
    e.window.__mercadoDelta.tick(e.scope); await e.flush();
    e.window.__mercadoDelta.tick(e.scope); await e.flush();
    const sanos = e.calls.filter((x) => x.url.startsWith("/mercado/rows")).length;
    e.document.hidden = true; e.handlers.visibilitychange();
    const antes = e.calls.length;
    await e.advance(10000);
    out.controles = { deltas_sanos: sanos, requests_oculto: e.calls.length - antes,
                      ok: sanos === 2 && e.calls.length - antes === 0 };
  }
  // 5) históricos macro: respuesta vieja después de la nueva
  {
    const p = chartsJs.indexOf('fetch("/historicos/data?"');
    const start = chartsJs.lastIndexOf("var hmGen = 0;", p);
    const stop = chartsJs.indexOf("\n    load();", p);
    if (p < 0 || start < 0 || stop < 0) { throw new Error("No encuentro load() de históricos macro en charts.js"); }
    const pend = [], shown = [];
    let selected = "CER";
    const ctx = { ctrls: {}, lastJ: null, paramsOf: () => "serie=" + selected,
                  fetch: (url) => new Promise((resolve) => pend.push({ url, resolve })),
                  draw() { shown.push(ctx.lastJ.label); }, renderDatos() {} };
    vm.runInNewContext(chartsJs.slice(start, stop), ctx, { filename: "charts.js:hist-macro-load" });
    ctx.load(); selected = "TAMAR"; ctx.load();
    pend[1].resolve({ json: async () => ({ label: "TAMAR" }) }); for (let i = 0; i < 8; i++) { await Promise.resolve(); }
    pend[0].resolve({ json: async () => ({ label: "CER" }) }); for (let i = 0; i < 8; i++) { await Promise.resolve(); }
    out.historico_orden = { pedidos: pend.map((x) => x.url), mostrados: shown, seleccion: selected,
                            ok: shown.length === 1 && shown[0] === "TAMAR" };
  }
  // 6) salud con el stream mudo (SSE abre, manda la baseline 5 y se calla: no
  //    hay handleSeq que re-renderice): feed_down se pinta 'down' EN el health
  //    — el inmediato del re-arm (ocultar y mostrar a los 2 s, instante en el
  //    que no vence ningún timer) — sin esperar otra seq ni el timer de 5 s;
  //    vuelve a 'idle' con el health periódico; connecting → 'idle' +
  //    "Conectando al broker…", nunca 'down'. Antes (polling o no) el dot sólo
  //    se tocaba en handleSeq: con el mercado parado no cambiaba jamás.
  {
    const e = env("ok", { sse: "ok" });
    await e.flush(); await e.advance(100);               // onopen + baseline "5" → 'idle'
    const inicial = e.dot.dataset.state;
    await e.advance(1900);
    e.health.feed_down = true;
    e.document.hidden = true; e.handlers.visibilitychange();
    e.document.hidden = false; e.handlers.visibilitychange(); await e.flush();   // re-arm → health inmediato
    const caido = e.dot.dataset.state;
    const caidoAt = (e.dotHist.find((h) => h.kind === "state" && h.v === "down") || {}).at;
    e.health.feed_down = false;
    await e.advance(15100);                              // health periódico (t = 17 s) con el stream mudo
    const vuelve = e.dot.dataset.state;
    e.health.feed_down = true; e.health.connecting = true; // sesión recién abierta: WS en handshake
    await e.advance(15000);
    const conectando = { state: e.dot.dataset.state, title: e.dot.title };
    delete e.health.connecting; e.health.feed_down = false;
    await e.advance(15000);
    out.health_sin_seq = { inicial, caido, caido_a_los_ms: caidoAt - e.t0, vuelve, conectando, md_updates: e.updates(),
                           final: e.dot.dataset.state, polls: e.seqs(), eventsources: e.sses.length,
                           ok: inicial === "idle" && caido === "down" && caidoAt - e.t0 === 2000 && vuelve === "idle" &&
                               conectando.state === "idle" && /Conectando al broker/.test(conectando.title) &&
                               e.updates() === 0 && e.dot.dataset.state === "idle" && e.seqs() === 0 && e.sses.length === 2 };
  }
  // 7) health colgado: el primer /market/health nunca vuelve → abort a los 6 s;
  //    el siguiente (15 s) se aplica igual (feed_down → 'down'), el que sigue lo
  //    levanta, y la respuesta VIEJA que llega al final no pisa el estado.
  {
    const e = env("ok", { health: "hang_first" });
    await e.flush();
    await e.advance(7000);
    const abortados = e.aborts.filter((a) => a.url === "/market/health");
    e.health.feed_down = true;
    await e.advance(10000);                              // t = 17 s: 2º health → 'down'
    const caido = e.dot.dataset.state;
    e.health.feed_down = false;
    await e.advance(15000);                              // 3º health → 'idle'
    const levantado = e.dot.dataset.state;
    e.healthPend[0]({ feed_down: true }); await e.flush();   // la vieja llega 32 s tarde: ignorada
    const tarde = e.dot.dataset.state;
    out.health_colgado = { abortados: abortados.length, abort_a_los_ms: abortados.length ? abortados[0].at - e.t0 : null,
                           healths: e.healths(), caido, levantado, tarde,
                           ok: abortados.length === 1 && abortados[0].at - e.t0 === 6000 && e.healths() >= 3 &&
                               caido === "down" && levantado === "idle" && tarde === "idle" };
  }
  // 8) EventSource en CONNECTING para siempre (pool HTTP/1.1 lleno, proxy que
  //    no streamea): nada de onopen/onerror → a los 8 s se cierra, dot 'off'
  //    "Sin stream del feed — sondeando" y arranca el polling de /market/seq.
  {
    const e = env("ok", { sse: "hang" });
    await e.flush();
    await e.advance(7900);
    const seqAntes = e.seqs(), abiertos = e.sses.length, cerradoAntes = e.sses[0] && e.sses[0].closed;
    await e.advance(200);                                // t = 8,1 s: watchdog
    const cerrado = e.sses[0].closed;
    const off = e.dotHist.find((h) => h.kind === "state" && h.v === "off");
    const offTitle = e.dotHist.find((h) => h.kind === "title" && /Sin stream del feed/.test(h.v));
    await e.advance(3000);
    out.sse_colgado = { eventsources: abiertos, seq_antes: seqAntes, cerrado_antes: !!cerradoAntes, cerrado,
                        off_a_los_ms: off ? off.at - e.t0 : null, aviso: !!offTitle, seq_despues: e.seqs(), final: e.dot.dataset.state,
                        ok: abiertos === 1 && seqAntes === 0 && !cerradoAntes && cerrado && off && off.at - e.t0 === 8000 &&
                            !!offTitle && e.seqs() >= 3 && e.dot.dataset.state === "idle" };
  }
  // 9) control: SSE sano → el watchdog no lo toca, cero polls, un md-update por
  //    mensaje nuevo, y 'live' → 'idle' a los 20 s de quietud SIN otra seq.
  {
    const e = env("ok", { sse: "ok" });
    await e.flush(); await e.advance(100);               // onopen + baseline "5"
    e.sses[0].onmessage({ data: "6" }); await e.flush();
    const vivo = e.dot.dataset.state, updates = e.updates();
    await e.advance(26000);                              // timer de estado (5 s): quieto > 20 s
    const quieto = e.dot.dataset.state;
    out.sse_sano = { eventsources: e.sses.length, cerrado: e.sses[0].closed, vivo, md_updates: updates, quieto_sin_seq: quieto,
                     polls: e.seqs(),
                     ok: e.sses.length === 1 && !e.sses[0].closed && vivo === "live" && updates === 1 && quieto === "idle" && e.seqs() === 0 };
  }
  // 10) pestaña oculta
  {
    const e = env("ok", { sse: "hang", hidden: true });
    await e.flush(); await e.advance(10000);
    const ocultaSinNada = e.sses.length === 0 && e.healths() === 0 && e.calls.length === 0;
    e.document.hidden = false; e.handlers.visibilitychange(); await e.flush();
    const armo = e.sses.length === 1 && e.healths() === 1;
    e.sses[0].onmessage({ data: "1" }); await e.flush();      // baseline
    // la carrera: hidden ya flipó pero el visibilitychange todavía no corrió y
    // el stream entrega un mensaje → no tiene que disparar md-update
    e.document.hidden = true;
    e.sses[0].onmessage({ data: "2" }); await e.flush();
    const updatesOculta = e.updates();
    // guard de htmx:beforeRequest: cancela md-update y hx:poll:trigger con la
    // pestaña oculta; un click sigue; con la pestaña visible nada se cancela
    let cancelados = 0;
    const ev = (type) => ({ detail: { requestConfig: { triggeringEvent: { type } } }, preventDefault() { cancelados++; } });
    e.handlers["htmx:beforeRequest"](ev("md-update"));
    e.handlers["htmx:beforeRequest"](ev("hx:poll:trigger"));
    e.handlers["htmx:beforeRequest"](ev("click"));
    const canceladosOculta = cancelados;
    e.document.hidden = false;
    e.handlers["htmx:beforeRequest"](ev("md-update"));
    out.oculta = { sin_sse_ni_health: ocultaSinNada, arma_al_mostrarse: armo, md_updates_oculta: updatesOculta,
                   cancelados_oculta: canceladosOculta, cancelados_visible: cancelados - canceladosOculta,
                   ok: ocultaSinNada && armo && updatesOculta === 0 && canceladosOculta === 2 && cancelados === 2 };
  }
  // 11) plazo global de htmx
  {
    const e = env("ok");
    out.htmx_plazo = { timeout: e.window.htmx.config.timeout, ok: e.window.htmx.config.timeout === 30000 };
  }
  out.ok = Object.keys(out).every((k) => typeof out[k] !== "object" || out[k].ok);
  console.log(JSON.stringify(out, null, 1));
  process.exit(out.ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
