# Health Checks — La Santísima Muerte

Los cuatro endpoints de operación expuestos por
`presentation/http_api.py`, qué significa cada respuesta y qué debe hacer
un humano (o un orquestador) en cada caso. Ninguno requiere auth (mismo
criterio en los cuatro: un probe de load balancer o un scraper Prometheus
no porta `device_token` ni API key, y ninguno expone contenido de
conversaciones — ver el docstring de `metricas_prometheus` en
`http_api.py`).

## `GET /health` — liveness

```bash
curl -s localhost:8000/health
# {"status": "ok"}
```

Confirma únicamente que el proceso ASGI está vivo y respondiendo — **no**
dice nada sobre si el motor de IA funciona. Siempre devuelve 200 mientras
el proceso responda; no lee `esta_degradado`, no toca disco ni el LLM.

**Qué hacer con cada valor**:

- **200 `{"status": "ok"}`**: el proceso está arriba. No es suficiente
  para decidir si debe recibir tráfico real — usar `/health/ready` para
  eso.
- **Sin respuesta / timeout / connection refused**: el proceso está caído
  o no arrancó. Ver `TROUBLESHOOTING.md` y `journalctl -u santisima -n
  50` para la causa del crash; systemd lo reinicia solo si
  `Restart=on-failure` está en la unit (ver `docs/despliegue.md §4`).

**Uso recomendado**: liveness probe puro (¿reiniciar el proceso?). Si esto
falla, reiniciar tiene sentido casi siempre — no hay estado interno que
un restart pueda empeorar.

## `GET /health/ready` — readiness

```bash
curl -s -i localhost:8000/health/ready
```

Refleja `servicio_respuestas.esta_degradado`: si el flow del motor de IA
(CrewAI o LangChain, según `Settings.use_langchain`) falló al construirse,
`esta_degradado=True` y el proceso sigue vivo pero sirviendo únicamente
respuestas de fallback genéricas — no las respuestas devocionales reales.
Cada llamada a este endpoint también actualiza el gauge
`santisima_llm_degradado` (ver `infrastructure/metrics.py`), así que
llamarlo periódicamente (probe, curl manual) es lo que mantiene esa
métrica fresca para Prometheus.

**Respuestas posibles**:

- **200 `{"status": "ready"}`**: motor de IA operando normal. Seguro
  recibir tráfico.
- **503 `{"status": "degraded", "detail": "Motor de IA operando en modo
  fallback."}`**: `esta_degradado=True`. El proceso responde pero degradado
  — ver `TROUBLESHOOTING.md#llm-degraded` para diagnóstico (causa típica:
  `flow.json` corrupto/ausente si `use_langchain=False`, o
  `DEEPINFRA_API_KEY` inválida). `esta_degradado` se fija una sola vez al
  construir el adapter en `_lifespan` — **no se auto-recupera en
  caliente**; corregir la causa raíz requiere `systemctl restart
  santisima`.

**Qué hacer con cada valor**:

- Un load balancer o proceso de rollout (ver `DEPLOYMENT.md`) debe sacar
  la instancia de rotación en 503 y no devolverla hasta ver 200 de forma
  sostenida tras el restart que corrige la causa.
- No reintentar automáticamente sin intervención: como no se auto-recupera,
  un probe que solo reintenta indefinidamente deja la instancia degradada
  para siempre sin que nadie lo note salvo por la alerta
  `SantisimaLLMDegradado` (`for: 2m` en `monitoring/prometheus_rules.yml`)
  o por usuarios reportando respuestas genéricas.

**Uso recomendado**: readiness probe (¿debe esta instancia recibir
tráfico?), distinto de liveness — una instancia degradada NO debe
reiniciarse automáticamente en bucle (el restart no arregla una
`DEEPINFRA_API_KEY` inválida), debe alertar a un humano.

## `GET /metrics` — Prometheus text format

```bash
curl -s localhost:8000/metrics | head -30
```

Expone todas las métricas de `infrastructure/metrics.py` en el formato de
exposición estándar de Prometheus (`text/plain`, vía
`prometheus_client.generate_latest`). Pensado para un scraper (Prometheus,
CloudWatch Agent, OTel Collector), no para lectura humana directa — aunque
`curl | grep <métrica>` sirve para inspección puntual sin Prometheus a
mano (ver ejemplos en `TROUBLESHOOTING.md`).

Métricas expuestas (nombre → qué mide):

