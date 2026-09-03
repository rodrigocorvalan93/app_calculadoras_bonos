# Referencia completa de fórmulas `=OMS.*`

Todas las funciones (salvo `HIST`) son *streaming*: se actualizan solas ~1 s
después de cada tick de mercado, sin recalcular a mano. Si un dato no existe
todavía (sin operaciones, especie sin cotizar) la celda muestra vacío; si la
especie/el campo no existen, `#N/A` con el detalle en el tooltip.

Separador de argumentos: `;` con configuración regional es-AR, `,` en inglés.
Los argumentos entre corchetes son opcionales.

---

## OMS.QUOTE(especie; [campo]; [plazo]; [mercado])

Dato de mercado de una especie: bonos, letras, ONs, acciones, CEDEARs e
índices — todo lo que está en el store (BYMA vía Primary WS, MAE vía API).

    =OMS.QUOTE("GD30")                    → último 24hs (defaults)
    =OMS.QUOTE("AL30D";"ask";"CI")        → offer de AL30D contado inmediato
    =OMS.QUOTE("S31L6";"var")             → variación vs cierre (decimal)
    =OMS.QUOTE("GD30";"vol";;"mae")       → VN operado en MAE

**especie** — ticker BYMA sin plazo: `GD30`, `AL30D`, `GD30C`, `S31L6`,
`YMCXO`, `GGAL`, etc.

**campo** (default `last`) — alias en castellano entre paréntesis:

| Campo | Qué devuelve | Alias |
|---|---|---|
| `last` | Último precio operado | `ultimo`, `px`, vacío |
| `bid` | Mejor compra | `compra` |
| `ask` | Mejor venta | `offer`, `venta` |
| `bid_size` | Volumen en la punta compradora (VN) | `volbid` |
| `ask_size` | Volumen en la punta vendedora (VN) | `volask` |
| `last_size` | Tamaño del último trade | |
| `open` | Apertura del día | `apertura` |
| `close` | Cierre anterior | `cierre` |
| `close_date` | Fecha del cierre anterior | `fechacierre` |
| `high` | Máximo del día | `max` |
| `low` | Mínimo del día | `min` |
| `vol` | Monto operado acumulado ($) | `volumen`, `monto` |
| `nominal` | Nominales operados acumulados (VN) | `nominales` |
| `trades` | Cantidad de operaciones del día | `operaciones` |
| `vwap` | Precio promedio ponderado (vol/nominal) | |
| `var` | Variación vs cierre, decimal (formatear como %) | `variacion` |
| `last_ts` | Hora del último trade | `hora` |

**plazo** (default `24hs`):

| Valor | Alias |
|---|---|
| `24hs` (estándar T+1) | `24`, `48`, `48hs`, `t1`, `t+1`, `t2`, `t+2` |
| `CI` (contado inmediato) | `0`, `t0`, `t+0`, `contado` |

(Los alias `48hs`/`t+2` existen para migrar libros de la época T+2 sin tocar
nada: hoy mapean al plazo estándar.)

**mercado** (default `byma`): `byma` | `mae`. La cinta MAE **no tiene
bid/ask** (es cinta + volumen, no libro). Con `mae`, el **plazo también
aplica**: `=OMS.QUOTE("AL30";"last";"CI";"mae")` trae el segmento t+0 y
`"24hs"` el t+1; sin plazo, la fila de mayor volumen del ticker (la de
siempre). Si el segmento pedido no operó, devuelve `#N/A` con el motivo —
antes pedir CI devolvía t+1 en silencio. Sus campos son:

| Campo (en `mae`) | Qué devuelve |
|---|---|
| `last` | Último precio MAE |
| `close` | Cierre anterior |
| `var` | Variación (%) |
| `high` / `max`, `low` / `min` | Máx/mín del día |
| `vol` | VN operado | 
| `monto` | $ operado |
| `plazo`, `moneda`, `segmento` | Metadata de la rueda |

