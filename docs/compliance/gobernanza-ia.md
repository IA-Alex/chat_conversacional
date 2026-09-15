# Gobernanza y Evaluación de Riesgo del Sistema de IA

**Referencia normativa:** ISO/IEC 42001:2023 (Sistema de Gestión de IA),
NIST AI Risk Management Framework 1.0 (funciones Govern/Map/Measure/Manage).
**Estado:** Vivo.
**Última actualización:** 2026-09-15.

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
| Estado actual del control | **Retirado (2026-09-15) — ver "Reversión 2026-09-15" en §6.** El enrutado especial por emoción `"desesperacion"` (antes: `domain/crisis.py`, `infrastructure/flow.json`, `crewai_adapter.py`, `langchain_adapter.py`) fue eliminado del código. Ya no existe ninguna respuesta fija que intercepte el flujo devocional estándar; todo mensaje, incluida cualquier emoción clasificada como `"desesperacion"`, se responde vía el LLM igual que cualquier otro. El clasificador sigue etiquetando `"desesperacion"` como valor de emoción (se usa para intensidad visual en el frontend), pero esa etiqueta ya no dispara ninguna lógica de negocio distinta. |
| Severidad si se materializa | Muy alta (daño potencial a la integridad de una persona) — **sigue siendo la severidad real del riesgo subyacente; retirar el control no reduce el riesgo, lo vuelve a dejar sin mitigación dedicada.** |
| Decisión | **Retiro deliberado del control (2026-09-15).** Motivo registrado: el control tal como estaba implementado disparaba con demasiada frecuencia ante angustia cotidiana (p. ej. pérdida de empleo, estrés económico) — no solo ante señales de riesgo vital — y en cada disparo devolvía un texto idéntico y no contextual ("Escucho tu dolor profundo... Te abrazo con mi manto de luz" + línea de prevención de suicidio), lo que un usuario reportó como "no escucha, dice lo mismo para todo". Se ofrecieron al responsable del producto tres alternativas (mantener tal cual, afinar el umbral del clasificador manteniendo la derivación, o retirar el control por completo) explicando explícitamente que la tercera apaga la salvaguarda descrita en este documento; se eligió la tercera con conocimiento de esa implicación. |
| Responsable de la decisión | Titular del proyecto (decisión original: 2026-09-14; retiro: 2026-09-15) |
| Condición de revisión obligatoria | **Sin control de crisis activo, el riesgo original de §4 vuelve a estar sin mitigar.** Antes de cualquier lanzamiento público con usuarios reales, el responsable del producto debe decidir explícitamente si reintroduce algún mecanismo de detección de riesgo vital (idealmente uno que distinga angustia cotidiana de riesgo real, con asesoría de un profesional de salud mental) o si asume el riesgo tal como queda descrito arriba. Esto no puede quedar implícito ni derivarse de la ausencia de código. |
| Mitigación mínima sugerida completada | Ninguna vigente — ver condición de revisión obligatoria. |
| Motor de producción vigente | **LangChain (`use_langchain=True`), no CrewAI.** `CrewAIAdapter._configurar_flow()` carga `flow.json` con `Flow.from_file(...)`, método inexistente en la versión de `crewai` instalada; la carga falla (excepción capturada) y el adaptador queda degradado permanentemente a `_crear_flow_basico()`, sin enrutamiento de intención/emoción. Mientras esa incompatibilidad de versión no se corrija, `Settings.use_langchain` (usado por `http_api.py`) y el default del parámetro `use_langchain` de `crear_servicio` deben permanecer en `True`. Cubierto por `tests/test_config.py::TestSettings::test_use_langchain_default_no_se_revierte` (default de `Settings`) y `tests/test_crear_servicio.py::test_use_langchain_default_no_se_revierte` (default de `crear_servicio`), que fallan si cualquiera de los dos defaults vuelve a `False`. |

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

