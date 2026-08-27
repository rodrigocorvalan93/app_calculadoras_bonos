# DEPLOY — guía de montaje y operación (para IT)

Cómo montar **ΔYieldVertex** en un servidor, mantenerla corriendo y actualizarla.
Este doc es la referencia de OPERACIÓN; la arquitectura interna está en
`backend/README.md` y las mediciones de performance en `backend/PERFORMANCE.md`.
Gobernanza del código: ver `README.md` y `LICENSE` (autoría y administración del
repo son potestad de Rodrigo Corvalán Salguero).

---

## 1. Qué es (en 5 líneas)

- **Una app Python** (FastAPI + uvicorn) que sirve HTML por HTTP en el puerto
  **8000** y, si hay certificados, un puente HTTPS en el **8443** para el
  add-in de Excel (Office exige https).
- **Sin base de datos**: el estado vivo (precios, curvas, caches) está **en
  memoria del proceso**; lo persistente son archivos chicos (JSON/Excel) en la
  carpeta del repo.
- Se conecta **hacia afuera** a: broker Primary/Matriz (REST + WebSocket de
  market data), BCRA, y opcionalmente MAE, CAFCI, SMTP y feeds RSS.

## 2. La regla de oro: UN solo proceso

La app es **stateful en memoria** (store de mercado alimentado por el WebSocket
del broker, caches, warmup). Por diseño:

- ❌ `uvicorn --workers N` — cada worker vería precios distintos.
- ❌ Dos instancias detrás de un balanceador — mismo problema, más el OMS.
- ❌ `--reload` en el server — es una herramienta de desarrollo.
- ✅ **Un proceso, un servidor**. Para 10–30 usuarios de desk sobra por un
  orden de magnitud (p95 < 15 ms server-side; ver `backend/PERFORMANCE.md`).

Si algún día hiciera falta más capacidad: máquina más grande, no más procesos.

## 3. Requisitos

| Qué | Detalle |
|---|---|
| SO | Windows Server / Windows 10-11, o Linux (ambos probados; scripts para los dos) |
| Python | 3.12+ recomendado (desarrollado en 3.11–3.14) |
| Git | para clonar y actualizar |
| Red saliente | `api.latinsecurities.matrizoms.com.ar` (REST+WSS), `api.bcra.gob.ar`; opcionales: MAE, CAFCI, SMTP (587), RSS |
| Red entrante | 8000/tcp (app) y 8443/tcp (add-in Excel) **sólo desde la red interna/VPN** — nunca expuesto a internet |
| Disco | < 2 GB (repo + venv + datos) |

> **⚠️ Carpeta del repo: FUERA de OneDrive/Dropbox/etc.** En el server el repo
> se actualiza por `git pull`, no por sync. OneDrive lockea archivos mientras
> sube y ya causó corrupción de escrituras y archivos "conflicto de copia".
> Sugerido: `C:\apps\yieldvertex` o `/opt/yieldvertex/app`.

## 4. Instalación (Windows, paso a paso)

```powershell
# 1. Clonar FUERA de OneDrive
git clone <url-del-repo> C:\apps\yieldvertex
cd C:\apps\yieldvertex

# 2. Entorno e instalación de dependencias (única fuente: backend\requirements.txt)
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt

# 3. Credenciales y config (sección 5) → crear C:\apps\yieldvertex\.env
#    (o secrets.txt, mismo formato KEY=VALUE). Restringir permisos NTFS del archivo.

# 4. Certificados del add-in de Excel (sección 8) — omitir si no se usa Excel:
.venv\Scripts\python -m backend.tools.https_local --host <NOMBRE-DEL-SERVER> --host <IP-LAN>

# 5. Instalar como servicio con auto-restart (PowerShell como Administrador):
deploy\install_service_windows.ps1 -BindHost 0.0.0.0

# 6. Verificar:
curl http://127.0.0.1:8000/healthz
```