---

## OMS.FX(tipo)

Dólares de referencia en vivo.

    =OMS.FX("mep")        =OMS.FX("canje")        =OMS.FX("mayorista")

| `tipo` | Qué devuelve | Alias |
|---|---|---|
| `mep` | MEP implícito 24hs (del soberano más operado) | `usb` |
| `ccl` | CCL implícito 24hs | `cable`, `usd` |
| `canje` | CCL/MEP − 1 (decimal) | |
| `mep_ci` / `ccl_ci` | Ídem en contado inmediato | |
| `mayorista` | Dólar mayorista intradía (SIOPEL → DLR/SPOT → A3500) | `oficial`, `siopel` |
| `a3500` | Cierre anterior del mayorista / A3500 | `cierre` |
| `mep_base` / `ccl_base` | Ticker del bono usado para el implícito | |

---

## OMS.ROFEX(contrato; [campo]; [canal])

Futuros de dólar DLR (Matba-Rofex) con tasas implícitas vs el mayorista.

    =OMS.ROFEX(1;"tna")               → TNA implícita del contrato más corto
    =OMS.ROFEX("DLR/AGO26M";"last")   → por código
    =OMS.ROFEX("Ago-26";"vto")        → por etiqueta

**contrato**: posición `1..14` (ordenado por vencimiento), código
(`DLR/AGO26M`) o etiqueta (`Ago-26`).

| `campo` | Qué devuelve | Alias |
|---|---|---|
| `last` | Último precio | `ultimo`, vacío |
| `bid` / `ask` | Puntas | `compra` / `venta`, `offer` |
| `bid_size` / `ask_size` | Contratos en cada punta | `volbid` / `volask` |
| `close` | Cierre anterior | `cierre` |
| `var` | Variación vs cierre | `variacion` |
| `vol` | Volumen | `volumen` |
| `oi` | Interés abierto (contratos) | `interes_abierto` |
| `tna` | TNA implícita (decimal) del último | |
| `tna_bid` / `tna_ask` | TNA implícita de cada punta | |
| `tea` | TIR efectiva anual implícita (decimal) | `tir` |
| `tem` | TEM implícita (decimal) | |
| `td` | Devaluación directa al vencimiento (decimal) | `directo` |
| `dias` | Días al vencimiento | |
| `vto` | Fecha de vencimiento | |
| `label` / `code` | Etiqueta (`Ago-26`) / código (`DLR/AGO26M`) | |

**canal** (default `may`): `may` mayorista | `min` minorista.

---

## OMS.CAUCION(dias; [campo]; [moneda])

Caución bursátil BYMA por plazo. La caución cotiza directo por TNA: los
"precios" son tasas **en puntos** (35,5 = 35,5%).

    =OMS.CAUCION(1)              =OMS.CAUCION(7;"bid")        =OMS.CAUCION(30;"tasa";"USD")

**dias**: 1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 35, 60, 90, 120 (las que coticen).

| `campo` | Qué devuelve |
|---|---|
| `tasa` (default) | TNA del último operado (alias `last`) |
| `bid` / `ask` | TNA de cada punta |
| `close` | TNA de cierre anterior |
| `var` | Variación de TNA en puntos |
| `vol` | Monto operado |
| `plazo` | Etiqueta (`7D`) |

**moneda** (default `ARS`): `ARS` | `USD`.

---

## OMS.TABLA(panel; [opcion])

Tabla completa con encabezados en una sola celda (spill: se desborda hacia
abajo/derecha; necesita espacio libre).

    =OMS.TABLA("futuros")        =OMS.TABLA("quotes";"CI")        =OMS.TABLA("cauciones";"USD")

