#!/bin/zsh
# Acceso directo para macOS: doble click levanta la calculadora de bonos
# (FastAPI) y abre el navegador. Para pararla: Ctrl+C en esta ventana.
#
# Primera vez: crea el entorno .venv e instala dependencias (unos minutos).
# Después arranca directo. Credenciales: lee secrets.txt / .env del repo,
# igual que siempre (ver backend/README.md).
set -e
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

# Si ya hay una instancia corriendo, sólo abrir el navegador.
if curl -s -o /dev/null --max-time 1 "${URL}/healthz"; then
  echo "La app ya está corriendo en ${URL} — abriendo el navegador."
  open "${URL}"
  exit 0
fi

if [ ! -x .venv/bin/uvicorn ]; then
  echo "▶ Primera vez: creando .venv e instalando dependencias…"
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip setuptools wheel
  # openpyxl: los Excel de Posiciones/Delta · feedparser: cinta de noticias
  .venv/bin/pip install -r backend/requirements.txt openpyxl feedparser
fi

# Abrir el navegador apenas el server responda (hasta ~30 s).
(
  for _ in {1..60}; do
    sleep 0.5
    if curl -s -o /dev/null --max-time 1 "${URL}/healthz"; then
      open "${URL}"
      exit 0
    fi
  done
) &

echo "▶ Levantando la calculadora en ${URL}  (Ctrl+C para pararla)"
exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port "${PORT}"