En Linux: mismo flujo con `deploy/yieldvertex.service` (las instrucciones están
comentadas dentro del archivo).

## 5. Configuración (env vars / `.env` / `secrets.txt`)

La app lee, en este orden: **env vars reales** → **`.env`** (raíz del repo) →
**`secrets.txt`** (raíz, formato `KEY=VALUE`, mismo loader que la app legacy).
Nombres completos en `backend/config.py`. Las que importan para el server:

| Variable | Default | Notas |
|---|---|---|
| `AUTH_ENABLED` | `1` | **Nunca `0` en un server.** Con `0` + host no-loopback la app directamente se niega a arrancar (guard de arranque). |
| `APP_HOST` | — | Informativa para el guard; el bind real lo fija el servicio (`--host`). El script la setea igual al bind. |
| `APP_SUPERUSER_USER` / `APP_SUPERUSER_PASSWORD` / `APP_SUPERUSER_EMAIL` | — | Bootstrap del superuser en el PRIMER arranque (después se administra en `/admin`). |
| `OMS_USER` / `OMS_PASS` | — | Credenciales del broker (market data + órdenes). También acepta `PRIMARY_USER`/`PRIMARY_PASS`. |
| `OMS_LIVE` | `0` | **⚠️ En `0` toda orden es PAPER (simulada).** `1` habilita el envío real al broker, con topes (`OMS_MAX_NOTIONAL*`, banda de precio). Prender sólo con OK de la mesa. |
| `OMS_COMITENTES` | — | JSON de cuentas por broker (sensible, fuera de git). |
| `MAE_API_KEY` | — | Opcional: pollers SIOPEL/MAE (dólar oficial, tasas OTC). |
| `CAFCI_TOKEN` | — | Opcional: VCP de fondos propios. |
| `APP_SMTP_*` | — | SMTP para reset de contraseña y mails operativos (watchdog del feed, resumen de cierre). |
| `APP_BASE_URL` | — | URL con la que los usuarios entran (ej. `http://server:8000`); se usa en links de mails y allowlist del manifest. |
| `HISTORICO_AUTOSAVE` | `1` | Autoguardado del histórico px/tasas a las 17:01 BA. **Debe estar prendido en UNA sola instancia** — si el server lo hace, apagarlo (`0`) en las máquinas de desarrollo. |
| `TLS_BRIDGE` / `TLS_PORT` / `TLS_BRIDGE_HOST` | `1` / `8443` / `127.0.0.1` | Puente HTTPS del add-in. En server: `TLS_BRIDGE_HOST=0.0.0.0`. |
| `BCRA_BACKUP_PATH` | `<repo>/bcra_data_backup.json` | Backup de series macro del BCRA. |

## 6. Servicio y auto-restart

**Windows (recomendado): NSSM** — `deploy/install_service_windows.ps1` deja:

- Arranque automático al boot + **auto-restart** si el proceso muere
  (3 s de espera; si vive < 5 s se considera arranque fallido y NSSM aplica
  backoff — no hay loop caliente).
- **Parada prolija**: Ctrl+C con hasta 15 s de gracia — la app guarda el
  snapshot de mercado y cierra el puente TLS antes de morir (todos los stops
  internos están acotados; el shutdown no puede colgarse).
- Logs en `<repo>\logs\service.log` con rotación a 10 MB.

Comandos del día a día: `nssm start|stop|restart|status YieldVertex` ·
editar la config: `nssm edit YieldVertex`.

**Linux**: `deploy/yieldvertex.service` (systemd, `Restart=always`,
`KillSignal=SIGINT` para la misma parada prolija).

**Además del restart de proceso**, la app trae watchdog propio del feed: si el
WebSocket del broker se corta > 5 min en horario de rueda, manda mail
(`FEED_WATCHDOG`, `APP_OPS_MAIL_TO`) y se reconecta sola con backoff. Cualquier
usuario logueado puede forzar reconexión desde la pestaña **/conexion**.

