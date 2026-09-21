# Cómo clasifica Posiciones

Manual de la **Categoría** de cada tenencia en la pestaña Posiciones (cuadro
"Composición por categoría", ramas de la tabla y "Target vs Actual").
Es la referencia de lo que hace el código (`backend/services/clasificacion.py`
y `routes/posiciones._clasif`); si cambia una regla, cambia este archivo.

Cada tenencia de la cartera (Delta o Galileo) tiene un **ticker** (`Cod_Delta`,
puede ser `NC`), una **descripción** (columna `Especie`) y una **Clase de
Activo** del Excel. La Categoría se decide en este orden; **el primer match
gana**. La celda Categoría de la tabla muestra como tooltip cuál de las
fuentes decidió: *ficha · Delta - Especies · descripción · Clase de Activo ·
sin regla*.

## A. El ticker tiene ficha en `especies.py`

1. **Dual**: la `Industria` de la ficha contiene "Dual" y "Tamar" → "Dual CER /
   TAMAR" si además dice CER, "Dual Fija / TAMAR" si dice Fija, si no "Dual /
   TAMAR".
2. **Ajuste sobre capital**: contiene CER → "CER"; UVA → "UVA"; A3500 →
   "USD-Linked".
3. **Moneda**: USD → "USD" (cable); USB → "USB" (MEP).
4. **Tasa**: `step_up` → "ARS Step Up"; tipo VARIABLE o VARIABLE_CAP → "ARS
   TAMAR" / "ARS BADLAR" (el índice de la ficha); FIJA → "ARS Fija"; nada →
   "ARS (s/tasa)".

Después se antepone el **emisor** según la `Clasificación` de la ficha:
"Soberano…" → `Soberano`, "Sub-soberano" → `Sub-soberano`, "Corporativo …" →
`ON`. Resultado: "ON ARS TAMAR", "Soberano CER", "Sub-soberano USD",
"Soberano Dual CER / TAMAR". Si la Clasificación no dice nada, queda sin
prefijo.

## B. El ticker no tiene ficha (o no hay ticker)

Se arma un texto normalizado — MAYÚSCULAS, sin tildes, todo lo que no es letra
o número pasa a espacio — de tres fuentes, que se prueban en este orden:

| Orden | Fuente | Qué texto se mira |
|---|---|---|
| 1 | Fila de `Delta - Especies` (si el ticker está en la hoja Base RF) | `Subclase de Activo`, `Clase de Activo`, `Industria`, `Sub Industria`, `Sector Delta` |
| 2 | Descripción de la cartera | columna `Especie` |
| 3 | Excel de cartera | columna `Clase de Activo` |

### B1. Tipo de instrumento por texto

En cada fuente se prueba, en este orden, y la primera fuente que reconoce
un tipo decide: plazo fijo → caución → cheque → pagaré → FCI cerrado →
fideicomiso → FCI.

| Tipo | Tokens que lo reconocen (palabras enteras) | Categoría |
|---|---|---|
| Plazo fijo | `PLAZO FIJO`, `PLAZOS FIJOS`, `P FIJO`, `PFIJO`, `PF` | "Plazos Fijos"; con `CER` o `UVA` en base + descripción → "Plazos Fijos UVA" |
| Caución | `CAUCION`, `CAUCIONES`, `CAUC` | "Caución" |
| Cheque | `CHEQUE(S)`, `CPD`, `ECHEQ(S)`, `CHPD`, `CH P D` | "Cheques Garantizados" / "Cheques No Garantizados" / "Cheques" |
| Pagaré | `PAGARE(S)` | "Pagarés Garantizados" / "Pagarés No Garantizados" / "Pagarés" |
| Fideicomiso | `FIDEICOMISO(S)`, `FID`, `FF`, `VDF`+letra, `VRD`+letra, `TDF` | "Fideicomisos TAMAR/BADLAR" · "CER/UVA" · "Tasa Fija" · "USD-Linked" · "USD" · "Financieros" |
| FCI | `FCI`, `FONDO(S) COMUN(ES)`, `FONDO(S)`, `CUOTAPARTE(S)` | "FCI Cerrados" / "FCI Money Markets" / "FCI" |

Matices, mirando **todo** el texto disponible (base + descripción + clase):

- **Garantía** (cheques y pagarés): `NO GARANT…`, `SIN GARANT…`, `NO AVAL…`,
  `SIN AVAL…`, `NG` → No Garantizados; `GARANT…`, `GTIA`, `AVAL…`, `SGR` →
  Garantizados. Se chequea primero el "no". Sin dato queda "Cheques" /
  "Pagarés": no se inventa la garantía.
