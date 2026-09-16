#!/usr/bin/env bash
# test-carga-predeployment.sh — corre las pruebas de carga (Locust) contra
# un servidor levantado localmente, para ejecutar a mano antes de un
# deploy. No está wireado en CI a propósito: necesita un LLM real accesible
# (DEEPINFRA_API_KEY) o corre en modo degradado, y no tiene sentido — ni es
# seguro — dispararlo automáticamente en cada push (ver tests/load/README.md).
#
# Uso:
#   DEEPINFRA_API_KEY=<tu-api-key> scripts/test-carga-predeployment.sh
#
# Variables opcionales:
#   USUARIOS=50 SPAWN_RATE=5 DURACION=5m scripts/test-carga-predeployment.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

USUARIOS="${USUARIOS:-50}"
SPAWN_RATE="${SPAWN_RATE:-5}"
DURACION="${DURACION:-5m}"
HOST="${HOST:-http://127.0.0.1:8000}"

if ! command -v locust >/dev/null 2>&1; then
    echo "locust no está instalado. Instala el extra 'load': pip install -e '.[load]'" >&2
    exit 1
fi

if [[ -z "${DEEPINFRA_API_KEY:-}" ]]; then
    echo "AVISO: DEEPINFRA_API_KEY no está configurada — el motor de IA" >&2
    echo "arrancará en modo degradado (fallback), lo cual NO representa" >&2
    echo "carga realista contra el LLM real." >&2
fi

echo "Iniciando servidor de prueba en $HOST ..."
SANTISIMA_DEBUG=true uvicorn la_santisima_conversacional.presentation.http_api:app \
    --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

# Sin esto, un locust fallido o un Ctrl-C deja el uvicorn de prueba huérfano
# corriendo en segundo plano.
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

echo "Esperando a que el servidor responda..."
for _ in $(seq 1 30); do
    if curl -sf "$HOST/metrics/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! curl -sf "$HOST/metrics/health" >/dev/null 2>&1; then
    echo "El servidor no respondió a tiempo en $HOST." >&2
    exit 1
fi

echo "Ejecutando pruebas de carga (usuarios=$USUARIOS, spawn-rate=$SPAWN_RATE, duración=$DURACION)..."
locust -f tests/load/locustfile.py \
    --host="$HOST" \
    --users="$USUARIOS" --spawn-rate="$SPAWN_RATE" \
    --run-time="$DURACION" --headless
