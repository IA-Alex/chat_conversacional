# Troubleshooting — La Santísima Muerte

Formato: síntoma → diagnóstico → arreglo. Comandos concretos, contra este
backend en concreto — no "revisa los logs" en abstracto.

## LLM degraded

**Síntoma**: `GET /health/ready` devuelve 503, o la app responde pero con
respuestas de fallback genéricas (no las respuestas devocionales
normales), o la alerta `SantisimaLLMDegradado` dispara.

**Diagnóstico**:

```bash
# 1. Confirmar el estado reportado por el proceso
curl -s localhost:8000/health/ready
# 503 {"status": "degraded", "detail": "Motor de IA operando en modo fallback."}
# significa que servicio_respuestas.esta_degradado == True

curl -s localhost:8000/metrics/health | python3 -m json.tool
# "llm_adapter_status": "degraded" confirma lo mismo con más contexto
# (db_backend, redis_rate_limit_enabled, ultima_purga)

# 2. santisima_llm_degradado en /metrics (para Prometheus/Grafana)
curl -s localhost:8000/metrics | grep santisima_llm_degradado
```

`esta_degradado` se fija en `True` una sola vez, al construir el
adapter, si `flow.json` no carga (ver
`infrastructure/crewai_adapter.py` — `self.esta_degradado = True` en la
rama de excepción de `_configurar_flow`). Con `use_langchain=True`
(default — ver `Settings.use_langchain` y el commit
`8168590 fix: fija use_langchain=True por defecto`), el adapter en uso es
`langchain_adapter.py`, no `crewai_adapter.py`; confirmar cuál está
activo:

```bash
journalctl -u santisima | grep "use_langchain"
# línea de arranque: "Backend ... listo (use_langchain=True, ...)"
```

Causas concretas a revisar, en orden de probabilidad:

1. **`flow.json` ausente o corrupto** (solo relevante si `use_langchain=False`,
   CrewAI):
   ```bash
   python3 -c "import json; json.load(open('src/la_santisima_conversacional/infrastructure/flow.json'))"
   ```
   Un `JSONDecodeError` o `FileNotFoundError` aquí es la causa. Restaurar
   el archivo desde git (`git checkout -- src/.../flow.json`) y reiniciar.

2. **`DEEPINFRA_API_KEY` inválida o revocada**:
   ```bash
   curl -s https://api.deepinfra.com/v1/openai/models \
     -H "Authorization: Bearer $DEEPINFRA_API_KEY" | head -c 300
   ```
   Un 401 aquí confirma la key. Regenerar en el dashboard de DeepInfra,
   actualizar `.env`, `systemctl restart santisima`.

3. **DeepInfra caído o degradado del lado del proveedor** — ver
   `INCIDENT_RESPONSE.md#llm-provider-outage`.

**Arreglo**: una vez corregida la causa raíz, reiniciar el proceso
(`systemctl restart santisima`) — `esta_degradado` se evalúa una sola vez
al construir el adapter en `_lifespan`, no se auto-recupera en caliente.
Confirmar con `curl -s localhost:8000/health/ready` → 200.

## Latencia alta

**Síntoma**: alerta `SantisimaLatenciaP95Alta` (p95 de
`POST /api/v1/mensajes` > 5s durante 5 min), o usuarios reportando
respuestas lentas.

**Diagnóstico**:

```bash
# p95/p99 vía Prometheus (si corre Prometheus + reglas de monitoring/prometheus_rules.yml)
# histogram_quantile(0.95, sum(rate(santisima_http_request_latency_seconds_bucket{endpoint="/api/v1/mensajes"}[5m])) by (le))

# Sin Prometheus a mano, inspeccionar los buckets crudos:
curl -s localhost:8000/metrics | grep 'santisima_http_request_latency_seconds_bucket{endpoint="/api/v1/mensajes"'
```

Causas a revisar en orden:

1. **DeepInfra con latencia elevada del lado del proveedor.** No hay
   status page propio documentado en este repo; medir directamente:
   ```bash
   time curl -s https://api.deepinfra.com/v1/openai/chat/completions \
     -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"google/gemma-4-31B-it-turbo","messages":[{"role":"user","content":"hola"}]}' \
     -o /dev/null -w '%{time_total}\n'
   ```
   Si esto solo es lento, el cuello de botella es el proveedor, no este
   backend — ver `INCIDENT_RESPONSE.md#llm-provider-outage` para decidir
   si escalar.

