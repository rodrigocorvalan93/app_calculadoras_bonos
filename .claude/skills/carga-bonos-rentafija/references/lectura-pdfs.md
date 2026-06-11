# Lectura de los PDFs

Los PDFs llegan a `/mnt/user-data/uploads/`. Primero hacé un inventario rápido y después extraé el
texto.

## Texto nativo (lo más común)

```bash
pip install pdfplumber --break-system-packages -q
```

```python
import pdfplumber
with pdfplumber.open("/mnt/user-data/uploads/suplemento.pdf") as pdf:
    print("páginas:", len(pdf.pages))
    texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
```

Para localizar secciones puntuales (cronograma, rescate), buscá por palabras clave dentro de `texto`
en vez de leer todo a ciegas: "Rescate", "Amortización", "Cronograma", "Servicios de Interés",
"Cómputo de los Intereses", "Fecha de Emisión".

Las tablas (cronograma de pagos, esquema de amortización) salen mejor con:
```python
with pdfplumber.open(ruta) as pdf:
    for p in pdf.pages:
        for tabla in p.extract_tables():
            ...
```

## Si el PDF está escaneado (sin texto)

Si `extract_text()` devuelve vacío o basura, es un escaneo: rasterizá y pasá OCR.

```bash
pip install pdf2image pytesseract --break-system-packages -q
apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-spa  # OCR en español
```

```python
from pdf2image import convert_from_path
import pytesseract
imgs = convert_from_path(ruta, dpi=200)
texto = "\n".join(pytesseract.image_to_string(im, lang="spa") for im in imgs)
```

## Buenas prácticas

- Si una sección no se lee bien, decilo y no rellenes con suposiciones.
- Verificá fechas y números contra ambos documentos cuando aparezcan en los dos (p. ej. la fecha de
  emisión suele estar en el aviso y en el suplemento).
- El Aviso de Resultados suele ser corto (1–3 páginas) — leelo entero. El Suplemento es largo;
  navegá por palabras clave.

## Gotchas de entorno (vistos en producción)

- **pypdf** suele estar instalado pero puede fallar con `ModuleNotFoundError: _cffi_backend` →
  `pip install cffi` lo arregla. Alternativa sin pip: el harness de Claude puede leer PDFs
  directamente con la herramienta Read (parámetro `pages`, máx 20 por llamada) si poppler está
  disponible; si no, pypdf/pdfplumber.
- Los avisos del Tesoro (Secretaría de Finanzas) son texto nativo: `pypdf.PdfReader` +
  `page.extract_text()` alcanza. Ignorá los warnings "wrong pointing object".
- El cwd puede resetearse entre comandos en sesiones web: usá rutas absolutas o `cd` explícito al
  correr los scripts.
