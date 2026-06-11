# Tipos de bono y convenciones de la casa

## Los tres campos acoplados

La clasificación de un bono se traduce a tres campos que tienen que ser coherentes entre sí:

- `Index` — el índice de **tasa** que se suma al spread (TAMAR, BADLAR). `None` si la tasa no se
  indexa.
- `Tipo Tasa Interés` — `"VARIABLE"` si el cupón depende de un índice de tasa; `"FIJA"` en cualquier
  otro caso (incluido cuando lo que ajusta es el capital, no la tasa).
- `Ajuste sobre Capital` — el índice de **capital** (`"CER"`, `"UVA"`, `"A3500"`) o `None`.

Regla mental: *un bono ajusta o la tasa o el capital, casi nunca las dos por el mismo mecanismo.*
Si ajusta la tasa → `VARIABLE` + `Index`. Si ajusta el capital → `FIJA` + `Ajuste sobre Capital`.
Los duales soberanos (CER/TAMAR) se cargan por su pata de capital (CER) con tasa fija; ver ejemplos.

## Distinción clave: lag de índice vs lag de ajuste

Hay dos familias de *lag* y se llenan según qué ajusta:

- **Tasa variable (TAMAR/BADLAR):** el lag va en `Días Lag índice desde inc` y
  `Días Lag índice hasta inc` (típico −7). `Días lag Ajuste base` y `Días lag Ajuste` quedan `None`.
- **Ajuste de capital (CER/UVA/A3500):** el lag va en `Días lag Ajuste base` y `Días lag Ajuste`
  (CER −10, UVA −5, A3500 −3). `Días Lag índice desde/hasta inc` quedan `0`.

Son enteros negativos (días hábiles previos a la fecha de determinación). El número exacto sale del
suplemento; los de arriba son los defaults de la casa.

## Tabla de convenciones por defecto

Punto de partida. **Siempre verificar en el suplemento** y sobrescribir si la emisión dice otra cosa
(p. ej. un UVA con lag −10 en lugar de −5). Anotar todo desvío en las notas con la referencia.

| Tipo | `Index` | `Tipo Tasa Interés` | `Ajuste sobre Capital` | Index lag | Ajuste lag | Devengamiento | Base | Pata "j" |
|------|---------|---------------------|------------------------|-----------|------------|---------------|------|----------|
| TAMAR | `"TAMAR"` | `"VARIABLE"` | `None` | −7 | `None` | Actual | 365 | No |
| BADLAR | `"BADLAR"` | `"VARIABLE"` | `None` | −7 | `None` | Actual | 365 | No |
| CER | `None` | `"FIJA"` | `"CER"` | 0 | −10 | ISMA-30 (sob.) / Actual (corp.) | 360 / 365 | **Sí** |
| UVA | `None` | `"FIJA"` | `"UVA"` | 0 | −5 | Actual (corp.) | 365 | **Sí** |
| Dollar Linked | `None` | `"FIJA"` | `"A3500"` | 0 | −3 | Actual | 365 | No |
| Hard Dollar / MEP | `None` | `"FIJA"` | `None` | 0 | `None` | Actual | 365 | No |
| Tasa Fija ARS | `None` | `"FIJA"` | `None` | 0 | `None` | Actual | 365 | No |

Sobre devengamiento/base: la regla práctica es **corporativos → Actual / 365**, **soberanos →
ISMA-30 / 360**. Pero confirmá en la sección de "Cómputo de intereses" del suplemento, porque hay
excepciones.

## Etiquetas `Clasificación` e `Industria`

`Clasificación` es la etiqueta gruesa que ya usás en el archivo. Valores existentes:
`"Corporativo TAMAR"`, `"Corporativo BADLAR"`, `"Corporativo UVA"`, `"Corporativo Dolar Linked"`,
`"Corporativo Hard Dolar"`, `"Corporativo Hard Dolar MEP"`, `"Corporativo Tasa Fija"`, `"Soberano"`,
`"Sub-soberano"`. Elegí la que corresponda al emisor + tipo.

`Industria` es libre y descriptiva (p. ej. `"Energy"`, `"Financials"`, `"Communications"`,
`"Consumer Discretionary"`, o para soberanos `"Soberano Inflación"`, `"Soberano ARS Dual CER/Tamar"`).
Inferila del emisor.

## Tasa fija capitalizable (LECAP / BONCAP) y el Factor de Capitalización

