# Ejemplos resueltos por tipo

Ejemplos reales de `especies.py`. Usalos como molde del formato y de cómo se acoplan los campos
según el tipo. No los copies literal: cada bono nuevo trae sus propios datos.

## Dollar Linked (A3500) con call por tramos — LUC3O

ON corporativa, ajuste de capital por A3500 (lag −3), trimestral, con rescate a opción de la
sociedad por tramos. **No** lleva pata "j".

```python
LUC3O = {
    "Nombre Security": "ON Luz de Tres Picos S.A. Clase 3 Vto 05 05 2032",
    "Código": "LUC3O",
    "ISIN": "ARLUZT560039",
    "Calificación": "AA(arg)",
    "País": "Argentina",
    "Clasificación": "Corporativo Dolar Linked",
    "Industria": "Energy",
    "Moneda": "ARS",
    "Plazo habitual de liquidación: t +": 1.,
    "Emisión": "05/05/2022",
    "Vencimiento": "05/05/2032",
    "Fecha Primer Cupón": "05/08/2022",
    "Cupón / Spread": 5.05,
    "Step-up": False,
    "Frecuencia de pago de cupón anual": 4.,
    "Convención fechas de pago": "Regular",
    "Convención de devengamiento": "Actual",
    "Convención Base": 365.,
    "Tipo de Amortización": "BULLET",
    "Tipo Tasa Interés": "FIJA",
    "Index": None,
    "Días Lag índice desde inc": 0,
    "Días Lag índice hasta inc": 0,
    "Valor Nominal": 100.,
    "Ajuste sobre Capital": "A3500",
    "Factor Capitalización": 1.,
    "Días lag Ajuste base": -3,
    "Días lag Ajuste": -3,
    "Fechas de cupón": ["05/08/2022", "05/11/2022", "05/02/2023", "05/05/2023"],  # ... hasta vto
    "Amortización": None,
    "Callable": True,
    "Tipo de Call": "Call total o parcial a opción de la sociedad a partir del m6 de emitido",
    "Fecha Call": "05/11/2025",
    "Precio Call": {"m42 al 48": 1.02, "m48 en adelante": 1.01},
    "Comentarios": "Desde el mes 42 ... 102%; luego del mes 48 ... 101%"
}
```

## TAMAR (tasa variable) — LNS3P

`VARIABLE` + `Index: "TAMAR"`, el lag va en el índice (−7), spread = margen de corte. Amortizable.
No lleva pata "j".

```python
LNS3P = {
    "Nombre Security": "ON Pyme CNV Garantizada Liliana S.R.L. Serie III Vto 30 04 2027",
    "Código": "LNS3P",
    "Clasificación": "Corporativo TAMAR",
    "Industria": "Consumer Discretionary",
    "Moneda": "ARS",
    "Emisión": "30/04/2025",
    "Vencimiento": "30/04/2027",
    "Cupón / Spread": 5.99,              # margen de corte del aviso
    "Frecuencia de pago de cupón anual": 4.,
    "Convención de devengamiento": "Actual",
    "Convención Base": 365.,
    "Tipo de Amortización": "AMORTIZABLE",
    "Tipo Tasa Interés": "VARIABLE",
    "Index": "TAMAR",
    "Días Lag índice desde inc": -7,
    "Días Lag índice hasta inc": -7,
    "Ajuste sobre Capital": None,
    "Días lag Ajuste base": None,
    "Días lag Ajuste": None,
    "Fechas de cupón": ["30/07/2025", "30/10/2025", "30/01/2026", "30/04/2026",
                        "30/07/2026", "30/10/2026", "30/01/2027", "30/04/2027"],
    "Amortización": ([0] * 5 + [33] * 2 + [34]),
    "Callable": False, "Tipo de Call": None, "Fecha Call": None, "Precio Call": 1,
}
```
(Campos comunes omitidos por brevedad — completalos como en la plantilla.)

## BADLAR — TYCZO

Igual que TAMAR pero `Index: "BADLAR"`. Variable, amortizable, lag índice −7.

```python
TYCZO = {
    "Clasificación": "Corporativo BADLAR",
    "Industria": "Financials",
    "Tipo Tasa Interés": "VARIABLE",
    "Index": "BADLAR",
    "Días Lag índice desde inc": -7,
    "Días Lag índice hasta inc": -7,
    "Cupón / Spread": 5.99,
    "Convención de devengamiento": "Actual",
    "Convención Base": 365.,
    "Tipo de Amortización": "AMORTIZABLE",
    "Amortización": ([0] * 3 + [33.33] * 2 + [33.34]),
    "Callable": False,
}
```

