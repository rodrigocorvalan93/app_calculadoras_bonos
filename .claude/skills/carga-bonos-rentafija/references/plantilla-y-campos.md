# Plantilla del dict y campos uno por uno

Esta es la estructura completa con el formato exacto que espera la calculadora. Respetá comillas
dobles en las claves, los comentarios `#`, las fechas `"dd/mm/aaaa"` y los flotantes con punto
(`100.`, `1.`, `5.05`).

```python
CODIGO = {
    "Nombre Security": "...",        # nombre del instrumento; SIEMPRE termina en "Vto dd mm yyyy"
    "Código": "...",                 # ticker / código de la especie
    "ISIN": "...",                   # del aviso de resultados o suplemento
    "Calificación": "...",           # rating (del aviso o del informe de calificadora); None si no hay
    "País": "Argentina",
    "Clasificación": "...",          # ver tipos-y-convenciones.md
    "Industria": "...",              # libre, inferida del emisor
    "Moneda": "ARS",                 # ARS o USD según el bono
    "Plazo habitual de liquidación: t +": 1.,   # entero (casi siempre 1)
    "Emisión": "dd/mm/aaaa",         # fecha de emisión/liquidación — del AVISO
    "Vencimiento": "dd/mm/aaaa",     # del suplemento/aviso
    "Fecha Primer Cupón": "dd/mm/aaaa",  # primer corte; None si se infiere del cronograma
    "Cupón / Spread": 0.,            # FIJA: cupón. VARIABLE: spread/margen de corte (del AVISO). Step-up: lista
    "Step-up": False,                # True solo si el cupón cambia en el tiempo (entonces Cupón/Spread es lista)
    "Frecuencia de pago de cupón anual": 4.,  # semestral=2, trimestral=4, mensual=12
    "Convención fechas de pago": "Regular",   # "Regular" o "Personalizado" (si el cronograma es irregular)
    "Convención de devengamiento": "Actual",  # "Actual", "ISMA-30", "NASD-30"
    "Convención Base": 365.,         # 365. o 360.
    "Tipo de Amortización": "BULLET",         # "BULLET" o "AMORTIZABLE"
    "Tipo Tasa Interés": "FIJA",     # "FIJA" o "VARIABLE"
    "Index": None,                   # "TAMAR", "BADLAR" o None
    "Días Lag índice desde inc": 0,  # negativo si es VARIABLE; 0 si no
    "Días Lag índice hasta inc": 0,
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": None,    # None, "CER", "CER PROYECTADO", "UVA", "UVA PROYECTADO", "A3500", "A3500 PROYECTADO"
    "Factor Capitalización": 1.,
    "Días lag Ajuste base": None,    # negativo si ajusta capital; None si no
    "Días lag Ajuste": None,
    "Fechas de cupón": [             # cronograma del suplemento, en orden ascendente
        "dd/mm/aaaa",
        # ...
    ],
    "Amortización": None,            # None si BULLET; si no, lista alineada al cronograma que suma 100
    "Callable": False,               # ver call-rescate.md
    "Tipo de Call": None,
    "Fecha Call": None,
    "Precio Call": None,
    "Comentarios": "",               # opcional: texto del régimen de rescate u otras condiciones
    "Aviso Resultados": "",          # URL del Aviso de Resultados en CNV (buscar_cnv.py)
    "Suplemento Prospecto": ""       # URL del Suplemento de Prospecto en CNV (buscar_cnv.py)
}
```

## Nombre Security

El `Nombre Security` describe el instrumento (emisor + clase/serie) y **siempre termina con la
leyenda `Vto dd mm yyyy`**, donde la fecha es el **vencimiento** con espacios y sin barras. Ejemplos:
`ON Tarjeta Naranja S.A.U. Clase 67 Serie I Vto 22 05 2027`, `ON Luz de Tres Picos S.A. Clase 3 Vto
05 05 2032`.

## De qué documento sale cada cosa

**Del Aviso de Resultados** (lo que se fijó en la licitación):
- `Cupón / Spread` ← margen de corte (variable) o tasa de corte (fija). El suplemento suele dar un
  rango; el número final está acá.
- `Emisión` ← fecha de emisión y liquidación.
- `ISIN`, `Valor Nominal`, monto, a veces `Calificación`.

### ISIN: cuándo está y cómo resolverlo

El ISIN de la serie **nueva** muchas veces no figura en el aviso ni en el suplemento el día de la
emisión (los ISINs que aparecen suelen ser de las clases viejas que se canjean). Buscalo en el
listado del MAE con el script incluido, por código o por emisor (sale junto con el ticker):

