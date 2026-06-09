---
name: nueva-especie
description: >-
  Dar de alta un bono nuevo en especies.py a partir de un aviso de licitación /
  suscripción del Tesoro (o de los términos de un bono). Usala cuando el usuario
  quiera "cargar una especie", "agregar/dar de alta un bono", "leer un aviso de
  licitación", o pegue/suba el aviso (texto, PDF, imagen o URL). Extrae los
  términos, los mapea al dict de especies.py con la Industria/Clasificación
  correctas, genera las fichas extra que correspondan (proy 'j', pata 'v' dual,
  patas C/D hard-dollar), previsualiza cómo cae en Curvas y Posiciones, y recién
  inserta cuando el usuario confirma.
---

# Cargar una especie nueva en `especies.py`

Convierte un **aviso de licitación/suscripción** del Tesoro (o los términos de un
bono) en el/los `dict` correctos de `especies.py`, los registra bien, y verifica
cómo caen en **Curvas** y **Posiciones** — todo con **confirmación previa**.

`especies.py` es legacy y crítico (está en la lista "no tocar salvo necesario" de
CLAUDE.md). Dar de alta un bono es la excepción legítima, pero: **previsualizá y
pedí OK antes de escribir, y validá después.**

---

## Flujo (en orden)

1. **Conseguí el aviso.** Texto pegado, PDF, imagen o URL.
   - PDF/imagen subidos → `Read` sobre el archivo.
   - URL → `WebFetch`.
   - Si un dato no está, **no lo inventes**: dejalo con `# ⚠ confirmar` y avisá.

2. **Extraé los términos** (ver *Qué buscar en el aviso*).

3. **Clasificá el instrumento** y elegí los campos discriminantes leyendo la
   **guía al inicio de `especies.py`** (el bloque `'''...'''` "GUÍA DE CARGA") —
   es la fuente autoritativa de qué `Industria`/`Clasificación` usar y cómo cae
   en cada curva/posición. Resumen en *Tabla rápida*.

4. **Espejá un bono comparable** (estrategia clave — ver abajo). No armes el dict
   de memoria: encontrá el bono existente del **mismo tipo**, leé su(s) ficha(s)
   completas y cloná la estructura cambiando sólo lo propio del papel nuevo.

5. **Armá TODAS las fichas** que correspondan (ver *Fichas múltiples*).

6. **Previsualizá sin tocar nada.** Mostrá: el/los dict + a qué **Curva** y a qué
   **Categoría/Tasa/Calificación de Posiciones** va a caer. Pedí confirmación.

7. **Insertá** sólo tras el OK — las **3 partes** por ficha (ver *Las 3 ediciones*).

8. **Validá**: `python .claude/skills/nueva-especie/preview.py <TICKER> [...]`
   (desde la raíz del repo). Confirmá que carga y cae donde esperabas. Si dice
   "no está en el universo", faltó alguna de las 3 ediciones.

---

## Estrategia clave: espejar un bono comparable

La forma más confiable de cargar bien (convenciones, lags, fichas múltiples) es
**copiar un bono existente del mismo tipo** y cambiarle sólo lo del papel nuevo
(nombre, ISIN, fechas, cupón/spread, amortización).

1. Identificá el tipo (CER, tasa fija, TAMAR, dual, dólar-linked, hard-dollar,
   ON, etc.).
2. Buscá un comparable de ese tipo EXACTO (misma `Industria`/`Clasificación`).
   Ejemplos por tipo en la *Tabla rápida*. Para ver sus campos:
   `python .claude/skills/nueva-especie/preview.py <COMPARABLE>`
   y leé su dict en `especies.py` (`grep -n "^<COMPARABLE> = {" especies.py`).
3. Cloná su estructura **y la de todas sus fichas hermanas** (`<C>j`, `<C>v`,
   `<C>C`, `<C>D` según el tipo).

---

## Qué buscar en el aviso