## CER con pata proyectada — TX26 + TX26j

Soberano CER, amortizable, ISMA-30 / 360, lag ajuste −10. Se cargan **los dos** dicts. Notá las tres
únicas diferencias en `TX26j`: nombre con `j`, `Industria` con `" Proyectado"`, y
`Ajuste sobre Capital: "CER PROYECTADO"`.

```python
TX26 = {
    "Nombre Security": "BONCER 2026",
    "Código": "TX26",
    "Clasificación": "Soberano",
    "Industria": "Soberano Inflación",
    "Moneda": "ARS",
    "Cupón / Spread": 2.,
    "Frecuencia de pago de cupón anual": 2.,
    "Convención de devengamiento": "ISMA-30",
    "Convención Base": 360.,
    "Tipo de Amortización": "AMORTIZABLE",
    "Tipo Tasa Interés": "FIJA",
    "Index": None,
    "Ajuste sobre Capital": "CER",
    "Días lag Ajuste base": -10,
    "Días lag Ajuste": -10,
    "Amortización": [0, 0, 0, 0, 0, 0, 0, 20., 20., 20., 20., 20.],
    "Callable": False,
}

TX26j = {
    # idéntico a TX26 salvo:
    "Industria": "Soberano Inflación Proyectado",
    "Ajuste sobre Capital": "CER PROYECTADO",
}
```

## UVA con pata proyectada — TLCJO + TLCJOj

Corporativo UVA, bullet, Actual / 365, lag ajuste −5. Lleva pata "j" (`"UVA PROYECTADO"`).

```python
TLCJO = {
    "Nombre Security": "ON Telecom Argentina S.A. Clase 18 Vto 17 11 2027",
    "Código": "TLCJO",
    "Clasificación": "Corporativo UVA",
    "Industria": "Communications",
    "Cupón / Spread": 1.,
    "Frecuencia de pago de cupón anual": 4.,
    "Convención de devengamiento": "Actual",
    "Convención Base": 365.,
    "Tipo de Amortización": "BULLET",
    "Tipo Tasa Interés": "FIJA",
    "Ajuste sobre Capital": "UVA",
    "Días lag Ajuste base": -5,
    "Días lag Ajuste": -5,
    "Callable": False,
}
# TLCJOj: idéntico salvo Industria "Communications Proyectado" y Ajuste "UVA PROYECTADO"
```

## Step-up + personalizado — PARP

Cupón en lista (`Step-up: True`) y cronograma irregular (`"Personalizado"`).

```python
PARP = {
    "Cupón / Spread": [1.77, 2.48],
    "Step-up": True,
    "Convención fechas de pago": "Personalizado",
    "Tipo de Amortización": "AMORTIZABLE",
}
```

## Dual soberano CER/TAMAR — TXMJ9 + TXMJ9j + TXMJ9v (TRES fichas)

El dual paga el máximo de las patas; el motor lo modela con tres fichas. La base es CER/FIJA; la
pata `v` es la TAMAR (`VARIABLE_CAP`, capitaliza c/32d, margen del aviso en `Cupón / Spread`).

```python
TXMJ9 = {
    "Nombre Security": "Bono de la Nacion Argentina Dual CER TAMAR 2029 Vto 29 06 2029",
    "Clasificación": "Soberano",
    "Industria": "Soberano ARS Dual CER/Tamar",
    "Moneda": "ARS",
    "Tipo Tasa Interés": "FIJA",
    "Index": None,
    "Ajuste sobre Capital": "CER",
    "Días lag Ajuste base": -10, "Días lag Ajuste": -10,
    "Convención de devengamiento": "ISMA-30", "Convención Base": 360.,
    "Tipo de Amortización": "BULLET",
    "Fechas de cupón": ["29/06/2029"],
}
# TXMJ9j: idéntico salvo Industria "Soberano ARS Dual CER/Tamar Proyectado"
#         y Ajuste "CER PROYECTADO".
# TXMJ9v: Industria "Soberano ARS Dual Tamar/CER", Tipo Tasa "VARIABLE_CAP",
#         Index "TAMAR", Ajuste None, y el MARGEN del aviso (p. ej. +3,00%)
#         en "Cupón / Spread". Espejá TTS26v/TXMD9v para los lags.
```

Las 3 fichas van a `todos_los_bonos` y a la sección de conversiones. Verificá con
`compare.py TXMJ9_nuevo TXMJ9` que el set quede completo.
