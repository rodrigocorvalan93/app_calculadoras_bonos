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

## Descuento a fecha de pago hábil (23/09)

`generate_cashflows` deja en `cashflow_cpn` la columna `FechaPago` (la fecha
hábil de `cashflow_pmt`, misma fila) y TIR / precio / duration / convexidad /
TR / `pricing._duration_desde_cashflows` / `ust.flujos_bono` descuentan a ESA
fecha: la plata entra el día hábil de pago, igual que 1816 (TX26 a 746,90 con
liq. 24/09/2026 = 3,59 %, no el 3,67 % que daba descontar al cupón del 09/11).
Los MONTOS, el devengamiento y el filtro `Fechas > settlement` siguen por
fecha de cupón. En bullets (`cupones == 1`) `dias_remanentes` y la TNA
"plazo remanente" (`dias_al_pago`) cuentan hasta el pago hábil. Feriados que
`holidays` (pineado 0.90) no trae van a `dias_habiles._additional_holidays`
(09/11/2026: visita papal). Regresión: `tests/test_descuento_fecha_pago.py`.

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

**TAMAR / BADLAR aplicable a mano** (YAS "TAMAR/BADLAR custom", 25/09):
`compute_metrics(bench_override=<TNA %>)` / `tr_puntual(bench_override=…)`.
Sobre la COPIA per-request, `rentafija.Bono.aplica_nivel_variable(nivel)`
reemplaza la serie proyectada (plana en el promedio 5 ruedas desde la última
observación, `indices.py`) por el nivel del usuario de ahí en adelante y
recomputa el cupón con la misma réplica de `__init__`
(`_cupon_desde_serie`, compartida con `recalcula_cupon_variable`: cortes por
período con `searchsorted` sobre el índice ordenado + el mismo `.mean()` de
pandas → bit a bit igual a la máscara del legacy, 11 → 3 ms); con el
nivel = ese promedio el precio es idéntico al de siempre (test). Costo del
what-if: +1 a +3 ms por cálculo. El mismo
nivel es el benchmark del margen (`_bench_for`: modo margen, Margen TNA,
card "aplicable (custom)", `bench_custom` en las métricas). No muta `inputs`
ni el singleton (mismo patrón que `_a3500_override`); en un bono que no es
floater no hace nada. El add-in de Excel no lo expone. Regresión:
`tests/test_bench_override.py`.

Hard-dollar detection is **decoupled from the FX leg**: `moneda` now
encodes the quote leg (USD = cable, USB = MEP), so `_is_hard_dollar` is
true when `moneda in ("USD","USB")` **or** the classification/industria
says hard-dollar — a MEP (USB) or pesos-quoted hard-dollar bond keeps
180/360, not the días/365 default.

## DLK — FX aplicable intradía (SIOPEL hasta que el BCRA publique, 19/10)

`pricing.a3500_aplicable()`: A3500 de HOY ya publicado → manda el cierre; si
no, el mayorista intradía de hoy (`dolares.oficial_intradia_hoy`: SIOPEL
fresco → DLR/SPOT de hoy → el ÚLTIMO SIOPEL de hoy aunque el fetch tenga más
de 15 min — MAE caído un rato o rueda cerrada —; nunca uno de ayer); si no, el
último publicado. **"Publicado" se decide con el backup BCRA en memoria**
(`historico.series_points("a3500")`, `pricing._a3500_bcra`), NO con
`rentafija.inputs['a3500']`: `especies.py` le inyecta al importarse una fila
con la fecha de HOY (`indices.refresh_a3500_in_rentafija`: el SIOPEL del
arranque o, sin MAE, el último cierre relabelado — mecanismo del Streamlit
legacy) y con eso la regla creía que el cierre del día ya estaba: los DLK se
valuaban TODO el día contra ese número (desk 19/10). Esa fila se saca al
cargar el universo (`bond_universe._sanear_inyeccion_a3500`: filas con fecha
≥ hoy que el backup no tiene; sin backup no toca nada; especies.py NO se
modifica). `_dlk_fx_auto()` pone el override por-objeto siempre que el FX
aplicable difiera del último de la serie de rentafija (intradía, o el
publicado mientras `inputs.refresh()` todavía no corrió); si coinciden, sin
override (numéricamente igual que siempre). Sábado / domingo / feriado
(`_es_rueda_hoy`, calendario de `dias_habiles`) → el último publicado, sin
intradía (el poller MAE corre 24×7 y dejaba el SIOPEL del viernes como "de
hoy"). Un arranque DESPUÉS de la publicación (la inyección PISA el A3500 del
día con el SIOPEL del arranque) → el saneo repone el valor del backup. Los
caminos que copian el bono a secas (`total_return._bond_tr_base`,
`tr_realizado`, perfil de vencimientos de Posiciones) llevan el mismo
override vía `pricing.aplicar_fx_dlk(obj, code)` — si agregás otro
`_bond_obj_copy` de un DLK, llamalo. El card de YAS muestra la fuente
("mayorista intradía (SIOPEL)" / "cierre"). `DLK_FX_INTRADIA=0` apaga el
intradía. Queda afuera a propósito: si `bcra_data_backup.json` no se pudo
escribir, "publicado" sigue al backup viejo (el refresh vespertino lo
reintenta cada 10 min). Regresión: `tests/test_dlk_fx_intradia.py`.

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

