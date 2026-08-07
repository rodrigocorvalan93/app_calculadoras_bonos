# backend/ — Front web FastAPI

Reescritura del frontend Streamlit en **FastAPI + Jinja2 + HTMX + Alpine.js**.
Single-process local, sin cloud, sin build step, sin frameworks JS pesados
(gráficos en SVG server-side + uPlot). Objetivo de performance: **< 50 ms p95
server-side warm en todo endpoint de cara al usuario** (medido con sweeps de
50–100 calls; hoy todas las pestañas rinden p95 ≤ ~8 ms warm).

## Cómo correr

```bash
# Desde la raíz del repo
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
# abrir http://127.0.0.1:8000  (redirige a /login)
```

Env mínimas para el muro de login (o `AUTH_ENABLED=0` para dev sin muro) — ver
la sección **Auth** abajo. Las credenciales del broker (`PRIMARY_USER` /
`PRIMARY_PASS`, vía `secrets.txt`) habilitan el feed en vivo; sin ellas la app
calcula igual con datos de cierre/backup.

Cada usuario del equipo corre **su propia instancia** en su notebook (el .bat
lanza uvicorn en `http://127.0.0.1:8000`); no hay un server central.

## Pestañas

| Pestaña | Ruta | Qué hace |
|---|---|---|
| YAS | `/yas` | Ficha de análisis por bono: precio ↔ TIREA ↔ TNA ↔ margen TNA, ticket, cashflows, settlement/TC custom, override de convención TNA, ubicación en la curva con distancia a la NSS y switch de fuente (BYMA / CAFCI). |
| Nueva especie | `/nueva` | Calculadora ad-hoc: se arma/pega una ficha y calcula cashflow + métricas sin tocar el universo. |
| Comparador | `/comparador` | Dos bonos lado a lado + ubicación en curva (mismo widget que YAS, con fuente switcheable). |
| Curvas | `/curves` | Curvas por segmento (CER, DLK, HD, tasa fija, etc.) con precios en vivo. |
| Mercado | `/mercado` | Paneles de mercado en vivo: quotes, book por especie, cauciones, FX, MAE. |
| Break-even | `/breakeven` | BE de inflación (CER) y de deva (futuros), con gráficos SVG estilo unificado. |
| Dólares | `/dolares` | MEP/CCL/canje implícitos por especie + calculadora de canje. |
| Tasas | `/tasas` | Tasas cortas: cauciones, REPO, plazos. |
| Posiciones | `/posiciones` | Tenencias por fondo con métricas en vivo, Vto por bono, PnL. |
| Matriz | `/matriz` | Matriz de compensación entre bonos (ratio de precios). |
| Forwards | `/forwards` | Matriz triangular de forwards (TIREA o margen TNA), what-if diferido, **histórico par-a-par** con media/desvío/percentil/z (celda de la matriz clickeable → carga ese par). |
| Futuros | `/futuros` | Rofex DLR: tasas implícitas, sintéticos DLK↔ARS, gráfico de deva. |
| Gráficos | `/graficos` | Scatter TIR/duration por curva + ajuste NSS, con recorte por tramo (dmin–dmax), overlay de segunda curva y fuente BYMA (default) o vector CAFCI para corporativos. |
| Total Return | `/total-return` | TR proyectado por bono (salida a TIR/fecha) y TR realizado. |
| Escenario | `/escenario` | Senderos de inflación/deva/tasas y revaluación del universo. |
| Históricos | `/historicos` | Series guardadas (px/tasas por rueda) con el autosave diario. |
| Qué pasó | `/que-paso` | Resumen de la rueda por segmento + cómo se movió cada curva (mail automático opcional tras el autosave). |
| Créditos | `/creditos` | Scoring crediticio propietario por emisor. |
| CAFCI | `/cafci` | FCIs: series, flujos y vector de TIRs corporativas. |
| Órdenes | `/ordenes` | OMS: cursado de órdenes reales contra el broker, book en vivo. |
| Alertas | `/alertas` | Alertas de precio/tasa (superuser-only). |

Además, fuera de la nav: `/admin` (gestión de usuarios/roles/features + panel
de instalación del add-in de Excel), `/conexion` (reconexión del feed: elegir
broker, usuario y clave — disponible para todos los usuarios; URL libre sólo
superuser) y `/excel/*` (API del add-in).

La lista canónica de pestañas vive en `backend/services/auth.py` (`TABS`); el
superuser define desde `/admin` qué pestañas ve cada rol.

## Motor en vivo

- `primary_ws.py` mantiene el WS al broker (Primary/BYMA) + REST autenticado;
  `mae.py` sondea MAE. Todo entra a `marketdata_store.py` (store en memoria
  con secuencia global; `store_persist.py` lo restaura entre reinicios).
