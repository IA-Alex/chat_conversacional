# Evaluación de Impacto en la Protección de Datos (DPIA/EIPD)

**Sistema evaluado:** La Santísima Muerte — backend conversacional
**Referencia normativa:** ISO/IEC 29134:2017 (guía de EIPD), alineado con
Art. 35 GDPR y Art. 21 LFPDPPP (México) como referencias de buena práctica.
**Jurisdicción asumida:** México, por defecto — el proyecto está en fase
pre-lanzamiento sin jurisdicción confirmada. **Debe revalidarse esta DPIA
en cuanto se confirme el país/países de lanzamiento**, ya que el marco
legal aplicable (LFPDPPP, GDPR, CCPA, u otro) cambia obligaciones
concretas (plazos de respuesta a derechos ARCO, notificación de brechas,
transferencias internacionales).
**Estado:** Vivo — debe revisarse ante cualquier cambio material del
sistema (nuevo proveedor de IA, nuevo tipo de dato recolectado, cambio de
jurisdicción, lanzamiento público).
**Última actualización:** 2026-09-14.

---

## 1. Descripción del tratamiento

| Campo | Detalle |
|---|---|
| Responsable del tratamiento | Pendiente de definir formalmente (persona física/moral operadora del servicio) |
| Finalidad | Proveer una experiencia conversacional devocional con una entidad personificada ("La Santísima Muerte") |
| Base legal propuesta | Consentimiento explícito y diferenciado para categoría especial de dato (ver §4) |
| Datos tratados | Ver §2 |
| Motor de procesamiento | DeepInfra — `google/gemma-4-31B-it-turbo` (chat), `google/gemma-4-26B-A4B-it` (resumen), `deepseek-ai/DeepSeek-V4-Flash-0731` (clasificación), vía adaptadores CrewAI y LangChain ([config.py](../../src/la_santisima_conversacional/config.py)) |
| Almacenamiento | SQLite u opcionalmente Postgres ([.env.example](../../.env.example)) |
| Cifrado en reposo | Sí, Fernet, clave en `SANTISIMA_CLAVE_CIFRADO` |
| Retención | 90 días por defecto, configurable (`SANTISIMA_RETENCION_DIAS`), purga vía [scripts/purgar_retencion.py](../../scripts/purgar_retencion.py) |
| Identidad de usuario | `device_token` sin login, sin dato civil obligatorio ([docs/privacidad.md](../privacidad.md)) |

## 2. Inventario de datos y clasificación

| Dato | Categoría | Sensibilidad |
|---|---|---|
| Contenido del mensaje del creyente | Dato personal, potencialmente **categoría especial** (creencia religiosa, salud emocional, orientación de vida) | Alta |
| Resumen de memoria persistente (temas, emociones, peticiones) | Derivado del anterior — hereda su sensibilidad | Alta |
| `device_id` / `session_id` | Identificador técnico opaco, no vinculado a identidad civil | Media (pseudonimizado) |
| Marca de tiempo por mensaje | Metadato técnico | Baja |
| IP de origen (si se registra a nivel de infraestructura/proxy) | **No confirmado si se persiste** — requiere verificación técnica antes de cerrar esta DPIA | Por determinar |

**Nota crítica:** a diferencia de un dato sensible declarado explícitamente
por el usuario (ej. un formulario que pregunta religión), aquí la
categoría especial de dato **emerge del contenido libre del mensaje**, no
de un campo estructurado. Esto significa que el sistema no puede evitar
recibir dato sensible — el diseño de privacidad debe asumir que **todo
mensaje es potencialmente sensible por defecto**.

## 3. Necesidad y proporcionalidad

- El tratamiento del contenido completo del mensaje es necesario para la
  finalidad (generar una respuesta contextual coherente) — no hay forma de
  ofrecer el servicio sin procesar el texto.
- El resumen de memoria persistente es necesario para dar continuidad
  entre sesiones, tal como se documenta en [architecture.md](../architecture.md).
