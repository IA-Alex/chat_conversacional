# Imagen para el despliegue "todo en contenedor" (docker-compose.yml).
#
# El despliegue de referencia del proyecto sigue siendo bare venv + systemd
# (ver docs/runbooks/DEPLOYMENT.md, docs/despliegue.md): esta imagen no lo
# reemplaza, es una alternativa para quien quiera correr el stack completo
# (backend + Postgres + Redis + Prometheus + Grafana) con un solo comando,
# p. ej. para desarrollo local o un entorno de staging.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
# curl: lo usa HEALTHCHECK. libpq-dev: requerido para compilar psycopg si
# no hay wheel binaria para esta plataforma (extra [postgres]).

COPY pyproject.toml uv.lock* ./
# --no-deps no: dependencias declaradas en pyproject.toml, no hay código
# fuente que "editable install" necesite todavía en este paso — solo se
# resuelve el árbol de dependencias, para aprovechar la cache de capas de
# Docker mientras src/ no cambie.
RUN pip install --no-cache-dir -e ".[crewai,postgres,redis]"

COPY src ./src
# _RUTA_FRONTEND y _RUTA_AVISO_PRIVACIDAD en presentation/http_api.py
# resuelven rutas relativas a la raíz del repo (parents[3] desde
# http_api.py) — sin estos dos, GET "/" y GET /privacidad/documento
# devuelven 404/500 en el contenedor aunque el resto de la API funcione.
COPY frontend/index_santa_flat.html ./frontend/index_santa_flat.html
COPY docs/privacidad.md ./docs/privacidad.md

RUN useradd -m -u 1000 santisima && chown -R santisima:santisima /app
USER santisima

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "la_santisima_conversacional.presentation.http_api:app", "--host", "0.0.0.0", "--port", "8000"]