```bash
python3 scripts/buscar_mae.py --codigo T671O T672O T673O
python3 scripts/buscar_mae.py --emisor "SCANIA"
```

Pasá el código **BYMA/MAE** (terminado en `O`: `T672D`→`T672O`; el script igual prueba la variante
con `O`). Si no sabés el código, buscá por `--emisor` y tomá la fila de la clase correspondiente. La
página del MAE es un GridView ASP.NET paginado sin buscador, así que un `web_fetch` simple no
alcanza; por eso el script pagina con postbacks (ViewState).

- Si lo encuentra, poné ese ISIN en el dict.
- Si el script avisa que **no hay red** hacia `servicios.mae.com.ar` (algunos contenedores no tienen
  salida a internet) o que el instrumento **todavía no está listado**, no lo inventes: dejá el
  `Código` como placeholder del campo `ISIN` y marcá "ISIN pendiente — completar al listar".

El mismo código con `O` es el que usa el flujo que baja precios de BYMA, así que sirve para ambas
cosas.

**Del Suplemento de Prospecto** (la estructura):
- `Fechas de cupón` ← cronograma de pago de servicios de interés.
- `Amortización` ← esquema de amortización (ver abajo).
- `Vencimiento`, `Frecuencia de pago de cupón anual`.
- `Convención de devengamiento`, `Convención Base` ← sección de cómputo de intereses.
- `Index` / `Ajuste sobre Capital` y los lags ← definición de la tasa y fechas de determinación.
- `Callable` y compañía ← sección de rescate (ver `call-rescate.md`).

### Calificación: FIX SCR y la regla corto/largo plazo

La calificación la asigna FIX SCR (afiliada de Fitch). Para una serie nueva, FIX la informa por aviso
complementario y suele tardar en aparecer por ISIN, así que se toma la **calificación del emisor**.
Usá el script incluido:

```bash
python3 scripts/buscar_calificacion.py "Naranja X" --plazo-meses 12
python3 scripts/buscar_calificacion.py --id 613 --plazo-meses 18 --isin AR0771688576
```

- **Regla (confirmada):** plazo del bono **≤ 12 meses → calificación de corto plazo** (p. ej.
  `A1+(arg)`); **> 12 meses → largo plazo** (p. ej. `AA(arg)`). El script aplica esto solo a partir
  de `--plazo-meses`.
- Si pasás `--isin` y ese ISIN ya figura en FIX, devuelve esa calificación exacta; si no, la del
  emisor según el plazo.
- **Resolución del emisor:** el script trae un mini-mapa de emisores frecuentes (Naranja X = 613). Si
  el emisor no está, resolvé su página con `web_search` ("fixscr <emisor>") y pasá la URL con `--url`
  (o el id con `--id`). El buscador del sitio es JavaScript y no se puede consultar por querystring.
- Siempre se carga **con `(arg)`** al final. Si no hay red o el script no encuentra al emisor, dejá
  `Calificación` en `None` y flagueá "calificación pendiente".

## Amortización

- **BULLET:** `Tipo de Amortización: "BULLET"` y `Amortización: None`. Paga todo el capital al
  vencimiento.
- **AMORTIZABLE:** `Tipo de Amortización: "AMORTIZABLE"` y `Amortización` es una lista de la misma
  longitud que `Fechas de cupón`, donde cada elemento es el % de capital que amortiza en esa fecha y
  el total suma 100. Las fechas sin amortización llevan `0`.

  Se puede escribir explícito o con la forma compacta que ya usás:
  ```python
  "Amortización": [0, 0, 0, 0, 0, 0, 0, 20., 20., 20., 20., 20.],   # explícito
  "Amortización": ([0] * 5 + [33] * 2 + [34]),                       # compacto (8 cuotas)
  ```
  En la forma compacta, la cantidad total de elementos tiene que igualar la cantidad de fechas de
  cupón.

## Step-up

Si el cupón cambia a lo largo de la vida del bono, `Step-up: True` y `Cupón / Spread` pasa a ser una
**lista** de cupones (p. ej. `[1.77, 2.48]`). Si la tasa es constante, `Step-up: False` y
`Cupón / Spread` es un único flotante.

## Moneda y dólar

- Hard Dollar / bonos en dólares → `Moneda: "USD"`.
- Dollar Linked (paga en pesos al tipo de cambio A3500) → `Moneda: "ARS"`, `Ajuste sobre Capital: "A3500"`.
- CER/UVA/TAMAR/BADLAR en pesos → `Moneda: "ARS"`.