- **Punto de atención:** no existe hoy un mecanismo que permita al usuario
  optar por una sesión *sin* memoria persistente (modo "conversación
  efímera"). Se recomienda evaluarlo como control de minimización
  adicional, sin que esto implique cambiar el comportamiento por defecto.

## 4. Base legal para categoría especial de dato

Dado que el contenido puede revelar creencias religiosas y estado
emocional/psicológico:

- Se requiere **consentimiento explícito, específico y diferenciado** del
  consentimiento general de uso — no basta un aviso de privacidad general
  aceptado implícitamente por el primer uso.
- **Estado: implementado en el backend (2026-09-14).**
  `POST /api/v1/dispositivos/consentimiento` registra, por dispositivo, la
  versión exacta del aviso aceptada (timestamp + `version`), y
  `POST /api/v1/mensajes` / `.../mensajes/stream` devuelven `403
  consentimiento_requerido` si el dispositivo no aceptó la versión vigente
  (`Settings.aviso_privacidad_version`) — ver
  `_exigir_consentimiento` en
  [http_api.py](../../src/la_santisima_conversacional/presentation/http_api.py).
  El saludo de bienvenida que el cliente muestra junto al recuadro de
  aceptación no pasa por el motor de IA ni se persiste, así que no hay
  ventana de tratamiento sin consentimiento.
- **Pendiente, fuera de este repositorio backend:** el cliente (app/web)
  debe mostrar el recuadro de aceptación y llamar a ese endpoint antes de
  habilitar el envío del primer mensaje — el backend ya bloquea el
  resultado de no hacerlo, pero no puede obligar a que el cliente muestre
  la pantalla correcta.

## 5. Riesgos identificados

| # | Riesgo | Probabilidad | Impacto | Mitigación existente | Mitigación pendiente |
|---|---|---|---|---|---|
| R1 | Fuga de contenido devocional/emocional sensible por brecha de BD | Media | Alto | Cifrado en reposo (Fernet), retención 90 días | Rotación de clave documentada, plan de respuesta a incidentes formal |
| R2 | Re-identificación de usuario vía patrones de contenido pese a `device_token` opaco | Baja | Medio | Sin dato civil recolectado | — |
| R3 | Usuario en crisis emocional recibe respuesta puramente devocional sin derivación a ayuda profesional | Media-Alta | Muy alto | Ninguna — el clasificador detecta la emoción `"desesperacion"` pero no la enruta a ningún tratamiento especial ([flow.json](../../src/la_santisima_conversacional/infrastructure/flow.json)) | **Riesgo formalmente identificado y aceptado temporalmente por decisión de producto** — ver [gobernanza-ia.md §Registro de aceptación de riesgo](gobernanza-ia.md#registro-de-aceptación-de-riesgo) para el detalle y la fecha de revisión obligatoria |
| R4 | Envío del contenido íntegro del mensaje a un proveedor externo (DeepInfra) sin que el usuario lo perciba con claridad | Media | Medio | Mencionado en [docs/privacidad.md](../privacidad.md) | Falta confirmar visibilidad real en el cliente (no solo en el endpoint `GET /privacidad`) |
| R5 | Ausencia de consentimiento explícito diferenciado para categoría especial de dato | Baja (backend implementado) | Alto | Gate de consentimiento por versión en el backend (ver §4) | Confirmar que el cliente (app/web) realmente muestra el recuadro y llama al endpoint antes del primer mensaje — fuera del alcance de este repositorio |
| R6 | Falta de proceso formal para atender derechos ARCO/DSAR dentro de plazo legal | Alta | Medio | Borrado manual vía endpoint de sesión | Definir SLA y responsable de atención de solicitudes |

## 6. Conclusión de la evaluación

El sistema **no debe lanzarse públicamente** sin confirmar que el cliente
efectivamente usa el gate de consentimiento ya implementado en el backend
(R5) y sin que el responsable del tratamiento haya firmado el registro de
aceptación de riesgo de R3 (ver [gobernanza-ia.md](gobernanza-ia.md)). El
resto de riesgos (R1, R2, R4, R6) son gestionables en paralelo al
lanzamiento con las mitigaciones pendientes trackeadas.

**Firma de responsable del tratamiento:** _pendiente — requiere que el
operador del negocio, no el equipo técnico, asuma formalmente esta
evaluación._
