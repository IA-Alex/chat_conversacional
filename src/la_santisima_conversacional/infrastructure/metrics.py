"""Métricas Prometheus del proceso servidor.

Antes no había ninguna métrica expuesta: un adapter LLM degradándose,
un rate limit disparándose en bucle, o una latencia p99 disparada solo
eran visibles buceando logs JSON línea por línea. ``prometheus-client``
es pura Python (sin dependencias nativas) y expone un registro global de
proceso — encaja con el requisito de monitoreo "ligero" sin sumar un
agente ni un SDK pesado. Un scraper (Prometheus, o el adapter CloudWatch
Agent/OTel Collector que lo lea vía `/metrics`) se conecta desde fuera;
este módulo no empuja nada por su cuenta.
"""

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "santisima_http_requests_total",
    "Requests HTTP recibidos, por endpoint/método/código de estado.",
    ["endpoint", "metodo", "status"],
)

http_request_latency_seconds = Histogram(
    "santisima_http_request_latency_seconds",
    "Latencia de respuesta HTTP en segundos, por endpoint.",
    ["endpoint"],
    # Buckets pensados para una respuesta que incluye una llamada a LLM
    # (segundos, no milisegundos): permiten leer p50/p95/p99 vía
    # histogram_quantile en Prometheus/Grafana sin re-desplegar buckets.
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 20, 30),
)

llm_degradado = Gauge(
    "santisima_llm_degradado",
    "1 si el motor de IA está operando en modo fallback (degradado), 0 si no.",
)

purga_ultimo_exito_timestamp = Gauge(
    "santisima_purga_ultimo_exito_timestamp_segundos",
    "Epoch (segundos) de la última purga de retención exitosa (ver scripts/purgar_retencion.py).",
)

purga_ultimo_registros_borrados = Gauge(
    "santisima_purga_ultimo_registros_borrados",
    "Filas borradas en la última ejecución de la purga de retención.",
)

rate_limit_exceeded_total = Counter(
    "santisima_rate_limit_exceeded_total",
    "Requests rechazados por rate limit, por tipo (mensajes/registro).",
    ["tipo"],
)

auth_failures_total = Counter(
    "santisima_auth_failures_total",
    "Fallos de autenticación de dispositivo, por motivo.",
    ["motivo"],
)

device_revocations_total = Counter(
    "santisima_device_revocations_total",
    "Dispositivos revocados vía /admin/dispositivos/{id}/revocar.",
)

messages_total = Counter(
    "santisima_messages_total",
    "Mensajes de conversación procesados exitosamente.",
)

# --- Sesiones -------------------------------------------------------------
# La auditoría pedía visibilidad de "sesiones activas" y "duración de
# sesión". Ni una ni otra se pueden derivar de los contadores HTTP: un
# contador de requests no dice cuántas conversaciones siguen vivas, ni
# cuánto duró la que acaba de reiniciarse. Se miden en el borde HTTP
# (``http_api.py``), que es donde existe la noción de "sesión".

session_duration_seconds = Histogram(
    "santisima_session_duration_seconds",
    "Duración en segundos de una sesión entre su creación y su reinicio, por dispositivo.",
    # Buckets en escala de minutos/horas (una conversación con la deidad es
    # un uso de sesión largo, no un request puntual): 1 min a 2 h.
    buckets=(60, 300, 600, 1800, 3600, 7200),
)

active_sessions = Gauge(
    "santisima_active_sessions",
    "Sesiones conversacionales abiertas y no reiniciadas en esta instancia.",
    multiprocess_mode="livesum",
)

# --- Base de datos --------------------------------------------------------
# ``PostgresConversationRepository`` abre una conexión nueva por operación
# (sin pool, ver su docstring). Bajo 100 requests concurrentes eso importa:
# el número de conexiones simultáneas contra Postgres es justo lo que
# revienta primero (``max_connections``), y sin esta métrica el síntoma
# visible es "el endpoint se cuelga", no "el pool está saturado". Se
# instrumenta en el repositorio, no en el borde HTTP, para que siga siendo
# cierto el día que se cambie a ``psycopg_pool.ConnectionPool``.

db_connections_active = Gauge(
    "santisima_db_connections_active",
    "Conexiones a la base de datos abiertas en este instante (en uso).",
    ["backend"],
    multiprocess_mode="livesum",
)

db_connections_created_total = Counter(
    "santisima_db_connections_created_total",
    "Conexiones a la base de datos abiertas desde el arranque del proceso.",
    ["backend"],
)

db_errors_total = Counter(
    "santisima_db_errors_total",
    "Operaciones de base de datos que fallaron, por backend.",
    ["backend"],
)

db_historial_filas = Gauge(
    "santisima_db_historial_filas",
    "Filas totales en la tabla de historial (tamaño del historial en disco/lógica).",
    ["backend"],
)

# --- Redis ----------------------------------------------------------------
# Se consulta bajo demanda desde ``GET /metrics/health`` (ver
# ``_estado_redis`` en http_api.py), no en cada request: un PING por request
# de mensajes sumaría una ida y vuelta de red al camino caliente solo para
# alimentar una métrica que se lee cada 15 s.

redis_up = Gauge(
    "santisima_redis_up",
    "1 si el rate limiter compartido (Redis) responde PING, 0 si no.",
)

# --- Degradación del LLM --------------------------------------------------
# ``llm_degradado`` (arriba) es el ESTADO actual; este contador registra
# cada VEZ que se entra en degradación. Un gauge no permite distinguir
# "lleva degradado desde el arranque" de "se degradó y se recuperó 40 veces
# en la última hora" — y esa diferencia es justo la que decide si hay que
# intervenir.

llm_degradation_events_total = Counter(
    "santisima_llm_degradation_events_total",
    "Veces que el motor de IA entró en modo degradado (fallback) desde el arranque.",
)
