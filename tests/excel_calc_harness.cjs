// Harness de OMSCalc (funciones de cálculo del add-in: OMS.TIREA / PRECIO /
// TNA / …): corre el functions.js REAL en un VM de Node con fetch y reloj
// simulados. Lo invoca tests/test_excel_calc_reintento.py; imprime JSON
// {caso: true | detalle}.
//   - un POST /excel/v1/calc colgado tiene plazo y se reintenta solo UNA vez;
//   - si tampoco responde, la celda sale con un error legible (no #OCUPADO) y
//     la misma fórmula se puede volver a pedir (pending no queda trabado);
//   - 5xx, red caída y cuerpo cortado se reintentan; 401 no;
//   - el dedup en vuelo sigue: dos celdas iguales = un POST.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const source = fs.readFileSync(path.join(__dirname, "..", "backend", "static", "excel", "functions.js"), "utf8");

class FakeCfError extends Error { constructor(code, msg) { super(msg); this.code = code; } }

function fixture(guion) {
  // guion: lista de modos por POST a /calc ("ok" | "hang" | "hang_body" | "red" | 503 | 401);
  // agotada, el último se repite.
  const st = { posts: 0, beacons: [], aborts: 0 };
  const sandbox = {
    console, Promise, Math, JSON, Number, String, Array, Object, Error, Map, Set, RegExp, Date,
    AbortController: typeof AbortController !== "undefined" ? AbortController : undefined,
    setInterval() { return 1; }, clearInterval() {},
    // plazos (≥ 1 s) y pausa del reintento comprimidos; la ventana de batch (80 ms) queda
    setTimeout(fn, ms) { return setTimeout(fn, ms >= 300 ? 20 : ms); },
    clearTimeout,
    window: { location: { search: "?token=SYNTHETIC" }, localStorage: { getItem() { return null; }, setItem() {} },
              OMS_BEACON(s, d) { st.beacons.push(s); } },
    OfficeRuntime: { storage: { getItem() { return Promise.resolve(null); }, setItem() { return Promise.resolve(); } } },
    CustomFunctions: { associate() {}, Error: FakeCfError, ErrorCode: { notAvailable: "#N/A" } },
    Office: { onReady() { return Promise.resolve({}); } },
    fetch(url, opts) {
      if (String(url).indexOf("/excel/v1/calc") < 0) { return new Promise(() => {}); }
      const modo = guion[Math.min(st.posts, guion.length - 1)];
      st.posts++;
      if (opts && opts.signal) { opts.signal.addEventListener("abort", () => { st.aborts++; }); }
      const n = JSON.parse(opts.body).items.length;
      const results = Array.from({ length: n }, () => ({ tirea: 0.0812 }));
      if (modo === "hang") { return new Promise(() => {}); }
      if (modo === "red") { return Promise.reject(new TypeError("Failed to fetch")); }
      if (modo === "hang_body") { return Promise.resolve({ ok: true, status: 200, json: () => new Promise(() => {}) }); }
      if (typeof modo === "number") { return Promise.resolve({ ok: false, status: modo, json: () => Promise.resolve({}) }); }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ results }) });
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { calc: sandbox.OMSCalc, st };
}
const item = (code) => ({ code, modo: "precio", valor: 70.5, plazo: "24hs", tipo: "tir" });
const res = (p) => p.then((v) => ({ ok: v }), (e) => ({ err: e }));
const eq = (a, b) => (JSON.stringify(a) === JSON.stringify(b) ? true : { got: a, want: b });

(async () => {
  const out = {};
  { // sano: un POST, sin beacons de problema
    const f = fixture(["ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.ok_resuelve = eq([r.ok && r.ok.tirea, f.st.posts, f.st.beacons], [0.0812, 1, []]);
  }
  { // el primer POST se cuelga → plazo, se aborta, reintento que responde
    const f = fixture(["hang", "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.colgado_y_reintento = eq([r.ok && r.ok.tirea, f.st.posts, f.st.beacons],
                                 [0.0812, 2, ["calc-reintento", "calc-reintento-ok"]]);
    out.colgado_se_aborta = f.st.aborts >= 1 ? true : { got: f.st.aborts };
  }
  { // nunca responde → error legible (no queda en #OCUPADO) y la fórmula se puede re-pedir
    const guion = ["hang", "hang", "ok"];
    const f = fixture(guion);
    const r = await res(f.calc.request(item("GD30C")));
    out.sin_respuesta_es_error_legible = (r.err instanceof FakeCfError && /no respondió el cálculo/.test(r.err.message)
      && /2 intentos/.test(r.err.message)) ? true : { got: String(r.err && r.err.message) };
    out.sin_respuesta_dos_posts = eq([f.st.posts, f.st.beacons], [2, ["calc-reintento", "calc-fallo"]]);
    const r2 = await res(f.calc.request(item("GD30C")));          // la MISMA key: antes quedaba colgada del pedido muerto
    out.la_misma_formula_vuelve_a_pedir = eq([r2.ok && r2.ok.tirea, f.st.posts], [0.0812, 3]);
  }
  { // el error no se memoiza; el resultado bueno sí (el 2º pedido no pega al server)
    const f = fixture(["ok"]);
    await res(f.calc.request(item("TTCDC")));
    await res(f.calc.request(item("TTCDC")));
    out.memo_sigue_andando = eq(f.st.posts, 1);
  }
  { // 503 del puente (uvicorn reiniciando) → reintento
    const f = fixture([503, "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.http_5xx_reintenta = eq([r.ok && r.ok.tirea, f.st.posts], [0.0812, 2]);
  }
  { // sin red / server caído → reintento
    const f = fixture(["red", "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.red_caida_reintenta = eq([r.ok && r.ok.tirea, f.st.posts], [0.0812, 2]);
  }
  { // headers OK y cuerpo que nunca termina → plazo igual
    const f = fixture(["hang_body", "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.cuerpo_colgado_reintenta = eq([r.ok && r.ok.tirea, f.st.posts], [0.0812, 2]);
  }
  { // 401: definitivo, sin reintento
    const f = fixture([401, "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.token_invalido_no_reintenta = (r.err instanceof FakeCfError && /Token/.test(r.err.message) && f.st.posts === 1)
      ? true : { got: [String(r.err && r.err.message), f.st.posts] };
  }
  { // 400 del server: definitivo
    const f = fixture([400, "ok"]);
    const r = await res(f.calc.request(item("AL30D")));
    out.http_4xx_no_reintenta = (r.err instanceof FakeCfError && f.st.posts === 1) ? true : { got: f.st.posts };
  }
  { // dedup en vuelo + batch: 2 celdas iguales y 1 distinta = UN POST, también a través del reintento
    const f = fixture(["hang", "ok"]);
    const rs = await Promise.all([res(f.calc.request(item("AL30D"))), res(f.calc.request(item("AL30D"))),
                                  res(f.calc.request(item("GD30C")))]);
    out.dedup_y_batch_con_reintento = eq([rs.map((r) => r.ok && r.ok.tirea), f.st.posts], [[0.0812, 0.0812, 0.0812], 2]);
  }
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
})();
