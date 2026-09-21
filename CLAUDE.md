# Conventions for Claude

## Performance — hard target

Any user-facing endpoint in the FastAPI rewrite (`backend/`) **must stay
under 50 ms p95 server-side** for the warm-cache path. This applies to
every phase, not just YAS.

- Measure with a 50- to 100-call sweep against the warmed endpoint
  before declaring a change done. Report `avg / p50 / p95 / p99`.
- If a change pushes p95 past 50 ms, fix it (cache, precompute,
  batch, drop the feature) before pushing.
- The numbers to beat as of Fase 1 finish: YAS `/yas/recompute`
  p50 ≈ 9 ms, p95 ≈ 10 ms, p99 ≈ 11 ms. Don't regress without a reason
  stated in the commit.

## Repo branch policy

Develop on the branch supplied by the session prompt (default:
`claude/laughing-turing-yG3tA`). Never push to `main` directly — always
open a PR. Don't create the PR unless the user explicitly asks for one.

## Don't touch unless necessary

- `rentafija.py`, `utils.py`, `indices.py`, `OMSapi.py`,
  `OMSmktdata.py`, `OMSprices.py` — legacy but correct. Reuse, don't
  rewrite. Fix bugs in place when needed.
- `especies.py` — **NO modificar sin permiso EXPLÍCITO del usuario**
  (regla del 10/09/2026; antes se permitía fix-in-place). Vale también
  para ISINs/fichas: proponer el cambio y esperar el OK.
- `OMSweb_app.py` — Streamlit legacy. Read-only reference for porting
  business logic. Don't import from `backend/`.

## Thread-safety pattern for `rentafija.Bono`

The bond singletons in `especies.py` mutate state on every calc
(`calcula_tirea`, `genera_ticket`, etc.). Always go through
`backend.services.pricing._bond_obj_copy(code)` (per-code lock +
`copy.copy`) before mutating, the same pattern the legacy uses in
`OMSweb_app._bond_obj_copy`.

## Locale and formatting

`es-AR`: comma decimals, period thousands separator, `DD/MM/AAAA` dates.
Use the Jinja filters in `backend/locale_ar.py`
(`ar_pct / ar_num / ar_int / ar_money / ar_date / ar_pct_pp`).

## TNA convention table

Implemented in `backend.services.pricing.tna_convention`. First match
wins:

| Tipo de bono | Convención TNA | Detección |
|---|---|---|
| Dual TAMAR | 32/365 cap | `VARIABLE_CAP` + `index == TAMAR` |
| Tasa variable pura (BADLAR / TAMAR) | 90/365 | `tipo_tasa_interes == VARIABLE` |
| CER / CER PROY | 180/360 | `"CER" in ajuste_sobre_capital` |
| UVA / UVA PROY | 180/360 | `"UVA" in ajuste_sobre_capital` |
| DLK corporativo (A3500) | 90/360 | `"A3500" in ajuste` + `"CORPORATIVO" in clasificacion` |
| DLK soberano (A3500) | 90/365 | `"A3500" in ajuste_sobre_capital` |
| Hard-dollar | 180/360 | `_is_hard_dollar(obj)` |
| LECAP / bullets ARS | días_remanentes / 365 | default |

`freq_override` + `base_override` always win over auto-detection (label
shows `… custom`).

Hard-dollar detection is **decoupled from the FX leg**: `moneda` now
encodes the quote leg (USD = cable, USB = MEP), so `_is_hard_dollar` is
true when `moneda in ("USD","USB")` **or** the classification/industria
says hard-dollar — a MEP (USB) or pesos-quoted hard-dollar bond keeps
180/360, not the días/365 default.

## Spreads vs UST (hard-dollar)

`backend/services/ust.py` — stdlib puro (lo importa también `bymaapi.py`
fuera del server). Curva par diaria de home.treasury.gov, bajada 1×/día en
un thread de fondo (NUNCA en un request); sin red cae a `ust_backup.json`
commiteado en el root (refrescarlo cada tanto, como `bcra_data_backup.json`;
la fecha de la curva usada viaja en `ust_fecha` y se muestra en la UI).
Bootstrap de ceros semianual; tiempos ACT/365 = el day-count de la TIR de
rentafija. `pricing.compute_metrics` agrega `g_spread_bps` / `z_spread_bps`
/ `ust_fecha` SOLO detrás de `_is_hard_dollar`, con los MISMOS flujos que
usó la TIR (`cashflow_cpn` con `Fechas > settlement`, col `Total`) —
g = TIREA − UST *efectiva* a la duration; z por bisección contra la curva
cero desplazada. rentafija.py NO se toca para esto. Ticket interactivo:
`bymaapi.genera_ticket_global(bono, px)`.

