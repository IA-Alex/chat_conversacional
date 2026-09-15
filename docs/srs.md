# Especificación de Requisitos de Software (SRS)

**Referencia normativa:** ISO/IEC/IEEE 29148:2018.
**Sistema:** Backend conversacional de La Santísima Muerte.
**Estado:** Vivo — extraído del comportamiento real del código a fecha
2026-09-14; cualquier cambio de comportamiento debe actualizar este
documento y su [RTM](rtm.md) en el mismo cambio, no después.

Cada requisito tiene un identificador estable (`RF-nnn` funcional,
`RNF-nnn` no funcional) usado por [rtm.md](rtm.md) para trazabilidad.

## 1. Alcance

Backend HTTP que permite a un usuario final ("creyente"), identificado
por dispositivo (sin cuenta ni login), sostener una conversación con una
IA que personifica a "La Santísima Muerte", con memoria persistente entre
sesiones, dos motores de IA intercambiables, y controles de privacidad,
seguridad y cumplimiento normativo (ver [docs/compliance/](compliance/)).

**Fuera de alcance de este documento:** el cliente (app/web) que consume
esta API — no existe en este repositorio.

## 2. Requisitos funcionales

### Identidad y consentimiento

| ID | Requisito | Fuente en código |
|---|---|---|
| RF-001 | El sistema debe permitir registrar un dispositivo nuevo sin pedir nombre, email ni contraseña, devolviendo un `device_id` y un `device_token` firmado | `POST /api/v1/dispositivos` — [http_api.py](../src/la_santisima_conversacional/presentation/http_api.py) |
| RF-002 | El sistema debe rechazar cualquier request autenticado con un `device_token` inválido o fabricado | `verificar_dispositivo` |
| RF-003 | El sistema debe permitir revocar un dispositivo (solo administración), y todo request posterior de ese dispositivo debe rechazarse | `POST /admin/dispositivos/{id}/revocar` |
| RF-004 | El sistema debe registrar, por dispositivo, la versión exacta del aviso de privacidad que aceptó | `POST /api/v1/dispositivos/consentimiento` |
| RF-005 | El sistema debe rechazar el envío de un mensaje si el dispositivo no aceptó la versión **vigente** del aviso (una aceptación de una versión anterior no es válida) | `_exigir_consentimiento` |

### Conversación

| ID | Requisito | Fuente en código |
|---|---|---|
| RF-010 | El sistema debe emitir un `session_id` nuevo, atado criptográficamente al dispositivo que lo solicitó | `POST /api/v1/sesiones` |
| RF-011 | El sistema debe rechazar el uso de un `session_id` que no pertenezca al dispositivo autenticado | `_validar_propiedad_sesion` |
| RF-012 | El sistema debe generar una respuesta a un mensaje del creyente, en el mismo idioma del mensaje, con tono devocional en primera persona | `POST /api/v1/mensajes`, prompt principal (`flow.json` / `langchain_adapter.py`) |
| RF-013 | El sistema debe ofrecer la misma funcionalidad en modo streaming (fragmentos incrementales) | `POST /api/v1/mensajes/stream` |
| RF-014 | El sistema debe clasificar cada mensaje como vacío, incompleto o válido, y responder de forma proporcional (invitación breve para vacío/incompleto, respuesta completa para válido) | `detectar_intencion` / `enrutar_por_intencion` |
| RF-015 | El sistema debe mantener un resumen de memoria persistente de la conversación, actualizado en segundo plano tras cada intercambio | `actualizar_memoria` / `persistir_resumen` |
| RF-016 | El sistema debe limitar el contexto enviado al modelo a los últimos N mensajes (ventana deslizante configurable) | `aplicar_sliding_window` |
| RF-017 | El sistema debe permitir al usuario borrar su historial y resumen de una sesión en cualquier momento | `POST /api/v1/sesiones/{id}/reiniciar` |
| RF-018 | Si el motor principal falla o produce una respuesta inválida, el sistema debe degradar a una respuesta de fallback en el mismo tono, sin exponer el error al usuario | `validar_o_usar_fallback`, `_fallback_responder` |

### Operación y privacidad

| ID | Requisito | Fuente en código |
|---|---|---|
| RF-020 | El sistema debe exponer el contenido del aviso de privacidad y su versión vigente sin requerir autenticación | `GET /privacidad` |
| RF-021 | El sistema debe exponer endpoints de liveness y readiness que reflejen si el motor de IA está operando en modo degradado | `GET /health`, `GET /health/ready` |
| RF-022 | El sistema debe purgar automáticamente los mensajes que superen el periodo de retención configurado | `scripts/purgar_retencion.py`, `purgar_expirados` |

## 3. Requisitos no funcionales

| ID | Requisito | Verificación |
|---|---|---|
| RNF-001 | El contenido de los mensajes debe cifrarse en reposo (Fernet) | `SANTISIMA_CLAVE_CIFRADO`, `SQLiteConversationRepository`/`PostgresConversationRepository` |
| RNF-002 | Cada dispositivo debe tener su propio cupo de mensajes por minuto, independiente de otros dispositivos | `LimitadorTasa` / `LimitadorTasaRedis` |
| RNF-003 | Ninguna llamada al proveedor de IA debe bloquear indefinidamente: debe tener timeout y reintentos configurables | `llm_timeout_segundos`, `llm_max_reintentos` |
| RNF-004 | El proceso debe fallar al arrancar (no en el primer request) si falta configuración requerida (key del proveedor de IA, secreto de sesión fuera de debug) | `Settings`, `validar_produccion` |
| RNF-005 | El sistema debe soportar escalar a más de una instancia sin duplicar información de rate limit ni de conversación | `usar_postgres`, `usar_redis_rate_limit` |
| RNF-006 | El motor de IA debe ser intercambiable (CrewAI o LangChain) sin cambiar el comportamiento observable para el creyente | `ServicioLaSantisima` (puerto), paridad documentada en [architecture.md](architecture.md) |
| RNF-007 | El sistema no debe exigir instalar el motor CrewAI (dependencia pesada, opcional) para poder correr con LangChain | extras opcionales en `pyproject.toml`, mock en `conftest.py` |
| RNF-008 | Cambiar de proveedor de modelo de IA no debe requerir cambios en `CrewAIAdapter` ni `LangChainAdapter` | traducción de credenciales en `crear_servicio` (ver [ADR-0003](adr/0003-migracion-deepinfra.md)) |

## 4. Restricciones y decisiones de producto no negociables en esta iteración

- El sistema mantiene la personificación en primera persona sin
  autoidentificarse como IA dentro del flujo conversacional — decisión de
  producto confirmada, registrada en
  [docs/compliance/gobernanza-ia.md](compliance/gobernanza-ia.md).
- No existe, a la fecha de este documento, un protocolo de detección o
  derivación ante crisis emocional grave — riesgo identificado y
  formalmente diferido (ver el mismo documento, §4).

## 5. Trazabilidad

Cada `RF-nnn`/`RNF-nnn` de este documento debe tener una fila en
[rtm.md](rtm.md) que lo vincule con el módulo que lo implementa y el/los
test(s) que lo verifican. Un requisito sin fila en la RTM se considera no
verificado, aunque el código lo cumpla.