| Dato del aviso | Campo(s) del dict |
|---|---|
| Denominación / nombre | `"Nombre Security"` |
| ISIN | `"ISIN"` (y a veces `"Código"`) |
| Ticker BYMA | **el nombre de la variable** (`TX30 = {...}`) → es lo que lee el sistema |
| Moneda de emisión/pago | `"Moneda"` (ARS / USD cable / USB MEP) |
| Fecha de emisión / liquidación | `"Emisión"` |
| Fecha de vencimiento | `"Vencimiento"`, `"Fechas de cupón"` |
| Tasa / cupón | `"Cupón / Spread"`, `"Tipo Tasa Interés"`, `"Index"` |
| Ajuste (CER / UVA / dólar-linked) | `"Ajuste sobre Capital"` |
| Amortización (íntegra=bullet / parcial) | `"Tipo de Amortización"`, `"Amortización"` |
| Frecuencia / fechas de pago de cupón | `"Frecuencia de pago de cupón anual"`, `"Fechas de cupón"` |
| Base de cálculo (30/360, act/365) | `"Convención Base"`, `"Convención de devengamiento"` |
| Ley aplicable (local / NY) | informa `Industria`/`Clasificación` (ley arg vs ext) |

Lo que el aviso casi nunca trae y se toma por convención (igual que el
comparable): lags de índice/ajuste (CER `-10`, UVA `-5`), `Factor
Capitalización` (1), `Plazo de liquidación` (t+1), calificación (la del
comparable). Marcá lo asumido.

---

## Tabla rápida (tipo → qué setear → comparable → dónde cae)

> La versión completa y autoritativa está en la **guía de `especies.py`**. Acá el
> resumen para elegir el comparable. (Los strings se matchean EXACTO.)

**SOBERANOS — curva por `Industria`, `Clasificación="Soberano"`:**

| Tipo | `Industria` | Moneda | Ajuste | Tasa/Index | Base | Comparable | → Curva / Pos |
|---|---|---|---|---|---|---|---|
| Global USD (ley ext) | `Soberano USD Ley Extranjera` | USD | None | FIJA | 360 | GD30 (+ GD30C/GD30D) | globales / USD |
| Bonar USB (ley arg) | `Soberano USD Ley Argentina`(+` D`) | USB | None | FIJA · step_up | 360 | AL30 / AL30D | bonares / USB |
| Bopreal (BCRA) | `Soberanos USD BCRA`(+` D`) | USB | None | FIJA | 360 | BPA7D | bopreales / USB |
| Dólar-Linked | `Soberanos Dolar Linked` | ARS | A3500 | FIJA | 360 | D31L6 | dolarlinked / USD-Linked |
| ARS Tasa fija (boncap) | `Soberano ARS Tasa Fija` | ARS | None | FIJA | 365 | T30J6 | lecap / ARS Fija |
| Letra zero (LEDE/LECAP) | `Soberano Letras Zero Cupón (Ledes y Letes)` | ARS | None | FIJA | 360 | S31L6 | lecap / ARS Fija |
| CER (boncer/lecer) | `Soberano Inflación` (+ `Proyectado` ficha `j`) | ARS | CER (`j`: CER PROYECTADO) | FIJA | 360 | TX26 / TX26j | cer + cerproy / CER |
| TAMAR | `Soberano ARS TAMAR` | ARS | None | VARIABLE_CAP · TAMAR | 360 | TMF27 | tamar / ARS TAMAR |
| Dual Fija/TAMAR | base `Soberano ARS Dual Fija/Tamar`, pata `…Tamar/Fija` | ARS | None | base FIJA / pata `v` VARIABLE_CAP·TAMAR | 360 | TTS26 / TTS26v | dualfija+dualtamar / Dual Fija / TAMAR |
| Dual CER/TAMAR | base `Soberano ARS Dual CER/Tamar` (+`…Proyectado` `j`), pata `…Tamar/CER` | ARS | base CER (`j`: CER PROY) / pata None | base FIJA / pata `v` VARIABLE_CAP·TAMAR | 360 | TXMJ9 / TXMJ9j / TXMJ9v | dualcer+dualtamar / Dual CER / TAMAR |

**CORPORATIVOS (ON) / SUBSOBERANOS — curva por `Clasificación`** (la `Industria`
del ON es el sector GICS, decorativa):

| Tipo | `Clasificación` | Moneda | Ajuste | Tasa/Index | Comparable | → Curva / Pos |
|---|---|---|---|---|---|---|
| ON ARS tasa fija | `Corporativo Tasa Fija` | ARS | None | FIJA | (ver grep) | corp_tasafija / ARS Fija |
| ON ARS TAMAR | `Corporativo TAMAR` | ARS | None | VARIABLE · TAMAR | RVS1O | corp_tamar / ARS TAMAR |
| ON ARS BADLAR | `Corporativo BADLAR` | ARS | None | VARIABLE · BADLAR | (ver grep) | corp_badlar / ARS BADLAR |
| ON UVA | `Corporativo UVA` | ARS | UVA | FIJA | FTM1O | corp_uva / UVA |
| ON CER | `Corporativo UVA` | ARS | CER | FIJA | (ver grep) | corp_uva / CER |
| ON Dólar-Linked | `Corporativo Dolar Linked` | ARS | A3500 | FIJA | CS40O | corp_dlk / USD-Linked |
| ON USD hard-dollar (cable) | `Corporativo Hard Dolar` | USD | None | FIJA | AEC2C | corp_hdcable / USD |
| ON USB hard-dollar MEP | `Corporativo Hard Dolar MEP` | USB | None | FIJA | AFCID | corp_hdmep / USB |