## FX legs and native-dollar basis (corp + sovereign USD)

A hard-dollar bond is **one ficha calculated on its native dollar**, with
up to three BYMA legs feeding it.

- **Native ficha** = the `…C` (cable) or `…D` (MEP) species, `DIRTY`,
  `Moneda` = `USD` (cable) or `USB` (MEP). This is what the BYMA curves
  price off. Globales / cable-corps: `GD30C`, `YM34C`. Bonares / MEP-corps:
  `AL30D`, `YFCND`.
- **Clean reference** (optional, for bonds with a Bloomberg/Euroclear
  quote) = the `…O` / no-suffix species, `CLEAN`, `Moneda` `USD`. **Never
  used to price a BYMA leg** — reference only (YAS manual entry / comparador).

A BYMA price's **leg** comes from its ticker suffix: `…O` / base → ARS
(pesos), `…D` → MEP (USB), `…C` → cable (USD). Every leg resolves to the
same native ficha; the price is converted **leg → ARS → native** with the
implicit rates CCL (`USD/ARS`) and MEP (`USB/ARS`) from
`backend.services.fx`:

| native ↓ \ leg → | ARS (…O) | MEP (…D) | cable (…C) |
|---|---|---|---|
| cable (`…C`, USD) | `/ CCL` | `× MEP / CCL` | — |
| MEP (`…D`, USB) | `/ MEP` | — | `× CCL / MEP` |

The native leg is a no-op, so the **basic curve is FX-free** (native ficha
+ native ticker); the FX only powers the cross-leg O/D/C view and price
fallbacks. Implemented in
`backend.services.fx.normalize_price(price, leg, native, fx)`.

## Cierre completo (`cierres/`)

Además de la base px/tasas (xlsx + parquet, sólo bonos de las curvas), el
autosave escribe UNA partición por rueda `Delta Bases/cierres/AAAA/AAAA-MM-DD.parquet`
con TODOS los símbolos del store (`historico_writer.build_cierre_rows`):
último/hora, cierre previo, OHLC, puntas, volumen, `opero` (último de HOY) y
TIREA/TNA/TEM/paridad/duration de los bonos con ficha. Append-only: nunca se
reescribe la historia; el archivo del día se pisa (keep-last) con la
recaptura `historico_recaptura_min` después del cierre. Journal local primero.
`services/cierres.py` = matrices numpy (fechas × símbolos) con `at / serie /
ret / vector_ref`; `historico_byma.ref_5d` (5D % de Mercado) lo usa cuando
está cargado. Backfill desde la base: `cierres.importar_base()` (automático en
el warmup del writer si no hay particiones). Nada de esto corre en un request.

**Espejo parquet de una base Excel** (`services/espejo.py`, stdlib puro —
también lo usa `bymaapi.py`): el `.parquet` vale SÓLO si es copia fiel del
xlsx. El writer / `_regen_parquet` / bymaapi dejan un sidecar
`<base>.parquet.src.json` con la firma (mtime ns + tamaño) del Excel del que
salió; `espejo_valido(pq, xlsx)` exige que la firma actual coincida exacto y,
sin sidecar, mtime ESTRICTO (ya no hay 2 s de gracia). Cualquier cambio del
Excel (corrección a mano, OneDrive con mtime viejo) hace ganar al Excel y el
espejo se regenera. Lectores: `historico_byma._pick_source`,
`historico_writer._leer_base`, `fx_hist._path`, `_leer_fx_previo`.