- El navegador **no** abre WebSockets: `static/js/app.js` sondea `/market/seq`
  (entero plano, ~0,5 ms) cada 1 s y dispara el evento `md-update` en `<body>`
  sólo cuando la secuencia avanzó (pausa con la pestaña oculta). Un panel vivo
  se declara `hx-trigger="md-update from:body, every 30s"` — el `every` largo
  es fallback, **no** usar `every 3-5s` fijo.
- `data-flash-scope` activa el diff de celdas post-swap → flash verde/rojo
  estilo terminal (`.tick-up` / `.tick-down`).
- El dot de la topbar (`#live-dot`) muestra live / idle / **stale** / off.
  `feed_health.py` detecta el broker "conectado pero mudo" (Md sin ticks +
  edad de los datos sobre la canasta de FX) y lo avisa en vez de mostrar
  precios viejos como vivos. `watchdog.py` reintenta la conexión.
- Cache de render por seq: `seq_cached(ttl=…)` — N clientes = 1 render.

## Históricos y forwards

- `historico_byma.py`: base parquet por rueda (TIREA/Duration/TEM/paridad por
  bono). `historico_writer.py` la guarda solo a las 17:01 hábiles
  (`HISTORICO_AUTOSAVE`, dejarlo prendido en **una** sola máquina del equipo).
- `forwards_hist.py`: serie histórica del forward par-a-par reconstruida de esa
  base (fórmula de descuento, gap mínimo 0,03 años para no anualizar ruido),
  con media/desvío/percentil empírico/z por ventana (30/60/90/todas). El
  percentil asume estacionariedad — la advertencia es parte del panel.

## FX legs y ficha nativa (hard-dollar)

`moneda` codifica la pata de cotización (USD = cable, USB = MEP). Un bono
hard-dollar es **una ficha calculada en su dólar nativo** (`…C` cable o `…D`
MEP, DIRTY) con hasta tres patas BYMA (`…O`/base = ARS, `…D` = MEP, `…C` =
cable). `services/fx.py::normalize_price(price, leg, native, fx)` convierte
pata → ARS → nativo con CCL/MEP implícitos; la pata nativa es no-op, así que
la curva básica queda libre de FX. La especie `…O`/sin sufijo CLEAN es sólo
referencia (Bloomberg/Euroclear) — nunca precia una pata BYMA.

## Convención TNA (tabla de detección)

Implementada en `services/pricing.py::tna_convention` — primera coincidencia
gana; `freq_override` + `base_override` del YAS siempre pisan el default
(label `… custom`):

| Tipo de bono | Convención | Detección |
|---|---|---|
| Dual TAMAR | 32/365 cap | `VARIABLE_CAP` + `index == TAMAR` |
| Tasa variable pura (BADLAR/TAMAR) | 90/365 | `tipo_tasa_interes == VARIABLE` |
| CER / CER PROY | 180/365 | `"CER" in ajuste_sobre_capital` |
| UVA / UVA PROY | 180/365 | `"UVA" in ajuste_sobre_capital` |
| DLK corporativo (A3500) | **90/360** | `"A3500" in ajuste` + `"CORPORATIVO" in clasificacion` |
| DLK soberano (A3500) | 90/365 | `"A3500" in ajuste_sobre_capital` |
| Hard-dollar | 180/360 | `_is_hard_dollar(obj)` (pata USD/USB **o** clasificación) |
| LECAP / bullets ARS | días_remanentes/365 | default |

El margen TNA usa la fórmula cap32 para `VARIABLE_CAP` y `TNA − bench/100`
para `VARIABLE` (benchmark = avg últimos 5 obs BCRA).

## Add-in de Excel «OMS Bonos»

Reemplazo del feed Reuters + calculadora YAS en la celda. Funciones en vivo
(`OMS.QUOTE/FX/ROFEX/CAUCION/TABLA/HIST`) vía snapshot compartido (1 build/s
para N libros) y funciones de cálculo puntuales (`OMS.TIREA/PRECIO/TNA/TICKET/
CALC/TR`) vía batch cacheado — una llamada, sin streaming de precios.
Manifest universal apuntando a `localhost:8000` (cada usuario corre su
instancia); instalación multi-máquina desde `/admin`. **Doc completa:**
`static/excel/README.md` (instalación/HTTPS) y `static/excel/FORMULAS.md`
(referencia de todas las fórmulas).

## Arquitectura

