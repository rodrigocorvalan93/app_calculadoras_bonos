# Add-in de Excel «OMS Bonos» (reemplazo del feed Reuters)

Funciones en tiempo real dentro de Excel alimentadas por esta app (mismo feed
Primary/BYMA + MAE que la web). Sin licencias: el server arma un snapshot por
tick y todos los libros conectados comparten ese único build.

## Fórmulas

| Fórmula | Equivalente Reuters |
|---|---|
| `=OMS.QUOTE("GD30";"bid")` | `RtGet("IDN";"ARGD30 3=ME";"BID")` |
| `=OMS.QUOTE("S31L6";"last";"CI")` | `RtGet("IDN";"ARS31L6=BA";"PRIMACT_1")` |
| `=OMS.QUOTE("GD30";"close")` | `…"HST_CLOSE"` (cierre anterior) |
| `=OMS.QUOTE("GD30";"vol";;"mae")` | cinta MAE (volumen OTC) |
| `=OMS.FX("mep")` / `("ccl")` / `("mayorista")` / `("a3500")` | `TR("ARS=BCRA";…)` etc. |
| `=OMS.ROFEX(1;"tna")` / `=OMS.ROFEX("DLR/AGO26M";"last")` | `TR("ARSc1";…)` |
| `=OMS.CAUCION(7;"tasa")` | `RtGet("IDN";"ARS…RP=BA";…)` |
| `=OMS.TABLA("futuros")` (spill) | hoja Rofex completa |
| `=OMS.HIST("a3500";365)` (spill) | `RHistory("ARS=BCRA";…)` |
| `=OMS.TIREA("GD30";78,5)` / `=OMS.PRECIO("GD30";0,14)` / `=OMS.TNA(…)` | calculadora YAS en la celda |
| `=OMS.TICKET("GD30";78,5;1000000)` (spill) / `=OMS.CALC(…;"duration";…)` | ticket + cualquier métrica YAS |

Campos de `QUOTE`: `last · bid · ask · bid_size · ask_size · close · close_date ·
var · vol · nominal · trades · vwap · open · high · low · last_ts` (con alias
es-AR: `ultimo`, `compra`, `venta`, `cierre`, `volumen`…). Plazos: `24hs`
(default; `48hs` se mapea acá) y `CI`.

**Referencia completa de todas las funciones, campos, alias y unidades:
[FORMULAS.md](FORMULAS.md).**

## Instalación (una vez por PC)

1. **Habilitar el usuario**: el superuser entra a `/admin` → tabla Usuarios →
   columna **Excel** → *Habilitar*. Copia el token y se lo pasa al usuario.
   (El mismo botón corta el acceso al instante; `⟳` rota el token.)
2. **Descargar el manifest** de la base **https** del puente TLS:
   `https://localhost:8443/excel/manifest.xml` — o mejor, el botón
   **⬇ con token** de la tarjeta de `/admin` (ya sale con la URL y el token
   del usuario puestos). Un manifest bajado por `http://` instala un add-in
   donde el panel anda pero las celdas no (ver «HTTPS» abajo).
3. **Sideload en Excel**:
   - *Windows*: compartir una carpeta de red con el manifest → Archivo →
     Opciones → Centro de confianza → Catálogos de complementos de confianza →
     agregar la carpeta → reiniciar Excel → Insertar → Complementos →
     CARPETA COMPARTIDA → OMS Bonos.
   - *Excel web*: Insertar → Complementos → Cargar mi complemento → subir el XML.
   - *Mac*: copiar el XML a `~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/`.
4. En la cinta aparece **OMS Bonos** → abrir el panel → pegar el token →
   *Guardar y conectar*. El dot en verde = feed vivo.

## Requisitos y HTTPS (la causa del "iniciando el runtime…" eterno)

- Las funciones `=OMS.*` streaming requieren **Excel de Microsoft 365**
  (Windows ≥ 1904, Mac o Excel web). Para Excel perpetuo (2016/2019/2021) usar
  el **modo hoja CRUDA** del panel: escribe todo en la hoja `OMS_DATA` una vez
  por tick y el libro sigue con `VLOOKUP` (keys `GD30|24hs`, `FX|MEP`,
  `FUT|DLR/AGO26M`, `CAU|ARS|7D`, `MAE|GD30`).
- **Office exige HTTPS para el runtime de las funciones custom.** Con un
  manifest `http://localhost:…` el add-in CARGA y engaña: el taskpane anda
  (conecta, Probar da OK — a los webviews visibles Office les tolera http en
  localhost), pero el runtime headless de las celdas NO ARRANCA: Excel queda
  con "Se está iniciando el runtime de los complementos…" en la barra de
  estado, re-baja `functions.html/js/json` en loop y toda celda `=OMS.*` da
  `#N/D`, sin ningún error que diga por qué.