- **Tasa del fideicomiso**: primero Ajuste × Tasa de la base (B2); si no,
  tokens en base + descripción (la Clase "Renta Fija" no cuenta): `TAMAR` o
  `BADLAR` → TAMAR/BADLAR; `CER` o `UVA` → CER/UVA; `DLK`, `DOLAR LINKED`,
  `USD LINKED`, `A3500` → USD-Linked; `USD`, `USB`, `MEP`, `CABLE`, `HARD
  DOL…`, `DOLARES` → USD; `FIJA` → Tasa Fija; nada → "Fideicomisos
  Financieros".
- **FCI**: `CERRADO(S)`, `FCIC`, `FCC` → "FCI Cerrados"; Clase de Activo
  "Liquidez" o tokens `MONEY MARKET`, `MM`, `T+0`, `MERCADO DE DINERO`,
  `LIQUIDEZ` → "FCI Money Markets"; si no, "FCI". Un "FCI CERRADO …
  FIDEICOMISO" es un FCI cerrado (el chequeo de cerrado va antes que el de
  fideicomiso).

### B2. Ajuste × Tasa de `Delta - Especies`

Si ningún texto reconoció un tipo y el ticker tiene fila en la base, manda la
regla del OMSposiciones legacy, con las **mismas etiquetas** que las fichas
(así un ON TAMAR sin ficha suma al mismo grupo que los que sí la tienen):

| `Ajuste` | `Tasa` | Categoría |
|---|---|---|
| empieza con `Dual` | — | "Dual CER / TAMAR" · "Dual Fija / TAMAR" · "Dual / TAMAR" (si no dice Tamar, el texto tal cual) |
| `CER` / `UVA` | — | "CER" / "UVA" |
| `USD-Linked`, `USD Linked`, `DLK`, `Dolar Linked`, `A3500` | — | "USD-Linked" |
| `USD` / `USB` | — | "USD" / "USB" |
| `ARS`, `En pesos`, `Pesos` | `Fija` / `TAMAR` / `BADLAR` / `Step Up` | "ARS Fija" / "ARS TAMAR" / "ARS BADLAR" / "ARS Step Up" |
| `ARS`, `En pesos`, `Pesos` | vacío o `NC` | "ARS (s/tasa)" |
| `ARS`, `En pesos`, `Pesos` | otra cosa | "ARS <esa tasa>" |
| vacío o `NC` | `Fija` / `TAMAR` / `BADLAR` / `Step Up` | en pesos por la Tasa |
| vacío, `NC` u otra cosa | — | sigue a B3 |

Después el **emisor**, buscando en este orden y con el primer match:

1. Texto de la base (Subclase / Clase / Industria / Sub Industria / Sector
   Delta): `SUB SOBERANO`, `PROVINCIA(S)`, `PROVINCIAL(ES)`, `MUNICIP…`,
   `CABA` → Sub-soberano; `SOBERANO(S)`, `TESORO`, `TITULO(S) PUBLICO(S)`,
   `LETRA(S) DEL TESORO`, `LETE(S)`, `LECAP(S)`, `LECER`, `BONCAP(S)`,
   `BONTE(S)`, `BONCER`, `BOPREAL`, `BCRA` → Soberano; `ON`, `OBLIGACION(ES)
   NEGOCIABLE(S)`, `CORPORATIVO/A(S)` → ON.
2. Descripción: **el token `ON` manda** ("ON BANCO PROVINCIA …" es una ON);
   después los de Sub-soberano; después los de Soberano.
3. Clase de Activo del Excel: Sub-soberano; Soberano ("Títulos Públicos");
   `Renta Fija` u `ON` → ON (en Delta la clase "Renta Fija" son las ONs).

Sin dato de emisor, la categoría queda sin prefijo ("ARS TAMAR").

### B3. Clase de Activo del Excel

- contiene `CEDEAR` → "CEDEARs"; contiene `ACCION` o `EQUITY` → "Acciones".
- es "Liquidez" y la fila tiene un ticker de 3 o más caracteres que **no** es
  de caja (`$`, `ARS`, `PESOS`, `USD`, `USB`, `DOLARES`, `DOLAR`, `CABLE`,
  `MEP`, `CCL`, `CAJA`, `CTA`, `CUENTA`, `DISPONIBILIDADES`, `NC`) → "FCI
  Money Markets" (Delta valúa los FCI de liquidez con ticker y cuotapartes;
  la caja no tiene ticker).