| `panel` | `opcion` | Columnas |
|---|---|---|
| `quotes` (alias `especies`, `cruda`) | plazo `24hs`/`CI` (sin opción: ambos) | Especie · Plazo · Últ · Bid · Ask · Vol Bid · Vol Ask · Cierre · F. cierre · Var · Vol $ · Nominal · VWAP |
| `futuros` (alias `rofex`) | canal `may` (default) / `min` | Contrato · Vto · Días · Últ · Bid · Ask · Cierre · Var % · TNA · TEM · Directo · Vol |
| `cauciones` | moneda `ARS` (default) / `USD` | Plazo · TNA · Bid · Ask · Cierre · Var (pp) · Vol |
| `fx` (alias `dolares`) | — | Tipo · Valor (MEP, CCL, Canje, MEP CI, CCL CI, Mayorista, A3500) |
| `mae` | — | Ticker · Últ · Cierre · Var % · Mín · Máx · VN · Monto · Plazo · Moneda |

---

## OMS.HIST(serie; [dias])

Serie histórica macro en dos columnas (Fecha · Valor) con encabezado.
No es streaming: se recalcula al abrir el libro o con F9. Reemplaza los
`RHistory` del modelo Reuters.

    =OMS.HIST("a3500";365)       =OMS.HIST("tamar";90)        =OMS.HIST("cer")

| `serie` (case-insensitive) | Qué es |
|---|---|
| `a3500` | Dólar mayorista A3500 (Com. BCRA) |
| `badlar` | BADLAR bancos privados (%) |
| `tamar` | TAMAR (%) |
| `cer` | Índice CER |
| `uva` | UVA ($) |
| `inflamom` | Inflación mensual (%) |

**dias**: últimos N días calendario; sin el argumento devuelve la serie entera.

---

## Calculadora YAS en celdas — OMS.TIREA / PRECIO / TNA / TICKET / CALC / TR

El mismo motor de cálculo del YAS web (`genera_ticket` / `calcula_tirea` /
`calcula_precio` de rentafija), en la celda. **No streamean**: son llamadas
PUNTUALES que corren sólo cuando cambian sus argumentos o con F9 — el diseño
esperado es tipear el precio a mano, no engancharlas a un precio vivo. Todas
las celdas que recalculan juntas viajan en UN solo request batch y el
resultado queda memoizado.

    =OMS.TIREA("GD30";78,5)              → 0,1388   (TIR efectiva anual, decimal)
    =OMS.TIREA("GD30")                   → TIR al LAST del mercado (puntual)
    =OMS.TICKET("TXMJ8")                 → ticket al last, 1.000.000 VN default
    =OMS.TIREA("GD30";78,5;"15/08/2026") (con fecha de liquidación custom)
    =OMS.PRECIO("GD30";0,14)             → precio a TIR 14%, en la convención de
                                           mercado del bono (clean para GD/AL,
                                           dirty para CER/lecaps/DLK) — inverso
                                           exacto de OMS.TIREA
    =OMS.TNA("TTM26";99,8)               → TNA bajo la convención del bono
    =OMS.TICKET("GD30";78,5;1000000)     → spill: VN, monto, principal, interés…
    =OMS.CALC("TX26";"duration";105)     → cualquier métrica del YAS
    =OMS.TR("GD30";78,5;0,12;"30/12/2026";1000000)   → total return puntual (spill)

En todas, el argumento `plazo` acepta `"24hs"` (default), `"CI"` **o una
fecha de liquidación custom** `"DD/MM/AAAA"` (el settle custom del YAS), y el
último argumento opcional es un **FX custom** (el de la ficha YAS).

**Precio omitido = last del mercado.** Dejando el precio vacío, el server
resuelve el último precio del store en ese momento (last → cierre) y calcula
UNA vez — se actualiza sólo al recalcular (F9), no streamea. Importante:
**no anides `OMS.QUOTE` adentro de estas funciones** — las funciones
streaming no pueden ser argumento de otra función custom (Office devuelve
`#¡VALOR!`); el precio-de-mercado omitido reemplaza ese patrón.

