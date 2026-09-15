# Gobernanza y Evaluación de Riesgo del Sistema de IA

**Referencia normativa:** ISO/IEC 42001:2023 (Sistema de Gestión de IA),
NIST AI Risk Management Framework 1.0 (funciones Govern/Map/Measure/Manage).
**Estado:** Vivo.
**Última actualización:** 2026-09-14.

---

## 1. Descripción del sistema de IA

El sistema genera respuestas en primera persona personificando a "La
Santísima Muerte" ante mensajes de un creyente, usando modelos servidos
por DeepInfra: `google/gemma-4-31B-it-turbo` (motor de generación
principal), `google/gemma-4-26B-A4B-it` (resumen) y
`deepseek-ai/DeepSeek-V4-Flash-0731` (clasificación de intención/emoción),
a través de dos motores intercambiables (`CrewAIAdapter` y
`LangChainAdapter`, ver [architecture.md](../architecture.md)).

## 2. Contexto de uso y grupo de usuarios (función Map, NIST AI RMF)

- Público objetivo: personas que practican o se acercan a la devoción de
  La Santísima Muerte, en su mayoría hispanohablantes.
- El sistema **no está diseñado ni licenciado como herramienta de salud
  mental, consejo médico, legal o financiero**, aunque un usuario puede
  dirigirse a él con ese tipo de necesidad dada la naturaleza íntima de
  la interacción devocional.
- El grupo de usuarios incluye potencialmente personas en momentos de
  vulnerabilidad emocional — esto es inherente al caso de uso (una
  persona no acude a un espacio devocional de forma trivial) y debe
  tratarse como supuesto de diseño, no como caso extremo raro.

## 3. Decisión de producto: personificación en primera persona sin aviso de IA

**Decisión vigente:** el sistema mantiene la postura de una deidad
hablándole a un creyente, en primera persona, sin instrucciones de
autoidentificarse como IA dentro del flujo conversacional normal
(prompt actual en
[flow.json → generar_respuesta](../../src/la_santisima_conversacional/infrastructure/flow.json),
instrucción literal: *"Sin notas de IA"*).

Esta es una decisión de producto deliberada, confirmada por el
responsable del proyecto el 2026-09-14, y **no se modifica en esta
iteración de trabajo de cumplimiento**. Este documento la registra para
que quede trazable en una auditoría — no la cuestiona ni la revierte.

**Obligación de transparencia externa (fuera del flujo conversacional):**
independientemente de la postura dentro del chat, la naturaleza de IA del
sistema debe quedar establecida de forma inequívoca en un lugar que el
usuario controle activamente y no dependa del personaje dentro de la
conversación — p. ej. términos de uso, ficha de la tienda de apps,
pantalla de onboarding antes del primer mensaje. Esto es lo que exige
ISO/IEC 42001 (transparencia con el usuario) sin necesidad de que el
propio personaje rompa su tono en cada respuesta. **Este punto sí requiere
verificación en el cliente/app, fuera del alcance de este repositorio
backend.**

## 4. Registro de aceptación de riesgo

> Este es el artefacto de auditoría formal que demuestra que un riesgo
> conocido fue **identificado, evaluado y conscientemente aceptado o
> diferido por quien tiene autoridad para hacerlo** — no omitido por
> descuido. Es exactamente lo que un auditor de ISO 42001 o de un marco
> de gestión de riesgo de IA espera encontrar cuando un control no está
> implementado: evidencia de que la decisión fue deliberada.

