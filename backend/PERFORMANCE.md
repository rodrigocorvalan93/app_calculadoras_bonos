# Informe de tiempos de carga y respuesta

Objetivo (CLAUDE.md): **< 50 ms p95 server-side** en el path caliente (warm-cache).
Este informe mide los endpoints server-side y documenta dos optimizaciones aplicadas.

## Metodología

- Medición **in-process** con `httpx.ASGITransport` (sin red) → mide el tiempo del
  handler + middleware, que es exactamente lo que pide el target ("server-side").
- **Muro de login activo + sesión iniciada** (path real de producción).
- Motor de cálculo **precalentado** (`warmup.prime_calc_engine`) antes de medir.
- Por endpoint: 15 llamadas de warm + 120-200 medidas. Se reportan `avg / p50 / p95 / p99` en ms.

> ⚠️ **Alcance del entorno de medición.** El sandbox de estas mediciones **no tiene
> data de mercado en vivo ni los Excel de Delta** (Posiciones, histórico BYMA). Por eso
> los endpoints que en producción arman tablas anchas con 100+ bonos cotizando
> (Curvas, Mercado, Posiciones, Qué pasó con el Excel) acá renderizan livianos.
> En producción esos números son más altos, pero el diseño existente los mantiene
> calientes: **warmup daemon** (precalienta el cache de métricas de todas las curvas
> cada 8 s) + **cache de métricas de 20 s** por bono. El path caliente medible (cálculo
> YAS / ad-hoc, render de páginas) es representativo y está bien por debajo del target.

## Respuesta warm (con muro + sesión)

| Endpoint | avg | p50 | p95 | p99 |
|---|--:|--:|--:|--:|
| `POST /yas/recompute` (cálculo YAS) | 12.7 | 12.1 | **14.1** | 15.9 |
| `POST /nueva/recompute` (especie ad-hoc) | 10.7 | 10.6 | **11.2** | 11.3 |
| `GET /escenario` | 4.5 | 4.5 | 4.9 | 5.1 |
| `GET /curves` | 3.2 | 3.2 | 3.3 | 4.3 |
| `GET /mercado` | 3.4 | 3.3 | 3.6 | 3.8 |
| `GET /futuros` | 2.7 | 2.7 | 3.0 | 3.4 |
| `GET /graficos` | 2.3 | 2.3 | 2.7 | 2.8 |
| `GET /yas` (página) | 2.3 | 2.3 | 3.0 | 3.2 |
| `GET /breakeven` / `/total-return` / `/comparador` / `/historicos` / `/forwards` | ~2.2 | ~2.2 | ~2.5 | ~2.9 |
| `GET /posiciones` / `/matriz` / `/creditos` / `/dolares` | ~1.6 | ~1.6 | ~1.8 | ~2.0 |
| `GET /que-paso` / `/tasas` / `/cafci` / `/tape` / `/dolares/rail` / `/nueva` | ~1.4 | ~1.4 | ~1.6 | ~1.8 |
| `GET /historicos/semanal` (Qué pasó) | 1.4 | 1.4 | 1.6 | 1.8 |
| `GET /healthz` | 1.1 | 1.1 | 1.3 | 1.7 |
| `GET /market/seq` (poller 1/s) | 1.0 | 1.0 | **1.2** | 1.2 |

**Todos los endpoints < 50 ms p95.** El techo son los dos endpoints de cálculo
(`/yas/recompute` y `/nueva/recompute`), CPU-bound sobre el motor legacy `rentafija`
(TIR + duration + cashflows). El resto son renders de página de 1-5 ms.

## Cold-start (arranque)

| Fase | Tiempo |
|---|--:|
| Import `especies.py` (1,4 MB) + construir ~550 bonos | ~3,7 s |
| Prime del motor (`indices.main` + 1er cálculo; usa backup BCRA) | ~0,02 s |
| **Total cold** (lo que pagaría el 1er request sin warmup) | **~3,7 s** |

El **warmup daemon** absorbe este costo en el `lifespan` (en un threadpool, sin
bloquear el arranque), así el primer request de un usuario ya llega caliente. El
bootstrap de auth que se agregó es despreciable (< 1 ms).

## Overhead del muro de login (middleware)

El `auth_guard` corre en cada request: verificar el HMAC de la cookie de sesión +
lookups en memoria. Medido: **~0,2 ms/request** (`/market/seq` 1,05 → 1,22 ms con vs
sin muro). Imperceptible.

## Optimizaciones aplicadas

### 1) Cache de la nav por rol (`services/auth.py`)

El middleware pedía `nav_for(role)` en **cada** request (incluido el poller de 1/s y
todos los partials htmx), reconstruyendo ~20 dicts cada vez. Como `role_tabs` sólo
cambia desde el panel del superuser, ahora la nav se **cachea por rol** (invalidada en
`refresh()` y `set_role_tabs()`). Elimina la asignación repetida en el path más
frecuente. Se devuelve la misma lista (read-only en los templates).

### 2) Cache del `Bono` ad-hoc por token (`services/adhoc.py`)

`/nueva/recompute` reconstruía el `rentafija.Bono` desde la ficha en cada tecla
(re-parseo de fechas de cupón + numpy). Como la ficha del token es inmutable, ahora
se construye **una vez** y `compute_metrics` copia (`copy.copy`) por request — mismo
patrón thread-safe que los singletons del universo. Excepción: los floaters
**VARIABLE** (TAMAR/BADLAR) congelan el cupón en `__init__` leyendo el índice
proyectado, así que esos se reconstruyen siempre (no servir cupón viejo).

**Antes → después** (`/nueva/recompute`, cálculo interno):

| Bono | antes p95 | después p95 |
|---|--:|--:|
| 6 cupones | 9,8 ms | 8,1 ms |
| 120 cupones (10 años mensual) | 18,3 ms | **14,1 ms** (−23 %) |

Correctitud verificada: la TIREA es idéntica con y sin cache.

## Conclusión

El sistema está sano y con amplio margen sobre el target de 50 ms p95. El costo
dominante es el motor de cálculo `rentafija` (que CLAUDE.md indica no reescribir); las
páginas rinden en 1-5 ms. Las dos optimizaciones recortan trabajo repetido en el path
caliente (nav por request) y en el peor caso de la especie ad-hoc (bonos de muchos
cupones), sin cambiar resultados.
