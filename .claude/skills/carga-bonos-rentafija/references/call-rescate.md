# Régimen de rescate (call)

Este es el dato que más tiempo come y el más fácil de equivocar. Leelo despacio y, si queda alguna
duda, dejalo conservador (sin call) y marcalo en las notas. **Nunca inventes un call.**

## Dónde buscar en el suplemento

Secciones tituladas, entre otras: "Rescate", "Rescate Anticipado", "Rescate a Opción de la
Emisora", "Rescate a Opción de la Sociedad", "Opción de Rescate", "Rescate por Razones
Impositivas", "Redemption", "Optional Redemption". Ojo: el **rescate por razones impositivas**
(tax call) es estándar en casi todas las ON y normalmente **no** se carga como call operativo — el
call que importa es el **rescate a opción del emisor** a precios y fechas determinadas.

## Los cuatro campos

- `Callable` — `True` si hay rescate a opción del emisor; `False` si no (o si solo hay tax call).
- `Tipo de Call` — texto corto que describe el régimen (p. ej.
  `"Call total o parcial a opción de la sociedad a partir del mes 6 de emitido"`).
- `Fecha Call` — la **primera** fecha en que el emisor puede ejercer, en `"dd/mm/aaaa"`. Si el
  suplemento la expresa como "a partir del mes N desde la emisión", calculala sumando N meses a la
  fecha de emisión.
- `Precio Call` — el precio de rescate. Tres formas:
  - Si es un único precio: el flotante (p. ej. `1.02` para 102%).
  - Si hay tramos por período, un dict que los describa, replicando el estilo del archivo:
    ```python
    "Precio Call": {"m42 al 48": 1.02, "m48 en adelante": 1.01}
    ```
  - Si el rescate es a la par / valor técnico, `1.` (o el valor que indique).

Conviene además pegar el texto literal del régimen en `"Comentarios"`, como hacés con LUC3O, para
tener la trazabilidad.

## Ejemplo de mapeo

Texto del suplemento (resumido): *"Desde el mes 42 inclusive desde la emisión la Sociedad podrá
rescatar las ON en su totalidad; entre el mes 42 y el 48 al 102%, y a partir del mes 48 al 101%."*
Emisión 05/05/2022.

```python
"Callable": True,
"Tipo de Call": "Call total a opción de la sociedad a partir del mes 42 de emitido",
"Fecha Call": "05/11/2025",                       # 05/05/2022 + 42 meses
"Precio Call": {"m42 al 48": 1.02, "m48 en adelante": 1.01},
```

## Si no hay call

```python
"Callable": False,
"Tipo de Call": None,
"Fecha Call": None,
"Precio Call": None,
```

## Cuando queda ambiguo

Si la sección de rescate existe pero no podés determinar fecha o precio con certeza (texto recortado,
condiciones cruzadas, remite a un anexo que no está), cargá `Callable: False` provisorio y poné en
las **Notas de carga**, bien arriba, algo como: "⚠️ El suplemento menciona rescate anticipado en la
sección X pero no pude confirmar fecha/precio — revisar antes de operar." Es preferible una falta
visible a un call inventado.
