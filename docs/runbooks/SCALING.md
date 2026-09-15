# Scaling — La Santísima Muerte

Cómo escalar este backend con lo que existe realmente en el repo. Sin
Kubernetes (no hay manifiestos ni referencia a él en el proyecto, salvo
como ejemplo de "un orquestador" en un comentario de `http_api.py`) —
todo lo de abajo asume systemd + un proxy TLS, como el resto de los
runbooks (ver `DEPLOYMENT.md`).

## El eje que importa: single-instance vs. multi-instance

No es "más CPU" o "más RAM" — es cuántos **procesos del backend** sirven
tráfico a la vez. Dos componentes tienen estado local por proceso y
dejan de ser correctos apenas hay más de una instancia:

1. **Persistencia**: `SQLiteConversationRepository` es un archivo en el
   disco de esa instancia. Dos instancias, dos archivos, dos historiales
   divergentes del mismo usuario según a cuál le toque servir cada
   request.
2. **Rate limiting**: `LimitadorTasa` (ver `infrastructure/rate_limit.py`)
   es un diccionario en memoria de ese proceso. Con `n` instancias, el
   límite real efectivo es `rate_limit_por_minuto * n` — cada instancia
   cuenta por su cuenta, sin coordinación (documentado explícitamente en
   el docstring del módulo).

Esto **no** es un detalle menor a ignorar "por ahora": corre en
producción, con datos sensibles (contenido devocional/emocional de
usuarios, categoría especial según `docs/compliance/gobernanza-ia.md`), y
la divergencia es silenciosa — no hay error, solo datos inconsistentes.

## Cuándo escalar

No escalar preventivamente — el propio README lo dice: "correcto y
suficiente mientras sea una sola instancia, no hay nada que ganar
activando Postgres/Redis antes de necesitarlos". Señales concretas para
pasar a multi-instancia:

- `SantisimaLatenciaP95Alta` disparándose de forma sostenida y el triage
  de `TROUBLESHOOTING.md#latencia-alta` descarta que sea DeepInfra o
  timeouts mal ajustados — el cuello de botella es el propio proceso
  saturado.
- Necesidad de disponibilidad durante deploys sin el downtime de
  segundos del restart single-instance (ver `DEPLOYMENT.md`).
- Volumen de tráfico que un solo proceso uvicorn no puede sostener incluso
  con `--workers` local (ver abajo, límite de esa opción).

## Camino 1: multi-proceso en una sola máquina (`--workers` / gunicorn)

Uvicorn/gunicorn con varios workers en la **misma máquina** es tentador
porque no requiere Postgres/Redis — pero cada worker es un proceso
Python separado con su propia memoria, así que **tiene exactamente el
mismo problema que multi-instancia**: cada worker abre su propio archivo
SQLite (o, peor, varios workers escribiendo al mismo archivo SQLite
concurrentemente, que no está diseñado para eso — ver los locks internos
de `SQLiteConversationRepository`, pensados para hilos de un mismo
proceso, no para procesos distintos) y su propio `LimitadorTasa` en
memoria.

**No usar `--workers > 1` sin antes activar Postgres + Redis** — en ese
sentido, `--workers` en esta app es multi-instancia con pasos extra, no
un camino distinto. Si el objetivo es más capacidad en una sola máquina,
el camino correcto es: activar Postgres + Redis (abajo) y luego sí subir
`--workers`, exactamente igual que si fueran máquinas separadas.

## Camino 2: multi-instancia (Postgres + Redis)

Requisito para correr más de un proceso del backend (misma máquina con
`--workers`, o varias máquinas/instancias detrás de un load balancer) de
forma correcta.

### Checklist de migración

- [ ] Aprovisionar un servidor Postgres accesible por red desde todas las
      instancias (no versionado en este repo — es infraestructura
      externa).
- [ ] Aprovisionar un servidor Redis accesible por red desde todas las
      instancias.
- [ ] `pip install -e ".[postgres,redis]"` en el venv de cada instancia
      (extras opcionales — no instalados por defecto, ver
      `pyproject.toml`).
