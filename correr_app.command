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
# Host de escucha: 127.0.0.1 (sólo esta Mac) por default. Para entrar desde
# el celular vía Tailscale (ver README § "Desde el celular"), agregá en
# secrets.txt la línea:  APP_HOST=0.0.0.0
if [ -z "${HOST:-}" ] && [ -f secrets.txt ]; then
  HOST="$(grep -E '^APP_HOST=' secrets.txt | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
fi
HOST="${HOST:-127.0.0.1}"
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
  .venv/bin/pip install -r backend/requirements.txt
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

echo "▶ Levantando la calculadora en ${URL}  (host ${HOST} · Ctrl+C para pararla)"
exec .venv/bin/uvicorn backend.main:app --host "${HOST}" --port "${PORT}"
