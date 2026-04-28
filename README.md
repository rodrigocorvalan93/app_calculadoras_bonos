# OMS · Calculadora de Bonos & Analytics

Suite de herramientas para análisis de **renta fija argentina**: pricing de bonos, curvas de tasas, monitoreo de mercado en tiempo real (BYMA), gestión de posiciones y un Order Management System (OMS) sobre Streamlit.

---

## 🧭 Mapa rápido

El proyecto tiene **tres puntos de entrada** según el caso de uso:

| Entry point | Tipo | Para qué se usa |
|---|---|---|
| `OMSweb_app.py` | Streamlit web app | **Front principal.** Dashboard completo: curvas, monitor, posiciones, news, OMS |
| `bymaapi.py` | Script REPL | **Calculadora en vivo** desde VS Code Interactive (`bymaapi.bat` lanza `python -i`) |
| `rentafija.py` | Librería core | **Núcleo duro de cálculos** (TIR, MD, flujos, valuación). No se ejecuta solo, se importa |

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

### Front web — Streamlit (`OMSweb_app.py` + módulos `OMS*`)

El web app es el agregador. Importa todos los módulos `OMS*` para armar las distintas tabs del dashboard.

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
OMStransformaciones.py    BondWrapper — adapter entre objetos Bond y la GUI
```

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

### Front web (uso normal)

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

Python 3.x · Streamlit · pandas/numpy · scipy · matplotlib/plotly · requests · feedparser · holidays · openpyxl