**Series diarias FX + caución** (`Delta - historico_fx`, `_guardar_fx`): UNA
fila por día que se mergea así: escalares (CCL, MEP, canje, A3500) POR COLUMNA
(último valor no nulo); cada caución POR GRUPO (`_FX_GRUPOS`: plazo + TNA +
VWAP + monto entran juntos desde el guardado que trae plazo+TNA, o se conserva
entero el anterior — nunca se mezcla el VWAP de un plazo con la TNA de otro).
Un segundo guardado del día (recaptura, botón manual) completa lo que falta y
nunca pisa con vacío lo ya guardado. Fuente previa = espejo válido o el Excel
(más nuevo); si hay archivos y NINGUNO se puede leer, `_guardar_fx` aborta
con RuntimeError (no pisa la historia); un xlsx ilegible con espejo sano se
aparta como `.corrupto-<fecha>`. La caución o/n sale de `cauciones.hist_row`: pick en
vivo del riel o, si a la hora del autosave el store ya no la tiene como "de
hoy", el último pick válido visto hoy (`_ULTIMO_HOY`, lo alimenta `rail_pick`
en cada refresh del riel). El autosave loguea qué caución guardó y, si no hay,
`cauciones.diagnostico()`; la recaptura vuelve a intentar la fila FX.
`fx_hist.status()["series"]` = cobertura por serie (n días con dato, último),
visible en la pestaña Series diarias. `historico_writer.escribir_fx(df, xlsx)`
es el ÚNICO camino de escritura del archivo (xlsx atómico + espejo + firma).
**Backfill hacia atrás**: `python -m backend.tools.backfill_fx --argentinadatos
[--dry-run] [--huecos] [--csv fx.csv]` (fuera de la app, en la máquina con
Delta Bases): sólo inserta fechas ANTERIORES a la primera fila de la app (o
días hábiles faltantes con `--huecos`), nunca pisa una fila existente, respalda
xlsx+parquet a `*.bak-<fecha>` y marca `ccl_base = ext:<fuente>`. Acciones /
CEDEARs: `backend.tools.backfill_acciones --byma` (BYMA Open Data; las filas
de la app ganan). `backfill_historico.bat` (raíz) corre los dos con el venv
de `run_backend (CORRER APP).bat` (`%LOCALAPPDATA%\venvs\bonos`), con menú
plan / escribir / acciones.

## Consola de arranque

`backend/consola.py`: `instalar()` (lo llama `main.py` al importar) pone UN
formato para la terminal — `HH:MM:SS  ·  módulo  mensaje` (`!` warning, `x`
error, traceback debajo) — en el root y en los handlers de uvicorn (access log
`GET /ruta → 200 · cliente`, con el filtro `_QuietPolls` intacto); sólo toca
handlers de consola (no el de pytest ni el ring de /admin) y cae a ASCII si
stderr no puede con `·`/`→`. `imprimir_banner()` al inicio del lifespan:
recuadro con app, autor, para quién, URL (`APP_HOST`/`PORT`), add-in y
versión (`version()` = git o `.git` a mano, nunca tira); y una línea `listo en
N s · bonos · feed · add-in · autosave` al final del arranque. Los launchers
(`run_backend (CORRER APP).bat`, `correr_app.command`) imprimen un encabezado
ASCII alineado y exportan `PORT`. Los `print` legacy de `indices.py` quedan
como están. **Segunda instancia**: uvicorn bindea el puerto recién DESPUÉS
del arranque (~15 s) y moría al final con WinError 10048; los dos launchers
sondean `/healthz` con curl antes de arrancar (si responde, abren el
navegador y salen) y el lifespan, con `PORT` seteado y sin `OMS_RELOAD=1`
(dev: el supervisor de `--reload` ya tiene el puerto), hace
`consola.app_ya_corriendo()` (GET /healthz, stdlib: sólo cuenta una respuesta
HTTP real) y sale con código 3 y un mensaje claro antes de cargar nada.
`rentafija.py` sube TODO `RuntimeWarning` a error a nivel proceso: cualquier
cast numpy sobre data externa (p. ej. `cierres._build`, float64 → float32)
va bajo `np.errstate` + `warnings.catch_warnings()` y lo que no entra queda
NaN — un valor basura en una celda no puede voltear una matriz entera.

## Posiciones — Categoría de las tenencias