- si no, **la Clase cruda** tal cual ("Renta Fija", "Liquidez", "Otros Activos
  Netos", "Bonos Corporativo USD"…). Fuente: *sin regla*. Sin Clase:
  "(sin clasif.)".

Las categorías de instrumento (plazos fijos, caución, cheques, pagarés,
fideicomisos, FCI) **nunca** llevan prefijo de emisor.

## Tasa y Calificación (los otros cuadros)

- **Tasa**, con ficha: Dual → la etiqueta dual; `step_up` → "Step Up";
  VARIABLE → el índice ("TAMAR", "BADLAR"); FIJA → "Fija". Sin ficha: la
  columna `Tasa` de la base (`Fija`, `TAMAR`, `BADLAR`, `Step Up`); si no la
  hay: plazos fijos, caución, cheques, pagarés y "Fideicomisos Tasa Fija" →
  "Fija"; "Fideicomisos TAMAR/BADLAR" → "Variable"; el resto "(sin clasif.)".
- **Calificación**, con ficha: la nota de la ficha ("Soberano" si es soberana
  sin nota). Sin ficha: `Califica_Local` de la base; si no, "(sin clasif.)".
  La columna Rating de la tabla muestra lo mismo.
- **Emisor** (columna de la tabla): `Emisor / Sponsor` de la base; un soberano
  sin fila en la base → "Tesoro Nacional".

## Qué cargar en `Delta - Especies` (hoja Base RF)

Para que una tenencia se clasifique **por dato** y no por su descripción, su
ticker (columna `BYMA`) tiene que tener:

| Columna | Valores que la app entiende | Para qué |
|---|---|---|
| `Ajuste` | `ARS` / `En pesos`, `CER`, `UVA`, `USD-Linked`, `USD`, `USB`, `Dual (…)` | Categoría (B2) |
| `Tasa` | `Fija`, `TAMAR`, `BADLAR`, `Step Up` | Categoría (B2) y cuadro Tasa |
| `Subclase de Activo` (o `Clase de Activo`, `Industria`, `Sector Delta`) | texto que diga `Fideicomiso Financiero`, `FCI Cerrado`, `Obligación Negociable`, `Títulos Públicos`, `Provincial`… | Tipo de instrumento (B1) y emisor |
| `Califica_Local` | la nota local (`AA(arg)`, `A1+(arg)`…) | Cuadro Calificación y Rating |
| `Emisor / Sponsor` | razón social | Columna Emisor |

La tarjeta **"Especies faltantes · qué pulir en la base"** de `/admin` lista
las tenencias Delta cuya Categoría no salió de ficha ni de la base: con
ticker (cargar lo de arriba, o la ficha en `especies.py`) y sin ticker sin
regla (pasar la descripción para sumar un token). Plazos fijos, cauciones,
cheques y pagarés no tienen ticker: sólo se clasifican por su descripción.

## Ejemplos

| Tenencia (ticker · descripción · Clase) | Categoría | Fuente |
|---|---|---|
| AFCNO con ficha Corporativo TAMAR | ON ARS TAMAR | ficha |
| TX26 con ficha Soberano, ajuste CER | Soberano CER | ficha |
| ZONT1 sin ficha · "ON FANTASMA TAMAR" · Renta Fija · base Ajuste ARS, Tasa TAMAR | ON ARS TAMAR | Delta - Especies |
| FFAB1 sin ficha · base Subclase "Fideicomiso Financiero", Tasa BADLAR | Fideicomisos TAMAR/BADLAR | Delta - Especies |
| NC · "PLAZO FIJO BANCO MACRO 15/10/2026" · Renta Fija | Plazos Fijos | descripción |
| NC · "CPD AVALADO SGR 12/11/26" · Renta Fija | Cheques Garantizados | descripción |
| NC · "CHEQUE PAGO DIFERIDO NO GARANTIZADO" · Renta Fija | Cheques No Garantizados | descripción |
| NC · "ECHEQ 30/11/26" · Renta Fija | Cheques | descripción |
| DELPESB · "DELTA PESOS CLASE B" · Liquidez | FCI Money Markets | Clase de Activo |
| $ · "CAJA PESOS" · Liquidez | Liquidez | sin regla |
| NC · "OTROS ACTIVOS NETOS" · Otros Activos Netos | Otros Activos Netos | sin regla |
| Galileo · Clasifica_Ficha "Cheques Garantizados" | Cheques Garantizados | Clase de Activo |

## Límites conocidos

- Los tokens se escribieron sin ver las descripciones reales de todas las
  carteras: lo que no matchea queda con la Clase cruda y se cuenta como
  "sin regla fina" en el título de la tabla. Es la lista para pulir.
- Un cheque o pagaré sin palabra de garantía queda genérico.
- Un provincial que Delta cargue como "Títulos Públicos" sin nada que diga
  "provincial" en la base o la descripción sale como Soberano.
- "FCI Money Markets" por Clase "Liquidez" + ticker es una inferencia: una
  fila de liquidez con un ticker raro se lee como FCI.
- Los targets guardados en el navegador se atan al nombre de la categoría:
  al cambiar un nombre ("ARS TAMAR" → "ON ARS TAMAR") hay que recargarlos.