## 7. Deploy de versiones y rollback

Todo cambio entra por PR a `main` (política del repo: nunca push directo).
Actualizar el server = **`deploy\deploy.ps1`**, que hace:

1. `git fetch` + verifica working tree limpio (aborta si alguien tocó archivos a mano).
2. `git merge --ff-only origin/main` (histórico lineal, sin sorpresas).
3. `pip install -r backend\requirements.txt` (por si cambiaron dependencias).
4. Renueva cert/CRL del add-in si está por vencer (idempotente).
5. `nssm restart` + espera `/healthz` hasta 45 s; si no responde, muestra el
   log y deja impreso el comando de **rollback**:
   `git reset --hard <sha-anterior> ; nssm restart YieldVertex`.

Ventana sugerida: fuera de rueda (antes de 10:30 o después de 17:05 BA — el
autosave del histórico corre 17:01). Un restart tarda ~10–20 s (carga de
especies + warmup) y no pierde datos: el snapshot de mercado se guarda al bajar
y se restaura al subir.

## 8. Add-in de Excel servido desde el server

Office exige HTTPS para las funciones `=OMS.*`; de eso se ocupa el puente TLS
(puerto 8443) con una CA local estilo mkcert. Para servirlo centralizado:

1. **Certs con el nombre del server en el SAN** (el tool une SANs, es idempotente):
   `python -m backend.tools.https_local --host <NOMBRE-DNS> --host <IP-LAN>`
2. `TLS_BRIDGE_HOST=0.0.0.0` en la config del servicio.
3. **Confiar la CA en cada PC cliente** (una vez por máquina, sin admin):
   descargar `http://<server>:8000/excel/ca.crt` y
   `certutil -addstore -user Root ca.crt` — o distribuirla por **GPO**
   (Trusted Root, ámbito usuario) si son muchas PCs.
4. Instalar el add-in desde `https://<server>:8443/excel/manifest.xml`
   (carpeta compartida de manifiestos o "cargar manifiesto" en Excel).
5. Cada usuario pega su **token** (lo genera el superuser en `/admin`) en el
   taskpane. El token se puede cortar al instante desde `/admin`.

Notas: la clave de la CA vive en `certs/` del server y **no sale de ahí**
(`/excel/ca.crt` sirve sólo el certificado público). `/excel/crl` es el punto
de distribución de revocación que los certs declaran — debe quedar accesible
por http 8000 (sin él, máquinas con política estricta cortan el handshake con
`CRYPT_E_NO_REVOCATION_CHECK`).

## 9. Monitoreo

- **`GET /healthz`** (público, sin login, ~1 ms):

  ```json
  {"status": "ok", "bonds_loaded": 512, "broker_authenticated": true,
   "feed_alive": true, "ws": {…}, "warmup": {…}}
  ```

  Alarmas sugeridas: `status != ok` o HTTP ≠ 200 (app caída) — crítico;
  `feed_alive: false` en horario de rueda (10:30–17:00 BA) — aviso (la app
  sigue sirviendo el último dato; el watchdog ya manda mail solo).
- El dot de la topbar (verde/gris) muestra lo mismo a los usuarios.
- Logs: `logs\service.log` (rotado). El proceso loggea a stdout/stderr.

## 10. Backups (qué y de dónde)

Diario, fuera de rueda. Todo es archivo — un robocopy/rsync alcanza:

| Qué | Path | Por qué |
|---|---|---|
| Usuarios, roles, tokens Excel | `auth_store.json` (raíz) | Sin esto, nadie entra. Chico y crítico. |
| **Auditoría del OMS** | `oms_audit.jsonl` (raíz) | Registro de órdenes cursadas. **Evidencia — retención larga.** |
| Preferencias y snapshot | `data/` (snapshot de mercado, prefs de escenario, alertas) | Estado operativo. |
| Credenciales | `.env` / `secrets.txt` | Restaurar el server sin re-tipear claves. Guardar cifrado. |
| CA y certs del add-in | `certs/` | Perder la CA = re-confiar en TODAS las PCs. |
| Históricos px/tasas | `Delta - historico_byma_px_tasas.xlsx` + `.parquet` (carpeta Delta que resuelve `deltapaths`) | Serie construida día a día; no se regenera sola. |
| Series macro BCRA | `bcra_data_backup.json` | Se re-descarga, pero el backup evita arrancar sin macro si BCRA está caído. |

## 11. Modelo de seguridad (resumen para IT)

- **Muro de login** con roles (superuser / premium / básico), pestañas por rol
  y **visibilidad de fondos por usuario** aplicada server-side.
- **Guard de arranque**: la app no levanta con `AUTH_ENABLED=0` en un host
  expuesto (imposible dejarla abierta por accidente).
- Anti-CSRF por Origin/Referer + `SameSite`, CSP, `X-Frame-Options: DENY`,
  sin CDNs externos (todo se sirve local).
- **OMS**: arranca en modo PAPER; `OMS_LIVE=1` exige además topes de nocional,
  banda de precio anti fat-finger y kill-switch de mesa (`/ordenes/kill`,
  superuser). Toda orden queda en `oms_audit.jsonl`.
- API del add-in por **token por usuario** (revocable al instante), no cookies.
- Recomendación de red: acceso por **VPN/Tailscale o LAN interna**. No publicar
  8000/8443 a internet. El login manda la clave al host elegido: la pestaña
  `/conexion` ya limita a los no-superuser a los brokers conocidos.

## 12. Problemas típicos

| Síntoma | Causa y solución |
|---|---|
| No arranca: `Config insegura: AUTH_ENABLED=0 … host expuesto` | Es el guard, intencional. Poner `AUTH_ENABLED=1` (o bindear a 127.0.0.1 si es una prueba local). |
| No arranca: puerto 8000/8443 en uso | Quedó un proceso viejo: `netstat -ano \| findstr :8000` → matar PID, o `nssm restart`. |
| Página carga pero precios congelados / dot gris | Feed del broker caído. `/healthz` → `feed_alive:false`. Se reconecta solo; forzar desde `/conexion`. Si persiste: credenciales `OMS_USER/PASS` o red saliente. |
| Excel: celdas `#N/D` con "iniciando el runtime…" | El runtime no llega al 8443: cert no confiado en esa PC (re-correr `certutil`), CRL inaccesible (`CRYPT_E_NO_REVOCATION_CHECK` → puerto 8000 alcanzable), o token inválido (regenerar en `/admin`). Diagnóstico en el taskpane. |
| `429 Too Many Requests` en scripts de históricos (bymaapi) | Rate-limit del REST de BYMA/Latin. Pedir cupo a IT de Latin o espaciar corridas; la app web NO usa ese REST (va por WebSocket). |
| Primer arranque lento (~10–20 s) | Normal: carga de especies + warmup del motor. `/healthz` responde cuando está listo. |
| Archivos `*-conflicto*` o corruptos | La carpeta está en OneDrive. Sacarla (sección 3). |
| El autosave de 17:01 pisó datos raros | Hay DOS instancias con `HISTORICO_AUTOSAVE=1` (server + una PC). Dejar una sola. |

## 13. Desarrollo vs producción

| | Desarrollo (PC del autor) | Producción (server) |
|---|---|---|
| Arranque | `run_backend (CORRER APP).bat` (estable; `… .bat dev` = auto-reload para desarrollar) | Servicio NSSM/systemd (sin reload) |
| Carpeta | OneDrive (tolerado) | **Fuera de OneDrive** |
| Cambios | Se editan en vivo | Sólo por `deploy.ps1` desde `main` |
| Autosave 17:01 | Apagar si el server está corriendo | Prendido |