`routes/posiciones._clasif(h, obj)` → `(categoría, fuente)`. Con ficha en
`especies.py` manda la ficha (`_categoria`: Dual → CER/UVA → USD-Linked →
USD/USB → ARS Fija/TAMAR/BADLAR/Step Up). SIN ficha entra
`services/clasificacion.py` (stdlib puro, ~µs por fila), primer match gana:
(1) **tipo de instrumento por texto** — fila de `Delta - Especies` si el ticker
está (Subclase / Clase de Activo / Industria / Sector Delta), descripción de
la cartera (columna `Especie`) y Clase de Activo del Excel: Plazos Fijos ·
Caución · Cheques (No) Garantizados · Pagarés (No) Garantizados ·
Fideicomisos TAMAR/BADLAR | CER/UVA | Tasa Fija | USD-Linked | USD |
Financieros · FCI Money Markets | FCI Cerrados | FCI; (2) **Ajuste × Tasa de
la base** (regla del legacy `OMSposiciones._categoria_bono`) con las MISMAS
etiquetas que las fichas — un ON TAMAR sin ficha suma a `ARS TAMAR`; (3)
Clase de Activo inferida (CEDEARs / Acciones) o cruda (`fuente = sin_regla`;
una fila `Liquidez` con ticker que no es caja se lee como FCI Money Markets).
Tasa y Calificación de los sin ficha también salen de la base
(`tasa_para` / `calificacion_base`; PF, caución, cheques y pagarés son Fija por
naturaleza). **Prefijo del emisor** (`con_emisor`): las categorías de bono
(CER / UVA / USD-Linked / USD / USB / ARS … / Dual …) llevan `Soberano` /
`Sub-soberano` / `ON` adelante — con ficha por su `Clasificación`
(`tipo_emisor_ficha`: "Soberano", "Sub-soberano", "Corporativo …"); sin ficha
por la taxonomía de la base, la descripción (el token `ON` manda: "ON BANCO
PROVINCIA" es una ON) o la Clase de Activo del Excel ("Títulos Públicos" =
soberano, la "Renta Fija" de Delta son las ONs). Sin dato de emisor la
categoría queda sin prefijo. PF / FF / cheques / FCI no llevan prefijo. La
celda Categoría lleva la fuente como tooltip y el título de la tabla cuenta
las filas `sin regla fina`. **Qué pulir en la base**: la tarjeta "Especies
faltantes" de /admin suma `routes.posiciones.reporte_clasificacion()` — las
tenencias Delta cuya categoría NO salió de ficha ni de la base, con ticker
(cargar Ajuste + Tasa, y Subclase para FF / FCI, en `Delta - Especies` o la
ficha en `especies.py`) y sin ticker sin regla (pasar la descripción). Antes
todo lo sin ficha caía a la Clase cruda: en Delta Ahorro, "Renta Fija" 47 %
del PN en una línea. Regresión: `tests/test_posiciones_clasificacion.py`.

**Pestañas lazy de Históricos** (`hx-trigger="reveal"`): las 4 rutas llevan
`@_pestana_resiliente(...)` — una excepción responde 200 con
`partials/historico_tab_error.html` (qué falló + Reintentar) en vez de un 500
que htmx no swapea (el tab quedaba en "Cargando…" para siempre); los
contenedores llevan `hx-request='{"timeout":90000}'` y `app.js` (`lazyFail`)
muestra el mismo alert ante error de red / timeout.

## Visual style (FastAPI rewrite)

Bloomberg palette + Notion/Apple/Linear typography. System sans
everywhere; numbers use `tabular-nums` instead of monospace. Dark
default with `[data-theme="light"]` available. No frameworks (no
Tailwind / Bootstrap / Google Fonts / JS libs beyond htmx + Alpine).

## Live engine (paneles de mercado)

`static/js/app.js` sondea `/market/seq` (entero plano, ~0,5 ms) cada 1 s y
dispara `md-update` en `<body>` sólo cuando la secuencia del store avanzó
(pausa con la pestaña oculta). Un panel con data de mercado se declara:

    <div id="…" data-flash-scope
         hx-get="/…" hx-trigger="md-update from:body, every 30s" …>

- `md-update from:body` → re-render ~1 s después de un tick real; el
  `every 20-30s` queda como fallback (datos que no pasan por el store,
  p. ej. pollers MAE). **No usar `every 3-5s` fijo**: con el seq el panel
  refresca más rápido y carga menos.
- `data-flash-scope` activa el diff de celdas post-swap (key = tabla +
  1ª celda de la fila + columna; en el riel, `.rail-l`→`.rail-v`) que pone
  `.tick-up` / `.tick-down` (flash CSS verde/rojo estilo terminal).
- El dot `#live-dot` de la topbar muestra el estado del feed
  (live/idle/off). Todo vanilla JS — sin librerías nuevas.