Algunos instrumentos de tasa fija **no pagan cupón periódico**: capitalizan los intereses y pagan
todo (capital + interés capitalizado) en un único pago al vencimiento. Son las letras/bonos tipo
LECAP/BONCAP (las series soberanas "S…" y "T…"). Se reconocen porque tienen `Cupón / Spread: 0`,
`Frecuencia de pago de cupón anual: 0`, una sola fecha de cupón (= vencimiento), `BULLET`, y
devengamiento `ISMA-30` / base `360`.

En estos casos el **`Factor Capitalización`** deja de ser `1.` y se carga como esta expresión
(dejala como expresión literal de Python, no la evalúes — así queda trazable como en el archivo):

```python
"Factor Capitalización": (1 + TEM)**((DIAS360 / 360) * 12),
```

donde:
- **`TEM`** es la tasa efectiva mensual de corte del instrumento (del Aviso de Resultados; p. ej.
  `0.0255` para 2,55% mensual).
- **`DIAS360`** es la cantidad de días entre emisión y vencimiento por el método **30/360 US**
  (el `DIAS360` de Excel). Calculalo vos y escribí el entero resultante.

Ejemplos reales: `(1+0.0255)**((360/360)*12)` (emisión 31/10/2025 → vto 30/10/2026),
`(1+0.025)**((291/360)*12)` (10/11/2025 → 31/08/2026), `(1+0.023)**((345/360)*12)`
(15/12/2025 → 30/11/2026).

### Cómo calcular DIAS360 (método 30/360 US / NASD)

```python
def dias360(emis, vto):  # emis, vto = (dia, mes, anio)
    d1, m1, y1 = emis
    d2, m2, y2 = vto
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 == 30:
        d2 = 30
    return (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)
```

Verificá el resultado contra los tres ejemplos de arriba (291, 360, 345) antes de confiar en él.
Para bonos que **no** capitalizan (cupón corriente, simple), `Factor Capitalización` queda en `1.`.

## Cómo obtener el ticker (`Código`)

El ticker en general **no se puede derivar** del bono: cada emisor tiene su propio prefijo en el MAE
(Scania → `SBC`, Tarjeta Naranja → `T`, Luz de Tres Picos → `LUC`, Liliana → `LNS`…). La vía
robusta y general es **buscarlo en el listado del MAE por el nombre del emisor**, que de paso
devuelve el ISIN y la moneda:

```bash
python3 scripts/buscar_mae.py --emisor "SCANIA"
#  SBC3O | AR0183143921 | ON.SCANIA CREDIT ARG CLASE 3 | Dólares
```

Tomá el código de la fila que corresponda a la clase/serie del bono (la descripción suele decir
"CLASE N"). Ese código del MAE termina **siempre en `O`**.

**Cómo buscar bien por nombre:** el MAE abrevia y pone en mayúsculas la descripción (p. ej.
`ON.CRESUD SERIE 36 CL 52`, `ON.SCANIA CREDIT ARG CLASE 3`). No busques con la razón social legal
completa ("CRESUD SOCIEDAD ANÓNIMA COMERCIAL, INMOBILIARIA..."): usá un **token corto y distintivo**
del emisor (`CRESUD`, `SCANIA`, `TARJETA NARANJA`). El script igualmente, si el nombre completo no
matchea, reintenta solo con la primera palabra distintiva.

**Cómo elegir la fila (clase correcta):** la clase del aviso suele venir en romano (Clase LII, LIII)
y en el MAE puede figurar en arábigo (`CL 52`, `CL 53`) o en romano (`CLASE XLVI`). Convertí el
romano a número (LII→52, LIII→53) y buscá la fila cuya descripción tenga esa clase. Ej. Cresud:
`CS52O` = `ON.CRESUD SERIE 36 CL 52` (Clase LII); `CS53O` = `... CL 53` (Clase LIII).

### El ticker de la casa = código del MAE con la letra de moneda

El ticker que va en `Código` se arma tomando el código del MAE y **reemplazando la letra final por la
letra de la moneda/liquidación del bono**. Esto aplica a **todos** los emisores:

| Liquidación / moneda | Letra final | `Moneda` |
|----------------------|-------------|----------|
| Pesos | `O` | `ARS` |
| Hard Dólar **MEP** | `D` | `USB` |
| Hard Dólar **CCL / exterior** | `C` | `USD` |