2. **`llm_timeout_segundos` / `llm_max_reintentos`** (`Settings`, default
   20s / 2 reintentos): con reintentos, una llamada lenta que además
   falla puede acumular hasta `llm_timeout_segundos * (1 + llm_max_reintentos)`
   ≈ 60s antes de responder (fallback). Confirmar valores efectivos:
   ```bash
   grep -E "SANTISIMA_LLM_TIMEOUT|SANTISIMA_LLM_MAX_REINTENTOS" .env
   ```
   Si no están en `.env`, están en el default de `config.py` (20.0 / 2).

3. **Carga del proceso** — con un solo worker uvicorn (default), toda la
   concurrencia comparte un proceso: `journalctl -u santisima` para ver
   si hay saturación evidente (muchas requests simultáneas, GC pausado,
   etc.) y considerar `--workers` (con las salvedades de `SCALING.md`)
   o, mejor, pasar a Postgres+Redis y escalar instancias.

**Arreglo**: si es DeepInfra, no hay arreglo local (ver
`INCIDENT_RESPONSE.md`); si es timeout/reintentos mal ajustados para el
modelo actual, ajustar `SANTISIMA_LLM_TIMEOUT_SEGUNDOS` /
`SANTISIMA_LLM_MAX_REINTENTOS` en `.env` y reiniciar.

## Purga de retención atrasada

**Síntoma**: alerta `SantisimaPurgaRetencionAtrasada` (última purga
exitosa hace > 24h), o `ultima_purga` en `/metrics/health` con timestamp
viejo o `exitosa: false`.

**Diagnóstico**:

```bash
# Estado crudo que lee /metrics/health
cat purga_estado.json   # o la ruta de SANTISIMA_PURGA_ESTADO_PATH
python3 -c "
import json, time
d = json.load(open('purga_estado.json'))
print('hace', (time.time() - d['timestamp'])/3600, 'horas — exitosa:', d['exitosa'])
"

# Vía la API (JSON):
curl -s localhost:8000/metrics/health | python3 -m json.tool

# ¿El timer systemd sigue programado y corriendo?
systemctl list-timers santisima-purga-retencion.timer
systemctl status santisima-purga-retencion.service
journalctl -u santisima-purga-retencion.service -n 50
```

Causas concretas:

1. **Timer no habilitado** (`systemctl list-timers` no lo lista, o
   `Persistent`/`OnCalendar` deshabilitados):
   ```bash
   systemctl enable --now santisima-purga-retencion.timer
   ```

2. **El script falló** (`exitosa: false` en `purga_estado.json` — ver
   `scripts/purgar_retencion.py`, que registra `exitosa=False` antes de
   re-lanzar cualquier excepción):
   ```bash
   journalctl -u santisima-purga-retencion.service -n 100 --no-pager
   ```
   Causas típicas del script: `sqlite_db_path`/`clave_cifrado` no
   coinciden con los del backend (`EnvironmentFile` del `.service` apunta
   a un `.env` distinto o desactualizado), o permisos de escritura sobre
   la ruta de la base o de `purga_estado.json`.

3. **`purga_estado_path` inconsistente** entre el backend y el script (si
   cada uno lee una ruta distinta, `/metrics/health` nunca refleja
   corridas reales aunque el timer sí ejecute):
   ```bash
   grep SANTISIMA_PURGA_ESTADO_PATH .env
   ```

**Arreglo**: corregir la causa, correr manualmente una vez para
confirmar (`sudo -u santisima .venv/bin/python scripts/purgar_retencion.py`),
verificar que `purga_estado.json` se actualizó, y confirmar que el timer
queda `enabled` y `active (waiting)`.

**Si este despliegue NO usa systemd** (contenedor, host minimalista): el
diagnóstico de arriba (pasos 2 y 3) aplica igual, pero los comandos de
inspección cambian — no hay `journalctl` ni `systemctl`:

| Mecanismo | Cómo verificar que corre | Cómo ver el resultado |
|---|---|---|
| systemd timer | `systemctl list-timers santisima-purga-retencion.timer` | `journalctl -u santisima-purga-retencion.service -n 100` |
| cron + `scripts/retencion_cron.sh` | `crontab -l \| grep retencion` | El log al que redirige el cron (ver `docs/despliegue.md` §7) |
| `docker-compose.purga.yml` | `docker compose -f docker-compose.purga.yml run --rm purga-retencion` (corrida puntual) | La salida del `run`; deja `purga_estado.json` en el repo montado |