- **Copiar gráfico (⧉)** (`app.js`, `copySvg`): un SVG del server que pinta
  por CLASES (`.fut-chart .pa-*`, `.fc-*`, `.hc-*`) o con `var(--x)` no puede
  serializarse a secas — la imagen suelta no ve el CSS de la página y cae al
  default de SVG (relleno negro, sin stroke, serif). Se clona con el estilo
  CALCULADO inline (pintura + tipografía, `display:none` respetado) y recién
  ahí se rasteriza; sólo al click, ~1 ms por 100 nodos. Regresión:
  `tests/chart_copy_harness.cjs` (JS real en Node).
- **Paneles por FILAS (delta)**: un contenedor `data-delta-scope` (Mercado)
  NO swapea completo en cada `md-update`: si adentro hay una
  `table[data-delta]`, app.js pide `data-delta&since=<data-seq>&order=<data-order>`
  (`/mercado/rows`) y el server devuelve sólo los `<tr data-code>` cuyo
  símbolo cambió desde esa seq (`MarketSnapshot.seq` = seq global del store en
  su último update; header `X-Seq` = la nueva). Cada fila se reemplaza en el
  lugar y el flash sale del diff de ESA fila. `X-Full: 1` (cambió el
  conjunto/orden — hash `data-order` —, panel de acciones, fuente MAE) o
  cualquier error → `htmx.trigger(scope, 'refresh')` = swap completo; el
  `every 30s` sigue de red de seguridad. La fila es UNA macro
  (`partials/mercado_row.html`) compartida por la tabla y el delta: tienen
  que salir idénticas. Server: `_rows_en_seq` (1 build por params+seq,
  single-flight) + `_ROW_MEMO` (fila por seq del símbolo: un tick re-arma
  sólo su fila). Si agregás columnas a Mercado, van en la macro.

## Seguridad — invariantes (no regresar sin querer)

La app cursa órdenes reales y se comparte en el equipo, así que estos
controles son load-bearing. Tests en `tests/test_seguridad.py` +
`tests/test_auth.py`.

- **Gating por subárbol de superficies sensibles**: `auth._TAB_PREFIX_GATED`
  gatea TODO el subárbol (no sólo la página exacta) de `/ordenes`,
  `/posiciones` y `/matriz` — los partials de datos (`…/table`, `…/targets`)
  filtran tenencias reales del desk. El modelo general sigue siendo
  página-exacta (partials compartidos como `/dolares/rail` no se atan a su
  prefijo); si agregás una pestaña con data confidencial y sub-endpoints
  propios, sumala acá.
- **Fondos visibles por usuario** (`auth.visible_fondos` / campo `fondos` del
  store; editor en /admin): filtro fino ADENTRO de las pestañas con
  tenencias. None = todos (default); lista = allowlist de `cod_fondo` (un
  fondo nuevo NO se muestra a un restringido hasta tildarlo). Los fondos
  GALILEO viven en el mismo pipeline con `cod_fondo + positions.GALILEO_OFFSET`
  (10000) — numeración propia que colisiona con la de Delta — así las
  allowlists/URLs siguen siendo ints y un restringido no los ve hasta tildar. Se aplica
  SERVER-SIDE en `services.positions` (param `visibles`) y entra por
  `auth.visible_fondos_for(request)` en Posiciones/Matriz (páginas y
  partials, robusto a `?fondo=` a mano) y en los desplegables de tenencia
  (`position_for`) de YAS / Comparador / Curvas, recalculando totales sobre
  lo visible. Si agregás una vista nueva que muestre tenencias por fondo,
  pasale `visibles` — nunca filtres en el template.
- **Middleware `_SecurityMiddleware`** (el más externo, ASGI puro en
  `main.create_app`): agrega `X-Frame-Options: DENY`, CSP con
  `frame-ancestors 'none'`/`object-src 'none'`/`base-uri 'self'`, `nosniff`,
  `Referrer-Policy`, y **rechaza POST/PUT/PATCH/DELETE cross-site** por
  Origin/Referer (defensa CSRF además de `SameSite=Lax`). `/excel/*` está
  EXENTO (corre en el iframe/webview de Office; auth por token, no cookie).
  La CSP deja `script-src`/`style-src` con `unsafe-inline`+`unsafe-eval`
  porque Alpine evalúa con `Function()` y hay inline en los templates — no lo
  quites o rompés Alpine.
