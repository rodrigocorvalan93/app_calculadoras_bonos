---
name: carga-bonos-rentafija
description: >
  Carga un bono nuevo (ON o soberano) en la calculadora de renta fija: lee los PDFs (Aviso de
  Resultados, Suplemento de Prospecto, aviso de licitación del Tesoro), clasifica el instrumento
  (TAMAR, BADLAR, CER, UVA, Dollar Linked/A3500, Hard Dollar, Tasa Fija, duales), extrae cronograma,
  amortización y régimen de rescate (call), arma el/los dict con el formato exacto de especies.py
  (incluidas las fichas hermanas: pata "j" proyectada, pata "v" dual, patas C/D hard-dollar), y —
  previa confirmación del usuario — los INSERTA en especies.py y verifica que caigan en la Curva y
  la Categoría de Posiciones correctas. Usala SIEMPRE que el usuario mande PDFs de un bono argentino
  o pida "cargar el bono/especie", "armar la estructura/el dict", "dar de alta un bono", "leer un
  aviso de licitación", o mencione un ticker de ON/soberano (con solo el ticker se resuelve
  emisor/ISIN/moneda por MAE y los links por CNV). También para identificar el tipo de bono o
  revisar si tiene call.
---

# Carga de bonos en la calculadora de renta fija

Convierte los documentos de una emisión en la(s) ficha(s) de `especies.py`, **las inserta** y
**verifica el impacto** en Curvas y Posiciones. Dos fases con una compuerta en el medio:

1. **EXTRACCIÓN** (PDFs → dict): clasificar, extraer, validar coherencia. El entregable intermedio
   es el bloque de código pegable + "Notas de carga".
2. **INSERCIÓN + VERIFICACIÓN** (dict → especies.py): sólo tras el **OK explícito del usuario**.
   `especies.py` es legacy y crítico — nunca escribas sin confirmación previa.

## Insumos

- **Aviso de Resultados** — autoritativo de *lo que se fijó en la licitación*: margen/tasa de corte
  (el suplemento suele dar un rango; el número real está acá), fecha de emisión/liquidación, monto,
  a veces ISIN y VN.
- **Suplemento de Prospecto** — autoritativo de *la estructura*: cronograma, amortización,
  devengamiento, índice/ajuste y lags, y el **régimen de rescate (call)**.
- **Soberanos**: el equivalente es el aviso de licitación/condiciones de la Secretaría de Finanzas
  (mismo flujo; sin call, sin CNV).
- **Solo un ticker**: `python3 scripts/buscar_mae.py --codigo <ticker>` → ISIN/emisor/moneda;
  `python3 scripts/buscar_cnv.py "<emisor>"` → links de los PDFs. Las condiciones viven en los PDFs
  y **no se pueden bajar del AIF automáticamente** (valet-key/CSRF): mostrá los links y pedile al
  usuario que los adjunte. Con eso volvés al camino principal.

## FASE 1 — Extracción

1. **Leé los PDFs** (`references/lectura-pdfs.md`, incluye OCR y los gotchas de pypdf). No adivines:
   si una sección no se lee, decilo.

2. **Clasificá y resolvé el ticker** (`references/tipos-y-convenciones.md`). La clasificación
   determina los tres campos acoplados (`Index` / `Tipo Tasa Interés` / `Ajuste sobre Capital`) y
   qué familia de lag aplica. El ticker NO se deriva: sale del MAE
   (`scripts/buscar_mae.py --emisor "<nombre>"`); el ticker de la casa = código MAE con la letra
   final por moneda (`O` pesos / `D` MEP→`Moneda USB` / `C` cable→`Moneda USD`).

3. **Espejá un bono comparable.** Antes de armar el dict de memoria, buscá en `especies.py` un bono
   existente del MISMO tipo (misma `Clasificación`/`Industria`; comparables sugeridos en
   `tipos-y-convenciones.md` y `ejemplos.md`), miralo con
   `python3 scripts/preview.py <COMPARABLE>` y cloná su estructura cambiando sólo lo propio del
   papel nuevo. Es la forma más confiable de respetar convenciones, lags y fichas hermanas.

4. **Extraé campo por campo** (`references/plantilla-y-campos.md`): del Aviso el corte/emisión/ISIN;
   del Suplemento cronograma/amortización/convenciones/lags. ISIN faltante → MAE; `Calificación` →
   `scripts/buscar_calificacion.py` (FIX, regla ≤12m corto / >12m largo plazo, siempre `(arg)`).
   Convenciones default (lag −7 TAMAR/BADLAR, −10 CER, −5 UVA, −3 A3500; corp Actual/365, sob
   ISMA-30/360): punto de partida, **verificá cada una contra el suplemento** y anotá los desvíos.