| Métrica | Tipo | Qué mide |
|---|---|---|
| `santisima_http_requests_total{endpoint,metodo,status}` | Counter | Requests HTTP por endpoint/método/código |
| `santisima_http_request_latency_seconds{endpoint}` | Histogram | Latencia de respuesta, buckets pensados para llamadas a LLM (0.1s–30s) |
| `santisima_llm_degradado` | Gauge | 1 si el motor de IA está en modo fallback, 0 si no — actualizado por `GET /health/ready` |
| `santisima_purga_ultimo_exito_timestamp_segundos` | Gauge | Epoch de la última purga de retención exitosa — actualizado por `GET /metrics/health` |
| `santisima_purga_ultimo_registros_borrados` | Gauge | Filas borradas en la última purga |
| `santisima_rate_limit_exceeded_total{tipo}` | Counter | Requests rechazados por rate limit (`mensajes`/`registro`) |
| `santisima_auth_failures_total{motivo}` | Counter | Fallos de auth de dispositivo (`sin_token`/`firma_invalida`/`no_reconocido`/`revocado`) |
| `santisima_device_revocations_total` | Counter | Dispositivos revocados vía `/admin/dispositivos/{id}/revocar` |
| `santisima_messages_total` | Counter | Mensajes de conversación procesados exitosamente |
| `santisima_session_duration_seconds` | Histogram | Duración de cada sesión cerrada (reinicio), buckets 1 min–2 h |
| `santisima_active_sessions` | Gauge | Sesiones abiertas y no reiniciadas en esta instancia (`livesum` entre procesos) |
| `santisima_db_connections_active{backend}` | Gauge | Conexiones a la BD abiertas en este instante |
| `santisima_db_connections_created_total{backend}` | Counter | Conexiones abiertas desde el arranque |
| `santisima_db_errors_total{backend}` | Counter | Operaciones de BD que fallaron |
| `santisima_db_historial_filas{backend}` | Gauge | Filas totales en la tabla de historial (tamaño lógico) |
| `santisima_redis_up` | Gauge | 1 si el Redis del rate limiter responde PING |
| `santisima_llm_degradation_events_total` | Counter | Veces que el motor entró en degradado (transiciones, no estado) |

**Detalle importante para operar esto bien**: `santisima_llm_degradado` y
las dos métricas de purga **no se actualizan solas** con cada scrape de
`/metrics` — se fijan como efecto secundario de llamar `/health/ready`
(la primera) y `/metrics/health` (las otras dos). Si nada llama a esos dos
endpoints entre scrapes, esas tres métricas quedan con el último valor
observado, potencialmente viejo. En la práctica esto es inofensivo si hay
un probe de readiness periódico (típico en cualquier despliegue) y
Prometheus scrapeando `/metrics/health` o `/health/ready` con la misma
frecuencia que `/metrics` — pero es la razón por la que las reglas de
`monitoring/prometheus_rules.yml` (`SantisimaLLMDegradado`,
`SantisimaPurgaRetencionAtrasada`) solo son confiables si ambos endpoints
se llaman con regularidad, no solo `/metrics`.

**Qué hacer con cada valor**: ver `monitoring/prometheus_rules.yml` (cada
regla tiene una anotación `runbook:` que apunta al procedimiento exacto)
y `TROUBLESHOOTING.md` para los síntomas concretos de
`santisima_llm_degradado==1`, latencia alta y purga atrasada.

## `GET /metrics/health` — resumen JSON legible

```bash
curl -s localhost:8000/metrics/health | python3 -m json.tool
```

```json
{
  "llm_adapter_status": "ok",
  "db_backend": "sqlite",
  "db_connection_pool_active_connections": 0,
  "db_historial_filas": 12480,
  "sesiones_activas": 3,
  "redis_rate_limit_enabled": false,
  "redis_connection_status": "disabled",
  "ultima_purga": {
    "timestamp": 1757900000.0,
    "registros_borrados": 12,
    "exitosa": true
  }
}
```

A diferencia de `/metrics` (pensado para un scraper), este es el punto de
partida para un humano inspeccionando el estado del sistema — un solo
`curl` da la foto completa sin tener que cruzar cuatro métricas de
Prometheus a mano. También es el endpoint que actualiza los gauges de
purga en `/metrics` (ver arriba).

### `llm_adapter_status`: `"ok"` | `"degraded"`

Mismo dato que `/health/ready` (`esta_degradado`), en el vocabulario de
este JSON.

- **`"ok"`**: normal, no requiere acción.
- **`"degraded"`**: motor de IA sirviendo fallback. Acción: ver
  `TROUBLESHOOTING.md#llm-degraded` — diagnosticar causa
  (`flow.json`/`DEEPINFRA_API_KEY`/proveedor caído),
  corregir, `systemctl restart santisima`, confirmar `"ok"` tras el
  restart (no se auto-recupera).