- **Guard de arranque**: `create_app` se niega a levantar si
  `AUTH_ENABLED=0` (sin muro, todo request = superuser) con `APP_HOST` no
  loopback (host expuesto). Dev local (auth off + 127.0.0.1) y Tailscale con
  muro puesto arrancan normal.
- **Parser ad-hoc** (`adhoc._eval_node`): whitelist AST (rechaza Name/Call/
  Attribute/…). `Mult` está acotado (`_MAX_SEQ_LEN`) para que `[0]*9e8` no
  reviente memoria, y `parse_ficha` corre en el threadpool (texto arbitrario
  del usuario, no bloquear el event loop).
- **Manifest de Excel** (`excel._safe_manifest_base`): `?base=` se valida
  contra una allowlist de hosts (loopback / IP LAN / `app_base_url` / host de
  descarga) y se RECONSTRUYE desde componentes parseados — no se interpola
  texto crudo en el XML (evita apuntar el add-in de un colega a un host
  atacante que capture el token).
- **`/conexion`**: la allowlist de hosts para no-superuser es la barrera
  anti-harvesting (el login MANDA la clave al host elegido). Mantené el
  match exacto de URL normalizada; la URL libre es superuser-only.
  **Reconexión**: se loguea un cliente CANDIDATO y recién con login OK se
  para el actual y se publica (`primary_ws.set_ws_client`, bajo
  `conexion._swap_lock`); un login fallido no toca la conexión de la mesa.
  Cada swap sube `primary_ws.context_version()`: los tickets la guardan
  (`ctx_version`, también en CADA hija de una multiorden) y `oms.place` la
  re-chequea al entrar Y justo antes de transmitir (después del audit / del
  resolve del instrumento) — un swap en el medio da `rechazada_contexto`; los
  caches de comitentes e instrumentos la llevan en la key.
- **Estados de orden** (`oms.place`): sólo `status == "OK"` + `order.clientId`
  es ENVIADA; un JSON de rechazo es `live_rechazo_broker` (RECHAZADA (broker));
  un timeout/corte DESPUÉS de mandar, un HTTP 5xx o un cuerpo vacío/no-JSON
  (`primary_ws.BrokerHTTPError` ≥ 500 / `BrokerRespuestaInvalida`) es
  `live_desconocida` (DESCONOCIDA: la orden PUDO entrar — no reenviar a
  ciegas). ConnectError / 4xx = nunca se procesó = ERROR. La reconciliación
  (`_reconciliar_desconocida`) sólo afirma lo que la evidencia permite:
  consulta `rest/order/all` (lista completa del día) y `actives`; una orden con
  los mismos términos cuenta como ESTE intento sólo si su `transactTime` es
  posterior a `enviada_ts` (margen 5 s) → `live_estado`; igual pero sin hora →
  `live_desconocida_posible` (sigue DESCONOCIDA, con el id); no está en la lista
  COMPLETA → `live_desconocida_sin_rastro` ("NO ENTRÓ"); si `all` no respondió
  → `live_desconocida_no_verificable` (DESCONOCIDA). `oms.cancel`: OK =
  "CANCEL ACEPTADA" (el estado final lo confirma el seguimiento), JSON de
  rechazo = "CANCEL RECHAZADA" (la orden sigue viva), excepción = "CANCEL
  ERROR" — nunca CANCELADA sin confirmación del broker.
- **Versión de sesión** (`auth.session_version`, campo `sv` del usuario): la
  cookie la lleva y el middleware la compara en cada request (~1 µs). Sube con
  cambio/reset de clave y con "cerrar sesiones" en /admin → las cookies
  anteriores dejan de autenticar. El token de Excel es independiente.
  `auth.reset_with_token` valida y cambia bajo el mismo lock (token de un uso
  aun con dos POST simultáneos). **uid de cuenta** (`auth.session_uid`, campo
  `uid`; `ensure_bootstrapped` lo completa en registros viejos): también viaja
  en la cookie y se compara — borrar y recrear un usuario con el mismo nombre
  es otra cuenta y las cookies del anterior no entran; cookies sin `uid` se
  rechazan. El login captura `sv`/`uid` ANTES de verificar la clave y rechaza si
  cambiaron durante la verificación (un reset simultáneo no regala la versión
  nueva a una verificación contra la clave vieja).