### OMS.TIREA(especie; precio; [plazo_o_fecha]; [fx])
TIR efectiva anual (decimal → formatear como %). `precio` en la misma
convención que tipeás en el YAS.

### OMS.PRECIO(especie; tir; [plazo_o_fecha]; [fx])
Inverso: precio **clean % del par** a la TIREA dada (decimal: `0,14` = 14%).

### OMS.TNA(especie; precio; [plazo_o_fecha]; [fx])
TNA bajo la convención del bono (dual TAMAR 32/365 · variable 90/365 ·
CER/UVA 180/365 · DLK corp 90/360 · DLK soberano 90/365 ·
hard-dollar 180/360 · LECAP días/365).

### OMS.TICKET(especie; precio; [nominales]; [plazo_o_fecha]; [fx])
Ticket de operación (spill, 2 columnas): VN, monto total, principal, interés,
TIREA, TNA (con su convención), TEM, duration y fecha de liquidación.
`nominales` opcional — default 1.000.000 VN (el mismo del ticket del YAS).

### OMS.CALC(especie; campo; valor; [modo]; [plazo_o_fecha]; [fx])
Escape general: cualquier métrica del YAS. `campo`: `tirea`, `tna`, `tna_raw`,
`tem`, `duration`, `paridad`, `precio_pct`, `precio_clean_pct`, `precio_mercado_pct`,
`intereses_corridos`, `dias_corridos`, `dias_remanentes`, `valor_residual`,
`valor_tecnico`, `settle`, `tna_convention_label`. `modo` dice qué es `valor`:
`precio` (default) | `tir` | `tna` | `margen`.

### OMS.TR(especie; precio; [tir_salida]; [fecha_salida]; [nominales]; [plazo_o_fecha]; [fx])
Total return puntual (spill), la misma ficha TR del YAS: entrada al `precio`,
salida a `tir_salida` (vacío = flat, la misma TIR de entrada) en
`fecha_salida` (vacío = settle+90 días; una fecha ≥ vencimiento = hold to
maturity). Devuelve días, TIR entrada/salida, px inicial/final, P&L de
capital, cobrado (interés + amortización con ajuste), TR directo, TEA, TNA y
los montos en $ por `nominales` (default 1.000.000). Cupones sin reinversión,
como el legacy.

---

## Unidades y formato — resumen

- **Precios**: como cotizan en pantalla BYMA (bonos por 100 VN; LECAPs por
  lámina de 100).
- **Decimales para formatear como %**: `var`, `canje`, `tna`, `tem`, `td`
  (0,068 → aplicar formato porcentaje → 6,8%).
- **Ya en puntos** (no aplicar formato %): tasas de caución (`35,5` = 35,5%),
  BADLAR/TAMAR/inflación de `HIST`.
- **Volúmenes**: `vol` en $ del día; `nominal`/`bid_size`/`ask_size` en VN.

## Hoja OMS_DATA (modo CRUDA)

Con el modo activado desde el panel, la hoja `OMS_DATA` tiene una fila por
clave (columna A) con columnas `LAST · BID · ASK · BID_SIZE · ASK_SIZE ·
CLOSE · CLOSE_DATE · VAR · VOL · NOMINAL · VWAP · TNA · TEM`:

| Prefijo de clave | Ejemplo |
|---|---|
| Especie BYMA | `GD30\|24hs`, `S31L6\|CI` |
| Dólares | `FX\|MEP`, `FX\|CCL`, `FX\|CANJE`, `FX\|MAYORISTA` |
| Futuros | `FUT\|DLR/AGO26M` (TNA y TEM en sus columnas) |
| Cauciones | `CAU\|ARS\|7D`, `CAU\|USD\|30D` |
| Cinta MAE | `MAE\|GD30` |

Uso típico: `=BUSCARV("GD30|24hs";OMS_DATA!A:N;2;FALSO)` para el último.