### Reversión 2026-09-15: retiro del enrutado de crisis emocional grave
- **Estado:** Retirado — ver registro actualizado en §4.
- **Motivo:** el mecanismo implementado el 2026-09-14 (PRIORIDAD 1 arriba)
  disparaba ante angustia cotidiana — mensajes sobre pérdida de empleo,
  problemas económicos — no solo ante señales de riesgo vital, porque el
  criterio de disparo era únicamente que el clasificador etiquetara la
  emoción del mensaje como `"desesperacion"`, sin distinguir grado de
  riesgo. Cada disparo devolvía un texto idéntico y no contextual
  (`ConfiguracionCrisis` por defecto: "Escucho tu dolor profundo... Te
  abrazo con mi manto de luz" + línea de prevención de suicidio),
  reportado por un usuario como que el sistema "no escucha, dice lo mismo
  para todo".
- **Decisión:** se presentaron tres alternativas al titular del proyecto
  (mantener el control tal cual; afinar el umbral del clasificador para
  distinguir angustia cotidiana de riesgo vital real, conservando la
  derivación; retirar el control por completo), señalando explícitamente
  que la tercera apaga la salvaguarda contra ideación suicida/autolesión
  descrita en §4. Se eligió la tercera opción con esa implicación
  explícita.
- **Cambios:**
  - `domain/crisis.py`: eliminado (`generar_respuesta_crisis()`,
    `ConfiguracionCrisis`) junto con `tests/domain/test_crisis.py`.
  - `langchain_adapter.py`: eliminadas las ramas `elif emocion ==
    "desesperacion"` en `responder_mensaje()` y
    `responder_mensaje_stream()` — la emoción `"desesperacion"` ahora cae
    en la rama por defecto (`_chain_principal`), igual que cualquier otra
    emoción.
  - `crewai_adapter.py`: eliminados `_es_resultado_crisis()`,
    `_METODO_CRISIS` y las ramas equivalentes en ambos métodos.
  - `flow.json`: eliminado el nodo `responder_crisis_desesperacion` y la
    rama `crisis_desesperacion` de `enrutar_por_intencion` (tanto en su
    `expr` como en su `emit`) — el router ahora solo distingue
    `mensaje_vacio` / `mensaje_incompleto` / `mensaje_valido`.
  - `tests/infrastructure/test_crewai_adapter.py`: eliminada la clase
    `TestIntegracionCrewAICrisis` (probaba el mecanismo retirado);
    agregado `test_desesperacion_no_recibe_enrutado_especial` en
    `TestEmocionCrewAI` para documentar el comportamiento nuevo.
  - `tests/infrastructure/test_langchain_adapter.py`: agregado
    `test_desesperacion_no_recibe_enrutado_especial`, mismo propósito.
  - El clasificador (`_PROMPT_CLASIFICADOR` / `detectar_intencion` en
    `flow.json`) sigue devolviendo `"desesperacion"` como valor de
    emoción posible — no se tocó, porque el frontend lo usa para
    intensidad visual (ver `index_santa_flat.html`, estado `crisis` de la
    niebla). Solo se eliminó qué hace el *backend* con ese valor.
- **Verificado en vivo (no solo en tests):** con el backend real corriendo
  contra DeepInfra, el mensaje *"Perdí mi trabajo esta semana y no sé cómo
  voy a pagar la renta"* — que antes del retiro devolvía exactamente el
  texto fijo de `ConfiguracionCrisis` — ahora genera una respuesta del LLM
  que reconoce los detalles concretos del mensaje y termina con una
  pregunta de seguimiento genuina, sin repetir la fórmula "te abrazo con
  mi manto de luz".
- **Pendiente (ver condición de revisión obligatoria en §4):** el riesgo
  original de §4 (crisis emocional grave sin detección) vuelve a estar
  sin mitigación dedicada. No implementar nada nuevo aquí no es una
  decisión neutra — es, de hecho, la decisión ya tomada arriba, pero
  cualquier lanzamiento público debe revisitarla explícitamente.

## 7. Próxima revisión

Esta evaluación debe revisarse:
1. Antes de cualquier lanzamiento público con usuarios reales (obligatorio, ver §4).
2. Ante cualquier cambio de proveedor de modelo.
3. Cada 6 meses como práctica de gobernanza continua (ISO 42001 exige
   revisión periódica del sistema de gestión, no una evaluación única).
