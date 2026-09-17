#!/usr/bin/env bash
# Punto de entrada único para levantar el backend en local.
#
# Por qué existe: el repo tenía 3 formas documentadas de arrancar (crewai
# run / uvicorn a mano / docker compose) y 3 entornos virtuales sueltos
# (.venv, venv, venv_chat) sin indicar cuál usar. Este script no cambia
# ninguna de ellas -- sigue siendo válido arrancar a mano como describe el
# README -- solo automatiza la ruta feliz (dependencias + .env + uvicorn)
# para no tener que decidir nada la primera vez.
#
# Uso:
#   ./start.sh              # backend local con reload (motor LangChain, default), puerto 8000
#   PORT=8080 ./start.sh    # idem, en otro puerto (por si 8000 ya está en uso)
#   ./start.sh --docker     # stack completo (Postgres + Redis + Prometheus + Grafana)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# Detecta puerto ocupado y busca automáticamente uno libre
check_port_available() {
    local port=$1
    # intenta conectar a localhost:puerto; si falla, está libre
    (echo >/dev/tcp/localhost/"$port") 2>/dev/null && return 1 || return 0
}

PORT="${PORT:-8000}"
REQUESTED_PORT="$PORT"

# Si el puerto pedido está ocupado, busca el siguiente libre (hasta +20)
if ! check_port_available "$PORT"; then
    ORIGINAL_PORT="$PORT"
    for offset in {1..20}; do
        PORT=$((ORIGINAL_PORT + offset))
        if check_port_available "$PORT"; then
            echo "⚠️  Puerto $ORIGINAL_PORT ocupado, usando $PORT en su lugar" >&2
            break
        fi
    done
    if [[ $PORT -eq $((ORIGINAL_PORT + 20)) ]] && ! check_port_available "$PORT"; then
        echo "❌ Puertos $ORIGINAL_PORT-$PORT todos ocupados. Intenta:" >&2
        echo "  PORT=9000 ./start.sh" >&2
        exit 1
    fi
fi

if [[ "${1:-}" == "--docker" ]]; then
    if [[ ! -f .env ]]; then
        echo "Falta .env. Copiando .env.example -> .env" >&2
        cp .env.example .env
        echo "Completa DEEPINFRA_API_KEY, SANTISIMA_SESSION_SECRET y SANTISIMA_CLAVE_CIFRADO en .env y vuelve a correr ./start.sh --docker" >&2
        exit 1
    fi
    # Bind mounts de docker-compose.yml: deben existir antes del primer `up`
    # (un bind mount de un archivo que no existe en el host puede crear un
    # directorio vacío en su lugar, según la versión de Docker -- peor que
    # cualquiera de los dos casos de abajo).
    touch dispositivos.db purga_estado.json
    if [[ ! -f deidad_1.jpeg ]]; then
        echo "⚠️  Falta deidad_1.jpeg (imagen del panel, no versionada -- ver docs/despliegue.md). Creando placeholder vacío: GET /assets/deidad.jpg devolverá 200 con una imagen en blanco hasta que copies el archivo real." >&2
        touch deidad_1.jpeg
    fi
    exec docker compose up
fi

if [[ ! -f .env ]]; then
    echo "Falta .env. Copiando .env.example -> .env" >&2
    cp .env.example .env
    echo "Completa DEEPINFRA_API_KEY, SANTISIMA_SESSION_SECRET y SANTISIMA_CLAVE_CIFRADO en .env y vuelve a correr ./start.sh" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "Falta 'uv' (https://docs.astral.sh/uv/). Instálalo o arranca a mano:" >&2
    echo "  pip install -e . && uvicorn la_santisima_conversacional.presentation.http_api:app --reload" >&2
    exit 1
fi

# `uv sync` crea/actualiza .venv a partir de uv.lock -- mismo entorno que
# usa el resto del equipo, sin depender de qué otro venv haya suelto en el repo.
uv sync --quiet

echo "Arrancando backend en http://localhost:${PORT} (Ctrl+C para detener)"
exec uv run uvicorn la_santisima_conversacional.presentation.http_api:app --reload --port "${PORT}"
