# Monitoreo — La Santísima Muerte

Decisión: **Prometheus + Grafana** para local/self-hosted; el mismo `GET
/metrics` (formato de exposición estándar) también puede ser leído por un
CloudWatch Agent con `prometheus_scrape` o por el Datadog Agent
(`openmetrics` check) sin cambiar una línea de este backend — la
instrumentación (`prometheus-client`, `src/.../infrastructure/metrics.py`)
es independiente del backend de observabilidad elegido. Se documenta
Prometheus porque es lo que corre en local/staging sin cuenta de nube.

## Qué expone el backend

- `GET /metrics` — formato de exposición Prometheus (sin auth, sin datos
  de usuario: solo contadores/histogramas agregados).
- `GET /metrics/health` — JSON legible por humanos, mismo propósito que
  un dashboard pero sin necesitar Grafana corriendo (ver
  `docs/runbooks/HEALTH_CHECKS.md`).

**Importante para el scrape**: `santisima_purga_ultimo_exito_timestamp_segundos`,
`santisima_redis_up` y `santisima_llm_degradado` **no se actualizan solos**
con un scrape de `/metrics` — se fijan como efecto secundario de llamar
`/metrics/health`. Por eso `prometheus.yml` define un segundo job
(`santisima-health`) que scrapea ese endpoint con la misma frecuencia;
sin él, las alertas que dependen de esos gauges (`SantisimaPurgaRetencionAtrasada`,
`SantisimaRedisInalcanzable`, `SantisimaLLMDegradado`) pueden leer un valor
viejo indefinidamente.

## Correr Prometheus + Grafana en local

```bash
docker run -d --name santisima-prometheus -p 9090:9090 \
  -v "$PWD/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml" \
  -v "$PWD/monitoring/prometheus_rules.yml:/etc/prometheus/prometheus_rules.yml" \
  prom/prometheus

docker run -d --name santisima-grafana -p 3000:3000 grafana/grafana
# Grafana → Connections → Data sources → Prometheus → http://host.docker.internal:9090
# Dashboards → Import → pegar monitoring/grafana_dashboard.json
```

`monitoring/prometheus.yml` (scrape config mínimo, crear junto a este
README si no existe):

```yaml
global:
  scrape_interval: 15s
rule_files:
  - prometheus_rules.yml
scrape_configs:
  - job_name: santisima-backend
    static_configs:
      - targets: ["host.docker.internal:8000"]
```

El archivo real del repo define **dos jobs** (ver el comentario dentro):
`santisima-backend` para `/metrics` y `santisima-health` para
`/metrics/health` — el segundo es necesario para que los gauges que ese
endpoint actualiza (purga, Redis) no queden con valores viejos.

## Alertas base (`prometheus_rules.yml`)

| Alerta | Condición | Severidad |
|---|---|---|
| `SantisimaErrorRateAlto` | 5xx / total > 5% durante 5 min | alta |
| `SantisimaLatenciaP95Alta` | p95 de `/api/v1/mensajes` > 5s durante 5 min | media |
| `SantisimaRateLimitSpike` | rate limit violations > 1/s durante 10 min | media |
| `SantisimaLLMDegradado` | `santisima_llm_degradado == 1` durante 2 min | alta |
| `SantisimaPurgaRetencionAtrasada` | última purga exitosa hace > 24h | media |
| `SantisimaPostgresConexionesSaturadas` | `santisima_db_connections_active{backend="postgres"} > 80` durante 5 min | alta |
| `SantisimaErroresBaseDeDatos` | operaciones de BD fallando > 0.1/s durante 5 min | alta |
| `SantisimaRedisInalcanzable` | `santisima_redis_up == 0` habiendo estado en 1 hace 1h | alta |
| `SantisimaDegradacionRecurrente` | > 3 entradas a degradado en 1h | media |
| `SantisimaAuthFailuresSpike` | requests de dispositivos revocados sostenidos | baja |

Cada alerta enlaza al runbook correspondiente en `annotations.runbook`.

## Dashboard (`grafana_dashboard.json`)

Error rate, latencia p50/p95/p99 de mensajes, rate limit violations por
tipo, auth failures por motivo, estado del LLM, mensajes/min, antigüedad
de la última purga y dispositivos revocados — un panel por métrica
pedida en la auditoría.

Paneles agregados junto con las métricas de operación (ids 9–12):

- **Sesiones activas / duración de sesión** — `sum(santisima_active_sessions)`
  (sumado entre instancias, ver `multiprocess_mode="livesum"`) con p50/p95
  de `santisima_session_duration_seconds`.
- **Conexiones a la BD vs `max_connections`** — `santisima_db_connections_active`
  junto a la tasa de creación de conexiones y las filas del historial.
  Es el panel que anticipa el `FATAL: sorry, too many clients already`.
- **Errores de BD / min y estado de Redis** — `santisima_db_errors_total`
  por backend y `santisima_redis_up`. El segundo solo se alimenta si el
  job `santisima-health` está configurado (ver arriba).
- **Entradas a degradado del LLM** — `increase(...[1h])` de
  `santisima_llm_degradation_events_total`: distingue una caída puntual de
  un proveedor inestable que se degrada y recupera en bucle.
