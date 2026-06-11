# Inserción en especies.py y verificación post-alta

`especies.py` es legacy y crítico (lista "no tocar salvo necesario" de CLAUDE.md). El alta de un
bono es la excepción legítima — pero SIEMPRE con confirmación previa del usuario y verificación
después.

## Las 3 ediciones por ficha

Para que el sistema (bond_universe → Curvas, Posiciones, YAS, Mercado) vea el bono, cada ficha
necesita TRES cosas en `especies.py`:

1. **El dict** — en la sección de definiciones, junto a los de su mismo tipo:
   ```python
   TICKER = { "Nombre Security": "...", ... }
   ```
2. **La conversión a Bono** — en la sección de conversiones
   (`grep -n "= rentafija.Bono(" especies.py`), en el grupo de su tipo:
   ```python
   TICKER = rentafija.Bono(TICKER)
   ```
3. **La lista `todos_los_bonos`** (`grep -n "todos_los_bonos = " especies.py`) — agregá `TICKER,`
   en el bloque comentado de su tipo (`# SOBERANOS TAMAR`, `# CORPORATIVOS UVA`, etc.).

> Sólo 1+2 ya hacen que `bond_universe` lo vea (enumera instancias `Bono` del módulo); el paso 3
> mantiene completo el registro `BONDS`/legacy. Hacé los 3, para CADA ficha hermana.

**Ubicación**: insertá al lado del comparable en cada una de las 3 secciones (buscalo con
`grep -n "^COMPARABLE = {" especies.py` etc.). Así el archivo queda ordenado por tipo.

## Verificación post-alta (obligatoria)

Desde la raíz del repo:

```bash
# 1) ¿Carga? ¿Están todas las hermanas? ¿Cae en la curva/categoría esperada?
python3 .claude/skills/carga-bonos-rentafija/scripts/preview.py TICKER

# 2) ¿El set de hermanas y la estructura son idénticos al comparable?
python3 .claude/skills/carga-bonos-rentafija/scripts/compare.py TICKER COMPARABLE
```

- `preview.py` expande automáticamente a las hermanas presentes (`j`/`v`/`C`/`D`) y muestra, por
  cada una: clasificación, moneda/ajuste, tasa/index, vencimiento, **curva(s)** en que cae y la
  **Categoría/Tasa/Calificación de Posiciones**. Si dice "no está en el universo", faltó alguna de
  las 3 ediciones.
- `compare.py` exige que el ticker nuevo tenga **el mismo set de hermanas** que el comparable
  (hermana faltante = error — el olvido más común) y que cada par tenga **estructura idéntica**
  (clasificación, industria base, ajuste, tasa, convenciones, lags, quote) con los campos propios
  (código/ISIN/nombre/vto) **distintos**.

Pegale ambas salidas al usuario. `[X]` en cualquiera → corregir antes de dar por terminado.

## Checklist final

1. ¿`validar_bono.py` pasó antes de insertar? (coherencia interna)
2. ¿Las 3 ediciones por CADA ficha hermana?
3. ¿`preview.py` las muestra en la curva/categoría esperada?
4. ¿`compare.py` da `[OK]` contra el comparable?
5. ¿Las "Notas de carga" quedaron en el chat con las banderas de lo no confirmado?

## Gotchas conocidos del archivo

- En fichas viejas el par `"Código"`/`"ISIN"` a veces está **invertido** (p. ej. TXMJ8 tiene el ISIN
  en `Código`). **El nombre de la VARIABLE es lo que manda** (es el ticker que enumera
  `bond_universe`); no copies la inversión en fichas nuevas.
- Los strings de `Industria`/`Clasificación` se matchean **EXACTO** (mayúsculas, tildes, barras) —
  un typo manda el bono a otra curva o lo deja sin clasificar. Por eso siempre espejá el comparable.
- La guía maestra al inicio de `especies.py` (bloque `'''GUÍA DE CARGA'''`) es la fuente
  autoritativa del mapeo tipo → Industria/Clasificación → Curva/Posición.
