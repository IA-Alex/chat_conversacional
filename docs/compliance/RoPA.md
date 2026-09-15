# Registro de Actividades de Tratamiento (RoPA)

**Referencia normativa:** Art. 30 GDPR (formato de referencia adoptado
como buena práctica internacional), ISO/IEC 27701:2019 §7.2.8, Art. 22
LFPDPPP (México, "registro de bases de datos" — verificar exigibilidad
exacta según jurisdicción final).
**Estado:** Vivo — cada actividad de tratamiento nueva debe añadirse aquí
antes de implementarse en código, no después.
**Última actualización:** 2026-09-14.

---

## Actividad 1 — Conversación devocional con el creyente

| Campo | Valor |
|---|---|
| Responsable del tratamiento | Pendiente de definir (ver [DPIA.md](DPIA.md)) |
| Encargado del tratamiento (procesador) | DeepInfra (proveedor del modelo de lenguaje, vía su endpoint compatible con la API de OpenAI) |
| Finalidad | Generar respuestas conversacionales personalizadas en el rol de "La Santísima Muerte" |
| Base legal | Consentimiento explícito (categoría especial de dato — ver DPIA §4) |
| Categorías de titulares | Usuarios finales de la app/web ("creyentes") |
| Categorías de datos | Contenido de mensaje, resumen de memoria persistente, emoción/intención clasificada, `device_id`, `session_id`, timestamp |
| Categoría especial de dato | Sí — creencia religiosa y estado emocional, inferidos del contenido libre |
| Destinatarios | DeepInfra (subprocesador, vía API); los modelos usados (Gemma 4 de Google, DeepSeek) son ejecutados por DeepInfra como infraestructura de inferencia — Google/DeepSeek no reciben el dato directamente, DeepInfra sirve los pesos del modelo en su propia infraestructura |
| Transferencias internacionales | Sí, a infraestructura de DeepInfra — **pendiente de confirmar la(s) región(es) de procesamiento exacta(s) y el mecanismo de transferencia aplicable según jurisdicción final** (ej. cláusulas contractuales tipo si aplica GDPR) |
| Plazo de conservación | 90 días por defecto (`SANTISIMA_RETENCION_DIAS`), purgado automáticamente por [scripts/purgar_retencion.py](../../scripts/purgar_retencion.py); borrado inmediato disponible vía `POST /api/v1/sesiones/{session_id}/reiniciar` |
| Medidas de seguridad | Cifrado en reposo (Fernet), autenticación por `device_token` firmado HMAC, rate limiting, API keys de administración separadas del cliente final ([architecture.md](../architecture.md)) |
| Fuente del dato | Directamente del titular (mensaje escrito por el usuario) |

## Actividad 2 — Clasificación automática de intención y emoción

| Campo | Valor |
|---|---|
| Responsable del tratamiento | Mismo que Actividad 1 |
| Encargado del tratamiento | DeepInfra (modelo clasificador, `modelo_clasificador`) |
| Finalidad | Determinar si el mensaje es válido/vacío/incompleto y detectar la emoción predominante, para enrutar la respuesta |
| Base legal | Misma que Actividad 1 (accesoria a la finalidad principal) |
| Categorías de datos | Contenido del mensaje actual (no se envía historial completo a este paso) |
| Decisión automatizada relevante | Sí — el resultado de esta clasificación determina qué tipo de respuesta recibe el usuario. **No constituye una decisión con efecto legal o significativo comparable** en el sentido de Art. 22 GDPR (no afecta derechos, acceso a servicios o consecuencias jurídicas), por lo que no activa las garantías reforzadas de ese artículo — pero debe re-evaluarse si en el futuro se automatizan decisiones con consecuencias reales (ej. bloqueo de cuenta, derivación a terceros) |
| Plazo de conservación | El resultado de la clasificación no se persiste de forma independiente — vive únicamente en el ciclo de ejecución de cada turno |

## Actividad 3 — Administración y moderación (endpoints `/admin/*`)

| Campo | Valor |
|---|---|
| Responsable del tratamiento | Operador del servicio |
| Finalidad | Revocar dispositivos abusivos, operación del servicio |
| Base legal | Interés legítimo del responsable (seguridad del servicio) |
| Categorías de titulares | Usuarios cuyo dispositivo es investigado/revocado |
| Categorías de datos | `device_id`, metadatos de uso (no contenido de mensajes, salvo que se consulte explícitamente para investigar abuso) |
| Acceso | Restringido a API key de administración, nunca distribuida en el cliente ([architecture.md §Backend HTTP](../architecture.md)) |

---

## Subprocesadores

| Subprocesador | Rol | Datos a los que accede |
|---|---|---|
| DeepInfra | Generación de respuestas y clasificación (modelos Gemma 4 de Google y DeepSeek servidos como inferencia por DeepInfra) | Contenido del mensaje, resumen de memoria, historial en ventana deslizante |
| (Infraestructura de hosting — pendiente de definir) | Alojamiento de base de datos y backend | Todo el dato en reposo, ya cifrado a nivel de aplicación |

**Pendiente:** una vez definido el proveedor de hosting/nube, añadirlo
aquí con su rol y confirmar si firma un DPA (Data Processing Agreement)
o equivalente.