- **El HTTPS local ya viene resuelto** — no hay que instalar nada:
  1. el `.bat` corre `python -m backend.tools.https_local` en cada arranque:
     genera una CA local + certificado para `localhost`/`127.0.0.1`/IP LAN en
     `certs/` (gitignored) y confía la CA en el usuario de Windows
     (`certutil -user`, sin admin). Idempotente: con el cert vigente no hace
     nada. La CA se REUSA entre regeneraciones (la confianza instalada no se
     invalida) y el certificado lleva un **punto de distribución de CRL**
     (`http://127.0.0.1:8000/excel/crl`, servida por la app) — ver el punto
     de revocación abajo;
  2. con los certs presentes, la app levanta sola el **puente TLS**
     (`backend/services/tls_bridge.py`): `https://localhost:8443` → proxy al
     uvicorn http local. `TLS_BRIDGE=0` lo apaga; puerto con `TLS_PORT`;
  3. el manifest se baja de `https://localhost:8443/excel/manifest.xml` (la
     tarjeta de `/admin` ya apunta ahí cuando el puente está activo).
- **CA confiada pero las celdas dan `Network request failed`** (DIAG muestra
  `REJECT: Network request failed`, y en el log del server no aparece NI el
  beacon): revocación. En máquinas con política estricta (GPO/EDR
  corporativo), schannel exige poder **verificar la revocación** del cert y
  corta el handshake con `CRYPT_E_NO_REVOCATION_CHECK` si el cert no trae
  CRL — los archivos estáticos cargan igual (el loader de Office es más
  laxo), lo que despista. Los certs nuevos ya traen el punto CRL; uno viejo
  se regenera solo al correr `python -m backend.tools.https_local` (misma
  CA: no hay que re-confiar nada). Verificación definitiva, porque el
  `curl.exe` de Windows usa schannel y exige revocación SIEMPRE:

      curl.exe -v https://localhost:8443/excel/ca.crt -o NUL

  Si curl conecta limpio, Office conecta. Ojo: el CDP queda horneado en el
  cert apuntando al puerto 8000 — si uvicorn corre en otro puerto, regenerar
  con `--crl-port`. Después de regenerar: reiniciar la app y cerrar Excel
  por completo.
- **Otra compu de la mesa contra un server central**: correr el puente
  escuchando afuera (`TLS_BRIDGE_HOST=0.0.0.0`), bajar la CA pública de
  `https://<server>:8443/excel/ca.crt` en cada PC y confiarla:
  `certutil -user -addstore -f Root oms-local-ca.crt`. Con Tailscale,
  `tailscale cert` emite un certificado válido `*.ts.net` (sin CA propia).
- Setear `APP_BASE_URL=https://…` para fijar la URL del manifest sin depender
  del host del request.
- `office.js` se carga del CDN de Microsoft (obligatorio para add-ins): las PCs
  necesitan salida a `appsforoffice.microsoft.com`.

## Diagnóstico: el runtime le reporta al log del server

El runtime de funciones es headless (no hay consola a mano en el Excel de
Windows), así que `functions.html`/`functions.js` reportan su ciclo de vida a
`GET /excel/v1/beacon` (público, sólo escribe una línea sanitizada). Con el
add-in sano, el log del server (`[backend.excel.addin]`) muestra en orden:

    page-cargada → office-ready → funciones-registradas → feed-live → celda-ok

Dónde se corta la cadena dice qué falló:

| Último estado | Significa |
|---|---|
| *(nada)* | El runtime ni ejecutó JS: manifest http (ver arriba), o Excel sin runtime de funciones. |
| *(nada)* pero `=OMS.PING()` responde y DIAG da `REJECT: Network request failed` | El JS corre pero NINGÚN fetch sale (ni el beacon): TLS bloqueado en el cliente — casi siempre revocación (`CRYPT_E_NO_REVOCATION_CHECK`, ver arriba); verificar con `curl.exe`. |
| `page-cargada` + `sin-customfunctions` | `office.js` no cargó (sin salida al CDN) o el runtime no soporta funciones. |
| `office-ready` sin `funciones-registradas` | `associate()` no corrió — mirar `js-error`. |
| `funciones-registradas` + `feed-auth` | Token ausente/roto: instalar el manifest "⬇ con token" desde `/admin`. |
| `funciones-registradas` + `feed-error` | El runtime no llega al server (red/cert) — el detalle viene en la línea. |
| `celda-timeout` | Una celda esperó 6 s sin datos; el detalle trae función, especie y estado del feed. |
| `js-error` | Excepción JS en el runtime, con archivo y línea. |

## Cómo funciona (y por qué no carga al server)

El add-in mantiene **una** conexión por libro: sondea `/excel/v1/seq` (entero
plano, ~µs) cada 1 s y sólo si la secuencia avanzó baja `/excel/v1/snapshot`.
El server construye ese snapshot **una vez por segundo como máximo** y cachea
los bytes: N libros = 1 build + N lookups. Con la pestaña/planilla quieta o el
mercado cerrado no se transfiere nada más que el entero de la seq.