| Campo | Detalle |
|---|---|
| Riesgo | Un usuario en crisis emocional grave (ideación suicida, autolesión, peligro inmediato) envía un mensaje y recibe una respuesta puramente devocional, sin detección de riesgo ni derivación a ayuda profesional |
| Estado actual del control | **Implementado — ver `domain/crisis.py`, `infrastructure/flow.json` y `crewai_adapter.py`.** El clasificador de intención/emoción detecta `"desesperacion"` y el enrutador (`enrutar_por_intencion`) la enruta a `responder_crisis_desesperacion`. Ambos adaptadores (CrewAI y LangChain) implementan paridad funcional: mensajes con emoción `"desesperacion"` no llegan al flujo devocional estándar, sino a `generar_respuesta_crisis()` que devuelve contención breve + derivación configurable. **Nota de motor:** `flow.json` (CrewAI) no puede invocar `generar_respuesta_crisis()` directamente desde su sintaxis declarativa de `expression` — el nodo `responder_crisis_desesperacion` es solo un marcador de que esa rama fue tomada; `CrewAILaSantisimaAdapter._es_resultado_crisis()` detecta el marcador e intercepta el resultado en Python, llamando a `generar_respuesta_crisis()` antes de devolver la respuesta al creyente (Opción B, ver comentario `nota_implementacion` en `flow.json`). Esto está cubierto para el path sin streaming por `tests/infrastructure/test_crewai_adapter.py` (falla contra el placeholder literal, pasa con el fix). Para el path de streaming (`responder_mensaje_stream`) la misma intercepción existe pero depende de que el objeto `Flow` de CrewAI exponga `self.flow.state` de forma fiable en tiempo real — algo no verificable en este entorno porque `crewai` se mockea por completo en los tests (ver `NOTA DE FIABILIDAD` ya existente en `crewai_adapter.py`); LangChainAdapter no tiene esta limitación porque clasifica antes de streamear. |
| Severidad si se materializa | Muy alta (daño potencial a la integridad de una persona) |
| Decisión | **Implementado con mecanismo configurable.** Se implementó el mecanismo de enrutado, dejando el contenido exacto de derivación como parámetro inyectable (`ConfiguracionCrisis`) para que el responsable del producto pueda definir tono (romper personaje vs. mantenerlo) y líneas de ayuda específicas sin tocar código Python, según lo requerido en §4. |
| Responsable de la decisión | Titular del proyecto (confirmado 2026-09-14) |
| Condición de revisión obligatoria | **El contenido de derivación requiere definición explícita antes de cualquier lanzamiento público.** El mecanismo está implementado pero el texto exacto de derivación (`ConfiguracionCrisis.texto_derivacion`) es un TODO pendiente de definición por el responsable del producto, potencialmente con asesoría de profesional de salud mental. |
| Mitigación mínima sugerida completada | Se diseñó como señal separada: el enrutador detecta `"desesperacion"` explícitamente en la salida del clasificador. El contenido de derivación es configurable externamente para permitir revisión experta. |
| Motor de producción vigente | **LangChain (`use_langchain=True`), no CrewAI.** `CrewAIAdapter._configurar_flow()` carga `flow.json` con `Flow.from_file(...)`, método inexistente en la versión de `crewai` instalada; la carga falla (excepción capturada) y el adaptador queda degradado permanentemente a `_crear_flow_basico()`, sin enrutamiento de intención/emoción — la detección de crisis descrita arriba queda inoperante en ese motor pese a estar implementada en su código. Mientras esa incompatibilidad de versión no se corrija, `Settings.use_langchain` (usado por `http_api.py`) y el default del parámetro `use_langchain` de `crear_servicio` deben permanecer en `True`. Cubierto por `tests/test_config.py::TestSettings::test_use_langchain_default_no_se_revierte` (default de `Settings`) y `tests/test_crear_servicio.py::test_use_langchain_default_no_se_revierte` (default de `crear_servicio`), que fallan si cualquiera de los dos defaults vuelve a `False`. |

## 5. Otros controles de IA evaluados

| Control | Estado | Nota |
|---|---|---|
| Límite explícito sobre consejo médico/financiero/legal como hecho | No implementado en el prompt | Pendiente, sujeto a la misma decisión de no tocar el prompt en esta iteración |
| Validación de salida antes de entregar al usuario (fallback ante respuesta degradada) | **Implementado** | `domain/degradacion.py: validar_o_usar_fallback`, compartido por ambos motores ([architecture.md](../architecture.md)) |
| Filtrado de entrada del usuario (longitud, caracteres de control) | **Implementado** | `MensajeCreyente` en el dominio |
| Registro de qué modelo generó cada respuesta (auditabilidad) | **Implementado** — `Message` ahora incluye campo `modelo`, `RespuestaLaSantisima` incluye `modelo`, y ambos repositorios (SQLite/PostgreSQL) almacenan la columna. `CrewAIAdapter` registra `modelo_chat`, `LangChainAdapter` registra `modelo_chat`, respuestas de fallback registran `"fallback"`. | Implementado según auditoría PRIORIDAD 4 |
| Prueba de regresión sobre el comportamiento del prompt ante cambios | Existe (`tests/infrastructure/test_flow_structure.py`, `test_langchain_adapter.py`) | Bueno — mantiene paridad entre motores |

