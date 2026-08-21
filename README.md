# ΔYieldVertex · Calculadora de Bonos & Analytics

Suite de herramientas para análisis de **renta fija argentina**: pricing de bonos, curvas de tasas, monitoreo de mercado en tiempo real (BYMA), gestión de posiciones y un Order Management System (OMS).

**Autor: [Rodrigo Corvalán Salguero](https://github.com/rodrigocorvalan93)** · código fuente disponible bajo
[licencia de uso](LICENSE) para **Grupo Latin Securities / Delta Asset Management / Galileo**.
La administración del repositorio, los roles y la aceptación de cambios sobre el código canónico
son potestad del autor.

El **front actual** es una reescritura en **FastAPI + Jinja2 + HTMX + Alpine** (`backend/`), enfocada en performance (objetivo < 50 ms p95 server-side en el path caliente). La app Streamlit original (`OMSweb_app.py`) queda como referencia/legacy para portar lógica de negocio.

---

## 🧭 Mapa rápido

Puntos de entrada según el caso de uso:

| Entry point | Tipo | Para qué se usa |
|---|---|---|
| `backend/` (`uvicorn backend.main:app`) | ⭐ **FastAPI web app** | **Front actual.** Muro de login + roles, YAS, Nueva especie ad-hoc, Curvas, Mercado, Qué pasó, Posiciones, OMS, etc. Arquitectura y detalle: `backend/README.md` · **montaje en server / operación (IT): [`DEPLOY.md`](DEPLOY.md)** |
| `backend/static/excel/` | Add-in de Excel «YieldVertex» | Feed en vivo + calculadora YAS en la celda (`=OMS.*`), servido por la app local |
| `OMSweb_app.py` | Streamlit web app (legacy) | Dashboard original. Referencia para portar lógica; no se importa desde `backend/` |
| `bymaapi.py` | Script REPL | **Calculadora en vivo** desde VS Code Interactive (`bymaapi.bat` lanza `python -i`) |
| `rentafija.py` | Librería core | **Núcleo duro de cálculos** (TIR, MD, flujos, valuación). No se ejecuta solo, se importa |

---

## ⚡ Front web — FastAPI (`backend/`)

Reescritura moderna del front, sin frameworks JS pesados (sólo HTMX + Alpine; gráficos en SVG/uPlot). Estado de larga vida cacheado en memoria y un *warmup daemon* que precalienta el motor de cálculo al arranque, así el path caliente queda bajo **50 ms p95**.

### Pestañas
YAS (análisis de yields, con ubicación en curva y distancia a la NSS) · **Nueva especie** (calculadora ad-hoc: armás/pegás una ficha y calcula cashflow + métricas en vivo, sin tocar el universo) · Comparador · Curvas · Mercado · Break-even · Dólares (MEP/CCL/canje) · Tasas · Posiciones · Matriz · **Forwards** (matriz TIREA o margen TNA + histórico par-a-par con media/desvío/percentil) · Futuros · **Gráficos** (NSS por tramos, overlay de curvas, fuente BYMA o vector CAFCI) · Total Return · Escenario · Históricos · **Qué pasó** (resumen de la ventana por segmento + gráfico de cómo se movió la curva) · Créditos · CAFCI · Órdenes · Alertas (superuser). Además: `/conexion` (reconexión del feed por usuario) y `/admin`.

### Add-in de Excel «YieldVertex»
Reemplazo del feed Reuters + calculadora YAS dentro de Excel: `=OMS.QUOTE/FX/ROFEX/CAUCION/TABLA/HIST` en vivo y `=OMS.TIREA/PRECIO/TNA/TICKET/CALC/TR` puntuales, contra la instancia local de cada usuario. Instalación y referencia completa: **`backend/static/excel/README.md`** y **`backend/static/excel/FORMULAS.md`**.

### Usuarios y permisos
Muro de login con roles **superuser / premium / básico**. El superuser gestiona usuarios y qué pestañas ve cada rol desde `/admin`. Contraseñas hasheadas (PBKDF2 + salt), sesión por cookie firmada, recuperación por mail (SMTP). Config por env (nada de credenciales en el código) — ver `backend/README.md`.

### Correr

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
# abrir http://127.0.0.1:8000  (redirige a /login)
```

Env mínimas para el muro de login (o `AUTH_ENABLED=0` para dev sin muro):

```
APP_SUPERUSER_USER=<usuario>
APP_SUPERUSER_PASSWORD=<clave>
APP_SUPERUSER_EMAIL=<mail>
APP_SECRET_KEY=<hex largo>
```

Detalle de todas las env (SMTP, paths, etc.) y de la arquitectura del backend en **`backend/README.md`**.

### Desde el celular (Tailscale)

La app no se hostea en el teléfono: sigue corriendo en tu Mac/PC y el celu
abre el navegador contra ella por una VPN privada. **No** la expongas a
internet con túneles públicos — el OMS cursa órdenes reales.

1. Instalá [Tailscale](https://tailscale.com/download) en la máquina que corre
   la app y en el celular, con la misma cuenta (gratis para uso personal).
2. En `secrets.txt` agregá `APP_HOST=0.0.0.0` (hace que uvicorn escuche en la
   red, no sólo en localhost). `correr_app.command` la lee solo; a mano:
   `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
3. En el celu abrí `http://<nombre-de-tu-maquina>:8000` (el nombre aparece en
   la app de Tailscale). Login normal — el muro de sesión sigue activo.

La máquina que corre la app tiene que quedar prendida. Con la app abierta a
las 17:01 de un día hábil, la base histórica de px/tasas del día se guarda
sola (ver `HISTORICO_AUTOSAVE` en `backend/config.py`).

---

## 🗂️ Estructura del proyecto

### Núcleo de cálculo (motor matemático)

Estos módulos NO dependen de Streamlit ni de APIs de mercado. Son la base que usan tanto el front web como el script interactivo.

```
rentafija.py        Núcleo duro: pricing de bonos, TIR, TNA, MD, convexidad,
                    flujos de fondos, valuación dirty/clean, paridad.
indices.py          Índices y series de referencia: A3500, CER, UVA, Badlar,
                    inflación, dólar MEP/CCL/oficial. Refresh + cache.
especies.py         Catálogo de bonos (objetos Bond) y agrupaciones
                    (todos_los_bonos, BONDS, etc.). Importa rentafija.
utils.py            Helpers transversales: fechas, conversiones tasa,
                    HTTP utils, formateo, optimización (scipy).
dias_habiles.py     Calendario AR: feriados, días hábiles, settlement.
plotter.py          Gráficos (matplotlib): curvas, NSS, scatter, dispersión.
```

### Front web legacy — Streamlit (`OMSweb_app.py` + módulos `OMS*`)

El web app Streamlit es el front original (hoy legacy; el front actual es `backend/`). Importa todos los módulos `OMS*` para armar las tabs del dashboard. Se mantiene como referencia para portar lógica de negocio.

```
OMSweb_app.py             ⭐ Front principal Streamlit (dashboard, OMS, monitor)

OMSsettings.py            Config global (paths, constantes, parámetros)
OMSsecrets.py             Carga secrets.txt → os.environ (auto al importarse)
OMSapi.py                 Cliente HTTP de la API de mercado (BYMA / broker)
OMSmktdata.py             Market data en vivo (puntas, last, volumen) + threading
OMSticker.py              Stream de tickers / actualización background
OMSprices.py              Wrapper de pricing usando rentafija + market data
OMScauciones.py           Lógica específica de cauciones
OMScredit.py              Scoring crediticio (lee credit_scores.json)
OMSposiciones.py          Gestión de posiciones / cartera / PnL
OMSnews.py                Feed asíncrono de noticias (feedparser)
```

> El adapter `BondWrapper` que poblaba `BONDS` vive ahora dentro de `especies.py` (antes en un módulo `OMStransformaciones.py` aparte).

### Calculadora interactiva — VS Code (`bymaapi.py`)

Pensado para **uso interactivo en VS Code** (modo `python -i`, celdas `#%%`). Importa el núcleo (`rentafija`, `especies`, `utils`, `plotter`) y trae datos de BYMA en vivo. Útil para análisis ad-hoc, exploración de curvas y pricing manual.

Se lanza con `bymaapi.bat` (Windows) que apunta al path del repo en OneDrive.

### Utilities

```
export_credit_scores.py   Genera/actualiza credit_scores.json desde un Excel.
                          Correr cuando cambian los scores propietarios.
cafciapi.py               Helpers para consumir la API de CAFCI (FCIs).
```

### Datasets versionados (referencia, no sensibles)

```
a3500completo.csv         Serie histórica A3500 (BCRA mayorista)
cer_completo.csv          Serie histórica CER
bcra_data_backup.json     Snapshot BCRA para fallback offline
bymaprices.xlsx           Mapping tickers / referencia BYMA
data_segmento.xlsx        Clasificación interna por segmento
fwd_exclusions.json       Tickers excluidos del cálculo de forwards
ficha bonos vencidos.txt  Referencia histórica de bonos ya vencidos
```

---

## 🔗 Diagrama de dependencias

```
                    ┌──────────────────┐
                    │  OMSweb_app.py   │  ◄── Front Streamlit
                    └────────┬─────────┘
                             │ importa
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   OMS{api,mktdata,     OMS{credit,         OMS{news,
   prices,ticker,       cauciones,          posiciones,
   secrets,settings}    transformaciones}   plotter}
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
        ┌────────────────────────────────────────┐
        │   NÚCLEO (motor de cálculo, sin GUI)   │
        │                                        │
        │   rentafija ◄── especies ◄── indices   │
        │       ▲           ▲           ▲        │
        │       └───────────┼───────────┘        │
        │                   │                    │
        │   utils ◄── dias_habiles               │
        │   plotter                              │
        └────────────────────────────────────────┘
                             ▲
                             │ importa
                    ┌────────┴─────────┐
                    │   bymaapi.py     │  ◄── REPL en VS Code
                    └──────────────────┘
```

---

## 🛠️ Instalación

```bash
git clone https://github.com/rodrigocorvalan93/app_calculadoras_bonos.git
cd app_calculadoras_bonos

python -m venv venv
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # Linux/Mac

pip install -r requirements.txt
```

### Credenciales

Archivos locales (NO versionados, ver `.gitignore`):

- `secrets.txt` — credenciales de la API de mercado. Lo carga `OMSsecrets.py` automáticamente a `os.environ`.
- `credit_scores.json` — scoring crediticio propietario. Generar con `export_credit_scores.py`.
- `.streamlit/secrets.toml` — secrets de Streamlit (opcional).

---

## 🚀 Uso

### Front web FastAPI (uso normal)

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Front web Streamlit (legacy)

```bash
streamlit run OMSweb_app.py
```

### Calculadora interactiva (VS Code)

Abrir `bymaapi.py` en VS Code y ejecutar celdas con `Shift+Enter`, o lanzar:

```bash
bymaapi.bat       # Windows: abre python -i con el módulo cargado
```

### Importar el motor en otro script

```python
import rentafija
from especies import BONDS, todos_los_bonos
from indices import refresh_a3500_in_rentafija

# ...
```

---

## 📦 Política de versionado (`.gitignore` whitelist)

El `.gitignore` usa **paradigma whitelist**: ignora todo por default y sólo se versiona lo explícitamente listado. Para agregar un archivo nuevo al repo hay que sumarlo con `!` en la sección 2 del `.gitignore`. Esto evita que se cuelen secretos, planillas internas de Delta o backups de OneDrive.

---

## 📝 Stack

**Front actual:** FastAPI · Jinja2 · HTMX · Alpine.js · uPlot/SVG · Starlette SessionMiddleware (auth) · itsdangerous · httpx · uvicorn

**Núcleo y legacy:** Python 3.11 · pandas/numpy · scipy · matplotlib/plotly · requests · feedparser · holidays · openpyxl · Streamlit (front legacy)
