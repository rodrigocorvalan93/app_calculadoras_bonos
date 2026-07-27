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
bid/ask** (es cinta + volumen, no libro); sus campos son:

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