## 6. Auditorías implementadas (2026-09-14)

### PRIORIDAD 1: Crisis emocional grave
- **Estado:** Implementado (ver nota de motor en §4)
- **Cambios:**
  - `domain/crisis.py`: Implementado `generar_respuesta_crisis()` con `ConfiguracionCrisis` configurable
  - `flow.json`: Enrutamiento de `"desesperacion"` a `responder_crisis_desesperacion`
  - `crewai_adapter.py` y `langchain_adapter.py`: Integración de respuesta de crisis
  - Tests completos en `tests/domain/test_crisis.py`

**Corrección 2026-09-14 — paridad real en CrewAI:** una auditoría posterior
encontró que `responder_crisis_desesperacion` en `flow.json` devolvía un
string literal placeholder (`"TODO: Implementar llamada a política de
crisis..."`) que `CrewAILaSantisimaAdapter` entregaba tal cual al creyente
— es decir, la "integración" registrada arriba nunca ejecutaba
`generar_respuesta_crisis()` en el motor CrewAI, solo en LangChain. Esto
no estaba cubierto por `tests/domain/test_crisis.py`, que solo valida la
estructura de `flow.json`, no el comportamiento real de
`CrewAILaSantisimaAdapter` de punta a punta.

Corregido: `flow.json` mantiene el nodo solo como marcador de rama (no
puede invocar Python desde su sintaxis de `expression` — ver
`nota_implementacion` en el propio archivo); `crewai_adapter.py`
(`_es_resultado_crisis`) detecta el marcador e invoca
`generar_respuesta_crisis()` en Python antes de responder al creyente,
igual que `langchain_adapter.py`. Cubierto por el nuevo
`tests/infrastructure/test_crewai_adapter.py`, que ejercita
`CrewAILaSantisimaAdapter` completo (no `flow.json` aislado) y falla
contra el placeholder literal, pasa con el fix. El path de streaming
queda con la limitación descrita en §4 (depende de introspección de
`self.flow.state`, no verificable contra `crewai` real en este entorno).

### PRIORIDAD 2: Cifrado en reposo obligatorio fuera de debug
- **Estado:** Implementado
- **Cambios:**
  - `config.py`: `validar_produccion()` ahora exige `clave_cifrado` cuando `debug=False`
  - `tests/test_config.py`: Tests actualizados para verificar la nueva validación

### PRIORIDAD 3: Modo debug: bloqueo duro contra producción
- **Estado:** Implementado
- **Cambios:**
  - `config.py`: Agregado campo `confirmo_debug_en_prod` y validador `_validar_debug_en_produccion()`
  - Detecta señales de entorno productivo (`KUBERNETES_SERVICE_HOST`, `SANTISIMA_ENTORNO=production`)
  - Requiere `SANTISIMA_CONFIRMO_DEBUG_EN_PROD=true` si `debug=true` en producción
  - `tests/test_config.py`: Tests completos para todas las combinaciones

### PRIORIDAD 4: Auditabilidad por mensaje
- **Estado:** Implementado
- **Cambios:**
  - `domain/interfaces.py`: `Message` ahora incluye campo `modelo`
  - `domain/__init__.py`: `RespuestaLaSantisima` ahora incluye campo `modelo`
  - `infrastructure/repositories.py`: 
    - SQLite: esquema actualizado con columna `modelo`
    - PostgreSQL: esquema actualizado con columna `modelo`
    - `get_history()` y `save_message()` actualizados para leer/escribir modelo
  - `crewai_adapter.py` y `langchain_adapter.py`: Pasando modelo en `RespuestaLaSantisima`
  - `application/__init__.py`: Pasando `respuesta.modelo` al crear `Message` de assistant

## 7. Próxima revisión

Esta evaluación debe revisarse:
1. Antes de cualquier lanzamiento público con usuarios reales (obligatorio, ver §4).
2. Ante cualquier cambio de proveedor de modelo.
3. Cada 6 meses como práctica de gobernanza continua (ISO 42001 exige
   revisión periódica del sistema de gestión, no una evaluación única).