- **Single-flight async** (`cache.AsyncSingleFlight`): N requests con la
  MISMA key fría comparten UN Future en el event loop (un solo worker calcula,
  los demás hacen `await` sin ocupar el pool; `shield` contra la cancelación
  de un request). Lo usan YAS (`routes/yas._INFLIGHT`), Escenario y Total
  Return (`_vuelo`) ANTES de mandar al `_row_pool` — antes 8 pedidos
  idénticos dormían sobre el compute-lock adentro del pool y dejaban sin
  worker al libro/Mercado. Sólo se comparte el cálculo; tenencias y permisos
  siguen por request. `LockedTTLCache` cuenta productor + esperadores por
  lock (`_compute_locks[key] = [lock, usuarios]`): la poda nunca descarta un
  lock en uso. `curves._rows_en_seq` valida su cache por seq del feed Y
  `pricing.indices_token()` (huella de A3500/CER/UVA/TAMAR/BADLAR +
  proyecciones), y la huella entra en el `order` hash del delta: un refresh de
  índices sin tick re-arma las filas y fuerza `X-Full` en el cliente.
- **Eficiencia (auditoría 17/09)**: `rentafija.calcula_intereses_corridos(
  …, _flujos_generados=True)` reutiliza los cashflows que `calcula_tirea` /
  `calcula_precio` acaban de generar (una valuación = 1 `generate_cashflows`,
  antes 2; default False = comportamiento legacy). `excel._snapshot_bytes`
  tiene un lock por key (un build por ventana) y `?codes=` hace lookup
  directo. `oms.kill_switch_async` / `set_live_async`: flag inmediato + audit
  en el executor (los handlers async NO llaman al `audit` síncrono).
  `/historicos/data` convierte cada fecha una vez, arma en el pool y memoiza
  el JSON por versión de la carga. Frontend: `app.js` sondea con UN request en
  vuelo, plazo total (`fetchTexto`) y backoff; el delta libera `deltaBusy`
  siempre (plazo 8 s → swap completo); `charts.js` descarta respuestas de una
  selección anterior (contador de generación). Regresiones en
  `tests/test_auditoria_eficiencia.py` + `tests/live_engine_harness.cjs`.
- **Readiness**: `/readyz` = 200/503 (universo cargado) y `/healthz` lleva
  `ready`; `deploy/deploy.ps1` espera `ready` y chequea `$LASTEXITCODE` de
  git/pip/nssm (un paso fallido aborta sin reiniciar el servicio).
- **Puente TLS del add-in** (`services/tls_bridge.py`): listener https
  (default `127.0.0.1:8443`) que proxya al uvicorn http local — Office exige
  https para el runtime de funciones custom. PISA `X-Forwarded-*` del cliente
  (nadie inyecta scheme/IP) y fuerza `Connection: close` (1 request por
  conexión → no parsea framing de respuestas). Certs estilo mkcert en
  `certs/` (gitignored) vía `backend/tools/https_local.py`; la clave de la CA
  no sale de la máquina (`/excel/ca.crt` sirve SOLO el certificado público).
  `/excel/v1/beacon` es público a propósito (diagnóstico del runtime headless:
  reporta cuando el token falta) — no devuelve datos, sólo loguea sanitizado
  con throttle. `/excel/crl` también es público: es el punto de distribución
  de CRL que llevan los certs del puente (schannel lo baja sin cookies; sin
  él, máquinas con política estricta cortan el handshake con
  `CRYPT_E_NO_REVOCATION_CHECK`) — sirve una CRL vacía firmada por la CA
  local, no expone datos.

## Tests

`pytest -q` at the repo root. New backend features need a smoke test
that (a) exercises the calc, (b) hits the HTTP endpoint via
`httpx.AsyncClient` with `ASGITransport`.

CI (`.github/workflows/tests.yml`) corre la suite en **Ubuntu y Windows**
(Python 3.12) con `pytest-timeout --timeout=300`: la app se despliega como
servicio Windows y el add-in de Excel vive ahí, así que nada Unix-only
(`os.fchmod`, `fcntl`, señales) puede entrar sin guard. Los tests de rutas
Mac (`test_deltapaths.py`) parchean `deltapaths._WINDOWS` para correr en
los dos runners. Las credenciales de bootstrap de la suite son sintéticas
(`tests/conftest.py`): nunca una cuenta real. Las regresiones de la
auditoría externa (sept. 2026) viven en `tests/test_auditoria_tanda1.py`.
