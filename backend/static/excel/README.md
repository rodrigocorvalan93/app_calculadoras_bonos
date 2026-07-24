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

Campos de `QUOTE`: `last · bid · ask · bid_size · ask_size · close · close_date ·
var · vol · nominal · trades · vwap · open · high · low · last_ts` (con alias
es-AR: `ultimo`, `compra`, `venta`, `cierre`, `volumen`…). Plazos: `24hs`
(default; `48hs` se mapea acá) y `CI`.

## Instalación (una vez por PC)

1. **Habilitar el usuario**: el superuser entra a `/admin` → tabla Usuarios →
   columna **Excel** → *Habilitar*. Copia el token y se lo pasa al usuario.
   (El mismo botón corta el acceso al instante; `⟳` rota el token.)
2. **Descargar el manifest**: `https://<host>/excel/manifest.xml` (ya sale con
   la URL del server puesta).
3. **Sideload en Excel**:
   - *Windows*: compartir una carpeta de red con el manifest → Archivo →
     Opciones → Centro de confianza → Catálogos de complementos de confianza →
     agregar la carpeta → reiniciar Excel → Insertar → Complementos →
     CARPETA COMPARTIDA → OMS Bonos.
   - *Excel web*: Insertar → Complementos → Cargar mi complemento → subir el XML.
   - *Mac*: copiar el XML a `~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/`.
4. En la cinta aparece **OMS Bonos** → abrir el panel → pegar el token →
   *Guardar y conectar*. El dot en verde = feed vivo.

## Requisitos y HTTPS

- Las funciones `=OMS.*` streaming requieren **Excel de Microsoft 365**
  (Windows ≥ 1904, Mac o Excel web). Para Excel perpetuo (2016/2019/2021) usar
  el **modo hoja CRUDA** del panel: escribe todo en la hoja `OMS_DATA` una vez
  por tick y el libro sigue con `VLOOKUP` (keys `GD30|24hs`, `FX|MEP`,
  `FUT|DLR/AGO26M`, `CAU|ARS|7D`, `MAE|GD30`).
- Office exige **HTTPS en TODAS las URLs del manifest** — también en localhost.
  Un manifest bajado por `http://` es rechazado con "el manifiesto no es válido"
  (Excel web lo corta en el upload; el desktop tampoco lo carga).
  - Server local (Windows): certificado con [mkcert](https://github.com/FiloSottile/mkcert)
    — una vez: `mkcert -install` y `mkcert localhost 127.0.0.1`; después correr

        uvicorn backend.main:app --port 8443 --ssl-certfile localhost+1.pem --ssl-keyfile localhost+1-key.pem

    y bajar el manifest de `https://localhost:8443/excel/manifest.xml` (las URLs
    salen con el esquema/host desde donde se lo descarga).
  - Server en la red: con Tailscale, `tailscale cert` emite un certificado
    válido `*.ts.net`; si no, un cert interno (mkcert) confiado en cada PC.
  - Setear `APP_BASE_URL=https://…` para fijar la URL del manifest sin depender
    del host del request.
- `office.js` se carga del CDN de Microsoft (obligatorio para add-ins): las PCs
  necesitan salida a `appsforoffice.microsoft.com`.

## Cómo funciona (y por qué no carga al server)

El add-in mantiene **una** conexión por libro: sondea `/excel/v1/seq` (entero
plano, ~µs) cada 1 s y sólo si la secuencia avanzó baja `/excel/v1/snapshot`.
El server construye ese snapshot **una vez por segundo como máximo** y cachea
los bytes: N libros = 1 build + N lookups. Con la pestaña/planilla quieta o el
mercado cerrado no se transfiere nada más que el entero de la seq.
