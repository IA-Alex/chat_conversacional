# Incident Response — La Santísima Muerte

Un incidente se ancla a una alerta de `monitoring/prometheus_rules.yml` o
a un reporte directo de usuarios. Este documento cubre **triage y
mitigación** — para diagnóstico paso a paso de una causa ya identificada,
ver `TROUBLESHOOTING.md`; para el significado de cada endpoint de salud,
`HEALTH_CHECKS.md`.

## Severidad y quién responde

Las alertas ya vienen con `severidad` en sus labels (ver
`monitoring/prometheus_rules.yml`):

| Severidad | Alertas | Respuesta esperada |
|---|---|---|
| **alta** | `SantisimaErrorRateAlto`, `SantisimaLLMDegradado` | Atender de inmediato — usuarios afectados en el momento |
| **media** | `SantisimaLatenciaP95Alta`, `SantisimaRateLimitSpike`, `SantisimaPurgaRetencionAtrasada` | Atender en el mismo día — degradación parcial o riesgo de retención de datos |
| **baja** | `SantisimaAuthFailuresSpike` | Revisar cuando haya ventana — señal de posible abuso, no de caída |

Este proyecto no tiene guardia rotativa documentada ni integración a
PagerDuty/Opsgenie en el repo — si se suma una, documentar aquí el
enrutamiento real en vez de asumirlo.

## Triage inicial (primeros 5 minutos, cualquier alerta)

```bash
# 1. ¿El proceso está vivo?
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/health

# 2. ¿Está listo para servir tráfico real?
curl -s -i localhost:8000/health/ready

# 3. Foto completa de estado
curl -s localhost:8000/metrics/health | python3 -m json.tool

# 4. Logs recientes, buscando tracebacks o el mensaje de arranque en modo debug
journalctl -u santisima -n 100 --no-pager
```

Con esto ya se sabe si el problema es "proceso caído" (ir a `#proceso-caído-o-no-arranca`
abajo), "degradado pero vivo" (`/health/ready` 503 —
`TROUBLESHOOTING.md#llm-degraded`) o "vivo y ready pero algo específico
falla" (seguir por alerta abajo).

## `error-rate-alto`

**Alerta**: `SantisimaErrorRateAlto` — más de 5% de requests con status
5xx en 5 minutos (`sum(rate(santisima_http_requests_total{status=~"5.."}[5m]))
/ sum(rate(santisima_http_requests_total[5m])) > 0.05`).

**Triage**:

```bash
# ¿Qué endpoints y qué códigos concretos están fallando?
curl -s localhost:8000/metrics | grep santisima_http_requests_total | grep -v 'status="2'

# Tracebacks recientes
journalctl -u santisima -n 200 --no-pager | grep -i "traceback\|error\|exception"
```

**Causas más probables, en orden**:

1. **`GET /health/ready` en 503** — el motor de IA está degradado y
   `POST /api/v1/mensajes` está devolviendo fallback, pero fallback en sí
   no es un 5xx (ver `crewai_adapter.py`/`langchain_adapter.py` — el
   fallback es una respuesta 200 con contenido genérico). Si el error
   rate es real, buscar el 5xx específico en logs, no asumir que es esto.
2. **Backend de persistencia inalcanzable**: si `db_backend: "postgres"`
   (ver `/metrics/health`), confirmar que Postgres está arriba —
   `SQLiteConversationRepository`/`PostgresConversationRepository` lanzan
   excepción en cada `save_message`/`get_history` si la conexión falla, y
   eso sí es un 500 real en `POST /api/v1/mensajes`.
3. **`SANTISIMA_CLAVE_CIFRADO` inconsistente**: si cambió entre deploys
   sin migrar los datos ya cifrados, `_descifrar` lanza `InvalidToken` al
   leer historial existente — ver `ROLLBACK.md`, mismo invariante que
   `session_secret`.
4. **Excepción no manejada en un endpoint específico**: el traceback en
   `journalctl` lo dice; si es reproducible, es un bug de código que
   necesita un fix y deploy, no una mitigación operativa.

**Mitigación mientras se diagnostica**: si el error rate viene de una sola
causa aislable a un deploy reciente, ir directo a `ROLLBACK.md` en vez de
seguir depurando en producción — es más rápido revertir y diagnosticar con
calma después.

## `rate-limit-violations-spike`

**Alertas**: `SantisimaRateLimitSpike` (`santisima_rate_limit_exceeded_total`
> 1/s sostenido 10 min) y `SantisimaAuthFailuresSpike`
(`santisima_auth_failures_total{motivo="revocado"}` > 0.5/s sostenido 5
min) — agrupadas aquí porque ambas apuntan a la misma pregunta: ¿es abuso
real o un cliente legítimo mal configurado?

**Triage**:

```bash
# ¿Qué tipo de rate limit se está disparando — mensajes o registro de dispositivo?
curl -s localhost:8000/metrics | grep santisima_rate_limit_exceeded_total

# ¿Auth failures por qué motivo? (sin_token/firma_invalida/no_reconocido/revocado)
curl -s localhost:8000/metrics | grep santisima_auth_failures_total

# IPs/patrones en los logs de acceso (si el proxy los loguea; el proceso
# uvicorn en sí no loguea IP por request salvo error)
journalctl -u santisima -n 500 --no-pager | grep -i "429\|401\|403"
```

**Interpretación**:

- **`tipo="registro"` disparándose**: alguien está creando dispositivos
  en bucle contra `POST /api/v1/dispositivos` (sin auth, ver
  `Settings.rate_limit_registro_por_minuto` — límite por IP). Si viene de
  pocas IPs, es un bot/scraper; si viene de muchas, podría ser un cliente
  legítimo con retry-loop mal implementado (verificar con el equipo de
  frontend si hubo un deploy reciente del cliente).
- **`tipo="mensajes"` disparándose**: uso agresivo de dispositivos ya
  registrados contra el LLM — revisar si son pocos `device_id` repetidos
  (abuso puntual, candidato a revocar) o distribuido (posible ataque
  coordinado o un bug de cliente que reintenta sin backoff).
- **`motivo="revocado"` en auth failures**: un dispositivo ya revocado
  sigue insistiendo — normal en bajo volumen (cliente viejo con caché),
  sospechoso si es sostenido y de alto volumen (alguien probando si la
  revocación realmente corta el acceso, o un cliente en bucle de retry
  ciego a 401).
- **`motivo="firma_invalida"` o `"no_reconocido"` en volumen**: podría
  ser tráfico automatizado probando `device_token`s al azar, o el
  síntoma de un `session_secret` mismatch tras un deploy — ver
  `TROUBLESHOOTING.md#sesión-inválida-tras-un-deploy` antes de asumir
  abuso.

**Mitigación**:

```bash
# Revocar un dispositivo abusivo identificado (requiere API key de admin,
# ver Settings.api_keys):
curl -s -X POST localhost:8000/admin/dispositivos/<device_id>/revocar \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

Si el volumen es alto y distribuido (no aislable a unos pocos
`device_id`), la mitigación real es a nivel de proxy/firewall (bloquear
IPs/rangos) — fuera del alcance de este backend; coordinar con quien
administre Caddy/el firewall (ver `docs/despliegue.md`).

Si `rate_limit_por_minuto`/`rate_limit_registro_por_minuto` resultan
demasiado holgados para el patrón de abuso observado, bajarlos en `.env` y
reiniciar es una mitigación válida, pero revisar primero que no corte
tráfico legítimo (usuarios con reintentos por red inestable, ver el
comentario de `Settings.rate_limit_registro_por_minuto`).

## `llm-provider-outage`

**Síntoma**: DeepInfra (el único proveedor de LLM configurado, ver
`config.py` — `deepinfra_api_base`) está caído, degradado o con latencia
alta del lado del proveedor, no del backend.

**Triage**: confirmar que el problema es del lado del proveedor y no de
este backend:

```bash
time curl -s https://api.deepinfra.com/v1/openai/chat/completions \
  -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemma-4-31B-it-turbo","messages":[{"role":"user","content":"hola"}]}' \
  -o /dev/null -w 'http=%{http_code} tiempo=%{time_total}s\n'
```

- **Timeout, 5xx, o tiempo muy por encima de lo normal**: confirmado, es
  del proveedor.
- **200 rápido**: el problema no es DeepInfra — volver a
  `TROUBLESHOOTING.md#llm-degraded` o `#latencia-alta` para la causa real
  en este backend.

**No hay mitigación local para una caída real del proveedor** — no hay
proveedor secundario configurado ni fallback a otro modelo/API en el
código actual (`crear_servicio` en `__init__.py` apunta a un único
`deepinfra_api_base`). Mientras dure:

- El sistema ya degrada de forma controlada: `esta_degradado=True` hace
  que `POST /api/v1/mensajes` sirva respuestas de fallback genéricas en
  vez de fallar duro — esto es preferible a que cada mensaje cuelgue
  hasta `llm_timeout_segundos * (1 + llm_max_reintentos)` (~60s con los
  defaults) antes de responder.
- Comunicar el estado a usuarios si el canal existe (el frontend no tiene
  un banner de estado en el código actual — evaluar si vale la pena
  agregarlo si esto se repite).
- Monitorear `santisima_llm_degradado` y el propio status del proveedor
  (sin status page documentada en este repo — si DeepInfra publica una,
  documentarla aquí) hasta que se recupere.
- Al recuperarse el proveedor, `systemctl restart santisima` para que
  `esta_degradado` se reevalúe (no se auto-recupera en caliente, ver
  `HEALTH_CHECKS.md`).

**Postmortem**: si esto se repite con frecuencia, es la señal para
evaluar un segundo proveedor compatible con el endpoint OpenAI (el
adapter ya usa ese estándar vía LiteLLM/SDK OpenAI — agregar un fallback
de proveedor es un cambio de código, no de configuración, con el estado
actual del repo).

## Comunicación durante un incidente

Este repo no documenta un canal de status page ni un proceso formal de
comunicación a usuarios — si el equipo tiene uno (Slack, status page
externa), documentarlo aquí. Como mínimo: registrar en el canal interno
del equipo la alerta que disparó, la hora, y el link a la sección
correspondiente de este documento, para que el handoff a quien continúe
el triage no dependa de memoria.

## Cierre de incidente

- [ ] Causa raíz identificada y corregida (o mitigada con plan de
      seguimiento).
- [ ] `curl -s localhost:8000/health/ready` → 200 sostenido.
- [ ] `curl -s localhost:8000/metrics/health` → todos los campos en
      estado esperado (ver `HEALTH_CHECKS.md`).
- [ ] Alerta correspondiente ya no está `firing` en Prometheus/Alertmanager.
- [ ] Si hubo rollback (`ROLLBACK.md`) o cambio de config de emergencia,
      registrar qué se cambió y si falta revertirlo o hacerlo permanente.
- [ ] Postmortem breve si la severidad fue alta: qué pasó, por qué, qué
      cambia para que no vuelva a pasar igual.