**Cierre perdido y feed caído al cierre** (`historico_writer`, 24/09): el
autosave de las 17:01 guarda lo que tenga el store con `last_ts` de hoy, no
necesita el feed "en vivo" (el gris del dot después del cierre es normal).
Con broker configurado y el WS desconectado o > 10 min sin market data
(`_feed_estado`, NO el `feed_alive` de 90 s: post-cierre el mercado calla)
NO guarda los últimos precios que llegaron como cierre: `skipped` +
`retry` + `feed_muerto`, aviso al superuser (chip "pendiente · feed caído",
banner con "Guardar igual" = force, mail 1×/día vía `mailer`) y reintento
cada 5 min hasta `_VENTANA_MIN` (95); otros errores siguen cada 10 min.
Feriado del calendario → skip explícito. Una rueda que igual se perdió se
REARMA (`reconstruir_cierre(dia)` / `reconstruir_faltantes()`): primero con
el cierre previo (CL con fecha) que el feed manda durante la rueda
siguiente (`cierres_en_store`: bastantes símbolos con CL de ese día, ninguno
posterior, la canasta líquida coincide), si no con el `Close Price` de las
filas de la rueda siguiente ya guardadas; TIREA/TNA/TEM/paridad/duration se
recalculan con liquidación al hábil siguiente (`_settle_24hs`, mismo settle
que Curvas ese día) vía `compute_metrics` directo (sin ensuciar el cache de
curvas), especie en pesos de un hard-dollar → nativa ÷ FX de los CIERRES
(`fx.compute_fx_cierres` / `_fx_desde_filas`). Filas `Price Source = RC`,
`Close Price` = último de la rueda anterior, journal `px_tasas_<dia>`, base
con el dedup de siempre, fila FX del día (CCL/MEP de cierres + A3500 de la
serie) y partición de cierres desde la base (`cierres.importar_base`, sin
volumen/OHLC; `opero` cuenta RC con fecha). Si los cierres previos de D+1 son
exactamente los últimos de D-1, D no tuvo rueda → `sin_rueda`. Sólo se
recupera el último día de un hueco, y una rueda RC NO es fuente para
reconstruir la anterior (`_filas_base_en` la salta: su `Close Price` es el
último de la rueda previa DISPONIBLE, no el cierre real de D-1 — fabricaría
D-1 con precios de D-2 o la marcaría `sin_rueda`); con dos huecos seguidos el
más viejo queda pendiente y visible. Corre solo al arrancar (espera el
snapshot hasta 4 min), a las 17:01 antes de guardar hoy, en
`tools/cierre.py`, y a mano: POST `/historicos/reconstruir-cierre`
(superuser; botón "Reconstruir DD/MM" del banner, también para huecos
anteriores al cierre esperado: `estado_cierre()["huecos"]`).
**Ignorar un hueco** (02/10): botón "Ignorar DD/MM" del mismo banner (también
cuando no hay de dónde reconstruir) → POST `/historicos/ignorar-hueco`
(superuser; `deshacer=1` lo revierte; con éxito manda `HX-Trigger:
cierre-refresh` y el chip del pie se refresca a los 2,5 s) →
`huecos_ignorados.json` EN LA CARPETA DE LA BASE (viaja por OneDrive: todas
las máquinas, la writer incluida, dejan de reclamarlo; `huecos_ignorados()`
cacheado por mtime, `ignorar_hueco()` escritura atómica, archivo ilegible =
vacío). `huecos_base` lo saltea (banner, log del arranque,
`reconstruir_faltantes`, `tools/cierre.py`) y el tooltip del chip los cuenta
(`estado_cierre()["ignorados"]`). NO es `sin_rueda`: para
`_fuente_reconstruccion` / `reconstruir_cierre` de la rueda anterior sigue
siendo una rueda que falta (no se fabrica una RC desde un día ignorado).
**La base nunca pierde ruedas** (05/10): la notebook arrancó con una réplica
de OneDrive atrasada y escribió la base → 5 ruedas perdidas que el chip
acusaba como huecos y Reconstruir rearmaba con RC (y la otra máquina volvía a
pisar). Defensas en `historico_writer`: (1) `_resumen_base` = {rueda: (filas,
reales)} desde la fuente FIEL — el espejo si `espejo_valido` (la firma lleva
ahora también `pq_size`), si no el Excel (segundos, una vez por cambio; cache
`_fechas_cache` por firmas de los dos archivos) — lo usan `huecos_base`,
`_ya_guardado_hoy`, consolidación y reconstrucción; (2) memoria local
`journal_dir()/base_vista.json` (máximo de filas/reales visto por rueda y por
carpeta de base, ventana `_MEMORIA_DIAS` = 120) + manifiesto compartido
`base_manifest.json` (host, hora, ruedas del último guardado) →
`regresion_detalle()`: ruedas que faltan / pasaron a RC / perdieron la mitad
de las filas; `recuperables` = el journal propio las tiene con filas reales,
el resto `bloqueantes`; (3) `_append_and_save_locked` lanza `BaseEnRegresion`
con bloqueantes (salvo `ignorar_regresion`) y repone del journal las
degradadas → `save_today` = skipped+retry con el día en el journal,
`consolidar_journal` frenado (`reponer=True` escribe igual, sin exigir
writer), `reconstruir_cierre` / `reconstruir_faltantes` / arranque frenados;
`reconstruir_cierre` tampoco pisa una rueda con filas reales aunque sea
`force`; (4) `estado_cierre` estado `regresion` (manda sobre falta / hueco) +
banner rojo con "Reponer del journal (n)" (`POST /historicos/reponer-journal`)
y "Aceptar la base como está" (`POST /historicos/aceptar-base`: memoria y
manifiesto pasan a describir el disco), superuser; (5) `_disparo_vencido`: el
temporizador del autosave que salta al despertar con la ventana vencida se
rearma sin evaluar (antes "feed caído al cierre" falso sobre el WS recién
reconectado por el resume); (6) el journal de la rueda que se está
escribiendo no se "consolida" dos veces. Diagnóstico sólo lectura en
cualquier máquina: `python -m backend.tools.base_check` (archivos, espejo
fiel, ruedas base / memoria / manifiesto / journal, regresión, copias de
conflicto). Regresión: `tests/test_base_regresion.py`.
**Writer por rol** (07/10; sólo superuser desde el 15/10):
`HISTORICO_BASE_WRITER` sigue siendo el máster (0 = esa máquina nunca escribe
lo compartido), pero con el flag en 1 y el muro de login puesto una instancia
escribe la base compartida sólo si HOY (fecha BA) la usó un **superuser**
(`auth.writer_presente`: rol, no feature). Pedido del desk: el historial lo
más limpio posible, con la menor cantidad de máquinas escribiendo; premium y
básico sólo journalean. Hasta el 15/10 era la feature `base_writer`, premium
por default: ya no existe (salió de `auth.FEATURES` y de /admin, que ahora lo
aclara con una nota) y una entrada vieja en `role_features` se ignora sola (no
está en `FEATURE_KEYS`). Un día sin superuser la instancia journalea las
filas REALES (local, por máquina) y **nunca se pierden** (15/10, "sin perder
historiales"): `HistoricoAutosave._catch_up_journal` (consolidar_journal +
consolidar_cierres_journal) corre en `_reconstruir_al_arrancar` DESPUÉS de
esperar al superuser (el del principio de `_run` corre sin nadie logueado y
con el muro no hacía nada) y antes de cada `reconstruir_faltantes` de las
17:01; y `reconstruir_cierre` con la rueda en el journal con filas reales la
CONSOLIDA desde ahí (`_consolidar_rueda_del_journal`: filas LA tal cual —
pisan RC del mismo día por símbolo —, fila FX con el CCL/MEP de la columna
`FX` de las patas en pesos + A3500, partición desde `cierre_<dia>` del
journal o desde la base) y nunca la rearma con RC ni pisa ese journal. Antes
la reconstrucción del día siguiente reemplazaba el cierre real por RC (lo
encontró la revisión de #254). El journal es POR MÁQUINA: la rueda entra
cuando un superuser usa ESA instancia; sólo una rueda que ninguna máquina
capturó se rearma con RC. Además (mismo día, limpieza "sin perder
historiales"): `consolidar_journal` y el merge del journal en
`_append_and_save_locked` suben a reales los días que la base tiene SÓLO como
RC si el journal los capturó reales (`_reales_por_dia`); `consolidar_cierres_journal`
reemplaza una partición armada desde la base (`importar_base`: sin volumen /
OHLC / puntas, `_con_datos_vivos`) por la captura en vivo del journal
(`_particion_mejorable`; una partición real nunca se pisa); el catch-up de un
día que la base no tenía escribe también su fila FX (CCL/MEP de la columna
`FX` de las patas en pesos); el banner dice "consolidado desde el journal
local … filas reales (no RC)"; y `_prune_journal` ya no poda por edad a
secas: a los 90 días borra un `px_tasas_` sólo si cada clave (symbol, Código)
del journal que pasa el `dropna(_REQUIRED)` está en la base y cada una REAL
está en la base como real (`_journal_contenido_en_base` +
`_claves_reales_base_cached`; por CLAVES, no por conteos: dos cuentas con
permisos de market data distintos tienen símbolos distintos con iguales
conteos), y un `cierre_` sólo si la partición tiene todos sus símbolos y, si
el journal tiene datos vivos, también ella (`_cierre_contenido`). Regresión:
`tests/test_journal_real_no_se_pisa.py`.
`auth.marcar_visto` corre en el
middleware (cookie y token de Excel, ~100 ns, memoria del proceso),
`auth.writer_presente()` resuelve el rol al momento, y
`historico_writer.writer_estado()` / `es_writer()` reemplazan al flag en
`save_today`, `consolidar_journal`, `reconstruir_cierre`, la recaptura, los
journals de cierres y `cierres.importar_base`; sin presencia la instancia
sólo journalea y el chip (`writer_motivo`), /admin y `base_check` dicen por
qué. `_reconstruir_al_arrancar` espera hasta `_ESPERA_WRITER_S` (5 min) a
que entre un superuser. La captura headless (`tools/cierre.py` →
`_WRITER_HEADLESS`) y `AUTH_ENABLED=0` deciden por el flag, como siempre.
Regresión: `tests/test_writer_por_rol.py`.
**Copias en conflicto y archivos viejos** (07/10, tarjeta de /admin,
`services/copias.py`): OneDrive deja al lado del archivo compartido la versión
perdedora con el nombre de la máquina (`…-NOTEBOOK-RC.xlsx`, `(conflicted
copy …)`), la app aparta `.corrupto-<fecha>`, el backfill deja `.bak-<fecha>`
y una escritura cortada un `.<pid>-<n>.tmp`. `carpetas()` = carpeta de la app
(+ `data/`), Delta Bases, `cierres/<año>`, Carteras y el journal local;
`clasificar(nombre, vecinos)` decide por nombre (principal = el archivo con
la misma extensión cuyo stem es prefijo, separado por `-`/espacio/`(`; un
punto NO: `cer_completo.generated.csv` no es copia) y `escanear()` es listdir +
stat (µs). "Revisar" (`analizar()`, executor) lee cada copia y su principal
(`stats_de`, cache por mtime+tamaño; una copia Excel de un año tarda
segundos) → filas / ruedas / desde-hasta / reales y el veredicto: `aporta`
True = tiene ruedas que la principal no (botón "Incorporar": `incorporar()`
mete SÓLO esas ruedas por el camino de siempre — `append_and_save(…,
ignorar_regresion=True)` para px/tasas, también las ruedas que la base tiene
sólo como RC; `escribir_fx` para FX; `append_acciones(gana_previo=True)` para
acciones), False = se PROBÓ que todo lo suyo está en la principal ("Borrar las
que no aportan"), None = revisar a mano. **Contención estricta** (15/10, "sin
perder historiales"; antes comparaba fechas y totales y daba por borrables una
copia con precios reales de un día que la principal tiene sólo como RC, una
copia FX con una celda de caución de más, un apartado ilegible o un temporal
legible): `_contencion(copia, principal)` (memo por las firmas) compara la
FILA ENTERA en todas las columnas de la copia (px/tasas incluidas las
métricas: una TIR corregida a mano es historia; una columna que la principal
no tiene → None) y el historial FX CELDA POR CELDA (una columna que la
principal no tiene = celdas vacías). `_norm`: números redondeados a 8
decimales, un número guardado como texto ("1790105400000") = el número,
fechas / instantes a ISO completo. Sólo si se lee TODA la copia
(`_una_tabla`: parquet o xlsx de UNA hoja; nunca .xlsm — "Delta -
Especies-PC.xlsx" con la edición en la segunda hoja salía "no aporta"). La
principal se lee UNA vez por firma para todas sus copias (`_memo_principal`)
y, si es un xlsx con espejo fiel, desde el parquet (`_fuente_principal`). Un
temporal de tabla ilegible (escritura cortada) sí es False; uno legible se
compara como una copia; un apartado `.corrupto` ilegible queda None (puede
tener datos recuperables a mano); JSON / jsonl (auth_store, pizarra,
oms_audit…) siempre None. `borrar()` re-valida en el momento (adentro de una
carpeta escaneada y clasificado como copia: nunca un principal) y loguea
quién/qué. GET `/admin/copias` pinta lo ya revisado (`solo_cache`) sin leer
nada; `base_check` usa el mismo escaneo (`resumen_bases`). Regresión:
`tests/test_copias.py`.
`HISTORICO_RECONSTRUIR=0` apaga lo automático. `_fecha_dato`: ISO sin zona =
hora BA y un instante 00:00Z es sello de FECHA (no las 21:00 BA del día
anterior). Regresión: `tests/test_cierre_reconstruccion.py`.
**Celdas basura en el Excel** (28/09): cuando el espejo no es fiel y hay que
leer el xlsx, una celda con TEXTO en una métrica deja la columna `object` y
un entero gigante (TIREA 1e+20 que dejó algún calc) queda como `int` de
Python → `to_parquet` moría con "PyLong is too large to fit int64" y con eso
TODO guardado (cierre, consolidación del journal, reconstrucción).
`espejo.normalizar_numericas` (`espejo.COLS_NUMERICAS`; pandas importado
adentro, el módulo sigue stdlib puro) corre antes de CADA escritura de un
espejo: writer (`_leer_base` Excel, `write_journal`, `_append_and_save_locked`
vía `_normalizar_numericas`), lector (`historico_byma._regen_parquet` — antes
"no pude regenerar el parquet" y releía el xlsx entero en cada carga) y
`bymaapi._guardar_excel_directo`: texto → NaN (la fila cae en el dropna de
métricas del writer), entero → float64, warning con código/fecha/valor de las
celdas para limpiar el Excel; una columna ya float64 no se toca (costo cero
por el espejo). Regresión: `test_append_tolera_celdas_basura_en_el_excel`,
`test_regenera_el_espejo_con_celdas_basura_en_el_excel`,
`test_guardar_directo_tolera_celdas_basura`.
**Columnas de texto mezcladas** (09/10): `espejo.normalizar_texto`
(`COLS_TEXTO` = symbol / Código / Price Source / Price Date → dtype `string`)
corre junto a `normalizar_numericas` en `historico_byma._regen_parquet` y en
el writer: el writer escribe `Price Date` como texto ISO pero bymaapi / una
celda tocada a mano la dejan como FECHA de Excel, y con str + datetime en la
misma columna `to_parquet` moría ("Expected bytes, got a 'datetime.datetime'
object") → esa máquina quedaba sin espejo y releía el xlsx en cada arranque
(PC de un compañero). Regresión:
`test_regenera_el_espejo_con_price_date_mixto_en_el_excel`.

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

## Cauciones BYMA — overnight por calendario y tira de Tasas (09/10)

`services/cauciones.py`. El overnight del riel / Inicio es el plazo del
CALENDARIO: `_overnight_n()` = (próximo hábil después de la rueda) − rueda →
1D normal, 3D un viernes, 4D un viernes con el lunes feriado (09/10/2026) o un
jueves con viernes feriado; sábado / domingo / feriado cuentan la última rueda.
`rail_pick(moneda, calendario=True)` muestra ESE plazo: operado hoy, o su
cierre previo (`es_cierre`), o `sin_dato` si el store no lo tiene; si el plazo
del calendario no está en el store y OTRO 1D–4D operó HOY, gana el que operó
(un feriado que `holidays` no trae); nunca el cierre viejo de otro plazo (el
09/10 el riel mostraba "3D · cierre previo" con el 3D sticky del martes).
`calendario=False` = la heurística por volumen entre 1D–4D de siempre: la usa
`hist_row` (la serie diaria lleva lo que de verdad operó). La pestaña Tasas
arma la tira con `tira_rows`: 1D–7D SIEMPRE (`TIRA_FIJA`; fila `sin_dato` =
"hoy no hay", con el cierre previo si lo hay; sólo puntas = fila normal sin
tasa) y de 14D en adelante sólo los que operaron hoy (tasa viva + volumen > 0;
un volumen sticky de otra rueda no cuenta porque su last ya se degradó a
cierre); `es_overnight` pone el tag `o/n`. Medido (store sembrado, tick por
request): `/tasas/table` p50 2,2 · p95 2,6 ms; `/dolares/rail` p95 2,6 ms.
Regresión: `tests/test_cauciones.py` (fixture `overnight(n)` fija el
calendario: la suite corre cualquier día).

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
**Ruido que NO va al log** (29/09): `main._QuietPolls` calla el access-log de
los paneles live (`md-update`: `/curves/table`, `/mercado/rows`, `/yas/market`,
libros, `/market/health`, …) SÓLO en 2xx/3xx — un 4xx/5xx sale igual (es la
única señal de que un panel se rompió); una pestaña de Curvas sola escribía
~430 `GET /curves/table → 200` por rueda. `errores._FiltroProactor` también
filtra el "ConnectionClosedError exception in shielded future" de websockets
(keepalive timeout): `primary_ws` loguea `disconnected: …` en la línea
siguiente con el mismo motivo.

**Revisión 29/09 — lo que no vuelve** (`tests/test_revision_2909.py`):
`/graficos` no arma el SVG server-side (la página dibuja con charts.js; el
pricing + fit NSS con scipy corría en el event loop para tirarse) y
`/graficos/svg`, la matriz de forwards (`_matrix_async`, N² por tick con la
pestaña abierta) y el form de Nueva especie (`build_ficha_from_form` +
`adhoc.register`) van al pool. `append_acciones` NO sigue con `prev=None`
si el parquet es ilegible y no se pudo apartar (pisaba la historia con las
filas de hoy); reintenta la lectura una vez antes de darlo por corrupto.
`cierres.particiones(strict=True)` en `importar_base` / `prime`: un error al
listar no se lee como "no hay particiones" (el backfill las pisaba con filas
sólo-base). `escenario_prefs._load_all(strict=True)` / `alertas._load(
strict=True)` en los que escriben: archivo ilegible → OSError, no se
reescribe con sólo la entrada del que guardó. `auth`: el PBKDF2 de
`create_user` / `set_password` / `reset_with_token` corre FUERA de `_lock`
(`_perfil_para_clave` + `_aplicar_clave`; el reset re-chequea el token bajo
el lock: sigue siendo de un uso). `instruments.detail`: cache acotado
(`_MAX_CACHE`, el símbolo lo arma el usuario) y por contexto de broker.
`curves.build_curve_codes` / `curve_key_for` / perfil de vencimientos de
Posiciones: `hoy_ba()`, no `date.today()`.

## Feed Primary — símbolos rechazados (cache local)

matrizoms rechaza el `smd` ENTERO si un símbolo del lote es inválido y
`primary_ws` reintenta el lote de a uno para conservar los válidos. Con
~500 símbolos del universo que el broker no lista (ONs viejas, plazos CI
sin rueda) cada arranque pagaba ~130 lotes rechazados + 500 reintentos
(30-40 s sin feed para los válidos de esos lotes, y solía terminar en un
keepalive timeout). Los rechazados quedan ahora en
`%LOCALAPPDATA%\bonos\primary_rechazados.json` (Mac/Linux
`~/.local/share/bonos/`), **por host** y con la fecha del rechazo: el
cliente los carga en `__init__` y el primer subscribe ya sale sin ellos;
una entrada vence a los `REJECTED_TTL_DAYS` (7) y se vuelve a probar (una
emisión nueva que el broker lista después no queda muda para siempre). UNA
escritura por tormenta (coalescida 3 s, en el executor, atómica) y flush en
`stop()`. `PRIMARY_REJECTED_CACHE` = ruta del archivo; `0` apaga (la suite
corre con 0 vía `conftest`). Regresión:
`test_marketdata.test_rechazados_persisten_por_host_con_ttl`.
**Plazos de caución = validez por día** (09/10): `MERV - XMEV - PESOS|DOLAR -
nD` existe sólo cuando hoy+n es hábil (4D: lunes, jueves y el viernes previo
a feriado del lunes; 1D nunca un viernes; 7D no si cae en feriado). El broker
los rechaza ese día y el cache de 7 días los dejaba mudos justo cuando sí
operaban: el viernes 09/10 la tira mostraba 1D–7D "hoy no hay" con sólo
14D/21D vivos (los únicos plazos que no fueron inválidos ningún día de la
semana) mientras el 4D operaba 912.000 M. `_es_diario(symbol)`: esos
símbolos NO entran a `_rejected` ni al JSON (un cache viejo con ellos se
ignora al cargar), van en `smd` DE A UNO (su rechazo no voltea el lote de los
demás), un rechazo los deja en `_rechazo_diario` con cooldown
`REPROBAR_DIARIO_S` (30 min) y `reprobar_pendientes()` (task
`_reprobar_loop`, cada `REPROBAR_CHECK_S` = 60 s, sólo conectado y dentro de
`_REPROBAR_HORAS` = 7–18 BA) los vuelve a pedir; al cambiar el día (BA) pide
TODOS los plazos de nuevo, y también reprueba con el proceso arriba los
rechazados persistentes cuya entrada venció (antes sólo al reiniciar).
`stats()["rechazados_hoy"]` los lista en `/market/diag`. Regresión:
`test_marketdata.test_plazos_de_caucion_rechazados_se_reprueban_y_no_van_al_cache`.
**Tormenta de rechazos** (09/10): una cuenta en LBO quedó con 2717 de 2903
símbolos en el cache (media universo o más NO son símbolos inválidos: es la
sesión / los permisos de market data de esa cuenta) → cada reconexión
suscribía 186 y el feed mostraba "precios viejos" toda la semana. Umbral
`_TORMENTA_MIN` (300) y `_TORMENTA_FRAC` (0,5 del universo suscripto):
`_chequear_tormenta` corta la recuperación de a uno, `_guardar_rechazados`
deja el host VACÍO en el JSON, `_connect_and_read` descarta un cache que ya
viene así (`_cache_es_tormenta`), `reprobar_pendientes` al cambiar el día
olvida todo y pide el universo entero, y el botón **«Reprobar símbolos
rechazados»** de /conexion (`POST /conexion/reprobar` →
`olvidar_rechazados()`, cualquier usuario logueado) lo hace al toque; la
página avisa la tormenta con el `last_error_desc` del broker. Regresión:
`test_marketdata.test_tormenta_de_rechazos_no_se_persiste_y_se_reprueba`,
`test_conexion.test_conexion_reprobar_olvida_rechazados`.
**Reconexión = pase nuevo de recuperación por lote** (09/10):
`_retried_individually` / `_retried_no_oi` se limpian al conectar
(`_reset_reintentos` en `_connect_and_read`); antes nunca se limpiaban y en
la reconexión un lote rechazado por un símbolo que dejó de existir volvía con
`pending` vacío → los 20 símbolos del lote mudos hasta reiniciar, sin log.
Regresión: `test_marketdata.test_reconexion_vuelve_a_reintentar_un_lote_rechazado`.
**Serie diaria de caución vacía 05–09/10** (diagnóstico verificado): fue
esto mismo + el cache por 7 días — `hist_row` exige un plazo 1D–4D con tasa
de HOY y estaban todos mudos; el writer no cambió (CCL/MEP se guardaron). No
hay de dónde reconstruir esos días dentro de la app (RC escribe la fila FX
sin caución a propósito, el journal no tiene lo que no estaba suscripto): se
cargan a mano en `Delta - historico_fx.xlsx` (columnas `caucion_plazo_d` /
`caucion_tna` / `caucion_tna_vwap` / `caucion_monto`, números; el Excel
editado gana al espejo y el próximo autosave mergea sólo SU fecha).

## Add-in de Excel — OMS.MACRO en vivo (01/10)

`=OMS.MACRO(serie; [fecha])` streamea como `OMS.FX`: el snapshot de
`/excel/v1/snapshot` lleva la sección `macro` (`routes/excel._macro_section`
= `_calc_macro` de las 8 series `_MACRO_SNAPSHOT_SERIES`, µs sobre el backup
en memoria, failure-silent como las demás secciones) y `functions.js` la lee
con `macroGet` (`makeStreaming("MACRO", …)`, `options.stream` en
functions.json, `MACRO_ALIAS` = la misma tabla de alias que el server). Un
refresh de la serie en la app (cambio de día, 11:00 / 15:30, A3500 del día)
llega solo a la celda en ≤ 30 s (refresco por edad del poller con la seq
quieta); hasta v24 era una async clásica con memo de 5 min y la celda no se
movía hasta tocarla o Ctrl+Alt+F9. El item `tipo: "macro"` del batch
`/excel/v1/calc` queda para los add-ins con el functions.js viejo cacheado.
El modo cruda escribe `MACRO|<SERIE>` (LAST = valor, CLOSE_DATE = fecha).
Regresión: `tests/test_excel_macro.py` + `excel_getters_harness.cjs`.

## Add-in de Excel — dólar BNA (07/10)

`=OMS.FX("bna_billete_compra" | "bna_billete_venta" | "bna_divisa_compra" |
"bna_divisa_venta")` y la fecha del dato `("bna_fecha")` / `("bna_divisa_fecha")`
(serial de Excel). Pedido del desk SÓLO para el add-in: `services/bna_fx.py`
parsea las páginas públicas del BNA (`/Personas` → tabla `id="billetes"`,
`/Empresas` → `id="divisas"`; fila "Dolar U.S.A", compra / venta es-AR y la
fecha `DD/MM/AAAA` del bloque) con expresiones tolerantes, en un THREAD DE FONDO
1×/hora (10 min si falló), NUNCA en un request; el último dato queda en
`bna_fx.json` de la carpeta LOCAL de la máquina (`estado_local`, ver "Estado
por máquina fuera de OneDrive") y el snapshot (`routes/excel` sección
`bna`, `functions.js` `fxGet`) sólo lee memoria. `BNA_FX=0` apaga el poller
(la suite corre así vía `conftest`), `BNA_FX_URLS` / `BNA_FX_PATH` overrides.
El sandbox de desarrollo no llega a bna.com.ar: el parser está probado contra
un fixture con la estructura conocida de la página (`tests/test_bna_fx.py`) —
si el BNA cambia el HTML, `snapshot()["error"]` lo dice y las celdas quedan
en el último dato guardado.

## Add-in de Excel — patas calculadas en minúscula (15/10)

Las fichas calculadas llevan sufijo en MINÚSCULA (`…v` = pata TAMAR de los
duales: `TMVE8v`, `TXMD8v`, …; `…j` = CER proyectado: `TXMD8j`, …; 49 en el
universo) y `functions.js` — también el que cada Excel tiene cacheado — manda
el código EN MAYÚSCULAS: `OMS.TIREA("TMVE8v"; …)` / `OMS.MARGEN` llegaban como
`TMVE8V` y daban "Bono 'TMVE8V' no encontrado". `bond_universe.resolve(code)`
(exacta primero, después `_upper_map` = {MAYÚSCULAS: código}, O(1); dos códigos
que chocaran en mayúsculas quedan fuera del mapa, nunca se adivina) y
`routes/excel._codigo_calc` lo aplican a TODO item del batch `/excel/v1/calc`
(precio / tir / tna / margen / duration / tr / meta): el resultado lleva el
código de la ficha (`codigo: "TMVE8v"`); un código inexistente sigue en
mayúsculas (mismo error, mismo símbolo de mercado). Sin precio, la pata usa el
last del ticker base (`md_symbol("TXMD8v") = … TXMD8 …`). El arreglo es del
server a propósito: no hace falta reinstalar el add-in. Si un endpoint nuevo
recibe un código tipeado por el usuario, resolvelo con `bond_universe.resolve`
(nunca `.upper()` a secas). Regresión: `tests/test_excel_patas_minuscula.py`.

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
Manual para el desk (orden de decisión, tokens, qué cargar en la base):
`backend/docs/posiciones_clasificacion.md` (el `.gitignore` es una allowlist:
`docs/` en la raíz queda afuera) — si cambia una regla, cambia el manual.

**Pestañas lazy de Históricos** (`hx-trigger="reveal"`): las rutas de pestaña
llevan `@_pestana_resiliente(...)` — una excepción responde 200 con
`partials/historico_tab_error.html` (qué falló + Reintentar) en vez de un 500
que htmx no swapea (el tab quedaba en "Cargando…" para siempre); los
contenedores llevan `hx-request='{"timeout":90000}'` y `app.js` (`lazyFail`)
muestra el mismo alert ante error de red / timeout.

**COMP (Históricos · Comparar, 29/09)**: `services/comp.py` — hasta 10
activos (bonos por código de calc vía `cierres` con fallback a la base,
acciones / CEDEARs / Merval del parquet; mismas fuentes que el price action:
`price_action.serie_de`) alineados a la unión de ruedas, `y` = base 100 en la
primera rueda con dato del rango / variación % / nivel, ÷ FX opcional
(`fx_por_fecha` + `_alinear`), TIR de bonos en % con Δ en pp; `stats` por
activo (inicio, fin, var, máx, mín, caída desde el máx, vol anualizada).
Rutas `/historicos/comp` (controles + `<datalist>` de especies + cuerpo) y
`/historicos/comp/body` (lo que swapea el form: avisos, gráfico, cuadro);
HTML cacheado por (parámetros normalizados, firmas de los archivos) como
Acciones; el cálculo es numpy en memoria (~ms) y corre en el executor. El
gráfico lo dibuja `charts.js initHistComp` con el JSON embebido en el cuerpo
(cero requests extra; colores del payload = punto de la tabla). **Fechas de
los gráficos históricos**: el server manda medianoche UTC por rueda y uPlot
formatea en UTC (`utcTz` / `utcDia`, opción `tzDate`) — con el reloj local
Buenos Aires (UTC-3) etiquetaba un día antes. Regresión:
`tests/test_historico_comp.py`.

**Qué pasó (30/09)**: los segmentos son las categorías de Escenario SIN los
duales que entraron ahí para el multi-activo, más los seis `DUAL_CATEGORIES`
juntos al final (sumar las dos listas a secas mostraba Dual TAMAR/CER, Dual
CER/TAMAR y Dual TAMAR/DLK dos veces). **Tilde por bono**: cada fila del
detalle lleva sus valores en `data-*` (dprice / dtir / dtem / cup / tir1 /
tem1 / dur, fracciones) y un checkbox `.sem-chk`; `app.js` (`qpSegStats` /
`qpSegCells`, puras) rehace las celdas `.sem-c-*` del encabezado con la misma
media simple del server (`_avg_seg`) sin los destildados — cero requests; la
selección vive en `localStorage` (`qp_excl`, por `data-seg`) y se re-aplica
tras cada swap. El CSV y el gráfico "antes/ahora" siguen con todos los bonos.
Regresión: `tests/quepaso_harness.cjs` (vía `test_historico_semanal`).
**Ventana efectiva**: el inicio es la RUEDA de la base más cercana a
(fin − días), de un lado o del otro (empate → la anterior; la rueda del fin
no vale como inicio), no la fecha calendario ni "la última anterior": con el
hueco de agosto 2026 (05/08 → 31/08 sin ruedas) "1 mes" arrancaba el 04/08 y
medía 57 días. El título dice cuántas ruedas abarca, hay un aviso ⚠ si la
rueda más cercana queda a más de 4 días (`aviso`, `hueco_dias`,
`dias_efectivos`) y cada fila del detalle lleva `p0 → p1` con
las fechas reales cuando no son las de la ventana (`desfasado`: ilíquido sin
dato en la rueda inicial). Un bono sin observación ≤ inicio NO tiene Δ (no se
inventa una desde su primera rueda). Antes "1 mes" podía medir mes y medio sin
decirlo (CER +4,35 % con el mercado en 2-3 %, 30/09). El CSV lleva las
mismas columnas (Precio ini/fin, Fecha ini/fin) y el aviso.

## Inicio y orden de pestañas (07/10)

`auth.TABS` manda el orden de la nav: **Inicio** (`home`, `/inicio`),
Mercado, Curvas, YAS, Futuros, Dólares, Históricos, Gráficos, Posiciones,
**Matriz Tenencias** (`matriz`, antes "Matriz") y recién ahí el resto.
`auth.ALWAYS_TABS = ("home",)`: la ve TODO rol aunque no esté en su
`role_tabs` (`allowed_tabs` / `can_access_path`), y /admin no la ofrece como
checkbox. `/`, el `next` default del login y la marca de la topbar van a
`/inicio`. Regresión: `tests/test_inicio.py` (orden, aterrizaje, básico sin
Inicio en su lista entra igual).

**Inicio** (`routes/inicio.py`, `services/inicio.py`, `templates/inicio.html`
+ `partials/inicio_body.html`): el mercado en una pantalla — Tipos de cambio
(oficial · MEP · CCL · brecha · canje, de `dolares.summary`), Tasas (TAMAR /
BADLAR del macro + caución ARS/USD BYMA del riel + caución ARS/USD MAE),
Mercado (Merval ARS y en CCL, riesgo país, SPY y EWZ cada uno en pesos y,
debajo, en CCL — `inicio._en_ccl`: CEDEAR ÷ CCL, variación contra el cierre
de ayer en CCL, el mismo criterio del Merval; desk 07/10), una tarjeta por
segmento soberano (Globales · Bonares · CER · Tasa fija · Dólar linked ·
TAMAR · Duales) con último · var · var % · TIR · Δ TIR (`delta_yield_bps`)
· TEM · margen (sólo si el segmento lo tiene), Panel líder y futuros de
dólar (contratos en columnas). UNA request live por tick para toda la página
(`/inicio/body`, `seq_cached`): las filas de bonos salen del MISMO cache por
curva y seq que Mercado / Curvas (`curves._rows_en_seq`, en serie para no
ocupar los 8 workers del pool); el resto son lookups en memoria
(`inicio.resumen`, en el executor). Cada tarjeta de bonos muestra hasta
`MAX_FILAS` (10): los más operados hoy (VN; sin VN, efectivo) completados con
los de vencimiento más corto, ordenados por vencimiento, con "+N más → ver la
curva" (el pie habla de la sección principal y linkea a su curva real:
Duales → `mix:dualfija,dualcer,dualdlk`). Duales = patas base (`dualfija` +
`dualcer` + `dualdlk`, un dual por fila); el margen de la pata TAMAR
(`dualtamar`, código base + `v`) se cruza a la pata fija y DLK, NUNCA a la
CER (no le corresponde — desk 07/10; tooltip propio de la columna). La pata
TAMAR (v) de los duales CER va como SUBDIVISIÓN de la tarjeta TAMAR
(`SUB_DUALES_V`, curva `dualtamar_cer`; `secciones` de la tarjeta, cada una
con su tope de filas, su "+N más" y su curva — /curves sólo reconoce las
`CurveDef` y las combinadas `mix:a,b`, así que `duales` y `dualtamar_cer`
linkean como `mix:`) con su TIR / TEM / margen. Las
tablas son `.cashflows` para que el
diff de flashes las vea (id propio por tarjeta: el ratchet de anchos de
app.js keyea por id + cabecera). Medido con el
store sembrado (bench_tick, 2000 símbolos): hit 0,9 ms; tick con rebuild
p50 ≈ 14 · p95 ≈ 20 ms.

**Caución MAE en Inicio** (13/10): `inicio._es_usd` decide por el código
CRUDO de MAE con la misma tabla que Tasas (`mae._moneda_lbl`: 'D' / 'X' =
dólar, '$' / 'T' = pesos). Antes buscaba 'USD'/'DOLAR' en el texto: la 'D' no
matcheaba, la caución en dólares pasaba por pesos y la tarjeta "Caución ARS ·
MAE" mostraba 1 % (la de dólar) con la de USD en "—". `mae.status()["cauciones"]`
lista crudas las que manda la API (plazo · moneda · tasa; /admin · Salud):
si ahí no hay una de pesos, MAE no la publicó — la UI no filtra por moneda.
Regresión: `test_inicio.test_mae_pick_distingue_pesos_de_dolar_por_codigo_crudo`.

**Riesgo país** (`services/riesgo_pais.py`): ArgentinaDatos
(`/v1/finanzas/indices/riesgo-pais[/ultimo]`, la misma API de
`backfill_fx`), thread daemon cada 30 min (10 min si falló), NUNCA en un
request; historia reciente en `riesgo_pais.json` de la carpeta LOCAL de la
máquina (`estado_local`) para la
variación contra la observación anterior y para mostrar el último dato sin
red. Primer arranque sin dos puntos locales → serie completa una vez; después
`/ultimo`. `RIESGO_PAIS=0` apaga el poller (la suite corre así vía
`conftest`), `RIESGO_PAIS_URL` / `RIESGO_PAIS_PATH` overrides.

**Pizarra por usuario** (`services/pizarra.py`, rutas `/inicio/pizarra*`,
`partials/inicio_pizarra.html` + `inicio_cotizacion.html` +
`_pizarra_tools.html`): debajo del resumen, cada usuario arma sus cuadros —
**libro** (el mismo `partials/mercado_book.html` de Mercado / Órdenes, el
libro COMPLETO embebido con `piz` = sin auto-refresh propio ni chips de
métrica, botones mover / quitar en el título y "Mi posición" plegada por
default — en Mercado / Órdenes sigue abierta; la métrica `y` es por usuario y
vale para todos sus libros; ocupa dos columnas de la grilla, `.piz-libro`) o
**cotización** (cuadro estilo BYMA: último · puntas con VN · var · TIR
last/bid/offer · TEM · dur · máx/mín · apertura/cierre · volumen, de
`curves._row_for_code(book=True)`). Grilla `.piz-grid` minmax 320 px. Hubo
una versión "compacta" (escalera de 4 columnas, 280 px, 4-5 por fila) que el
desk rechazó el 07/10: NO volver a achicar los cuadros sin pedido explícito.
Default: sin cuadros. Persisten en `data/pizarra.json` por username
(`_local` sin muro), tope 24, sin duplicados, código validado contra el
universo; `PIZARRA_PATH` override (la suite lo apunta a un tmp). El formulario
de alta (input + `<datalist>` del universo) y los chips viven FUERA del
contenedor live (un input adentro perdería el foco en cada refresh); cada
acción (agregar / mover / quitar / métrica) devuelve la pizarra entera. Render
= UN request por tick para todos los cuadros: `routes.curves.book_context`
(extraído de `mercado_book`, también lo usa `/ordenes/quote`) por libro, las
cotizaciones en una sola tarea del pool, y memo por usuario keyeado por (seq
del store, firma mtime+tamaño del JSON) — un cuadro recién agregado se ve en
el próximo refresh con la seq quieta, y la firma también detecta otra
instancia escribiendo el mismo archivo. Medido con 6 libros + 4
cotizaciones (store sembrado): hit 1,6 ms; tick con puntas de un cuadro
cambiando p50 ≈ 10 · p95 ≈ 14 ms; tick de otro símbolo p95 ≈ 7 ms. Regresión:
`tests/test_inicio_pizarra.py` (servicio, HTTP por usuario, memo, el libro de
Mercado sigue igual).

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
- **"Conectando" ≠ "Feed caído"** (09/10): `PrimaryWS.connecting` = sesión
  abierta + lector vivo + sin socket hace menos de `CONNECT_GRACE_S` (10 s;
  `_disconnected_since`); `feed_health.snapshot()["connecting"]` y
  `feed_down` sólo cuando NO está conectando. `/conexion/login` espera
  acotado (`_esperar_conexion`, 3 s) el handshake antes de renderizar, la
  tarjeta dice "⏳ Conectando…" y `#conn-status` sondea `GET /conexion/status`
  cada 10 s — antes el partial, renderizado un instante después de
  `start()`, mostraba "⚠ Feed caído" pegado al "✅ Conectado" y el desk volvía a
  apretar Reconectar (`old.stop()` tira un WS sano): ese era el "se me cae
  todo el tiempo" de la PC de un compañero. El SSE (`/market/events`) deja
  UNA línea `[sse] <cliente> cerró el stream tras N s · M eventos` al cortarse
  (el access log sólo ve la apertura y `_QuietPolls` la calla). Los launchers
  corren uvicorn con `--timeout-keep-alive 75` (default 5 s: Chrome reutiliza
  sockets ociosos minutos y pegaba `ERR_CONNECTION_RESET` esporádicos).
  Regresión: `test_feed_health.test_conectando_no_es_feed_caido`,
  `test_conexion.test_conexion_status_se_refresca_y_espera_el_handshake`,
  `test_marketdata.test_connecting_es_gracia_de_handshake_no_feed_caido`,
  `test_live_engine.test_sse_emits_baseline_and_tick`.
- **Motor live endurecido** (09/10, `app.js`): `renderEstado(advanced, rtt)`
  (dot + meta; prioridad down > stale > live > conectando > idle) lo llaman
  `handleSeq`, `checkHealth` y un timer de 5 s — antes un cambio de salud con
  el mercado quieto (SSE sin seqs) no se veía y `live → idle` nunca pasaba;
  `checkHealth` va con `fetchTexto` (plazo 6 s) y generación (una respuesta
  vieja no pisa), `connecting` del server = dot 'idle' "Conectando al
  broker…"; `linkDown` (polling con 3 fallos / SSE reconectando) deja el dot
  en 'off' y el primer seq que vuelve dispara un health ya. **SSE**: watchdog
  de CONNECTING — sin `onopen` ni mensaje en 8 s (pool de 6 conexiones
  HTTP/1.1 lleno por pestañas duplicadas, proxy que no streamea) se cierra y
  cae a polling con "Sin stream del feed — sondeando"; `arm()` no abre nada
  con la pestaña oculta y `dispatchUpdate` / `htmx:beforeRequest` cancelan el
  `md-update` oculto. **`htmx.config.timeout = 30 s`** (antes 0 = nunca: un
  XHR colgado dejaba el panel con datos viejos en silencio) + toast en
  `htmx:timeout` como el de `sendError`; las acciones largas llevan
  `hx-request='{"timeout":600000}'` (guardar base, reconstruir / reponer /
  aceptar, Copias en conflicto) y Históricos conserva sus 90 s. Regresión:
  `tests/live_engine_harness.cjs` casos 6-11 (health sin seq, health colgado,
  SSE colgado, SSE sano, pestaña oculta, plazo htmx) vía
  `test_auditoria_eficiencia`.
- **Pestaña vieja tras un deploy** (09/10): `/market/health` lleva `asset_v`
  (la misma versión de estáticos que `?v=` de los templates, `app.state.asset_v`)
  y la página la pone en `<body data-asset-v>`; `app.js checkVersion` (en el
  sondeo de health, ~15 s) muestra un toast fijo "Hay una versión nueva ·
  click para recargar" una vez por versión y NUNCA recarga sola (puede haber
  un ticket a medio cargar). Era el "se me cae todo el tiempo" de una PC del
  desk que en incógnito andaba bien: JS de ayer contra el server de hoy.
  Regresión: `test_feed_health.test_market_health_lleva_la_version_de_los_estaticos`.
- **Libro** (`partials/mercado_book.html`, `/mercado/book/{code}`, también
  embebido en Órdenes vía `/ordenes/quote`): se swapea entero en cada
  `md-update`. Por eso el dim de carga
  (`[data-flash-scope]:not([hx-trigger*="md-update"]).htmx-request`) EXCLUYE
  los paneles live — a 1 request/s parpadeaba. El botón ⧉ de copiar tabla
  que inyecta `app.js` va dentro de un `.tbl-wrap` cuando el padre es
  grid/flex (`.book-grid`): un hermano suelto ocupaba una celda de la grilla y
  apilaba bid y offer. Celdas `data-noflash` (Acum) no entran al diff de
  flashes. **Métrica por nivel** `?y=tirea|tem|tna|margen`: sale del mismo
  dict de `pricing.metrics_for_market_price` que ya daba la TIREA (costo
  cero); chips `data-book-y` en el título, elección en `localStorage`
  (`book-y`) que `app.js` agrega en `htmx:configRequest` a todo pedido del
  libro sin `y=`; Margen sólo si el bono tiene benchmark (si no, cae a
  TIREA). Regresión: `tests/test_mercado_book_switch.py`.
- **Copiar gráfico (⧉)** (`app.js`, `copySvg`): un SVG del server que pinta
  por CLASES (`.fut-chart .pa-*`, `.fc-*`, `.hc-*`) o con `var(--x)` no puede
  serializarse a secas — la imagen suelta no ve el CSS de la página y cae al
  default de SVG (relleno negro, sin stroke, serif). Se clona con el estilo
  CALCULADO inline (pintura + tipografía, `display:none` respetado) y recién
  ahí se rasteriza; sólo al click, ~1 ms por 100 nodos. Regresión:
  `tests/chart_copy_harness.cjs` (JS real en Node).
- **Gráficos · tabla de bonos** (`#graf-tabla`, 25/09): cajón colapsado
  abajo de todo con los puntos del chart en cuadro (bono · vto · calif. ·
  industria · mon. · precio · fuente · TIR · TNA · TEM · dur [· margen]).
  `charts.js` la arma desde el MISMO payload de `/graficos/data` (cero
  requests: `grafTablaRows` / `grafTablaHTML`, funciones puras expuestas en
  `window` para `tests/graficos_tabla_harness.cjs`), en el orden del eje x y
  con cada comparación como bloque propio (columna Curva; la principal con
  el label del selector). `meta[code]` del payload lleva la ficha estática
  `vto/cal/ind` (`curves._graf_ficha`, de `pricing.bond_meta`, también con
  fuente CAFCI). Colapsada sólo actualiza el conteo; abierta se rearma en
  cada refresh (~ms). Estado en `localStorage` (`graf_tabla_open`); el ⧉ de
  app.js la copia como celdas. Regresión: `tests/test_graficos_tabla.py`.
- **Celda Var %** (`.var-cell`, 29/09) en Curvas / Mercado / Acciones: número
  en color fuerte (`--up-strong` / `--down-strong` por tema, peso 650) +
  barrita de magnitud bajo el número (`::after`, gradiente `currentColor`
  hasta `--vw`, anclada a la derecha). `--vw` = |var| / tope (2 % bonos, 5 %
  acciones) y la clase salen de los filtros `var_w(cap)` / `var_cls` de
  `locale_ar` (0,00 % → sin clase ni barra). Cero nodos extra: el diff de
  flashes (`textContent`) y el ⧉ no la ven; vive en el padding inferior de
  `.cashflows`, la fila no crece. Reemplazó el fondo translúcido `var_bg`
  que armaba `curves._row`. Regresión: `tests/test_table_ux.py`.
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
- **Acciones / CEDEARs** (`partials/equities_table.html`, `services/equities.py`):
  las columnas Open / Close / Low / High / Rango llevan `col-oclh` (el toggle
  OCLH de la página es CSS puro: sin la clase no hacía nada, 30/09). El panel
  Líderes (y Líder + General, badge `I`) arranca con la fila del índice
  Merval (`equities.merval_row`: nivel por IV, OCLH del feed, var vs cierre;
  sin puntas / VWAP / volumen, no abre libro, no cuenta como especie). Va
  DESPUÉS de `_finish_rows` y con `data-pin`: el sort por columna de `app.js`
  deja las filas `tr[data-pin]` fijadas arriba (sirve para cualquier tabla
  `data-sortable`). Regresión:
  `test_tape_equities.test_panel_lideres_encabeza_con_el_merval_y_oclh_ocultable`.
- **Recuadro quieto al actualizar (02/10)**: el flash de un tick es SÓLO
  color (`.tick-up` / `.tick-down`: nada de `transform` / `font-weight` /
  `padding` — hubo un `tick-pop` de escala que agrandaba la celda en cada
  tick); el botón ⧉ (`.tbl-copy`, que app.js inyecta ADENTRO del swap) tiene
  alto neto cero (`height: 14px` + `margin-bottom: -14px`; con -18 px la
  tabla saltaba 4 px por un frame en cada swap completo — acciones = cada
  tick) y se inyecta en `htmx:afterSwap` (antes del paint); el dim
  `.htmx-request` excluye `[data-delta-scope]` (Mercado no lleva md-update
  en su trigger); el `scrollLeft` de cada `.table-scroll` del target se
  conserva a través del swap (app.js, "Scroll horizontal…"); `.live-meta`
  con `min-width` (la métrica del feed corría la nav). **Anchos de columna
  congelados** (app.js "Anchos de columna estables", tablas `.mercado-table`
  / `.curve-table`): con layout auto la columna mide su celda más ancha y
  cuando el valor más largo cambia de dígitos corre todo lo de la derecha
  (medido: VWAP 85 → 73 px). Se miden los th una vez, se fijan como `width`
  y el PADRE de la tabla lleva `data-cols-fijas` (CSS → `table-layout:
  fixed`); los anchos sólo crecen (ratchet: una celda que desborda,
  `scrollWidth > clientWidth`, re-mide y toma el máximo), se reaplican en
  `htmx:afterSwap` y tras el delta por filas, y se olvidan en `resize`.
  Gotcha htmx 2: al asentar el swap (settle, 20 ms) re-escribe los atributos
  de los nodos nuevos CON id tal como vinieron del server — un `style`
  inline puesto en afterSwap sobre `<table id=…>` desaparece; por eso el
  atributo va en el padre (sin id) y los th (sin id) conservan su width.
  Medición:
  `python backend/tools/dev_ticks.py 8765` (server sembrado con ticks) +
  `python backend/tools/flicker_probe.py http://127.0.0.1:8765/mercado 45
  1920 1080 [lideres]` (Playwright): alto del card, anchos de columna,
  frames sin ⧉, opacidad, scrollLeft y layout-shifts por frame; otro panel
  live con `PROBE_SCOPE=#forwards-matrix … /forwards` (la matriz de
  forwards usa las mismas clases y el mismo ⧉: mismo salto de 4 px antes,
  0 después). Regresión: `tests/test_mercado_sin_saltos.py` (antes/después
  en el docstring).
- **Libro (Mercado / Órdenes) quieto y con órdenes propias (02/10)**: el
  card del libro se reemplaza A SÍ MISMO (`hx-target="this"`,
  `hx-swap="outerHTML"`) en cada md-update. **Gotcha htmx 2**: en
  `htmx:afterSwap` el `detail.target` es el nodo VIEJO ya fuera del DOM y el
  evento se dispara sobre el NUEVO (`evt.target`) — el flash diffeaba contra
  el viejo (el libro NUNCA flasheaba) y el congelado de columnas no lo veía.
  Los tres handlers (flash, anchos, scrollLeft) usan el nodo vivo
  (`isConnected ? detail.target : evt.target`). El freeze cubre toda tabla
  `.cashflows` de un `[data-flash-scope]` (puntas y tenencia del libro) y
  saltea cabeceras con colspan/rowspan; CSS `[data-cols-fijas] > table`.
  **Profundidad fija**: las dos puntas se rellenan con `tr.depth-pad` hasta
  5 filas (o más si el broker manda más) → el card no cambia de alto cuando
  entra o sale un nivel. **Órdenes propias**: `oms.own_levels(symbol)` →
  `{buy: {px: VN}, sell: {…}}` desde `_OWN` (lo que esta app envió y el
  broker aceptó: `recordar_propia` en `place`, baja por estado final del
  seguimiento / `cancel` OK / lista del broker que ya no la trae) y
  `_ACTIVES` (última `rest/order/actives` por comitente: la carga el panel
  de Órdenes y `maybe_refresh_activas()` en background desde el libro,
  throttle 15 s, NUNCA en el request; vencida a los 10 min). `marcar_niveles`
  deja `l.own` y el template pone `own-order own-buy|own-sell` (negrita,
  verde / rojo, ● y tooltip con el VN propio). El libro se cachea por seq
  (`seq_cached`): una orden nueva se ve en el tick siguiente (≤ 2 s).
  Tests: `tests/test_book_ordenes_propias.py`. Para mirar un libro con ticks
  constantes: `DEV_TICKS_FOCUS=S13N6 python backend/tools/dev_ticks.py 8765`
  (alterna un tick de sólo tamaños —flashea— con uno de precios).

## Noticias — marquesina (09/10)

`services/news.py` (stdlib, thread daemon cada 120 s, NUNCA en un request).
El desk veía sólo Ámbito y Bloomberg Línea: los CDN de Infobae / Cronista
devolvían 403 al User-Agent "raro" y las rutas de RSS cambian. Ahora: UA de
navegador real; por fuente una lista de URLs alternativas (la primera que
responde queda fija) y backoff exponencial (2 → 16 ciclos) para la que no
responde; **GET condicional** (`If-None-Match` / `If-Modified-Since` → 304 =
cero bytes y se conserva el último lote de esa fuente) + `Accept-Encoding:
gzip` + tope `_MAX_BYTES`; fuentes AR (Ámbito, Cronista, Infobae, Bloomberg
Línea, La Nación, Clarín, iProfesional, Perfil, Página/12), **Google News**
(una búsqueda del mercado local, `when:1d`, UN pedido que agrega Reuters /
Bloomberg / etc.; la fuente real sale de `<source>` y el título pierde el
" - Fuente") y Yahoo Finance / CNBC / MarketWatch al final. La lista se arma
por **round-robin** entre fuentes (variedad en la marquesina) con dedup por
título; `items()` da 30. `status()` = por fuente: status / URL / ítems /
bytes / fallos (tarjeta "Noticias (RSS)" en /admin · Salud) y el log deja
una línea cuando cambia el estado de alguna fuente. Marquesina: la duración
de la animación es `max(90, 6 × titulares)` s (antes 90 s fijos: con más
fuentes corría más rápido; el desk la quería más lenta). Las URLs no se
pueden verificar desde el sandbox (el proxy corta todo salvo GitHub/PyPI):
las que no respondan en la máquina del desk se ven en /admin y se corrigen
en `_FEEDS`. Regresión: `tests/test_news.py`.

## Matriz de tenencias — vistas (09/10)

`routes/posiciones._matriz_ctx(view)`: `vn` (nominales), `pct` (% sobre PN,
1 decimal) y `vnpct` = **VN y %** en la misma celda, texto plano
"772.000.000 5,0%" (sin PN del fondo queda sólo el VN; sin tenencia, vacía) —
pedido del desk para leer tamaño y peso de un vistazo. El ancho de columna
sale del texto más largo, así que esa vista ensancha las columnas; el HTML
va al mismo `_MATRIZ_CACHE` por (generación, familia, vista, visibles). Un
test que pisa `positions._cache` a mano tiene que vaciar ese cache (es
orden-dependiente si no). Regresión: `test_posiciones_galileo.test_http_matriz_markup_compacto`.

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

## Auditoría 30/09 — trabajo por tick compartido e integridad del cierre

Auditoría externa sobre `fcc335f` (100 llamadas por endpoint, "tick" = un
update del store antes de cada request, ráfagas de 100 ondas × 24 clientes,
heartbeat del loop). Regresiones en `tests/test_auditoria_gpt.py`.

- **Delta de Mercado** (`/mercado/rows`, `routes/curves.py`): `_DELTA_MEMO` +
  `_DELTA_INFLIGHT` — UN render + UN gzip (nivel 5, en el executor) por (query,
  since, order, seq, ym); N pestañas sobre la misma tabla comparten la respuesta
  ya comprimida (antes 24 clientes × 30 filas: p95 261 ms; compartida, 48 ms).
  `GZipMiddleware` deja pasar lo que ya trae `Content-Encoding`.
- **Curvas por fila**: `_curve_rows_html` memoiza el HTML de cada `<tr>`
  (`_CROW_MEMO`, key = `_rk` que deja `_rows_for` = (key del `_ROW_MEMO`, seq
  del símbolo) + plazo + fracción de volumen). La macro
  `partials/curve_row.html` es la ÚNICA fuente de la fila (tabla completa y
  memo salen idénticas, `compact` por fila): un tick re-renderiza sólo su
  fila. Si agregás columnas a Curvas, van en la macro. **Mercado igual**
  (07/10, `_mercado_rows_html` / `_MROW_MEMO`, key = `_rk` + plazo/leg/fuente/ym
  + fracción de nominal): la tabla completa (`/mercado/table`, la que piden
  el `every 30s` y los `X-Full`) rehacía las 163 filas por tick — 46 → 14 ms
  p50 — y el delta (`/mercado/rows`) sale del MISMO memo, así la fila es
  idéntica por los dos caminos y queda cebada para el próximo swap completo.
  Regresión: `test_auditoria_gpt.test_mercado_rerenderiza_solo_las_filas_que_cambiaron`.
  **Matriz de forwards** (07/10): los N² pares salen de numpy (`_forwards_matrix`,
  11 → < 1 ms), el texto/fondo de cada celda se memoiza por valor
  (`_fwd_cell`) y cada fila llega al template como UN string (`cells_html`;
  `_fwd_matrix.html` deja el loop por celda sólo de fallback) — 30 → 17 ms
  p50 por tick en corp_hdmep y sin los picos de 150-190 ms que dejaban
  2.500 celdas de Jinja por request. `cells` (dicts) sigue para los tests.
  Regresión: `test_auditoria_gpt.test_forwards_matrix_cells_html_igual_al_template`.
- **Excel**: `_snapshot_entry` guarda `(seq, at, body, gz)` — un gzip por
  build, servido con `Content-Encoding` si el cliente acepta
  (`_json_gz_response`); `/excel/v1/hist` memo `_HIST_MEMO` por (serie, días,
  versión de la carga macro); `functions.js` `histFn` con promesa por args
  (`histInflight`) y timeout de 20 s.
- **auth copy-on-write**: `_mutar(fn)` copia el store bajo `_lock` (µs),
  aplica la mutación sobre la copia, escribe bajo `_disk_lock` FUERA de
  `_lock` y publica recién con el archivo durable (OSError → memoria
  intacta); `_store()` lee sin lock. `reset_with_token` re-chequea el token
  adentro de la mutación. Nunca sostener `_lock` durante PBKDF2 ni fsync.
- **cierres**: carga degradada — una partición ilegible NO publica una matriz
  parcial como completa: se conserva la íntegra anterior y se reintenta a los
  60 s (`completa` / `retry_at` / `degradada_sig`). La firma incluye los mtimes
  de las carpetas por año (corregir una partición vieja invalida) y se memoiza
  por esos mtimes (`_sig_memo`: las rutas de Históricos la piden en cada
  request; el listado completo sólo cuando cambió una carpeta). Recarga
  single-flight (`_load_lock`) y sin `df.copy()` del concat (`_build(copy=False)`).
- **Cierre parcial**: `save_today` devuelve `pendientes` (fx / acciones /
  cierre) cuando un componente falla DESPUÉS de la base; el autosave los
  reintenta cada 5 min (`completar_cierre`, idempotente) hasta la recaptura y
  el chip dice "parcial". Un no-writer con el journal fallido NO es éxito
  (`error` + `retry`). `_tmp_de(path)` / `_escribir_parquet_atomico`: temporal
  ÚNICO por escritor en journal, cierre completo y particiones (dos escritores
  no se pisan; sin `.tmp` huérfanos). `consolidar_cierres_journal()` al
  arrancar (writer): un `cierre_AAAAMMDD.parquet` del journal sin partición
  compartida se repone (respeta `sin_rueda`); `_prune_journal` también poda
  esos journals a los 90 días.
- **Store**: `update_from_md` hace copy-on-write del `MarketSnapshot`
  (`copy.copy(prev)`): la referencia que tomó un worker queda consistente
  aunque entre otro tick en el medio.
- **Breakeven**: `_ctx` memo + Future compartido por (plazo, tildes, seq,
  huella de índices) — tabla y chart = un armado por tick. `/historicos/curva/data`
  alinea y serializa en el pool.
- **Frontend**: los `every` de htmx se cancelan con la pestaña oculta
  (`htmx:beforeRequest` sobre `hx:poll:trigger`) y `stopAll` limpia
  `pendingDispatch`; `charts.js load()` con AbortController (una petición en
  vuelo, 20 s). Posiciones: el picker es Alpine (`x-model` fondo / plazo), el
  link ↻ Cartera se arma en el cliente y el último fondo elegido se recuerda
  en `localStorage` (`pos_fondo`) — antes el href server-side reseteaba el
  fondo con cada actualización.
- **Benchmark por tick**: `python -m backend.tools.bench_tick [--json x.json]
  [--compare antes.json despues.json] [--slo 50]` — warm / tick / delta /
  ráfagas de 24 con lag del loop, misma metodología que la auditoría
  (in-process, store sembrado a 2000 símbolos, sin red ni lifespan, estado en
  una carpeta temporal). Correrlo antes y después de tocar el camino live.
- Quedó afuera a propósito (ver el informe del 30/09): arranque solapado
  (universo + posiciones + metadata en paralelo), presupuesto en bytes para
  los caches de respuesta (hoy acotados por entradas) y lectura incremental de
  las particiones de cierres.

## Tests

`pytest -q` at the repo root. New backend features need a smoke test
that (a) exercises the calc, (b) hits the HTTP endpoint via
`httpx.AsyncClient` with `ASGITransport`.

CI (`.github/workflows/tests.yml`) corre la suite en **Ubuntu, Windows y
macOS (arm64)** (Python 3.12) con `pytest-timeout --timeout=300`, en cada
push a CUALQUIER rama y en cada PR (repo público: runners gratis; a mano,
`workflow_dispatch` con la versión de Python como input, p. ej. 3.14 = `brew
install python`). La app se despliega como servicio Windows y el add-in de
Excel vive ahí, así que nada Unix-only (`os.fchmod`, `fcntl`, señales) puede
entrar sin guard; el desk también la levanta en Macs (sección **macOS**). Los
tests de rutas Mac (`test_deltapaths.py`) parchean `deltapaths._WINDOWS` para
correr en todos los runners. Las credenciales de bootstrap de la suite son
sintéticas (`tests/conftest.py`): nunca una cuenta real. Las regresiones de
la auditoría externa (sept. 2026) viven en `tests/test_auditoria_tanda1.py`.
La suite corre también sábados, domingos y feriados: un test que ejercite
`save_today` / `recapturar_cierre` / el 5D de Mercado fija "hoy" en el último
día hábil (`_ahora_habil()` en `test_cierres` / `test_historico_writer`,
`hoy_ba` parcheado en `test_ret5d`) — el calendario tiene sus tests aparte.
Nunca `datetime.now()` a secas como "hoy operable".

## macOS (Macs del desk con `correr_app.command`)

Invariantes que mantienen la app andando en Mac — CI la corre en
`macos-latest` en cada push, y `tests/test_tls_local.py` /
`tests/test_consola.py` cubren las ramas darwin parcheando constantes:

- **Rutas**: `secrets.txt` viene en estilo Windows (`~\...`,
  `%USERPROFILE%\...`). TODO lector pasa por `deltapaths.expand` /
  `deltapaths.historico_dir()`, que remapea la cola de carpetas a
  `~/Library/CloudStorage/OneDrive-…`. Nunca `os.getenv("DELTA_…")` a secas.
- **TLS saliente**: el Python de python.org no trae CAs → cada `urlopen` /
  SMTP / wss usa `ssl.create_default_context(cafile=certifi.where())` (`ust`,
  `news`, `mailer`, `primary_ws`); `requests` trae el suyo. El launcher
  exporta `SSL_CERT_FILE` sólo si certifi contesta (vacío = OpenSSL sin CAs).
- **Certificado del add-in** (`tools/https_local.py`): hoja ≤ 825 días (Apple
  rechaza más largas); el CN de la CA lleva el hostname acotado a 64 bytes
  (`_ca_common_name`: cryptography valida RFC 5280 y con un nombre de equipo
  largo `generate()` reventaba — lo vio el runner de macOS); el hostname
  entra a `wanted_hosts` sólo si puede ir al SAN (`_san_ok`: un
  "…-Corvalán.local" con acento regeneraba la hoja en CADA arranque); la
  confianza en el keychain de login (`security add-trusted-cert`, pide la
  clave) se instala SÓLO con CA nueva o no confiada — `ca_trusted_macos`
  (`security verify-cert -L`, sin diálogo) lo decide cuando la hoja se
  regenera por cambio de red/IP. Ramas por plataforma con `_PLATFORM`
  (parcheable), no `sys.platform` inline.
- **git**: sin Command Line Tools, `/usr/bin/git` es un stub de Apple que abre
  un diálogo; `consola._git_disponible()` (`xcode-select -p`, una vez por
  proceso) decide antes de invocarlo y el banner lee `.git` a mano. Cualquier
  subprocess nuevo a `git` va por ahí.
- **Launcher**: venv en `~/.venvs/bonos` (fuera de OneDrive), `ulimit -S -n
  4096` (una terminal de macOS arranca con tope 256 FDs), `TLS_TARGET_PORT =
  PORT`, shebang zsh y sin CRLF (test).
- **Clon fuera de OneDrive**: un `.git` adentro de la biblioteca compartida se
  sincroniza entre máquinas (locks ajenos, refs que cambian abajo del fetch,
  objetos a 1 KB/s). En la Mac el código va en `~/Code/...` clonado con git;
  las bases se leen igual del OneDrive vía `secrets.txt` (deltapaths). La
  carpeta compartida es para el equipo, con `git pull` desde UNA máquina.
- **Safari / WebKit** (también el WKWebView de Excel para Mac): escribir en el
  portapapeles sólo dentro del gesto → `app.js deliver` arma el
  `ClipboardItem` con la PROMESA del PNG y reintenta con el Blob; todo
  `localStorage` bajo try/catch (puede tirar con cookies bloqueadas); nada de
  `.at()`, lookbehind, `structuredClone` sin fallback; `color-mix` /
  `scrollbar-width` en el CSS son sólo cosméticos si faltan.
- Windows-only sin guard no entra: `os.fchmod`, `msvcrt`, `winreg`,
  `LOCALAPPDATA` (`historico_writer.journal_dir` cae a `~/.local/share`).

## Windows — carpeta del código sincronizada por OneDrive (13/10)

En las PCs del desk el clon vive en la biblioteca de SharePoint que sincroniza
OneDrive (`git pull` desde UNA máquina, OneDrive reparte los archivos). Con
Archivos a petición, un archivo NUEVO del repo llega a las otras PCs como
marcador "sólo en la nube" (`FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`) y se baja
recién al leerlo; si OneDrive no lo entrega en ese momento (cerrado, pausado,
sin sesión, sin red) `ReadFile` falla con un ERROR_CLOUD_FILE_* que el CRT
traduce a EINVAL y Python muere al importar con `OSError: [Errno 22] Invalid
argument` en `importlib … get_data` (Pablo, 13/10, `bna_fx.py` nuevo de #242).
`backend/tools/onedrive.py` (stdlib) corre en el .bat ANTES de `https_local`
(que ya importa medio backend): `escanear` (scandir con `follow_symlinks=False`,
atributos del listado, sin `.git` / `__pycache__`; `certs/` y `data/` SÍ, viven
adentro del clon sincronizado y se leen al arrancar) junta los
marcadores sin contenido, `hidratar` los lee enteros (eso dispara la bajada;
`attrib +P` solo es un pedido asincrónico al motor, no garantiza nada), y si
la carpeta es de nube y la raíz no está fijada, `fijar` = `attrib -U +P` sobre
la raíz + `attrib -U +P <raíz>\* /S /D` ("Mantener siempre en este
dispositivo": lo nuevo hereda el pin y Storage Sense —Win11 22H2 vacía lo no
abierto en 30 días— no lo toca; el `-U` porque un archivo ya "sólo en la
nube" lleva UNPINNED y ese estado propio le gana al de la carpeta). "De nube"
= tag 0x9000x01A en alguna entrada (el proceso pide verlos con
`RtlSetProcessPlaceholderCompatibilityMode(2)`: por default Windows se los
disfraza a una app común), o atributos que sólo pone el motor (RECALL /
PINNED / UNPINNED), o la raíz bajo `raices_onedrive()` (variables `OneDrive*`
+ registro `HKCU\Software\Microsoft\OneDrive\Accounts`: las bibliotecas de
SharePoint NO cuelgan de %OneDrive%). Un EINVAL en el read es consistente
con un marcador pero no prueba: la prueba es el bit RECALL_ON_DATA_ACCESS que
muestra `--listar`. Fuera de OneDrive y en Mac / Linux no hace nada
(silencio, exit 0). Si algo
no se pudo bajar, o no se pudo listar una carpeta de la nube (lo de adentro no
se chequeó), sale con código 4 (`EXIT_SIN_BAJAR`; 3 es "app ya corriendo") y
el .bat explica qué hacer; cualquier otro código (traceback del tool mismo
como marcador con OneDrive cerrado) va a un mensaje genérico que señala el
`Errno 22`. El paso corre DESPUÉS de crear el venv y ANTES de pip (lee
requirements.txt) y de https_local; `attrib` se lee con el codec `oem` y
`errors="replace"` (cp850 vs cp1252 estricto tiraba UnicodeDecodeError).
`--listar` sólo informa, `--sin-pin` baja sin fijar, `--quiet` sólo problemas
(`backfill_historico.bat` lo corre así). Regresión:
`tests/test_onedrive.py` (parchea `_atributos` / `_leer` / `_PLATFORM`).

## Estado por máquina fuera de OneDrive (15/10)

El desk vio `data/` con ~6 GB y el chequeo de arranque bajando 6.522 de 8.449
archivos: miles de `data/market_snapshot-DAM-NB-CIO-<n>.json` (~1,7 MB c/u).
Cada instancia reescribía el snapshot del store (`store_persist`, cada 5 min)
adentro del clon sincronizado; con dos o más PCs corriendo, OneDrive veía el
mismo archivo cambiado en varias máquinas y dejaba la versión perdedora como
copia en conflicto con el nombre de la PC. Lo mismo, en chico, con
`riesgo_pais.json` (30 min), `bna_fx.json` (1 h) y el dump
`cer_completo.generated.csv` de `indices.main()` (cada arranque, en la raíz).
**Regla**: lo que una instancia escribe sola y es de ESA máquina (lo que vio su
feed, lo que bajó su poller) va a `services/estado_local.dir_local()` =
`BONOS_LOCAL_DIR` o `%LOCALAPPDATA%\bonos` (Mac/Linux `~/.local/share/bonos`;
la misma carpeta del journal y de `primary_rechazados.json`), NUNCA a `data/`
ni a la raíz del clon. En `data/` queda sólo lo compartido a propósito:
pizarra y preferencias de escenario (escritas por acción del usuario) y
alertas (además cada instancia las marca disparadas al cruzar: escritura rara;
sus copias en conflicto pueden traer un cambio del usuario y NO se limpian).
`bcra_data_backup.json` sigue reescribiéndose en la raíz con cada
`indices.main()` a propósito (decisión del desk, 15/10): es la semilla
versionada que lee Históricos.
`estado_local.ruta(nombre, env)` = dónde se escribe (respeta
`MARKET_SNAPSHOT_PATH` / `RIESGO_PAIS_PATH` / `BNA_FX_PATH`);
`ruta_lectura` = la local o, si todavía no existe y no hay override, el viejo
de `data/` una vez (el primer arranque abre poblado). `indices.py` calcula la
misma carpeta a mano (es legacy, no importa el backend). La suite apunta
`BONOS_LOCAL_DIR` y `MARKET_SNAPSHOT_PATH` a un tmp (`conftest`).
**Limpieza** (`tools/onedrive.py`, en el .bat antes de bajar nada):
`CACHES_POR_MAQUINA` + `basura_de(carpeta, nombre, edad)` → copias en
conflicto (`<stem>` + `-`/espacio/`(` + … + `<ext>`), temporales `<original>…tmp`
con más de 10 min y el original cuando nadie lo escribió en 7 días (una PC con
la versión anterior todavía corriendo lo sigue tocando hasta reiniciar);
`bcra_data_backup.json` está versionado: sólo sus copias. Sólo en la raíz y
en `data/`, sólo en una carpeta de nube. `escanear` las separa en `basura`
(ni `pendientes` ni `total`) y `borrar_basura` las borra SIN bajarlas (borrar
un marcador "sólo en la nube" no lo descarga; el borrado viaja a SharePoint
—queda en su papelera— y a las otras PCs). Si alguna no se pudo borrar, la
carpeta NO se fija (con el pin OneDrive las bajaría en segundo plano) y se
reintenta en el próximo arranque. Con más de `DETALLE_MAX` (40) pendientes el
progreso sale resumido por carpeta y cada ~10 %, no una línea por archivo.
`--listar` muestra la basura sin borrarla. **`.pyc` fuera del clon** (15/10):
los launchers (los dos .bat y `correr_app.command`) ponen
`PYTHONPYCACHEPREFIX` (`%LOCALAPPDATA%\bonos\pycache`, Mac
`~/.cache/bonos/pycache`) antes del primer python: cada PC escribía sus `.pyc`
en `__pycache__` adentro de la carpeta sincronizada y OneDrive los repartía
(un set por versión de Python, huérfanos, copias `-<PC>.pyc`, una bajada por
`.pyc` al importar). `escanear` junta en `caches_py` los `__pycache__` /
`.pytest_cache` / `.ruff_cache` (siguen en `EXCLUIR`: nunca se bajan) y `main`
los borra con `borrar_caches_py` SÓLO si este proceso corre con el prefijo
(`prefijo_pycache()`; sin él volverían en el próximo import). Un Ctrl+C a mitad de la bajada o
del borrado sale sin traceback y con 0 (cmd pregunta igual si terminar el
.bat; si se sigue, la app arranca y OneDrive baja lo que falte al leerlo) y
no fija la carpeta. Sigue compartido a propósito (no es
esto): `certs/` (SAN convergente entre máquinas, `https_local`),
`auth_store.json`, `oms_audit.jsonl`. Regresión: `tests/test_estado_local.py`
+ `tests/test_onedrive.py` (casos de basura).

## Históricos · Base — ver y bajar los archivos de Delta Bases (13/10)

Pedido del desk ("dónde puedo ver y descargar la base"): pestaña lazy **Base
(ver / bajar)** en Históricos (`hist-base` → `GET /historicos/base`,
`partials/historico_base.html`, `services/base_export.py`, todo sólo
lectura). Tarjeta de archivos: base px/tasas (xlsx + espejo parquet, ¿espejo
fiel?, ruedas / filas / reales / desde-hasta del `_resumen_base_cached` del
writer), serie FX (xlsx + parquet, `fx_hist.status()`), cierre completo
(particiones: cuántas, desde-hasta, bytes; listado memoizado por
`cierres.signature()`) y acciones; un `os.stat` por archivo. Vista: las
últimas N filas de la base px/tasas (todas las columnas, pre-formateadas
es-AR) filtradas por Código / rango; `base_export.frame()` lee la base UNA
vez por `hw._firmas_base` (parquet si el espejo vale, si no el Excel; sin
apartar ni regenerar nada) y la deja en memoria compacta (`category`, ~10 MB
por 250 ruedas) — `historico_byma` sólo guarda seis métricas por código, no
sirve para symbol / cierre previo / fuente / hora. Descargas: `GET
/historicos/base/archivo?que=px_xlsx|px_parquet|fx_xlsx|fx_parquet|acciones`
(FileResponse por chunks, clave CERRADA → ruta; nunca texto del usuario),
`GET /historicos/base/cierre?fecha=AAAA-MM-DD&fmt=parquet|csv` (la fecha se
busca en `cierres.particiones()`), `GET /historicos/base.csv?codigo&desde&hasta`
(CSV es-AR `;` + coma decimal + BOM en BYTES, por tramos de `CSV_CHUNK` filas
para soltar el GIL entre llamadas C, `float_format %.15g` — con `%.10g` un
volumen salía `9,12e+11` —, tope `CSV_MAX_FILAS`). Las tres rutas mandan
`Content-Encoding: identity` y `main._SSESinGzip` les saca el
`Accept-Encoding` (`_SIN_GZIP`): un xlsx / parquet ya viene comprimido y el
CSV grande no vale el CPU del server. Antes del 200 de una descarga se lee
UN byte en el executor (`probar_lectura`): FileResponse abre el archivo
después de mandar los headers y un marcador de OneDrive sin bajar / un
archivo en uso dejaba un 200 cortado → ahora 503 con motivo. `?codigo=` pasa
por `_codigo_qs` (sin caracteres de control: un `%0d%0a` llegaba al
`Content-Disposition`; el espacio se conserva, "AEROAR 31" es un código).
Jinja renderiza en el executor; HTML cacheado por (parámetros, firmas: base +
FX + cierres + error del frame) en bytes con presupuesto `_BASE_CACHE_BYTES`;
warm = lookup (medido: avg 3,1 · p50 2,9 · p95 4,2 ms; filtro nuevo p95 43
ms). La pestaña nunca muestra rutas absolutas (el HTML se cachea sin rol):
sólo el nombre de la carpeta; "configurada pero ausente en esta máquina"
(OneDrive sin sincronizar) y "carpeta sin base todavía" tienen su aviso.
Sub-rutas de Históricos: sólo login (la base no tiene tenencias). Regresión:
`tests/test_historico_base.py`.

## Patas de los soberanos hard-dollar en el histórico (13/10)

Pedido del desk: guardar también la historia de las OTRAS patas de globales y
bonares (no corporativos) con su TIR. `services/patas.py` es el único
resolver: `soberanas()` = por cada nativa de `globales` / `bonares` (base =
nativa sin el sufijo, por SUFIJO y no por ISIN: AO29 / AO29D traen ISIN
placeholder) dos entradas — la pata en PESOS (`AO27`, `GD30`: TIR = precio ÷
FX de referencia del día, MEP para un bonar / CCL para un global, la misma
rama que ya usaban las especies pesos de las ON) y la CRUZADA (`AO27C` de un
bonar, `GD30D` de un global: TIR **directa** = precio crudo contra el flujo
de la ficha nativa; es la TIR por ticker del mercado y difiere de la vista
por pata de Curvas, que convierte con CCL/MEP, en ≈ canje / duration —
depende de la duration del día: con 3 % de canje ≈ 50 bps en GD46, ≈ 150 en
AL30, 300-450 en AO27). `build_rows` las emite DESPUÉS del loop de curvas
desde esa lista propia (NO entran a `build_curve_codes`: Curvas / Inicio /
Escenario / Qué pasó no las heredan), `Código` = ticker de la pata (el
lector dedupea por Código + fecha: con el código de la ficha se pisarían),
`symbol` = su ticker, precio crudo de pantalla, columnas nuevas `Pata` ∈
ARS / MEP / CABLE (`espejo.COLS_TEXTO`) y `FX` = tipo de cambio por el que
se dividió un precio en pesos (`espejo.COLS_NUMERICAS`; también en las
especies pesos de ON — reproducibilidad: la recaptura de las 17:31 pisa el
CCL/MEP del archivo FX). `_fila_rc` / `_filas_desde_feed` usan el mismo
resolver (antes `bond_meta('AO27C')` = {} caía en `sin_calc` en silencio) y
con AL30 + AL30C + AL30D en la base `_fx_desde_filas` por fin resuelve el
FX de cierre para la reconstrucción desde la base (cada pata por separado
en la primera base que la tenga: sin AL30C en D+1 el CCL sale de GD30 /
GD30C). `_metricas_por_simbolo`
→ la partición de cierres lleva `tirea` en el símbolo de la pata. Lectores:
`price_action.serie_de` acepta una pata sin ficha (cierres → base) y
`_grupos_especies` suma "Bonos · patas pesos / C / D (soberanos)". Costo
medido: +30 TIR (≈ +100 ms, medido 98 ms; `soberanas()` < 0,1 ms) una vez por
día en el thread del autosave; cero en requests. Regresión: `tests/test_patas_soberanas.py`.

## Índice Merval clavado (14/10)

El desk veía el I.MERVAL quieto mientras las acciones se movían. El índice
puede estar en el store bajo VARIAS variantes de string (`equities.
MERVAL_SYMBOLS`: `… I.MERVAL - 24hs` / `- CI` / sin plazo / `I.MERVAL`, más lo
que `main` suma del universo del broker) y `merval_snapshot()` memoizaba la
PRIMERA con dato y la usaba para siempre: una `… - 24hs` con un cierre viejo
(snapshot persistido o una CL suelta) tapaba a la variante que recibía el IV
en vivo (reproducido en test). Ahora `merval_candidatos()` (variantes
conocidas + cualquier símbolo con 'MERVAL', re-escaneo sólo cuando cambia el
tamaño del store o cada `_MERVAL_RESCAN_S`) y `merval_snapshot()` elige la de
`updated_at` más reciente, prefiriendo las que traen `last` (IV) sobre las
sólo-cierre; un snapshot restaurado del disco conserva su `updated_at`
original y pierde contra uno vivo. Lo usan el panel Líderes (fila `data-pin`),
el tape e Inicio. `GET /market/diag` → `indices` = variantes en el store
(last / close / last_ts / updated_at / seq) y `elegido`: ahí se ve bajo qué
string manda el broker el IV en cada máquina. Regresión:
`test_tape_equities.test_merval_snapshot_elige_la_variante_que_el_feed_actualiza`.
