# Links de las fuentes en CNV (campos `Aviso Resultados` y `Suplemento Prospecto`)

El dict termina con dos campos para dejar la trazabilidad de la emisión:

```python
    "Aviso Resultados": "",      # URL del Aviso de Resultados en CNV/AIF
    "Suplemento Prospecto": ""   # URL del Suplemento de Prospecto en CNV/AIF
```

Para completarlos, conseguí los links en CNV a partir de la razón social con el script incluido:

```bash
python3 scripts/buscar_cnv.py "TARJETA NARANJA" --desde 2026-05-01
```

Salida (el más reciente por tipo; usá `--todos` o `--desde` para elegir la clase por fecha):

```
[SUPLEMENTO DE PROSPECTO] 15/05/2026
   https://aif2.cnv.gov.ar/presentations/publicview/d7bc6733-...
[AVISO DE RESULTADOS] 20/05/2026
   https://aif2.cnv.gov.ar/presentations/publicview/c01e14ef-...
```

Pegá esos links en `Suplemento Prospecto` y `Aviso Resultados` respectivamente. **Eso es todo lo que
hay que hacer con CNV**: dejar los dos links en el dict. No hay que descargar el PDF ni nada más.

## Cómo funciona

Replica el camino manual: buscador global de CNV -> ficha de la empresa (Régimen General) ->
presentaciones (Emisiones / Obligaciones Negociables). Internamente:
1. POST al buscador (`BuscadorGlobal/DataTableBuscadorGlobal`) con la razón social. Pide un token
   reCAPTCHA pero acepta el token vacío, así que la consulta funciona desde script.
2. Abre la ficha de la empresa y parsea la tabla de presentaciones (fecha, título, link al AIF),
   clasificando Suplemento / Aviso de Resultados / Prospecto, y devuelve el link `publicview`.

Notas:
- Si hay varias clases/series, devuelve el más reciente por tipo; con `--desde`/`--todos` elegís por
  fecha la presentación de la clase que estás cargando (el título suele traer "INSTRUMENTO: N").
- Necesita salida de red hacia `www.cnv.gov.ar` (server lento/inestable; el script reintenta). Si no
  hay red, dejá esos dos campos vacíos.
- Para **leer** las condiciones del bono se usan los PDFs (que adjunta el usuario); estos links son
  solo para dejar pegada la fuente en el dict.