- [ ] `.env` (idéntico en todas las instancias, salvo lo que
      deliberadamente difiera):
      ```bash
      SANTISIMA_USAR_POSTGRES=true
      SANTISIMA_POSTGRES_DSN=postgresql://usuario:password@host:5432/la_santisima
      SANTISIMA_USAR_REDIS_RATE_LIMIT=true
      SANTISIMA_REDIS_URL=redis://host:6379/0
      ```
- [ ] **`SANTISIMA_SESSION_SECRET` y `SANTISIMA_CLAVE_CIFRADO` idénticos
      en todas las instancias** — no es opcional. `session_id`/
      `device_token` son HMAC-firmados y stateless (ver
      `infrastructure/security.py`): cualquier instancia debe poder
      validar el token emitido por cualquier otra, lo que solo funciona
      si comparten el mismo `session_secret`. Mismo razonamiento para
      `clave_cifrado` — el contenido cifrado por una instancia debe ser
      descifrable por cualquier otra que lo lea después.
- [ ] Confirmar que `PostgresConversationRepository` usa el mismo
      contrato/esquema que `SQLiteConversationRepository` (cifrado,
      retención) — ver `infrastructure/repositories.py`. No requiere
      migración de datos manual de ida (se usa desde cero), pero sí
      revisar si hay datos existentes en SQLite que deban migrarse antes
      del corte (fuera del alcance de este repo: no hay script de
      migración SQLite→Postgres versionado — escribir uno si aplica antes
      de cortar tráfico).
- [ ] Arrancar UNA instancia primero contra Postgres+Redis, confirmar
      `curl -s localhost:8000/metrics/health` → `"db_backend":
      "postgres"`, `"redis_rate_limit_enabled": true`, antes de sumar más
      instancias.
- [ ] Sumar el resto de las instancias detrás del load balancer.
      **No se requiere session affinity** en el load balancer — cualquier
      instancia valida el token de cualquier otra (ver arriba).
- [ ] Confirmar en cada instancia nueva: `GET /health/ready` → 200 antes
      de meterla en rotación (ver `DEPLOYMENT.md#camino-multi-instancia`).
- [ ] Apuntar el scraper de Prometheus a **todas** las instancias
      (`/metrics` es por-proceso — un dashboard que solo scrapea una
      instancia subestima el tráfico real total).

### Qué NO cambia al escalar

`session_id` ya es un token firmado stateless y el resto del
dominio/adapters no sabe ni le importa qué repositorio o qué limitador
está detrás — ver README "Escalar a múltiples instancias". No hay lógica
de negocio que reescribir; es enteramente un cambio de configuración +
infraestructura.

## Límites que esto NO resuelve

- **El proveedor de LLM (DeepInfra) sigue siendo un único punto
  compartido** — sumar instancias del backend no añade capacidad de
  inferencia; si el cuello de botella real es latencia/rate limit del
  lado de DeepInfra, escalar el backend no ayuda (ver
  `INCIDENT_RESPONSE.md#llm-provider-outage`).
- **`llm_timeout_segundos`/`llm_max_reintentos`** son por-request,
  independientes de cuántas instancias corran — si el problema es
  timeouts mal ajustados para el modelo actual, ajustar esos valores en
  `.env`, no el número de instancias (ver
  `TROUBLESHOOTING.md#latencia-alta`).
- **No hay autoscaling** documentado ni configurado en este repo (no hay
  Kubernetes HPA, no hay Auto Scaling Group versionado) — escalar hoy es
  un procedimiento manual siguiendo este checklist, no una respuesta
  automática a carga.

## Cómo volver a single-instance

Si el tráfico baja y ya no justifica Postgres+Redis: apagar instancias
extra hasta quedar con una, luego `SANTISIMA_USAR_POSTGRES=false` /
`SANTISIMA_USAR_REDIS_RATE_LIMIT=false` requiere primero migrar los datos
de Postgres de vuelta a SQLite (no hay script para esto en el repo —
escribir uno si se necesita) antes de apagar Postgres, para no perder
historial. No es una operación frecuente ni optimizada en este proyecto;
tratarla como una migración deliberada, no un toggle.
