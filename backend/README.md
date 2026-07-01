# backend/ — FastAPI rewrite (Fase 1: YAS)

Reescritura del frontend Streamlit en FastAPI + Jinja2 + HTMX + Alpine.js.
Single-process local, sub-100ms en re-cómputo de YAS, sin cloud, sin build step.

Solo el panel YAS está implementado. Curvas, Mercado, Comparador, Forwards,
WebSocket en vivo, charts, tape de trades — todo eso llega en fases siguientes.

## Cómo correr

```bash
# Desde la raíz del repo
python -m venv .venv-fastapi
source .venv-fastapi/bin/activate     # Windows: .venv-fastapi\Scripts\activate
pip install -r backend/requirements.txt

# Variables de entorno opcionales (Fase 1 no las necesita para calcular;
# son para que el lifespan de FastAPI haga login al broker — se puede omitir):
export PRIMARY_USER="..."
export PRIMARY_PASS="..."

uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Abrir <http://127.0.0.1:8000/yas>.

## Lo que ya funciona (Fase 1)

- Dropdown con los ~480 bonos de `especies.py` (todas las instancias
  `rentafija.Bono` exportadas a módulo).
- Cuatro modos de input: **Precio**, **TIREA**, **TNA**, **Margen TNA**.
- Recompute por HTMX: form `hx-post=/yas/recompute` con
  `hx-trigger="change, keyup changed delay:80ms from:input[name=value]"` →
  partial swap de las cards de métricas + ticket.
- Convención TNA por tipo de bono y Margen TNA para `VARIABLE` /
  `VARIABLE_CAP` (la corrección del commit 0106d25 está portada).
- Format es-AR (decimales con coma, separador de miles con punto, fechas
  DD/MM/AAAA).
- Overrides opcionales: settlement custom, TC (A3500) custom.
- Thread-safety: lock por código + `copy.copy(bono)` antes de mutar,
  igual al patrón `_bond_obj_copy` del legacy.
- Health check en `/healthz` (devuelve cantidad de bonos cargados +
  estado de auth al broker).

## Lo que NO está aún

- WebSocket al broker / hub WS hacia el navegador (Fase 4).
- Auto-refresh de precios en vivo. El form se recalcula solo cuando el
  user cambia un input — no hay polling todavía.
- Tabs Curvas / Mercado / Comparador / Forwards (Fases 2-3).
- Charts (Lightweight Charts + Plotly) — Fase 5.
- Multi-pestaña sync (tab-id en sessionStorage) — Fase 4.
- Tailwind build. Tailwind no se usa aún; el CSS está a mano en
  `static/css/style.css`. Build se agrega en Fase 6.

## Arquitectura

```
backend/
  main.py                  FastAPI app + lifespan (carga universo, opcional login broker)
  config.py                Settings vía pydantic-settings (.env)
  cache.py                 LockedTTLCache (genérico para fases siguientes)
  locale_ar.py             Filtros Jinja2 ar_pct / ar_num / ar_date
  routes/
    yas.py                 /yas, /yas/recompute, /yas/meta/{code}
  services/
    bond_universe.py       Enumera bonos desde especies.py (lazy)
    pricing.py             compute_metrics() — port de _ticket_numeric + _bond_obj_copy
    primary_ws.py          WS market data + REST autenticado (login broker; lo usa el OMS)
  templates/
    base.html              Layout topbar + content + footer
    yas.html               Página completa: form + result + conv-note
    partials/
      yas_header.html      Strip con código/nombre/tipo/vto/moneda
      yas_metrics.html     5+5+3 cards (precio/TIREA/TNA/TEM/Duration/paridad/IC/...)
      yas_ticket.html      Tabla ticket en formato es-AR
      yas_result.html      Wrapper que mete metrics + ticket en el #yas-result
  static/
    css/style.css          Tema 1816-like
    js/app.js              Sólo helpers de debug (htmx 2.0 + Alpine.js 3 vía CDN)