En los tres casos la fuente de verdad es la misma: el campo `ultima_purga`
de `GET /metrics/health` (y `santisima_purga_ultimo_exito_timestamp_segundos`
en `/metrics`). Si ese timestamp no avanza, el problema no está en el
script — está en que el scheduler no lo está disparando.

## "Sesión inválida" tras un deploy (session_secret mismatch)

**Síntoma**: tras un deploy o reinicio, usuarios existentes reciben 404
"Sesión no encontrada" en `POST /api/v1/mensajes` o 401 "device_token no
reconocido" — aunque el dispositivo/sesión existía momentos antes.

**Diagnóstico**: este es un gotcha real y documentado en
`presentation/http_api.py:_fingerprint_secreto`. `SANTISIMA_SESSION_SECRET`
firma HMAC tanto `device_token` como `session_id`
(`infrastructure/security.py`); si el valor efectivo cambia entre dos
arranques del proceso — típicamente porque una variable de entorno
exportada en el shell (`export SANTISIMA_SESSION_SECRET=...`) le gana en
silencio al valor de `.env` (precedencia estándar: entorno > archivo) —
todo token firmado con el secreto anterior deja de validar de golpe.

```bash
# El fingerprint (hash corto, no reversible) se loguea en cada arranque —
# comparar entre el arranque de ANTES y el de DESPUÉS del deploy:
journalctl -u santisima | grep "session_secret_fingerprint"
```

Si el fingerprint cambió entre dos arranques consecutivos sin que nadie
rotara `SANTISIMA_SESSION_SECRET` intencionalmente, esa es la causa.

**Arreglo**: fijar `SANTISIMA_SESSION_SECRET` explícitamente en `.env`
(no depender de una variable de shell heredada) y confirmar que el
`EnvironmentFile=` del `.service` systemd apunta al `.env` correcto.
Reiniciar. Nota: esto invalida TODOS los tokens emitidos con el secreto
anterior — no hay forma de "recuperar" sesiones viejas, solo evitar que
vuelva a pasar (ver también `ROLLBACK.md`, mismo invariante).

## CORS "Verifica tu conexión" (falso negativo)

**Síntoma**: el frontend muestra un error de conexión genérico ("Verifica
tu conexión") pero el backend está sano (`/health` responde 200) y no hay
nada en los logs del backend sobre la request en cuestión — o sí aparece,
pero como 400.

**Diagnóstico**: gotcha documentado en `_permitir_origen_propio` /
`crear_app` (`presentation/http_api.py`). Pasa cuando la página se sirve
desde un origen loopback distinto del que usa el cliente para llamar a la
API — p. ej. HTML abierto en `http://localhost:8000` pero `API_BASE`
apunta a `http://127.0.0.1:8000` (o viceversa), o un frontend separado en
`http://localhost:3000` sin ese origen en `SANTISIMA_CORS_ORIGINS`.
`CORSMiddleware` responde al preflight con 400 "Disallowed CORS origin" —
el navegador lo reporta al JS como un fallo de red indistinguible de una
caída real del backend.

```bash
# Reproducir el preflight a mano y ver si CORS lo rechaza:
curl -s -i -X OPTIONS localhost:8000/api/v1/mensajes \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" | head -20
# 400 "Disallowed CORS origin" confirma el diagnóstico
```

Loopback (`localhost`/`127.0.0.1`, cualquier puerto) siempre debería
pasar vía el `allow_origin_regex` de `crear_app` — si un origen loopback
da 400, revisar que el esquema (`http` vs `https`) coincida exactamente
con el regex `^https?://(localhost|127\.0\.0\.1)(:\d+)?$`.

**Arreglo**:
- Si es el frontend servido por el propio backend (`GET /` sirve
  `index_santa_flat.html`), usar ese mismo origen para las llamadas API
  (mismo origen = CORS no aplica en absoluto, ver comentario en
  `_RUTA_FRONTEND`) en vez de abrir el HTML por `file://` o desde otro
  puerto.
- Si es un frontend separado deliberadamente, añadir su origen exacto a
  `SANTISIMA_CORS_ORIGINS` (CSV) y reiniciar.
