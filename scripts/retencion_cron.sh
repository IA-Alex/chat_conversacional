#!/usr/bin/env bash
# retencion_cron.sh — alternativa a systemd para la purga de retención.
#
# Por qué existe este archivo habiendo ya un systemd timer
# (scripts/systemd/santisima-purga-retencion.{service,timer}): el timer es
# la opción correcta en un servidor con systemd (es lo que documenta
# docs/despliegue.md §4), pero no es la única forma en que este backend se
# despliega. Un contenedor, un host sin systemd (Alpine, contenedores
# minimalistas), un macOS de desarrollo o una tarea programada de un
# orquestador no tienen timers — sin esta alternativa, la purga
# simplemente no corre en esos entornos, y "no corre" es exactamente el
# incumplimiento de la política de retención que el job existe para evitar.
#
# No duplica lógica de purga: solo envuelve scripts/purgar_retencion.py
# (que ya registra el resultado en purga_estado.json y alimenta
# santisima_purga_ultimo_exito_timestamp_segundos — ver
# infrastructure/purga_estado.py).
#
# Uso — cron diario a las 03:00:
#   0 3 * * * /ruta/al/repo/scripts/retencion_cron.sh >> /var/log/santisima-purga.log 2>&1
#
# O directamente contra el contenedor del backend, sin cron en el host:
#   docker compose run --rm purga-retencion
#   (ver docker-compose.purga.yml)
#
# Variables (todas opcionales; el .env del proyecto las define igual):
#   SANTISIMA_PURGA_ESTADO_PATH   Dónde escribir el resultado. Default: el
#                                 que ya trae Settings (purga_estado.json).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# Se prefiere el intérprete del venv del proyecto (donde están instaladas
# las dependencias de la app) y se cae al python3 del PATH si no existe:
# en un contenedor las dependencias suelen estar en el python del sistema,
# no en un venv.
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${REPO_ROOT}/.venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

if [[ -z "${PYTHON:-}" ]]; then
    echo "retencion_cron.sh: ERROR: no se encontró un intérprete de Python." >&2
    exit 1
fi

# Marca de tiempo del wrapper (además de la que escribe el propio script):
# permite distinguir en el log "el cron no disparó" de "disparó y la purga
# falló" — dos causas con arreglos completamente distintos.
echo "[retencion_cron.sh] $(date -u +%Y-%m-%dT%H:%M:%SZ) iniciando purga de retención"

cd "${REPO_ROOT}"
exec "${PYTHON}" scripts/purgar_retencion.py "$@"