5. **El call es lo más importante** (`references/call-rescate.md`): mapear rescate a opción del
   emisor a `Callable/Tipo de Call/Fecha Call/Precio Call`; el tax call NO se carga; ambiguo →
   `False` + bandera roja en notas. **Nunca inventes un call.**

6. **Armá TODAS las fichas hermanas** según el tipo (detalle en `tipos-y-convenciones.md`):
   - CER / UVA → base + pata **"j"** proyectada (3 diferencias: nombre+`j`, Industria+" Proyectado",
     ajuste `… PROYECTADO`). Dollar Linked NO lleva "j".
   - **Dual soberano** (CER/TAMAR o Fija/TAMAR) → base + "j" (si CER) + pata **"v"**
     (`VARIABLE_CAP` + `Index TAMAR`, Industria `…Dual Tamar/CER` o `…Dual Tamar/Fija`).
   - **Hard-dollar cable** (global / ON ley ext) → ficha referencia CLEAN + pata **C** (DIRTY, USD);
     **Bonar / ON MEP** → pata **D** (DIRTY, USB). En la duda: replicá el set de hermanas del
     comparable (`grep -nE "^COMP(j|v|C|D)? = " especies.py`).

7. **Validá coherencia ANTES de mostrar**: guardá el/los dict en un `.py` temporal y corré
   `python3 scripts/validar_bono.py <archivo.py>` (fechas ordenadas, amortización suma 100, lags con
   signo correcto, call completo, pata "j" coherente). Corregí lo que marque.

8. **Mostrá el preview y pedí confirmación.** Bloque(s) de código pegable(s) con el estilo exacto de
   `especies.py` (comillas dobles, fechas `"dd/mm/aaaa"`, flotantes con punto, campos de
   trazabilidad `Comentarios` / `Aviso Resultados` / `Suplemento Prospecto`) + **"Notas de carga"**:
   tipo y por qué (1 línea), desvíos del default con referencia, banderas de lo no confirmado
   (call primero), y a qué **Curva** y **Categoría/Tasa de Posiciones** va a caer. Cerrá con
   **"¿Lo inserto en especies.py?"**.

## FASE 2 — Inserción + verificación (sólo tras el OK)

Detalle completo en `references/insercion-y-verificacion.md`. Resumen: cada ficha necesita **3
ediciones** en `especies.py` (el dict + `TICKER = rentafija.Bono(TICKER)` + `TICKER,` en
`todos_los_bonos`), ubicadas **al lado del comparable** en cada sección. Después verificá:

```bash
python3 scripts/preview.py <TICKER>            # carga + hermanas + curva + posiciones
python3 scripts/compare.py <TICKER> <COMPARABLE>   # set de hermanas completo + estructura idéntica
```

Pegale ambas salidas al usuario. Si `compare.py` marca `[X]` (hermana faltante o campo estructural
distinto), corregí antes de dar por terminado.

## Referencias y scripts

| Archivo | Qué tiene |
|---|---|
| `references/tipos-y-convenciones.md` | Taxonomía, campos acoplados, defaults, ticker MAE→casa, pata "j", fichas hermanas por tipo, strings exactos de Industria/Clasificación → Curvas/Posiciones |
| `references/plantilla-y-campos.md` | El dict campo por campo y de qué documento sale cada cosa |
| `references/call-rescate.md` | Cómo leer y mapear el régimen de rescate |
| `references/ejemplos.md` | Ejemplos reales resueltos por tipo (incluye dual 3 fichas) |
| `references/lectura-pdfs.md` | Extracción de texto de PDFs (+ OCR, + gotchas) |
| `references/buscar-fuentes-cnv.md` | Links de trazabilidad CNV |
| `references/insercion-y-verificacion.md` | Las 3 ediciones, ubicación, checklist post-alta |
| `scripts/buscar_mae.py` | Ticker/ISIN/moneda por código o emisor (pagina el GridView) |
| `scripts/buscar_cnv.py` | Links de Suplemento/Aviso en CNV por razón social |
| `scripts/buscar_calificacion.py` | Calificación FIX con regla CP/LP por plazo |
| `scripts/validar_bono.py` | Coherencia interna del dict (pre-inserción) |
| `scripts/preview.py` | Post-alta: campos discriminantes + hermanas + curva(s) + Posiciones |
| `scripts/compare.py` | Post-alta: set de hermanas vs comparable + estructura idéntica |