### `db_backend`: `"sqlite"` | `"postgres"`

Refleja `Settings.usar_postgres` directamente (`"postgres"` si `True`,
`"sqlite"` si no) — no es una comprobación de que la conexión funcione, es
solo el backend configurado.

- **`"sqlite"`**: modo single-instance por defecto. Si el despliegue actual
  corre más de una instancia detrás de un load balancer, esto es un error
  de configuración — cada instancia tiene su propio archivo SQLite
  divergente (ver `SCALING.md`). Acción: verificar cuántas instancias
  están realmente sirviendo tráfico; si es más de una, esto necesita
  arreglarse migrando a Postgres antes que cualquier otra cosa.
- **`"postgres"`**: modo multi-instancia. Confirmar que `postgres_dsn`
  apunta a un servidor accesible — este campo no lo valida, solo refleja
  el flag; un DSN roto se manifiesta como errores 500 en
  `POST /api/v1/mensajes`, no aquí.

### `db_connection_pool_active_connections`: entero

Conexiones contra la base de datos abiertas **en este instante**
(`santisima_db_connections_active`, ver `infrastructure/metrics.py`). No es
un pool en sentido estricto y eso importa para interpretarlo:
`PostgresConversationRepository` abre una conexión nueva por operación (ver
su docstring), así que este número es aproximadamente la **concurrencia de
operaciones de BD** en ese momento.

- **`0` con `db_backend: "sqlite"`**: esperado siempre — SQLite es un
  archivo, no un servidor con conexiones concurrentes.
- **`0` con `db_backend: "postgres"`**: no hay operaciones de BD en curso
  (un scrape en un momento tranquilo). No es un error.
- **Número alto y creciente (p. ej. > 80 con los 100 usuarios de
  `tests/load/scenarios/db_pool_test.py`)**: la señal que este campo existe
  para dar. Postgres tiene `max_connections` (100 por defecto) y agotarlo
  se manifiesta como `FATAL: sorry, too many clients already` dentro del
  repositorio — que el usuario ve como timeout o 504, indistinguible de
  "el LLM va lento". Acción: subir `max_connections`, o implementar
  `psycopg_pool.ConnectionPool` (la evolución que el propio docstring del
  repositorio anticipa). Ver `SCALING.md`.
- **Comparar contra `max_connections` del servidor**, no contra un número
  absoluto fijo: lo relevante es qué fracción del límite se está usando.

### `db_historial_filas`: entero | `null`

Filas totales en la tabla `messages` (`count(*)`, consultado al vuelo).

- **Entero**: tamaño lógico del historial. Qué mirar es la **tendencia**,
  no el valor: con retención de 90 días y tráfico estable, este número
  debería estabilizarse. Si crece indefinidamente, la purga no está
  borrando (ver `TROUBLESHOOTING.md#purga-de-retencion-atrasada`) — y ese
  crecimiento es a la vez un problema de disco y un incumplimiento de la
  política de retención.
- **`null`**: el repositorio no implementa `contar_filas` (p. ej.
  `ConversationRepositoryMemory` en desarrollo). **`null` ≠ 0**: 0 sería
  "el historial está vacío", `null` es "no se midió". No interpretarlo como
  base vacía.

### `sesiones_activas`: entero

Sesiones creadas en esta instancia y todavía no reiniciadas
(`santisima_active_sessions`).

- Es una **cota inferior** del total real si hay más de una instancia: cada
  proceso reporta solo las que emitió él. Para el total, sumar la métrica
  Prometheus entre instancias (el gauge usa `multiprocess_mode="livesum"`).
- También es una cota inferior si se superaron las 10 000 sesiones seguidas
  (`_MAX_SESIONES_SEGUIDAS` en `http_api.py`, que existe para acotar
  memoria): las sesiones abandonadas sin reinicio se descartan por
  antigüedad. Una sesión abandonada no es un incidente — el tamaño real
  del historial está en `db_historial_filas`.
- **Qué hacer**: comparar contra el tráfico esperado. Un valor que no baja
  nunca sugiere que los clientes no están reiniciando sesiones (revisar el
  frontend) o que hay un `session_id` reutilizándose.

### `redis_connection_status`: `"disabled"` | `"ok"` | `"unreachable"`

Resultado de un PING real contra el Redis del rate limiter (no solo el flag
de configuración — para eso está `redis_rate_limit_enabled` al lado).

- **`"disabled"`**: `usar_redis_rate_limit=False`. **No es un problema**:
  es la configuración correcta en single-instance. No "arreglarlo"
  habilitando Redis sin haber migrado también a Postgres (ver `SCALING.md`)
  — los dos componentes tienen que migrar juntos.