Subsoberanos (provinciales): `Clasificación="Sub-soberano"`. **Hoy no caen en
ninguna curva** — avisale al usuario si carga uno.

Tipos que NO están soportados todavía (avisá y consultá antes): **Dual
Dólar-Linked/CER** (falta curva + detección), curvas de subsoberanos,
`Corporativo CER` propio.

---

## Fichas múltiples (¡clave!)

Muchos instrumentos son MÁS de una ficha en `especies.py`. Cargá TODAS, espejando
las del comparable:

- **CER (boncer/lecer)** → base `TICKER` (Ajuste `CER`) + proy `TICKERj`
  (Industria `…Proyectado`, Ajuste `CER PROYECTADO`).
- **Dual Fija/TAMAR** → base `TICKER` (FIJA) + pata `TICKERv` (Industria
  `…Tamar/Fija`, VARIABLE_CAP · TAMAR).
- **Dual CER/TAMAR** → base `TICKER` (CER, FIJA) + proy `TICKERj` + pata
  `TICKERv` (Industria `…Tamar/CER`, VARIABLE_CAP · TAMAR).
- **Hard-dollar (global / ON cable)** → ficha de referencia `TICKER` (CLEAN,
  Moneda USD) + pata cable `TICKERC` (DIRTY, USD) + pata MEP `TICKERD` (DIRTY,
  USB). Ver "FX legs" en CLAUDE.md.
- **Bonar / Bopreal / ON MEP** → ficha base + pata `TICKERD` (MEP, USB, DIRTY).
- **Tasa fija / TAMAR / Letra simple** → 1 sola ficha.

En la duda: mirá cuántas fichas hermanas tiene el comparable
(`grep -nE "^TICKER(j|v|C|D)? = " especies.py`) y replicá exactamente ese set.

---

## Las 3 ediciones por ficha

Para que el sistema (bond_universe → Curvas, Posiciones, YAS) vea el bono, cada
ficha necesita **3 cosas** en `especies.py`:

1. **El dict** — en la sección de definiciones, junto a los de su mismo tipo:
   ```python
   TICKER = {
       "Nombre Security": "...",
       ...
       "Industria": "Soberano Inflación",
       ...
   }
   ```
2. **La conversión a Bono** — en la sección de conversiones (`grep -n "= rentafija.Bono(" especies.py`, ~línea 26336+), en el grupo de su tipo:
   ```python
   TICKER = rentafija.Bono(TICKER)
   ```
3. **La lista `todos_los_bonos`** (~línea 26894+) — agregá `TICKER,` en el bloque
   con el comentario de su tipo (`# SOBERANOS TAMAR`, etc.).

> Sólo 1+2 ya hacen que `bond_universe` lo vea (enumera instancias `Bono` del
> módulo); el paso 3 mantiene completo el registro `BONDS`/legacy. Hacé los 3.

Ubicá las inserciones **al lado del comparable** en cada una de las 3 secciones
(buscá el comparable con `grep -n` y editá cerca).

---

## Formato de la previsualización (paso 6)

Antes de escribir, mostrale al usuario algo así:

```
Voy a cargar 3 fichas para el Boncer TX31 (Dual CER/TAMAR):
  • TX31   (base, CER, FIJA)        → Curva dualcer  · Pos: Dual CER / TAMAR
  • TX31j  (CER proyectado)         → Curva cerproy/dualcer
  • TX31v  (pata TAMAR, VAR_CAP)    → Curva dualtamar
Comparable espejado: TXMJ9 / TXMJ9j / TXMJ9v.
Asumido (confirmá): lag CER -10, base 360, calificación CCC-, t+1.
Campos del aviso: emisión 30/06/2026, vto 30/06/2031, cupón CER+X%, bullet.
¿Lo cargo?
```

Recién con el OK, hacé las ediciones y corré el `preview.py` para verificar.