Ejemplos:
- Scania Clase 3: el MAE la lista `SBC3O`; es Hard Dólar **MEP** → en la casa es **`SBC3D`**.
- Tarjeta Naranja Clase 67: el MAE lista `T671O`/`T672O`/`T673O` (incrementando la serie); en la casa
  quedan `T671O` (pesos), `T672D` (MEP), `T673C` (CCL/exterior).

O sea: el **prefijo + dígitos** del código salen del MAE (no se inventan); la **letra final** la
ponés vos según la moneda. Para buscar el ISIN o precios externos se usa la forma con `O` (el script
`buscar_mae.py` ya prueba la variante con `O` automáticamente).

## La pata proyectada (versión "j")

Los bonos **CER** y **UVA** se cargan dos veces: el dict base y un dict "proyectado". El proyectado
es **idéntico** al base salvo tres campos:

1. **Nombre de la variable:** se le agrega `j` al final. `TX26` → `TX26j`. (El campo `"Código"`
   interno NO cambia; sigue siendo el ticker real.)
2. **`Industria`:** se le agrega `" Proyectado"` al final.
   `"Soberano Inflación"` → `"Soberano Inflación Proyectado"`.
3. **`Ajuste sobre Capital`:** `"CER"` → `"CER PROYECTADO"`, `"UVA"` → `"UVA PROYECTADO"`.

Todo lo demás (fechas, cupón, amortización, lags, call) queda igual. Los **Dollar Linked (A3500) no
llevan** pata proyectada — solo CER y UVA.

## Moneda en hard-dollar: USD vs USB (convención de la casa)

`Moneda` codifica la **pata de liquidación**, no solo la divisa: cable/exterior (`…C`) → `"USD"`;
**MEP** (`…D`) → `"USB"`; pesos (`…O`) → `"ARS"`. Un ON MEP lleva `Moneda: "USB"` (no "USD") — esto
es lo que usa el motor de FX implícito y la clasificación de Posiciones.

## Fichas hermanas por tipo (cargar TODAS)

| Tipo | Fichas | Comparable |
|---|---|---|
| CER / UVA (sob o corp) | base + **j** proyectada | TX26+TX26j / TLCJO+TLCJOj |
| Dual CER/TAMAR soberano | base + **j** + **v** (VARIABLE_CAP·TAMAR, Industria `Soberano ARS Dual Tamar/CER`) | TXMJ9 / TXMJ9j / TXMJ9v |
| Dual Fija/TAMAR soberano | base + **v** (Industria `Soberano ARS Dual Tamar/Fija`) | TTS26 / TTS26v |
| Global / ON cable | referencia **CLEAN** + pata **C** (DIRTY, USD) | GD30+GD30C(+GD30D) |
| Bonar / ON MEP | base + pata **D** (DIRTY, USB) | AL30+AL30D / AFCID |
| TAMAR / BADLAR / DLK / Tasa fija ARS | 1 sola ficha | LNS3P / TYCZO / LUC3O / S31L6 |

En la duda: `grep -nE "^COMP(j|v|C|D)? = " especies.py` y replicá exactamente ese set.

## Strings exactos → Curvas y Posiciones

La curva de un **soberano** sale del string EXACTO de `Industria`; la de un **corporativo** del de
`Clasificación` (su `Industria` es el sector GICS, decorativa). Tabla completa y autoritativa: el
bloque `'''GUÍA DE CARGA'''` al inicio de `especies.py`. Claves frecuentes:

| String | → Curva |
|---|---|
| `Soberano Inflación` (+` Proyectado`) | cer / cerproy |
| `Soberano ARS Tasa Fija` · `Soberano Letras Zero Cupón (Ledes y Letes)` | lecap |
| `Soberano ARS TAMAR` | tamar |
| `Soberanos Dolar Linked` | dolarlinked |
| `Soberano USD Ley Extranjera` · `Soberano USD Ley Argentina D` · `Soberanos USD BCRA D` | globales / bonares / bopreales |
| `Soberano ARS Dual Fija/Tamar` · `…Dual CER/Tamar` · `…Dual Tamar/…` | dualfija / dualcer / dualtamar |
| `Corporativo TAMAR/BADLAR/Tasa Fija/UVA/Dolar Linked/Hard Dolar/Hard Dolar MEP` | corp_* |

En **Posiciones**, los duales se detectan porque `Industria` contiene "Dual" y "Tamar" (sin lista de
tickers): respetá esa convención de nombre y el bono nuevo se agrupa solo como "Dual CER / TAMAR" o
"Dual Fija / TAMAR". `Sub-soberano` hoy NO cae en ninguna curva — avisale al usuario.