- **`"ok"`**: el rate limiter compartido responde. Nada que hacer.
- **`"unreachable"`**: configurado pero no responde. **Estado peligroso**:
  con `usar_redis_rate_limit=True` cada request que toca el limitador
  depende de Redis, así que un Redis caído degrada el control de cupo del
  LLM justo cuando más tráfico hay. Acción: ver
  `INCIDENT_RESPONSE.md`.

### `redis_rate_limit_enabled`: `true` | `false`

Refleja `Settings.usar_redis_rate_limit` directamente.

- **`false`**: rate limiter en memoria (`LimitadorTasa`). Correcto solo en
  single-instance — ver el docstring de `infrastructure/rate_limit.py`:
  con más de una instancia, el límite efectivo real es
  `rate_limit_por_minuto * n_instancias` sin que nadie lo note salvo por
  abuso que se cuela.
- **`true`**: rate limiter en Redis (`LimitadorTasaRedis`), correcto
  entre instancias. Confirmar que `redis_url` apunta a un Redis accesible
  — igual que con Postgres, este campo no valida la conexión.
- **Acción combinada**: `db_backend` y `redis_rate_limit_enabled` deben
  cambiar **juntos** al pasar a multi-instancia (ver `SCALING.md`). Si uno
  dice `"postgres"`/`true` y el otro no, es una migración a medias —
  corregirla antes de sumar instancias.

### `ultima_purga`: `{timestamp, registros_borrados, exitosa}` | `null`

Lee `purga_estado_path` (default `purga_estado.json`), escrito por
`scripts/purgar_retencion.py` cada vez que corre (vía el timer systemd
`santisima-purga-retencion.timer`, ver `docs/despliegue.md §5`). El
proceso HTTP no ejecuta la purga — solo lee el resultado que otro proceso
dejó en disco (ver el docstring de `infrastructure/purga_estado.py`: es
la alternativa elegida a sumar un pushgateway).

- **`null`**: el archivo no existe o no se pudo parsear
  (`FileNotFoundError`, `JSONDecodeError`, campos faltantes — ver
  `leer_estado` en `infrastructure/purga_estado.py`, que devuelve `None`
  en cualquiera de esos casos en vez de lanzar). Acción: si el sistema es
  nuevo y la purga nunca corrió, esperado hasta la primera ejecución del
  timer; si ya debería haber corrido, ver
  `TROUBLESHOOTING.md#purga-de-retencion-atrasada`.
- **`exitosa: true`**: la última corrida completó sin excepción.
  `timestamp` reciente (horas, no días) es la señal sana; comparar con
  `time.time()` actual (ver ejemplo en `TROUBLESHOOTING.md`).
- **`exitosa: false`**: `scripts/purgar_retencion.py` capturó una
  excepción, registró `exitosa=False` y volvió a lanzarla (ver el
  script). Acción: `journalctl -u santisima-purga-retencion.service -n
  100` para la causa (típicamente `sqlite_db_path`/`clave_cifrado`
  desalineados entre el `.env` del backend y el del timer, o permisos de
  escritura) — ver `TROUBLESHOOTING.md#purga-de-retencion-atrasada`.
- **`timestamp` viejo (> 24h) con `exitosa: true`**: la última corrida
  exitosa fue hace mucho, pero el timer probablemente dejó de disparar
  del todo (no es un fallo del script, es que no corrió). Acción:
  `systemctl list-timers santisima-purga-retencion.timer` — si no
  aparece o está inactivo, `systemctl enable --now
  santisima-purga-retencion.timer`.
- Esto es exactamente lo que dispara `SantisimaPurgaRetencionAtrasada` en
  `monitoring/prometheus_rules.yml` (`(time() -
  santisima_purga_ultimo_exito_timestamp_segundos) > 86400`, `for: 10m`)
  — ese gauge se alimenta de este mismo campo (ver arriba, "detalle
  importante" en `/metrics`).

## Resumen: qué probe usar para qué

| Necesito... | Endpoint | Frecuencia sugerida |
|---|---|---|
| ¿Reiniciar el proceso? (liveness) | `GET /health` | Cada pocos segundos, por el orquestador/proxy |
| ¿Sacar la instancia de rotación? (readiness) | `GET /health/ready` | Cada pocos segundos, por el load balancer |
| Scrape para Prometheus/Grafana | `GET /metrics` | Según `scrape_interval` (ver `monitoring/README.md`) |
| Inspección humana rápida / dashboard simple | `GET /metrics/health` | Bajo demanda, o scrapeado también si se quiere alimentar los gauges de purga sin depender de `/health/ready` |