```

## Convenciones implementadas

| Tipo de bono | Detección | Conversión TNA aplicada por rentafija |
|---|---|---|
| Dual TAMAR (VARIABLE_CAP + TAMAR) | `tipo_tasa_interes == "VARIABLE_CAP"` y `index == "TAMAR"` | Margen TNA: `((1+TIREA)^(32/365)−1)×(365/32) − TAMAR/100` |
| CER / CER proyectado | `"CER" in ajuste_sobre_capital` | `tir_a_tna(TIREA, 180, 365)` (vía rentafija) |
| Hard-dollar / USD | `moneda == "USD"` | `tir_a_tna(TIREA, 180, 360)` |
| DLK (A3500) | `"A3500" in ajuste_sobre_capital` | `tir_a_tna(TIREA, 90, 365)` |
| LECAP / TAMAR puro / bullets ARS | default | `tir_a_tna(TIREA, días_remanentes, 365)` |

Para la **TNA en sí**, la app delega en `rentafija.Bono.calcula_tirea`
(igual que el legacy YAS) — ahí se aplica la convención por
`cnv_tna`/`convencion_base` del bono. La detección por tipo (la tabla del
prompt) se usa para mostrar la convención correcta en la UI y para
elegir la fórmula de margen TNA. Si en algún caso la TNA reportada no
encaja con la convención esperada, el fix correcto es en `rentafija.py`
(como ya se hizo para el cálculo del margen en el commit 0106d25).

## Tests

```bash
pytest -q
```

Se ejecutan:
- Parse de números es-AR (`'87,30'` ↔ `'87.30'` ↔ `'1.234.567,89'`).
- Cálculo end-to-end para TXMJ9v @ 87,30 (dual TAMAR): TIREA, TNA, Margen
  TNA finitos y dentro de rango plausible (0,10 < TNA < 0,80;
  −0,30 < Margen TNA < 0,30).
- Cálculo para un LECAP y un hard-dollar (USD, FIJA).
- HTTP: `GET /yas` y `POST /yas/recompute` devuelven 200 y el HTML
  partial contiene los labels esperados.

> **TXMJ9v @ 87,30 hoy** (TAMAR aplicable avg-5d = 22,875%): el pipeline
> nuevo devuelve **TIREA = 35,81% · TNA = 31,03% · Margen TNA = 8,15%**.
> El target del prompt (TNA ≈ 31%, Margen TNA ≈ 8%) se cumple.
> Para diagnóstico también se expone `tna_raw = 51,34%`, que es lo que
> `rentafija.calcula_tirea` deja en `obj.tna` con la convención "plazo
> remanente / 360" — esa es la TNA cruda que reportaba el legacy y que
> motivó este rewrite del pipeline YAS.

### Cómo se llegó al fix

El commit `0106d25` corrigió **solo el cálculo del Margen TNA** (la fórmula
cap 32/365 para `VARIABLE_CAP`). La TNA reportada seguía siendo
`obj.tna` cruda. Este rewrite agrega `pricing.tna_from_obj(obj, tirea)`,
que aplica la convención correcta por tipo de bono detectado desde los
atributos del objeto Bono — la tabla del prompt. También invierte la
fórmula correcta cuando el user ingresa por `mode=tna` o `mode=margen`,
para que los cuatro modos lleguen al mismo TIREA (`test_txmj9v_modes_are_symmetric`).

## Performance

Target: **< 50 ms p95 en recompute** (1816-style). Medido sobre 100
calls a `POST /yas/recompute` con el server warm:

```
n=100  avg=0.0079s  p50=0.0078s  p95=0.0094s  p99=0.0111s  max=0.0111s
```

- Recompute warm: **~8 ms p50, ~9 ms p95**.
- Cambio de bono (incluye OOB swap del header): **~9 ms**.
- Render inicial `GET /yas` (dropdown con 481 bonos): **~9 ms**.

El cold-start aún es lento porque `indices.main()` carga el backup BCRA
en el primer acceso (segundos). Mitigación en Fase 2: agregar al lifespan
una warmup task que dispare la carga sin bloquear el arranque.

## Decisiones pendientes para mergear

- [ ] Branch a la que pushear (este chat va a `claude/laughing-turing-yG3tA`,
      el prompt mencionaba `feature/fastapi-rewrite` — abrir PR contra
      `main` desde la branch correcta).
- [ ] `_legacy/OMSweb_app.py`: el archivo sigue en la raíz para no romper
      la app Streamlit existente. Mover en Fase 6.
- [ ] Confirmar visualmente abriendo `http://127.0.0.1:8000/yas`,
      seleccionando TXMJ9v y comparando con la app Streamlit corriendo
      en paralelo.

## Auth (login wall + roles)

La app tiene un muro de login con 3 roles: **superuser**, **premium**,
**básico**. El superuser gestiona usuarios y qué pestañas ve cada rol desde
`/admin`. Config por env (nada de contraseñas en el código):

```
AUTH_ENABLED=1                       # 0 apaga el muro (dev/emergencia)
APP_SECRET_KEY=<hex largo>           # firma de la cookie de sesión (si falta
                                     # se autogenera y persiste en el store)
APP_USERS_PATH=auth_store.json       # store de usuarios (gitignored). Default: raíz
APP_SUPERUSER_USER=rodricor93        # se siembra en el 1er arranque si no hay superuser
APP_SUPERUSER_PASSWORD=<tu clave>
APP_SUPERUSER_EMAIL=vos@ejemplo.com
APP_BASE_URL=https://tuapp.example   # para los links de reset por mail

# SMTP para recuperación de contraseña (Gmail: App Password, no la clave normal)
APP_SMTP_HOST=smtp.gmail.com
APP_SMTP_PORT=587
APP_SMTP_USER=vos@gmail.com
APP_SMTP_PASSWORD=<app password>
APP_SMTP_FROM=vos@gmail.com
```

- El hash de contraseñas es PBKDF2-HMAC-SHA256 con salt por usuario (stdlib).
- El gating es a nivel de página: las sub-rutas (partials/data) sólo piden
  sesión. Overhead del middleware: ~0,2 ms/request (cookie HMAC + lookups).
- Recuperación: `/forgot` manda un link de reset por mail (si SMTP está
  configurado); el superuser también puede resetear cualquier clave desde `/admin`.
