#!/bin/zsh
# ============================================================
#  Corre el backend FastAPI (backend.main:app) en macOS.
#  Espejo del "run_backend (CORRER APP).bat" de Windows:
#    1) busca Python 3.11+ (python3 del PATH, Homebrew o python.org);
#    2) crea/usa un venv POR MAQUINA en ~/.venvs/bonos
#       (FUERA de OneDrive: un venv adentro de la carpeta sincronizada
#       se corrompe y ensucia el sync de todo el equipo);
#    3) instala/actualiza dependencias solo si requirements.txt cambio.
#  Navegador: http://127.0.0.1:8000  (se abre solo cuando levanta)
#  Modo DEV (auto-reload al editar .py):   ./correr_app.command dev
#  Si el doble click no abre (Gatekeeper/permisos):
#    boton derecho -> Abrir, o en Terminal:  zsh "correr_app.command"
# ============================================================
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
# Host de escucha: 127.0.0.1 (solo esta Mac) por default. Para entrar desde
# el celular via Tailscale, agregar en secrets.txt:  APP_HOST=0.0.0.0
if [ -z "${HOST:-}" ] && [ -f secrets.txt ]; then
  HOST="$(grep -E '^APP_HOST=' secrets.txt | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
fi
HOST="${HOST:-127.0.0.1}"
URL="http://127.0.0.1:${PORT}"

# Si ya hay una instancia corriendo, solo abrir el navegador.
if curl -s -o /dev/null --max-time 1 "${URL}/healthz"; then
  echo "La app ya esta corriendo en ${URL} — abriendo el navegador."
  open "${URL}"
  exit 0
fi

# --- 1) Python base: 3.11+ (python3 del PATH, Homebrew o python.org) ---
# Nota: en una Mac sin Python, "python3" es un stub de Apple que abre un
# dialogo de instalacion de las Command Line Tools — por eso se verifica
# que el candidato REALMENTE corra y sea 3.11+.
PYBASE=""
for cand in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && \
     "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PYBASE="$cand"
    break
  fi
done
if [ -z "$PYBASE" ]; then
  echo "[ERROR] No hay Python 3.11+ en esta Mac."
  echo
  echo "Instalarlo con UNA de estas opciones y volver a correr este archivo:"
  echo "  a) brew install python                    (si usas Homebrew)"
  echo "  b) https://www.python.org/downloads/      (instalador oficial macOS)"
  echo
  read -r -s -k 1 "?Presiona una tecla para cerrar..." || true
  exit 1
fi

# --- 2) venv por maquina, FUERA de OneDrive ---
VENVDIR="$HOME/.venvs/bonos"
PY="$VENVDIR/bin/python"
if [ ! -x "$PY" ]; then
  echo "Primera vez en esta Mac: creando entorno en $VENVDIR ..."
  "$PYBASE" -m venv "$VENVDIR" || {
    echo "[ERROR] No se pudo crear el entorno virtual."
    read -r -s -k 1 "?Presiona una tecla para cerrar..." || true
    exit 1
  }
fi
if [ -d .venv ]; then
  echo "(hay un .venv viejo ADENTRO del repo/OneDrive: ya no se usa;"
  echo " conviene borrarlo con:  rm -rf .venv )"
fi

# --- 3) dependencias: instalar solo si backend/requirements.txt cambio ---
if ! cmp -s backend/requirements.txt "$VENVDIR/requirements.instalado"; then
  echo "Instalando/actualizando dependencias (1-3 min la primera vez)..."
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1
  "$PY" -m pip install -r backend/requirements.txt || {
    echo "[ERROR] La instalacion de dependencias fallo. Revisar la salida de pip."
    read -r -s -k 1 "?Presiona una tecla para cerrar..." || true
    exit 1
  }
  cp backend/requirements.txt "$VENVDIR/requirements.instalado"
fi
echo "Usando Python: $("$PY" --version)"
echo
# (el puente HTTPS del add-in de Excel es de Windows — aca no se genera nada)

# --- Modo de ejecucion: ESTABLE por default; "dev" -> auto-reload ---
# Con la carpeta compartida por OneDrive, cada git pull del equipo hace
# llegar archivos de a uno y el auto-reload reiniciaba la app una y otra
# vez, en plena rueda. Igual que el .bat: estable salvo pedido explicito.
RELOAD=""
case "${1:-}" in
  dev|DEV|reload|RELOAD) RELOAD="--reload";;
esac
if [ -n "$RELOAD" ]; then
  echo "Iniciando FastAPI en ${URL} ... [modo DEV: auto-reload al tocar un .py]"
else
  echo "Iniciando FastAPI en ${URL} ... [estable: sin auto-reload]"
  echo "  - un git pull / sync de OneDrive ya NO reinicia la app sola"
  echo "  - tras actualizar el codigo o especies.py: Ctrl+C y volver a abrir"
  echo "  - para desarrollar con auto-reload:  ./correr_app.command dev"
fi
echo "(Ctrl+C para detener)"
echo

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

exec "$PY" -m uvicorn backend.main:app --host "${HOST}" --port "${PORT}" ${RELOAD:+--reload} --timeout-graceful-shutdown 10
