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

function env(mode) {
  let now = 100000, id = 0;
  const calls = [], timers = new Map(), pending = [], events = [];
  const dot = { dataset: {}, classList: { add() {}, remove() {} } };
  const handlers = {};
  let tbl = { getAttribute(k) { return { "data-delta": "/mercado/rows?curve=globales", "data-seq": "1", "data-order": "same" }[k]; }, setAttribute() {} };
  const scope = { id: "market-scope", querySelector() { return tbl; } };
  const document = {
    hidden: false, readyState: "complete",
    body: { addEventListener(n, f) { handlers[n] = f; } },
    addEventListener(n, f) { handlers[n] = f; },
    getElementById(n) { return n === "live-dot" ? dot : null; },
    querySelectorAll() { return [scope]; },
  };
  function fetch(url) {
    calls.push({ url, at: now });
    if (url === "/market/health") { return Promise.resolve({ json: async () => ({ feed_down: false }) }); }
    if (url.startsWith("/mercado/rows")) {
      if (mode === "delta_body") { return Promise.resolve({ text: () => new Promise(() => {}), ok: true, headers: { get: () => null } }); }
      if (mode === "delta_fetch") { return new Promise(() => {}); }
      return Promise.resolve({ text: async () => "", ok: true, headers: { get: (k) => (k === "X-Seq" ? "2" : null) } });
    }
    if (mode === "poll_hang") { return new Promise(() => {}); }
    if (mode === "poll_manual") { return new Promise((resolve) => pending.push((v) => resolve({ text: async () => String(v) }))); }
    return Promise.resolve({ text: async () => "1" });
  }
  const window = {
    localStorage: { getItem: () => null }, matchMedia: () => ({ matches: false }),
    htmx: { trigger: (target, name) => events.push({ name, at: now }), process() {} },
    requestAnimationFrame: (f) => f(),
  };
  const context = {
    window, document, fetch, performance: { now: () => now },
    Date: class extends Date { static now() { return now; } }, console, Promise, Math, parseInt, isNaN, String, Number, Error,
    setInterval(f, ms) { const k = ++id; timers.set(k, { f, ms, next: now + ms, repeat: true }); return k; },
    setTimeout(f, ms) { const k = ++id; timers.set(k, { f, ms, next: now + ms }); return k; },
    clearInterval(k) { timers.delete(k); }, clearTimeout(k) { timers.delete(k); },
  };
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
  return { calls, events, pending, dot, handlers, document, window, scope, advance, flush, replaceTable() { tbl = { ...tbl }; } };
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
  out.ok = Object.keys(out).every((k) => typeof out[k] !== "object" || out[k].ok);
  console.log(JSON.stringify(out, null, 1));
  process.exit(out.ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
