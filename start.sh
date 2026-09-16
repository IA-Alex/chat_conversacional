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
#   ./start.sh            # backend local con reload (motor LangChain, default)
#   ./start.sh --docker   # stack completo (Postgres + Redis + Prometheus + Grafana)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${1:-}" == "--docker" ]]; then
    if [[ ! -f .env ]]; then
        echo "Falta .env. Copiando .env.example -> .env" >&2
        cp .env.example .env
        echo "Completa DEEPINFRA_API_KEY, SANTISIMA_SESSION_SECRET y SANTISIMA_CLAVE_CIFRADO en .env y vuelve a correr ./start.sh --docker" >&2
        exit 1
    fi
    # Bind mounts de docker-compose.yml: deben existir antes del primer `up`.
    touch dispositivos.db purga_estado.json
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

echo "Arrancando backend en http://localhost:8000 (Ctrl+C para detener)"
exec uv run uvicorn la_santisima_conversacional.presentation.http_api:app --reload