```
backend/
  main.py                  App + lifespan (warmup daemon, middleware auth/nav)
  config.py                Settings pydantic (.env / secrets.txt)
  cache.py                 LockedTTLCache + seq_cached (cache de render por seq)
  locale_ar.py             Filtros Jinja es-AR: ar_pct/ar_num/ar_int/ar_money/
                           ar_date/ar_pct_pp + parse_ar_num + hoy_ba
  routes/                  Un módulo por pestaña (+ admin, auth, conexion,
                           excel, market, tape)
  services/
    pricing.py             compute_metrics — motor YAS (TIR/TNA/ticket/TR),
                           convención TNA, cache TTL con fingerprint de índices
    bond_universe.py       Universo lazy desde especies.py
    marketdata_store.py    Store en memoria + seq global
    primary_ws.py          WS/REST broker · mae.py — pollers MAE
    feed_health.py         Detección de feed mudo/datos viejos
    curves.py              Armado de curvas (códigos por segmento); la lógica
                           de forwards/NSS por tramos/fuente CAFCI está en
                           routes/curves.py
    nss.py                 Ajuste Nelson-Siegel(-Svensson) con fallback NS
    forwards_hist.py       Histórico de forwards par-a-par
    historico_byma.py      Base parquet por rueda + autosave 17:01
    fx.py                  Patas O/D/C ↔ ficha nativa (CCL/MEP implícitos)
    svg_charts.py          Barras/ticks SVG compartidos (deva, BE)
    auth.py                Usuarios, roles, TABS, tokens de Excel
    ...                    (un service por dominio: dolares, futuros, breakeven,
                           escenario, total_return, credito, cafci, oms, ...)
  templates/               Una página por pestaña + partials/ (swaps HTMX)
  static/
    css/style.css          Tema Bloomberg-dark (+ [data-theme="light"])
    js/app.js              Live engine (seq/md-update/flash), sorters, copy-table
    js/charts.js           uPlot (gráficos, locate, overlay 2ª curva)
    excel/                 Add-in: manifest, functions.js/json, taskpane, docs
```

Legacy reutilizado (no reescribir): `rentafija.py`, `especies.py`, `utils.py`,
`indices.py`, `OMSapi.py`, `OMSmktdata.py`, `OMSprices.py`. Los singletons
`rentafija.Bono` mutan estado al calcular → **siempre** pasar por
`pricing._bond_obj_copy(code)` (lock por código + `copy.copy`).

## Auth (login wall + roles)

Muro de login con 3 roles: **superuser / premium / básico**. El superuser
gestiona usuarios, pestañas por rol, features y tokens de Excel desde `/admin`.
Contraseñas PBKDF2-HMAC-SHA256 con salt; sesión por cookie firmada;
recuperación por mail (SMTP). Config por env:

```
AUTH_ENABLED=1                       # 0 apaga el muro (dev/emergencia)
APP_SECRET_KEY=<hex largo>           # firma de la cookie de sesión
APP_USERS_PATH=auth_store.json       # store de usuarios (gitignored)
APP_SUPERUSER_USER=...               # se siembra en el 1er arranque
APP_SUPERUSER_PASSWORD=...
APP_SUPERUSER_EMAIL=...
APP_BASE_URL=https://...             # links de reset + manifest de Excel

APP_SMTP_HOST=smtp.gmail.com         # SMTP para reset de clave y mail Qué pasó
APP_SMTP_PORT=587
APP_SMTP_USER=... / APP_SMTP_PASSWORD=... / APP_SMTP_FROM=...
```

`/conexion` permite a **cualquier** usuario reconectar el feed contra los
brokers conocidos con su propio usuario/clave (vacío = credenciales de la
casa); la URL libre queda superuser-only porque el login manda la clave al
host que se elija.

## Performance

Regla de la casa (ver `CLAUDE.md`): **< 50 ms p95 warm** en todo endpoint de
cara al usuario, medido con sweep de 50–100 calls reportando avg/p50/p95/p99.
Números de referencia: YAS `/yas/recompute` p50 ≈ 9 ms · p95 ≈ 10 ms; sweep
integral de las 21 pestañas p95 ≤ ~8 ms warm. Los cómputos pesados (fits NSS,
cache-miss de métricas) corren en threadpool y quedan cacheados con
fingerprint de índices (A3500/CER/UVA) + día.

## Tests

```bash
pytest -q        # ~470 tests, suite completa en la raíz del repo
```

Toda feature nueva del backend lleva un smoke test que (a) ejercita el
cálculo y (b) pega al endpoint HTTP vía `httpx.AsyncClient` con
`ASGITransport`. Ojo con los exit codes: `pytest -q | tail` se come el código
de salida — chequearlo aparte (`set -o pipefail`).
